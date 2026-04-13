from __future__ import annotations
from server.core.rbac import require_permission, Permission  # noqa: E402

"""
ALIS Policy Governance API Router — E00-S09

Exposes the Policy Governance Service via RESTful endpoints.

Endpoints:
    POST /policy/draft     — Create a new policy draft
    POST /policy/submit    — Submit a draft for approval
    POST /policy/approve   — Approve a submitted policy
    GET  /policy/{id}      — Retrieve a policy (with optional temporal query)
    GET  /policy/          — List policies (with optional filters)
    GET  /policy/type/{t}  — Get active policy by type (Rule Engine API)
    GET  /policy/history/{t} — Version history for diff viewer

All endpoints enforce RBAC via the standard middleware pattern.
"""


import logging  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

from fastapi import APIRouter, Header, HTTPException, Query  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from server.core.policy_service import PolicyService, PolicyStatus  # noqa: E402
from server.core.rbac import Role  # noqa: E402
from server.core.security import SessionManager  # noqa: E402
from server.db_service import execute_query  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/policy", tags=["Policy Governance (E00-S09)"])


# ============================================================================
# AUTH HELPERS
# ============================================================================


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _require_session(authorization: str | None):
    token = _extract_token(authorization)
    if not token:
        return None, "Missing or malformed Authorization header"
    session = SessionManager.validate_token(token)
    if not session:
        return None, "Token is invalid, expired, or revoked"
    return session, None


def _fetch_caller(session) -> dict[str, Any] | None:
    rows = execute_query(
        "SELECT id, username, role, status FROM users "
        "WHERE id = %s AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=session.tenant_id,
    )
    return rows[0] if rows else None


def _err(status: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message, "code": code})


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================


class PolicyDraftRequest(BaseModel):
    """Request body for creating a policy draft."""

    policy_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Category (e.g., 'attendance_threshold')",
    )
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    parameters: dict[str, Any] = Field(..., description="Structured JSON parameters")
    effective_from: datetime = Field(
        ..., description="When the policy becomes applicable"
    )
    effective_to: datetime | None = Field(None, description="When the policy expires")
    module: str | None = Field(None, description="Owning module (e.g., 'm1', 'm4')")


class PolicyActionRequest(BaseModel):
    """Request body for submit / approve actions."""

    policy_id: str = Field(..., description="ID of the policy to act on")


class PolicyResponse(BaseModel):
    """Standard response for policy mutations."""

    id: str
    status: str
    policy_type: str | None = None
    version: int | None = None
    name: str | None = None
    content_hash: str | None = None


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/draft", response_model=PolicyResponse)
@require_permission(Permission.POLICY_DRAFT)
async def create_draft(
    body: PolicyDraftRequest,
    authorization: str | None = Header(default=None),
):
    """
    POST /policy/draft — Create a new policy draft. ADMIN / SUPER_ADMIN only.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")
    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")
    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        return _err(403, "ADMIN or SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    try:
        result = PolicyService.create_draft(
            policy_type=body.policy_type,
            name=body.name,
            description=body.description,
            parameters=body.parameters,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
            created_by=session.user_id,
            actor_role=caller["role"],
            tenant_id=session.tenant_id,
            module=body.module,
        )
        return PolicyResponse(**result)
    except Exception as e:
        logger.error("Failed to create policy draft: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/submit", response_model=PolicyResponse)
@require_permission(Permission.POLICY_SUBMIT)
async def submit_for_approval(
    body: PolicyActionRequest,
    authorization: str | None = Header(default=None),
):
    """
    POST /policy/submit — Submit a DRAFT policy for approval. ADMIN / SUPER_ADMIN only.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")
    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")
    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        return _err(403, "ADMIN or SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    try:
        result = PolicyService.submit_for_approval(
            policy_id=body.policy_id,
            submitted_by=session.user_id,
            actor_role=caller["role"],
            tenant_id=session.tenant_id,
        )
        return PolicyResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to submit policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve", response_model=PolicyResponse)
@require_permission(Permission.POLICY_APPROVE)
async def approve_policy(
    body: PolicyActionRequest,
    authorization: str | None = Header(default=None),
):
    """
    POST /policy/approve — Approve a SUBMITTED policy. SUPER_ADMIN only.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")
    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")
    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
    if caller_role != Role.SUPER_ADMIN:
        return _err(
            403, "SUPER_ADMIN role required to approve policies", "ERR_LAYER5_ACCESS"
        )

    try:
        result = PolicyService.approve_policy(
            policy_id=body.policy_id,
            approved_by=session.user_id,
            actor_role=caller["role"],
            tenant_id=session.tenant_id,
        )
        return PolicyResponse(**result)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to approve policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{policy_id}")
@require_permission(Permission.POLICY_READ)
async def get_policy(
    policy_id: str,
    authorization: str | None = Header(default=None),
    date: datetime | None = Query(
        None, description="Temporal query — returns the version active on this date"
    ),
):
    """
    GET /policy/{policy_id}?date= — Retrieve a policy by ID. Any authenticated user.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    try:
        result = PolicyService.get_policy(
            policy_id=policy_id,
            tenant_id=session.tenant_id,
            as_of_date=date,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/type/{policy_type}")
@require_permission(Permission.POLICY_READ)
async def get_active_by_type(
    policy_type: str,
    authorization: str | None = Header(default=None),
    date: datetime | None = Query(None, description="Point-in-time resolution"),
):
    """
    GET /policy/type/{policy_type}?date= — Active policy by type. Any authenticated user.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    try:
        result = PolicyService.get_active_policy_by_type(
            policy_type=policy_type,
            tenant_id=session.tenant_id,
            as_of_date=date,
        )
        if not result:
            raise HTTPException(
                status_code=404, detail="No active policy found for this type."
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve active policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
@require_permission(Permission.POLICY_READ)
async def list_policies(
    authorization: str | None = Header(default=None),
    policy_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    GET /policy/ — List policies. ADMIN / SUPER_ADMIN only.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")
    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")
    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        return _err(403, "ADMIN or SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    try:
        status_enum = PolicyStatus(status) if status else None
        results = PolicyService.list_policies(
            tenant_id=session.tenant_id,
            policy_type=policy_type,
            status=status_enum,
            limit=limit,
            offset=offset,
        )
        return {"policies": results, "count": len(results)}
    except Exception as e:
        logger.error("Failed to list policies: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{policy_type}")
@require_permission(Permission.POLICY_READ)
async def get_version_history(
    policy_type: str,
    authorization: str | None = Header(default=None),
):
    """
    GET /policy/history/{policy_type} — Version history. ADMIN / SUPER_ADMIN only.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")
    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")
    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        return _err(403, "ADMIN or SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    try:
        results = PolicyService.get_version_history(
            policy_type=policy_type,
            tenant_id=session.tenant_id,
        )
        return {"versions": results, "count": len(results)}
    except Exception as e:
        logger.error("Failed to retrieve version history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
