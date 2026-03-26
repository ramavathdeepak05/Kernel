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
from __future__ import annotations

import os
import secrets
import logging
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt as _pyjwt

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.security import (
    PasswordHasher,
    SessionManager,
    PasswordResetManager,
    GuardianOTPManager,
    FailedLoginTracker,
    RateLimiter,
    InputValidator,
)
from server.core.rbac import Role
from server.core.audit import AuditLedger, AuditAction
from server.core.mfa_service import MFAService, MFA_REQUIRED_ROLES
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
    role: str = Field(default=Role.STUDENT.value, description="RBAC role to assign")
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


# ---------------------------------------------------------------------------
# MFA Request / Response Models
# ---------------------------------------------------------------------------

class MFAEnrollRequest(BaseModel):
    device_name: str = Field(default="Authenticator App", max_length=128)


class MFAConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8, description="6-digit TOTP code")


class MFAVerifyRequest(BaseModel):
    mfa_token: str = Field(..., description="Short-lived challenge token from /login")
    code: str = Field(..., min_length=6, max_length=8, description="6-digit TOTP or 8-char backup code")
    trust_device: bool = Field(default=False, description="Trust this device for 30 days")


class MFADisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8, description="Current TOTP code to confirm disable")


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


# ---------------------------------------------------------------------------
# MFA challenge token helpers (short-lived JWT, purpose="mfa_challenge")
# ---------------------------------------------------------------------------

def _build_mfa_token(user_id: str, tenant_id: str, role: str) -> str:
    """
    Issue a short-lived JWT for the MFA challenge step.

    Claims:
        sub      — user_id
        tenant   — tenant_id
        role     — user role (needed to create the full session after MFA)
        purpose  — "mfa_challenge"  (used to reject this token at all other endpoints)
        exp      — now + mfa_challenge_token_expire_minutes
    """
    from server.core.settings import settings

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.mfa_challenge_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "role": role,
        "purpose": "mfa_challenge",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return _pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_mfa_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate an mfa_challenge JWT.

    Returns the claims dict on success, None if invalid/expired/wrong purpose.
    """
    from server.core.settings import settings

    try:
        claims = _pyjwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if claims.get("purpose") != "mfa_challenge":
            return None
        return claims
    except _pyjwt.ExpiredSignatureError:
        return None
    except _pyjwt.PyJWTError:
        return None


def _device_fingerprint(request: Request) -> str:
    """
    Build a stable device fingerprint from User-Agent + client IP.

    Used as the input to SHA-256 inside MFAService.trust_device / is_device_trusted.
    """
    ua = request.headers.get("user-agent", "unknown-ua")
    ip = request.client.host if request.client else "unknown-ip"
    return f"{ua}:{ip}"


# =============================================================================
# POST /api/auth/login
# =============================================================================

@router.post("/login")
async def login(request: Request, body: LoginRequest) -> JSONResponse:
    ip = request.client.host if request.client else "unknown"

    # Rate-limit check (20 req/min per IP)
    if not RateLimiter.check(f"login:{ip}", max_requests=20, window_seconds=60):
        return _err(429, "Too many login attempts. Try again shortly.", "ERR_RATE_LIMITED")

    identifier = f"{body.tenant_id}:{body.username}"

    # Account lockout check
    if FailedLoginTracker.is_locked_out(identifier):
        remaining = FailedLoginTracker.get_lockout_remaining(identifier)
        retry_secs = int(remaining.total_seconds()) if remaining else 900
        return JSONResponse(
            status_code=423,
            content={
                "error": "Account temporarily locked after repeated failures",
                "code": "ERR_ACCOUNT_LOCKED",
                "retry_after_seconds": retry_secs,
            },
        )

    # Fetch user
    rows = execute_query(
        "SELECT id, username, email, display_name, password_hash, role, status, actor_type "
        "FROM users WHERE username = %s AND is_deleted = FALSE",
        (body.username,),
        tenant_id=body.tenant_id,
    )

    if not rows or not PasswordHasher.verify(body.password, rows[0].get("password_hash") or ""):
        FailedLoginTracker.record_attempt(identifier, success=False, ip_address=ip)
        return _err(401, "Invalid credentials", "ERR_AUTH_INVALID")

    user = rows[0]

    if user["status"] != "ACTIVE":
        return _err(403, "Account is not active", "ERR_ACCOUNT_INACTIVE")

    FailedLoginTracker.record_attempt(identifier, success=True, ip_address=ip)

    user_id_str = str(user["id"])
    user_role = user["role"]

    # ------------------------------------------------------------------
    # MFA gate: check if MFA is required and device is not already trusted
    # ------------------------------------------------------------------
    role_requires_mfa = user_role in MFA_REQUIRED_ROLES
    has_mfa = MFAService.has_active_mfa(body.tenant_id, user_id_str)
    fingerprint = _device_fingerprint(request)
    device_trusted = MFAService.is_device_trusted(body.tenant_id, user_id_str, fingerprint)

    mfa_needed = (role_requires_mfa or has_mfa) and not device_trusted

    if mfa_needed:
        # Issue a short-lived MFA challenge token — do NOT create a full session yet
        mfa_token = _build_mfa_token(user_id_str, body.tenant_id, user_role)

        AuditLedger.log(
            action=AuditAction.LOGIN,
            actor_id=user_id_str,
            actor_role=user_role,
            entity_type="mfa_challenge",
            entity_id=user_id_str,
            tenant_id=body.tenant_id,
            metadata={"ip": ip, "username": user["username"], "event": "mfa_challenge_issued"},
        )

        return JSONResponse(
            status_code=200,
            content={
                "mfa_required": True,
                "mfa_token": mfa_token,
                "user_id": user_id_str,
                "tenant_id": body.tenant_id,
            },
        )

    # ------------------------------------------------------------------
    # No MFA required (or device already trusted) — issue full session
    # ------------------------------------------------------------------
    session, token = SessionManager.create_session(
        user_id=user_id_str,
        tenant_id=body.tenant_id,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )

    AuditLedger.log(
        action=AuditAction.LOGIN,
        actor_id=user_id_str,
        actor_role=user_role,
        entity_type="session",
        entity_id=session.id,
        tenant_id=body.tenant_id,
        metadata={"ip": ip, "username": user["username"]},
    )

    return JSONResponse(
        status_code=200,
        content={
            "token": token,
            "session_id": session.id,
            "user_id": user_id_str,
            "username": user["username"],
            "role": user_role,
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
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    user = _fetch_user_by_id(session.user_id, session.tenant_id)
    if not user:
        return _err(404, "User account not found", "ERR_USER_NOT_FOUND")

    return JSONResponse(
        status_code=200,
        content={
            "id": str(user["id"]),
            "username": user["username"],
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "role": user["role"],
            "status": user.get("status", "ACTIVE"),
            "tenant_id": session.tenant_id,
            "actor_type": user.get("actor_type", "human"),
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


# =============================================================================
# POST /api/auth/mfa/enroll
# =============================================================================

@router.post("/mfa/enroll")
async def mfa_enroll(
    request: Request,
    body: MFAEnrollRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Begin TOTP enrollment for the authenticated user.

    Creates a pending (is_active=FALSE) mfa_devices row and returns:
      - totp_uri     : otpauth:// URI — render as a QR code in the frontend
      - backup_codes : 8 one-time codes — show once and prompt user to save them

    The device is NOT yet active. Call POST /mfa/confirm with the first TOTP
    code to activate it.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    result = MFAService.enroll_device(
        org_id=session.tenant_id,
        user_id=session.user_id,
        device_name=body.device_name,
    )

    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=session.user_id,
        actor_role="user",
        entity_type="mfa_device",
        entity_id=result["device_id"],
        tenant_id=session.tenant_id,
        metadata={"event": "mfa_enrollment_started", "device_name": body.device_name},
    )

    return JSONResponse(status_code=200, content=result)


# =============================================================================
# POST /api/auth/mfa/confirm
# =============================================================================

@router.post("/mfa/confirm")
async def mfa_confirm(
    body: MFAConfirmRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Confirm TOTP enrollment by verifying the first code from the authenticator app.

    Activates the pending mfa_devices row for the authenticated user.
    Returns 200 on success, 400 if the code is wrong or no pending enrollment exists.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    ok = MFAService.confirm_enrollment(
        org_id=session.tenant_id,
        user_id=session.user_id,
        code=body.code,
    )
    if not ok:
        return _err(400, "Invalid TOTP code or no pending enrollment found", "ERR_MFA_INVALID_CODE")

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role="user",
        entity_type="mfa_device",
        entity_id=session.user_id,
        tenant_id=session.tenant_id,
        metadata={"event": "mfa_enrollment_confirmed"},
    )

    return JSONResponse(status_code=200, content={"message": "MFA enrollment confirmed. MFA is now active."})


# =============================================================================
# POST /api/auth/mfa/verify
# =============================================================================

@router.post("/mfa/verify")
async def mfa_verify(
    request: Request,
    body: MFAVerifyRequest,
) -> JSONResponse:
    """
    Complete the MFA challenge during login and receive a full session token.

    Flow:
      1. POST /login  → mfa_required=true + mfa_token (5-minute JWT)
      2. User enters TOTP code from authenticator app (or a backup code)
      3. POST /mfa/verify  → full session token (same shape as a normal login response)

    If trust_device=true the device fingerprint (UA + IP) is stored as trusted
    for 30 days; future logins from this device skip the MFA challenge.
    """
    # Decode and validate the short-lived MFA challenge token
    claims = _decode_mfa_token(body.mfa_token)
    if not claims:
        return _err(401, "MFA token is invalid or expired", "ERR_MFA_TOKEN_INVALID")

    user_id = claims["sub"]
    tenant_id = claims["tenant"]
    user_role = claims.get("role", "")

    # Verify the TOTP / backup code
    ok = MFAService.verify_challenge(
        org_id=tenant_id,
        user_id=user_id,
        code=body.code,
    )
    if not ok:
        return _err(401, "Invalid MFA code", "ERR_MFA_INVALID_CODE")

    # Optionally trust the device
    if body.trust_device:
        MFAService.trust_device(tenant_id, user_id, _device_fingerprint(request))

    # Issue full session
    ip = request.client.host if request.client else "unknown"
    session, token = SessionManager.create_session(
        user_id=user_id,
        tenant_id=tenant_id,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )

    # Fetch user details for the response
    user = _fetch_user_by_id(user_id, tenant_id)
    username = user["username"] if user else user_id

    AuditLedger.log(
        action=AuditAction.LOGIN,
        actor_id=user_id,
        actor_role=user_role,
        entity_type="session",
        entity_id=session.id,
        tenant_id=tenant_id,
        metadata={
            "ip": ip,
            "event": "mfa_verified",
            "device_trusted": body.trust_device,
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "token": token,
            "session_id": session.id,
            "user_id": user_id,
            "username": username,
            "role": user_role,
            "tenant_id": tenant_id,
            "expires_at": session.expires_at.isoformat(),
        },
    )


# =============================================================================
# POST /api/auth/mfa/disable
# =============================================================================

@router.post("/mfa/disable")
async def mfa_disable(
    body: MFAConfirmRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Disable MFA for the authenticated user.

    Requires a valid current TOTP code to prevent an attacker with a stolen
    session token from disabling MFA without physical access to the device.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    # Re-verify TOTP to confirm intent
    ok = MFAService.verify_challenge(
        org_id=session.tenant_id,
        user_id=session.user_id,
        code=body.code,
    )
    if not ok:
        return _err(401, "Invalid TOTP code — MFA not disabled", "ERR_MFA_INVALID_CODE")

    MFAService.disable_mfa(org_id=session.tenant_id, user_id=session.user_id)

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=session.user_id,
        actor_role="user",
        entity_type="mfa_device",
        entity_id=session.user_id,
        tenant_id=session.tenant_id,
        metadata={"event": "mfa_disabled"},
    )

    return JSONResponse(status_code=200, content={"message": "MFA has been disabled for your account."})


# =============================================================================
# GET /api/auth/mfa/status
# =============================================================================

@router.get("/mfa/status")
async def mfa_status(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Return MFA enrollment status and whether MFA is mandatory for the caller's role.

    Response:
        {
            "mfa_enrolled":  bool,   # has at least one active TOTP device
            "mfa_required":  bool,   # role is in MFA_REQUIRED_ROLES
            "role":          str,
        }
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    user = _fetch_user_by_id(session.user_id, session.tenant_id)
    if not user:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    user_role = user["role"]
    enrolled = MFAService.has_active_mfa(session.tenant_id, session.user_id)
    required = user_role in MFA_REQUIRED_ROLES

    return JSONResponse(
        status_code=200,
        content={
            "mfa_enrolled": enrolled,
            "mfa_required": required,
            "role": user_role,
        },
    )


# =============================================================================
# PASSWORD RESET (unauthenticated flows — no session required)
# =============================================================================


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Registered email address")
    tenant_id: str = Field(..., description="Institution tenant ID")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Reset token from email")
    new_password: str = Field(..., min_length=8, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


@router.post("/forgot-password")
async def forgot_password(request: Request, body: ForgotPasswordRequest) -> JSONResponse:
    """
    Initiate password reset. Always returns 200 to prevent user enumeration.

    If the email is registered, a reset link is queued via the notification service.
    Token is Redis-backed, 30-minute TTL, single-use.
    """
    if not InputValidator.validate_email(body.email):
        return _err(400, "Invalid email format", "ERR_INVALID_EMAIL")

    if not RateLimiter.check(f"pwreset:{body.email}", max_requests=3, window_seconds=3600):
        return _err(429, "Too many reset requests. Try again in 1 hour.", "ERR_RATE_LIMITED")

    # Look up user — safe to fail silently (prevents enumeration)
    rows = execute_system_query(
        "SELECT id, email, role, is_deleted FROM users WHERE email = %s AND tenant_id = %s",
        (body.email.lower(), body.tenant_id),
    )
    if rows and not rows[0].get("is_deleted"):
        user = rows[0]
        try:
            token = PasswordResetManager.generate_token(user["id"], body.tenant_id)
            # Deliver via notification service (email)
            from server.core.notifications.service import NotificationService
            NotificationService.send(
                channel="email",
                recipient_id=user["id"],
                template_key="auth.password_reset",
                tenant_id=body.tenant_id,
                context={"reset_token": token, "user_email": body.email},
            )
        except Exception:
            logger.exception("forgot_password: token/notification error for user %s", user["id"])
            # Still return 200 — don't expose internal errors

        AuditLog.log(
            action=AuditAction.PASSWORD_RESET_REQUESTED,
            actor_id=rows[0]["id"],
            actor_type="user",
            tenant_id=body.tenant_id,
            metadata={"email": body.email},
        )

    return JSONResponse(status_code=200, content={
        "message": "If that email is registered, a reset link has been sent."
    })


@router.post("/reset-password")
async def reset_password(request: Request, body: ResetPasswordRequest) -> JSONResponse:
    """
    Complete password reset using a valid token.

    Token is consumed (single-use) on first call. Returns 400 if expired or invalid.
    """
    payload = PasswordResetManager.validate_and_consume(body.token)
    if not payload:
        return _err(400, "Reset token is invalid or has expired.", "ERR_INVALID_RESET_TOKEN")

    user_id = payload["user_id"]
    tenant_id = payload["tenant_id"]

    new_hash = PasswordHasher.hash(body.new_password)
    execute_transaction(
        [("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s AND tenant_id = %s",
          (new_hash, user_id, tenant_id))],
        tenant_id=tenant_id,
    )

    # Revoke all existing sessions — password change invalidates all sessions
    SessionManager.revoke_all_user_sessions(user_id, reason="Password reset")

    AuditLog.log(
        action=AuditAction.PASSWORD_RESET_COMPLETED,
        actor_id=user_id,
        actor_type="user",
        tenant_id=tenant_id,
        metadata={},
    )

    return JSONResponse(status_code=200, content={"message": "Password updated. Please log in."})


@router.post("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """
    Change password for an authenticated user.

    Requires current password verification. Revokes all other sessions on success.
    """
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    user = _fetch_user_by_id(session.user_id, session.tenant_id)
    if not user:
        return _err(404, "User not found", "ERR_USER_NOT_FOUND")

    if not PasswordHasher.verify(body.current_password, user.get("password_hash", "")):
        return _err(400, "Current password is incorrect.", "ERR_WRONG_PASSWORD")

    new_hash = PasswordHasher.hash(body.new_password)
    execute_transaction(
        [("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s AND tenant_id = %s",
          (new_hash, session.user_id, session.tenant_id))],
        tenant_id=session.tenant_id,
    )

    # Revoke all sessions except the current one
    all_sessions = SessionManager.list_user_sessions(session.user_id)
    for s in all_sessions:
        if s["session_id"] != session.id and s["is_active"]:
            SessionManager.revoke_session(s["session_id"], reason="Password changed")

    AuditLog.log(
        action=AuditAction.PASSWORD_CHANGED,
        actor_id=session.user_id,
        actor_type="user",
        tenant_id=session.tenant_id,
        metadata={},
    )

    return JSONResponse(status_code=200, content={"message": "Password changed."})


# =============================================================================
# SESSION VISIBILITY (authenticated)
# =============================================================================


@router.get("/sessions")
async def list_sessions(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """List all active sessions for the authenticated user."""
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    sessions = SessionManager.list_user_sessions(session.user_id)
    # Mark which one is the current session
    for s in sessions:
        s["is_current"] = s["session_id"] == session.id

    return JSONResponse(status_code=200, content={"sessions": sessions})


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Revoke a specific session. Cannot revoke the current session — use logout instead."""
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    if session_id == session.id:
        return _err(400, "Cannot revoke your current session. Use /logout instead.", "ERR_CANNOT_REVOKE_CURRENT")

    target = SessionManager.get_session(session_id)
    if not target or target.user_id != session.user_id:
        return _err(404, "Session not found", "ERR_SESSION_NOT_FOUND")

    SessionManager.revoke_session(session_id, reason="User revoked via API")

    AuditLog.log(
        action=AuditAction.SESSION_REVOKED,
        actor_id=session.user_id,
        actor_type="user",
        tenant_id=session.tenant_id,
        metadata={"revoked_session_id": session_id},
    )

    return JSONResponse(status_code=200, content={"message": "Session revoked."})


@router.delete("/sessions")
async def revoke_all_other_sessions(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Revoke all sessions except the current one (sign out everywhere else)."""
    session, error = _require_session(authorization)
    if error:
        return _err(401, error, "ERR_AUTH_REQUIRED")

    all_sessions = SessionManager.list_user_sessions(session.user_id)
    revoked = 0
    for s in all_sessions:
        if s["session_id"] != session.id and s["is_active"]:
            SessionManager.revoke_session(s["session_id"], reason="Sign out all other sessions")
            revoked += 1

    AuditLog.log(
        action=AuditAction.SESSION_REVOKED,
        actor_id=session.user_id,
        actor_type="user",
        tenant_id=session.tenant_id,
        metadata={"revoked_count": revoked, "reason": "sign_out_all"},
    )

    return JSONResponse(status_code=200, content={"revoked": revoked})


# =============================================================================
# GUARDIAN PORTAL — OTP-only auth (unauthenticated flows)
# =============================================================================


class GuardianOTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15, description="Guardian's registered mobile number")
    tenant_id: str = Field(..., description="Institution tenant ID")


class GuardianVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=6, max_length=6)
    tenant_id: str = Field(...)


@router.post("/guardian/request-otp")
async def guardian_request_otp(request: Request, body: GuardianOTPRequest) -> JSONResponse:
    """
    Send a 6-digit OTP to a registered guardian's mobile number.

    Looks up the guardian by phone + tenant. If not found, returns 200 (no enumeration).
    Rate-limited to 3 OTP requests per hour per phone number.
    """
    phone = body.phone.strip().replace(" ", "").replace("-", "")

    if not RateLimiter.check(f"gotp:{phone}", max_requests=3, window_seconds=3600):
        return _err(429, "Too many OTP requests. Try again in 1 hour.", "ERR_RATE_LIMITED")

    rows = execute_system_query(
        """SELECT u.id AS guardian_id, gs.student_id, gs.student_name
           FROM users u
           JOIN guardian_student_links gs ON gs.guardian_id = u.id
           WHERE u.phone = %s AND u.tenant_id = %s AND u.is_deleted = FALSE
           LIMIT 1""",
        (phone, body.tenant_id),
    )

    if rows:
        row = rows[0]
        try:
            otp = GuardianOTPManager.generate(phone, row["student_id"], body.tenant_id)
            from server.core.notifications.service import NotificationService
            NotificationService.send(
                channel="sms",
                recipient_id=row["guardian_id"],
                template_key="auth.guardian_otp",
                tenant_id=body.tenant_id,
                context={"otp": otp, "student_name": row.get("student_name", "your ward")},
            )
        except Exception:
            logger.exception("guardian_request_otp: OTP/notification error for phone %s", phone[-4:])

    return JSONResponse(status_code=200, content={
        "message": "If your number is registered, an OTP has been sent."
    })


@router.post("/guardian/verify-otp")
async def guardian_verify_otp(request: Request, body: GuardianVerifyRequest) -> JSONResponse:
    """
    Verify guardian OTP and issue a scoped session token.

    On success, returns a session token valid for 4 hours with PARENT role,
    plus the linked student's info for rendering the portal.
    """
    phone = body.phone.strip().replace(" ", "").replace("-", "")

    if not RateLimiter.check(f"gotp_verify:{phone}", max_requests=5, window_seconds=600):
        return _err(429, "Too many OTP attempts.", "ERR_RATE_LIMITED")

    result = GuardianOTPManager.verify_and_consume(phone, body.otp)
    if not result:
        return _err(400, "Invalid or expired OTP.", "ERR_INVALID_OTP")

    student_id = result["student_id"]
    tenant_id = result["tenant_id"]

    # Look up guardian user record to create a session
    rows = execute_system_query(
        "SELECT id, display_name FROM users WHERE phone = %s AND tenant_id = %s AND is_deleted = FALSE LIMIT 1",
        (phone, tenant_id),
    )
    if not rows:
        return _err(401, "Guardian account not found.", "ERR_AUTH_FAILED")

    guardian = rows[0]

    # Fetch student summary for the portal response
    student_rows = execute_system_query(
        "SELECT id, display_name, enrollment_number FROM users WHERE id = %s AND tenant_id = %s LIMIT 1",
        (student_id, tenant_id),
    )
    student = student_rows[0] if student_rows else {"display_name": "Student", "enrollment_number": ""}

    token = SessionManager.create_session(
        user_id=guardian["id"],
        role=Role.PARENT.value,
        tenant_id=tenant_id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
        expires_in=timedelta(hours=4),
    )

    AuditLog.log(
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=guardian["id"],
        actor_type="guardian",
        tenant_id=tenant_id,
        metadata={"channel": "otp", "student_id": student_id},
    )

    return JSONResponse(status_code=200, content={
        "token": token,
        "role": "PARENT",
        "guardian_name": guardian.get("display_name", ""),
        "student": {
            "student_id": student_id,
            "name": student.get("display_name", ""),
            "enrollment_number": student.get("enrollment_number", ""),
        },
        "tenant_id": tenant_id,
    })
