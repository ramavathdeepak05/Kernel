"""Ledger routes — trail and verify.

GET /v1/ledger/{tenant}/trail  →  200 LedgerTrailResponse
GET /v1/ledger/health          →  200 { "ok": true }
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.account.scopes import LEDGER_READ
from core.types import TenantId
from delivery.api.auth import enforce_scope
from delivery.api.deps import get_kernel, get_request_tenant
from delivery.api.routes.actions import _bearer_token
from delivery.api.schemas import LedgerEntryResponse, LedgerTrailResponse

router = APIRouter(prefix="/v1/ledger", tags=["ledger"])


@router.get(
    "/{tenant}/trail",
    response_model=LedgerTrailResponse,
    summary="List sealed ledger entries for a tenant",
)
async def ledger_trail(tenant: str, request: Request) -> LedgerTrailResponse:
    """Return the sealed ledger entries for the requested tenant.

    Requires a bearer token (401 if absent). The audit trail is tenant-private: the path tenant
    must match this kernel instance's tenant (F-07) — any mismatch is 403, never a silent empty
    result. Entries are read via the ledger's tenant-scoped ``get_entries`` and projected to the
    API schema.
    """
    _bearer_token(request)  # require authentication
    enforce_scope(request, LEDGER_READ)

    kernel = get_kernel(request)
    if tenant != str(get_request_tenant(request)):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Cannot read another tenant's audit trail",
                "code": "TENANT_ISOLATION",
            },
        )

    ledger = kernel.engine._ledger  # type: ignore[attr-defined]
    entries = ledger.get_entries(TenantId(tenant))

    projected = [
        LedgerEntryResponse(
            ledger_seq=e.ledger_seq,
            action_id=str(e.action_id),
            action_type=e.action_type,
            actor_id=str(e.actor_id),
            decision=e.decision.value,
            policy_versions=list(e.policy_versions),
            sealed_at=e.sealed_at.isoformat(),
            approver=str(e.approver) if e.approver else None,
        )
        for e in entries
    ]

    return LedgerTrailResponse(tenant=tenant, entries=projected, count=len(projected))


@router.get("/health", summary="Ledger health check")
async def ledger_health(request: Request) -> dict:
    return {"ok": True}
