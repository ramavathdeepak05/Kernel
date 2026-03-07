import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Exclude standalone verification scripts from pytest collection
collect_ignore = ["test_e03_s02_model_registry.py"]

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------
TEST_ORG_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_ID = "00000000-0000-0000-0000-000000000002"
TEST_TENANT = "TEST-TENANT-AUTOUSE"

@pytest.fixture(autouse=True, scope="module")
def isolate_sys_modules():
    """
    Saves and restores sys.modules for each test module.
    """
    _orig_modules = sys.modules.copy()
    yield
    # Restore modules after the module's tests are done
    for mod_name in list(sys.modules.keys()):
        if mod_name not in _orig_modules:
            del sys.modules[mod_name]
        else:
            sys.modules[mod_name] = _orig_modules[mod_name]

@pytest.fixture(autouse=True)
def mock_audit_log(request):
    """Globally mock AuditLog to use in-memory storage for all tests except audit-specific tests."""
    # Skip for tests that verify the actual AuditLog logic (like hashing and data integrity)
    if "test_audit_ledger" in request.module.__name__:
        yield
        return

    # We use patch because AuditLog might be imported as AuditLog or AuditLedger
    from server.core.audit import AuditLog, AuditEntry
    
    _entries = []
    
    def mock_log(**kwargs):
        from uuid import uuid4
        # Use real AuditEntry if possible, or a compatible object
        from server.core.audit import AuditEntry
        
        # Set attributes from kwargs
        action = kwargs.get("action")
        if hasattr(action, "value"): action = action.value
        
        entry = AuditEntry(
            id=str(uuid4()),
            tenant_id=kwargs.get("tenant_id", "TEST-TENANT"),
            actor_id=kwargs.get("actor_id", "system"),
            actor_role=kwargs.get("actor_role", "system"),
            action=action,
            entity_type=kwargs.get("entity_type", "unknown"),
            entity_id=kwargs.get("entity_id", "unknown"),
            metadata=kwargs.get("metadata", {}),
            timestamp=datetime.now(timezone.utc),
            previous_hash=None,
            hash="mock-hash"
        )
        
        # Backward compatibility for old tests using old attribute names
        # if any exist (e.g. action_detail)
        if "action_detail" in kwargs:
            object.__setattr__(entry, "action_detail", kwargs["action_detail"])
        else:
            object.__setattr__(entry, "action_detail", f"Mock {action}")
        
        _entries.append(entry)
        return entry

    def mock_query(**kwargs):
        results = []
        for entry in _entries:
            match = True
            for k, v in kwargs.items():
                val = getattr(entry, k, None)
                target = v.value if hasattr(v, "value") else v
                if val != target:
                    match = False
                    break
            if match:
                results.append(entry)
        return results

    with patch.object(AuditLog, 'log', side_effect=mock_log), \
         patch.object(AuditLog, 'query', side_effect=mock_query), \
         patch.object(AuditLog, 'log_state_transition', side_effect=mock_log): # Close enough for tests
        yield

@pytest.fixture(autouse=True)
def fake_redis_global():
    """
    Patch server.core.security._get_redis with a fakeredis server for all tests.
    Each test gets a fresh, empty in-memory Redis so security state never leaks.
    """
    import fakeredis
    server = fakeredis.FakeServer()
    fake_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    with patch("server.core.security._get_redis", return_value=fake_client):
        yield fake_client


@pytest.fixture(autouse=True)
def mock_db_global():
    """Globally mock database connections for all tests to prevent OperationalErrors."""
    with patch("server.db_service.get_db_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Default responses for common audit/security queries
        mock_cursor.fetchone.return_value = {"id": "1", "hash": "genesis-hash-mock"}
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [("id",), ("hash",)] # Mocked description for dict factory
        
        yield mock_get_conn

@pytest.fixture(autouse=True)
def set_default_tenant():
    """Ensure a default tenant context is set for all tests to avoid isolation errors."""
    try:
        from server.core.security import _current_tenant_id
        token = _current_tenant_id.set("TEST-TENANT-AUTOUSE")
        yield
        _current_tenant_id.reset(token)
    except (ImportError, AttributeError, Exception):
        yield

@pytest.fixture(autouse=True)
def cleanup_leaked_mocks():
    """Explicitly clean up known persistent mock targets if they leak."""
    yield
    to_clean = [
        "server.core.security",
        "server.core.rbac",
        "server.core.audit",
        "server.core.tenant_crypto",
        "server.db_service",
        "psycopg2",
        "psycopg2.extras"
    ]
    for mod in to_clean:
        if mod in sys.modules and isinstance(sys.modules[mod], MagicMock):
            del sys.modules[mod]


# =============================================================================
# P0-S07 — FastAPI TestClient + JWT Auth fixtures
# =============================================================================

def _make_jwt(
    user_id: str = TEST_USER_ID,
    org_id: str = TEST_ORG_ID,
    role: str = "SUPER_ADMIN",
    email: str = "test@alis.local",
    expires_minutes: int = 60,
) -> str:
    """Generate a real signed JWT for test requests."""
    from jose import jwt as jose_jwt
    from server.core.settings import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jose_jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest.fixture(scope="session")
def test_client():
    """
    FastAPI TestClient for the full ALIS app.
    DB and external services are mocked via the autouse fixtures above.
    Scope=session for speed — reuses the client across all tests.
    """
    from fastapi.testclient import TestClient
    from server.main import app
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture
def auth_headers():
    """
    Factory fixture: call it with a role to get Authorization headers.

    Usage:
        def test_something(auth_headers):
            headers = auth_headers("ADMIN")
            response = test_client.get("/api/...", headers=headers)
    """
    def _make(role: str = "SUPER_ADMIN", org_id: str = TEST_ORG_ID) -> dict:
        token = _make_jwt(role=role, org_id=org_id)
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
def super_admin_headers():
    """Pre-built headers for SUPER_ADMIN role (most common in tests)."""
    token = _make_jwt(role="SUPER_ADMIN")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers():
    """Pre-built headers for STUDENT role."""
    token = _make_jwt(role="STUDENT", user_id=str(uuid.uuid4()))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def counsellor_headers():
    """Pre-built headers for COUNSELLOR role."""
    token = _make_jwt(role="COUNSELLOR")
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# Integration test fixtures (require real Postgres — skipped in unit mode)
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: requires real Postgres + Redis")
    config.addinivalue_line("markers", "ai: requires Ollama running with models loaded")


@pytest.fixture(scope="session")
def real_db():
    """
    Real Postgres connection for integration tests.
    Skip automatically if no DB is reachable.

    Usage:
        @pytest.mark.integration
        def test_something(real_db):
            conn = real_db
            ...
    """
    pytest.importorskip("psycopg2")
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from server.core.settings import settings

    try:
        conn = psycopg2.connect(settings.db_url, cursor_factory=RealDictCursor)
        conn.autocommit = False
    except Exception as exc:
        pytest.skip(f"No Postgres available — skipping integration test: {exc}")
        return

    yield conn

    conn.rollback()
    conn.close()


@pytest.fixture
def db_transaction(real_db):
    """
    Wraps each integration test in a transaction that is rolled back after.
    Guarantees test isolation even against a real database.
    """
    real_db.execute(f"SET LOCAL alis.current_tenant = '{TEST_ORG_ID}'")
    yield real_db
    real_db.rollback()
