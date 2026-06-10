"""Authorization route — pure policy-decision endpoint (PDP).

POST /v1/authorize  →  200 AuthorizeResponse (always 200; check ``allowed`` in the body)

This is a **decision-only** endpoint: the kernel evaluates policy + consent + identity for the
requested action type and returns a verdict. No action is executed, no state is transitioned.
The caller (the PEP — Policy Enforcement Point) decides what to do with the verdict.

Monitoring: under the default governance profile (``all()``) every decision is sealed into the
tamper-evident ledger. Pass ``record: false`` in the body to suppress sealing on the hot path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.errors import QUAICUError
from core.types import Actor, ActorId, RequestContext
from delivery.api.routes.actions import _bearer_token
from delivery.api.schemas import AuthorizeRequest, AuthorizeResponse
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1", tags=["authorize"])


@router.post(
    "/authorize",
    response_model=AuthorizeResponse,
    summary="Pure policy-decision query (PDP)",
)
async def authorize(body: AuthorizeRequest, request: Request) -> AuthorizeResponse:
    """Check whether an action is allowed without performing it.

    Always returns 200 — the verdict is in the body (``allowed``, ``decision``). HTTP 4xx/5xx are
    only raised for infrastructure errors (missing identity adapter, kernel fault). The caller is
    the enforcement point.
    """
    kernel: Kernel = request.app.state.kernel

    token = _bearer_token(request)
    if not kernel.has_identity:
        raise HTTPException(
            status_code=503,
            detail={"error": "API requires an identity adapter", "code": "IDENTITY_NOT_CONFIGURED"},
        )

    ctx = RequestContext(
        headers=dict(request.headers),
        source_ip=request.client.host if request.client else None,
        raw_token=token,
        tenant_hint=kernel.tenant,
    )
    placeholder_actor = Actor(id=ActorId("unresolved"), tenant=kernel.tenant)

    try:
        result = await kernel.check(
            action_type=body.type,
            actor=placeholder_actor,
            payload=body.payload,
            idempotency_key=body.idempotency_key,
            context=ctx,
            record=body.record,
        )
    except QUAICUError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc), "code": exc.code})

    return AuthorizeResponse(
        decision=result.decision.value,
        allowed=result.allowed,
        actor_id=str(result.actor_id),
        reason=result.reason,
        policy_versions=list(result.policy_versions),
        approvers=list(result.approvers),
        enforced_layers=list(result.enforced_layers),
        sealed=result.sealed,
        ledger_seq=result.ledger_seq,
    )
