"""
ALIS Audit Ledger API Router — E00-S02

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Orchestration (FastAPI)
ENTITY: AuditLedger

Exposes the Immutable Audit Ledger's verification and export
capabilities as REST endpoints.

Endpoints:
    GET /api/v1/audit/verify   — Hash chain verification
    GET /api/v1/audit/export   — Admin ledger export (JSON / CSV)

Must Align With:
    - E00-S02 Acceptance Criteria: Hash chain verification endpoint,
      Admin export capability
    - Layer 5: Only ADMIN / SUPER_ADMIN may access these endpoints
      (enforced via RBAC+ Permission.AUDIT_LOG_READ)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from server.core.audit import AuditLedger
from server.core.rbac import require_permission, Permission
from server.core.security import get_current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ============================================================================
# GET /api/v1/audit/verify  —  Hash Chain Verification
# ============================================================================

@router.get("/verify")
@require_permission(Permission.AUDIT_LOG_READ)
async def verify_audit_chain(request: Request) -> JSONResponse:
    """
    Walk the entire hash chain for the current tenant and verify
    every link.

    Returns:
        200: { "valid": bool, "total_entries": int,
               "first_invalid_id": int | null, "message": str }

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()
    result = AuditLedger.verify_chain_integrity(tenant_id)

    status_code = 200 if result["valid"] else 409  # 409 Conflict on tamper
    return JSONResponse(content=result, status_code=status_code)


# ============================================================================
# GET /api/v1/audit/export  —  Admin Ledger Export
# ============================================================================

@router.get("/export")
@require_permission(Permission.AUDIT_LOG_READ)
async def export_audit_ledger(
    request: Request,
    fmt: str = Query(
        default="json",
        description="Export format: 'json' or 'csv'.",
        pattern="^(json|csv)$",
    ),
    start_time: Optional[str] = Query(
        default=None,
        description="ISO-8601 lower-bound filter (e.g. 2025-01-01T00:00:00Z).",
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="ISO-8601 upper-bound filter.",
    ),
) -> Response:
    """
    Export the audit ledger for the current tenant.

    Returns:
        200: Full ledger export as JSON or CSV.

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()

    # Parse optional datetime filters
    parsed_start = _parse_iso(start_time) if start_time else None
    parsed_end = _parse_iso(end_time) if end_time else None

    export_str = AuditLedger.export_ledger(
        tenant_id=tenant_id,
        fmt=fmt,
        start_time=parsed_start,
        end_time=parsed_end,
    )

    if fmt == "csv":
        return Response(
            content=export_str,
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=audit_ledger_{tenant_id}.csv"
                )
            },
        )

    # Default: JSON
    return Response(
        content=export_str,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=audit_ledger_{tenant_id}.json"
            )
        },
    )


# ============================================================================
# HELPERS
# ============================================================================

def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime."""
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
