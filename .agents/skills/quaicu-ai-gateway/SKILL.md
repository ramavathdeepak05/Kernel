---
name: quaicu-ai-gateway
description: |
  QUAICU K·05 AI Gateway — pluggable inference, PII masking, prompt logging (mandatory/fail-closed),
  model routing policies, cost governance, and the InferencePort interface. Use when building
  core/gateway/, adapters/inference/, or any code that calls a model. Enforces: InferencePort only
  (never import model SDKs in core), fail-closed prompt logging (unlogged call = denied call),
  PII masking before transmission, fail-closed model routing (no unapproved fallback), per-tenant
  cost budgets. Trigger keywords: InferencePort, AI Gateway, inference, model, prompt, PII, masking,
  model_routing, cost_budget, prompt_logging, ModelRef, ModelResponse, generate, vllm, ollama,
  openai, anthropic, bedrock, azure_openai, vertex, circuit_breaker, retry, deduplication,
  idempotency, presidio, token_map_encryption, budget_reset.
---

# QUAICU K·05 AI Gateway

You are the AI Gateway correctness enforcer. The gateway is the governance layer between the kernel
and any model. Every model call must be: governed (recorded to the ledger), masked (PII removed),
routed by policy (only approved models), and logged (fail-closed — if it can't be logged, it's denied).
This document is the complete implementation reference. Every section must be implemented exactly.

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every gateway choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → DENY the model call.

### Invariants — never violated
- ALWAYS call models through `InferencePort`. NEVER `import openai|anthropic|boto3|google.cloud` in core/ (F-08).
- ALWAYS log the call BEFORE sending it. If logging fails → DENY. An unlogged model call is ungoverned and forbidden.
- ALWAYS mask PII BEFORE the prompt leaves the gateway. The port receives masked text; the token map is stored per-tenant.
- ALWAYS route by policy. No approved model for this action/tenant → `GatewayDeniedError`. NEVER fall back to an unapproved model.
- ALWAYS per-tenant prompt logs and token maps. NEVER shared (F-07).

### Governed generate flow (exact order — do not reorder)
1. resolve route via policy → None → DENY (no fallback).
2. check cost budget → exhausted → DENY (default `block`).
3. mask PII → store token map (per-tenant).
4. log_start (fail-closed: if it fails, DENY before calling the model).
5. call `InferencePort.generate`.
6. record output for ledger replay (non-determinism recorded here).
7. log_complete + seal.

### Decision table
| Situation | Do exactly this |
|---|---|
| Policy returns no approved model | raise `GatewayDeniedError` (no fallback) |
| Prompt log write fails (start) | DENY before the model call |
| Budget exhausted, behavior=block (default) | DENY |
| Budget exhausted, behavior=degrade | route to a cheaper *approved* model only |
| Tenant-declared PII field present | mask it; map stored per-tenant, never in the prompt |
| Provider down/timeout | raise `InferencePortError`/`PortTimeoutError` → caller DENIES |

### Tie-break rules
- Fall back to another model? → NEVER, unless that model is also policy-approved for this tenant+action.
- Proceed when logging is flaky? → DENY. No log = no call.
- Is this field PII? → assume yes and mask it. Over-masking is safe; leaking is not.

### Stop-and-apply triggers
- About to call `generate` before `log_start` succeeded? → STOP, log first.
- About to send a prompt before masking? → STOP, mask first.
- About to pick a default/fallback model? → STOP, confirm policy approves it.

### Self-check
- [ ] No model SDK import in core/; all calls via InferencePort.
- [ ] log_start precedes generate and is fail-closed.
- [ ] PII masked before transmission; token map per-tenant.
- [ ] No unapproved fallback; None route → deny.
- [ ] Budget-exhausted default is block (deny).

## Frozen Decisions That Apply Here

| ADR | Rule |
|-----|------|
| F-08 | Core never imports a model SDK. All calls go through `InferencePort`. |
| F-02 | Governance is model-agnostic. Routing is a policy decision, not a hardcoded model preference. |
| F-03 | Fail-closed everywhere. No approved model → DENY. Log failure → DENY. Budget exhausted → DENY. |
| F-07 | Per-tenant prompt logs and token maps. Never shared. |

---

## Error Type Hierarchy

```python
# core/gateway/errors.py

class GatewayError(Exception):
    """Base for all AI Gateway errors. Never raised directly."""
    error_code: str = "GW_000"

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context

class GatewayDeniedError(GatewayError):
    """The call was denied. Fail-closed outcome — action lifecycle → HALTED."""
    error_code = "GW_001"

class GatewayNoApprovedModelError(GatewayDeniedError):
    """No approved model available for this action/tenant combination."""
    error_code = "GW_002"

class GatewayLogFailureError(GatewayDeniedError):
    """pre-call logging failed — unlogged call is ungoverned, deny it."""
    error_code = "GW_003"

class GatewayPIIMaskingError(GatewayDeniedError):
    """PII masking failed. Sending unmasked content is not permitted."""
    error_code = "GW_004"

class GatewayBudgetExhaustedError(GatewayDeniedError):
    """Per-tenant cost budget exhausted. Behavior = block (fail-closed default)."""
    error_code = "GW_005"

class GatewayCircuitOpenError(GatewayDeniedError):
    """Circuit breaker is open for this provider. No call attempted."""
    error_code = "GW_006"

class GatewayInferenceError(GatewayError):
    """Inference call failed (network, provider error, timeout). May be retried."""
    error_code = "GW_007"
    def __init__(self, message: str, provider: str, status_code: int | None = None, **ctx):
        super().__init__(message, **ctx)
        self.provider = provider
        self.status_code = status_code

class GatewayRetryExhaustedError(GatewayDeniedError):
    """All retry attempts failed. Final fail-closed outcome."""
    error_code = "GW_008"

class GatewayTokenMapError(GatewayError):
    """Token map encryption/decryption failed."""
    error_code = "GW_009"

class GatewayDeduplicationError(GatewayError):
    """Idempotency key already used with different parameters — reject."""
    error_code = "GW_010"

class GatewayRoutingError(GatewayDeniedError):
    """Model routing policy evaluation failed — fail-closed."""
    error_code = "GW_011"
```

---

## Architecture: InferencePort (Frozen Decision F-08)

Core NEVER imports a model SDK. Every model call goes through `InferencePort`.

```python
# core/ports/inference.py
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass, field


@dataclass
class Prompt:
    system: str | None
    messages: list[dict]          # OpenAI-compatible message format
    temperature: float = 0.0      # determinism by default for governed calls
    max_tokens: int | None = None
    metadata: dict = field(default_factory=dict)  # non-transmitted context


@dataclass
class ModelRef:
    provider: str       # "ollama" | "vllm" | "openai" | "anthropic" | "bedrock" | "azure_openai" | "vertex"
    model_id: str       # e.g. "llama3:8b", "gpt-4o", "claude-sonnet-4-6"
    tenant_id: str
    is_approved: bool   # resolved from Model Registry (K·08) before calling
    priority: int = 0   # higher = preferred when multiple approved models available
    tier: str = "cloud" # "local" | "cloud" | "hyperscaler"

    def __post_init__(self):
        if not self.is_approved:
            raise GatewayNoApprovedModelError(
                f"ModelRef constructed with is_approved=False: {self.model_id}",
                provider=self.provider,
                model_id=self.model_id,
            )


@dataclass
class ModelResponse:
    content: str
    model_id: str
    provider: str
    prompt_hash: str       # SHA-256 of the MASKED prompt (hex) — for ledger
    response_hash: str     # SHA-256 of the raw response content (hex)
    tokens_input: int
    tokens_output: int
    tokens_used: int       # total = tokens_input + tokens_output
    cost_usd: str          # string decimal — never float (precision required for chargeback)
    latency_ms: int
    finish_reason: str     # "stop" | "length" | "content_filter" | "error"


class InferencePort(Protocol):
    async def generate(
        self,
        *,
        prompt: Prompt,
        model_ref: ModelRef,
        tenant: str,
    ) -> ModelResponse: ...
```

---

## Full Cost Calculation Table Per Provider

Costs in USD per 1000 tokens (input / output). Update when providers change pricing.
Store as config, not hardcoded — these change frequently.

```python
# core/gateway/cost_table.py
"""
Provider cost table. Input: cost per 1k input tokens.
Output: cost per 1k output tokens. All in USD.
Source: provider pricing pages as of June 2026. Must be kept updated.
These are defaults; per-tenant overrides are supported via config.
"""
from decimal import Decimal

# Structure: provider -> model_id_prefix -> (input_per_1k, output_per_1k)
COST_TABLE: dict[str, dict[str, tuple[Decimal, Decimal]]] = {
    "openai": {
        "gpt-4o":              (Decimal("0.005"),   Decimal("0.015")),
        "gpt-4o-mini":         (Decimal("0.00015"), Decimal("0.0006")),
        "gpt-4-turbo":         (Decimal("0.010"),   Decimal("0.030")),
        "gpt-3.5-turbo":       (Decimal("0.0005"),  Decimal("0.0015")),
        "o1":                  (Decimal("0.015"),   Decimal("0.060")),
        "o1-mini":             (Decimal("0.003"),   Decimal("0.012")),
        "o3":                  (Decimal("0.010"),   Decimal("0.040")),
    },
    "anthropic": {
        "claude-opus-4":       (Decimal("0.015"),   Decimal("0.075")),
        "claude-sonnet-4-6":   (Decimal("0.003"),   Decimal("0.015")),
        "claude-haiku-3-5":    (Decimal("0.001"),   Decimal("0.005")),
    },
    "bedrock": {
        # AWS Bedrock adds ~10% surcharge on top of model base price
        "anthropic.claude":    (Decimal("0.0033"),  Decimal("0.0165")),
        "meta.llama3":         (Decimal("0.0009"),  Decimal("0.0009")),
        "amazon.titan":        (Decimal("0.0008"),  Decimal("0.0016")),
    },
    "azure_openai": {
        "gpt-4o":              (Decimal("0.005"),   Decimal("0.015")),
        "gpt-4-turbo":         (Decimal("0.010"),   Decimal("0.030")),
    },
    "vertex": {
        "gemini-1.5-pro":      (Decimal("0.00125"), Decimal("0.005")),
        "gemini-1.5-flash":    (Decimal("0.000075"),Decimal("0.0003")),
        "gemini-2.0-flash":    (Decimal("0.0001"),  Decimal("0.0004")),
    },
    "ollama": {
        # Local inference: no token cost, but resource cost tracked separately
        "*":                   (Decimal("0"),       Decimal("0")),
    },
    "vllm": {
        "*":                   (Decimal("0"),       Decimal("0")),
    },
}


def estimate_cost(model_ref: ModelRef, input_tokens: int, output_tokens: int) -> Decimal:
    """
    Returns estimated cost in USD as a Decimal (exact arithmetic — never float).
    Falls back to wildcard "*" entry if exact model_id not found.
    Returns Decimal("0") for local providers.
    """
    provider = COST_TABLE.get(model_ref.provider, {})
    # Try exact match, then prefix match, then wildcard
    entry = (
        provider.get(model_ref.model_id)
        or next(
            (v for k, v in provider.items() if model_ref.model_id.startswith(k)),
            None,
        )
        or provider.get("*")
    )
    if entry is None:
        # Unknown model/provider: fail-closed — do not assume zero cost
        raise GatewayError(
            f"No cost entry for provider={model_ref.provider} model={model_ref.model_id}. "
            "Add to COST_TABLE before use.",
            error_code="GW_012",
        )
    input_rate, output_rate = entry
    return (input_rate * input_tokens + output_rate * output_tokens) / Decimal("1000")
```

---

## Full PII Detection Pipeline

PII masking runs in three ordered layers. Tenant-declared fields are the backbone; regex/NER
catch free-text leakage. All three run before any content leaves the tenant boundary.

```python
# core/gateway/pii_masker.py
from __future__ import annotations
import re
import json
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any
from opentelemetry import trace

tracer = trace.get_tracer("quaicu.gateway.pii")

# ---------------------------------------------------------------------------
# Token format
# ---------------------------------------------------------------------------
TOKEN_PREFIX = "[REDACTED:"
TOKEN_SUFFIX = "]"
# Token format: [REDACTED:TYPE:UUID4_8CHARS]  e.g. [REDACTED:EMAIL:a3f7bc12]
# Chosen to be unlikely to appear in natural language and easy to find with regex.

TOKEN_PATTERN = re.compile(r'\[REDACTED:[A-Z_]+:[0-9a-f]{8}\]')


@dataclass
class PIISpan:
    start: int
    end: int
    pii_type: str
    original_value: str
    token: str


@dataclass
class MaskingReport:
    """Recorded per-action — so the masking guarantee is never ambiguous (§3.12)."""
    applied_layers: list[str]          # which layers ran: ["declared_fields", "regex", "ner"]
    spans_detected: int                # total PII spans found
    ner_available: bool                # NER was configured and ran
    residual_risk: str                 # "none" | "low" | "best_effort"


# ---------------------------------------------------------------------------
# Layer 1: Tenant-declared sensitive fields
# ---------------------------------------------------------------------------

DECLARED_FIELD_REGISTRY: dict[str, set[str]] = {}  # tenant_id → set of field paths


async def mask_declared_fields(
    obj: Any,
    tenant_id: str,
    schema_registry,
    token_map: dict[str, str],
) -> tuple[Any, list[PIISpan]]:
    """
    Recursively walk action payload/prompt and replace values at declared sensitive
    field paths (dot-notation) with tokens.

    Example declared fields: ["payload.ssn", "payload.account_number", "messages.*.content"]
    """
    sensitive_paths = await schema_registry.get_sensitive_fields(tenant_id)
    spans: list[PIISpan] = []
    result = _mask_at_paths(obj, sensitive_paths, token_map, spans, path="")
    return result, spans


def _mask_at_paths(
    obj: Any,
    paths: set[str],
    token_map: dict[str, str],
    spans: list[PIISpan],
    path: str,
) -> Any:
    """Recursive field masker. Handles dicts, lists, and scalar strings."""
    if isinstance(obj, dict):
        return {
            k: _mask_at_paths(v, paths, token_map, spans, f"{path}.{k}" if path else k)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _mask_at_paths(item, paths, token_map, spans, f"{path}[*]")
            for item in obj
        ]
    if isinstance(obj, str):
        # Check if current path (or wildcard variant) is in sensitive_paths
        if path in paths or _wildcard_match(path, paths):
            token = _make_token("DECLARED")
            token_map[token] = obj
            spans.append(PIISpan(0, len(obj), "DECLARED", obj, token))
            return token
    return obj


def _wildcard_match(path: str, paths: set[str]) -> bool:
    """Check path against wildcard patterns like 'messages[*].content'."""
    normalized = re.sub(r'\[\d+\]', '[*]', path)
    return normalized in paths


# ---------------------------------------------------------------------------
# Layer 2: Regex detectors (free-text leakage)
# ---------------------------------------------------------------------------

# Pattern registry: type → compiled regex
# Extend as needed; add test coverage for each new pattern.
REGEX_DETECTORS: list[tuple[str, re.Pattern]] = [
    ("EMAIL",        re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b')),
    ("PHONE_IN",     re.compile(r'\b(?:\+91[\-\s]?)?[6-9]\d{9}\b')),            # Indian mobile
    ("PHONE_INTL",   re.compile(r'\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}')),
    ("PAN_IN",       re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')),                 # India PAN card
    ("AADHAAR_IN",   re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')),         # Aadhaar
    ("SSN_US",       re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("CREDIT_CARD",  re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b')),
    ("IBAN",         re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b')),
    ("IP_ADDRESS",   re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')),
    ("DATE_DMY",     re.compile(r'\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b')), # date of birth proxy
]


def mask_with_regex(
    text: str,
    token_map: dict[str, str],
) -> tuple[str, list[PIISpan]]:
    """
    Apply regex detectors to a text string. Returns masked text and detected spans.
    Detectors run in order; earlier matches take priority (no double-masking).
    """
    spans: list[PIISpan] = []
    # Collect all matches first, then apply right-to-left to preserve offsets
    all_matches: list[tuple[int, int, str, str]] = []  # (start, end, pii_type, value)
    for pii_type, pattern in REGEX_DETECTORS:
        for m in pattern.finditer(text):
            # Don't double-mask already tokenized spans
            if not TOKEN_PATTERN.match(text[m.start():m.end()]):
                all_matches.append((m.start(), m.end(), pii_type, m.group()))

    # Sort by start descending for right-to-left replacement
    all_matches.sort(key=lambda x: x[0], reverse=True)
    for start, end, pii_type, value in all_matches:
        token = _make_token(pii_type)
        token_map[token] = value
        spans.append(PIISpan(start, end, pii_type, value, token))
        text = text[:start] + token + text[end:]

    return text, spans


# ---------------------------------------------------------------------------
# Layer 3: NER (optional, configurable per tenant)
# ---------------------------------------------------------------------------

async def mask_with_ner(
    text: str,
    token_map: dict[str, str],
    ner_client,  # NERPort — tenant-configured, may be None
) -> tuple[str, list[PIISpan]]:
    """
    Optional NER pass for unstructured text. Uses presidio or a local NER model
    behind a NERPort interface (never imported directly in core).

    If ner_client is None, returns text unchanged.
    NER errors do NOT fail the call — log a warning and continue.
    Residual risk is recorded in MaskingReport.
    """
    if ner_client is None:
        return text, []
    try:
        entities = await ner_client.analyze(text)
        spans: list[PIISpan] = []
        # Apply right-to-left
        for ent in sorted(entities, key=lambda e: e.start, reverse=True):
            token = _make_token(ent.entity_type)
            token_map[token] = text[ent.start:ent.end]
            spans.append(PIISpan(ent.start, ent.end, ent.entity_type,
                                 text[ent.start:ent.end], token))
            text = text[:ent.start] + token + text[ent.end:]
        return text, spans
    except Exception as e:
        # NER failure → log warning, continue without NER — residual risk increases
        tracer.get_tracer("quaicu.gateway.pii").start_as_current_span(
            "gateway.pii.ner_error"
        ).__enter__().record_exception(e)
        return text, []


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def _make_token(pii_type: str) -> str:
    token_id = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
    return f"{TOKEN_PREFIX}{pii_type}:{token_id}{TOKEN_SUFFIX}"


# ---------------------------------------------------------------------------
# PIIMasker (orchestrates all three layers)
# ---------------------------------------------------------------------------

class PIIMasker:
    """
    Full PII masking pipeline.

    Detection order (§3.12):
    1. Tenant-declared sensitive fields — reliable backbone (exact paths)
    2. Regex detectors — catch free-text leakage (patterns)
    3. NER (optional, per-tenant config) — catch unstructured entity mentions

    Token map is AES-GCM encrypted at rest (see TokenMapStore below).
    Token map NEVER leaves the tenant boundary — only token_ref (a UUID) is passed to model.
    Rehydration is in-tenant only.

    IMPORTANT: Free-text masking is best-effort. For maximum-sensitivity workloads use the
    Sovereign tier (local inference, nothing transmitted). The kernel records which masking
    layers were applied per action — the guarantee is never ambiguous.
    """

    def __init__(self, schema_registry, token_map_store, ner_client=None):
        self.schema_registry = schema_registry
        self.token_map_store = token_map_store  # TokenMapStore (encrypted at rest)
        self.ner_client = ner_client

    async def mask(
        self,
        prompt: Prompt,
        tenant_id: str,
    ) -> tuple[Prompt, str, MaskingReport]:
        """
        Returns: (masked_prompt, token_ref, masking_report).
        token_ref is a UUID pointing to the encrypted token map in tenant storage.
        Raises GatewayPIIMaskingError if any layer fails critically.
        """
        with tracer.start_as_current_span(
            "gateway.pii.mask",
            attributes={"tenant_id": tenant_id},
        ) as span:
            token_map: dict[str, str] = {}
            total_spans = 0
            applied_layers: list[str] = []

            try:
                # Layer 1: declared fields
                masked_messages = []
                for msg in prompt.messages:
                    content, spans = await mask_declared_fields(
                        msg.get("content", ""),
                        tenant_id,
                        self.schema_registry,
                        token_map,
                    )
                    masked_messages.append({**msg, "content": content})
                    total_spans += len(spans)
                applied_layers.append("declared_fields")

                masked_system = prompt.system or ""
                if masked_system:
                    masked_system, sys_spans = await mask_declared_fields(
                        masked_system, tenant_id, self.schema_registry, token_map
                    )
                    total_spans += len(sys_spans)

                # Layer 2: regex on all text fields
                for i, msg in enumerate(masked_messages):
                    content, spans = mask_with_regex(str(msg.get("content", "")), token_map)
                    masked_messages[i] = {**msg, "content": content}
                    total_spans += len(spans)
                if masked_system:
                    masked_system, sys_spans = mask_with_regex(masked_system, token_map)
                    total_spans += len(sys_spans)
                applied_layers.append("regex")

                # Layer 3: NER (optional)
                ner_available = False
                if self.ner_client is not None:
                    for i, msg in enumerate(masked_messages):
                        content, spans = await mask_with_ner(
                            str(msg.get("content", "")), token_map, self.ner_client
                        )
                        masked_messages[i] = {**msg, "content": content}
                        total_spans += len(spans)
                    applied_layers.append("ner")
                    ner_available = True

                # Determine residual risk
                residual_risk = "none" if ner_available else (
                    "low" if "declared_fields" in applied_layers else "best_effort"
                )

                # Encrypt and store token map — never pass raw map outside this method
                token_ref = await self.token_map_store.store(tenant_id, token_map)

                masked_prompt = Prompt(
                    system=masked_system if prompt.system else None,
                    messages=masked_messages,
                    temperature=prompt.temperature,
                    max_tokens=prompt.max_tokens,
                )

                span.set_attribute("gateway.pii.spans_detected", total_spans)
                span.set_attribute("gateway.pii.layers", ",".join(applied_layers))

                report = MaskingReport(
                    applied_layers=applied_layers,
                    spans_detected=total_spans,
                    ner_available=ner_available,
                    residual_risk=residual_risk,
                )
                return masked_prompt, token_ref, report

            except GatewayPIIMaskingError:
                raise
            except Exception as e:
                raise GatewayPIIMaskingError(
                    f"PII masking pipeline failed: {e}",
                    tenant_id=tenant_id,
                ) from e

    def rehydrate(self, text: str, token_ref: str, tenant_id: str) -> str:
        """Replace all tokens in text with their original values. Synchronous — no I/O."""
        token_map = self.token_map_store.get_sync(tenant_id, token_ref)
        for token, value in token_map.items():
            text = text.replace(token, value)
        return text
```

---

## Token Map Encryption at Rest (AES-GCM)

Token maps contain the actual PII values. They are encrypted at rest using AES-256-GCM with
a per-tenant key from OpenBao. The map never leaves tenant storage unencrypted.

```python
# core/gateway/token_map_store.py
import json
import os
from base64 import b64encode, b64decode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenMapStore:
    """
    Stores encrypted token maps in per-tenant storage.
    Encryption: AES-256-GCM. Key sourced from OpenBao per tenant.
    Nonce: 12 random bytes, unique per encryption operation.

    token_ref = "{tenant_id}:{uuid4}" — opaque to callers, used for lookup + deletion.
    TTL: token maps are deleted after the governed action is sealed (default) or after
    a configurable retention window (max: action retention policy for the tenant).
    """

    def __init__(self, storage, key_port):
        self.storage = storage    # per-tenant blob storage
        self.key_port = key_port  # OpenBao key port — provides AES key bytes

    async def store(self, tenant_id: str, token_map: dict[str, str]) -> str:
        """Encrypt and store token_map. Returns token_ref (opaque UUID)."""
        key_bytes = await self.key_port.get_aes_key(tenant_id=tenant_id)
        aesgcm = AESGCM(key_bytes)
        nonce = os.urandom(12)
        plaintext = json.dumps(token_map, ensure_ascii=True).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=tenant_id.encode())
        # Store: nonce || ciphertext (both b64 encoded for JSON storage)
        blob = json.dumps({
            "n": b64encode(nonce).decode(),
            "c": b64encode(ciphertext).decode(),
        })
        token_ref = await self.storage.store_token_map_blob(tenant_id, blob)
        return token_ref

    def get_sync(self, tenant_id: str, token_ref: str) -> dict[str, str]:
        """Decrypt and return token map. Synchronous for use in rehydrate()."""
        blob_json = self.storage.get_token_map_blob_sync(tenant_id, token_ref)
        blob = json.loads(blob_json)
        key_bytes = self.key_port.get_aes_key_sync(tenant_id=tenant_id)
        aesgcm = AESGCM(key_bytes)
        nonce = b64decode(blob["n"])
        ciphertext = b64decode(blob["c"])
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=tenant_id.encode())
        return json.loads(plaintext.decode())

    async def delete(self, tenant_id: str, token_ref: str) -> None:
        """Delete token map after action is sealed. Called by gateway post-seal."""
        await self.storage.delete_token_map_blob(tenant_id, token_ref)
```

---

## Circuit Breaker Per Provider

Each inference provider gets its own circuit breaker. A failing provider opens the circuit;
calls to that provider are denied fast rather than accumulating timeouts.

```python
# core/gateway/circuit_breaker.py
import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field


class CircuitState(Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing — fast-deny all calls
    HALF_OPEN = "half_open" # probing — allow one call to test recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5         # consecutive failures to open
    success_threshold: int = 2         # consecutive successes in HALF_OPEN to close
    timeout_seconds: float = 60.0      # time in OPEN before moving to HALF_OPEN
    half_open_probe_count: int = 1     # calls to allow in HALF_OPEN


@dataclass
class CircuitBreaker:
    provider: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _success_count: int = 0
    _opened_at: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def call(self, fn, *args, **kwargs):
        """
        Execute fn through the circuit breaker.
        Raises GatewayCircuitOpenError if circuit is OPEN.
        Updates failure/success counts and transitions state accordingly.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at > self.config.timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise GatewayCircuitOpenError(
                        f"Circuit OPEN for provider {self.provider}",
                        provider=self.provider,
                    )

        try:
            result = await fn(*args, **kwargs)
            async with self._lock:
                self._on_success()
            return result
        except GatewayInferenceError:
            async with self._lock:
                self._on_failure()
            raise

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def _on_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    @property
    def state(self) -> CircuitState:
        return self._state


# Registry: one circuit breaker per (tenant_id, provider)
_breakers: dict[tuple[str, str], CircuitBreaker] = {}


def get_circuit_breaker(tenant_id: str, provider: str) -> CircuitBreaker:
    key = (tenant_id, provider)
    if key not in _breakers:
        _breakers[key] = CircuitBreaker(provider=provider)
    return _breakers[key]
```

---

## Retry with Exponential Backoff

Transient failures (network hiccup, provider 429/503) are retried. Non-transient failures
(auth error, bad request, circuit open) are not.

```python
# core/gateway/retry.py
import asyncio
import random
from opentelemetry import trace

tracer = trace.get_tracer("quaicu.gateway.retry")

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

RETRY_CONFIG = {
    "max_attempts": 3,
    "base_delay_seconds": 0.5,
    "max_delay_seconds": 30.0,
    "jitter_factor": 0.25,  # ±25% jitter to prevent thundering herd
    "backoff_multiplier": 2.0,
}


async def with_retry(fn, *, provider: str, max_attempts: int = RETRY_CONFIG["max_attempts"]):
    """
    Execute fn with exponential backoff. Only retries GatewayInferenceError with
    transient status codes. All other exceptions propagate immediately.

    If all retries are exhausted → raises GatewayRetryExhaustedError (fail-closed).
    """
    delay = RETRY_CONFIG["base_delay_seconds"]
    last_exc = None

    with tracer.start_as_current_span(
        "gateway.retry",
        attributes={"provider": provider, "max_attempts": max_attempts},
    ) as span:
        for attempt in range(1, max_attempts + 1):
            try:
                result = await fn()
                span.set_attribute("gateway.retry.attempts", attempt)
                return result
            except GatewayInferenceError as exc:
                last_exc = exc
                if exc.status_code not in TRANSIENT_STATUS_CODES:
                    # Non-transient — do not retry
                    span.set_attribute("gateway.retry.non_transient", True)
                    raise
                if attempt == max_attempts:
                    break
                # Exponential backoff with jitter
                jitter = delay * RETRY_CONFIG["jitter_factor"] * (random.random() * 2 - 1)
                sleep_time = min(delay + jitter, RETRY_CONFIG["max_delay_seconds"])
                span.add_event(f"retry.attempt.{attempt}", {
                    "delay_ms": int(sleep_time * 1000),
                    "status_code": exc.status_code or 0,
                })
                await asyncio.sleep(sleep_time)
                delay *= RETRY_CONFIG["backoff_multiplier"]
            except (GatewayCircuitOpenError, GatewayDeniedError):
                raise  # never retry a denied call

        raise GatewayRetryExhaustedError(
            f"All {max_attempts} retry attempts failed for provider {provider}",
            provider=provider,
        ) from last_exc
```

---

## Request Deduplication (Idempotency Key)

The same idempotency key on two calls with identical parameters returns the cached response.
The same key with different parameters is rejected (conflict). This prevents double-billing
and double side-effects on retried requests from the lifecycle engine.

```python
# core/gateway/deduplication.py
import json
import hashlib
from opentelemetry import trace

tracer = trace.get_tracer("quaicu.gateway.dedup")


class IdempotencyStore:
    """
    Per-tenant idempotency store. Keyed by (tenant_id, idempotency_key).
    Stores: request_fingerprint, cached_response, status.
    TTL: 24 hours (configurable).
    """

    def __init__(self, storage):
        self.storage = storage

    async def check_or_reserve(
        self,
        tenant_id: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[bool, dict | None]:
        """
        Returns (is_duplicate, cached_response).
        - (False, None): first time — proceed, slot reserved.
        - (True, response): exact duplicate — return cached response.
        - Raises GatewayDeduplicationError if same key with different fingerprint.
        """
        existing = await self.storage.get_idempotency_record(tenant_id, idempotency_key)
        if existing is None:
            await self.storage.create_idempotency_record(
                tenant_id, idempotency_key, request_fingerprint
            )
            return False, None
        if existing["fingerprint"] != request_fingerprint:
            raise GatewayDeduplicationError(
                f"Idempotency key {idempotency_key!r} reused with different parameters",
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
            )
        if existing["status"] == "completed" and existing.get("response"):
            return True, existing["response"]
        # status == "in_progress" — caller should retry with backoff
        return False, None

    async def complete(
        self,
        tenant_id: str,
        idempotency_key: str,
        response: dict,
    ) -> None:
        await self.storage.update_idempotency_record(
            tenant_id, idempotency_key, status="completed", response=response
        )


def make_request_fingerprint(prompt: Prompt, model_ref: ModelRef) -> str:
    """Stable fingerprint of a (prompt, model) pair — used for deduplication check."""
    obj = {
        "messages": prompt.messages,
        "system": prompt.system,
        "model_id": model_ref.model_id,
        "provider": model_ref.provider,
        "temperature": prompt.temperature,
    }
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()
```

---

## Cost Governor — Budget Period Reset Logic

```python
# core/gateway/cost_governor.py
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from opentelemetry import trace, metrics

tracer = trace.get_tracer("quaicu.gateway.cost")
meter = metrics.get_meter("quaicu.gateway.cost")
_budget_exceeded_ctr = meter.create_counter(
    "gateway.budget.exceeded", description="Budget exhaustion events"
)
_cost_histogram = meter.create_histogram(
    "gateway.cost.usd", description="Per-call cost in USD", unit="usd"
)


class BudgetPeriod:
    """Supported budget periods. Resets are computed as wall-clock boundaries."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ROLLING_30D = "rolling_30d"

    @staticmethod
    def get_period_start(period: str, now: datetime) -> datetime:
        """Return the start of the current budget period."""
        if period == BudgetPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == BudgetPeriod.WEEKLY:
            days_since_monday = now.weekday()
            return (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if period == BudgetPeriod.MONTHLY:
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period == BudgetPeriod.ROLLING_30D:
            return now - timedelta(days=30)
        raise ValueError(f"Unknown budget period: {period}")


class CostGovernor:
    """
    Per-tenant token/cost budget enforcement.
    Budget behavior: "block" (default/fail-closed) | "degrade" | "alert".
    Budget periods: daily | weekly | monthly | rolling_30d.

    On period reset: usage is zeroed at the period boundary.
    Budget config and usage are stored per-tenant — never shared.
    """

    def __init__(self, storage, model_registry=None):
        self.storage = storage
        self.model_registry = model_registry

    async def check_and_reserve(
        self,
        tenant_id: str,
        estimated_cost: Decimal,
        model_ref: ModelRef,
    ) -> str:
        """
        Check budget and reserve estimated_cost. Returns reservation_id.
        Raises GatewayBudgetExhaustedError if blocked.
        If behavior == "degrade", returns a cheaper approved model_ref instead.
        """
        with tracer.start_as_current_span(
            "gateway.cost.check",
            attributes={"tenant_id": tenant_id, "estimated_cost_usd": float(estimated_cost)},
        ) as span:
            budget = await self.storage.get_budget(tenant_id)
            if budget is None:
                # No budget configured → allow but log (not fail-closed for cost-unmanaged tenants)
                span.set_attribute("gateway.cost.budget_configured", False)
                return "no_budget"

            # Period reset: check if usage should be zeroed
            now = datetime.now(timezone.utc)
            period_start = BudgetPeriod.get_period_start(budget.period, now)
            usage_since = await self.storage.get_usage_since(tenant_id, period_start)

            remaining = Decimal(str(budget.limit_usd)) - usage_since
            span.set_attribute("gateway.cost.remaining_usd", float(remaining))
            span.set_attribute("gateway.cost.limit_usd", float(budget.limit_usd))

            if usage_since + estimated_cost > Decimal(str(budget.limit_usd)):
                _budget_exceeded_ctr.add(1, {"tenant_id": tenant_id})
                behavior = getattr(budget, "on_exhaustion", "block")

                if behavior == "block":
                    raise GatewayBudgetExhaustedError(
                        f"Tenant {tenant_id} cost budget exhausted "
                        f"(used={usage_since}, limit={budget.limit_usd}, "
                        f"estimated={estimated_cost})",
                        tenant_id=tenant_id,
                    )
                elif behavior == "degrade":
                    # Route to cheapest permitted model — still from approved list only
                    cheaper = await self._find_cheapest_approved_model(tenant_id, model_ref)
                    if cheaper is None:
                        raise GatewayBudgetExhaustedError(
                            f"No cheaper approved model available for degraded mode",
                            tenant_id=tenant_id,
                        )
                    return await self._reserve(tenant_id, estimated_cost)
                elif behavior == "alert":
                    # Log alert but allow — operator has configured non-blocking behavior
                    span.set_attribute("gateway.cost.alert_mode", True)

            reservation_id = await self._reserve(tenant_id, estimated_cost)
            _cost_histogram.record(float(estimated_cost), {"tenant_id": tenant_id,
                                                            "provider": model_ref.provider})
            return reservation_id

    async def finalize(
        self,
        tenant_id: str,
        reservation_id: str,
        actual_cost: Decimal,
    ) -> None:
        """Replace estimated reservation with actual cost. Called after inference completes."""
        if reservation_id == "no_budget":
            return
        await self.storage.finalize_cost_reservation(tenant_id, reservation_id, actual_cost)

    async def _reserve(self, tenant_id: str, amount: Decimal) -> str:
        return await self.storage.reserve_budget(tenant_id, amount)

    async def _find_cheapest_approved_model(
        self, tenant_id: str, original_ref: ModelRef
    ) -> ModelRef | None:
        if self.model_registry is None:
            return None
        approved = await self.model_registry.list_approved_models(tenant_id)
        local_models = [m for m in approved if m.tier == "local"]
        if local_models:
            return local_models[0]  # local is free
        # Sort by estimated cost for a 1k-token call
        priced = sorted(
            approved,
            key=lambda m: estimate_cost(m, 500, 500),
        )
        return priced[0] if priced else None
```

---

## Complete Provider Adapter with Error Normalization

All adapters in `adapters/inference/` implement `InferencePort` and normalize provider-specific
errors into `GatewayInferenceError` with a standard `status_code`. Core only sees
`GatewayInferenceError` — never a provider SDK exception.

```python
# adapters/inference/openai.py
from __future__ import annotations
import hashlib
import time
from decimal import Decimal

# SDK imported HERE only — never in core
from openai import AsyncOpenAI, APIStatusError, APIConnectionError, APITimeoutError

from core.ports.inference import InferencePort, Prompt, ModelRef, ModelResponse
from core.gateway.errors import GatewayInferenceError
from core.gateway.cost_table import estimate_cost


class OpenAIAdapter:
    """
    Implements InferencePort for OpenAI. Imports openai SDK here only — never in core.

    Error normalization:
    - APIStatusError(429)  → GatewayInferenceError(status_code=429) — transient, retried
    - APIStatusError(401)  → GatewayInferenceError(status_code=401) — auth, not retried
    - APIConnectionError   → GatewayInferenceError(status_code=503) — transient
    - APITimeoutError      → GatewayInferenceError(status_code=504) — transient
    - Other SDK errors     → GatewayInferenceError(status_code=500)
    """

    def __init__(self, api_key_provider):
        self._api_key_provider = api_key_provider  # OpenBao adapter for key retrieval

    async def generate(
        self,
        *,
        prompt: Prompt,
        model_ref: ModelRef,
        tenant: str,
    ) -> ModelResponse:
        api_key = await self._api_key_provider.get_key(
            key_name=f"openai/{tenant}", tenant_id=tenant
        )
        client = AsyncOpenAI(api_key=api_key)

        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": prompt.system})
        messages.extend(prompt.messages)

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=model_ref.model_id,
                messages=messages,
                temperature=prompt.temperature,
                max_tokens=prompt.max_tokens,
            )
        except APIStatusError as exc:
            raise GatewayInferenceError(
                f"OpenAI API error: {exc.message}",
                provider="openai",
                status_code=exc.status_code,
            ) from exc
        except APIConnectionError as exc:
            raise GatewayInferenceError(
                f"OpenAI connection error: {exc}",
                provider="openai",
                status_code=503,
            ) from exc
        except APITimeoutError as exc:
            raise GatewayInferenceError(
                f"OpenAI timeout",
                provider="openai",
                status_code=504,
            ) from exc
        except Exception as exc:
            raise GatewayInferenceError(
                f"OpenAI unexpected error: {exc}",
                provider="openai",
                status_code=500,
            ) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        content = response.choices[0].message.content or ""
        usage = response.usage

        # Compute hashes over masked content (prompt is already masked by gateway)
        prompt_text = " ".join(m.get("content", "") for m in messages)
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        response_hash = hashlib.sha256(content.encode()).hexdigest()

        # Cost: use actual token counts from response
        actual_cost = estimate_cost(
            model_ref,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

        return ModelResponse(
            content=content,
            model_id=model_ref.model_id,
            provider="openai",
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            tokens_input=usage.prompt_tokens,
            tokens_output=usage.completion_tokens,
            tokens_used=usage.total_tokens,
            cost_usd=str(actual_cost),
            latency_ms=latency_ms,
            finish_reason=response.choices[0].finish_reason or "stop",
        )
```

---

## The Governed Generate Flow (full implementation)

```python
# core/gateway/gateway.py
import hashlib
import time
from decimal import Decimal
from opentelemetry import trace, metrics

tracer = trace.get_tracer("quaicu.gateway")
meter  = metrics.get_meter("quaicu.gateway")

_call_counter    = meter.create_counter("gateway.calls.total",           description="Total model calls")
_call_errors     = meter.create_counter("gateway.calls.errors",          description="Model call failures by error code")
_call_duration   = meter.create_histogram("gateway.calls.duration_ms",   description="End-to-end call latency", unit="ms")
_token_counter   = meter.create_counter("gateway.tokens.total",          description="Tokens used")
_cost_counter    = meter.create_counter("gateway.cost.usd_total",        description="Total cost in USD cents")
_pii_spans_ctr   = meter.create_counter("gateway.pii.spans_detected",    description="PII spans detected")


class AIGateway:
    """
    K·05 AI Gateway. Orchestrates the full governed generate pipeline.
    All dependencies injected — no concrete imports from core.
    """

    def __init__(
        self,
        inference_port,       # InferencePort
        model_registry,       # K·08 Model Registry
        pii_masker,           # PIIMasker
        cost_governor,        # CostGovernor
        prompt_logger,        # PromptLogger
        idempotency_store,    # IdempotencyStore
        circuit_breakers,     # dict[str, CircuitBreaker] keyed by provider
    ):
        self.inference_port = inference_port
        self.model_registry = model_registry
        self.pii_masker = pii_masker
        self.cost_governor = cost_governor
        self.prompt_logger = prompt_logger
        self.idempotency_store = idempotency_store
        self.circuit_breakers = circuit_breakers

    async def call_model(
        self,
        *,
        action,
        prompt: Prompt,
        idempotency_key: str | None = None,
    ) -> ModelResponse:
        """
        Full governed generate pipeline. Any step failure → GatewayDeniedError (fail-closed).

        Steps:
        1.  Deduplication check (idempotency key)
        2.  PII masking (three-layer pipeline)
        3.  Model routing — fail-closed: no approved model → DENY
        4.  Cost budget check and reservation
        5.  Pre-call logging — FAIL-CLOSED: log failure → DENY
        6.  Circuit breaker + retry + inference
        7.  Post-call logging + cost finalization
        8.  Token rehydration (in-tenant only)
        9.  Token map cleanup
        """
        tenant = action.tenant_id
        t0 = time.monotonic()

        with tracer.start_as_current_span(
            "gateway.call_model",
            attributes={
                "gateway.tenant_id": tenant,
                "gateway.action_id": str(action.id),
                "gateway.action_type": action.type,
            },
        ) as span:
            try:
                result = await self._execute_pipeline(
                    action, prompt, tenant, idempotency_key, span
                )
                duration_ms = int((time.monotonic() - t0) * 1000)
                _call_counter.add(1, {"tenant_id": tenant, "status": "ok"})
                _call_duration.record(duration_ms, {"tenant_id": tenant})
                span.set_attribute("gateway.duration_ms", duration_ms)
                return result
            except GatewayError as exc:
                _call_errors.add(1, {
                    "tenant_id": tenant,
                    "error_code": exc.error_code,
                })
                span.record_exception(exc)
                span.set_attribute("gateway.error_code", exc.error_code)
                raise

    async def _execute_pipeline(self, action, prompt, tenant, idempotency_key, span):
        token_ref = None
        reservation_id = None
        call_id = None

        try:
            # Step 1: Deduplication
            if idempotency_key:
                fingerprint = make_request_fingerprint(prompt, ModelRef(
                    provider="unknown", model_id="unknown", tenant_id=tenant,
                    is_approved=True,
                ))
                is_dup, cached = await self.idempotency_store.check_or_reserve(
                    tenant, idempotency_key, fingerprint
                )
                if is_dup and cached:
                    span.set_attribute("gateway.deduplicated", True)
                    return ModelResponse(**cached)

            # Step 2: PII masking — fail-closed
            masked_prompt, token_ref, masking_report = await self.pii_masker.mask(
                prompt, tenant
            )
            span.set_attribute("gateway.pii.spans", masking_report.spans_detected)
            span.set_attribute("gateway.pii.residual_risk", masking_report.residual_risk)
            _pii_spans_ctr.add(
                masking_report.spans_detected, {"tenant_id": tenant}
            )

            # Step 3: Model routing — fail-closed
            model_ref = await self._route(action, tenant)
            if model_ref is None:
                raise GatewayNoApprovedModelError(
                    f"No approved model for action type {action.type!r} tenant {tenant!r}",
                    action_type=action.type,
                    tenant_id=tenant,
                )
            span.set_attribute("gateway.model_id", model_ref.model_id)
            span.set_attribute("gateway.provider", model_ref.provider)

            # Step 4: Cost budget check
            estimated_cost = estimate_cost(model_ref, 500, 500)  # rough estimate pre-call
            reservation_id = await self.cost_governor.check_and_reserve(
                tenant, estimated_cost, model_ref
            )

            # Step 5: Pre-call logging — MANDATORY, FAIL-CLOSED
            prompt_hash = hashlib.sha256(
                str(masked_prompt.messages).encode()
            ).hexdigest()
            try:
                call_id = await self.prompt_logger.log_start(
                    action_id=action.id,
                    tenant_id=tenant,
                    prompt_hash=prompt_hash,
                    model_ref=model_ref,
                )
            except Exception as log_exc:
                # An unlogged model call is ungoverned — deny
                raise GatewayLogFailureError(
                    f"Pre-call log failed: {log_exc}. Denying call (fail-closed).",
                    tenant_id=tenant,
                ) from log_exc

            # Step 6: Circuit breaker + retry + inference
            breaker = self.circuit_breakers.get(
                model_ref.provider,
                get_circuit_breaker(tenant, model_ref.provider),
            )
            response = await with_retry(
                lambda: breaker.call(
                    self.inference_port.generate,
                    prompt=masked_prompt,
                    model_ref=model_ref,
                    tenant=tenant,
                ),
                provider=model_ref.provider,
            )

            # Step 7: Post-call logging
            actual_cost = Decimal(response.cost_usd)
            await self.prompt_logger.log_complete(
                call_id=call_id,
                response_hash=response.response_hash,
                tokens_used=response.tokens_used,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
            )
            await self.cost_governor.finalize(tenant, reservation_id, actual_cost)

            _token_counter.add(response.tokens_used, {"tenant_id": tenant,
                                                       "provider": model_ref.provider})
            _cost_counter.add(
                int(actual_cost * 100),  # USD cents
                {"tenant_id": tenant, "provider": model_ref.provider},
            )

            # Step 8: Token rehydration (in-tenant only, never transmits PII)
            if token_ref:
                response.content = self.pii_masker.rehydrate(
                    response.content, token_ref, tenant
                )

            # Step 9: Token map cleanup
            if token_ref:
                await self.pii_masker.token_map_store.delete(tenant, token_ref)

            # Idempotency: store completed response
            if idempotency_key:
                await self.idempotency_store.complete(
                    tenant, idempotency_key, {
                        "content": response.content,
                        "model_id": response.model_id,
                        "provider": response.provider,
                        "prompt_hash": response.prompt_hash,
                        "response_hash": response.response_hash,
                        "tokens_input": response.tokens_input,
                        "tokens_output": response.tokens_output,
                        "tokens_used": response.tokens_used,
                        "cost_usd": response.cost_usd,
                        "latency_ms": response.latency_ms,
                        "finish_reason": response.finish_reason,
                    }
                )

            return response

        except GatewayDeniedError:
            # Log partial failure if we got a call_id
            if call_id:
                await self.prompt_logger.log_failure(call_id, "denied")
            raise
        except GatewayInferenceError as exc:
            if call_id:
                await self.prompt_logger.log_failure(call_id, str(exc))
            raise GatewayDeniedError(
                f"Inference failed after retries: {exc}",
                original_error=str(exc),
            ) from exc
```

---

## Prompt Logging Schema

```sql
-- Per-tenant schema (F-07)
CREATE TABLE "tenant_{tenant_id}".model_call_log (
    call_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id           UUID NOT NULL REFERENCES "tenant_{tenant_id}".ledger_entries(action_id)
                            DEFERRABLE INITIALLY DEFERRED,
    tenant_id           TEXT NOT NULL CHECK (tenant_id = '{tenant_id}'),
    model_id            TEXT NOT NULL,
    provider            TEXT NOT NULL,
    prompt_hash         TEXT NOT NULL,       -- SHA-256(hex) of masked prompt
    response_hash       TEXT,                -- SHA-256(hex) of response (NULL until complete)
    tokens_input        INT,
    tokens_output       INT,
    tokens_used         INT,
    cost_usd            NUMERIC(18, 8),      -- exact decimal, never float
    status              TEXT NOT NULL        -- "started" | "completed" | "failed"
                            CHECK (status IN ('started', 'completed', 'failed')),
    failure_reason      TEXT,
    latency_ms          INT,
    finish_reason       TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    retention_ref       TEXT,               -- reference to tenant blob storage for full content
    masking_layers      TEXT[],             -- which PII layers were applied
    pii_spans_detected  INT,
    residual_risk       TEXT                -- "none" | "low" | "best_effort"
);

-- Index for audit queries
CREATE INDEX ON "tenant_{tenant_id}".model_call_log (action_id);
CREATE INDEX ON "tenant_{tenant_id}".model_call_log (started_at);
CREATE INDEX ON "tenant_{tenant_id}".model_call_log (provider, status);
```

---

## Anti-Patterns Section

### Anti-Pattern 1: Importing a model SDK in core

```python
# WRONG — violates F-08; hard-couples core to a provider SDK
# core/gateway/gateway.py
from openai import AsyncOpenAI   # NEVER in core/

# CORRECT — import SDK only in adapters/inference/
# adapters/inference/openai.py
from openai import AsyncOpenAI   # correct location
```

### Anti-Pattern 2: Proceeding after log_start failure

```python
# WRONG — unlogged call is ungoverned; this violates the audit guarantee
try:
    call_id = await self.prompt_logger.log_start(...)
except Exception:
    pass  # silently continue — CATASTROPHIC BUG

# CORRECT — fail-closed: log failure = call denied
try:
    call_id = await self.prompt_logger.log_start(...)
except Exception as exc:
    raise GatewayLogFailureError(f"Pre-call log failed: {exc}") from exc
```

### Anti-Pattern 3: Falling back to an unapproved model

```python
# WRONG — silently uses an unapproved model when routing fails
if model_ref is None:
    model_ref = DEFAULT_MODEL  # governance bypass

# CORRECT — fail-closed: no approved model → deny
if model_ref is None:
    raise GatewayNoApprovedModelError(...)
```

### Anti-Pattern 4: Storing raw PII in token map outside tenant boundary

```python
# WRONG — token map transmitted to external logging service
await external_logger.log(token_map=token_map)

# CORRECT — token_map encrypted at rest in tenant storage; only token_ref crosses
# any boundary; map deleted after seal
token_ref = await token_map_store.store(tenant_id, token_map)
```

### Anti-Pattern 5: Using float for cost

```python
# WRONG — float arithmetic loses precision; chargeback disputes follow
cost = tokens_used * 0.002 / 1000  # float multiplication errors compound

# CORRECT — Decimal arithmetic, string serialization
from decimal import Decimal
cost = Decimal(str(tokens_used)) * Decimal("0.002") / Decimal("1000")
response.cost_usd = str(cost)  # never float in ModelResponse or DB
```

### Anti-Pattern 6: No circuit breaker on provider calls

```python
# WRONG — slow provider accumulates hanging connections
response = await client.generate(...)  # no timeout, no circuit

# CORRECT — all provider calls through circuit breaker + retry with backoff
response = await with_retry(
    lambda: breaker.call(self.inference_port.generate, ...),
    provider=model_ref.provider,
)
```

---

## Checklist Before Merging Any Gateway Change

- [ ] No model SDK imports in `core/gateway/` — only `InferencePort`
- [ ] `log_start()` failure raises `GatewayLogFailureError` — not silently proceeds
- [ ] PII masking (all three layers) runs BEFORE prompt is passed to `inference_port.generate()`
- [ ] Token map encrypted with AES-GCM via OpenBao key — never plaintext at rest
- [ ] Token map stored in tenant storage — never serialized to model, external log, or cross-tenant
- [ ] `route()` returns `None` → `GatewayNoApprovedModelError` — no unapproved fallback
- [ ] Cost uses `Decimal` arithmetic — never `float`
- [ ] Budget period reset logic tested for daily/weekly/monthly/rolling_30d
- [ ] Circuit breaker per provider — state shared across calls in the same process
- [ ] Retry with exponential backoff + jitter — only for transient status codes
- [ ] Idempotency key checked before masking — duplicate returns cached response
- [ ] Token map deleted after seal (post-pipeline cleanup)
- [ ] OTel spans and metrics: `gateway.call_model`, `gateway.pii.mask`, `gateway.cost.check`, `gateway.retry`
- [ ] Error normalization in every adapter: provider SDK exceptions → `GatewayInferenceError(status_code=N)`
- [ ] `masking_report.residual_risk` recorded in model_call_log per action
- [ ] All adapters in `adapters/inference/` — none in `core/`
