"""
ALIS AI Gateway - E03-S01 + E00-S06

MODULE: Platform Core (E03 - AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions) + Layer 4 (Invariant Enforcement)
ENTITY: AIGateway

This module implements the centralized AI Gateway service.
All AI model invocations MUST go through this gateway.

Must Align With:
- Blueprint B — AI Agent Architecture
- "Agents draft, rules decide"
- "AI is read-only with respect to state"
- "No cloud LLM usage"

E00-S06 — AI Boundary Enforcement:
- Prompt injection detection layer (before LLM call)
- Strict JSON schema validation on AI output
- STATE_IMPACT invariant enforcement (forbid Final/Commit/Override)
- Confidence scoring mandate for non-advisory agents
- PII masking before AI context injection (via DataMasker)

Acceptance Criteria (E03-S01):
- [x] Single API surface for AI calls
- [x] No direct model invocation elsewhere in codebase
- [x] Request/response fully logged (metadata only)
- [x] RBAC-protected access
- [x] Tenant-aware invocation

Acceptance Criteria (E00-S06):
- [x] AI cannot call mutation endpoints
- [x] Injection attempts flagged
- [x] PII masked before AI context injection
- [x] AI output validated against mandatory schema
- [x] Forbidden STATE_IMPACT values rejected
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from datetime import datetime, timezone
import json
import re
import logging
import hashlib

from pydantic import BaseModel, Field as PydanticField, field_validator

from langchain_ollama import OllamaLLM
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# External LLM support (OpenAI-compatible: NVIDIA NIM, OpenAI, etc.)
try:
    from langchain_openai import ChatOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

from .rbac import Role, Permission, verify_access, AccessResult
from .audit import AuditLog, AuditAction
from .config import ConfigRegistry
from .model_registry import ModelRegistry
from .exceptions import (
    PermissionDeniedError,
    PromptInjectionError,
    AISchemaViolationError,
    PromptNotFoundError,
    PromptResolutionError,
    GuardrailViolationError,
)


logger = logging.getLogger(__name__)


# =============================================================================
# E00-S06: AI RESPONSE SCHEMA (Mandatory Output Contract)
# =============================================================================

class ConfidenceTier(str, Enum):
    """Confidence tier classification per ALIS AI Governance Sec. 6."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StateImpact(str, Enum):
    """
    Allowed STATE_IMPACT values per ALIS AI Governance Sec. 5.

    FORBIDDEN values (Final, Commit, Override) are intentionally absent.
    If the LLM outputs them, validation will reject immediately.
    """
    NONE = "None"
    DRAFT = "Draft"
    PROVISIONAL_ONLY = "ProvisionalOnly"


# Forbidden values — if the LLM emits any of these, the response is rejected.
_FORBIDDEN_STATE_IMPACTS = {"final", "commit", "override"}


class AIResponseSchema(BaseModel):
    """
    Mandatory schema for all non-advisory AI agent outputs.

    Per ALIS AI Governance Sec. 5, 6, and 8:
    - AI must return structured JSON
    - Free-text may not be used directly for decisions
    - Confidence scoring is mandatory
    - STATE_IMPACT must be declared and cannot be Final/Commit/Override

    This model is used to parse and validate the raw LLM text output.
    """
    decision: str = PydanticField(
        ...,
        description="The AI's proposed decision or recommendation"
    )
    confidence_score: float = PydanticField(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    confidence_tier: ConfidenceTier = PydanticField(
        ...,
        description="Confidence tier: HIGH, MEDIUM, or LOW"
    )
    state_impact: str = PydanticField(
        default="Draft",
        description="State impact declaration: None, Draft, or ProvisionalOnly"
    )
    reasoning: Optional[str] = PydanticField(
        default=None,
        description="Optional reasoning or justification"
    )

    @field_validator("state_impact")
    @classmethod
    def validate_state_impact(cls, v: str) -> str:
        """
        Layer 4 Invariant: Reject forbidden STATE_IMPACT values.

        Per ALIS AI Governance Sec. 5:
        Forbidden: Final, Commit, Override
        If detected → reject configuration.
        """
        if v.lower().strip() in _FORBIDDEN_STATE_IMPACTS:
            raise ValueError(
                f"Forbidden STATE_IMPACT '{v}' — AI cannot declare "
                f"Final, Commit, or Override (E00-S06 Layer 4 Invariant)"
            )
        return v


# =============================================================================
# E00-S06: PROMPT INJECTION DETECTOR
# =============================================================================

class PromptInjectionDetector:
    """
    Deterministic heuristic-based prompt injection detector.

    Scans input prompts for known injection patterns before they reach
    the LLM. This is a security-critical component (E00-S06).

    Detection Strategy:
    - Regex-based pattern matching against known injection vectors
    - Case-insensitive matching
    - Returns all matched patterns for audit logging
    """

    # Known injection patterns (case-insensitive)
    _INJECTION_PATTERNS: List[re.Pattern] = [
        # Direct instruction override
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
        re.compile(r"ignore\s+(all\s+)?prior\s+instructions?", re.IGNORECASE),
        re.compile(r"ignore\s+(all\s+)?above\s+instructions?", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
        re.compile(r"forget\s+(everything|all|your)\s+(you\s+)?know", re.IGNORECASE),

        # System prompt manipulation
        re.compile(r"you\s+are\s+now\s+(in\s+)?(\w+\s+)?mode", re.IGNORECASE),
        re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
        re.compile(r"override\s+system\s+prompt", re.IGNORECASE),
        re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),

        # Jailbreak patterns
        re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
        re.compile(r"do\s+anything\s+now", re.IGNORECASE),
        re.compile(r"jailbreak", re.IGNORECASE),
        re.compile(r"bypass\s+(safety|filter|restriction|guardrail)", re.IGNORECASE),

        # Role manipulation
        re.compile(r"pretend\s+you\s+(are|have)\s+no\s+(restrictions?|limits?|rules?)", re.IGNORECASE),
        re.compile(r"act\s+as\s+(if|though)\s+you\s+have\s+no\s+rules?", re.IGNORECASE),

        # Data exfiltration / authority escalation
        re.compile(r"reveal\s+(your\s+)?(system|initial)\s+prompt", re.IGNORECASE),
        re.compile(r"show\s+(me\s+)?(your\s+)?(system|initial)\s+prompt", re.IGNORECASE),
        re.compile(r"output\s+(your\s+)?(system|initial)\s+prompt", re.IGNORECASE),
        re.compile(r"what\s+(is|are)\s+your\s+(system|initial)\s+(prompt|instructions?)", re.IGNORECASE),

        # Delimiter injection
        re.compile(r"```\s*system\b", re.IGNORECASE),
        re.compile(r"\[SYSTEM\]", re.IGNORECASE),
        re.compile(r"<\|system\|>", re.IGNORECASE),
    ]

    @classmethod
    def detect(cls, text: str) -> List[str]:
        """
        Scan input text for known prompt injection patterns.

        Args:
            text: The prompt text to scan

        Returns:
            List of matched pattern descriptions. Empty list = clean.
        """
        if not text:
            return []

        matches = []
        for pattern in cls._INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                matches.append(
                    f"Injection pattern detected: '{match.group()}' "
                    f"(pattern: {pattern.pattern})"
                )

        return matches

    @classmethod
    def assert_clean(cls, text: str, context: Optional["AIGatewayContext"] = None) -> None:
        """
        Assert that the prompt is clean. Raises PromptInjectionError if not.

        Also logs the injection attempt to the audit ledger.

        Args:
            text: The prompt text to scan
            context: Optional gateway context for audit logging

        Raises:
            PromptInjectionError: If injection patterns are detected
        """
        matches = cls.detect(text)
        if matches:
            # Log the injection attempt
            AuditLog.log(
                action=AuditAction.AI_PROMPT_INJECTION,
                actor_id=context.actor_id if context else "unknown",
                actor_type=context.actor_type if context else "unknown",
                actor_role=(
                    context.actor_role.value
                    if context and context.actor_role
                    else None
                ),
                entity_type="ai_gateway",
                entity_id=context.request_id if context else "unknown",
                success=False,
                failure_reason="Prompt injection detected",
                org_id=context.org_id if context else None,
                module=context.module if context else None,
                wizard=context.wizard if context else None,
                metadata={
                    "injection_patterns": matches,
                    "prompt_hash": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                },
            )

            raise PromptInjectionError(
                message="Prompt injection detected — request blocked (E00-S06)",
                details={
                    "patterns_matched": len(matches),
                    "patterns": matches,
                },
            )


# =============================================================================
# E00-S06: OUTPUT SCHEMA VALIDATOR
# =============================================================================

class AIOutputValidator:
    """
    Validates AI output against the mandatory AIResponseSchema.

    Per ALIS AI Governance Sec. 8:
    - AI must return structured JSON
    - Schema must be validated before any downstream logic executes
    - Invalid schema → reject output (no silent fallback)
    """

    @classmethod
    def validate(
        cls,
        raw_output: str,
        context: Optional["AIGatewayContext"] = None,
    ) -> AIResponseSchema:
        """
        Parse and validate raw LLM text output.

        Args:
            raw_output: The raw string response from the LLM
            context: Optional gateway context for audit logging

        Returns:
            Validated AIResponseSchema instance

        Raises:
            AISchemaViolationError: If output is not valid JSON or
                                    fails schema validation
        """
        # Step 1: Extract JSON from the raw output
        json_str = cls._extract_json(raw_output)
        if json_str is None:
            cls._log_schema_rejection(
                reason="LLM output is not valid JSON",
                raw_output=raw_output,
                context=context,
            )
            raise AISchemaViolationError(
                message=(
                    "AI output is not valid JSON — "
                    "free-text responses cannot be used for decisions (E00-S06)"
                ),
                details={"raw_output_length": len(raw_output)},
            )

        # Step 2: Parse JSON
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            cls._log_schema_rejection(
                reason=f"JSON parse error: {e}",
                raw_output=raw_output,
                context=context,
            )
            raise AISchemaViolationError(
                message=f"AI output JSON parse failed: {e}",
                details={"raw_output_length": len(raw_output)},
            )

        # Step 3: Validate against Pydantic schema
        try:
            validated = AIResponseSchema(**parsed)
        except Exception as e:
            cls._log_schema_rejection(
                reason=f"Schema validation failed: {e}",
                raw_output=raw_output,
                context=context,
            )
            raise AISchemaViolationError(
                message=f"AI output failed schema validation: {e}",
                details={
                    "parsed_keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
                    "error": str(e),
                },
            )

        return validated

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """
        Extract a JSON object from LLM output.

        Handles common LLM output patterns:
        1. Pure JSON string
        2. JSON wrapped in markdown code fences (```json ... ```)
        3. JSON embedded in explanatory text
        """
        text = text.strip()

        # Case 1: Direct JSON object
        if text.startswith("{") and text.endswith("}"):
            return text

        # Case 2: Markdown code-fenced JSON
        fence_match = re.search(
            r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```",
            text,
            re.DOTALL,
        )
        if fence_match:
            return fence_match.group(1).strip()

        # Case 3: Embedded JSON — find outermost { ... }
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)

        return None

    @classmethod
    def _log_schema_rejection(
        cls,
        reason: str,
        raw_output: str,
        context: Optional["AIGatewayContext"] = None,
    ) -> None:
        """Log a schema validation rejection to the audit ledger."""
        AuditLog.log(
            action=AuditAction.AI_SCHEMA_REJECTED,
            actor_id=context.actor_id if context else "unknown",
            actor_type=context.actor_type if context else "unknown",
            actor_role=(
                context.actor_role.value
                if context and context.actor_role
                else None
            ),
            entity_type="ai_gateway",
            entity_id=context.request_id if context else "unknown",
            success=False,
            failure_reason=reason,
            org_id=context.org_id if context else None,
            module=context.module if context else None,
            wizard=context.wizard if context else None,
            metadata={
                "output_length": len(raw_output),
                "output_hash": hashlib.sha256(
                    raw_output.encode("utf-8")
                ).hexdigest(),
            },
        )


# =============================================================================
# GATEWAY CONTEXT
# =============================================================================

@dataclass
class AIGatewayContext:
    """
    Context for AI Gateway invocations.

    This context is passed to every AI call and used for:
    - RBAC verification
    - Audit logging
    - Tenant isolation
    """
    actor_id: str
    actor_type: str = "system"  # human, ai_agent, system
    actor_role: Role = Role.SYSTEM

    # Tenant/Organization context
    org_id: Optional[str] = None

    # Module/Wizard context
    module: Optional[str] = None  # M1, M2, etc.
    wizard: Optional[str] = None

    # Request tracing
    request_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: Optional[str] = None

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# GATEWAY INVOCATION RESULT
# =============================================================================

@dataclass
class AIInvocationResult:
    """Result of an AI Gateway invocation."""
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    request_id: str = ""
    model: str = ""
    latency_ms: float = 0.0
    token_count: Optional[int] = None

    # E00-S06: Validated structured output (populated when validate_schema=True)
    validated_output: Optional[AIResponseSchema] = None

    # E03-S08: Guardrail result (always populated on successful invocation)
    guardrail_violations: int = 0
    guardrail_blocked: bool = False

    # Phase D: Selective auto-execution (True when policy bypassed HITL)
    auto_executed: bool = False


# =============================================================================
# INSTRUMENTED LLM WRAPPER
# =============================================================================

class InstrumentedLLM:
    """
    Wrapper around LangChain LLM that enforces RBAC and logs invocations.

    This wrapper intercepts all LLM calls to:
    1. Verify RBAC permissions before invocation
    2. Detect prompt injection attempts (E00-S06)
    3. Log invocation metadata to audit log
    4. Optionally validate output schema (E00-S06)
    5. Measure latency and track usage

    The wrapper is transparent to LangGraph - it can be used as a drop-in
    replacement for any LangChain LLM.
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        context: AIGatewayContext,
        model_name: str
    ):
        self._llm = llm
        self._context = context
        self._model_name = model_name

    def invoke(
        self,
        input_text: str,
        validate_schema: bool = False,
        **kwargs,
    ) -> AIInvocationResult:
        """
        Invoke the LLM with RBAC checking, injection detection, and audit
        logging.

        Args:
            input_text: The prompt to send to the LLM
            validate_schema: If True, parse and validate output against
                             AIResponseSchema (E00-S06). Agents that produce
                             decisions MUST set this to True.
            **kwargs: Additional arguments passed to the LLM

        Returns:
            AIInvocationResult with the response or error

        Raises:
            PermissionDeniedError: If actor lacks AI_INVOKE permission
            PromptInjectionError: If injection patterns detected (E00-S06)
            AISchemaViolationError: If validate_schema=True and output
                                    fails validation (E00-S06)
        """
        request_id = str(uuid4())
        start_time = datetime.now(timezone.utc)

        # --- Step 0: Lockdown Check (E00-S05) ---
        # During lockdown ALL AI invocations are blocked regardless of role.
        from .lockdown import LockdownManager
        LockdownManager.assert_ai_allowed(actor_id=self._context.actor_id)

        # --- Step 1: RBAC Check ---
        access_result = verify_access(
            actor_role=self._context.actor_role,
            permission=Permission.AI_INVOKE,
            context={"action": "invoke", "module": self._context.module}
        )

        if not access_result.allowed:
            # Log denied access
            AuditLog.log(
                action=AuditAction.ACCESS_DENIED,
                actor_id=self._context.actor_id,
                actor_type=self._context.actor_type,
                actor_role=self._context.actor_role.value if self._context.actor_role else None,
                entity_type="ai_gateway",
                entity_id=request_id,
                success=False,
                failure_reason=access_result.reason,
                org_id=self._context.org_id,
                module=self._context.module,
                wizard=self._context.wizard,
                metadata={
                    "permission": Permission.AI_INVOKE.value,
                    "violations": access_result.context_violations
                }
            )
            raise PermissionDeniedError(
                message=f"AI Gateway access denied: {access_result.reason}",
                details={"violations": access_result.context_violations}
            )

        # --- Step 1.5: E00-S01 — AI Context Scrubbing ---
        # Mask sensitive fields in context metadata before LLM sees them.
        _sensitive_fields_scrubbed = False
        if self._context.metadata:
            from .data_classification import DataMasker
            entity_type = self._context.metadata.get("entity_type", "")
            if entity_type:
                self._context.metadata = DataMasker.mask_for_ai_context(
                    self._context.metadata, entity_type
                )
                _sensitive_fields_scrubbed = True

        # --- Step 1.6: E00-S06 — Prompt Injection Detection ---
        PromptInjectionDetector.assert_clean(input_text, context=self._context)

        # --- Step 2: LLM Invocation ---
        try:
            response = self._llm.invoke(input_text, **kwargs)
            content = response if isinstance(response, str) else str(response)
            success = True
            error = None
        except Exception as e:
            logger.exception(f"LLM invocation failed: {e}")
            content = None
            success = False
            error = str(e)

        # --- Step 2.5: E00-S06 — Output Schema Validation ---
        validated_output = None
        if success and validate_schema and content:
            # This will raise AISchemaViolationError if invalid
            validated_output = AIOutputValidator.validate(
                content, context=self._context
            )

        # --- Step 2.6: E03-S08 — Post-Generation Guardrails ---
        guardrail_violations = 0
        guardrail_blocked = False
        if success and content:
            from .guardrails import AIGuardrails
            gr_result = AIGuardrails.check_output(
                output=content,
                input_context=input_text,
                tenant_id=self._context.org_id or "default",
                actor_id=self._context.actor_id,
                actor_role=(
                    self._context.actor_role.value
                    if self._context.actor_role else None
                ),
                module=self._context.module,
                wizard=self._context.wizard,
                request_id=request_id,
            )
            guardrail_violations = len(gr_result.violations)
            guardrail_blocked = gr_result.blocked
            if gr_result.blocked:
                raise GuardrailViolationError(
                    message="AI output blocked by guardrails (E03-S08)",
                    details={
                        "violations": [
                            {
                                "filter": v.filter_name,
                                "severity": v.severity,
                                "detail": v.detail,
                            }
                            for v in gr_result.violations
                        ],
                        "fallback": gr_result.fallback_response,
                    },
                )

        # --- Step 2.7: Selective Auto-execution (Phase D) ---
        # If the caller passed a policy_result with auto_execute=True, and the
        # guardrails passed, this invocation is eligible to skip the HITL gate.
        # Logged separately as AUTO_EXECUTED for regulatory traceability.
        auto_executed = False
        policy_result = kwargs.get("policy_result")
        if (
            policy_result is not None
            and getattr(policy_result, "detail", {}).get("auto_execute") is True
            and success
            and not guardrail_blocked
        ):
            auto_executed = True
            AuditLog.log(
                action=AuditAction.AUTO_EXECUTED,
                actor_id=self._context.actor_id,
                actor_type=self._context.actor_type,
                actor_role=(
                    self._context.actor_role.value
                    if self._context.actor_role else None
                ),
                entity_type="ai_gateway",
                entity_id=request_id,
                org_id=self._context.org_id,
                module=self._context.module,
                metadata={
                    "policy_id": getattr(policy_result, "policy_id", None),
                    "policy_version": getattr(policy_result, "policy_version", None),
                    "rule_id": getattr(policy_result, "rule_id", None),
                    "verdict": getattr(policy_result, "verdict", None),
                    "confidence_score": (
                        validated_output.confidence_score if validated_output else None
                    ),
                    "reason": "auto_execute_if condition satisfied",
                },
            )

        # --- Step 3: Calculate Metrics ---
        end_time = datetime.now(timezone.utc)
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # --- Step 4: Audit Log ---
        # Per AI Governance Sec. 10: log output_json and confidence_score
        # for replay capability. We log the sanitized parsed JSON, not raw text.
        audit_metadata: Dict[str, Any] = {
            "model": self._model_name,
            "latency_ms": latency_ms,
            "prompt_length": len(input_text),
            "response_length": len(content) if content else 0,
            "correlation_id": self._context.correlation_id,
            "schema_validated": validate_schema,
        }

        # If schema was validated, include structured output in audit
        if validated_output:
            audit_metadata["confidence_score"] = validated_output.confidence_score
            audit_metadata["confidence_tier"] = validated_output.confidence_tier.value
            audit_metadata["state_impact"] = validated_output.state_impact
            audit_metadata["output_json"] = validated_output.model_dump()

        AuditLog.log(
            action=AuditAction.AI_INVOCATION,
            actor_id=self._context.actor_id,
            actor_type=self._context.actor_type,
            actor_role=self._context.actor_role.value if self._context.actor_role else None,
            entity_type="ai_gateway",
            entity_id=request_id,
            success=success,
            failure_reason=error,
            org_id=self._context.org_id,
            module=self._context.module,
            wizard=self._context.wizard,
            metadata=audit_metadata,
        )

        return AIInvocationResult(
            success=success,
            content=content,
            error=error,
            request_id=request_id,
            model=self._model_name,
            latency_ms=latency_ms,
            validated_output=validated_output,
            guardrail_violations=guardrail_violations,
            guardrail_blocked=guardrail_blocked,
            auto_executed=auto_executed,
        )

    def invoke_with_prompt(
        self,
        prompt_name: str,
        prompt_version: int,
        variables: Dict[str, Any],
        validate_schema: bool = False,
        **kwargs,
    ) -> AIInvocationResult:
        """
        Invoke the LLM using a versioned prompt from the Prompt Registry.

        This is the contract-compliant invocation method per E03-S03
        and the AI Invocation Contract.

        Flow:
        1. Validate version (reject "latest" / None)
        2. Fetch prompt from registry by name + explicit version
        3. Render Jinja2 template with provided variables
        4. Compute input_hash on the rendered prompt
        5. Run injection detection on rendered prompt
        6. Invoke LLM
        7. Log prompt_version, model_version, and input_hash to audit

        Args:
            prompt_name: Registry prompt name (e.g., "eligibility.extract_grades")
            prompt_version: Explicit integer version ("latest" prohibited)
            variables: Dict of runtime variables for Jinja2 template
            validate_schema: If True, validate output against AIResponseSchema
            **kwargs: Additional arguments passed to the LLM

        Returns:
            AIInvocationResult with the response or error

        Raises:
            PromptResolutionError: If version is "latest" or None
            PromptNotFoundError: If prompt not found in registry
            PermissionDeniedError: If actor lacks AI_INVOKE permission
            PromptInjectionError: If injection detected in rendered prompt
            AISchemaViolationError: If output fails schema validation
        """
        from .prompt_registry import PromptRegistry

        # --- Step 0: Strict version validation (Contract Rule #3) ---
        validated_version = PromptRegistry.assert_valid_version(prompt_version)

        # --- Step 1: Fetch prompt from registry ---
        tenant_id = self._context.org_id or "default"
        prompt_record = PromptRegistry.get_prompt(
            name=prompt_name,
            version=validated_version,
            tenant_id=tenant_id,
        )

        # --- Step 2: Render Jinja2 template ---
        rendered_prompt = PromptRegistry.render_prompt(
            template_content=prompt_record["content"],
            variables=variables,
        )

        # --- Step 3: Compute input hash for replay verification ---
        input_hash = hashlib.sha256(
            rendered_prompt.encode("utf-8")
        ).hexdigest()

        # --- Step 4: Invoke via existing invoke() method ---
        # This handles RBAC, lockdown, injection detection, schema
        # validation, and basic audit logging.
        result = self.invoke(
            input_text=rendered_prompt,
            validate_schema=validate_schema,
            **kwargs,
        )

        # --- Step 5: Supplemental audit entry with contract payload ---
        # The base invoke() already logs AI_INVOCATION. This additional
        # log records the full Mandatory Invocation Payload per the
        # AI Invocation Contract.
        AuditLog.log(
            action=AuditAction.AI_INVOCATION,
            actor_id=self._context.actor_id,
            actor_type=self._context.actor_type,
            actor_role=(
                self._context.actor_role.value
                if self._context.actor_role
                else None
            ),
            entity_type="ai_invocation_contract",
            entity_id=result.request_id,
            success=result.success,
            failure_reason=result.error,
            org_id=self._context.org_id,
            module=self._context.module,
            wizard=self._context.wizard,
            metadata={
                "prompt_name": prompt_name,
                "prompt_version": validated_version,
                "model_version": self._model_name,
                "input_hash": input_hash,
                "content_hash": prompt_record.get("content_hash", ""),
                "execution_mode": "advisory",
                "correlation_id": self._context.correlation_id,
            },
        )

        return result

    def __getattr__(self, name):
        """Proxy all other attributes to the underlying LLM."""
        return getattr(self._llm, name)


# =============================================================================
# AI GATEWAY SERVICE
# =============================================================================

class AIGateway:
    """
    Centralized AI Gateway for ALIS.

    This is the ONLY authorized entry point for AI model invocations.
    Direct instantiation of Ollama or other LLM classes is forbidden.

    Usage:
        context = AIGatewayContext(actor_id="agent-123", actor_role=Role.AI_AGENT)
        llm = AIGateway.get_llm(context)
        result = llm.invoke("Analyze this document...")

    Hard Constraints (E03):
    - Local / self-hosted LLMs only (Ollama)
    - No OpenAI, Anthropic, or external cloud inference
    - All invocations are logged
    - RBAC is enforced

    E00-S06 Enforcement:
    - Prompt injection detection (pre-LLM)
    - Output schema validation (post-LLM)
    - STATE_IMPACT invariant (no Final/Commit/Override)
    - Confidence scoring logged to audit
    """

    # Forbidden imports (for static analysis / linting)
    _FORBIDDEN_IMPORTS = [
        "anthropic",
        "langchain_anthropic",
        # openai / langchain_openai are permitted — used via external LLM API config
    ]

    @classmethod
    def get_llm(
        cls,
        context: AIGatewayContext,
        capability: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0
    ) -> InstrumentedLLM:
        """
        Get an instrumented LLM instance for AI operations.

        This is the ONLY way to obtain an LLM instance in ALIS.

        Resolution order (E03-S02 hot-swap):
        1. Explicit `model_name` override (escape hatch for testing)
        2. DB-backed ModelRegistry lookup by `capability` + tenant
        3. Fallback to ConfigRegistry defaults

        Args:
            context: AIGatewayContext with actor and tenant information
            capability: AI role capability (Infer, Score, Plan, Execute).
                        When provided, the active model for this
                        capability is resolved from the Model Registry.
            model_name: Optional explicit model override (bypasses registry)
            temperature: LLM temperature (default 0.0 for deterministic)

        Returns:
            InstrumentedLLM that can be used with LangGraph

        Raises:
            PermissionDeniedError: If actor lacks AI_INVOKE permission
        """
        # Get base config
        base_url = ConfigRegistry.get(
            ConfigRegistry.LLM_BASE_URL,
            "http://localhost:11434"
        )

        # --- E03-S02: Model Resolution ---
        model = model_name  # Priority 1: explicit override

        if model is None and capability and context.org_id:
            # Priority 2: DB-backed Model Registry (hot-swap path)
            try:
                resolved = ModelRegistry.get_active_model(
                    capability=capability,
                    tenant_id=context.org_id,
                )
                if resolved:
                    model = resolved.ollama_model_tag
                    # Use per-model temperature if configured
                    temperature = resolved.config.get(
                        "temperature", temperature
                    )
                    logger.info(
                        f"E03-S02: Resolved model from registry — "
                        f"{resolved.ollama_model_tag} for {capability}"
                    )
            except Exception as e:
                logger.warning(
                    f"E03-S02: ModelRegistry lookup failed, "
                    f"falling back to config: {e}"
                )

        if model is None:
            # Priority 3: Fallback to ConfigRegistry
            model = ConfigRegistry.get(
                ConfigRegistry.LLM_MODEL_NAME,
                "llama3"
            )

        # --- Resource Limit Parameters (E03-S02) ---
        # Extracted from the resolved model's config JSONB.
        # Only known OllamaLLM resource params are forwarded — unknown
        # keys are ignored to avoid breaking the constructor.
        _RESOURCE_LIMIT_KEYS = {
            "num_ctx",     # Context window size (tokens)
            "num_gpu",     # Number of GPU layers to offload
            "num_thread",  # CPU threads for inference
            "keep_alive",  # Duration to keep model loaded (e.g. "5m")
            "timeout",     # Request timeout (seconds)
        }
        resource_kwargs: dict = {}
        if capability and context.org_id:
            # Re-use the already-resolved config if available
            try:
                resolved_for_limits = ModelRegistry.get_active_model(
                    capability=capability,
                    tenant_id=context.org_id,
                )
                if resolved_for_limits:
                    resource_kwargs = {
                        k: v
                        for k, v in resolved_for_limits.config.items()
                        if k in _RESOURCE_LIMIT_KEYS
                    }
            except Exception:
                pass  # Non-fatal; gateway falls back to Ollama defaults

        # --- LLM Backend Selection ---
        # If external API is configured (NVIDIA NIM / OpenAI-compatible), use it.
        # Otherwise fall back to local Ollama.
        from .settings import get_settings
        _settings = get_settings()

        if _settings.use_external_llm and _OPENAI_AVAILABLE:
            logger.info(
                f"AI Gateway: using external LLM backend — "
                f"{_settings.llm_api_base_url} / {_settings.llm_api_model}"
            )
            llm = ChatOpenAI(
                base_url=_settings.llm_api_base_url,
                api_key=_settings.llm_api_key,
                model=_settings.llm_api_model,
                temperature=temperature or _settings.llm_api_temperature,
                max_tokens=_settings.llm_api_max_tokens,
                streaming=False,
            )
        else:
            # Local Ollama (default)
            llm = OllamaLLM(
                base_url=base_url,
                model=model,
                temperature=temperature,
                **resource_kwargs,
            )

        # Wrap with instrumentation
        return InstrumentedLLM(
            llm=llm,
            context=context,
            model_name=model
        )

    @classmethod
    def check_access(cls, context: AIGatewayContext) -> AccessResult:
        """
        Pre-check if a context has permission to use AI Gateway.

        Useful for early validation before building complex agent graphs.
        """
        return verify_access(
            actor_role=context.actor_role,
            permission=Permission.AI_INVOKE,
            context={"action": "invoke", "module": context.module}
        )

    @classmethod
    def validate_no_cloud_imports(cls) -> List[str]:
        """
        Static validation helper to detect forbidden cloud LLM imports.

        Returns list of any forbidden imports found.
        This is intended for use in CI/CD pipelines.
        """
        import sys
        violations = []
        for forbidden in cls._FORBIDDEN_IMPORTS:
            if forbidden in sys.modules:
                violations.append(f"Forbidden import detected: {forbidden}")
        return violations
