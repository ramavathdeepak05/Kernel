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

import logging
from typing import List, Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import SessionManager
from server.core.rbac import Role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/consent", tags=["consent"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class GiveConsentRequest(BaseModel):
    purposes: List[str] = Field(..., min_length=1, description="Consent purposes to grant")


class WithdrawConsentRequest(BaseModel):
    purposes: List[str] = Field(..., min_length=1, description="Consent purposes to withdraw")


class ErasureRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class RejectErasureRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# =============================================================================
# HELPERS
# =============================================================================

def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _require_auth(authorization: Optional[str]):
    """
    Validate the Bearer token and return (session, None) or (None, error_json).
    """
    token = _extract_token(authorization)
    if not token:
        return None, JSONResponse(
            status_code=401,
            content={"error": "Missing or malformed Authorization header", "code": "ERR_AUTH_REQUIRED"},
        )
    session = SessionManager.validate_token(token)
    if not session:
        return None, JSONResponse(
            status_code=401,
            content={"error": "Token is invalid, expired, or revoked", "code": "ERR_AUTH_REQUIRED"},
        )
    return session, None


def _org(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default")


# =============================================================================
# GET /api/v1/consent/
# =============================================================================

@router.get("/")
async def list_consents(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Return all consent records for the authenticated user."""
    session, err = _require_auth(authorization)
    if err:
        return err

    org_id = _org(request)

    from server.consent.consent_service import ConsentService
    records = ConsentService.get_consents(org_id, session.user_id)

    return JSONResponse(status_code=200, content={"consents": records, "total": len(records)})


# =============================================================================
# POST /api/v1/consent/give
# =============================================================================

@router.post("/give")
async def give_consent(
    request: Request,
    body: GiveConsentRequest,
    authorization: Optional[str] = Header(default=None),
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
        return JSONResponse(status_code=422, content={"error": str(exc), "code": "ERR_INVALID_PURPOSE"})

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
    authorization: Optional[str] = Header(default=None),
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
        return JSONResponse(status_code=422, content={"error": str(exc), "code": "ERR_INVALID_PURPOSE"})

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
    authorization: Optional[str] = Header(default=None),
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
    authorization: Optional[str] = Header(default=None),
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
    authorization: Optional[str] = Header(default=None),
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
