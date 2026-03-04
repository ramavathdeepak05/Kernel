"""
ALIS Authentication Router — E01-S01 & E01-S02

MODULE: Platform Core (E01 — Platform Foundation)
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: Session, User

Provides authentication endpoints for ALIS.

Endpoints:
    POST /api/auth/login      — Authenticate and receive session token
    POST /api/auth/logout     — Revoke current session
    POST /api/auth/refresh    — Extend session expiry by 24h
    GET  /api/auth/me         — Get current authenticated user
    POST /api/auth/register   — Create a new user (ADMIN / SUPER_ADMIN only)
    POST /api/auth/bootstrap  — One-time: create first SUPER_ADMIN for a tenant

Must Align With:
    - security.py  : PasswordHasher, SessionManager, FailedLoginTracker, RateLimiter
    - rbac.py      : Role — enforced at endpoint level, no controller shortcuts
    - audit.py     : AuditLedger — every auth event is logged (Layer 6)
    - db_service.py: execute_query / execute_transaction (tenant-scoped)
    - Layer 4      : /login and /bootstrap are TenantMiddleware-exempt paths
    - Layer 5      : default-deny; no role bypasses

Hard Constraints (from Master Handbook):
    - NO JWT, NO cloud dependencies — tokens are opaque random strings
    - Passwords are NEVER stored or logged in plaintext
    - All auth events MUST be audit-logged
    - Rate limiting on login (20 req/min per IP)
    - Account lockout after 5 failed attempts (15 min)
    - Bootstrap is a one-time operation per tenant, protected by env secret
"""

import os
import secrets
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import (
    PasswordHasher,
    SessionManager,
    FailedLoginTracker,
    RateLimiter,
    InputValidator,
)
from server.core.rbac import Role
from server.core.audit import AuditLedger, AuditAction
from server.db_service import (
    execute_query,
    execute_transaction,
    execute_system_query,
    execute_system_transaction,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    tenant_id: str = Field(..., description="Institution tenant ID (e.g. 'woxsen')")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    role: str = Field(default="student", description="RBAC role to assign")
    email: Optional[str] = None
    display_name: Optional[str] = None
    # Defaults to caller's tenant; SUPER_ADMIN may override
    tenant_id: Optional[str] = None


class BootstrapRequest(BaseModel):
    """
    One-time request to seed the first SUPER_ADMIN for a new tenant.
    Protected by ALIS_BOOTSTRAP_SECRET environment variable.
    """
    tenant_id: str = Field(..., description="Tenant to bootstrap")
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    bootstrap_secret: str = Field(..., description="Must match ALIS_BOOTSTRAP_SECRET env var")
    email: Optional[str] = None
    display_name: Optional[str] = None


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _extract_token(authorization: Optional[str]) -> Optional[str]:
    """Extract the raw token from an 'Authorization: Bearer <token>' header."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _require_session(authorization: Optional[str]):
    """
    Validate the Authorization header and return the active session.

    Returns:
        (session, None)   on success
        (None, error_str) on failure
    """
    token = _extract_token(authorization)
    if not token:
        return None, "Missing or malformed Authorization header"
    session = SessionManager.validate_token(token)
    if not session:
        return None, "Token is invalid, expired, or revoked"
    return session, None


def _fetch_user_by_id(user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a non-deleted user row by primary key (tenant-scoped)."""
    rows = execute_query(
        "SELECT id, username, email, display_name, role, status, actor_type "
        "FROM users WHERE id = %s AND is_deleted = FALSE",
        (user_id,),
        tenant_id=tenant_id,
    )
    return rows[0] if rows else None


def _err(status: int, message: str, code: str, **extra) -> JSONResponse:
    """Construct a consistent error JSONResponse."""
    body: Dict[str, Any] = {"error": message, "code": code}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


# =============================================================================
# POST /api/auth/login
# =============================================================================

@router.post("/login")
async def login(request: Request, body: LoginRequest) -> JSONResponse:
    """
    Authenticate a user and issue a session token.

    Decision: Should this username/password be granted a session for this tenant?

    Flow:
        1. Rate-limit by IP (20 req/min)
        2. Lockout check — 5 failed attempts → 15-min block
        3. Fetch user from DB (tenant-scoped, case-sensitive username)
        4. Verify password hash
        5. Assert account is ACTIVE
        6. Create in-memory session; stamp tenant_id on session
        7. Audit LOGIN event
        8. Return opaque token (token value is never logged)
    """
    ip = request.client.host if request.client else "unknown"
    identifier = f"{body.tenant_id}:{body.username}"

    # --- Step 1: Rate limit ---
    if not RateLimiter.check(identifier=ip, max_requests=20, window_seconds=60):
        return _err(429, "Too many login attempts — try again in a minute", "ERR_RATE_LIMITED")

    # --- Step 2: Lockout ---
    if FailedLoginTracker.is_locked_out(identifier):
        remaining = FailedLoginTracker.get_lockout_remaining(identifier)
        AuditLedger.log(
            action=AuditAction.ACCESS_DENIED,
            actor_id=body.username,
            actor_role="unknown",
            entity_type="user",
            entity_id=body.username,
            tenant_id=body.tenant_id,
            metadata={"reason": "account_locked", "ip": ip},
        )
        retry_after = int(remaining.total_seconds()) if remaining else 900
        return _err(
            423,
            "Account temporarily locked due to repeated failed login attempts",
            "ERR_ACCOUNT_LOCKED",
            retry_after_seconds=retry_after,
        )

    # --- Step 3: Fetch user ---
    rows = execute_query(
        "SELECT id, username, email, display_name, password_hash, role, status, actor_type "
        "FROM users WHERE username = %s AND is_deleted = FALSE",
        (InputValidator.sanitize_string(body.username),),
        tenant_id=body.tenant_id,
    )

    if not rows:
        FailedLoginTracker.record_attempt(identifier, success=False, ip_address=ip)
        # Generic message — never reveal whether the username exists
        return _err(401, "Invalid credentials", "ERR_AUTH_INVALID")

    user = rows[0]

    # --- Step 4: Verify password ---
    if not PasswordHasher.verify(body.password, user["password_hash"]):
        FailedLoginTracker.record_attempt(identifier, success=False, ip_address=ip)
        AuditLedger.log(
            action=AuditAction.ACCESS_DENIED,
            actor_id=str(user["id"]),
            actor_role=user["role"],
            entity_type="user",
            entity_id=str(user["id"]),
            tenant_id=body.tenant_id,
            metadata={"reason": "wrong_password", "ip": ip},
        )
        return _err(401, "Invalid credentials", "ERR_AUTH_INVALID")

    # --- Step 5: Status check ---
    if user["status"] != "ACTIVE":
        return _err(
            403,
            f"Account is {user['status'].lower()} — contact your administrator",
            "ERR_ACCOUNT_INACTIVE",
        )

    # --- Step 6: Create session ---
    FailedLoginTracker.record_attempt(identifier, success=True, ip_address=ip)

    session, raw_token = SessionManager.create_session(
        user_id=str(user["id"]),
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    # Stamp tenant_id so TenantMiddleware can resolve it from the session
    # on all subsequent authenticated requests
    session.tenant_id = body.tenant_id

    # --- Step 7: Audit ---
    AuditLedger.log(
        action=AuditAction.LOGIN,
        actor_id=str(user["id"]),
        actor_role=user["role"],
        entity_type="user",
        entity_id=str(user["id"]),
        tenant_id=body.tenant_id,
        metadata={"ip": ip, "session_id": session.id},
    )

    # --- Step 8: Return token (raw token is never stored or logged) ---
    return JSONResponse(
        status_code=200,
        content={
            "token": raw_token,
            "session_id": session.id,
            "user_id": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "tenant_id": body.tenant_id,
            "expires_at": session.expires_at.isoformat(),
        },
    )


# =============================================================================
# POST /api/auth/logout
# =============================================================================

@router.post("/logout")
async def logout(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Revoke the current session.

    The token is immediately invalidated. Any subsequent request using
    this token will receive 401.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    SessionManager.revoke_session(session.id, reason="User-initiated logout")

    AuditLedger.log(
        action=AuditAction.LOGOUT,
        actor_id=session.user_id,
        actor_role="user",
        entity_type="session",
        entity_id=session.id,
        tenant_id=session.tenant_id,
        metadata={"ip": request.client.host if request.client else "unknown"},
    )

    return JSONResponse(status_code=200, content={"message": "Logged out successfully"})


# =============================================================================
# POST /api/auth/refresh
# =============================================================================

@router.post("/refresh")
async def refresh_session(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Extend the current session expiry by 24 hours.

    Call this before the token expires to maintain an active session
    without forcing a full re-login.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    session.refresh(extend_hours=24)

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.id,
            "expires_at": session.expires_at.isoformat(),
        },
    )


# =============================================================================
# GET /api/auth/me
# =============================================================================

@router.get("/me")
async def get_me(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Return the authenticated user's profile.

    Password hash is never included in the response.
    Uses session.tenant_id for RLS-scoped DB lookup.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    user = _fetch_user_by_id(session.user_id, session.tenant_id)
    if not user:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    return JSONResponse(
        status_code=200,
        content={
            "id": str(user["id"]),
            "username": user["username"],
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "role": user["role"],
            "status": user["status"],
            "tenant_id": session.tenant_id,
            "actor_type": user["actor_type"],
        },
    )


# =============================================================================
# POST /api/auth/register  (ADMIN / SUPER_ADMIN only)
# =============================================================================

@router.post("/register")
async def register_user(
    body: RegisterRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Create a new user within a tenant.

    Authority rules (Layer 5):
        - ADMIN       — may create users only within their own tenant
        - SUPER_ADMIN — may create users in any tenant; may assign any role

    Invariants:
        - ADMIN cannot assign SUPER_ADMIN role
        - Username must be unique within the target tenant
        - Password is hashed before storage and never logged
        - All creations are audit-logged with creator identity
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    caller = _fetch_user_by_id(session.user_id, session.tenant_id)
    if not caller:
        return _err(401, "Caller account not found", "ERR_AUTH_REQUIRED")

    try:
        caller_role = Role(caller["role"])
    except ValueError:
        return _err(403, "Caller has an unrecognised role", "ERR_LAYER5_ACCESS")

    # Only ADMIN or SUPER_ADMIN may register users
    if caller_role not in (Role.ADMIN, Role.SUPER_ADMIN):
        return _err(403, "ADMIN or SUPER_ADMIN role required to register users", "ERR_LAYER5_ACCESS")

    # Determine target tenant
    target_tenant = body.tenant_id or session.tenant_id

    # Cross-tenant creation: SUPER_ADMIN only
    if target_tenant != session.tenant_id and caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may create users in other tenants", "ERR_LAYER5_ACCESS")

    # Validate the role being assigned
    try:
        new_role = Role(body.role)
    except ValueError:
        return _err(
            422,
            f"Invalid role '{body.role}'",
            "ERR_INVALID_ROLE",
            valid_roles=[r.value for r in Role],
        )

    # ADMIN cannot grant SUPER_ADMIN
    if new_role == Role.SUPER_ADMIN and caller_role != Role.SUPER_ADMIN:
        return _err(403, "Only SUPER_ADMIN may assign the SUPER_ADMIN role", "ERR_LAYER5_ACCESS")

    # Validate email format
    if body.email and not InputValidator.validate_email(body.email):
        return _err(422, "Invalid email format", "ERR_VALIDATION")

    # Uniqueness check within the target tenant
    existing = execute_query(
        "SELECT id FROM users WHERE username = %s AND is_deleted = FALSE",
        (body.username,),
        tenant_id=target_tenant,
    )
    if existing:
        return _err(409, "Username already exists in this tenant", "ERR_DUPLICATE_USERNAME")

    # Hash password — plaintext is discarded immediately after hashing
    password_hash = PasswordHasher.hash(body.password)

    user_id = str(uuid4())
    now = datetime.now(timezone.utc)

    execute_transaction(
        [
            (
                """
                INSERT INTO users (
                    id, tenant_id, username, email, display_name,
                    password_hash, role, actor_type, status,
                    is_deleted, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'human', 'ACTIVE', FALSE, %s)
                """,
                (
                    user_id,
                    target_tenant,
                    InputValidator.sanitize_string(body.username),
                    body.email,
                    body.display_name,
                    password_hash,
                    new_role.value,
                    now,
                ),
            )
        ],
        tenant_id=target_tenant,
    )

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role=caller["role"],
        entity_type="user",
        entity_id=user_id,
        tenant_id=target_tenant,
        metadata={
            "username": body.username,
            "assigned_role": new_role.value,
            "created_by": caller["username"],
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": user_id,
            "username": body.username,
            "email": body.email,
            "display_name": body.display_name,
            "role": new_role.value,
            "status": "ACTIVE",
            "tenant_id": target_tenant,
            "actor_type": "human",
        },
    )


# =============================================================================
# POST /api/auth/bootstrap  (One-time per tenant)
# =============================================================================

@router.post("/bootstrap")
async def bootstrap_tenant(body: BootstrapRequest) -> JSONResponse:
    """
    One-time endpoint: seed the first SUPER_ADMIN for a brand-new tenant.

    Safety guarantees:
        - Blocked unless ALIS_BOOTSTRAP_SECRET env var is set
        - bootstrap_secret in the request body must match the env var
          (constant-time comparison — prevents timing attacks)
        - Rejected if the tenant already has ANY users (idempotency guard)
        - Uses system-level DB access (no tenant ContextVar needed yet)
        - Full audit log entry is written for the bootstrap event

    After this succeeds:
        POST /api/auth/login     → get a session token
        POST /api/auth/register  → provision the rest of the institution
    """
    expected_secret = os.getenv("ALIS_BOOTSTRAP_SECRET", "")
    if not expected_secret:
        return _err(
            503,
            "Bootstrap is disabled — set ALIS_BOOTSTRAP_SECRET to enable it",
            "ERR_BOOTSTRAP_DISABLED",
        )

    # Constant-time comparison prevents timing-based secret enumeration
    if not secrets.compare_digest(body.bootstrap_secret.encode(), expected_secret.encode()):
        return _err(403, "Invalid bootstrap secret", "ERR_AUTH_INVALID")

    # One-time guarantee: reject if the tenant already has users
    existing = execute_system_query(
        "SELECT COUNT(*) AS cnt FROM users WHERE tenant_id = %s AND is_deleted = FALSE",
        (body.tenant_id,),
    )
    count = int(existing[0]["cnt"]) if existing else 0
    if count > 0:
        return _err(
            409,
            "Tenant already has users — bootstrap is a one-time operation",
            "ERR_BOOTSTRAP_ALREADY_DONE",
        )

    if body.email and not InputValidator.validate_email(body.email):
        return _err(422, "Invalid email format", "ERR_VALIDATION")

    password_hash = PasswordHasher.hash(body.password)
    user_id = str(uuid4())
    now = datetime.now(timezone.utc)

    execute_system_transaction(
        [
            (
                """
                INSERT INTO users (
                    id, tenant_id, username, email, display_name,
                    password_hash, role, actor_type, status,
                    is_deleted, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'human', 'ACTIVE', FALSE, %s)
                """,
                (
                    user_id,
                    body.tenant_id,
                    InputValidator.sanitize_string(body.username),
                    body.email,
                    body.display_name,
                    password_hash,
                    Role.SUPER_ADMIN.value,
                    now,
                ),
            )
        ]
    )

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id="SYSTEM_BOOTSTRAP",
        actor_role="system",
        entity_type="user",
        entity_id=user_id,
        tenant_id=body.tenant_id,
        metadata={
            "username": body.username,
            "role": Role.SUPER_ADMIN.value,
            "event": "tenant_bootstrap",
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "message": "Tenant bootstrapped. Use POST /api/auth/login to continue.",
            "user_id": user_id,
            "username": body.username,
            "role": Role.SUPER_ADMIN.value,
            "tenant_id": body.tenant_id,
        },
    )
