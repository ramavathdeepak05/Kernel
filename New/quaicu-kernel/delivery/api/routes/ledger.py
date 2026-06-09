"""Ledger routes — trail and verify.

GET /v1/ledger/{tenant}/trail  →  200 LedgerTrailResponse
GET /v1/ledger/health          →  200 { "ok": true }
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from delivery.api.schemas import LedgerEntryResponse, LedgerTrailResponse

router = APIRouter(prefix="/v1/ledger", tags=["ledger"])


@router.get(
    "/{tenant}/trail",
    response_model=LedgerTrailResponse,
    summary="List sealed ledger entries for a tenant",
)
async def ledger_trail(tenant: str, request: Request) -> LedgerTrailResponse:
    """Return all sealed ledger entries for the requested tenant.

    In this implementation the ledger is the in-memory FakeLedger (or a real
    TrustLedger). The route projects from domain types to API schemas.
    """
    ledger = request.app.state.kernel.engine._ledger  # type: ignore[attr-defined]
    entries = getattr(ledger, "sealed", [])

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
        if str(e.tenant) == tenant
    ]

    return LedgerTrailResponse(tenant=tenant, entries=projected, count=len(projected))


@router.get("/health", summary="Ledger health check")
async def ledger_health(request: Request) -> dict:
    return {"ok": True}
