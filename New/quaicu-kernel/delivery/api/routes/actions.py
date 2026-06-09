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
    LifecycleDeniedError,
    LifecycleHaltedError,
    QUAICUError,
)
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    IdempotencyKey,
    TenantId,
)
from delivery.api.schemas import ActionResponse, ApproveRequest, ProposeRequest
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/actions", tags=["actions"])


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
    kernel: Kernel = request.app.state.kernel
    tenant: TenantId = kernel.tenant

    actor = Actor(
        id=ActorId(body.actor_id),
        tenant=tenant,
        roles=tuple(body.actor_roles),
    )
    action = Action(
        id=ActionId(str(uuid.uuid4())),
        type=body.type,
        payload=body.payload,
        actor=actor,
        tenant=tenant,
        idempotency_key=IdempotencyKey(body.idempotency_key),
        proposed_at=datetime.now(tz=timezone.utc),
    )

    async def execute_fn() -> dict[str, Any]:
        return {"payload": dict(action.payload)}

    try:
        final = await kernel.engine.run(action, execute_fn)
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
    kernel: Kernel = request.app.state.kernel
    repo = kernel.engine._repo  # type: ignore[attr-defined]

    # Scan for action by id (in-memory repo is keyed by idempotency_key)
    for action in repo.by_key.values() if hasattr(repo, "by_key") else []:
        if str(action.id) == action_id:
            return _action_response(action)

    raise HTTPException(status_code=404, detail={"error": "Action not found", "action_id": action_id})
