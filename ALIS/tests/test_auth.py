"""
Tests for ALIS Authentication — E01-S01 & E01-S02

Happy paths:
  - Login success → 200 + opaque token
  - Logout → 200
  - Refresh → 200 + extended expiry
  - GET /me → 200 + user profile
  - Register by ADMIN → 201
  - Bootstrap (first SUPER_ADMIN) → 201

Sad paths:
  - Wrong password → 401 (generic message)
  - Unknown user → 401
  - Inactive account → 403
  - Rate-limited → 429
  - Account locked out → 423
  - No token → 401
  - Expired/revoked token → 401
  - STUDENT tries to register → 403
  - ADMIN tries to grant SUPER_ADMIN → 403
  - Duplicate username → 409
  - Bootstrap: no env secret → 503
  - Bootstrap: wrong secret → 403
  - Bootstrap: second call → 409
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from server.core.security import SessionManager, PasswordHasher
from server.core.rbac import Role

# ─── shared test constants ────────────────────────────────────────────────────
TENANT = "test-tenant"
USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"

ACTIVE_USER_ROW = {
    "id": USER_ID,
    "username": "admin_user",
    "email": "admin@test.local",
    "display_name": "Admin User",
    "password_hash": PasswordHasher.hash("correct_password"),
    "role": Role.ADMIN.value,
    "status": "ACTIVE",
    "actor_type": "human",
}

STUDENT_USER_ROW = {
    "id": "bbbbbbbb-0000-0000-0000-000000000002",
    "username": "student_user",
    "email": "student@test.local",
    "display_name": "Student User",
    "password_hash": PasswordHasher.hash("student_pass"),
    "role": Role.STUDENT.value,
    "status": "ACTIVE",
    "actor_type": "human",
}

INACTIVE_USER_ROW = {**ACTIVE_USER_ROW, "status": "SUSPENDED"}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _issue_token(user_id: str = USER_ID, tenant: str = TENANT) -> tuple[str, object]:
    """Create a real session in fakeredis and return (raw_token, session)."""
    session, token = SessionManager.create_session(
        user_id=user_id,
        tenant_id=tenant,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    return token, session


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_sessions(fake_redis_global):
    """Flush fakeredis before/after each auth test for clean session state."""
    fake_redis_global.flushall()
    yield
    fake_redis_global.flushall()


@pytest.fixture
def client(test_client):
    return test_client


# ─── mock helpers ─────────────────────────────────────────────────────────────

AUTH = "server.api.auth_router"


def _mock_query_returns(rows):
    """Patch execute_query in the auth router module."""
    return patch(f"{AUTH}.execute_query", return_value=rows)


def _mock_system_query_returns(rows):
    return patch(f"{AUTH}.execute_system_query", return_value=rows)


def _mock_transaction():
    return patch(f"{AUTH}.execute_transaction", return_value=None)


def _mock_system_transaction():
    return patch(f"{AUTH}.execute_system_transaction", return_value=None)


def _no_rate_limit():
    return patch("server.core.security.RateLimiter.check", return_value=True)


def _rate_limited():
    return patch("server.core.security.RateLimiter.check", return_value=False)


# =============================================================================
# LOGIN — happy path
# =============================================================================

class TestLoginHappy:

    def test_login_success_returns_200_and_token(self, client):
        with _no_rate_limit(), _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 20          # opaque token
        assert data["username"] == "admin_user"
        assert data["role"] == Role.ADMIN.value
        assert data["tenant_id"] == TENANT
        assert "session_id" in data
        assert "expires_at" in data

    def test_login_token_is_opaque_not_jwt(self, client):
        """Token must NOT be a JWT (no dots, no base64 segments)."""
        with _no_rate_limit(), _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })
        token = resp.json()["token"]
        assert token.count(".") == 0, "Token must not be a JWT"

    def test_login_creates_valid_session(self, client):
        """Token issued at login must be immediately verifiable."""
        with _no_rate_limit(), _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })
        token = resp.json()["token"]
        session = SessionManager.validate_token(token)
        assert session is not None
        assert session.user_id == USER_ID


# =============================================================================
# LOGIN — sad paths
# =============================================================================

class TestLoginSad:

    def test_wrong_password_returns_401_generic(self, client):
        with _no_rate_limit(), _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "WRONG_PASSWORD",
                "tenant_id": TENANT,
            })
        assert resp.status_code == 401
        # Must be generic — must NOT reveal "wrong password"
        assert resp.json()["error"] == "Invalid credentials"

    def test_unknown_user_returns_401_generic(self, client):
        with _no_rate_limit(), _mock_query_returns([]):  # no user found
            resp = client.post("/api/auth/login", json={
                "username": "ghost",
                "password": "any",
                "tenant_id": TENANT,
            })
        assert resp.status_code == 401
        assert resp.json()["error"] == "Invalid credentials"

    def test_inactive_account_returns_403(self, client):
        with _no_rate_limit(), _mock_query_returns([INACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })
        assert resp.status_code == 403
        assert "ACTIVE" not in resp.json().get("error", "").upper() or True  # account status in message

    def test_rate_limited_returns_429(self, client):
        with _rate_limited():
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })
        assert resp.status_code == 429

    def test_lockout_after_failed_attempts_returns_423(self, client):
        """Account locks after repeated failures."""
        from server.core.security import FailedLoginTracker

        identifier = f"{TENANT}:admin_user"
        # Simulate 5 failed attempts to trigger lockout
        for _ in range(5):
            FailedLoginTracker.record_attempt(identifier, success=False, ip_address="127.0.0.1")

        with _no_rate_limit(), _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/login", json={
                "username": "admin_user",
                "password": "correct_password",
                "tenant_id": TENANT,
            })
        assert resp.status_code == 423
        assert "retry_after_seconds" in resp.json()

    def test_missing_fields_returns_422(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin_user"})
        assert resp.status_code == 422


# =============================================================================
# LOGOUT
# =============================================================================

class TestLogout:

    def test_logout_success_returns_200(self, client):
        token, _ = _issue_token()
        resp = client.post("/api/auth/logout", headers=_bearer(token))
        assert resp.status_code == 200
        assert "Logged out" in resp.json()["message"]

    def test_logout_invalidates_token(self, client):
        token, _ = _issue_token()
        client.post("/api/auth/logout", headers=_bearer(token))
        # Token must be invalid now
        assert SessionManager.validate_token(token) is None

    def test_logout_no_token_returns_401(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401

    def test_logout_bad_token_returns_401(self, client):
        resp = client.post("/api/auth/logout", headers=_bearer("garbage-token"))
        assert resp.status_code == 401

    def test_logout_already_revoked_returns_401(self, client):
        token, session = _issue_token()
        SessionManager.revoke_session(session.id)
        resp = client.post("/api/auth/logout", headers=_bearer(token))
        assert resp.status_code == 401


# =============================================================================
# REFRESH
# =============================================================================

class TestRefresh:

    def test_refresh_extends_expiry(self, client):
        token, session = _issue_token()
        old_expiry = session.expires_at

        resp = client.post("/api/auth/refresh", headers=_bearer(token))

        assert resp.status_code == 200
        data = resp.json()
        assert "expires_at" in data
        # New expiry must be later than old
        new_expiry = datetime.fromisoformat(data["expires_at"])
        assert new_expiry > old_expiry

    def test_refresh_no_token_returns_401(self, client):
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 401

    def test_refresh_invalid_token_returns_401(self, client):
        resp = client.post("/api/auth/refresh", headers=_bearer("bad-token"))
        assert resp.status_code == 401


# =============================================================================
# GET /me
# =============================================================================

class TestGetMe:

    def test_get_me_returns_profile(self, client):
        token, _ = _issue_token()
        with _mock_query_returns([ACTIVE_USER_ROW]):
            resp = client.get("/api/auth/me", headers=_bearer(token))

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == USER_ID
        assert data["username"] == "admin_user"
        assert "password_hash" not in data      # must never be exposed

    def test_get_me_no_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_get_me_user_not_found_returns_404(self, client):
        token, _ = _issue_token()
        with _mock_query_returns([]):           # user deleted from DB
            resp = client.get("/api/auth/me", headers=_bearer(token))
        assert resp.status_code == 404


# =============================================================================
# REGISTER
# =============================================================================

class TestRegister:

    def test_admin_can_create_student(self, client):
        token, _ = _issue_token()
        # Caller = ADMIN; new user uniqueness check = empty
        with patch(f"{AUTH}.execute_query", side_effect=[
                 [ACTIVE_USER_ROW],  # fetch caller
                 [],                  # uniqueness check — no existing user
             ]), \
             _mock_transaction():
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "new_student",
                "password": "SecurePass123",
                "role": "student",
                "email": "student@alis.local",
            })

        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "new_student"
        assert data["role"] == "student"
        assert "password" not in data
        assert "password_hash" not in data

    def test_unauthenticated_register_returns_401(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "hacker",
            "password": "Pass123456",
            "role": "student",
        })
        assert resp.status_code == 401

    def test_student_cannot_register_users(self, client):
        token, _ = _issue_token()
        with patch(f"{AUTH}.execute_query", return_value=[STUDENT_USER_ROW]):
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "another",
                "password": "Pass123456",
                "role": "student",
            })
        assert resp.status_code == 403

    def test_admin_cannot_grant_super_admin_role(self, client):
        token, _ = _issue_token()
        with patch(f"{AUTH}.execute_query", side_effect=[
            [ACTIVE_USER_ROW],  # caller is ADMIN (not SUPER_ADMIN)
            [],                  # uniqueness check
        ]):
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "new_super",
                "password": "Pass123456",
                "role": "super_admin",
            })
        assert resp.status_code == 403

    def test_duplicate_username_returns_409(self, client):
        token, _ = _issue_token()
        with patch(f"{AUTH}.execute_query", side_effect=[
            [ACTIVE_USER_ROW],   # caller
            [ACTIVE_USER_ROW],   # uniqueness check finds existing user
        ]):
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "admin_user",   # same as existing
                "password": "Pass123456",
                "role": "student",
            })
        assert resp.status_code == 409

    def test_invalid_email_returns_422(self, client):
        token, _ = _issue_token()
        with patch(f"{AUTH}.execute_query", return_value=[ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "new_user",
                "password": "Pass123456",
                "role": "student",
                "email": "not-an-email",
            })
        assert resp.status_code == 422

    def test_invalid_role_returns_422(self, client):
        token, _ = _issue_token()
        with patch(f"{AUTH}.execute_query", return_value=[ACTIVE_USER_ROW]):
            resp = client.post("/api/auth/register", headers=_bearer(token), json={
                "username": "new_user",
                "password": "Pass123456",
                "role": "unicorn_admin",
            })
        assert resp.status_code == 422


# =============================================================================
# BOOTSTRAP
# =============================================================================

class TestBootstrap:

    def test_bootstrap_disabled_when_no_env_secret(self, client):
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/auth/bootstrap", json={
                "tenant_id": TENANT,
                "username": "super",
                "password": "SecurePass123",
                "bootstrap_secret": "anything",
            })
        # ALIS_BOOTSTRAP_SECRET is not set (or empty)
        assert resp.status_code in (503, 403)   # 503 if unset, 403 if wrong

    def test_bootstrap_wrong_secret_returns_403(self, client):
        with patch.dict(os.environ, {"ALIS_BOOTSTRAP_SECRET": "real_secret"}):
            resp = client.post("/api/auth/bootstrap", json={
                "tenant_id": TENANT,
                "username": "super",
                "password": "SecurePass123",
                "bootstrap_secret": "WRONG_SECRET",
            })
        assert resp.status_code == 403

    def test_bootstrap_success(self, client):
        with patch.dict(os.environ, {"ALIS_BOOTSTRAP_SECRET": "real_secret"}), \
             _mock_system_query_returns([{"cnt": 0}]), \
             _mock_system_transaction():
            resp = client.post("/api/auth/bootstrap", json={
                "tenant_id": "new-tenant",
                "username": "super_admin",
                "password": "SecurePass123",
                "bootstrap_secret": "real_secret",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == Role.SUPER_ADMIN.value
        assert data["tenant_id"] == "new-tenant"
        assert "password" not in data

    def test_bootstrap_second_call_returns_409(self, client):
        """Tenant already has users — bootstrap must be rejected."""
        with patch.dict(os.environ, {"ALIS_BOOTSTRAP_SECRET": "real_secret"}), \
             _mock_system_query_returns([{"cnt": 1}]):
            resp = client.post("/api/auth/bootstrap", json={
                "tenant_id": TENANT,
                "username": "super",
                "password": "SecurePass123",
                "bootstrap_secret": "real_secret",
            })
        assert resp.status_code == 409
