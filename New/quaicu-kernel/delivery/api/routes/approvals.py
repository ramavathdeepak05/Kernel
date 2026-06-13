"""HITL approvals routes — the operator approval queue (K·03).

A reviewable queue over the in-process HITL port: list pending approvals and approve/reject them.
Every endpoint resolves the caller from the bearer token via the IdentityPort; the HITL port itself
enforces approver eligibility + the self-approval guard on decide.

    GET  /v1/approvals                       → 200 list pending approval records
    POST /v1/approvals/{handle_id}/approve   → 200 approve (actor from token)
    POST /v1/approvals/{handle_id}/reject    → 200 reject  (actor from token)

Caveat (deployment model): under the synchronous LifecycleEngine.run (default max_poll_attempts=1) a
REQUIRE_APPROVAL action polls once and times out → DENIED, which can leave a stale PENDING record.
A real "suspend then resume on approval" flow needs the async K·06 process engine or the webhook
adapter (whose queue lives in an external system, so it is not listable here → 503). This surface is
the operator queue over the in-process approval store; it does not itself resume a denied action.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.account.scopes import APPROVAL_DECIDE, APPROVAL_READ
from core.errors import HITLPortError, IdentityPortError
from core.hitl.model import ApprovalRecord
from core.types import Actor, RequestContext, TenantId
from delivery.api.auth import enforce_scope
from delivery.api.deps import get_kernel, get_request_tenant
from delivery.api.routes.actions import _bearer_token
from delivery.api.schemas import ApprovalListResponse, ApprovalRecordResponse
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


async def _authenticate(request: Request, *, scope: str) -> tuple[Kernel, Actor, TenantId]:
    """Resolve the caller from the bearer token; require an in-process HITL port and ``scope``.

    503 if no identity adapter or no in-process HITL port; 401 if the token cannot be resolved; 403
    if the API key lacks ``scope`` (no-op when API-key auth is disabled). Returns the serving kernel,
    the resolved actor, and the request's tenant.
    """
    enforce_scope(request, scope)
    kernel: Kernel = get_kernel(request)
    tenant = get_request_tenant(request)
    if kernel._in_process_hitl() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Approvals require an in-process HITL port (an external/webhook queue "
                "is managed by its own system)",
                "code": "HITL_QUEUE_UNAVAILABLE",
            },
        )
    token = _bearer_token(request)
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
    try:
        actor = await kernel.resolve_actor(ctx, tenant=tenant)
    except IdentityPortError as exc:
        raise HTTPException(status_code=401, detail={"error": str(exc), "code": exc.code})
    return kernel, actor, tenant


def _to_response(record: ApprovalRecord) -> ApprovalRecordResponse:
    return ApprovalRecordResponse(
        handle_id=record.handle_id,
        action_id=str(record.action_id),
        tenant=str(record.tenant),
        required_approvers=[str(a) for a in record.required_approvers],
        requested_at=record.requested_at.isoformat(),
        decision=record.decision.value,
        decided_by=str(record.decided_by) if record.decided_by else None,
        decided_at=record.decided_at.isoformat() if record.decided_at else None,
        expires_at=record.expires_at.isoformat() if record.expires_at else None,
        proposed_by=str(record.proposed_by) if record.proposed_by else None,
    )


@router.get("", response_model=ApprovalListResponse, summary="List pending HITL approvals")
async def list_approvals(request: Request) -> ApprovalListResponse:
    kernel, _, tenant = await _authenticate(request, scope=APPROVAL_READ)
    records = [r for r in kernel.list_pending_approvals() if str(r.tenant) == str(tenant)]
    return ApprovalListResponse(
        approvals=[_to_response(r) for r in records], count=len(records)
    )


@router.post(
    "/{handle_id}/approve",
    response_model=ApprovalRecordResponse,
    summary="Approve a pending HITL request",
)
async def approve(handle_id: str, request: Request) -> ApprovalRecordResponse:
    """Approve as the token-resolved actor. 404 if absent; 409 if already decided / not authorized /
    expired / self-approval."""
    return await _decide(request, handle_id, "approved")


@router.post(
    "/{handle_id}/reject",
    response_model=ApprovalRecordResponse,
    summary="Reject a pending HITL request",
)
async def reject(handle_id: str, request: Request) -> ApprovalRecordResponse:
    return await _decide(request, handle_id, "rejected")


async def _decide(request: Request, handle_id: str, decision: str) -> ApprovalRecordResponse:
    kernel, actor, tenant = await _authenticate(request, scope=APPROVAL_DECIDE)
    record = kernel._in_process_hitl().get_record(handle_id)  # type: ignore[union-attr]
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Approval {handle_id!r} not found", "code": "APPROVAL_NOT_FOUND"},
        )
    if str(record.tenant) != str(tenant):
        raise HTTPException(
            status_code=403,
            detail={"error": "Cannot decide another tenant's approval", "code": "TENANT_ISOLATION"},
        )
    try:
        updated = await kernel.decide_approval(handle_id, decision=decision, actor=actor)
    except HITLPortError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})
    return _to_response(updated)
