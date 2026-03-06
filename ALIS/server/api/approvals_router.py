"""
ALIS Approval & Quorum Router — E02-S02

MODULE: Platform Core (E02 — Shared Services)
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: ApprovalRequest, ApprovalAction

DB-backed REST surface for the Approval & Quorum framework.
Implements all three approval modes from the master handbook:
  - SINGLE : one approver from any allowed role
  - ANY    : M-of-N approvers from allowed roles (quorum count)
  - ALL    : every specified role must approve

Endpoints:
    POST  /api/approvals                   — Create approval request
    GET   /api/approvals                   — List requests (role-filtered)
    GET   /api/approvals/pending           — My actionable queue  ← before /{id}
    GET   /api/approvals/{id}              — Get request + actions
    POST  /api/approvals/{id}/approve      — Record approval; auto-resolves on quorum
    POST  /api/approvals/{id}/reject       — Reject (terminates immediately)

Authority Matrix (Layer 5):
    | Action         | Creator | Allowed Approver Role | ADMIN/SUPER_ADMIN |
    |----------------|---------|-----------------------|-------------------|
    | Create         |    ✓    |          ✓            |         ✓         |
    | List / Get     |   own   |         own           |        all        |
    | Pending queue  |    —    |      own role         |        all        |
    | Approve/Reject |    ✗    |          ✓            |    if in roles    |

Invariants:
    - A user can only take ONE action per request (DB unique constraint)
    - Rejection terminates immediately (no partial approval survives)
    - APPROVED / REJECTED are terminal states
    - All actions are audit-logged
"""

import json
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import SessionManager
from server.core.rbac import Role
from server.core.audit import AuditLedger, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_MODES = {"single", "any", "all"}


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateApprovalRequest(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=100,
                             description="Type of entity being approved, e.g. 'invoice'")
    entity_id: str = Field(..., min_length=1, max_length=100)
    action_type: str = Field(..., min_length=1, max_length=100,
                             description="Action requiring approval, e.g. 'fee_waiver'")
    config_id: str = Field(..., min_length=1, max_length=100,
                           description="Label for the approval configuration, e.g. 'fee_waiver'")
    required_roles: List[str] = Field(..., min_length=1,
                                      description="Role values that are authorised to approve")
    mode: str = Field(default="single", description="single | any | all")
    required_count: int = Field(default=1, ge=1,
                                description="Minimum approvals for ANY mode")
    context: Optional[Dict[str, Any]] = Field(default=None,
                                              description="Contextual metadata for audit")


class ApprovalActionRequest(BaseModel):
    comment: Optional[str] = Field(None, max_length=1000)


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


def _decode_jsonb(value) -> Any:
    """psycopg2 may return JSONB as string or native Python; handle both."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def _fetch_request(request_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_query(
        "SELECT id, tenant_id, entity_type, entity_id, action_type, config_id, "
        "status, requested_by, required_roles, mode, required_count, "
        "resolved_at, resolution_reason, context, created_at "
        "FROM approval_requests WHERE id = %s",
        (request_id,),
        tenant_id=tenant_id,
    )
    if not rows:
        return None
    row = dict(rows[0])
    row["required_roles"] = _decode_jsonb(row["required_roles"])
    row["context"] = _decode_jsonb(row.get("context") or {})
    return row


def _fetch_actions(request_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    return list(execute_query(
        "SELECT id, actor_id, actor_role, action, comment, acted_at "
        "FROM approval_actions WHERE request_id = %s ORDER BY acted_at",
        (request_id,),
        tenant_id=tenant_id,
    ))


def _serialize_request(req: Dict[str, Any],
                        actions: Optional[List] = None) -> Dict[str, Any]:
    out = {
        "id": str(req["id"]),
        "tenant_id": str(req["tenant_id"]),
        "entity_type": req["entity_type"],
        "entity_id": req["entity_id"],
        "action_type": req["action_type"],
        "config_id": req["config_id"],
        "status": req["status"],
        "requested_by": req["requested_by"],
        "required_roles": req["required_roles"],
        "mode": req["mode"],
        "required_count": req["required_count"],
        "resolved_at": req["resolved_at"].isoformat() if req.get("resolved_at") else None,
        "resolution_reason": req.get("resolution_reason"),
        "context": req.get("context") or {},
        "created_at": req["created_at"].isoformat() if req.get("created_at") else None,
    }
    if actions is not None:
        out["actions"] = [
            {
                "id": str(a["id"]),
                "actor_id": a["actor_id"],
                "actor_role": a["actor_role"],
                "action": a["action"],
                "comment": a.get("comment"),
                "acted_at": a["acted_at"].isoformat() if a.get("acted_at") else None,
            }
            for a in actions
        ]
    return out


def _check_quorum(req: Dict[str, Any], tenant_id: str) -> bool:
    """
    Return True if approval quorum is now met.
    Called AFTER inserting the new approval action.
    """
    actions = _fetch_actions(req["id"], tenant_id)
    approvals = [a for a in actions if a["action"] == "approve"]
    mode = req["mode"]

    if mode == "single":
        return len(approvals) >= 1

    if mode == "any":
        return len(approvals) >= req["required_count"]

    if mode == "all":
        approver_roles = {a["actor_role"] for a in approvals}
        required = set(req["required_roles"])
        return required.issubset(approver_roles)

    return False


# =============================================================================
# POST /api/approvals — Create approval request
# =============================================================================

@router.post("")
async def create_approval_request(
    body: CreateApprovalRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Create a new approval request.

    The caller specifies the entity being approved, the action type,
    which roles can approve, and the approval mode.

    Authority:
        - Any authenticated user (the requestor)
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_caller(session)
    if not caller:
        return _err(401, "Caller not found", "ERR_AUTH_REQUIRED")

    # Validate mode
    if body.mode not in VALID_MODES:
        return _err(422, f"Invalid mode '{body.mode}'. Must be: single, any, all",
                    "ERR_VALIDATION")

    # Validate required_roles are known Role values
    valid_role_values = {r.value for r in Role}
    bad_roles = [r for r in body.required_roles if r not in valid_role_values]
    if bad_roles:
        return _err(422, f"Unknown role(s): {bad_roles}", "ERR_INVALID_ROLE",
                    valid_roles=list(valid_role_values))

    # Compute effective required_count
    required_count = body.required_count
    if body.mode == "all":
        required_count = len(set(body.required_roles))
    elif body.mode == "single":
        required_count = 1

    request_id = str(uuid4())
    now = datetime.now(timezone.utc)

    execute_transaction(
        [
            (
                "INSERT INTO approval_requests "
                "(id, tenant_id, entity_type, entity_id, action_type, config_id, "
                "status, requested_by, required_roles, mode, required_count, "
                "context, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s, %s, %s, %s, %s)",
                (
                    request_id,
                    session.tenant_id,
                    body.entity_type,
                    body.entity_id,
                    body.action_type,
                    body.config_id,
                    session.user_id,
                    json.dumps(list(dict.fromkeys(body.required_roles))),  # deduplicated
                    body.mode,
                    required_count,
                    json.dumps(body.context or {}),
                    now,
                ),
            )
        ],
        tenant_id=session.tenant_id,
    )

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="approval_request",
        entity_id=request_id,
        tenant_id=session.tenant_id,
        metadata={
            "entity_type": body.entity_type,
            "entity_id": body.entity_id,
            "action_type": body.action_type,
            "mode": body.mode,
            "required_roles": body.required_roles,
        },
    )

    req = _fetch_request(request_id, session.tenant_id)
    return JSONResponse(status_code=201, content=_serialize_request(req, actions=[]))


# =============================================================================
# GET /api/approvals — List requests
# =============================================================================

@router.get("")
async def list_approval_requests(
    authorization: Optional[str] = Header(default=None),
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    List approval requests.

    Authority:
        - ADMIN / SUPER_ADMIN: all requests in tenant
        - Others: only requests they created
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

    conditions: list = []
    params: list = []

    # Scope: admins see all; others see own
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        conditions.append("requested_by = %s")
        params.append(session.user_id)

    if status:
        conditions.append("status = %s")
        params.append(status.upper())
    if entity_type:
        conditions.append("entity_type = %s")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = %s")
        params.append(entity_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_rows = execute_query(
        f"SELECT COUNT(*) AS total FROM approval_requests {where}",
        tuple(params) if params else None,
        tenant_id=session.tenant_id,
    )
    total = int(count_rows[0]["total"]) if count_rows else 0

    params.extend([limit, offset])
    rows = execute_query(
        f"SELECT id, tenant_id, entity_type, entity_id, action_type, config_id, "
        f"status, requested_by, required_roles, mode, required_count, "
        f"resolved_at, resolution_reason, context, created_at "
        f"FROM approval_requests {where} "
        f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(params),
        tenant_id=session.tenant_id,
    )

    results = []
    for row in rows:
        r = dict(row)
        r["required_roles"] = _decode_jsonb(r["required_roles"])
        r["context"] = _decode_jsonb(r.get("context") or {})
        results.append(_serialize_request(r))

    return JSONResponse(
        status_code=200,
        content={"total": total, "limit": limit, "offset": offset, "requests": results},
    )


# =============================================================================
# GET /api/approvals/pending — My actionable queue
# NOTE: Defined BEFORE /{id} to avoid path collision.
# =============================================================================

@router.get("/pending")
async def get_pending_for_me(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    List PENDING approval requests that the caller is authorised to act on
    (i.e. their role is in required_roles).

    Authority:
        - Any authenticated user (filtered to own role)
        - ADMIN / SUPER_ADMIN: see all pending
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

    if caller_role in (Role.ADMIN, Role.SUPER_ADMIN):
        # Admins see all pending
        rows = execute_query(
            "SELECT id, tenant_id, entity_type, entity_id, action_type, config_id, "
            "status, requested_by, required_roles, mode, required_count, "
            "resolved_at, resolution_reason, context, created_at "
            "FROM approval_requests WHERE status = 'PENDING' "
            "ORDER BY created_at ASC",
            None,
            tenant_id=session.tenant_id,
        )
    else:
        # Filter to requests where caller's role is in required_roles
        # and caller hasn't already acted
        rows = execute_query(
            "SELECT ar.id, ar.tenant_id, ar.entity_type, ar.entity_id, "
            "ar.action_type, ar.config_id, ar.status, ar.requested_by, "
            "ar.required_roles, ar.mode, ar.required_count, "
            "ar.resolved_at, ar.resolution_reason, ar.context, ar.created_at "
            "FROM approval_requests ar "
            "WHERE ar.status = 'PENDING' "
            "AND ar.required_roles @> %s::jsonb "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM approval_actions aa "
            "  WHERE aa.request_id = ar.id AND aa.actor_id = %s"
            ") "
            "ORDER BY ar.created_at ASC",
            (json.dumps([caller_role.value]), session.user_id),
            tenant_id=session.tenant_id,
        )

    results = []
    for row in rows:
        r = dict(row)
        r["required_roles"] = _decode_jsonb(r["required_roles"])
        r["context"] = _decode_jsonb(r.get("context") or {})
        results.append(_serialize_request(r))

    return JSONResponse(
        status_code=200,
        content={"total": len(results), "pending": results},
    )


# =============================================================================
# GET /api/approvals/{request_id} — Get request + actions
# =============================================================================

@router.get("/{request_id}")
async def get_approval_request(
    request_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Get a single approval request with its full action history.

    Authority:
        - ADMIN / SUPER_ADMIN: any request
        - Others: only requests they created or can act on
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

    req = _fetch_request(request_id, session.tenant_id)
    if not req:
        return _err(404, "Approval request not found", "ERR_NOT_FOUND")

    # Access check: must be admin, creator, or an authorised approver
    is_admin = caller_role in (Role.ADMIN, Role.SUPER_ADMIN)
    is_creator = req["requested_by"] == session.user_id
    is_approver = caller_role.value in req["required_roles"]

    if not (is_admin or is_creator or is_approver):
        return _err(403, "You do not have access to this approval request", "ERR_LAYER5_ACCESS")

    actions = _fetch_actions(request_id, session.tenant_id)
    return JSONResponse(status_code=200, content=_serialize_request(req, actions))


# =============================================================================
# POST /api/approvals/{request_id}/approve — Record approval
# =============================================================================

@router.post("/{request_id}/approve")
async def approve_request(
    request_id: str,
    body: ApprovalActionRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Record an approval action.

    Auto-resolves to APPROVED when quorum is met based on mode:
        - SINGLE : any 1 approval
        - ANY    : required_count approvals
        - ALL    : every required role has approved

    Invariants:
        - Caller's role must be in required_roles
        - Each user can only act once per request
        - Requestor cannot self-approve

    Authority:
        - Users whose role is listed in required_roles
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

    req = _fetch_request(request_id, session.tenant_id)
    if not req:
        return _err(404, "Approval request not found", "ERR_NOT_FOUND")

    if req["status"] != "PENDING":
        return _err(409,
                    f"Request is already {req['status'].lower()} — no further actions allowed",
                    "ERR_ALREADY_RESOLVED")

    # Role authorisation check
    if caller_role.value not in req["required_roles"]:
        return _err(403,
                    f"Role '{caller_role.value}' is not authorised to approve this request. "
                    f"Required: {req['required_roles']}",
                    "ERR_LAYER5_ACCESS")

    # Self-approval guard
    if req["requested_by"] == session.user_id:
        return _err(403, "You cannot approve a request you created", "ERR_SELF_APPROVE")

    # For ALL mode — check if this role has already approved
    if req["mode"] == "all":
        existing_role_approval = execute_query(
            "SELECT id FROM approval_actions "
            "WHERE request_id = %s AND actor_role = %s AND action = 'approve'",
            (request_id, caller_role.value),
            tenant_id=session.tenant_id,
        )
        if existing_role_approval:
            return _err(409,
                        f"Role '{caller_role.value}' has already approved this request",
                        "ERR_DUPLICATE_ROLE_APPROVAL")

    action_id = str(uuid4())
    now = datetime.now(timezone.utc)

    try:
        execute_transaction(
            [
                (
                    "INSERT INTO approval_actions "
                    "(id, tenant_id, request_id, actor_id, actor_role, action, comment, acted_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'approve', %s, %s)",
                    (action_id, session.tenant_id, request_id,
                     session.user_id, caller_role.value, body.comment, now),
                )
            ],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_approval_actor" in str(e):
            return _err(409, "You have already taken action on this request",
                        "ERR_DUPLICATE_ACTION")
        logger.error(f"Failed to record approval action: {e}")
        return _err(500, "Internal error recording approval", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="approval_request",
        entity_id=request_id,
        tenant_id=session.tenant_id,
        metadata={"action": "approve", "comment": body.comment},
    )

    # Re-fetch updated request and check quorum
    req = _fetch_request(request_id, session.tenant_id)
    quorum_met = _check_quorum(req, session.tenant_id)

    if quorum_met:
        execute_transaction(
            [
                (
                    "UPDATE approval_requests "
                    "SET status = 'APPROVED', resolved_at = %s, resolution_reason = 'Quorum met' "
                    "WHERE id = %s",
                    (now, request_id),
                )
            ],
            tenant_id=session.tenant_id,
        )
        AuditLedger.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=session.user_id,
            actor_role=caller["role"],
            entity_type="approval_request",
            entity_id=request_id,
            tenant_id=session.tenant_id,
            metadata={"previous_state": "PENDING", "new_state": "APPROVED", "reason": "Quorum met"},
        )

    req = _fetch_request(request_id, session.tenant_id)
    actions = _fetch_actions(request_id, session.tenant_id)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Approval recorded" + (" — request approved" if quorum_met else " — awaiting more approvals"),
            "request": _serialize_request(req, actions),
        },
    )


# =============================================================================
# POST /api/approvals/{request_id}/reject — Reject request
# =============================================================================

@router.post("/{request_id}/reject")
async def reject_request(
    request_id: str,
    body: ApprovalActionRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Reject an approval request. Terminates the request immediately.

    A single rejection from any authorised role is sufficient to terminate.

    Invariants:
        - Caller's role must be in required_roles
        - Each user can only act once per request
        - Requestor cannot self-reject

    Authority:
        - Users whose role is listed in required_roles
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

    req = _fetch_request(request_id, session.tenant_id)
    if not req:
        return _err(404, "Approval request not found", "ERR_NOT_FOUND")

    if req["status"] != "PENDING":
        return _err(409,
                    f"Request is already {req['status'].lower()} — no further actions allowed",
                    "ERR_ALREADY_RESOLVED")

    if caller_role.value not in req["required_roles"]:
        return _err(403,
                    f"Role '{caller_role.value}' is not authorised to reject this request",
                    "ERR_LAYER5_ACCESS")

    if req["requested_by"] == session.user_id:
        return _err(403, "You cannot reject a request you created", "ERR_SELF_REJECT")

    action_id = str(uuid4())
    now = datetime.now(timezone.utc)
    reason = body.comment or "Rejected"

    try:
        execute_transaction(
            [
                (
                    "INSERT INTO approval_actions "
                    "(id, tenant_id, request_id, actor_id, actor_role, action, comment, acted_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'reject', %s, %s)",
                    (action_id, session.tenant_id, request_id,
                     session.user_id, caller_role.value, body.comment, now),
                ),
                (
                    "UPDATE approval_requests "
                    "SET status = 'REJECTED', resolved_at = %s, resolution_reason = %s "
                    "WHERE id = %s",
                    (now, reason, request_id),
                ),
            ],
            tenant_id=session.tenant_id,
        )
    except Exception as e:
        if "uq_approval_actor" in str(e):
            return _err(409, "You have already taken action on this request",
                        "ERR_DUPLICATE_ACTION")
        logger.error(f"Failed to record rejection: {e}")
        return _err(500, "Internal error recording rejection", "ERR_INTERNAL")

    AuditLedger.log(
        action=AuditAction.STATE_TRANSITION,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="approval_request",
        entity_id=request_id,
        tenant_id=session.tenant_id,
        metadata={
            "previous_state": "PENDING",
            "new_state": "REJECTED",
            "reason": reason,
        },
    )

    req = _fetch_request(request_id, session.tenant_id)
    actions = _fetch_actions(request_id, session.tenant_id)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Request rejected",
            "request": _serialize_request(req, actions),
        },
    )
