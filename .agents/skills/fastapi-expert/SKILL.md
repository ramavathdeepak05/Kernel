---
name: fastapi-expert
description: "Use when building high-performance async Python APIs with FastAPI and Pydantic V2. Invoke to create REST endpoints, define Pydantic models, implement authentication flows, set up async SQLAlchemy database operations, add JWT authentication, build WebSocket endpoints, or generate OpenAPI documentation. Trigger terms: FastAPI, Pydantic, async Python, Python API, REST API Python, SQLAlchemy async, JWT authentication, OpenAPI, Swagger Python. QUAICU kernel — the delivery/api REST surface (thin wrapper over the kernel SDK), tenant_id from the JWT claim into a ContextVar, RFC 7807 problem details, readiness gated on tenant migrations, side-effect-free policy pre-flight. Triggers — QUAICU, delivery/api, kernel REST, tenant middleware, RFC 7807, readiness probe."
license: MIT
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.0"
  domain: backend
  triggers: FastAPI, Pydantic, async Python, Python API, REST API Python, SQLAlchemy async, JWT authentication, OpenAPI, Swagger Python
  role: specialist
  scope: implementation
  output-format: code
  related-skills: fullstack-guardian, django-expert, test-master
---

# FastAPI Expert

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific API choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** Missing rule → return an error, never proceed unguarded.

### Invariants — never violated
- The API lives in `delivery/api/` and is a THIN wrapper over the kernel SDK. NEVER put governance logic (policy, ledger, lifecycle) in a route handler.
- Resolve `tenant_id` from the validated JWT claim (format `tenant_id:actor_id`), set it in the ContextVar via middleware. NEVER read tenant_id from a query param or body.
- All errors use RFC 7807 Problem Details (`application/problem+json`). NEVER leak stack traces or raw exception text.
- Inject the five ports via `app.state` (constructed once at startup). NEVER construct adapters per-request.
- Readiness is true only when every tenant schema has completed its Alembic migrations.

### HTTP status map (use exactly)
| Outcome | Status |
|---|---|
| propose accepted (async) | 202 |
| validation error | 422 |
| policy denied / tenant mismatch | 403 |
| idempotency-key collision | 409 |
| port unavailable / fail-closed | 503 |
| malformed request | 400 |

### Tie-break rules
- Tenant from JWT vs request body? → JWT claim only; body/query is untrusted.
- Catch an exception in a handler? → translate to RFC 7807; never swallow into a 200.
- Side-effect-free pre-flight check needed? → expose `POST /kernel/v1/policy/evaluate` (dry-run), never let it execute.

### Self-check
- [ ] Handlers thin; no governance logic in routes.
- [ ] tenant_id from JWT → ContextVar via middleware; slug validated.
- [ ] All errors RFC 7807; status codes match the map.
- [ ] Ports from app.state; readiness gated on migrations.

---

Deep expertise in async Python, Pydantic V2, and production-grade API development with FastAPI.

## When to Use This Skill

- Building REST APIs with FastAPI
- Implementing Pydantic V2 validation schemas
- Setting up async database operations
- Implementing JWT authentication/authorization
- Creating WebSocket endpoints
- Optimizing API performance

## Core Workflow

1. **Analyze requirements** — Identify endpoints, data models, auth needs
2. **Design schemas** — Create Pydantic V2 models for validation
3. **Implement** — Write async endpoints with proper dependency injection
4. **Secure** — Add authentication, authorization, rate limiting
5. **Test** — Write async tests with pytest and httpx; run `pytest` after each endpoint group and verify OpenAPI docs at `/docs`

> **Checkpoint after each step:** confirm schemas validate correctly, endpoints return expected HTTP status codes, and `/docs` reflects the intended API surface before proceeding.

## Minimal Complete Example

Schema + endpoint + dependency injection in one cohesive unit:

```python
# schemas.py
from pydantic import BaseModel, EmailStr, field_validator, model_config

class UserCreate(BaseModel):
    model_config = model_config(str_strip_whitespace=True)

    email: EmailStr
    password: str
    name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class UserResponse(BaseModel):
    model_config = model_config(from_attributes=True)

    id: int
    email: EmailStr
    name: str | None = None
```

```python
# routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.database import get_db
from app.schemas import UserCreate, UserResponse
from app import crud

router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DbDep) -> UserResponse:
    existing = await crud.get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return await crud.create_user(db, payload)
```

```python
# crud.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User
from app.schemas import UserCreate
from app.security import hash_password

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    user = User(email=payload.email, hashed_password=hash_password(payload.password), name=payload.name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

## JWT Authentication Snippet

```python
# security.py
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated

SECRET_KEY = "read-from-env"  # use os.environ / settings
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def create_access_token(subject: str, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    payload = {"sub": subject, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject: str | None = data.get("sub")
        if subject is None:
            raise ValueError
        return subject
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

CurrentUser = Annotated[str, Depends(get_current_user)]
```

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Pydantic V2 | `references/pydantic-v2.md` | Creating schemas, validation, model_config |
| SQLAlchemy | `references/async-sqlalchemy.md` | Async database, models, CRUD operations |
| Endpoints | `references/endpoints-routing.md` | APIRouter, dependencies, routing |
| Authentication | `references/authentication.md` | JWT, OAuth2, get_current_user |
| Testing | `references/testing-async.md` | pytest-asyncio, httpx, fixtures |
| Django Migration | `references/migration-from-django.md` | Migrating from Django/DRF to FastAPI |

## Constraints

### MUST DO
- Use type hints everywhere (FastAPI requires them)
- Use Pydantic V2 syntax (`field_validator`, `model_validator`, `model_config`)
- Use `Annotated` pattern for dependency injection
- Use async/await for all I/O operations
- Use `X | None` instead of `Optional[X]`
- Return proper HTTP status codes
- Document endpoints (auto-generated OpenAPI)

### MUST NOT DO
- Use synchronous database operations
- Skip Pydantic validation
- Store passwords in plain text
- Expose sensitive data in responses
- Use Pydantic V1 syntax (`@validator`, `class Config`)
- Mix sync and async code improperly
- Hardcode configuration values

## Output Templates

When implementing FastAPI features, provide:
1. Schema file (Pydantic models)
2. Endpoint file (router with endpoints)
3. CRUD operations if database involved
4. Brief explanation of key decisions

## Knowledge Reference

FastAPI, Pydantic V2, async SQLAlchemy, Alembic migrations, JWT/OAuth2, pytest-asyncio, httpx, BackgroundTasks, WebSockets, dependency injection, OpenAPI/Swagger

[Documentation](https://jeffallan.github.io/claude-skills/skills/backend/fastapi-expert/)

---

## QUAICU-Specific Application

This section documents advanced FastAPI patterns required by the QUAICU governance kernel's `delivery/api/` module. These go beyond the baseline skill and are specifically shaped by the spec's requirements for tenant isolation (§3.10), replayability (§3.13), operational simplicity, and fail-closed behaviour (F-03).

### Router Structure — `delivery/api/` Layout

The `delivery/api/` module is a **thin wrapper over core**. Each router file maps to one kernel concern. No router file contains governance logic — if you find a `CEL.eval()` call or a `LedgerEntry` construction in a router, that is a boundary violation (ADR F-08).

```
delivery/api/
├── main.py               # FastAPI app, lifespan, middleware registration
├── database.py           # async DB session dependency with per-tenant search_path
├── auth.py               # JWT decode, get_current_claims, ws token verify
├── dependencies.py       # Depends factories for lifecycle engine and all 5 ports
├── middleware/
│   ├── logging.py        # LoggingMiddleware — outermost
│   ├── auth.py           # AuthMiddleware — validates JWT, sets request.state.claims
│   ├── tenant.py         # TenantMiddleware — sets tenant ContextVar
│   └── rate_limit.py     # RateLimitMiddleware — per-tenant, innermost
└── routers/
    ├── actions_router.py   # POST /propose, GET /{id}, POST /{id}/approve, WebSocket
    ├── policies_router.py  # GET /policies, POST /policies, POST /policies/evaluate
    ├── ledger_router.py    # GET /ledger/{entity}/trail (streaming), GET /ledger/verify
    └── admin_router.py     # GET /health, GET /readiness, POST /admin/tenant
```

**Router file shape — thin wrapper rule:**

```python
# delivery/api/routers/actions_router.py
from fastapi import APIRouter, Depends, BackgroundTasks
from typing import Annotated
from delivery.api.dependencies import get_lifecycle_engine, TenantContextDep
from delivery.api.schemas import ProposeRequest, ActionResponse
from core.lifecycle.engine import LifecycleEngine

router = APIRouter(prefix="/kernel/v1/actions", tags=["actions"])

LifecycleEngineDep = Annotated[LifecycleEngine, Depends(get_lifecycle_engine)]

@router.post(
    "/propose",
    status_code=202,
    response_model=ActionResponse,
    summary="Propose a governed action",
)
async def propose_action(
    payload: ProposeRequest,
    engine: LifecycleEngineDep,
    tenant: TenantContextDep,
    background_tasks: BackgroundTasks,
) -> ActionResponse:
    """
    Propose a governed action. Returns 202 immediately; the lifecycle runs
    asynchronously. Poll GET /{action_id} or subscribe to the WebSocket for
    state updates. Idempotency key prevents double-execution on retry.
    """
    # Router does exactly one thing: translate HTTP request → core call → HTTP response.
    # No governance logic lives here.
    action = await engine.propose(
        action_type=payload.type,
        action_payload=payload.payload,
        idempotency_key=payload.idempotency_key,
        tenant_id=tenant.tenant_id,
        actor_context=tenant.actor_context,
    )
    return ActionResponse.from_action(action)
```

### Tenant Middleware — JWT Sub Claim to ContextVar

QUAICU uses schema-per-tenant (spec §3.10). Every request must carry a tenant identity. The `TenantMiddleware` extracts `tenant_id` from the JWT `sub` claim (formatted as `tenant_id:actor_id`), calls `set_tenant()` to store it in a `ContextVar`, and rejects the request with 403 if the claim is missing or malformed.

```python
# delivery/api/middleware/tenant.py
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_current_tenant_id: ContextVar[str] = ContextVar("current_tenant_id", default="")

def get_current_tenant_id() -> str:
    """
    Returns the tenant_id for the current request.
    Raises ValueError if called outside a request context (e.g. in a background task
    that was not seeded — background tasks must explicitly pass tenant_id, not read
    from the ContextVar, because ContextVars do not propagate to background tasks).
    """
    tenant_id = _current_tenant_id.get()
    if not tenant_id:
        raise ValueError(
            "No tenant_id in context. TenantMiddleware must run before this code path."
        )
    return tenant_id

def set_tenant(tenant_id: str) -> None:
    _current_tenant_id.set(tenant_id)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Reads tenant_id from request.state.claims (set by AuthMiddleware).
    Rejects with 403 if tenant_id is missing — fail-closed: an untenanted
    request must never reach the lifecycle engine.
    """

    async def dispatch(self, request: Request, call_next):
        # AuthMiddleware must have run first and set request.state.claims
        claims: dict = getattr(request.state, "claims", {})
        sub: str = claims.get("sub", "")

        # JWT sub claim format: "tenant_id:actor_id"
        # This format is enforced at token issuance; validate it strictly here.
        if ":" not in sub:
            return JSONResponse(
                status_code=403,
                content={
                    "type": "https://quaicu.io/errors/missing-tenant",
                    "title": "Tenant identity missing",
                    "status": 403,
                    "detail": "JWT sub claim must encode tenant_id:actor_id. "
                              "No request may proceed without a resolved tenant.",
                    "instance": str(request.url),
                },
            )

        tenant_id, actor_id = sub.split(":", 1)

        # Validate slug format to prevent schema injection downstream
        if not tenant_id.replace("-", "").replace("_", "").isalnum():
            return JSONResponse(
                status_code=403,
                content={
                    "type": "https://quaicu.io/errors/invalid-tenant",
                    "title": "Invalid tenant identifier",
                    "status": 403,
                    "detail": f"tenant_id {tenant_id!r} is not a valid slug.",
                    "instance": str(request.url),
                },
            )

        set_tenant(tenant_id)
        request.state.tenant_id = tenant_id
        request.state.actor_id = actor_id

        response = await call_next(request)
        return response
```

### Dependency Injection for Lifecycle Engine and All 5 Ports

All five ports and the lifecycle engine are injected via `Depends`. They are constructed once at startup (lifespan) and stored on `app.state`. The `Depends` functions read from `request.app.state`, never constructing new adapter instances per request.

```python
# delivery/api/dependencies.py
from typing import Annotated
from fastapi import Depends, Request, HTTPException
from core.lifecycle.engine import LifecycleEngine
from core.ports.inference import InferencePort
from core.ports.hitl import HITLPort
from core.ports.identity import IdentityPort
from core.ports.storage import StoragePort
from core.ports.workflow import WorkflowPort

# ── Lifecycle engine ──────────────────────────────────────────────────────────

def get_lifecycle_engine(request: Request) -> LifecycleEngine:
    engine: LifecycleEngine | None = getattr(request.app.state, "lifecycle_engine", None)
    if engine is None:
        # 503 — kernel not initialised; fail-closed
        raise HTTPException(
            status_code=503,
            detail={
                "type": "https://quaicu.io/errors/engine-unavailable",
                "title": "Lifecycle engine unavailable",
                "status": 503,
                "detail": "The governance lifecycle engine has not been initialised. "
                          "This is a startup error — check lifespan logs.",
            },
        )
    return engine

# ── Individual port accessors (used by health check and admin routes) ─────────

def get_inference_port(request: Request) -> InferencePort:
    return _require_port(request, "inference_adapter", "InferencePort")

def get_hitl_port(request: Request) -> HITLPort:
    return _require_port(request, "hitl_adapter", "HITLPort")

def get_identity_port(request: Request) -> IdentityPort:
    return _require_port(request, "identity_adapter", "IdentityPort")

def get_storage_port(request: Request) -> StoragePort:
    return _require_port(request, "storage_adapter", "StoragePort")

def get_workflow_port(request: Request) -> WorkflowPort:
    return _require_port(request, "workflow_adapter", "WorkflowPort")

def _require_port(request: Request, attr: str, port_name: str):
    adapter = getattr(request.app.state, attr, None)
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail={
                "type": "https://quaicu.io/errors/port-unavailable",
                "title": f"{port_name} unavailable",
                "status": 503,
                "detail": f"The {port_name} adapter is not registered. Check lifespan and kernel.toml.",
            },
        )
    return adapter

# ── Tenant context ─────────────────────────────────────────────────────────────

from dataclasses import dataclass
from delivery.api.middleware.tenant import get_current_tenant_id

@dataclass
class TenantContext:
    tenant_id: str
    actor_id: str
    actor_context: dict   # full claims dict for IdentityPort resolution

def get_tenant_context(request: Request) -> TenantContext:
    return TenantContext(
        tenant_id=request.state.tenant_id,
        actor_id=request.state.actor_id,
        actor_context=request.state.claims,
    )

# Annotated type aliases for use in router function signatures
LifecycleEngineDep  = Annotated[LifecycleEngine,  Depends(get_lifecycle_engine)]
TenantContextDep    = Annotated[TenantContext,     Depends(get_tenant_context)]
InferencePortDep    = Annotated[InferencePort,     Depends(get_inference_port)]
HITLPortDep         = Annotated[HITLPort,          Depends(get_hitl_port)]
StoragePortDep      = Annotated[StoragePort,       Depends(get_storage_port)]
WorkflowPortDep     = Annotated[WorkflowPort,      Depends(get_workflow_port)]
```

### Background Task Polling for Async Workflow State

When an action enters `PENDING_APPROVAL`, the REST response returns `202` with `state: PENDING_APPROVAL`. The client polls `GET /kernel/v1/actions/{id}` for state updates. For long-lived workflows (multi-day HITL windows), the API uses a `BackgroundTasks` job to check workflow state and push updates to the event bus (K·07), which the WebSocket subscribes to.

```python
# delivery/api/routers/actions_router.py  — polling background task

from fastapi import BackgroundTasks
from core.ports.workflow import WorkflowPort

async def _poll_workflow_until_terminal(
    action_id: str,
    workflow_handle_id: str,
    tenant_id: str,
    workflow_port: WorkflowPort,
    event_bus,          # core.events.EventBus
    poll_interval_s: float = 5.0,
) -> None:
    """
    Background task: polls the WorkflowPort for state updates and emits
    state-change events to the event bus so WebSocket subscribers are notified.
    Exits when the action reaches a terminal state (EXECUTED, DENIED, HALTED, SEALED).
    This task is only started for async workflows (PENDING_APPROVAL, EXECUTING).
    """
    import asyncio
    from core.ports.workflow import ProcessState

    TERMINAL_STATES = {ProcessState.COMPLETED, ProcessState.FAILED, ProcessState.CANCELLED}

    while True:
        state = await workflow_port.state(workflow_handle_id)
        await event_bus.emit_state_change(
            action_id=action_id,
            tenant_id=tenant_id,
            new_state=state,
        )
        if state.is_terminal:
            break
        await asyncio.sleep(poll_interval_s)

@router.post("/propose", status_code=202, response_model=ActionResponse)
async def propose_action(
    payload: ProposeRequest,
    engine: LifecycleEngineDep,
    tenant: TenantContextDep,
    workflow_port: WorkflowPortDep,
    background_tasks: BackgroundTasks,
) -> ActionResponse:
    action = await engine.propose(
        action_type=payload.type,
        action_payload=payload.payload,
        idempotency_key=payload.idempotency_key,
        tenant_id=tenant.tenant_id,
        actor_context=tenant.actor_context,
    )
    # Only start polling background task for async states
    if action.state in ("PENDING_APPROVAL", "EXECUTING"):
        background_tasks.add_task(
            _poll_workflow_until_terminal,
            action_id=action.id,
            workflow_handle_id=action.workflow_handle_id,
            tenant_id=tenant.tenant_id,
            workflow_port=workflow_port,
            event_bus=action_router_event_bus,
        )
    return ActionResponse.from_action(action)
```

### OpenAPI Schema Customization

The OpenAPI schema must reflect the QUAICU kernel's domain types precisely. `ActionState` must appear as a string enum with all lifecycle values; `action_type` must be constrained to a dotted-path format.

```python
# delivery/api/schemas.py
from pydantic import BaseModel, Field, model_config
from typing import Literal
import re

# ActionState — all lifecycle values as a Literal union for OpenAPI precision
ActionState = Literal[
    "PROPOSED", "EVALUATING", "PENDING_APPROVAL", "APPROVED",
    "EXECUTING", "EXECUTED", "DENIED", "HALTED", "SEALED",
    "COMPLETED", "CANCELLED",
]

# action_type validation — dotted path, e.g. "ciro.ifrs9.stage_transition"
_ACTION_TYPE_PATTERN = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')

class ProposeRequest(BaseModel):
    model_config = model_config(str_strip_whitespace=True)

    type: str = Field(
        ...,
        description="Dotted action type path, e.g. 'ciro.ifrs9.stage_transition'",
        json_schema_extra={"pattern": r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"},
    )
    payload: dict = Field(..., description="Action payload — schema is action-type-specific")
    idempotency_key: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Client-generated idempotency key. Re-submitting the same key returns the original result.",
    )

    @field_validator("type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        if not _ACTION_TYPE_PATTERN.match(v):
            raise ValueError(
                f"action_type must be a dotted path like 'domain.subdomain.action_name'. Got: {v!r}"
            )
        return v


class ActionResponse(BaseModel):
    action_id: str
    state: ActionState
    ledger_seq: int | None = Field(
        None,
        description="Ledger sequence number — present only after SEALED state",
    )
    inclusion_proof: str | None = Field(
        None,
        description="RFC 6962 inclusion proof (hex-encoded) — present only after SEALED",
    )

    @classmethod
    def from_action(cls, action) -> "ActionResponse":
        return cls(
            action_id=action.id,
            state=action.state,
            ledger_seq=getattr(action, "ledger_seq", None),
            inclusion_proof=getattr(action, "inclusion_proof_hex", None),
        )


# OpenAPI customization — applied at app construction
def customize_openapi(app) -> None:
    from fastapi.openapi.utils import get_openapi
    if app.openapi_schema:
        return
    schema = get_openapi(
        title="QUAICU Governance Kernel API",
        version="1.0.0",
        description=(
            "REST interface to the QUAICU governance lifecycle. "
            "All actions pass through evaluate → gate → execute → seal → emit. "
            "See the kernel spec §10 for the full worked example."
        ),
        routes=app.routes,
    )
    # Ensure ActionState is rendered as a string enum, not an integer
    if "ActionState" in schema.get("components", {}).get("schemas", {}):
        schema["components"]["schemas"]["ActionState"]["type"] = "string"
    app.openapi_schema = schema
```

### Error Response Format — RFC 7807 Problem Details

All error responses from `delivery/api/` use [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807). This is the format regulators and enterprise integration teams expect. Every field is required; no bare `{"detail": "..."}` responses.

```python
# delivery/api/errors.py
from pydantic import BaseModel
from fastapi import Request
from fastapi.responses import JSONResponse
from core.exceptions import (
    PolicyDeniedError,
    TenantIsolationError,
    FailClosedError,
    IdempotencyCollisionError,
)

class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""
    type: str       # URI reference identifying the problem type
    title: str      # Short, human-readable summary
    status: int     # HTTP status code
    detail: str     # Human-readable explanation of this specific occurrence
    instance: str   # URI reference identifying the specific request


# ── Exception handlers registered on the app ──────────────────────────────────

async def handle_policy_denied(request: Request, exc: PolicyDeniedError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=ProblemDetail(
            type="https://quaicu.io/errors/policy-denied",
            title="Action denied by policy",
            status=403,
            detail=str(exc),
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


async def handle_tenant_mismatch(request: Request, exc: TenantIsolationError) -> JSONResponse:
    """
    Tenant isolation violation — 403, not 401. The request was authenticated
    but the tenant in the JWT does not match the resource being accessed.
    Never return 404 for tenant mismatch (avoid leaking resource existence).
    """
    return JSONResponse(
        status_code=403,
        content=ProblemDetail(
            type="https://quaicu.io/errors/tenant-mismatch",
            title="Tenant isolation violation",
            status=403,
            detail="The requested resource belongs to a different tenant.",
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


async def handle_idempotency_collision(
    request: Request, exc: IdempotencyCollisionError
) -> JSONResponse:
    """
    409: an action with this idempotency key already exists and is in a
    non-terminal state. The client should poll the existing action's state
    rather than re-submitting.
    """
    return JSONResponse(
        status_code=409,
        content=ProblemDetail(
            type="https://quaicu.io/errors/idempotency-collision",
            title="Idempotency key collision",
            status=409,
            detail=f"An action with idempotency_key {exc.idempotency_key!r} already exists "
                   f"(action_id: {exc.existing_action_id}, state: {exc.existing_state}). "
                   "Poll the existing action for state updates.",
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


async def handle_port_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """503: a port adapter is unreachable — fail-closed."""
    return JSONResponse(
        status_code=503,
        content=ProblemDetail(
            type="https://quaicu.io/errors/port-unavailable",
            title="Governance port unavailable",
            status=503,
            detail="A required governance port adapter is unavailable. "
                   "The action cannot be governed — fail-closed.",
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


async def handle_fail_closed(request: Request, exc: FailClosedError) -> JSONResponse:
    """503: any unrecoverable governance failure — fail-closed, never allow through."""
    return JSONResponse(
        status_code=503,
        content=ProblemDetail(
            type="https://quaicu.io/errors/fail-closed",
            title="Governance failure — action denied",
            status=503,
            detail=str(exc),
            instance=str(request.url),
        ).model_dump(),
        media_type="application/problem+json",
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(PolicyDeniedError,        handle_policy_denied)
    app.add_exception_handler(TenantIsolationError,     handle_tenant_mismatch)
    app.add_exception_handler(IdempotencyCollisionError, handle_idempotency_collision)
    app.add_exception_handler(FailClosedError,          handle_fail_closed)
```

### HTTP Status Codes Used in the QUAICU API

Every status code has an exact semantic in the kernel. Do not deviate.

| Status | Endpoint / condition | Reason |
|--------|---------------------|--------|
| `202 Accepted` | `POST /propose` | Action accepted and lifecycle started; not yet terminal |
| `200 OK` | `GET /{id}`, `POST /{id}/approve`, `GET /ledger/verify` | Synchronous read or terminal state reached |
| `409 Conflict` | `POST /propose` with duplicate idempotency key | Idempotency collision — action already exists in a non-terminal state |
| `403 Forbidden` | Any request where tenant in JWT does not match resource; policy denied | Tenant mismatch OR access control failure (never 404 for tenant mismatch) |
| `403 Forbidden` | `POST /propose` when policy evaluation returns `DENY` | Action denied by governance policy |
| `401 Unauthorized` | Missing or invalid JWT | Authentication failure |
| `422 Unprocessable Entity` | Pydantic validation failure on request body | Bad request shape |
| `503 Service Unavailable` | Any port adapter unreachable; lifecycle engine not initialised | Fail-closed — cannot govern, must not allow |
| `503 Service Unavailable` | `GET /readiness` when migrations not complete for tenant | Kernel not ready to serve tenant |

**Rule:** never return `200` from `POST /propose` — the lifecycle is asynchronous even for fast synchronous-seeming cases. Return `202` and let the client poll or subscribe. This makes the async-by-default nature of the governance lifecycle explicit.

### Async Generator for DB Session with Per-Tenant `search_path`

QUAICU uses schema-per-tenant (spec §3.10). Every database session must set `search_path` to the requesting tenant's schema before executing any query. This is enforced via a session dependency that wraps the SQLAlchemy async session factory.

```python
# delivery/api/database.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from delivery.api.middleware.tenant import get_current_tenant_id

# One engine per deployment (shared pool); search_path is per-session, not per-engine.
_engine = create_async_engine(
    "postgresql+asyncpg://...",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an AsyncSession scoped to the current tenant's schema.
    Sets search_path before first use and resets it on exit (defense in depth).
    """
    tenant_id = get_current_tenant_id()
    # Validate tenant slug to prevent schema injection.
    if not tenant_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid tenant_id format: {tenant_id!r}")

    async with _session_factory() as session:
        # Set search_path for this session: tenant schema first, then public
        # (public holds kernel-wide tables like the tenant registry itself).
        await session.execute(
            f"SET search_path TO {tenant_id}, public"
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Reset to default — belt-and-suspenders for connection pool reuse.
            await session.execute("SET search_path TO public")

DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
```

### Lifespan Handler for Connection Pool Init and Shutdown

Use the FastAPI lifespan context manager (not deprecated `@app.on_event`) to initialise all port adapters, connection pools, and OpenBao clients exactly once at startup. This ensures that the first request does not incur cold-start latency and that all adapters are health-checked before traffic is admitted.

```python
# delivery/api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from adapters.storage.postgres import PostgresStorageAdapter
from adapters.workflow.temporal import TemporalWorkflowAdapter  # or postgres_statemachine
from adapters.inference.factory import build_inference_adapter
from core.lifecycle.engine import LifecycleEngine
from delivery.api.errors import register_exception_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    cfg = app.state.config  # loaded from kernel.toml at process start

    storage = PostgresStorageAdapter(cfg.database_url)
    await storage.initialize()  # creates pool, runs connectivity check

    workflow = TemporalWorkflowAdapter(cfg.temporal) if cfg.adapters.workflow == "temporal" \
               else PostgresStateMachineAdapter(storage)

    inference = build_inference_adapter(cfg.adapters.inference)

    app.state.lifecycle_engine = LifecycleEngine(
        storage=storage,
        workflow=workflow,
        inference=inference,
        # ... hitl, identity adapters
    )
    app.state.storage_adapter   = storage
    app.state.workflow_adapter  = workflow
    app.state.inference_adapter = inference

    yield  # application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await storage.close()          # drains connection pool
    await workflow.shutdown()      # flushes in-flight workflow handles


def create_app(config) -> FastAPI:
    app = FastAPI(
        title="QUAICU Governance Kernel",
        lifespan=lifespan,
        # Disable default /docs in production — expose only to internal/admin
        docs_url=None if config.env == "production" else "/docs",
        redoc_url=None,
    )
    app.state.config = config
    register_exception_handlers(app)
    customize_openapi(app)
    _register_middleware(app)
    _include_routers(app)
    return app
```

### Middleware Stack Order

Starlette applies middleware in reverse-registration order (last registered = outermost = first to process the request). Register in this order so the effective execution order is:

```
Request →  LoggingMiddleware → AuthMiddleware → TenantMiddleware → RateLimitMiddleware → route handler
Response ← LoggingMiddleware ← AuthMiddleware ← TenantMiddleware ← RateLimitMiddleware ← route handler
```

```python
# delivery/api/main.py  — registration order (last = outermost)
def _register_middleware(app: FastAPI) -> None:
    app.add_middleware(RateLimitMiddleware)   # 4. innermost — applied last, sees authed+tenant request
    app.add_middleware(TenantMiddleware)      # 3. sets ContextVar after auth validates JWT
    app.add_middleware(AuthMiddleware)        # 2. validates JWT, attaches claims to request.state
    app.add_middleware(LoggingMiddleware)     # 1. outermost — logs every request including auth failures
```

Rationale:
- **LoggingMiddleware first (outermost):** captures ALL requests including 401s and 403s for audit trail.
- **AuthMiddleware before TenantMiddleware:** TenantMiddleware reads JWT claims set by AuthMiddleware; it must run after.
- **TenantMiddleware before RateLimitMiddleware:** rate limiting is per-tenant; tenant must be resolved first.
- **RateLimitMiddleware innermost:** only rate-limits authenticated, tenant-resolved requests.

### Streaming Response for Ledger Trail (Large Tenants)

Banks and regulated enterprises may have thousands of ledger entries per entity. Stream the trail as JSON Lines (`application/x-ndjson`) to avoid loading all entries into memory. Each line is a complete, independently parseable JSON object.

```python
# delivery/api/routers/ledger_router.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

router = APIRouter(prefix="/kernel/v1/ledger", tags=["ledger"])

async def _stream_trail(
    entity_id: str,
    tenant_id: str,
    db: AsyncSession,
    after_seq: int,
) -> AsyncGenerator[bytes, None]:
    """Async generator yielding ledger entries as newline-delimited JSON."""
    from core.ledger.repository import LedgerRepository
    repo = LedgerRepository(db)
    async for entry in repo.stream_trail(entity_id=entity_id, after_seq=after_seq):
        yield (entry.model_dump_json() + "\n").encode()

@router.get(
    "/entity/{entity_id}/trail",
    summary="Stream verifiable ledger trail for an entity",
    response_class=StreamingResponse,
)
async def get_ledger_trail(
    entity_id: Annotated[str, Path()],
    after_seq: Annotated[int, Query(ge=0)] = 0,
    tenant: TenantContextDep = None,
    db: DbSessionDep = None,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_trail(entity_id, tenant.tenant_id, db, after_seq),
        media_type="application/x-ndjson",
        headers={"X-Tenant-ID": tenant.tenant_id},
    )
```

### WebSocket for Real-Time HITL Notifications

When an action enters `PENDING_APPROVAL`, the actor (or an approval dashboard) needs real-time notification. Use a WebSocket endpoint that subscribes to the internal event bus (K·07) for the tenant and action.

```python
# delivery/api/routers/actions_router.py  — WebSocket addition
from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/{action_id}/updates")
async def action_updates_ws(
    websocket: WebSocket,
    action_id: str,
    token: Annotated[str, Query()],  # JWT passed as query param for WS auth
):
    """
    Real-time state updates for a governed action.
    Sends a JSON message on each state transition (PENDING → PENDING_APPROVAL → EXECUTED/REJECTED).
    Closes when the action reaches a terminal state.
    """
    from delivery.api.auth import verify_ws_token
    claims = await verify_ws_token(token)
    tenant_id = claims["tenant_id"]
    await websocket.accept()

    from delivery.api.event_bridge import subscribe_action_updates
    try:
        async for update in subscribe_action_updates(action_id=action_id, tenant_id=tenant_id):
            await websocket.send_json(update.model_dump())
            if update.is_terminal:
                break
    except WebSocketDisconnect:
        pass  # Client disconnected — no error; event bridge cleans up subscription
    finally:
        await websocket.close()
```

### Health and Readiness Endpoints Checking All 5 Port Adapters

The health endpoint is used by Kubernetes liveness probes; the readiness endpoint by readiness probes. They check all port adapters. **Fail any probe if any adapter is unhealthy** — a partially initialised kernel must not receive traffic.

```python
# delivery/api/routers/admin_router.py  — health/readiness
from pydantic import BaseModel
from fastapi import Request, HTTPException

class AdapterStatus(BaseModel):
    name: str
    healthy: bool
    latency_ms: float | None = None
    detail: str | None = None

class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    adapters: list[AdapterStatus]

router = APIRouter(prefix="/kernel/v1", tags=["admin"])

@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check(request: Request) -> HealthResponse:
    """
    Liveness probe: checks that all 5 port adapters respond within timeout.
    Returns 200 if all healthy, 503 if any adapter is unhealthy.
    A governance kernel that is partially available is worse than unavailable
    (fail-closed: a degraded kernel must not silently pass actions).
    """
    engine: LifecycleEngine = request.app.state.lifecycle_engine
    checks = await engine.health_check_all_adapters()  # runs checks in parallel
    all_healthy = all(c.healthy for c in checks)
    response = HealthResponse(
        status="healthy" if all_healthy else "unhealthy",
        adapters=checks,
    )
    if not all_healthy:
        raise HTTPException(status_code=503, detail=response.model_dump())
    return response


@router.get("/readiness", include_in_schema=False)
async def readiness_check(request: Request):
    """
    Readiness probe: verifies the kernel has completed startup and can serve requests.
    Only ready when: DB pool warm, workflow adapter connected, packs loaded,
    AND all Alembic migrations have run for every registered tenant.
    An unmigrated tenant schema means the kernel cannot serve that tenant —
    fail-closed: do not return 200 until the tenant is fully provisioned.
    """
    engine: LifecycleEngine = request.app.state.lifecycle_engine
    ready, reason = await engine.is_ready()
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={
                "type": "https://quaicu.io/errors/not-ready",
                "title": "Kernel not ready",
                "status": 503,
                "detail": reason,
            },
        )
    return {"status": "ready"}
```

**Adapter health check contract** — every port adapter must implement:

```python
# core/ports/base.py (extend all ports with this mixin)
class HealthCheckMixin:
    async def health_check(self) -> AdapterStatus:
        """
        Must return within 2 seconds. Never raise — return AdapterStatus(healthy=False)
        on any error. A raised exception is treated as unhealthy by the engine.
        """
        ...
```

### Readiness Gate — Only Ready When Migrations Complete for Tenant

A tenant's schema must have all Alembic migrations applied before the kernel can serve requests for that tenant. The readiness endpoint checks this explicitly. This prevents a race condition where the kernel starts serving requests before the migration job has finished.

```python
# core/lifecycle/engine.py  — is_ready implementation excerpt

async def is_ready(self) -> tuple[bool, str]:
    """
    Returns (True, "") if the kernel is ready to serve all registered tenants.
    Returns (False, reason) for the first unready condition found.

    Readiness requires:
    1. Storage pool is warm and reachable.
    2. Workflow adapter is connected (Temporal) or available (Postgres statemachine).
    3. All registered tenants have completed Alembic migrations.
    4. At least one content pack (policy pack) is loaded.
    """
    # Check 1: storage
    if not await self._storage.ping():
        return False, "Storage adapter unreachable"

    # Check 2: workflow
    if not await self._workflow.ping():
        return False, "Workflow adapter unreachable"

    # Check 3: tenant migrations — critical for multi-tenant deployments
    unmigrated = await self._storage.list_unmigrated_tenants()
    if unmigrated:
        return False, (
            f"Tenants with pending migrations: {unmigrated}. "
            "The kernel will not serve requests for these tenants until migrations complete."
        )

    # Check 4: packs loaded
    if not await self._policy_engine.has_active_policies():
        return False, "No active policy packs loaded — kernel cannot govern any actions"

    return True, ""
```

### Policies Router — Evaluate Endpoint for Pre-Flight

The `POST /kernel/v1/policy/evaluate` endpoint (spec §3.9 "single-action pre-flight") dry-runs a proposed action without enforcing. It is side-effect-free: no ledger entry is written, no HITL request is created.

```python
# delivery/api/routers/policies_router.py
router = APIRouter(prefix="/kernel/v1/policy", tags=["policies"])

class PolicyEvaluateRequest(BaseModel):
    action_type: str
    action_payload: dict
    tenant_id: str | None = None   # defaults to JWT tenant if omitted

class PolicyEvaluateResponse(BaseModel):
    decision: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    deciding_policy_id: str | None = None
    deciding_policy_version: int | None = None
    reason: str

@router.post(
    "/evaluate",
    response_model=PolicyEvaluateResponse,
    summary="Dry-run a proposed action against active policies (no enforcement)",
)
async def evaluate_policy_preflight(
    payload: PolicyEvaluateRequest,
    engine: LifecycleEngineDep,
    tenant: TenantContextDep,
) -> PolicyEvaluateResponse:
    """
    Side-effect-free policy pre-flight. Returns the governance decision that would
    apply if this action were proposed, without writing to the ledger, triggering
    HITL, or executing anything. Use before proposing to give users early feedback.
    """
    result = await engine.evaluate_preflight(
        action_type=payload.action_type,
        action_payload=payload.action_payload,
        tenant_id=tenant.tenant_id,
    )
    return PolicyEvaluateResponse(
        decision=result.decision.value,
        deciding_policy_id=result.deciding_policy_id,
        deciding_policy_version=result.deciding_policy_version,
        reason=result.reason,
    )
```
