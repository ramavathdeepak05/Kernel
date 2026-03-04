"""
ALIS Dynamic Role Management Router — E01-S03

MODULE: Platform Core (E01 — Platform Foundation)
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: CustomRole, CustomRolePermission, UserCustomRole

Implements the dynamic RBAC+ role system:
  - Module Managers (M1–M8) create custom roles within their module scope
  - Permissions from other modules require the owning module manager's approval
  - Custom role permissions are additive on top of a user's base role

Endpoints:
    POST   /api/roles                            — Create custom role
    GET    /api/roles                            — List custom roles in tenant
    GET    /api/roles/approvals/pending          — View pending approvals
    POST   /api/roles/approvals/{req_id}/approve — Approve a permission request
    POST   /api/roles/approvals/{req_id}/deny    — Deny a permission request
    GET    /api/roles/{id}                       — Get role + permissions
    POST   /api/roles/{id}/permissions           — Request permissions for a role
    DELETE /api/roles/{id}/permissions/{perm}    — Remove a permission from a role
    DELETE /api/roles/{id}                       — Archive a custom role

Authority Matrix (Layer 5):
    | Action                  | SUPER_ADMIN | M*_MANAGER  | Others |
    |-------------------------|-------------|-------------|--------|
    | Create role             |      ✓      |     ✓       |   ✗    |
    | List roles              |      ✓      |     ✓       |   ✗    |
    | Get role                |      ✓      |     ✓       |   ✗    |
    | Request permissions     |      ✓      |  own role   |   ✗    |
    | View pending approvals  |      ✓      |  own module |   ✗    |
    | Approve / Deny          |      ✓      |  own module |   ✗    |
    | Archive role            |      ✓      |  own role   |   ✗    |

Permission routing:
    - Same-module permission   → APPROVED immediately (no approval needed)
    - Platform-level perm      → APPROVED immediately (no module owner)
    - Cross-module permission   → PENDING (owning module manager must approve)
    - SUPER_ADMIN requests      → always APPROVED
"""

import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import SessionManager
from server.core.rbac import (
    Role, Permission,
    ALL_MANAGER_ROLES, MANAGER_MODULE, MODULE_PERMISSIONS,
    PERMISSION_TO_MODULE, is_manager_role, get_manager_module,
)
from server.core.audit import AuditLedger, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roles", tags=["roles"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateRoleRequest(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class RequestPermissionsBody(BaseModel):
    permissions: List[str] = Field(..., description="List of permission strings to request")


class DenyRequest(BaseModel):
    review_note: Optional[str] = Field(None, max_length=500)


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


def _fetch_caller_user(session) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        "SELECT id, tenant_id, username, role, status FROM users "
        "WHERE id = %s AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=session.tenant_id,
    )
    return rows[0] if rows else None


def _err(status: int, message: str, code: str, **extra) -> JSONResponse:
    body: Dict[str, Any] = {"error": message, "code": code}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


def _is_manager_or_super(caller_role: Role) -> bool:
    return caller_role == Role.SUPER_ADMIN or is_manager_role(caller_role)


def _fetch_custom_role(role_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        "SELECT id, tenant_id, module, role_name, description, status, "
        "created_by, created_at, updated_at "
        "FROM custom_roles WHERE id = %s AND status != 'ARCHIVED'",
        (role_id,),
        tenant_id=tenant_id,
    )
    return rows[0] if rows else None


def _get_role_permissions(role_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    return list(execute_query(
        "SELECT id, permission, status, requested_by, requested_at, "
        "reviewed_by, reviewed_at, review_note "
        "FROM custom_role_permissions WHERE role_id = %s ORDER BY requested_at",
        (role_id,),
        tenant_id=tenant_id,
    ))


def _serialize_role(role: Dict[str, Any], perms: Optional[List] = None) -> Dict[str, Any]:
    out = {
        "id": str(role["id"]),
        "tenant_id": str(role["tenant_id"]),
        "module": role["module"],
        "role_name": role["role_name"],
        "description": role.get("description"),
        "status": role["status"],
        "created_by": role["created_by"],
        "created_at": role["created_at"].isoformat() if role.get("created_at") else None,
        "updated_at": role["updated_at"].isoformat() if role.get("updated_at") else None,
    }
    if perms is not None:
        out["permissions"] = [
            {
                "id": str(p["id"]),
                "permission": p["permission"],
                "status": p["status"],
                "requested_by": p["requested_by"],
                "requested_at": p["requested_at"].isoformat() if p.get("requested_at") else None,
                "reviewed_by": p.get("reviewed_by"),
                "reviewed_at": p["reviewed_at"].isoformat() if p.get("reviewed_at") else None,
                "review_note": p.get("review_note"),
            }
            for p in perms
        ]
    return out


def _serialize_pending(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(r["id"]),
        "role_id": str(r["role_id"]),
        "role_name": r["role_name"],
        "role_module": r["role_module"],
        "permission": r["permission"],
        "status": r["status"],
        "requested_by": r["requested_by"],
        "requested_at": r["requested_at"].isoformat() if r.get("requested_at") else None,
    }


# =============================================================================
# POST /api/roles — Create custom role
# =============================================================================

@router.post("")
async def create_custom_role(
    body: CreateRoleRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Create a new custom role.

    The role is scoped to the creator's module (or 'SYSTEM' for SUPER_ADMIN).
    Permissions are requested separately via POST /api/roles/{id}/permissions.

    Authority:
        - SUPER_ADMIN: creates roles with module = 'SYSTEM'
        - M*_MANAGER: creates roles scoped to their module
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    module = get_manager_module(caller_role) or "SYSTEM"
    role_id = str(uuid4())
    now = datetime.now(timezone.utc)

    try:
        execute_transaction(
            [
                (
                    "INSERT INTO custom_roles "
                    "(id, tenant_id, module, role_name, description, status, "
                    "created_by, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s)",
                    (
                        role_id,
                        session.tenant_id,
                        module,
                        body.role_name,
                        body.description,
                        session.user_id,
                        now,
                        now,
                    ),
                )
            ],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_custom_role_name_tenant" in str(e):
            return _err(
                409,
                f"A custom role named '{body.role_name}' already exists in this tenant",
                "ERR_DUPLICATE_ROLE",
            )
        logger.error(f"Failed to create custom role: {e}")
        return _err(500, "Internal error creating role", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role",
        entity_id=role_id,
        tenant_id=session.tenant_id,
        metadata={"role_name": body.role_name, "module": module},
    )

    role_row = _fetch_custom_role(role_id, session.tenant_id)
    return JSONResponse(status_code=201, content=_serialize_role(role_row, perms=[]))


# =============================================================================
# GET /api/roles — List custom roles
# =============================================================================

@router.get("")
async def list_custom_roles(
    authorization: Optional[str] = Header(default=None),
    module: Optional[str] = None,
    status: Optional[str] = None,
) -> JSONResponse:
    """
    List custom roles in the tenant (excluding archived).

    Supports optional filters:
        ?module=M1          — filter by owning module
        ?status=ACTIVE      — filter by status

    Authority:
        - SUPER_ADMIN or any M*_MANAGER
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    conditions = ["status != 'ARCHIVED'"]
    params: list = []

    if module:
        conditions.append("module = %s")
        params.append(module.upper())
    if status:
        conditions.append("status = %s")
        params.append(status.upper())

    where = " AND ".join(conditions)
    rows = execute_query(
        f"SELECT id, tenant_id, module, role_name, description, status, "
        f"created_by, created_at, updated_at "
        f"FROM custom_roles WHERE {where} ORDER BY created_at DESC",
        tuple(params) if params else None,
        tenant_id=session.tenant_id,
    )

    return JSONResponse(
        status_code=200,
        content={"total": len(rows), "roles": [_serialize_role(r) for r in rows]},
    )


# =============================================================================
# GET /api/roles/approvals/pending — Pending approval queue
# NOTE: This route must be defined BEFORE /{role_id} to avoid path collision.
# =============================================================================

@router.get("/approvals/pending")
async def get_pending_approvals(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    List cross-module permission requests pending this manager's approval.

    Authority:
        - M*_MANAGER: sees PENDING requests for permissions in their module only
        - SUPER_ADMIN: sees ALL pending requests across all modules
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    if caller_role == Role.SUPER_ADMIN:
        rows = execute_query(
            "SELECT crp.id, crp.role_id, cr.role_name, cr.module AS role_module, "
            "crp.permission, crp.status, crp.requested_by, crp.requested_at "
            "FROM custom_role_permissions crp "
            "JOIN custom_roles cr ON cr.id = crp.role_id "
            "WHERE crp.status = 'PENDING' "
            "ORDER BY crp.requested_at ASC",
            None,
            tenant_id=session.tenant_id,
        )
    else:
        manager_module = get_manager_module(caller_role)
        module_perms = [p.value for p in MODULE_PERMISSIONS.get(manager_module, [])]
        if not module_perms:
            return JSONResponse(status_code=200, content={"total": 0, "pending": []})

        placeholders = ", ".join(["%s"] * len(module_perms))
        rows = execute_query(
            f"SELECT crp.id, crp.role_id, cr.role_name, cr.module AS role_module, "
            f"crp.permission, crp.status, crp.requested_by, crp.requested_at "
            f"FROM custom_role_permissions crp "
            f"JOIN custom_roles cr ON cr.id = crp.role_id "
            f"WHERE crp.status = 'PENDING' "
            f"AND crp.permission IN ({placeholders}) "
            f"ORDER BY crp.requested_at ASC",
            tuple(module_perms),
            tenant_id=session.tenant_id,
        )

    return JSONResponse(
        status_code=200,
        content={"total": len(rows), "pending": [_serialize_pending(r) for r in rows]},
    )


# =============================================================================
# POST /api/roles/approvals/{request_id}/approve — Approve permission request
# NOTE: Defined before /{role_id} routes to avoid path collision.
# =============================================================================

@router.post("/approvals/{request_id}/approve")
async def approve_permission_request(
    request_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Approve a cross-module permission request.

    The caller must be the manager of the module that owns the requested permission,
    or a SUPER_ADMIN.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    reqs = execute_query(
        "SELECT id, role_id, permission, status "
        "FROM custom_role_permissions WHERE id = %s AND status = 'PENDING'",
        (request_id,),
        tenant_id=session.tenant_id,
    )
    if not reqs:
        return _err(404, "Pending permission request not found", "ERR_NOT_FOUND")

    req = reqs[0]

    # Verify the caller manages the module that owns this permission
    if caller_role != Role.SUPER_ADMIN:
        try:
            perm_enum = Permission(req["permission"])
        except ValueError:
            return _err(400, f"Unknown permission '{req['permission']}'", "ERR_INVALID_PERMISSION")

        owning_module = PERMISSION_TO_MODULE.get(perm_enum)
        manager_module = get_manager_module(caller_role)
        if owning_module != manager_module:
            return _err(
                403,
                f"You manage module {manager_module}, but this permission belongs to {owning_module}",
                "ERR_LAYER5_ACCESS",
            )

    now = datetime.now(timezone.utc)
    execute_transaction(
        [
            (
                "UPDATE custom_role_permissions "
                "SET status = 'APPROVED', reviewed_by = %s, reviewed_at = %s "
                "WHERE id = %s",
                (session.user_id, now, request_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role_permission",
        entity_id=request_id,
        tenant_id=session.tenant_id,
        metadata={"decision": "APPROVED", "role_id": str(req["role_id"]), "permission": req["permission"]},
    )

    return JSONResponse(
        status_code=200,
        content={"message": "Permission request approved", "request_id": request_id},
    )


# =============================================================================
# POST /api/roles/approvals/{request_id}/deny — Deny permission request
# =============================================================================

@router.post("/approvals/{request_id}/deny")
async def deny_permission_request(
    request_id: str,
    body: DenyRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Deny a cross-module permission request. Same authority rules as approve.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    reqs = execute_query(
        "SELECT id, role_id, permission, status "
        "FROM custom_role_permissions WHERE id = %s AND status = 'PENDING'",
        (request_id,),
        tenant_id=session.tenant_id,
    )
    if not reqs:
        return _err(404, "Pending permission request not found", "ERR_NOT_FOUND")

    req = reqs[0]

    if caller_role != Role.SUPER_ADMIN:
        try:
            perm_enum = Permission(req["permission"])
        except ValueError:
            return _err(400, f"Unknown permission '{req['permission']}'", "ERR_INVALID_PERMISSION")

        owning_module = PERMISSION_TO_MODULE.get(perm_enum)
        manager_module = get_manager_module(caller_role)
        if owning_module != manager_module:
            return _err(
                403,
                f"You manage module {manager_module}, but this permission belongs to {owning_module}",
                "ERR_LAYER5_ACCESS",
            )

    now = datetime.now(timezone.utc)
    execute_transaction(
        [
            (
                "UPDATE custom_role_permissions "
                "SET status = 'DENIED', reviewed_by = %s, reviewed_at = %s, review_note = %s "
                "WHERE id = %s",
                (session.user_id, now, body.review_note, request_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role_permission",
        entity_id=request_id,
        tenant_id=session.tenant_id,
        metadata={
            "decision": "DENIED",
            "role_id": str(req["role_id"]),
            "permission": req["permission"],
            "review_note": body.review_note,
        },
    )

    return JSONResponse(
        status_code=200,
        content={"message": "Permission request denied", "request_id": request_id},
    )


# =============================================================================
# GET /api/roles/{role_id} — Get role with full permission list
# =============================================================================

@router.get("/{role_id}")
async def get_custom_role(
    role_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Get a custom role with its full permission list and approval statuses.

    Authority:
        - SUPER_ADMIN or any M*_MANAGER
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    role_row = _fetch_custom_role(role_id, session.tenant_id)
    if not role_row:
        return _err(404, "Custom role not found", "ERR_NOT_FOUND")

    perms = _get_role_permissions(role_id, session.tenant_id)
    return JSONResponse(status_code=200, content=_serialize_role(role_row, perms))


# =============================================================================
# POST /api/roles/{role_id}/permissions — Request permissions
# =============================================================================

@router.post("/{role_id}/permissions")
async def request_permissions(
    role_id: str,
    body: RequestPermissionsBody,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Request one or more permissions for a custom role.

    Permission routing logic:
        - SUPER_ADMIN requests        → always APPROVED
        - Same-module permission       → APPROVED (no approval needed)
        - Platform-level permission    → APPROVED (no module owner)
        - Cross-module permission      → PENDING (owning module manager must approve)

    Authority:
        - SUPER_ADMIN
        - The M*_MANAGER who created the role
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    if not body.permissions:
        return _err(422, "permissions list must not be empty", "ERR_VALIDATION")

    role_row = _fetch_custom_role(role_id, session.tenant_id)
    if not role_row:
        return _err(404, "Custom role not found", "ERR_NOT_FOUND")

    # Only the role creator or SUPER_ADMIN can add permissions
    if caller_role != Role.SUPER_ADMIN and str(role_row["created_by"]) != session.user_id:
        return _err(
            403,
            "Only the role creator or SUPER_ADMIN can add permissions to this role",
            "ERR_LAYER5_ACCESS",
        )

    manager_module = get_manager_module(caller_role)  # None for SUPER_ADMIN
    now = datetime.now(timezone.utc)

    results = []
    insert_queries = []

    for perm_str in body.permissions:
        # Validate the permission value
        try:
            perm_enum = Permission(perm_str)
        except ValueError:
            results.append({
                "permission": perm_str,
                "status": "ERROR",
                "reason": f"Unknown permission '{perm_str}'",
            })
            continue

        # Skip if already requested
        existing = execute_query(
            "SELECT id, status FROM custom_role_permissions "
            "WHERE role_id = %s AND permission = %s",
            (role_id, perm_str),
            tenant_id=session.tenant_id,
        )
        if existing:
            results.append({
                "permission": perm_str,
                "status": existing[0]["status"],
                "reason": "Permission already requested on this role",
            })
            continue

        # Determine approval status via permission ownership
        owning_module = PERMISSION_TO_MODULE.get(perm_enum)  # None = platform-level
        if caller_role == Role.SUPER_ADMIN:
            approval_status = "APPROVED"
        elif owning_module is None:
            # Platform-level permission (USER_READ, AI_INVOKE, etc.) — auto-approve
            approval_status = "APPROVED"
        elif owning_module == manager_module:
            # Same-module permission — auto-approve
            approval_status = "APPROVED"
        else:
            # Cross-module — requires owning module manager's approval
            approval_status = "PENDING"

        req_id = str(uuid4())
        insert_queries.append((
            "INSERT INTO custom_role_permissions "
            "(id, tenant_id, role_id, permission, status, requested_by, requested_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (req_id, session.tenant_id, role_id, perm_str, approval_status, session.user_id, now),
        ))
        results.append({
            "permission": perm_str,
            "request_id": req_id,
            "status": approval_status,
            "reason": (
                "Auto-approved (same module or platform permission)"
                if approval_status == "APPROVED"
                else f"Pending approval from {owning_module} module manager"
            ),
        })

    if insert_queries:
        execute_transaction(insert_queries, tenant_id=session.tenant_id)

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role_permission",
        entity_id=role_id,
        tenant_id=session.tenant_id,
        metadata={"requested_permissions": body.permissions, "results": results},
    )

    return JSONResponse(
        status_code=200,
        content={
            "role_id": role_id,
            "results": results,
            "approved_count": sum(1 for r in results if r.get("status") == "APPROVED"),
            "pending_count": sum(1 for r in results if r.get("status") == "PENDING"),
            "error_count": sum(1 for r in results if r.get("status") == "ERROR"),
        },
    )


# =============================================================================
# DELETE /api/roles/{role_id}/permissions/{permission} — Remove permission
# =============================================================================

@router.delete("/{role_id}/permissions/{permission}")
async def remove_permission(
    role_id: str,
    permission: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Remove a permission from a custom role.

    Authority:
        - SUPER_ADMIN or the M*_MANAGER who created the role
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    role_row = _fetch_custom_role(role_id, session.tenant_id)
    if not role_row:
        return _err(404, "Custom role not found", "ERR_NOT_FOUND")

    if caller_role != Role.SUPER_ADMIN and str(role_row["created_by"]) != session.user_id:
        return _err(403, "Only the role creator or SUPER_ADMIN can remove permissions", "ERR_LAYER5_ACCESS")

    perm_rows = execute_query(
        "SELECT id FROM custom_role_permissions WHERE role_id = %s AND permission = %s",
        (role_id, permission),
        tenant_id=session.tenant_id,
    )
    if not perm_rows:
        return _err(404, "Permission not found on this role", "ERR_NOT_FOUND")

    execute_transaction(
        [("DELETE FROM custom_role_permissions WHERE role_id = %s AND permission = %s", (role_id, permission))],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.DELETE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role_permission",
        entity_id=str(perm_rows[0]["id"]),
        tenant_id=session.tenant_id,
        metadata={"role_id": role_id, "permission": permission},
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"Permission '{permission}' removed from role '{role_row['role_name']}'"},
    )


# =============================================================================
# DELETE /api/roles/{role_id} — Archive role
# =============================================================================

@router.delete("/{role_id}")
async def archive_custom_role(
    role_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Archive a custom role (ACTIVE → ARCHIVED).

    Archiving cascades: the role is revoked from all users it was assigned to.

    Invariants:
        - ARCHIVED is a terminal state (irreversible)
        - All user assignments are removed on archive

    Authority:
        - SUPER_ADMIN or the M*_MANAGER who created the role
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller_user(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Unrecognised caller role", "ERR_LAYER5_ACCESS")

    if not _is_manager_or_super(caller_role):
        return _err(403, "Module Manager or SUPER_ADMIN required", "ERR_LAYER5_ACCESS")

    role_row = _fetch_custom_role(role_id, session.tenant_id)
    if not role_row:
        return _err(404, "Custom role not found (or already archived)", "ERR_NOT_FOUND")

    if caller_role != Role.SUPER_ADMIN and str(role_row["created_by"]) != session.user_id:
        return _err(403, "Only the role creator or SUPER_ADMIN can archive this role", "ERR_LAYER5_ACCESS")

    now = datetime.now(timezone.utc)
    execute_transaction(
        [
            (
                "UPDATE custom_roles SET status = 'ARCHIVED', updated_at = %s WHERE id = %s",
                (now, role_id),
            ),
            # Revoke from all users (cascade archive)
            (
                "DELETE FROM user_custom_roles WHERE role_id = %s",
                (role_id,),
            ),
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="custom_role",
        entity_id=role_id,
        tenant_id=session.tenant_id,
        metadata={
            "previous_state": "ACTIVE",
            "new_state": "ARCHIVED",
            "role_name": role_row["role_name"],
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "message": (
                f"Role '{role_row['role_name']}' archived and revoked from all users"
            )
        },
    )
