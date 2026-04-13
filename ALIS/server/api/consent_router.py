from __future__ import annotations
from server.core.rbac import Permission, require_permission  # noqa: E402

"""E21 — DPDP Consent Management API Router

MODULE: Consent Management (E21)
LAYER: Layer 5 (Roles, Authority & Quorum)
PREFIX: /api/v1/consent

Endpoints:
  GET  /api/v1/consent/               — list my consent records
  POST /api/v1/consent/give           — give consent for one or more purposes
  POST /api/v1/consent/withdraw       — withdraw consent for one or more purposes
  POST /api/v1/consent/erasure        — request right-to-erasure
  GET  /api/v1/consent/erasure        — get erasure request status
  POST /api/v1/consent/erasure/{id}/reject — ADMIN: reject an erasure request

All endpoints require a valid Bearer token (session validated via SessionManager).
The user's identity is read from the validated session (not from query params).
The tenant (org_id) is read from request.state.tenant_id set by TenantMiddleware.
"""


import logging  # noqa: E402

from fastapi import APIRouter, Header, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from server.core.rbac import Role  # noqa: E402
from server.core.security import SessionManager  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/consent", tags=["consent"])


# =============================================================================
# REQUEST MODELS
# =============================================================================


class GiveConsentRequest(BaseModel):
    purposes: list[str] = Field(
        ..., min_length=1, description="Consent purposes to grant"
    )


class WithdrawConsentRequest(BaseModel):
    purposes: list[str] = Field(
        ..., min_length=1, description="Consent purposes to withdraw"
    )


class ErasureRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class RejectErasureRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# =============================================================================
# HELPERS
# =============================================================================


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _require_auth(authorization: str | None):
    """
    Validate the Bearer token and return (session, None) or (None, error_json).
    """
    token = _extract_token(authorization)
    if not token:
        return None, JSONResponse(
            status_code=401,
            content={
                "error": "Missing or malformed Authorization header",
                "code": "ERR_AUTH_REQUIRED",
            },
        )
    session = SessionManager.validate_token(token)
    if not session:
        return None, JSONResponse(
            status_code=401,
            content={
                "error": "Token is invalid, expired, or revoked",
                "code": "ERR_AUTH_REQUIRED",
            },
        )
    return session, None


def _org(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default")


# =============================================================================
# GET /api/v1/consent/
# =============================================================================


@router.get("/")
@require_permission(Permission.COMPLIANCE_READ)
async def list_consents(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Return all consent records for the authenticated user."""
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.consent.consent_service import ConsentService

    records = ConsentService.get_consents(org_id, session.user_id)

    return JSONResponse(
        status_code=200, content={"consents": records, "total": len(records)}
    )


# =============================================================================
# POST /api/v1/consent/give
# =============================================================================


@router.post("/give")
async def give_consent(
    request: Request,
    body: GiveConsentRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Give consent for one or more purposes.

    Body: {"purposes": ["ADMISSIONS", "FINANCE"]}
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    from server.consent.consent_service import ConsentService

    try:
        records = ConsentService.give_consent(
            org_id=org_id,
            user_id=session.user_id,
            purposes=body.purposes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422, content={"error": str(exc), "code": "ERR_INVALID_PURPOSE"}
        )

    return JSONResponse(
        status_code=200,
        content={"message": "Consent recorded.", "consents": records},
    )


# =============================================================================
# POST /api/v1/consent/withdraw
# =============================================================================


@router.post("/withdraw")
async def withdraw_consent(
    request: Request,
    body: WithdrawConsentRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Withdraw consent for one or more purposes.

    Body: {"purposes": ["FINANCE"]}
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.consent.consent_service import ConsentService

    try:
        records = ConsentService.withdraw_consent(
            org_id=org_id,
            user_id=session.user_id,
            purposes=body.purposes,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422, content={"error": str(exc), "code": "ERR_INVALID_PURPOSE"}
        )

    return JSONResponse(
        status_code=200,
        content={"message": "Consent withdrawn.", "consents": records},
    )


# =============================================================================
# POST /api/v1/consent/erasure
# =============================================================================


@router.post("/erasure")
async def request_erasure(
    request: Request,
    body: ErasureRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Submit a right-to-erasure request (DPDP Act 2023, Section 12).

    Creates an erasure request covering all modules.  Each module must
    acknowledge completion via mark_module_erased().  The request is
    auto-completed when all modules have confirmed erasure, or within
    30 days (whichever comes first).
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.consent.consent_service import ConsentService

    erasure = ConsentService.request_erasure(
        org_id=org_id,
        user_id=session.user_id,
        requested_by=session.user_id,
        reason=body.reason,
    )

    return JSONResponse(
        status_code=201,
        content={"message": "Erasure request submitted.", "erasure": erasure},
    )


# =============================================================================
# GET /api/v1/consent/erasure
# =============================================================================


@router.get("/erasure")
async def get_erasure_status(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Return the most recent erasure request status for the authenticated user."""
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.consent.consent_service import ConsentService

    erasure = ConsentService.get_erasure_status(org_id, session.user_id)

    if erasure is None:
        return JSONResponse(
            status_code=404,
            content={"error": "No erasure request found", "code": "ERR_NOT_FOUND"},
        )

    return JSONResponse(status_code=200, content={"erasure": erasure})


# =============================================================================
# POST /api/v1/consent/erasure/{erasure_id}/reject  (ADMIN only)
# =============================================================================


@router.post("/erasure/{erasure_id}/reject")
async def reject_erasure(
    erasure_id: str,
    request: Request,
    body: RejectErasureRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Reject an erasure request.  ADMIN or SUPER_ADMIN role required.

    Body: {"reason": "Legal hold — active litigation"}
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    # --- RBAC: ADMIN or SUPER_ADMIN only ---
    from server.db_service import execute_query

    user_rows = execute_query(
        "SELECT role FROM users WHERE id = %s::uuid AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=org_id,
    )
    if not user_rows:
        return JSONResponse(
            status_code=403,
            content={"error": "User not found", "code": "ERR_LAYER5_ACCESS"},
        )
    caller_role = user_rows[0].get("role", "")
    if caller_role not in (Role.ADMIN.value, Role.SUPER_ADMIN.value):
        return JSONResponse(
            status_code=403,
            content={
                "error": "ADMIN or SUPER_ADMIN role required to reject erasure requests",
                "code": "ERR_LAYER5_ACCESS",
            },
        )

    from server.consent.consent_service import ConsentService

    try:
        erasure = ConsentService.reject_erasure(
            erasure_id=erasure_id,
            reason=body.reason,
            org_id=org_id,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": str(exc), "code": "ERR_NOT_FOUND"},
        )

    return JSONResponse(
        status_code=200,
        content={"message": "Erasure request rejected.", "erasure": erasure},
    )


# =============================================================================
# GET /api/v1/consent/admin/stats  (ADMIN/SUPER_ADMIN — DPO dashboard)
# =============================================================================


@router.get("/admin/stats")
@require_permission(Permission.COMPLIANCE_READ)
async def consent_admin_stats(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Aggregate consent rates by purpose for the DPO dashboard.
    Returns: { stats: [{ purpose, given, revoked, total, rate }] }
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.db_service import execute_query

    user_rows = execute_query(
        "SELECT role FROM users WHERE id = %s::uuid AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=org_id,
    )
    if not user_rows or user_rows[0].get("role") not in (
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
    ):
        return JSONResponse(
            status_code=403,
            content={"error": "Admin access required", "code": "ERR_LAYER5_ACCESS"},
        )

    rows = execute_query(
        """
        SELECT purpose,
               COUNT(*) FILTER (WHERE status = 'GIVEN')     AS given,
               COUNT(*) FILTER (WHERE status = 'WITHDRAWN') AS revoked,
               COUNT(*)                                      AS total
        FROM consent_records
        WHERE org_id = %s
        GROUP BY purpose
        ORDER BY purpose
        """,
        (org_id,),
        tenant_id=org_id,
    )

    stats = []
    for r in rows:
        total = (r["given"] or 0) + (r["revoked"] or 0)
        rate = round((r["given"] / total * 100) if total > 0 else 0, 1)
        stats.append(
            {
                "purpose": r["purpose"],
                "given": r["given"] or 0,
                "revoked": r["revoked"] or 0,
                "total": total,
                "rate": rate,
            }
        )

    return JSONResponse(status_code=200, content={"stats": stats})


# =============================================================================
# GET /api/v1/consent/admin/events  (ADMIN/SUPER_ADMIN — DPO dashboard)
# =============================================================================


@router.get("/admin/events")
@require_permission(Permission.COMPLIANCE_READ)
async def consent_admin_events(
    request: Request,
    limit: int = 50,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Recent GIVEN/WITHDRAWN consent events for the DPO activity feed.
    Returns: { events: [{ purpose, action, ts, user_name, ip_address }] }
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.db_service import execute_query

    user_rows = execute_query(
        "SELECT role FROM users WHERE id = %s::uuid AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=org_id,
    )
    if not user_rows or user_rows[0].get("role") not in (
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
    ):
        return JSONResponse(
            status_code=403,
            content={"error": "Admin access required", "code": "ERR_LAYER5_ACCESS"},
        )

    rows = execute_query(
        """
        SELECT cr.purpose,
               cr.status,
               COALESCE(cr.given_at, cr.withdrawn_at) AS event_ts,
               cr.ip_address::text                    AS ip_address,
               u.name                                 AS user_name
        FROM consent_records cr
        LEFT JOIN users u ON u.id = cr.user_id
        WHERE cr.org_id = %s
        ORDER BY event_ts DESC
        LIMIT %s
        """,
        (org_id, min(limit, 200)),
        tenant_id=org_id,
    )

    events = [
        {
            "purpose": r["purpose"],
            "action": r["status"],
            "ts": r["event_ts"].isoformat() if r["event_ts"] else None,
            "user_name": r["user_name"] or "Unknown",
            "ip_address": r["ip_address"] or "",
        }
        for r in rows
    ]

    return JSONResponse(
        status_code=200, content={"events": events, "total": len(events)}
    )


# =============================================================================
# GET /api/v1/consent/admin/dsr  (ADMIN/SUPER_ADMIN — DPO dashboard)
# =============================================================================


@router.get("/admin/dsr")
@require_permission(Permission.COMPLIANCE_READ)
async def consent_admin_dsr(
    request: Request,
    status: str | None = None,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """
    Erasure / DSR request queue for the DPO.
    ?status=PENDING|IN_PROGRESS|COMPLETED|REJECTED  (omit for all pending+in-progress)
    Returns: { requests: [...], total: int }
    """
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from datetime import datetime, timezone

    from server.db_service import execute_query

    user_rows = execute_query(
        "SELECT role FROM users WHERE id = %s::uuid AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=org_id,
    )
    if not user_rows or user_rows[0].get("role") not in (
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
    ):
        return JSONResponse(
            status_code=403,
            content={"error": "Admin access required", "code": "ERR_LAYER5_ACCESS"},
        )

    sql = """
        SELECT er.id, er.status, er.reason, er.due_by,
               er.created_at   AS requested_at,
               er.completed_at, er.rejected_at, er.rejection_reason,
               u.name          AS user_name
        FROM erasure_requests er
        LEFT JOIN users u ON u.id = er.user_id
        WHERE er.org_id = %s
    """
    params: list = [org_id]
    if status:
        sql += " AND er.status = %s"
        params.append(status.upper())
    else:
        sql += " AND er.status IN ('PENDING', 'IN_PROGRESS')"
    sql += " ORDER BY er.created_at DESC LIMIT 100"

    rows = execute_query(sql, params, tenant_id=org_id)

    def _sla_hours(due_by) -> int | None:
        if not due_by:
            return None
        now = datetime.now(timezone.utc)
        due = due_by if due_by.tzinfo else due_by.replace(tzinfo=timezone.utc)
        return max(0, int((due - now).total_seconds() / 3600))

    out = [
        {
            "id": str(r["id"]),
            "type": "ERASURE",
            "status": r["status"],
            "reason": r["reason"] or "",
            "user_name": r["user_name"] or "Unknown",
            "requested_at": r["requested_at"].isoformat()
            if r["requested_at"]
            else None,
            "due_by": r["due_by"].isoformat() if r["due_by"] else None,
            "sla_hours_remaining": _sla_hours(r["due_by"]),
            "completed_at": r["completed_at"].isoformat()
            if r["completed_at"]
            else None,
            "rejected_at": r["rejected_at"].isoformat() if r["rejected_at"] else None,
            "rejection_reason": r["rejection_reason"] or "",
        }
        for r in rows
    ]

    return JSONResponse(status_code=200, content={"requests": out, "total": len(out)})
