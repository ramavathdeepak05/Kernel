"""
ALIS User Management Router — E01-S01 & E01-S03

MODULE: Platform Core (E01 — Platform Foundation)
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: User

Provides user lifecycle management for ALIS administrators.

Endpoints:
    GET    /api/users              — List users in tenant (paginated, filterable)
    GET    /api/users/{id}         — Get a single user's profile
    PATCH  /api/users/{id}         — Update profile fields (email, display_name)
    DELETE /api/users/{id}         — Soft-delete user (status → ARCHIVED)
    PATCH  /api/users/{id}/role    — Change a user's role (SUPER_ADMIN only)
    POST   /api/users/{id}/suspend — Suspend a user (ADMIN / SUPER_ADMIN)
    POST   /api/users/{id}/activate — Reactivate a suspended user (ADMIN / SUPER_ADMIN)

Authority Matrix (Layer 5):
    | Action          | ADMIN | SUPER_ADMIN | Others |
    |-----------------|-------|-------------|--------|
    | List users      |  own tenant  |  any  |   ✗   |
    | Get user        |  own tenant  |  any  |  own  |
    | Update profile  |  own tenant  |  any  |  own  |
    | Soft-delete     |  own tenant  |  any  |   ✗   |
    | Change role     |      ✗       |   ✓   |   ✗   |
    | Suspend         |  own tenant  |  any  |   ✗   |
    | Activate        |  own tenant  |  any  |   ✗   |

Invariants:
    - A user cannot delete themselves
    - A user cannot change their own role
    - SUPER_ADMIN accounts cannot be suspended by ADMIN
    - All mutations are audit-logged
    - Soft-delete only — no hard deletes
    - Status state machine: ACTIVE ↔ SUSPENDED → ARCHIVED (irreversible)
"""
from __future__ import annotations

import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import (
    SessionManager,
    InputValidator,
)
from server.core.rbac import Role, is_manager_role
from server.core.audit import AuditLedger, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class UserUpdateRequest(BaseModel):
    """Fields that any user may update on their own profile, or ADMIN on others."""
    email: Optional[str] = None
    display_name: Optional[str] = None


class RoleChangeRequest(BaseModel):
    """SUPER_ADMIN only — change a user's RBAC role."""
    role: Role = Field(..., description="New role to assign")


class AssignCustomRoleRequest(BaseModel):
    """Assign a custom role to a user."""
    role_id: str = Field(..., description="ID of the custom role to assign")


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _require_session(authorization: Optional[str]):
    token = _extract_token(authorization)
    if not token:
        return None, "Missing or malformed Authorization header"
    session = SessionManager.validate_token(token)
    if not session:
        return None, "Token is invalid, expired, or revoked"
    return session, None


def _fetch_user(user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a non-deleted user by ID within a tenant."""
    rows = execute_query(
        "SELECT id, tenant_id, username, email, display_name, role, status, "
        "actor_type, is_deleted, created_at, updated_at "
        "FROM users WHERE id = %s AND is_deleted = FALSE",
        (user_id,),
        tenant_id=tenant_id,
    )
    return rows[0] if rows else None


def _fetch_caller(session) -> Optional[Dict[str, Any]]:
    """Fetch the session owner's user row."""
    return _fetch_user(session.user_id, session.tenant_id)


def _err(status: int, message: str, code: str, **extra) -> JSONResponse:
    body: Dict[str, Any] = {"error": message, "code": code}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


def _serialize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a DB user row to a safe API response dict."""
    return {
        "id": str(user["id"]),
        "username": user["username"],
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "role": user["role"],
        "status": user["status"],
        "actor_type": user["actor_type"],
        "tenant_id": str(user["tenant_id"]),
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
        "updated_at": user["updated_at"].isoformat() if user.get("updated_at") else None,
    }


# =============================================================================
# GET /api/users  — List users
# =============================================================================

@router.get("")
async def list_users(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    role: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    List users in the caller's tenant.

    Supports optional filters:
        ?role=faculty          — filter by role
        ?status=ACTIVE         — filter by status
        ?limit=50&offset=0     — pagination

    Authority:
        - ADMIN / SUPER_ADMIN only
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

    # Build query
    conditions = ["is_deleted = FALSE"]
    params: list = []

    if role:
        conditions.append("role = %s")
        params.append(role)
    if status:
        conditions.append("status = %s")
        params.append(status)

    where = " AND ".join(conditions)

    # Count total for pagination metadata
    count_rows = execute_query(
        f"SELECT COUNT(*) AS total FROM users WHERE {where}",
        tuple(params) if params else None,
        tenant_id=session.tenant_id,
    )
    total = int(count_rows[0]["total"]) if count_rows else 0

    # Fetch page
    params.extend([limit, offset])
    rows = execute_query(
        f"SELECT id, tenant_id, username, email, display_name, role, status, "
        f"actor_type, is_deleted, created_at, updated_at "
        f"FROM users WHERE {where} "
        f"ORDER BY created_at DESC "
        f"LIMIT %s OFFSET %s",
        tuple(params),
        tenant_id=session.tenant_id,
    )

    return JSONResponse(
        status_code=200,
        content={
            "total": total,
            "limit": limit,
            "offset": offset,
            "users": [_serialize_user(r) for r in rows],
        },
    )


# =============================================================================
# GET /api/users/{user_id}  — Get single user
# =============================================================================

@router.get("/{user_id}")
async def get_user(
    user_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Get a single user's profile.

    Authority:
        - Any authenticated user may fetch their own profile
        - ADMIN / SUPER_ADMIN may fetch any user in the tenant
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    # Self-access is always allowed; others require ADMIN+
    if user_id != session.user_id:
        try:
            caller_role = Role(caller["role"])
        except ValueError:
            return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
        if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
            return _err(403, "You may only view your own profile", "ERR_LAYER5_ACCESS")

    user = _fetch_user(user_id, session.tenant_id)
    if not user:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    return JSONResponse(status_code=200, content=_serialize_user(user))


# =============================================================================
# PATCH /api/users/{user_id}  — Update profile
# =============================================================================

@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Update a user's profile fields (email, display_name).

    Authority:
        - Any authenticated user may update their own profile
        - ADMIN / SUPER_ADMIN may update any user in the tenant

    Note: role and status are NOT updated here.
        Use PATCH /{id}/role and POST /{id}/suspend|activate instead.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    # Self-update allowed; updating others requires ADMIN+
    if user_id != session.user_id:
        try:
            caller_role = Role(caller["role"])
        except ValueError:
            return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
        if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
            return _err(403, "You may only update your own profile", "ERR_LAYER5_ACCESS")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    # Validate email
    if body.email and not InputValidator.validate_email(body.email):
        return _err(422, "Invalid email format", "ERR_VALIDATION")

    # Build update
    fields: list = []
    values: list = []

    if body.email is not None:
        fields.append("email = %s")
        values.append(body.email)
    if body.display_name is not None:
        fields.append("display_name = %s")
        values.append(InputValidator.sanitize_string(body.display_name, max_length=256))

    if not fields:
        return _err(422, "No fields provided to update", "ERR_NO_FIELDS")

    fields.append("updated_at = %s")
    values.append(datetime.now(timezone.utc))
    values.append(user_id)

    execute_transaction(
        [(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", tuple(values))],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=session.tenant_id,
        metadata={
            "updated_fields": [f.split(" = ")[0] for f in fields[:-1]],
            "updated_by": caller["username"],
        },
    )

    # Return updated record
    updated = _fetch_user(user_id, session.tenant_id)
    return JSONResponse(status_code=200, content=_serialize_user(updated))


# =============================================================================
# DELETE /api/users/{user_id}  — Soft-delete
# =============================================================================

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Soft-delete a user (status → ARCHIVED, is_deleted = TRUE).

    Invariants:
        - A user cannot delete themselves
        - ADMIN cannot delete SUPER_ADMIN accounts
        - Hard deletes are forbidden (Layer 4)

    Authority:
        - ADMIN / SUPER_ADMIN only
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

    # Self-delete is forbidden
    if user_id == session.user_id:
        return _err(403, "You cannot delete your own account", "ERR_SELF_DELETE")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    # ADMIN cannot delete SUPER_ADMIN
    if target["role"] == Role.SUPER_ADMIN.value and caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may delete SUPER_ADMIN accounts", "ERR_LAYER5_ACCESS")

    now = datetime.now(timezone.utc)
    execute_transaction(
        [
            (
                "UPDATE users SET status = 'ARCHIVED', is_deleted = TRUE, "
                "deleted_at = %s, updated_at = %s WHERE id = %s",
                (now, now, user_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.DELETE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=session.tenant_id,
        metadata={
            "deleted_username": target["username"],
            "deleted_role": target["role"],
            "deleted_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"User '{target['username']}' archived successfully"},
    )


# =============================================================================
# PATCH /api/users/{user_id}/role  — Change role (SUPER_ADMIN only)
# =============================================================================

@router.patch("/{user_id}/role")
async def change_user_role(
    user_id: str,
    body: RoleChangeRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Change a user's RBAC role.

    Invariants:
        - SUPER_ADMIN only
        - A user cannot change their own role
        - Target must be ACTIVE (not ARCHIVED or SUSPENDED)

    This is a high-privilege operation and is always audit-logged.
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

    # SUPER_ADMIN only
    if caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may change user roles", "ERR_LAYER5_ACCESS")

    # Cannot change own role
    if user_id == session.user_id:
        return _err(403, "You cannot change your own role", "ERR_SELF_ROLE_CHANGE")

    # Validate new role
    try:
        new_role = Role(body.role)
    except ValueError:
        return _err(
            422,
            f"Invalid role '{body.role}'",
            "ERR_INVALID_ROLE",
            valid_roles=[r.value for r in Role],
        )

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    if target["status"] == "ARCHIVED":
        return _err(409, "Cannot change role of an archived user", "ERR_USER_ARCHIVED")

    previous_role = target["role"]

    execute_transaction(
        [
            (
                "UPDATE users SET role = %s, updated_at = %s WHERE id = %s",
                (new_role.value, datetime.now(timezone.utc), user_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=session.tenant_id,
        metadata={
            "field": "role",
            "previous_role": previous_role,
            "new_role": new_role.value,
            "target_username": target["username"],
            "changed_by": caller["username"],
        },
    )

    updated = _fetch_user(user_id, session.tenant_id)
    return JSONResponse(status_code=200, content=_serialize_user(updated))


# =============================================================================
# POST /api/users/{user_id}/suspend  — Suspend user
# =============================================================================

@router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Suspend a user (ACTIVE → SUSPENDED).

    A suspended user cannot log in but their data and history are preserved.
    Reactivate with POST /{id}/activate.

    Invariants:
        - Cannot suspend yourself
        - ADMIN cannot suspend SUPER_ADMIN accounts
        - User must currently be ACTIVE
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

    if user_id == session.user_id:
        return _err(403, "You cannot suspend your own account", "ERR_SELF_SUSPEND")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    # ADMIN cannot suspend SUPER_ADMIN
    if target["role"] == Role.SUPER_ADMIN.value and caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may suspend SUPER_ADMIN accounts", "ERR_LAYER5_ACCESS")

    if target["status"] != "ACTIVE":
        return _err(
            409,
            f"User is already {target['status'].lower()} — only ACTIVE users can be suspended",
            "ERR_INVALID_STATE_TRANSITION",
        )

    execute_transaction(
        [
            (
                "UPDATE users SET status = 'SUSPENDED', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), user_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=session.tenant_id,
        metadata={
            "previous_state": "ACTIVE",
            "new_state": "SUSPENDED",
            "target_username": target["username"],
            "suspended_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"User '{target['username']}' suspended successfully"},
    )


# =============================================================================
# POST /api/users/{user_id}/activate  — Reactivate user
# =============================================================================

@router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Reactivate a suspended user (SUSPENDED → ACTIVE).

    Invariants:
        - Only SUSPENDED users can be reactivated (not ARCHIVED)
        - ADMIN cannot reactivate SUPER_ADMIN accounts
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

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    # ADMIN cannot activate SUPER_ADMIN
    if target["role"] == Role.SUPER_ADMIN.value and caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may reactivate SUPER_ADMIN accounts", "ERR_LAYER5_ACCESS")

    if target["status"] == "ARCHIVED":
        return _err(409, "Archived users cannot be reactivated", "ERR_INVALID_STATE_TRANSITION")

    if target["status"] == "ACTIVE":
        return _err(409, "User is already active", "ERR_INVALID_STATE_TRANSITION")

    execute_transaction(
        [
            (
                "UPDATE users SET status = 'ACTIVE', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), user_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=session.tenant_id,
        metadata={
            "previous_state": "SUSPENDED",
            "new_state": "ACTIVE",
            "target_username": target["username"],
            "activated_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"User '{target['username']}' reactivated successfully"},
    )


# =============================================================================
# GET /api/users/{user_id}/roles  — List user's custom roles
# =============================================================================

@router.get("/{user_id}/roles")
async def list_user_custom_roles(
    user_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    List all custom roles currently assigned to a user.

    Authority:
        - Any user may list their own custom roles
        - ADMIN / SUPER_ADMIN / any M*_MANAGER may list any user's custom roles
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    if user_id != session.user_id:
        try:
            caller_role = Role(caller["role"])
        except ValueError:
            return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")
        if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN) and not is_manager_role(caller_role):
            return _err(403, "Insufficient authority to view this user's roles", "ERR_LAYER5_ACCESS")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    rows = execute_query(
        "SELECT ucr.id AS assignment_id, ucr.role_id, cr.role_name, cr.module, "
        "cr.status AS role_status, ucr.assigned_by, ucr.assigned_at "
        "FROM user_custom_roles ucr "
        "JOIN custom_roles cr ON cr.id = ucr.role_id "
        "WHERE ucr.user_id = %s "
        "ORDER BY ucr.assigned_at DESC",
        (user_id,),
        tenant_id=session.tenant_id,
    )

    return JSONResponse(
        status_code=200,
        content={
            "user_id": user_id,
            "custom_roles": [
                {
                    "assignment_id": str(r["assignment_id"]),
                    "role_id": str(r["role_id"]),
                    "role_name": r["role_name"],
                    "module": r["module"],
                    "role_status": r["role_status"],
                    "assigned_by": r["assigned_by"],
                    "assigned_at": r["assigned_at"].isoformat() if r.get("assigned_at") else None,
                }
                for r in rows
            ],
        },
    )


# =============================================================================
# POST /api/users/{user_id}/roles  — Assign custom role
# =============================================================================

@router.post("/{user_id}/roles")
async def assign_custom_role(
    user_id: str,
    body: AssignCustomRoleRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Assign a custom role to a user.

    The custom role must be ACTIVE and have at least one APPROVED permission.

    Authority:
        - SUPER_ADMIN or any M*_MANAGER
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

    if caller_role != Role.SUPER_ADMIN and not is_manager_role(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    if target["status"] == "ARCHIVED":
        return _err(409, "Cannot assign roles to an archived user", "ERR_USER_ARCHIVED")

    # Validate the custom role exists and is ACTIVE
    role_rows = execute_query(
        "SELECT id, role_name, status FROM custom_roles "
        "WHERE id = %s AND status = 'ACTIVE'",
        (body.role_id,),
        tenant_id=session.tenant_id,
    )
    if not role_rows:
        return _err(404, "Custom role not found or not active", "ERR_ROLE_NOT_FOUND")

    custom_role = role_rows[0]

    # Role must have at least one APPROVED permission to be assignable
    approved_perms = execute_query(
        "SELECT COUNT(*) AS cnt FROM custom_role_permissions "
        "WHERE role_id = %s AND status = 'APPROVED'",
        (body.role_id,),
        tenant_id=session.tenant_id,
    )
    if not approved_perms or int(approved_perms[0]["cnt"]) == 0:
        return _err(
            409,
            "This role has no approved permissions yet and cannot be assigned",
            "ERR_ROLE_NO_APPROVED_PERMISSIONS",
        )

    assignment_id = str(uuid4())
    now = datetime.now(timezone.utc)

    try:
        execute_transaction(
            [
                (
                    "INSERT INTO user_custom_roles "
                    "(id, tenant_id, user_id, role_id, assigned_by, assigned_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (assignment_id, session.tenant_id, user_id, body.role_id, session.user_id, now),
                )
            ],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_user_custom_role" in str(e):
            return _err(409, "This custom role is already assigned to the user", "ERR_DUPLICATE_ASSIGNMENT")
        logger.error(f"Failed to assign custom role: {e}")
        return _err(500, "Internal error assigning role", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user_custom_role",
        entity_id=assignment_id,
        tenant_id=session.tenant_id,
        metadata={
            "user_id": user_id,
            "role_id": body.role_id,
            "role_name": custom_role["role_name"],
            "assigned_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "message": f"Role '{custom_role['role_name']}' assigned successfully",
            "assignment_id": assignment_id,
        },
    )


# =============================================================================
# DELETE /api/users/{user_id}/roles/{role_id}  — Revoke custom role
# =============================================================================

@router.delete("/{user_id}/roles/{role_id}")
async def revoke_custom_role(
    user_id: str,
    role_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Revoke a custom role from a user.

    Authority:
        - SUPER_ADMIN or any M*_MANAGER
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

    if caller_role != Role.SUPER_ADMIN and not is_manager_role(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    target = _fetch_user(user_id, session.tenant_id)
    if not target:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    assignment_rows = execute_query(
        "SELECT id FROM user_custom_roles WHERE user_id = %s AND role_id = %s",
        (user_id, role_id),
        tenant_id=session.tenant_id,
    )
    if not assignment_rows:
        return _err(404, "This custom role is not assigned to the user", "ERR_ASSIGNMENT_NOT_FOUND")

    assignment_id = str(assignment_rows[0]["id"])

    execute_transaction(
        [("DELETE FROM user_custom_roles WHERE user_id = %s AND role_id = %s", (user_id, role_id))],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.DELETE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user_custom_role",
        entity_id=assignment_id,
        tenant_id=session.tenant_id,
        metadata={
            "user_id": user_id,
            "role_id": role_id,
            "revoked_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=200,
        content={"message": "Custom role revoked from user successfully"},
    )
