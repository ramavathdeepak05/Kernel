import sys
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

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
