---
name: fastapi
description: FastAPI best practices and conventions. Use when working with FastAPI APIs and Pydantic models for them. Keeps FastAPI code clean and up to date with the latest features and patterns, updated with new versions. Write new code or refactor and update old code. QUAICU kernel — the delivery/api REST surface, a thin wrapper over the kernel SDK; tenant_id from the validated JWT into a ContextVar via middleware, RFC 7807 problem-details errors, fail-closed status codes (202 propose, 403 denied, 409 idempotency, 503 fail-closed). Triggers — QUAICU, delivery/api, kernel REST, tenant middleware, RFC 7807, propose endpoint.
---

# FastAPI

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific API choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** Missing rule → return an error, never proceed unguarded.

### Invariants — never violated
- The API lives in `delivery/api/` and is a THIN wrapper over the kernel SDK. NEVER put governance logic (policy, ledger, lifecycle) in a route handler.
- Resolve `tenant_id` from the validated JWT claim, set it in the ContextVar via middleware, and pass it down. NEVER read tenant_id from a query param or body.
- All errors use RFC 7807 Problem Details (`application/problem+json`). NEVER leak stack traces or raw exception text.
- Inject the five ports via `app.state` (constructed once at startup). NEVER construct adapters per-request.
- ContextVars do NOT propagate into background tasks — re-set the tenant inside the task.

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

### Self-check
- [ ] Handlers are thin; no governance logic in routes.
- [ ] tenant_id from JWT → ContextVar via middleware.
- [ ] All errors are RFC 7807; status codes match the map.
- [ ] Ports injected from app.state, not per-request.

---

Official FastAPI skill to write code with best practices, keeping up to date with new versions and features.

## Use the `fastapi` CLI

Run the development server on localhost with reload:

```bash
fastapi dev
```


Run the production server:

```bash
fastapi run
```

### Add an entrypoint in `pyproject.toml`

FastAPI CLI will read the entrypoint in `pyproject.toml` to know where the FastAPI app is declared.

```toml
[tool.fastapi]
entrypoint = "my_app.main:app"
```

### Use `fastapi` with a path

When adding the entrypoint to `pyproject.toml` is not possible, or the user explicitly asks not to, or it's running an independent small app, you can pass the app file path to the `fastapi` command:

```bash
fastapi dev my_app/main.py
```

Prefer to set the entrypoint in `pyproject.toml` when possible.

## Use `Annotated`

Always prefer the `Annotated` style for parameter and dependency declarations.

It keeps the function signatures working in other contexts, respects the types, allows reusability.

### In Parameter Declarations

Use `Annotated` for parameter declarations, including `Path`, `Query`, `Header`, etc.:

```python
from typing import Annotated

from fastapi import FastAPI, Path, Query

app = FastAPI()


@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
):
    return {"message": "Hello World"}
```

instead of:

```python
# DO NOT DO THIS
@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(ge=1, description="The item ID"),
    q: str | None = Query(default=None, max_length=50),
):
    return {"message": "Hello World"}
```

### For Dependencies

Use `Annotated` for dependencies with `Depends()`.

Unless asked not to, create a new type alias for the dependency to allow re-using it.

```python
from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


@app.get("/items/")
async def read_item(current_user: CurrentUserDep):
    return {"message": "Hello World"}
```

instead of:

```python
# DO NOT DO THIS
@app.get("/items/")
async def read_item(current_user: dict = Depends(get_current_user)):
    return {"message": "Hello World"}
```

## Do not use Ellipsis for *path operations* or Pydantic models

Do not use `...` as a default value for required parameters, it's not needed and not recommended.

Do this, without Ellipsis (`...`):

```python
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float = Field(gt=0)


app = FastAPI()


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query()]): ...
```

instead of this:

```python
# DO NOT DO THIS
class Item(BaseModel):
    name: str = ...
    description: str | None = None
    price: float = Field(..., gt=0)


app = FastAPI()


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query(...)]): ...
```

## Return Type or Response Model

When possible, include a return type. It will be used to validate, filter, document, and serialize the response.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me")
async def get_item() -> Item:
    return Item(name="Plumbus", description="All-purpose home device")
```

**Important**: Return types or response models are what filter data ensuring no sensitive information is exposed. And they are used to serialize data with Pydantic (in Rust), this is the main idea that can increase response performance.

The return type doesn't have to be a Pydantic model, it could be a different type, like a list of integers, or a dict, etc.

### When to use `response_model` instead

If the return type is not the same as the type that you want to use to validate, filter, or serialize, use the `response_model` parameter on the decorator instead.

```python
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me", response_model=Item)
async def get_item() -> Any:
    return {"name": "Foo", "description": "A very nice Item"}
```

This can be particularly useful when filtering data to expose only the public fields and avoid exposing sensitive information.

```python
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class InternalItem(BaseModel):
    name: str
    description: str | None = None
    secret_key: str


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me", response_model=Item)
async def get_item() -> Any:
    item = InternalItem(
        name="Foo", description="A very nice Item", secret_key="supersecret"
    )
    return item
```

## Performance

Do not use `ORJSONResponse` or `UJSONResponse`, they are deprecated.

Instead, declare a return type or response model. Pydantic will handle the data serialization on the Rust side.

## Including Routers

When declaring routers, prefer to add router level parameters like prefix, tags, etc. to the router itself, instead of in `include_router()`.

Do this:

```python
from fastapi import APIRouter, FastAPI

app = FastAPI()

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/")
async def list_items():
    return []


# In main.py
app.include_router(router)
```

instead of this:

```python
# DO NOT DO THIS
from fastapi import APIRouter, FastAPI

app = FastAPI()

router = APIRouter()


@router.get("/")
async def list_items():
    return []


# In main.py
app.include_router(router, prefix="/items", tags=["items"])
```

There could be exceptions, but try to follow this convention.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Dependency Injection

See [the dependency injection reference](references/dependencies.md) for detailed patterns including `yield` with `scope`, and class dependencies.

Use dependencies when the logic can't be declared in Pydantic validation, depends on external resources, needs cleanup (with `yield`), or is shared across endpoints.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Async vs Sync *path operations*

Use `async` *path operations* only when fully certain that the logic called inside is compatible with async and await (it's called with `await`) or that doesn't block.

```python
from fastapi import FastAPI

app = FastAPI()


# Use async def when calling async code
@app.get("/async-items/")
async def read_async_items():
    data = await some_async_library.fetch_items()
    return data


# Use plain def when calling blocking/sync code or when in doubt
@app.get("/items/")
def read_items():
    data = some_blocking_library.fetch_items()
    return data
```

In case of doubt, or by default, use regular `def` functions, those will be run in a threadpool so they don't block the event loop.

The same rules apply to dependencies.

Make sure blocking code is not run inside of `async` functions. The logic will work, but will damage the performance heavily.

When needing to mix blocking and async code, see Asyncer in [the other tools reference](references/other-tools.md).

## Streaming (JSON Lines, SSE, bytes)

See [the streaming reference](references/streaming.md) for JSON Lines, Server-Sent Events (`EventSourceResponse`, `ServerSentEvent`), and byte streaming (`StreamingResponse`) patterns.

## Tooling

See [the other tools reference](references/other-tools.md) for details on uv, Ruff, ty for package management, linting, type checking, formatting, etc.

## Other Libraries

See [the other tools reference](references/other-tools.md) for details on other libraries:

* Asyncer for handling async and await, concurrency, mixing async and blocking code, prefer it over AnyIO or asyncio.
* SQLModel for working with SQL databases, prefer it over SQLAlchemy.
* HTTPX for interacting with HTTP (other APIs), prefer it over Requests.

## Do not use Pydantic RootModels

Do not use Pydantic `RootModel`, instead use regular type annotations with `Annotated` and Pydantic validation utilities.

For example, for a list with validations you could do:

```python
from typing import Annotated

from fastapi import Body, FastAPI
from pydantic import Field

app = FastAPI()


@app.post("/items/")
async def create_items(items: Annotated[list[int], Field(min_length=1), Body()]):
    return items
```

instead of:

```python
# DO NOT DO THIS
from typing import Annotated

from fastapi import FastAPI
from pydantic import Field, RootModel

app = FastAPI()


class ItemList(RootModel[Annotated[list[int], Field(min_length=1)]]):
    pass


@app.post("/items/")
async def create_items(items: ItemList):
    return items

```

FastAPI supports these type annotations and will create a Pydantic `TypeAdapter` for them, so that types can work as normally and there's no need for the custom logic and types in RootModels.

## Use one HTTP operation per function

Don't mix HTTP operations in a single function, having one function per HTTP operation helps separate concerns and organize the code.

Do this:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.get("/items/")
async def list_items():
    return []


@app.post("/items/")
async def create_item(item: Item):
    return item
```

instead of this:

```python
# DO NOT DO THIS
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.api_route("/items/", methods=["GET", "POST"])
async def handle_items(request: Request):
    if request.method == "GET":
        return []
```

---

## QUAICU-Specific Application

This section covers patterns for the `delivery/api/` FastAPI application in the QUAICU governance kernel. The REST delivery mode is a **thin wrapper over core** — it translates HTTP into `core/lifecycle/` calls and never implements business logic directly. All patterns here are consistent with the spec's hexagonal architecture (F-08) and tenant isolation requirements (§3.10, F-07).

### Router Structure (`delivery/api/`)

The API mounts four routers under the `/kernel/v1` prefix. Each router enforces the tenant middleware and carries shared dependencies at the router level.

```python
# delivery/api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from delivery.api.middleware import LoggingMiddleware, AuthMiddleware, TenantMiddleware, RateLimitMiddleware
from delivery.api.routers import actions, policies, ledger, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pools and port adapters once at startup.
    # See the fastapi-expert QUAICU section for the full lifespan pattern.
    await startup_adapters(app)
    yield
    await shutdown_adapters(app)

app = FastAPI(
    title="QUAICU Governance Kernel",
    version="1.0.0",
    lifespan=lifespan,
    # Disable the default /docs in production; expose only to internal networks.
    docs_url="/internal/docs",
    redoc_url="/internal/redoc",
)

# Middleware stack — order matters (applied bottom-up by Starlette):
# Request passes: logging → auth → tenant → rate-limit → route
# See fastapi-expert QUAICU section for stack ordering rationale.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(LoggingMiddleware)

# Routers — all under /kernel/v1
app.include_router(actions.router)    # /kernel/v1/actions
app.include_router(policies.router)   # /kernel/v1/policy
app.include_router(ledger.router)     # /kernel/v1/ledger
app.include_router(admin.router)      # /kernel/v1/admin
```

**Actions router** — the primary lifecycle surface:

```python
# delivery/api/routers/actions.py
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, status
from delivery.api.dependencies import LifecycleEngineDep, TenantContextDep
from delivery.api.schemas import ProposeActionRequest, ActionResponse, EvaluateRequest, EvaluateResponse

router = APIRouter(prefix="/kernel/v1/actions", tags=["actions"])

@router.post(
    "/propose",
    response_model=ActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Propose a governed action",
)
async def propose_action(
    body: ProposeActionRequest,
    tenant: TenantContextDep,
    engine: LifecycleEngineDep,
    background_tasks: BackgroundTasks,
) -> ActionResponse:
    """
    Submits a governed action into the lifecycle.
    Returns 202 immediately; the action is PENDING while evaluate/gate runs.
    For REQUIRE_APPROVAL decisions the state will be PENDING_APPROVAL.
    Poll GET /actions/{id} or subscribe to the WebSocket for state updates.
    """
    handle = await engine.propose(body.to_action(tenant.tenant_id))
    # For Temporal adapter: workflow is started; poll asynchronously.
    # For Postgres state-machine adapter: synchronous transitions occur in-process.
    background_tasks.add_task(_poll_until_terminal, handle, tenant.tenant_id)
    return ActionResponse.from_handle(handle)

@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: Annotated[str, Path(description="Governed action ID")],
    tenant: TenantContextDep,
    engine: LifecycleEngineDep,
) -> ActionResponse:
    """Poll for current action state."""
    state = await engine.get_state(action_id=action_id, tenant_id=tenant.tenant_id)
    return ActionResponse.from_state(state)

@router.post("/{action_id}/approve", response_model=ActionResponse)
async def approve_action(
    action_id: Annotated[str, Path()],
    tenant: TenantContextDep,
    engine: LifecycleEngineDep,
) -> ActionResponse:
    """Human approves a PENDING_APPROVAL action (K·03 HITL gate)."""
    result = await engine.approve(action_id=action_id, tenant_id=tenant.tenant_id)
    return ActionResponse.from_result(result)

@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(
    action_id: Annotated[str, Path()],
    tenant: TenantContextDep,
    engine: LifecycleEngineDep,
) -> ActionResponse:
    """Human rejects a PENDING_APPROVAL action."""
    result = await engine.reject(action_id=action_id, tenant_id=tenant.tenant_id)
    return ActionResponse.from_result(result)

@router.post("/evaluate", response_model=EvaluateResponse)
async def pre_flight_evaluate(
    body: EvaluateRequest,
    tenant: TenantContextDep,
    engine: LifecycleEngineDep,
) -> EvaluateResponse:
    """
    Dry-run policy evaluation for a single proposed action — side-effect free.
    Does NOT propose, execute, seal, or emit. Returns what the decision WOULD be.
    Per spec §3.9: 'POST /kernel/v1/policy/evaluate' pre-flight.
    """
    result = await engine.evaluate_only(body.to_action(tenant.tenant_id))
    return EvaluateResponse.from_result(result)
```

**Policies router** — policy lifecycle management:

```python
# delivery/api/routers/policies.py
router = APIRouter(prefix="/kernel/v1/policy", tags=["policy"])

# Endpoints: GET /list, POST /create, GET /{id}, POST /{id}/activate,
#            POST /evaluate (pre-flight, also linked from actions router),
#            POST /{id}/simulate (backtest / shadow-mode trigger per §3.9)
```

**Ledger router** — audit trail and integrity proofs:

```python
# delivery/api/routers/ledger.py
router = APIRouter(prefix="/kernel/v1/ledger", tags=["ledger"])

# GET /entity/{entity_id}/trail — paginated ledger entries for an entity
# GET /verify                   — returns a signed STH (Signed Tree Head) proof
# GET /entry/{seq}/proof        — RFC 6962 inclusion proof for a specific entry
```

**Admin router** — tenant and adapter management (restricted; internal network only):

```python
# delivery/api/routers/admin.py
router = APIRouter(
    prefix="/kernel/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_role)],  # enforced at router level
)

# POST /tenants        — onboard a new tenant (creates schema, loads packs)
# GET  /health         — health check (all adapters; see fastapi-expert section)
# GET  /readiness      — readiness probe
```

### Tenant Middleware: Extract Tenant from JWT, Set ContextVar

The tenant is resolved from the JWT once per request and stored in a `contextvars.ContextVar` so that any downstream code (repositories, port calls) can read it without threading it through every function signature.

```python
# delivery/api/middleware/tenant.py
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from delivery.api.auth import decode_jwt_tenant

# Module-level ContextVar — set per request, isolated across async tasks.
_current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("current_tenant")

def get_current_tenant_id() -> str:
    """Call from anywhere within a request context."""
    try:
        return _current_tenant.get()
    except LookupError:
        raise RuntimeError("Tenant context not set — request did not pass TenantMiddleware")

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # AuthMiddleware (applied before TenantMiddleware) has already validated
        # the JWT and stored the decoded claims in request.state.
        tenant_id: str | None = getattr(request.state, "jwt_claims", {}).get("tenant_id")
        if not tenant_id:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"type": "about:blank", "title": "Forbidden",
                         "detail": "No tenant claim in token", "status": 403},
            )
        # Set the ContextVar for this request's async context.
        token = _current_tenant.set(tenant_id)
        try:
            response = await call_next(request)
        finally:
            _current_tenant.reset(token)
        return response
```

### Dependency Injection for Lifecycle Engine and Ports

Port adapters are initialised once (in the lifespan handler) and injected as FastAPI dependencies. Core never sees the concrete adapter type — only the port interface.

```python
# delivery/api/dependencies.py
from typing import Annotated
from fastapi import Depends, Request
from core.lifecycle.engine import LifecycleEngine
from delivery.api.middleware.tenant import get_current_tenant_id

async def get_lifecycle_engine(request: Request) -> LifecycleEngine:
    """Returns the kernel's LifecycleEngine, pre-wired with all port adapters."""
    return request.app.state.lifecycle_engine

async def get_tenant_context(
    engine: Annotated[LifecycleEngine, Depends(get_lifecycle_engine)],
) -> "TenantContext":
    tenant_id = get_current_tenant_id()
    # Verifies the tenant exists and is active; raises 404 if not.
    tenant = await engine.get_tenant(tenant_id)
    return TenantContext(tenant_id=tenant.id, tenant=tenant)

# Reusable type-aliases for endpoint signatures
LifecycleEngineDep = Annotated[LifecycleEngine, Depends(get_lifecycle_engine)]
TenantContextDep = Annotated["TenantContext", Depends(get_tenant_context)]
```

### Background Task for Async Workflow Polling

When the Temporal adapter is active, `propose` starts a workflow and returns a handle immediately. A background task polls for terminal state and notifies via the event bus (K·07). This prevents HTTP timeouts for long-running governed actions (e.g. those awaiting HITL).

```python
# delivery/api/routers/actions.py  (background task helper)
import asyncio
from core.ports.workflow import WorkflowHandle

async def _poll_until_terminal(handle: WorkflowHandle, tenant_id: str) -> None:
    """
    Polls the workflow adapter for terminal state, then publishes an event.
    Only used for the Temporal adapter — the Postgres state-machine adapter
    resolves synchronously and does not need polling.
    """
    from delivery.api.dependencies import _get_event_bus
    event_bus = await _get_event_bus()
    max_polls = 120  # 10-minute cap (120 × 5 s)
    for _ in range(max_polls):
        state = await handle.get_state()
        if state.is_terminal:
            await event_bus.publish(state.to_event(tenant_id=tenant_id))
            return
        await asyncio.sleep(5)
    # Exceeded poll cap — log and alert; action remains in PENDING state.
    # The HITL timeout in the workflow itself will eventually resolve it fail-closed.
```

### OpenAPI Schema Customization: Action Types as Enum

Action types are the primary discriminator for policy routing. Expose them as an enum in the OpenAPI schema so generated clients get type-safe action type values from the loaded content packs.

```python
# delivery/api/schemas/actions.py
from enum import Enum
from pydantic import BaseModel, Field
import json

# Dynamically built from loaded content packs at startup.
# In tests and docs generation, use the fixed set below as a representative sample.
class ActionTypeEnum(str, Enum):
    IFRS9_STAGE_TRANSITION = "ciro.ifrs9.stage_transition"
    DPDP_CONSENT_GRANT     = "dpdp.consent.grant"
    DPDP_CONSENT_REVOKE    = "dpdp.consent.revoke"
    MODEL_DEPLOYMENT       = "quaicu.model.deploy"
    POLICY_ACTIVATE        = "quaicu.policy.activate"

class ProposeActionRequest(BaseModel):
    type: ActionTypeEnum = Field(description="Governed action type (must be registered in loaded packs)")
    payload: dict        = Field(description="Action-type-specific payload; validated against the action schema")
    idempotency_key: str = Field(min_length=16, max_length=128, description="Client-generated idempotency key")

    def to_action(self, tenant_id: str):
        from core.lifecycle.models import Action
        return Action(
            type=self.type.value,
            payload=self.payload,
            tenant_id=tenant_id,
            idempotency_key=self.idempotency_key,
        )
```

### Error Response Format: RFC 7807 Problem Details

All error responses from QUAICU's API use RFC 7807 Problem Details (`application/problem+json`). This is the format bank and enterprise integrators expect, and it makes error semantics unambiguous in logs.

```python
# delivery/api/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

def problem_detail(status: int, title: str, detail: str, **extra) -> dict:
    return {"type": "about:blank", "title": title, "detail": detail, "status": status, **extra}

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content=problem_detail(exc.status_code, exc.detail, exc.detail),
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content=problem_detail(422, "Unprocessable Entity", str(exc.errors())),
    )

async def governance_denial_handler(request: Request, exc: "GovernanceDeniedError") -> JSONResponse:
    """
    Raised by the lifecycle engine when an action is denied at any step.
    Includes the policy decision and the step at which denial occurred.
    """
    return JSONResponse(
        status_code=403,
        media_type="application/problem+json",
        content=problem_detail(
            403, "Governance Denial",
            f"Action denied at step '{exc.step}': {exc.reason}",
            step=exc.step,
            policy_id=exc.policy_id,
        ),
    )

# Register in main.py:
# app.add_exception_handler(HTTPException, http_exception_handler)
# app.add_exception_handler(RequestValidationError, validation_exception_handler)
# app.add_exception_handler(GovernanceDeniedError, governance_denial_handler)
```
