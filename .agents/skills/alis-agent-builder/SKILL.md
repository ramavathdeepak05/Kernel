---
name: alis-agent-builder
description: |
  Build ALIS AI agents that comply with the advisory-only architecture. Use when creating new AI agents,
  modifying existing agents, wiring agents into module pipelines, or reviewing agent code for compliance.
  Covers AI Gateway invocation, mandatory output schema (AIResponse with confidence + state_impact),
  Draft-only state outputs, PolicyResolver integration, HITL routing, guardrails, PII masking, Celery
  task integration, and the agent 5-part module contract. Trigger keywords: AI agent, agent, LLM,
  Ollama, qwen, nomic, embedding, AI Gateway, invoke_ai, AIResponse, confidence, state_impact,
  guardrail, HITL, human-in-the-loop, policy resolver, advisory, draft state, agent decision,
  eligibility agent, counsellor allocation, intake quality, autonomous pipeline, new agent.
---

# ALIS Agent Builder

You are the ALIS AI Agent Architect. Every agent in ALIS is advisory-only — AI drafts, rules decide.

## Core Law (Non-Negotiable)

> **AI agents NEVER directly mutate database state.**
> All agent outputs are `Draft`. A deterministic PolicyResolver or human reviewer converts Draft to Final.

Violating this law makes ALIS non-compliant and unauditable.

## AI Stack

- **LLM (tiered)**: Three model sizes via Ollama (local, no cloud) — routed by task class
- **Embeddings**: `nomic-embed-text` via Ollama (768 dimensions, pgvector) — fixed
- **Gateway**: `server.core.ai_gateway.AIGateway` — ALL model calls go through here
- **Model routing**: via `LLMTaskClass` from `server.core.llm_router` — never hardcode model names

```python
from server.core.llm_router import LLMTaskClass, get_model_for_task

# Extraction tasks (slot-filling, JSON schema output) — 1.5b
model = get_model_for_task(LLMTaskClass.EXTRACTION)

# Generation tasks (document drafting, briefing summaries) — 7b
model = get_model_for_task(LLMTaskClass.GENERATION)

# Reasoning tasks (eligibility decisions, risk scoring) — 14b
model = get_model_for_task(LLMTaskClass.REASONING)

# Embeddings — always nomic-embed-text regardless of tier settings
model = get_model_for_task(LLMTaskClass.EMBEDDING)
```

**Match the task class to the agent's job.** Using a 1.5b model for offer-letter drafting or
eligibility reasoning is a product quality risk — generated output will be inconsistent and
erode institutional trust. Using a 14b model for structured JSON extraction wastes resources.

## Mandatory AI Output Schema (AIResponse)

Every agent call MUST return a validated `AIResponse`:

```python
from server.core.ai_gateway import AIResponse, ConfidenceTier, StateImpact

# Schema enforced by AIGateway — agents cannot skip this
class AIResponse(BaseModel):
    recommendation: str          # Human-readable explanation
    confidence: float            # 0.0–1.0
    confidence_tier: ConfidenceTier  # HIGH / MEDIUM / LOW
    state_impact: str            # "DRAFT" only — NEVER "FINAL", "COMMIT", "OVERRIDE"
    reasoning: Optional[str]     # Chain-of-thought (optional but encouraged)
    metadata: Dict[str, Any]     # Agent-specific structured output
```

**`state_impact` must always be `"DRAFT"`** — the gateway rejects any other value.

## Invoking the AI Gateway

```python
from server.core.ai_gateway import AIGateway
from server.core.rbac import Role

# All AI calls go through the gateway
response: AIResponse = await AIGateway.invoke(
    prompt_id="eligibility_eval_v1",    # Registered prompt key
    context={
        "applicant_id": applicant_id,
        "marks": marks_data,            # PII will be auto-masked by gateway
        "program": program_code,
    },
    actor_role=Role.AI_AGENT,
    tenant_id=org_id,
)

# response.confidence_tier determines routing
if response.confidence_tier == ConfidenceTier.HIGH:
    await policy_resolver.apply(response, entity_id=applicant_id)
elif response.confidence_tier == ConfidenceTier.MEDIUM:
    await review_queue.enqueue(response, entity_id=applicant_id)
else:  # LOW
    await hitl_service.escalate(response, entity_id=applicant_id)
```

## Confidence Routing Rules

| Tier | Confidence | Route |
|---|---|---|
| HIGH | ≥ 0.85 | PolicyResolver auto-applies (if within policy bounds) |
| MEDIUM | 0.60–0.84 | Review queue — staff confirms within SLA |
| LOW | < 0.60 | HITL escalation — mandatory human decision |

Always implement all three branches. Never skip the LOW path.

## Agent Module Structure

Every agent-enabled module follows the 5-part contract:

```
server/<module>/
    automation_pipeline.py   # Celery task chain (trigger → AI → route)
    event_publisher.py       # Domain events this module emits
    event_handlers.py        # Events from other modules this agent reacts to
    review_queue.py          # Human review queue + SLA tracking
    <agent>_agent.py         # Agent logic (prompt construction, gateway call, output parsing)
```

## Agent Implementation Pattern

```python
# server/admissions/eligibility_agent.py
import logging
from typing import Dict, Any
from uuid import uuid4

from server.core.ai_gateway import AIGateway, AIResponse, ConfidenceTier
from server.core.audit import AuditLedger, AuditAction
from server.core.rbac import Role
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class EligibilityAgent:
    """
    Advisory-only agent. Produces Draft eligibility recommendations.
    Final decision made by PolicyResolver or human reviewer.
    """

    @staticmethod
    async def evaluate(applicant_id: str, org_id: str, actor_id: str) -> AIResponse:
        # 1. Fetch context (read-only)
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id)
        )
        if not rows:
            raise NotFoundError(f"Applicant {applicant_id} not found")

        applicant = rows[0]

        # 2. Invoke AI Gateway (PII masking + injection detection handled internally)
        response = await AIGateway.invoke(
            prompt_id="admissions.eligibility_eval_v1",
            context={
                "applicant_id": applicant_id,
                "program": applicant["program_code"],
                "academic_scores": applicant.get("metadata", {}).get("scores", {}),
            },
            actor_role=Role.AI_AGENT,
            tenant_id=org_id,
        )

        # 3. Audit the agent decision (mandatory)
        AuditLedger.log_agent_decision(
            agent_id="eligibility_agent",
            entity_type="Applicant",
            entity_id=applicant_id,
            tenant_id=org_id,
            decision=response.recommendation,
            confidence=response.confidence,
        )

        # 4. Return Draft response — DO NOT write to DB here
        return response
```

## Celery Pipeline Pattern

```python
# server/admissions/automation_pipeline.py
from celery import chain
from server.worker import celery_app

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_eligibility_pipeline(self, applicant_id: str, org_id: str):
    """Idempotent — safe to re-run after failure."""
    try:
        import asyncio
        response = asyncio.run(
            EligibilityAgent.evaluate(applicant_id, org_id, actor_id="system")
        )
        # Route based on confidence
        if response.confidence_tier == "HIGH":
            auto_apply_eligibility.delay(applicant_id, org_id, response.metadata)
        else:
            enqueue_for_review.delay(applicant_id, org_id, response.dict())
    except Exception as exc:
        # Dead letter — route to review queue on any failure
        enqueue_for_review.delay(applicant_id, org_id, {"error": str(exc)})
        raise self.retry(exc=exc)
```

**Every Celery task must be idempotent** — re-running after failure must not corrupt data or duplicate records.

## PGVector / Embedding Pattern

```python
from server.core.ai_gateway import AIGateway

# Generate embedding
embedding = await AIGateway.embed(
    text="Student specialises in machine learning and data science",
    tenant_id=org_id,
)  # Returns List[float] of dimension 768

# Store
execute_transaction([
    ("UPDATE counsellor_profiles SET embedding = %s WHERE id = %s",
     (embedding, counsellor_id)),
])

# Similarity search (cosine distance)
rows = execute_query(
    """
    SELECT id, name, 1 - (embedding <=> %s::vector) AS similarity
    FROM counsellor_profiles
    WHERE org_id = %s AND status = 'ACTIVE'
    ORDER BY embedding <=> %s::vector
    LIMIT 5
    """,
    (embedding, org_id, embedding)
)
```

## HITL Integration

```python
from server.core.hitl import HITLService

# Route to human when confidence is LOW or policy boundary hit
await HITLService.escalate(
    entity_type="Applicant",
    entity_id=applicant_id,
    tenant_id=org_id,
    reason="Low confidence eligibility decision",
    ai_response=response.dict(),
    escalation_level="MODULE_MANAGER",  # Who gets it
)
```

## Guardrails

The AI Gateway automatically applies guardrails. To add a custom guardrail:

```python
from server.core.guardrails import GuardrailRegistry

@GuardrailRegistry.register("no_minor_financial_decisions")
def check_minor_financial(context: Dict, response: AIResponse) -> bool:
    """Block AI from recommending >50k fee waivers autonomously."""
    if "waiver_amount" in response.metadata:
        if float(response.metadata["waiver_amount"]) > 50000:
            return False  # Block — route to HITL
    return True
```

## Agent Compliance Checklist

Before shipping any agent:

- [ ] All model calls go through `AIGateway.invoke()` — never direct Ollama calls
- [ ] `state_impact` is always `"DRAFT"` — gateway enforces but verify in tests
- [ ] All three confidence tiers handled (HIGH / MEDIUM / LOW)
- [ ] `AuditLedger.log_agent_decision()` called after every AI invocation
- [ ] Agent does NOT call `execute_transaction` — reads only
- [ ] Celery task is idempotent (re-runnable without data corruption)
- [ ] Dead letter path routes to review queue on any exception
- [ ] PII fields not passed raw — use `metadata.scores` not `metadata.ssn`
- [ ] Model selected via `get_model_for_task(LLMTaskClass.X)` — not hardcoded
- [ ] Correct task class chosen: EXTRACTION (JSON/slots), GENERATION (drafts), REASONING (decisions)
- [ ] Prompt registered in prompt registry with version (`_v1`, `_v2`, etc.)
