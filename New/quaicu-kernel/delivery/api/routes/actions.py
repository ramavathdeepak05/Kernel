"""Action lifecycle routes — propose / approve / status.

POST /v1/actions/propose  →  202 ActionResponse (or 200 on idempotency hit)
GET  /v1/actions/{id}     →  200 ActionResponse
POST /v1/actions/{id}/approve  →  200 ActionResponse  (webhook HITL short-circuit)

These routes are thin adapters over LifecycleEngine. No business logic here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from core.errors import (
    QUAICUError,
)
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    IdempotencyKey,
    RequestContext,
    TenantId,
)
from core.account.scopes import ACTIONS_READ, ACTIONS_WRITE
from delivery.api.auth import enforce_scope
from delivery.api.deps import get_kernel, get_request_tenant
from delivery.api.schemas import ActionResponse, ProposeRequest
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/actions", tags=["actions"])


def _bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header, or 401.

    The kernel never trusts a caller-supplied identity — the actor is resolved from this token
    by the configured IdentityPort.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing or malformed bearer token", "code": "UNAUTHENTICATED"},
        )
    return token.strip()


def _action_response(action: Action) -> ActionResponse:
    return ActionResponse(
        action_id=str(action.id),
        state=action.state.value,
        type=action.type,
        tenant=str(action.tenant),
        actor_id=str(action.actor.id),
    )


@router.post(
    "/propose",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ActionResponse,
    summary="Propose a governed action",
)
async def propose_action(body: ProposeRequest, request: Request) -> ActionResponse:
    """Drive an action through the full governance lifecycle.

    Returns 202 on first submission; 200 on idempotency hit (same action returned).
    Returns 403 if policy denies; 422 if a lifecycle halt occurs.
    """
    kernel: Kernel = get_kernel(request)
    tenant: TenantId = get_request_tenant(request)

    # Authentication is mandatory on the standalone API: extract the bearer token and require a
    # configured IdentityPort. The actor is resolved from the token by the engine — never trusted
    # from the request body.
    token = _bearer_token(request)
    enforce_scope(request, ACTIONS_WRITE)
    if not kernel.has_identity:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "API requires an identity adapter to authenticate callers",
                "code": "IDENTITY_NOT_CONFIGURED",
            },
        )

    ctx = RequestContext(
        headers=dict(request.headers),
        source_ip=request.client.host if request.client else None,
        raw_token=token,
        tenant_hint=tenant,
    )

    # Placeholder actor — the engine replaces it with the token-resolved identity during _propose.
    placeholder_actor = Actor(id=ActorId("unresolved"), tenant=tenant)
    action = Action(
        id=ActionId(str(uuid.uuid4())),
        type=body.type,
        payload=body.payload,
        actor=placeholder_actor,
        tenant=tenant,
        idempotency_key=IdempotencyKey(body.idempotency_key),
        proposed_at=datetime.now(tz=timezone.utc),
    )

    async def execute_fn() -> dict[str, Any]:
        return {"payload": dict(action.payload)}

    try:
        final = await kernel.engine.run(action, execute_fn, context=ctx)
    except QUAICUError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc), "code": exc.code})

    if final.state is ActionState.DENIED:
        raise HTTPException(
            status_code=403,
            detail={"error": "Action denied by governance", "action_id": str(final.id)},
        )
    if final.state is ActionState.HALTED:
        raise HTTPException(
            status_code=422,
            detail={"error": "Action halted by governance", "action_id": str(final.id)},
        )

    return _action_response(final)


@router.get(
    "/{action_id}",
    response_model=ActionResponse,
    summary="Get action state",
)
async def get_action(action_id: str, request: Request) -> ActionResponse:
    """Look up an action by id.

    Returns 404 if the action is not found (this implementation uses the in-memory
    repo; a postgres adapter would query the DB).
    """
    enforce_scope(request, ACTIONS_READ)
    kernel: Kernel = get_kernel(request)
    repo = kernel.engine._repo  # type: ignore[attr-defined]

    # Scan for action by id (in-memory repo is keyed by idempotency_key)
    for action in repo.by_key.values() if hasattr(repo, "by_key") else []:
        if str(action.id) == action_id:
            return _action_response(action)

    raise HTTPException(status_code=404, detail={"error": "Action not found", "action_id": action_id})
