---
name: alis-machine-learning
description: |
  ALIS machine learning engineering — model registry, LLM operations, embedding/vector search,
  guardrails, observability, prompt engineering, and ML governance. Use when building ML features,
  managing models, implementing RAG, tuning prompts, adding guardrail filters, reading AI metrics,
  or reviewing ML pipeline correctness. Covers ModelRegistry (register/hot-swap), ModelCapability
  (Infer/Score/Plan/Execute), AIGuardrails (toxicity/hallucination/policy/unsafe), AIObservabilityService
  (latency/failure rates/HITL routing), pgvector embeddings (nomic-embed-text 768-dim), PromptRegistry,
  confidence tier routing, and ALIS ML governance rules. Trigger keywords: machine learning, ML, LLM,
  model, Ollama, qwen, nomic, embedding, vector, pgvector, RAG, retrieval, prompt, prompt engineering,
  guardrail, hallucination, toxicity, observability, metrics, latency, confidence, ModelRegistry,
  ModelCapability, AIObservabilityService, InvocationMetrics, hot-swap, model upgrade, evaluation,
  training, fine-tune, inference, scoring, semantic search, cosine similarity, ivfflat.
---

# ALIS Machine Learning Engineering

You are the ALIS ML Engineer. The ALIS ML stack is fully local — no cloud, no telemetry leaks.

## ML Stack Overview

| Component | Technology | Purpose |
|---|---|---|
| LLM — Extraction tier | `qwen2.5:1.5b-instruct-q8_0` via Ollama | Slot-filling, JSON schema output, classification |
| LLM — Generation tier | `qwen2.5:7b-instruct` via Ollama | Document drafting, summaries, email composition |
| LLM — Reasoning tier | `qwen2.5:14b-instruct` via Ollama | Eligibility decisions, risk scoring, multi-step logic |
| Embeddings | `nomic-embed-text` via Ollama | Semantic search, RAG, counsellor allocation (768-dim) |
| Vector DB | PostgreSQL + pgvector (768-dim) | Nearest-neighbour retrieval |
| Prompt Store | `PromptRegistry` (PostgreSQL) | Versioned, tenant-scoped prompts |
| Model Store | `ModelRegistry` (PostgreSQL) | Capability-mapped, hot-swappable models |
| Guardrails | `AIGuardrails` (deterministic, local) | Post-generation safety filters |
| Observability | `AIObservabilityService` (audit-derived) | Latency, failure rate, HITL metrics |

Tier models are env-configurable: `OLLAMA_EXTRACTION_MODEL`, `OLLAMA_GENERATION_MODEL`, `OLLAMA_REASONING_MODEL`.

## Task Class Router

All agent code must select the model via `LLMTaskClass` — never read `settings.ollama_*_model` directly.

```python
from server.core.llm_router import LLMTaskClass, get_model_for_task, get_temperature_for_task

# EXTRACTION — structured output, constrained schema, classification
model = get_model_for_task(LLMTaskClass.EXTRACTION)   # qwen2.5:1.5b (default)
temp  = get_temperature_for_task(LLMTaskClass.EXTRACTION)  # 0.0

# GENERATION — long-form text, narrative quality matters
model = get_model_for_task(LLMTaskClass.GENERATION)   # qwen2.5:7b (default)
temp  = get_temperature_for_task(LLMTaskClass.GENERATION)  # 0.3

# REASONING — multi-step logic, decisions with consequence
model = get_model_for_task(LLMTaskClass.REASONING)    # qwen2.5:14b (default)
temp  = get_temperature_for_task(LLMTaskClass.REASONING)   # 0.0

# EMBEDDING — semantic similarity, RAG (never changes)
model = get_model_for_task(LLMTaskClass.EMBEDDING)    # nomic-embed-text
```

Routing rule: if `settings.use_external_llm` is True, all non-embedding tasks use `settings.llm_api_model`.

## Model Capabilities

Every AI task in ALIS declares one of four capabilities:

```python
from server.core.model_registry import ModelCapability

ModelCapability.INFER    # "Infer"   — classification, eligibility evaluation
ModelCapability.SCORE    # "Score"   — numeric scoring, intake quality, GPA prediction
ModelCapability.PLAN     # "Plan"    — multi-step academic planning, workflow drafting
ModelCapability.EXECUTE  # "Execute" — structured output generation (offer letters, reports)
```

The `ModelRegistry` maps each capability to an active model. AIGateway resolves the right model
automatically — never hardcode model names in business logic.

## Model Registry — Registration & Hot-Swap

```python
from server.core.model_registry import ModelRegistry, LLMModelRegister, ModelCapability

# Register a new model (e.g., after pulling a new Ollama model)
model_id = ModelRegistry.register_model(
    tenant_id=org_id,
    model=LLMModelRegister(
        name="qwen2.5",
        version="3b-instruct-q8_0",     # ollama tag: qwen2.5:3b-instruct-q8_0
        capability=ModelCapability.PLAN,
        is_active=True,                  # Deactivates previous PLAN model atomically
        config={
            "temperature": 0.0,          # Deterministic — always 0.0 in ALIS
            "num_ctx": 8192,             # Context window
            "num_gpu": 1,
            "num_thread": 4,
            "keep_alive": "5m",
            "timeout": 60,
        },
    ),
    registered_by=super_admin_id,
)
# Audit logged: AuditAction.CONFIG_CHANGE on llm_model_registry
```

```python
# Hot-swap: activate a different registered model for a capability
# (no code change needed — AIGateway picks it up on next call)
ModelRegistry.swap_active_model(
    capability="Plan",
    new_model_id=model_id,
    tenant_id=org_id,
    swapped_by=super_admin_id,
)

# Look up the active model for a capability
resolved = ModelRegistry.get_active_model(capability="Infer", tenant_id=org_id)
# resolved.ollama_model_tag  → "qwen2.5:1.5b-instruct-q8_0"
# resolved.config            → {"temperature": 0.0, "num_ctx": 4096, ...}

# List all registered models
all_models = ModelRegistry.list_models(tenant_id=org_id, capability="Score")
```

## Model Config Best Practices

```python
config = {
    "temperature": 0.0,    # Always 0.0 — deterministic outputs required for audit replay
    "num_ctx": 4096,       # Set per-task: 2048 (scoring), 4096 (inference), 8192 (planning)
    "num_gpu": 1,          # Use GPU layers if available
    "num_thread": 4,       # CPU threads for inference
    "keep_alive": "5m",    # Keep model warm — reduces first-call latency
    "timeout": 60,         # Seconds before timeout
}
```

`temperature=0.0` is mandatory in ALIS. Non-zero temperature produces non-deterministic outputs
that cannot be replayed for appeals (Legal Addendum §20).

## Prompt Registry & Versioning

```python
from server.core.prompt_registry import PromptRegistry

# Register a versioned prompt
prompt_id = PromptRegistry.register(
    key="admissions.eligibility_eval",
    version="v2",
    template="""
You are an academic eligibility evaluator. Given the applicant data below, assess eligibility.

Applicant Program: {program}
Academic Scores: {academic_scores}

Return a JSON with keys: recommendation (string), confidence (0.0-1.0), reasoning (string).
Do NOT include student names or personal identifiers in your response.
""",
    tenant_id=org_id,
    registered_by=actor_id,
)

# Retrieve active prompt for invocation
prompt = PromptRegistry.get_active("admissions.eligibility_eval", tenant_id=org_id)

# Retrieve historical version (for appeal replay — §20)
historical = PromptRegistry.get_by_version("admissions.eligibility_eval", "v1", tenant_id=org_id)
```

Prompt versioning rules:
- Never delete old prompt versions — they are needed for appeal replay
- Use semantic version strings: `v1`, `v2`, `v2.1`
- Increment version whenever prompt text changes
- Log version in every AI invocation metadata

## Embedding & Vector Search (RAG / Semantic Search)

```python
from server.core.ai_gateway import AIGateway
from server.db_service import execute_query, execute_transaction

# 1. Generate embedding (768-dim, nomic-embed-text)
embedding = await AIGateway.embed(
    text="Student specialises in machine learning and data science, needs technical counsellor",
    tenant_id=org_id,
)
# Returns List[float], length=768

# 2. Store embedding in pgvector column
execute_transaction([
    ("UPDATE counsellor_profiles SET embedding = %s::vector WHERE id = %s",
     (embedding, counsellor_id)),
])

# 3. Cosine similarity search (nearest neighbour)
results = execute_query(
    """
    SELECT
        id,
        name,
        specialty,
        1 - (embedding <=> %s::vector) AS similarity
    FROM counsellor_profiles
    WHERE org_id = %s
      AND status = 'ACTIVE'
    ORDER BY embedding <=> %s::vector
    LIMIT 5
    """,
    (embedding, org_id, embedding),
)
# results[0]["similarity"] → 0.94 (highest = most similar)

# 4. Threshold filtering (discard low-similarity matches)
SIMILARITY_THRESHOLD = 0.75
relevant = [r for r in results if r["similarity"] >= SIMILARITY_THRESHOLD]
```

### RAG Pattern (Retrieval-Augmented Generation)

```python
# Step 1: Embed the query
query_embedding = await AIGateway.embed(text=user_query, tenant_id=org_id)

# Step 2: Retrieve relevant documents from pgvector
docs = execute_query(
    """
    SELECT content, source, 1 - (embedding <=> %s::vector) AS relevance
    FROM knowledge_base
    WHERE org_id = %s
    ORDER BY embedding <=> %s::vector
    LIMIT 3
    """,
    (query_embedding, org_id, query_embedding),
)

# Step 3: Build grounded context (include retrieved docs in prompt)
context = "\n\n".join([f"Source: {d['source']}\n{d['content']}" for d in docs])

# Step 4: Invoke LLM with grounded context
response = await AIGateway.invoke(
    prompt_id="rag.answer_query",
    context={"query": user_query, "retrieved_context": context},
    actor_role=Role.AI_AGENT,
    tenant_id=org_id,
)
```

### pgvector Index Setup (in migration)

```python
# IVFFlat index — fast approximate nearest neighbour
op.execute("""
CREATE INDEX IF NOT EXISTS idx_counsellor_embedding
ON counsellor_profiles USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100)
""")
# lists = sqrt(num_rows) is the rule of thumb
# Use vector_cosine_ops for nomic-embed-text (cosine similarity)
```

## Guardrails — Understanding and Extending

All AI output passes through 4 deterministic filters before being returned:

```
LLM Output → ToxicityFilter → HallucinationDetector → PolicyContradictionDetector → UnsafeSuggestionBlocker
```

### Filter Summary

| Filter | Severity | What It Catches |
|---|---|---|
| `ToxicityFilter` | BLOCK | Abusive language, slurs, academic dishonesty promotion |
| `HallucinationDetector` | WARNING | Numeric claims (scores, %, GPA) not in input context |
| `PolicyContradictionDetector` | BLOCK | Values contradicting active ConfigRegistry policies |
| `UnsafeSuggestionBlocker` | BLOCK | DROP TABLE, bypass auth, skip audit, shell commands |

```python
from server.core.guardrails import AIGuardrails

result = AIGuardrails.check_output(
    output=llm_raw_text,
    input_context=original_prompt,
    tenant_id=org_id,
    actor_id=actor_id,
    actor_role="ai_agent",
    module="M1",
    wizard="eligibility_eval",
    request_id=request_id,
)

if result.blocked:
    # Output suppressed — safe fallback returned
    return result.fallback_response

if not result.passed:
    # Warnings present — annotate output but still return
    for v in result.violations:
        logger.warning("Guardrail warning: %s — %s", v.filter_name, v.detail)
```

### Adding a Custom Guardrail Filter

```python
# Example: block AI from recommending fee waivers above policy threshold
import re
from server.core.guardrails import GuardrailViolation

class FeeWaiverGuardrail:
    _WAIVER_PATTERN = re.compile(
        r'\b(\d{1,3})\s*(%|percent)\s*(waiver|discount|reduction)', re.IGNORECASE
    )
    MAX_WAIVER_PCT = 50  # From ConfigRegistry

    @classmethod
    def check(cls, output: str) -> list[GuardrailViolation]:
        violations = []
        for match in cls._WAIVER_PATTERN.finditer(output):
            value = float(match.group(1))
            if value > cls.MAX_WAIVER_PCT:
                violations.append(GuardrailViolation(
                    filter_name="fee_waiver_limit",
                    severity="BLOCK",
                    detail=f"AI suggested {value}% waiver; policy max is {cls.MAX_WAIVER_PCT}%",
                ))
        return violations
```

Register it in `AIGuardrails.check_output()` by appending `FeeWaiverGuardrail.check(output)` to the violations list.

## AI Observability — Reading Metrics

```python
from server.core.ai_observability import AIObservabilityService

# 24-hour metrics for a tenant
metrics = AIObservabilityService.get_metrics(tenant_id=org_id, window_hours=24)

print(f"Invocations: {metrics.total_invocations}")
print(f"Failure rate: {metrics.failure_rate:.1%}")
print(f"Avg latency: {metrics.avg_latency_ms:.0f}ms")
print(f"P95 latency: {metrics.p95_latency_ms:.0f}ms")
print(f"Guardrail blocks: {metrics.guardrail_blocks}")
print(f"HITL escalations: {metrics.hitl_escalations}")
print(f"Injection attempts: {metrics.injection_attempts}")

# Per-model breakdown
model_stats = AIObservabilityService.get_model_breakdown(tenant_id=org_id)
for m in model_stats:
    print(f"{m.model_name}: {m.invocation_count} calls, {m.avg_latency_ms:.0f}ms avg")
```

Metrics are derived purely from the audit ledger — no separate metrics store. All metrics are
scoped per tenant — `tenant_id` never appears in API responses to prevent cross-tenant leakage.

### Health Thresholds to Monitor

| Metric | Warning | Critical |
|---|---|---|
| Failure rate | > 5% | > 15% |
| Avg latency | > 3,000ms | > 8,000ms |
| P95 latency | > 10,000ms | > 30,000ms |
| Guardrail block rate | > 2% | > 10% |
| HITL escalation rate | > 20% | > 50% |
| Injection attempts | > 0 any window | — |

## Confidence Tier Routing (Decision Framework)

```python
from server.core.ai_gateway import ConfidenceTier

# HIGH (≥ 0.85) — PolicyResolver auto-applies within policy bounds
if response.confidence_tier == ConfidenceTier.HIGH and response.confidence >= 0.85:
    await policy_resolver.apply_draft(response, entity_id)

# MEDIUM (0.60–0.84) — Staff review queue (SLA: 24 hours)
elif response.confidence >= 0.60:
    await review_queue.enqueue(response, entity_id, sla_hours=24)

# LOW (< 0.60) — Mandatory HITL escalation (SLA: 4 hours)
else:
    await hitl_service.escalate(
        response, entity_id,
        reason=f"Low confidence: {response.confidence:.2f}",
        escalation_level="MODULE_MANAGER",
    )
```

## Prompt Engineering Principles for ALIS

1. **Determinism first** — `temperature=0.0`, never ask for creative/varied outputs
2. **JSON output mandate** — always request structured JSON; validate against `AIResponse` schema
3. **No PII in prompts** — use `DataMasker.mask_for_ai_context()` before building context
4. **Ground numeric claims** — include all expected numeric values in context to prevent hallucination
5. **Declare role** — start prompts with "You are a [role] for [purpose]"
6. **No chain-of-action** — AI describes reasoning, never executes actions
7. **Confidence instruction** — always ask model to include confidence score (0.0–1.0)
8. **State impact instruction** — always include: "Set state_impact to DRAFT only"

```python
# Example well-formed prompt template
ELIGIBILITY_PROMPT = """
You are an academic eligibility evaluator for {institution_name}.

Program Requirements for {program_code}:
- Minimum aggregate: {min_aggregate}%
- Required subjects: {required_subjects}

Applicant Academic Record:
- Aggregate score: {aggregate}%
- Completed subjects: {subjects}

Evaluate eligibility and return JSON:
{{
  "recommendation": "<ELIGIBLE|INELIGIBLE|BORDERLINE> — one sentence reason",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<chain of thought>",
  "state_impact": "DRAFT"
}}

Do not include student names or personal identifiers.
"""
```

## ML Governance Rules

| Rule | Requirement |
|---|---|
| No cloud LLM | All inference via local Ollama only |
| Deterministic | `temperature=0.0` always |
| Advisory only | `state_impact="DRAFT"` always — gateway rejects FINAL/COMMIT |
| Version locked | Every invocation logs `model_version`, `prompt_version`, `policy_version` |
| No mid-cycle drift | Model upgrades take effect from next academic cycle |
| Appeal replayable | Historical versions retained indefinitely — never delete |
| PII-free context | `DataMasker.mask_for_ai_context()` before every LLM call |
| Audit every call | `AuditLedger.log_agent_decision()` after every invocation |

## ML Operations Checklist — New AI Feature

- [ ] Task class declared: `LLMTaskClass.EXTRACTION` / `GENERATION` / `REASONING`
- [ ] Model selected via `get_model_for_task(task_class)` — not hardcoded string
- [ ] Temperature via `get_temperature_for_task(task_class)` — not hardcoded float
- [ ] Model capability declared in ModelRegistry (`Infer` / `Score` / `Plan` / `Execute`)
- [ ] Prompt registered in `PromptRegistry` with version `v1`
- [ ] PII masked before context injection (`DataMasker.mask_for_ai_context`)
- [ ] All 3 confidence tiers handled (HIGH auto-apply / MEDIUM queue / LOW HITL)
- [ ] `AuditLedger.log_agent_decision()` called after every invocation
- [ ] Guardrails applied (via `AIGateway.invoke()` — automatic, or `AIGuardrails.check_output()` manually)
- [ ] `state_impact="DRAFT"` — no exceptions
- [ ] Model version + prompt version logged in invocation metadata
- [ ] Observability metrics accessible via `AIObservabilityService.get_metrics()`
- [ ] Latency measured and within acceptable threshold (< 3,000ms avg for extraction, < 8,000ms for reasoning)
- [ ] Hallucination risk mitigated: all expected numeric values included in prompt context
