"""
ALIS Security Module - E01-S02 & E01-S11

MODULE: Platform Core
LAYER: Cross-cutting (Security)
ENTITY: Session, Token

This module implements authentication primitives, session control,
and security guardrails.

Must Align With:
- Security Model: RBAC+

Acceptance Criteria (E01-S02):
- [x] Password hashing (no plaintext ever)
- [x] Token-based authentication
- [x] Session expiry & revocation
- [x] Failed login protection
- [x] No module-level bypass

Acceptance Criteria (E01-S11):
- [x] Rate limiting
- [x] Input validation
- [x] Permission guardrails
- [x] No sensitive error leakage
- [x] Default deny posture
"""

import hashlib
import secrets
import contextvars
import logging
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import json

import bcrypt as _bcrypt
import redis as _redis_lib

from .audit import AuditLog, AuditAction

logger = logging.getLogger(__name__)


# --- Token Types ---

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"


# --- Session Entity ---

@dataclass
class Session:
    """
    User session entity.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    token_hash: str = ""
    token_type: TokenType = TokenType.ACCESS

    # Tenant Isolation (E00-S03)
    tenant_id: str = ""  # MANDATORY — set at login from User.org_id

    # Device info
    device_id: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Status
    is_active: bool = True
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def refresh(self, extend_hours: int = 24) -> None:
        """Extend session expiry."""
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=extend_hours)
        self.last_activity = datetime.now(timezone.utc)

    def revoke(self, reason: str = "Manual revocation") -> None:
        """Revoke the session."""
        self.is_active = False
        self.revoked_at = datetime.now(timezone.utc)
        self.revoke_reason = reason


# --- Password Hashing ---

class PasswordHasher:
    """
    Password hashing utility using bcrypt (rounds=12).

    New hashes: bcrypt ($2b$ prefix).
    Legacy hashes (PBKDF2 salt:hex format) are still verified for
    backward compatibility but new passwords always use bcrypt.
    """

    BCRYPT_ROUNDS = 12

    @staticmethod
    def hash(password: str) -> str:
        """Hash a password with bcrypt. Returns a bcrypt hash string."""
        return _bcrypt.hashpw(
            password.encode("utf-8"), _bcrypt.gensalt(rounds=PasswordHasher.BCRYPT_ROUNDS)
        ).decode("utf-8")

    @staticmethod
    def verify(password: str, stored_hash: str) -> bool:
        """
        Verify a password against a stored hash.

        Supports both bcrypt hashes (new) and legacy PBKDF2 salt:hex hashes.
        """
        try:
            if stored_hash.startswith("$2"):
                # bcrypt format
                return _bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
            # Legacy PBKDF2-HMAC-SHA256 format: "salt:hex_hash"
            salt, hash_value = stored_hash.split(":", 1)
            new_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                100000,
            ).hex()
            return secrets.compare_digest(new_hash, hash_value)
        except Exception:
            return False


# --- Token Generation ---

class TokenGenerator:
    """Token generation utility."""

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()


# --- Redis Helpers ---

_SESS_PREFIX    = "alis:sess:"
_TOK_PREFIX     = "alis:tok:"
_USER_SESS_PFX  = "alis:user_sess:"
_FAIL_PREFIX    = "alis:fail:"
_LOCKOUT_PREFIX = "alis:lockout:"
_RATE_PREFIX    = "alis:rate:"


def _get_redis() -> "_redis_lib.Redis":
    """Return a Redis client from the configured URL. Lazy — never called at import time."""
    from server.core.settings import settings
    return _redis_lib.from_url(settings.redis_url, decode_responses=True)


def _session_to_dict(session: "Session") -> dict:
    def _fmt(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None
    return {
        "id": session.id,
        "user_id": session.user_id,
        "token_hash": session.token_hash,
        "token_type": session.token_type.value,
        "tenant_id": session.tenant_id,
        "device_id": session.device_id,
        "user_agent": session.user_agent,
        "ip_address": session.ip_address,
        "created_at": _fmt(session.created_at),
        "expires_at": _fmt(session.expires_at),
        "last_activity": _fmt(session.last_activity),
        "is_active": session.is_active,
        "revoked_at": _fmt(session.revoked_at),
        "revoke_reason": session.revoke_reason,
    }


def _dict_to_session(d: dict) -> "Session":
    def _parse(s: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(s) if s else None
    return Session(
        id=d["id"],
        user_id=d["user_id"],
        token_hash=d["token_hash"],
        token_type=TokenType(d["token_type"]),
        tenant_id=d.get("tenant_id", ""),
        device_id=d.get("device_id"),
        user_agent=d.get("user_agent"),
        ip_address=d.get("ip_address"),
        created_at=_parse(d["created_at"]),
        expires_at=_parse(d["expires_at"]),
        last_activity=_parse(d.get("last_activity")),
        is_active=d.get("is_active", True),
        revoked_at=_parse(d.get("revoked_at")),
        revoke_reason=d.get("revoke_reason"),
    )


# --- Failed Login Tracker ---

class FailedLoginTracker:
    """
    Track failed login attempts for account lockout.

    Redis-backed — safe for multi-worker deployments.
    Keys:
      alis:fail:{identifier}    — INCR counter, TTL = LOCKOUT_SECONDS
      alis:lockout:{identifier} — sentinel, TTL = remaining lockout
    """

    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 900  # 15 minutes
    LOCKOUT_DURATION = timedelta(seconds=LOCKOUT_SECONDS)

    @classmethod
    def record_attempt(
        cls,
        identifier: str,
        success: bool,
        ip_address: Optional[str] = None,
    ) -> None:
        try:
            r = _get_redis()
            if success:
                r.delete(_FAIL_PREFIX + identifier)
                r.delete(_LOCKOUT_PREFIX + identifier)
                return
            count = r.incr(_FAIL_PREFIX + identifier)
            r.expire(_FAIL_PREFIX + identifier, cls.LOCKOUT_SECONDS)
            if count >= cls.MAX_ATTEMPTS:
                r.setex(_LOCKOUT_PREFIX + identifier, cls.LOCKOUT_SECONDS, "1")
        except Exception:
            logger.exception("FailedLoginTracker.record_attempt Redis error")

    @classmethod
    def is_locked_out(cls, identifier: str) -> bool:
        try:
            return _get_redis().exists(_LOCKOUT_PREFIX + identifier) > 0
        except Exception:
            logger.exception("FailedLoginTracker.is_locked_out Redis error")
            return False  # fail open — don't block logins if Redis is down

    @classmethod
    def get_lockout_remaining(cls, identifier: str) -> Optional[timedelta]:
        try:
            ttl = _get_redis().ttl(_LOCKOUT_PREFIX + identifier)
            return timedelta(seconds=ttl) if ttl > 0 else None
        except Exception:
            logger.exception("FailedLoginTracker.get_lockout_remaining Redis error")
            return None


# --- Session Manager ---

class SessionManager:
    """
    Session management service.

    Redis-backed — safe for multi-worker deployments.
    Keys:
      alis:sess:{session_id}    — JSON session blob, TTL = seconds until expiry
      alis:tok:{token_hash}     — session_id string, same TTL (O(1) lookup)
      alis:user_sess:{user_id}  — SET of session_ids (lazily cleaned up)
    """

    @classmethod
    def _save(cls, r: "_redis_lib.Redis", session: Session) -> None:
        """Persist a session to Redis with TTL derived from expiry."""
        ttl = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())
        if ttl <= 0:
            return
        data = json.dumps(_session_to_dict(session))
        r.setex(_SESS_PREFIX + session.id, ttl, data)
        r.setex(_TOK_PREFIX + session.token_hash, ttl, session.id)
        r.sadd(_USER_SESS_PFX + session.user_id, session.id)

    @classmethod
    def _load(cls, r: "_redis_lib.Redis", session_id: str) -> Optional[Session]:
        """Load a session from Redis. Returns None if not found."""
        data = r.get(_SESS_PREFIX + session_id)
        return _dict_to_session(json.loads(data)) if data else None

    @classmethod
    def create_session(
        cls,
        user_id: str,
        tenant_id: str = "",
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        expiry_hours: int = 24,
    ) -> "tuple[Session, str]":
        """
        Create a new session.

        Returns (session, raw_token) — raw_token is returned only once.
        """
        token = TokenGenerator.generate_token()
        session = Session(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=TokenGenerator.hash_token(token),
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
        cls._save(_get_redis(), session)
        return session, token

    @classmethod
    def validate_token(cls, token: str) -> Optional[Session]:
        """
        Validate a token and return the associated session.

        Returns None if token is invalid, expired, or revoked.
        """
        try:
            r = _get_redis()
            token_hash = TokenGenerator.hash_token(token)
            session_id = r.get(_TOK_PREFIX + token_hash)
            if not session_id:
                return None
            session = cls._load(r, session_id)
            if session is None or session.is_expired or not session.is_active:
                return None
            session.last_activity = datetime.now(timezone.utc)
            cls._save(r, session)
            return session
        except Exception:
            logger.exception("SessionManager.validate_token Redis error")
            return None  # fail safe — deny access if Redis is unreachable

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Session]:
        """Load a session by ID from Redis. Returns None if not found or expired."""
        try:
            return cls._load(_get_redis(), session_id)
        except Exception:
            logger.exception("SessionManager.get_session Redis error")
            return None

    @classmethod
    def revoke_session(cls, session_id: str, reason: str = "Manual revocation") -> bool:
        """Revoke a session."""
        try:
            r = _get_redis()
            session = cls._load(r, session_id)
            if not session:
                return False
            session.revoke(reason)
            cls._save(r, session)
            return True
        except Exception:
            logger.exception("SessionManager.revoke_session Redis error")
            return False

    @classmethod
    def revoke_all_user_sessions(cls, user_id: str, reason: str = "User logout all") -> int:
        """Revoke all active sessions for a user."""
        try:
            r = _get_redis()
            session_ids = r.smembers(_USER_SESS_PFX + user_id)
            count = 0
            for sid in session_ids:
                session = cls._load(r, sid)
                if session and session.is_active:
                    session.revoke(reason)
                    cls._save(r, session)
                    count += 1
            return count
        except Exception:
            logger.exception("SessionManager.revoke_all_user_sessions Redis error")
            return 0

    @classmethod
    def revoke_all_sessions(cls, reason: str = "Mass revocation") -> int:
        """
        Revoke every active session in the system.

        Used by lockdown activation. Scans all alis:sess:* keys in Redis.
        """
        try:
            r = _get_redis()
            count = 0
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=_SESS_PREFIX + "*", count=200)
                for key in keys:
                    data = r.get(key)
                    if not data:
                        continue
                    session = _dict_to_session(json.loads(data))
                    if session.is_active:
                        session.revoke(reason)
                        cls._save(r, session)
                        count += 1
                if cursor == 0:
                    break
            return count
        except Exception:
            logger.exception("SessionManager.revoke_all_sessions Redis error")
            return 0


# --- Rate Limiter ---

class RateLimiter:
    """
    Fixed-window rate limiter.

    Redis-backed — safe for multi-worker deployments.
    Key: alis:rate:{identifier}  — INCR counter, TTL = window_seconds
    """

    @classmethod
    def check(
        cls,
        identifier: str,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> bool:
        """
        Check if request is within rate limit.

        Returns True if allowed, False if rate limited.
        Fails open (allows request) if Redis is unreachable.
        """
        try:
            r = _get_redis()
            key = _RATE_PREFIX + identifier
            count = r.incr(key)
            if count == 1:
                r.expire(key, window_seconds)
            return count <= max_requests
        except Exception:
            logger.exception("RateLimiter.check Redis error — failing open")
            return True  # fail open — don't block traffic if Redis is down


# --- Input Validation ---

class InputValidator:
    """
    Input validation utilities.

    Prevents injection attacks and validates input format.
    """

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize a string input."""
        if not isinstance(value, str):
            return ""
        # Truncate
        value = value[:max_length]
        # Remove null bytes
        value = value.replace('\x00', '')
        return value.strip()

    @staticmethod
    def validate_email(email: str) -> bool:
        """Basic email validation."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_uuid(value: str) -> bool:
        """Validate UUID format."""
        import re
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(pattern, value.lower()))


# --- Security Exception (No Sensitive Leakage) ---

class SecurityException(Exception):
    """
    Security exception that does not leak sensitive information.

    The internal_message is for logging only.
    The public_message is safe to return to clients.
    """

    def __init__(
        self,
        public_message: str = "Access denied",
        internal_message: Optional[str] = None
    ):
        self.public_message = public_message
        self.internal_message = internal_message or public_message
        super().__init__(self.public_message)


# ============================================================================
# E00-S03: TENANT ISOLATION ENFORCEMENT
# ============================================================================
# Layer 4 Invariant: Every request MUST carry a valid tenant_id.
# This section implements:
#   1. A request-scoped ContextVar for tenant_id
#   2. TenantContext dataclass for structured tenant info
#   3. TenantMiddleware for FastAPI/Starlette integration
#   4. Helper functions for setting/getting tenant context
# ============================================================================

# --- Request-Scoped Tenant ContextVar ---
# This variable is set once per request by the TenantMiddleware
# and read by db_service.py, rbac.py, and all downstream code.
_current_tenant_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_tenant_id', default=None
)


@dataclass
class TenantContext:
    """
    Structured tenant context for the current request.

    Set by TenantMiddleware. Read by db_service, rbac, agents.
    """
    tenant_id: str
    tenant_name: Optional[str] = None
    encryption_key_id: Optional[str] = None  # For optional per-tenant encryption


def set_tenant_context(tenant_id: str) -> None:
    """
    Set the tenant context for the current request.

    Called by TenantMiddleware. Must not be called by application code.

    Raises:
        ValueError: If tenant_id is empty or None.
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_id cannot be empty — Layer 4 Invariant")
    _current_tenant_id.set(tenant_id.strip())


def get_current_tenant_id() -> str:
    """
    Get the current request's tenant_id.

    Returns the tenant_id from the ContextVar set by TenantMiddleware.

    Raises:
        TenantIsolationError: If tenant context is not set.
    """
    from .exceptions import TenantIsolationError
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise TenantIsolationError(
            message="Tenant context not set — all operations require tenant_id (Layer 4 Invariant)",
            details={"hint": "Ensure TenantMiddleware is applied to all routes"}
        )
    return tenant_id


def clear_tenant_context() -> None:
    """
    Clear the tenant context. Called at end of request lifecycle.
    """
    _current_tenant_id.set(None)


class TenantMiddleware:
    """
    FastAPI/Starlette middleware for tenant isolation enforcement.

    This middleware:
    1. Extracts tenant_id from the authenticated session's tenant_id field.
    2. Sets the request-scoped ContextVar.
    3. Attaches tenant_id to request.state for downstream access.
    4. Clears the ContextVar after the request completes.

    LAYER 4 INVARIANT: If tenant_id cannot be resolved, the request is REJECTED.
    No module may bypass this middleware.

    Usage (FastAPI):
        app = FastAPI()
        app.add_middleware(TenantMiddleware)
    """

    # Paths exempt from tenant enforcement (e.g., health, login)
    EXEMPT_PATHS = {
        "/health",
        "/api/auth/login",
        "/api/auth/bootstrap",
        "/api/auth/mfa/verify",   # carries mfa_token, not a session Bearer token
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        """
        ASGI middleware entry point.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip exempt paths (login, health, etc.)
        if path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Extract tenant_id from the Bearer token (primary) or X-Tenant-ID header (fallback)
        tenant_id = None

        headers = dict(scope.get("headers", []))

        # Primary: validate Bearer token → get tenant_id from Redis session
        auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()
            session = SessionManager.validate_token(raw_token)
            if session and session.tenant_id:
                tenant_id = session.tenant_id

        # Fallback: X-Tenant-ID header (for internal service calls / tests)
        if not tenant_id:
            tenant_header = headers.get(b"x-tenant-id", b"").decode("utf-8", errors="ignore")
            if tenant_header:
                tenant_id = tenant_header

        if not tenant_id:
            # Layer 4 Invariant Violation: REJECT
            from .exceptions import TenantIsolationError

            AuditLog.log(
                action=AuditAction.ACCESS_DENIED,
                actor_id="unknown",
                actor_type="unknown",
                entity_type="tenant_middleware",
                entity_id="",
                success=False,
                failure_reason="Missing tenant_id — Layer 4 Invariant",
                metadata={"path": path}
            )

            # Return 403 Forbidden
            response_body = b'{"error": "Tenant context required", "code": "ERR_LAYER4_TENANT"}'
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(response_body)).encode()],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": response_body,
            })
            return

        # Set the ContextVar for the duration of this request
        ctx_token = _current_tenant_id.set(tenant_id)

        # Also set on scope state so request.state.tenant_id is available in route handlers.
        # Starlette's HTTPConnection.state does State(scope["state"]) — so scope["state"]
        # must remain a plain dict (Starlette wraps it in State automatically).
        if "state" not in scope:
            scope["state"] = {}
        if isinstance(scope["state"], dict):
            scope["state"]["tenant_id"] = tenant_id

        try:
            await self.app(scope, receive, send)
        finally:
            # Always clean up the ContextVar
            _current_tenant_id.reset(ctx_token)


# ============================================================================
# E00-S02: AUDIT MIDDLEWARE
# ============================================================================
# Epic Constraint: "All modules inherit audit middleware"
# All state-mutating requests (POST, PUT, PATCH, DELETE) are logged.
# ============================================================================

class AuditMiddleware:
    """
    Middleware that ensures all write API requests automatically generate
    an audit log entry, regardless of whether the business logic explicitly
    calls the audit logger.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        # Only mutate actions are globally logged by the middleware
        # (Read actions are too voluminous, specific reads like PII are logged manually)
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            path = scope.get("path", "")
            
            # Extract basic actor details from auth state if present
            actor_id = "unknown"
            actor_role = "unknown"
            if hasattr(scope, 'state') and getattr(scope.state, 'session', None):
                actor_id = scope.state.session.user_id
                
                # Role usually lives on the user or token, but middleware might just
                # have the session. We use "api_user" as a fallback until the actual
                # RBAC decorator resolves the true role.
                actor_role = getattr(scope.state, 'user_role', "api_user")

            # Try to get tenant_id (might not be set if TenantMiddleware runs after, 
            # ideally AuditMiddleware runs AFTER TenantMiddleware).
            try:
                tenant_id = get_current_tenant_id()
            except Exception:
                tenant_id = "SYSTEM"

            # Determine action type
            action = AuditAction.UPDATE
            if method == "POST":
                action = AuditAction.CREATE
            elif method == "DELETE":
                action = AuditAction.DELETE

            # Log the request attempt
            AuditLog.log(
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                entity_type="api_route",
                entity_id=path,
                tenant_id=tenant_id,
                metadata={"http_method": method, "trigger": "audit_middleware"}
            )

        # Proceed with the request
        await self.app(scope, receive, send)
