---
name: alis-backend-patterns
description: |
  ALIS-specific FastAPI + Python backend patterns. Use when building or reviewing any ALIS server module,
  router, service, or core component. Covers execute_query vs execute_transaction rules, RBAC decorator
  usage, AuditLedger logging, domain event publishing, tenant isolation, state machine transitions,
  Pydantic models, exception handling, and the 6-layer architecture. Trigger keywords: FastAPI route,
  router, service, execute_query, execute_transaction, audit, RBAC, permission, tenant, domain event,
  state transition, AuditLedger, AuditLog, org_id, actor_id, actor_role, policy, module manager.
---

# ALIS Backend Patterns

You are an ALIS backend expert. Every line of server code must comply with the 6-layer architecture and
the institutional laws below.

## The 6 Layers (Never Bypass)

| Layer | Name | Responsibility |
|---|---|---|
| 1 | Entity | Pydantic models, DB rows, value objects |
| 2 | Agentic Decisions | AI Gateway outputs (advisory only, Draft state) |
| 3 | State Machine | Lifecycle transitions via orchestrators |
| 4 | Global Locks | Tenant isolation, lockdown enforcement |
| 5 | RBAC+ | Role/permission checks, context-aware ABAC |
| 6 | Audit | Append-only hash-chained ledger (AuditLedger) |

## DB Rules (Absolute)

```python
# READ-ONLY — never commits, tenant-scoped via ContextVar
from server.db_service import execute_query
rows = execute_query("SELECT * FROM students WHERE org_id = %s", (org_id,))

# WRITE — commits atomically, use for ALL inserts/updates/deletes in request handlers
from server.db_service import execute_transaction
execute_transaction([
    ("INSERT INTO students (id, org_id, name) VALUES (%s, %s, %s)",
     (str(uuid4()), org_id, name)),
])

# SYSTEM READ — bypasses RLS, use in Celery Beat tasks, migrations, health checks
# (Celery workers have no HTTP context so execute_query will raise TenantIsolationError)
from server.db_service import execute_system_query
rows = execute_system_query("SELECT id FROM domain_events WHERE status = 'PENDING' LIMIT 50")

# SYSTEM WRITE — same rules as execute_system_query, for Celery writes
from server.db_service import execute_system_transaction
execute_system_transaction([
    ("UPDATE domain_events SET status = 'PROCESSING' WHERE id = %s", (event_id,)),
])
```

**Never use `execute_query` for writes. Never use raw psycopg2 connections in business logic.**
**In Celery tasks: use `execute_system_query`/`execute_system_transaction` — no HTTP tenant context exists.**

## LLM Model Routing

Never hardcode model names. Use the task-class router — it reads from `settings` and respects
environment-variable overrides per tier.

```python
from server.core.llm_router import LLMTaskClass, get_model_for_task, get_temperature_for_task

# Three task classes map to three model tiers
model = get_model_for_task(LLMTaskClass.EXTRACTION)   # 1.5b — slot-filling, JSON schemas
model = get_model_for_task(LLMTaskClass.GENERATION)   # 7b   — drafting, summaries, emails
model = get_model_for_task(LLMTaskClass.REASONING)    # 14b  — eligibility, risk, decisions
model = get_model_for_task(LLMTaskClass.EMBEDDING)    # nomic-embed-text (always fixed)

temp = get_temperature_for_task(LLMTaskClass.GENERATION)  # 0.3
temp = get_temperature_for_task(LLMTaskClass.REASONING)   # 0.0
```

If `settings.use_external_llm` is True (LLMM_API_KEY + LLM_API_BASE_URL set), all non-embedding
tasks route to `settings.llm_api_model` automatically.

## Router Pattern

```python
from fastapi import APIRouter, Request
from server.core.rbac import Permission, require_permission
from server.core.exceptions import ALISError

router = APIRouter(prefix="/api/v1/module", tags=["module"])

def _org(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default")

def _actor(request: Request) -> str:
    return getattr(request.state, "user_id", "anonymous")

def _role(request: Request) -> str:
    return getattr(request.state, "user_role", "unknown")

@router.post("/resource")
@require_permission(Permission.RESOURCE_CREATE)
async def create_resource(body: ResourceCreate, request: Request):
    try:
        result = await ResourceService.create(body, _org(request), _actor(request))
        return result
    except ALISError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message})
```

## Audit Logging (Mandatory on Every Mutation)

```python
from server.core.audit import AuditLedger, AuditAction

# Basic log
AuditLedger.log(
    action=AuditAction.CREATE,
    actor_id=actor_id,
    actor_role=actor_role,
    entity_type="Student",
    entity_id=student_id,
    tenant_id=org_id,
    metadata={"name": student_name},
)

# State transition
AuditLedger.log_state_transition(
    actor_id=actor_id,
    actor_role=actor_role,
    entity_type="Application",
    entity_id=app_id,
    tenant_id=org_id,
    previous_state="PENDING",
    new_state="APPROVED",
)

# AI agent decision
AuditLedger.log_agent_decision(
    agent_id="eligibility_agent",
    entity_type="Application",
    entity_id=app_id,
    tenant_id=org_id,
    decision="ELIGIBLE",
    confidence=0.87,
)
```

## Domain Events (Cross-Module Communication)

```python
from server.core.domain_events import DomainEventBus

# Publish — modules NEVER call each other directly
await DomainEventBus.publish("StudentEnrolled", {
    "student_id": student_id,
    "org_id": org_id,
    "program": program_code,
})

# Subscribe (in module __init__ or startup)
DomainEventBus.subscribe("FeePaymentReceived", handle_payment_received)
# alias: DomainEventBus.register_handler(...)
```

## RBAC Permissions Reference

Use `Permission.<NAME>` from `server.core.rbac`. Never hardcode string permission names.

| Resource | Permissions |
|---|---|
| Student | `STUDENT_READ`, `STUDENT_CREATE`, `STUDENT_UPDATE`, `STUDENT_READ_PII` |
| Course | `COURSE_READ`, `COURSE_CREATE`, `COURSE_UPDATE` |
| Marks | `MARKS_READ`, `MARKS_ENTRY`, `MARKS_FINALIZE` |
| Finance | `FEE_READ`, `FEE_CREATE`, `PAYMENT_PROCESS`, `LEDGER_READ` |
| Exam | `EXAM_PAPER_READ`, `EXAM_PAPER_CREATE`, `HALL_TICKET_GENERATE`, `RESULT_PUBLISH` |
| Override | `OVERRIDE_REQUEST`, `OVERRIDE_APPROVE` |
| AI | `AI_INVOKE` |
| Process | `PROCESS_READ`, `PROCESS_MANAGE` |

AI_AGENT role: READ-only. Cannot call mutation endpoints or override tenant context.

## Exceptions

```python
from server.core.exceptions import (
    ALISError,           # Base — status_code + message
    PermissionDeniedError,
    NotFoundError,
    ValidationError,
    PromptInjectionError,
    GuardrailViolationError,
)
raise NotFoundError(f"Student {student_id} not found")
raise PermissionDeniedError("Only REGISTRAR can publish results")
```

## State Machine Rule

- AI agents ONLY produce `Draft` state outputs
- State transitions require deterministic rules via PolicyResolver or WorkflowEngine
- Never let an LLM directly set a Final/Committed/Published state
- Always log transitions with `AuditLedger.log_state_transition()`

## Soft Delete Convention

```python
# Lifecycle entities (students, courses, staff)
execute_transaction([("UPDATE students SET status='ARCHIVED' WHERE id=%s", (id,))])

# State machine entities (applications, approvals)
execute_transaction([("UPDATE applications SET status='ANNULLED' WHERE id=%s", (id,))])

# NEVER hard-delete unless HARD_DELETE permission is granted and logged
```

## Module Structure (per Epic)

```
server/<module>/
    models.py          # Pydantic request/response models
    service.py         # Business logic (no DB calls in routers)
    automation_pipeline.py  # Celery task chains
    event_publisher.py      # Domain events this module emits
    event_handlers.py       # Handlers for events from other modules
    review_queue.py         # Human fallback queue
```

## Common Mistakes to Avoid

- Using `execute_query` for INSERT/UPDATE/DELETE — always use `execute_transaction`
- Calling another module's service directly — use `DomainEventBus.publish()`
- Letting AI output directly mutate DB state — route through PolicyResolver
- Skipping `AuditLedger.log()` on any state mutation
- Hardcoding `org_id` or `tenant_id` — always read from `request.state.tenant_id`
- Using `Role.SUPER_ADMIN` as a shortcut to bypass checks — every route still needs `@require_permission`
