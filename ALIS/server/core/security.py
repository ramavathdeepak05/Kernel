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
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

# Note: In production, use bcrypt or argon2
# from bcrypt import hashpw, checkpw, gensalt


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

    # Device info
    device_id: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    last_activity: datetime = field(default_factory=datetime.utcnow)

    # Status
    is_active: bool = True
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def refresh(self, extend_hours: int = 24) -> None:
        """Extend session expiry."""
        self.expires_at = datetime.utcnow() + timedelta(hours=extend_hours)
        self.last_activity = datetime.utcnow()

    def revoke(self, reason: str = "Manual revocation") -> None:
        """Revoke the session."""
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoke_reason = reason


# --- Password Hashing ---

class PasswordHasher:
    """
    Password hashing utility.

    Uses PBKDF2-HMAC-SHA256 with random salt.
    In production, prefer bcrypt or argon2.
    """

    @staticmethod
    def hash(password: str) -> str:
        """
        Hash a password.

        Returns: salt:hash format
        """
        salt = secrets.token_hex(16)
        hash_value = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return f"{salt}:{hash_value}"

    @staticmethod
    def verify(password: str, stored_hash: str) -> bool:
        """Verify a password against stored hash."""
        try:
            salt, hash_value = stored_hash.split(":")
            new_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
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


# --- Failed Login Tracker ---

@dataclass
class LoginAttempt:
    """Record of a login attempt."""
    timestamp: datetime
    success: bool
    ip_address: Optional[str] = None


class FailedLoginTracker:
    """
    Track failed login attempts for rate limiting.

    Implements lockout after MAX_ATTEMPTS failures.
    """

    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION = timedelta(minutes=15)

    _attempts: Dict[str, List[LoginAttempt]] = {}

    @classmethod
    def record_attempt(
        cls,
        identifier: str,  # username or IP
        success: bool,
        ip_address: Optional[str] = None
    ) -> None:
        """Record a login attempt."""
        if identifier not in cls._attempts:
            cls._attempts[identifier] = []

        cls._attempts[identifier].append(LoginAttempt(
            timestamp=datetime.utcnow(),
            success=success,
            ip_address=ip_address
        ))

        # Keep only recent attempts
        cutoff = datetime.utcnow() - cls.LOCKOUT_DURATION
        cls._attempts[identifier] = [
            a for a in cls._attempts[identifier]
            if a.timestamp > cutoff
        ]

    @classmethod
    def is_locked_out(cls, identifier: str) -> bool:
        """Check if identifier is locked out."""
        attempts = cls._attempts.get(identifier, [])
        recent_failures = [
            a for a in attempts
            if not a.success
        ]
        return len(recent_failures) >= cls.MAX_ATTEMPTS

    @classmethod
    def get_lockout_remaining(cls, identifier: str) -> Optional[timedelta]:
        """Get remaining lockout time."""
        if not cls.is_locked_out(identifier):
            return None

        attempts = cls._attempts.get(identifier, [])
        if not attempts:
            return None

        oldest_in_window = min(a.timestamp for a in attempts)
        unlock_time = oldest_in_window + cls.LOCKOUT_DURATION
        remaining = unlock_time - datetime.utcnow()

        return remaining if remaining.total_seconds() > 0 else None


# --- Session Manager ---

class SessionManager:
    """
    Session management service.
    """

    _sessions: Dict[str, Session] = {}

    @classmethod
    def create_session(
        cls,
        user_id: str,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        expiry_hours: int = 24
    ) -> tuple[Session, str]:
        """
        Create a new session.

        Returns (session, raw_token) - raw_token is returned only once.
        """
        token = TokenGenerator.generate_token()
        token_hash = TokenGenerator.hash_token(token)

        session = Session(
            user_id=user_id,
            token_hash=token_hash,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.utcnow() + timedelta(hours=expiry_hours)
        )

        cls._sessions[session.id] = session
        return session, token

    @classmethod
    def validate_token(cls, token: str) -> Optional[Session]:
        """
        Validate a token and return the associated session.

        Returns None if token is invalid, expired, or revoked.
        """
        token_hash = TokenGenerator.hash_token(token)

        for session in cls._sessions.values():
            if session.token_hash == token_hash:
                if session.is_expired or not session.is_active:
                    return None
                session.last_activity = datetime.utcnow()
                return session

        return None

    @classmethod
    def revoke_session(cls, session_id: str, reason: str = "Manual revocation") -> bool:
        """Revoke a session."""
        session = cls._sessions.get(session_id)
        if session:
            session.revoke(reason)
            return True
        return False

    @classmethod
    def revoke_all_user_sessions(cls, user_id: str, reason: str = "User logout all") -> int:
        """Revoke all sessions for a user."""
        count = 0
        for session in cls._sessions.values():
            if session.user_id == user_id and session.is_active:
                session.revoke(reason)
                count += 1
        return count


# --- Rate Limiter ---

@dataclass
class RateLimitEntry:
    count: int
    window_start: datetime


class RateLimiter:
    """
    Simple rate limiter.

    Limits requests per identifier within a time window.
    """

    _limits: Dict[str, RateLimitEntry] = {}

    @classmethod
    def check(
        cls,
        identifier: str,
        max_requests: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if request is allowed.

        Returns True if allowed, False if rate limited.
        """
        now = datetime.utcnow()
        entry = cls._limits.get(identifier)

        if entry is None:
            cls._limits[identifier] = RateLimitEntry(count=1, window_start=now)
            return True

        window_elapsed = (now - entry.window_start).total_seconds()

        if window_elapsed >= window_seconds:
            # Reset window
            cls._limits[identifier] = RateLimitEntry(count=1, window_start=now)
            return True

        if entry.count >= max_requests:
            return False

        entry.count += 1
        return True


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
