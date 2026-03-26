"""
ALIS Organization Management Router — E01-S05

MODULE: Platform Core (E01 — Platform Foundation)
LAYER: Layer 1 (Module Authority) + Layer 5 (Roles, Authority & Quorum)
ENTITY: Organization

Manages institutional org units within a tenant (colleges, departments, etc.).
Organizations form a hierarchy via parent_id — a tenant can have one root org
with child departments beneath it.

Endpoints:
    POST   /api/organizations                   — Create organization
    GET    /api/organizations                   — List organizations (tree or flat)
    GET    /api/organizations/{id}              — Get single organization
    PATCH  /api/organizations/{id}              — Update name / code
    POST   /api/organizations/{id}/suspend      — Suspend (ACTIVE → SUSPENDED)
    POST   /api/organizations/{id}/activate     — Reactivate (SUSPENDED → ACTIVE)
    DELETE /api/organizations/{id}              — Soft-delete (→ ARCHIVED)

Authority Matrix (Layer 5):
    | Action         | SUPER_ADMIN | ADMIN | Others |
    |----------------|-------------|-------|--------|
    | Create         |      ✓      |   ✗   |   ✗    |
    | List / Get     |      ✓      |   ✓   |   ✗    |
    | Update         |      ✓      |   ✗   |   ✗    |
    | Suspend        |      ✓      |   ✗   |   ✗    |
    | Activate       |      ✓      |   ✗   |   ✗    |
    | Delete         |      ✓      |   ✗   |   ✗    |

Invariants:
    - code must be unique within a tenant (e.g. "CSE", "MECH")
    - ARCHIVED is terminal — no reactivation
    - Cannot delete an org that has child orgs (prevent orphaned hierarchy)
    - Suspending a parent does NOT cascade to children (explicit intent required)
    - All mutations are audit-logged
"""
from __future__ import annotations

import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import SessionManager
from server.core.rbac import Role
from server.core.audit import AuditLedger, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=256)
    code: str = Field(..., min_length=2, max_length=32,
                      description="Short unique code within tenant, e.g. 'CSE', 'FINANCE'")
    parent_id: Optional[str] = Field(None, description="Parent org ID for hierarchy")


class UpdateOrgRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=256)
    code: Optional[str] = Field(None, min_length=2, max_length=32)


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


def _fetch_caller(session) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        "SELECT id, username, role, status FROM users "
        "WHERE id = %s AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=session.tenant_id,
    )
    return rows[0] if rows else None


def _err(status: int, message: str, code: str, **extra) -> JSONResponse:
    body: Dict[str, Any] = {"error": message, "code": code}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


def _fetch_org(org_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a non-deleted org by ID within a tenant."""
    rows = execute_query(
        "SELECT id, tenant_id, name, code, parent_id, status, "
        "is_deleted, created_by, created_at, updated_at "
        "FROM organizations WHERE id = %s AND is_deleted = FALSE",
        (org_id,),
        tenant_id=tenant_id,
    )
    return rows[0] if rows else None


def _serialize_org(org: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(org["id"]),
        "tenant_id": str(org["tenant_id"]),
        "name": org["name"],
        "code": org["code"],
        "parent_id": str(org["parent_id"]) if org.get("parent_id") else None,
        "status": org["status"],
        "created_by": org["created_by"],
        "created_at": org["created_at"].isoformat() if org.get("created_at") else None,
        "updated_at": org["updated_at"].isoformat() if org.get("updated_at") else None,
    }


# =============================================================================
# POST /api/organizations — Create organization
# =============================================================================

@router.post("")
async def create_organization(
    body: CreateOrgRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Create a new organization unit within the tenant.

    Authority:
        - SUPER_ADMIN only

    Hierarchy:
        - Omit parent_id for a root-level org
        - Set parent_id to nest under an existing org (departments, etc.)
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
        return _err(403, "SUPER_ADMIN role required to create organizations", "ERR_LAYER5_ACCESS")

    # Validate parent exists (if provided)
    if body.parent_id:
        parent = _fetch_org(body.parent_id, session.tenant_id)
        if not parent:
            return _err(404, "Parent organization not found", "ERR_PARENT_NOT_FOUND")
        if parent["status"] == "ARCHIVED":
            return _err(409, "Cannot create a child under an archived organization", "ERR_PARENT_ARCHIVED")

    org_id = str(uuid4())
    now = datetime.now(timezone.utc)

    try:
        execute_transaction(
            [
                (
                    "INSERT INTO organizations "
                    "(id, tenant_id, name, code, parent_id, status, is_deleted, "
                    "created_by, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'ACTIVE', FALSE, %s, %s, %s)",
                    (
                        org_id,
                        session.tenant_id,
                        body.name,
                        body.code.upper(),
                        body.parent_id,
                        session.user_id,
                        now,
                        now,
                    ),
                )
            ],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_org_code_tenant" in str(e):
            return _err(
                409,
                f"An organization with code '{body.code.upper()}' already exists in this tenant",
                "ERR_DUPLICATE_ORG_CODE",
            )
        logger.error(f"Failed to create organization: {e}")
        return _err(500, "Internal error creating organization", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="organization",
        entity_id=org_id,
        tenant_id=session.tenant_id,
        metadata={"name": body.name, "code": body.code.upper(), "parent_id": body.parent_id},
    )

    org = _fetch_org(org_id, session.tenant_id)
    return JSONResponse(status_code=201, content=_serialize_org(org))


# =============================================================================
# GET /api/organizations — List organizations
# =============================================================================

@router.get("")
async def list_organizations(
    authorization: Optional[str] = Header(default=None),
    parent_id: Optional[str] = None,
    status: Optional[str] = None,
) -> JSONResponse:
    """
    List organizations within the tenant.

    Supports optional filters:
        ?parent_id=<id>     — list direct children of a parent
        ?parent_id=root     — list top-level orgs (no parent)
        ?status=ACTIVE      — filter by status

    Authority:
        - ADMIN / SUPER_ADMIN
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

    conditions = ["is_deleted = FALSE"]
    params: list = []

    if parent_id == "root":
        conditions.append("parent_id IS NULL")
    elif parent_id:
        conditions.append("parent_id = %s")
        params.append(parent_id)

    if status:
        conditions.append("status = %s")
        params.append(status.upper())

    where = " AND ".join(conditions)
    rows = execute_query(
        f"SELECT id, tenant_id, name, code, parent_id, status, "
        f"is_deleted, created_by, created_at, updated_at "
        f"FROM organizations WHERE {where} ORDER BY name ASC",
        tuple(params) if params else None,
        tenant_id=session.tenant_id,
    )

    return JSONResponse(
        status_code=200,
        content={"total": len(rows), "organizations": [_serialize_org(r) for r in rows]},
    )


# =============================================================================
# GET /api/organizations/{org_id} — Get single organization
# =============================================================================

@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Get a single organization by ID.

    Authority:
        - ADMIN / SUPER_ADMIN
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

    org = _fetch_org(org_id, session.tenant_id)
    if not org:
        return _err(404, "Organization not found", "ERR_ORG_NOT_FOUND")

    # Include direct child count for context
    child_rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM organizations WHERE parent_id = %s AND is_deleted = FALSE",
        (org_id,),
        tenant_id=session.tenant_id,
    )
    child_count = int(child_rows[0]["cnt"]) if child_rows else 0

    result = _serialize_org(org)
    result["child_count"] = child_count
    return JSONResponse(status_code=200, content=result)


# =============================================================================
# PATCH /api/organizations/{org_id} — Update organization
# =============================================================================

@router.patch("/{org_id}")
async def update_organization(
    org_id: str,
    body: UpdateOrgRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Update an organization's name or code.

    Authority:
        - SUPER_ADMIN only
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
        return _err(403, "SUPER_ADMIN role required to update organizations", "ERR_LAYER5_ACCESS")

    org = _fetch_org(org_id, session.tenant_id)
    if not org:
        return _err(404, "Organization not found", "ERR_ORG_NOT_FOUND")

    if org["status"] == "ARCHIVED":
        return _err(409, "Cannot update an archived organization", "ERR_ORG_ARCHIVED")

    fields: list = []
    values: list = []

    if body.name is not None:
        fields.append("name = %s")
        values.append(body.name)
    if body.code is not None:
        fields.append("code = %s")
        values.append(body.code.upper())

    if not fields:
        return _err(422, "No fields provided to update", "ERR_NO_FIELDS")

    fields.append("updated_at = %s")
    values.append(datetime.now(timezone.utc))
    values.append(org_id)

    try:
        execute_transaction(
            [(f"UPDATE organizations SET {', '.join(fields)} WHERE id = %s", tuple(values))],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_org_code_tenant" in str(e):
            return _err(409, f"An organization with that code already exists", "ERR_DUPLICATE_ORG_CODE")
        logger.error(f"Failed to update organization: {e}")
        return _err(500, "Internal error updating organization", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="organization",
        entity_id=org_id,
        tenant_id=session.tenant_id,
        metadata={"updated_fields": [f.split(" = ")[0] for f in fields[:-1]]},
    )

    updated = _fetch_org(org_id, session.tenant_id)
    return JSONResponse(status_code=200, content=_serialize_org(updated))


# =============================================================================
# POST /api/organizations/{org_id}/suspend — Suspend
# =============================================================================

@router.post("/{org_id}/suspend")
async def suspend_organization(
    org_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Suspend an organization (ACTIVE → SUSPENDED).

    A suspended org's users lose access but data is preserved.
    Does NOT cascade to child organizations.

    Authority:
        - SUPER_ADMIN only
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
        return _err(403, "SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    org = _fetch_org(org_id, session.tenant_id)
    if not org:
        return _err(404, "Organization not found", "ERR_ORG_NOT_FOUND")

    if org["status"] != "ACTIVE":
        return _err(
            409,
            f"Organization is already {org['status'].lower()} — only ACTIVE orgs can be suspended",
            "ERR_INVALID_STATE_TRANSITION",
        )

    execute_transaction(
        [("UPDATE organizations SET status = 'SUSPENDED', updated_at = %s WHERE id = %s",
          (datetime.now(timezone.utc), org_id))],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="organization",
        entity_id=org_id,
        tenant_id=session.tenant_id,
        metadata={"previous_state": "ACTIVE", "new_state": "SUSPENDED", "org_name": org["name"]},
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"Organization '{org['name']}' suspended successfully"},
    )


# =============================================================================
# POST /api/organizations/{org_id}/activate — Reactivate
# =============================================================================

@router.post("/{org_id}/activate")
async def activate_organization(
    org_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Reactivate a suspended organization (SUSPENDED → ACTIVE).

    Invariants:
        - Only SUSPENDED orgs can be reactivated
        - ARCHIVED is terminal (cannot be reactivated)

    Authority:
        - SUPER_ADMIN only
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
        return _err(403, "SUPER_ADMIN role required", "ERR_LAYER5_ACCESS")

    org = _fetch_org(org_id, session.tenant_id)
    if not org:
        return _err(404, "Organization not found", "ERR_ORG_NOT_FOUND")

    if org["status"] == "ARCHIVED":
        return _err(409, "Archived organizations cannot be reactivated", "ERR_INVALID_STATE_TRANSITION")

    if org["status"] == "ACTIVE":
        return _err(409, "Organization is already active", "ERR_INVALID_STATE_TRANSITION")

    execute_transaction(
        [("UPDATE organizations SET status = 'ACTIVE', updated_at = %s WHERE id = %s",
          (datetime.now(timezone.utc), org_id))],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="organization",
        entity_id=org_id,
        tenant_id=session.tenant_id,
        metadata={"previous_state": "SUSPENDED", "new_state": "ACTIVE", "org_name": org["name"]},
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"Organization '{org['name']}' reactivated successfully"},
    )


# =============================================================================
# DELETE /api/organizations/{org_id} — Soft-delete (ARCHIVED)
# =============================================================================

@router.delete("/{org_id}")
async def delete_organization(
    org_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Soft-delete an organization (status → ARCHIVED, is_deleted = TRUE).

    Invariants:
        - Cannot delete an org that has active child organizations
          (prevents orphaned hierarchy — delete children first)
        - ARCHIVED is terminal (irreversible)
        - Hard deletes are forbidden (Layer 4)

    Authority:
        - SUPER_ADMIN only
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
        return _err(403, "SUPER_ADMIN role required to delete organizations", "ERR_LAYER5_ACCESS")

    org = _fetch_org(org_id, session.tenant_id)
    if not org:
        return _err(404, "Organization not found", "ERR_ORG_NOT_FOUND")

    # Guard: block delete if active children exist
    children = execute_query(
        "SELECT COUNT(*) AS cnt FROM organizations "
        "WHERE parent_id = %s AND is_deleted = FALSE",
        (org_id,),
        tenant_id=session.tenant_id,
    )
    child_count = int(children[0]["cnt"]) if children else 0
    if child_count > 0:
        return _err(
            409,
            f"Cannot delete '{org['name']}': it has {child_count} active child organization(s). "
            "Delete or archive children first.",
            "ERR_HAS_CHILDREN",
            child_count=child_count,
        )

    now = datetime.now(timezone.utc)
    execute_transaction(
        [
            (
                "UPDATE organizations SET status = 'ARCHIVED', is_deleted = TRUE, "
                "deleted_at = %s, updated_at = %s WHERE id = %s",
                (now, now, org_id),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.DELETE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="organization",
        entity_id=org_id,
        tenant_id=session.tenant_id,
        metadata={"org_name": org["name"], "org_code": org["code"], "deleted_by": caller["username"]},
    )

    return JSONResponse(
        status_code=200,
        content={"message": f"Organization '{org['name']}' archived successfully"},
    )
