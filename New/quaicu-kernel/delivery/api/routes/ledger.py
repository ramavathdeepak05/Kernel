"""Ledger routes — trail, regulator export, and verify.

GET  /v1/ledger/{tenant}/trail   →  200 LedgerTrailResponse
GET  /v1/ledger/{tenant}/export  →  200 LedgerProofBundle (self-verifying regulator export, WS-F)
POST /v1/ledger/export/verify    →  200 { ok, errors } (stateless offline-equivalent verifier)
GET  /v1/ledger/health           →  200 { "ok": true }
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


def _parse_window(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"error": f"{field} is not an ISO-8601 datetime", "code": "BAD_WINDOW"},
        )


@router.get(
    "/{tenant}/export",
    summary="Export a self-verifying ledger-proof bundle for a regulator (WS-F)",
)
async def ledger_export(tenant: str, request: Request) -> dict:
    """Build a regulator proof bundle of the tenant's sealed actions in an optional time window.

    Query params (all optional): ``from`` / ``to`` (ISO-8601 datetimes), ``regulations`` and
    ``policy_versions`` (comma-separated). Same tenant-isolation + scope guard as the audit trail —
    the bundle is tenant-private. The returned JSON is independently verifiable offline via
    ``POST /v1/ledger/export/verify`` or `core.regmap.export.verify_ledger_proof_bundle`.
    """
    _bearer_token(request)
    enforce_scope(request, LEDGER_READ)

    kernel = get_kernel(request)
    if tenant != str(get_request_tenant(request)):
        raise HTTPException(
            status_code=403,
            detail={"error": "Cannot export another tenant's ledger", "code": "TENANT_ISOLATION"},
        )

    qp = request.query_params
    window_start = _parse_window(qp.get("from"), "from")
    window_end = _parse_window(qp.get("to"), "to")
    regulations = [s for s in (qp.get("regulations", "").split(",")) if s]
    policy_versions = [s for s in (qp.get("policy_versions", "").split(",")) if s]

    bundle = kernel.export_ledger_proof(
        TenantId(tenant),
        window_start=window_start,
        window_end=window_end,
        regulation_refs=regulations or None,
        policy_versions=policy_versions or None,
    )
    return bundle.to_dict()


class VerifyResult(BaseModel):
    ok: bool
    errors: list[str]


@router.post(
    "/export/verify",
    response_model=VerifyResult,
    summary="Verify a ledger-proof bundle (stateless; the same check a regulator runs offline)",
)
async def ledger_export_verify(bundle: dict, request: Request) -> VerifyResult:
    """Re-run the independent bundle verifier on a posted export. No kernel state is read — this is a
    convenience mirror of the offline verifier so a regulator can confirm a bundle via the API too."""
    from core.regmap.export import verify_ledger_proof_bundle

    ok, errors = verify_ledger_proof_bundle(bundle)
    return VerifyResult(ok=ok, errors=errors)


@router.get("/health", summary="Ledger health check")
async def ledger_health(request: Request) -> dict:
    return {"ok": True}
