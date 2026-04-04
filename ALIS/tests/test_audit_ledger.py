"""
Tests for ALIS Immutable Audit Ledger (E00-S02)

Run:  PYTHONPATH=. pytest tests/test_audit_ledger.py -v
"""

import sys
import os
import importlib.util
import hashlib
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Direct-load server/core/audit.py inside a controlled fixture
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_AUDIT_PATH = os.path.join(_PROJECT_ROOT, "server", "core", "audit.py")

@pytest.fixture(scope="module", autouse=True)
def audit_context():
    """Load audit module only for this module's scope."""
    _orig_modules = sys.modules.copy()
    try:
        spec = importlib.util.spec_from_file_location("server.core.audit", _AUDIT_PATH)
        audit_mod = importlib.util.module_from_spec(spec)
        sys.modules["server.core.audit"] = audit_mod
        spec.loader.exec_module(audit_mod)
        
        # Inject symbols into the module's global namespace safely
        globals()["AuditAction"] = audit_mod.AuditAction
        globals()["AuditEntry"] = audit_mod.AuditEntry
        globals()["AuditLedger"] = audit_mod.AuditLedger
        globals()["AuditLog"] = audit_mod.AuditLog
        globals()["compute_entry_hash"] = audit_mod.compute_entry_hash
        globals()["_canonical_payload"] = audit_mod._canonical_payload
        globals()["_tenant_lock_key"] = audit_mod._tenant_lock_key
        globals()["_rows_to_csv"] = audit_mod._rows_to_csv
        globals()["_rows_to_json"] = audit_mod._rows_to_json
        
        yield
    finally:
        # Restore sys.modules
        for mod_name in list(sys.modules.keys()):
            if mod_name not in _orig_modules:
                del sys.modules[mod_name]
            else:
                sys.modules[mod_name] = _orig_modules[mod_name]




# ============================================================================
# 1. HASH COMPUTATION TESTS
# ============================================================================

class TestHashComputation:
    """Tests for deterministic hashing logic (no DB required)."""

    def test_canonical_payload_is_deterministic(self):
        """Same input dict produces same canonical string regardless of key order."""
        d1 = {"b": 2, "a": 1, "c": 3}
        d2 = {"a": 1, "c": 3, "b": 2}
        assert _canonical_payload(d1) == _canonical_payload(d2)

    def test_canonical_payload_handles_datetime(self):
        """Datetimes are serialised to ISO format."""
        ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = _canonical_payload({"time": ts})
        assert "2025-01-15T12:00:00" in result

    def test_compute_entry_hash_genesis(self):
        """Genesis entry (no previous_hash) produces a valid SHA-256 hex."""
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        h = compute_entry_hash(
            previous_hash=None,
            tenant_id="tenant_1",
            actor_id="user_1",
            actor_role="admin",
            action="create",
            entity_type="student",
            entity_id="s001",
            timestamp=ts,
        )
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)

    def test_compute_entry_hash_chaining(self):
        """Hash changes when previous_hash is provided vs. None."""
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        kwargs = dict(
            tenant_id="t1", actor_id="u1", actor_role="admin",
            action="create", entity_type="x", entity_id="x1", timestamp=ts,
        )
        h_genesis = compute_entry_hash(previous_hash=None, **kwargs)
        h_chained = compute_entry_hash(previous_hash="abc123", **kwargs)
        assert h_genesis != h_chained

    def test_compute_entry_hash_deterministic(self):
        """Same inputs always produce the same hash."""
        ts = datetime(2025, 6, 1, 10, 30, 0, tzinfo=timezone.utc)
        kwargs = dict(
            previous_hash="prev",
            tenant_id="t1", actor_id="u1", actor_role="staff",
            action="update", entity_type="grade", entity_id="g1",
            timestamp=ts, metadata={"score": 95},
        )
        h1 = compute_entry_hash(**kwargs)
        h2 = compute_entry_hash(**kwargs)
        assert h1 == h2


# ============================================================================
# 2. TENANT LOCK KEY TESTS
# ============================================================================

class TestTenantLockKey:
    def test_deterministic(self):
        assert _tenant_lock_key("tenant_a") == _tenant_lock_key("tenant_a")

    def test_different_tenants(self):
        assert _tenant_lock_key("tenant_a") != _tenant_lock_key("tenant_b")


# ============================================================================
# 3. AUDIT ENTRY IMMUTABILITY
# ============================================================================

class TestAuditEntry:
    def test_frozen_dataclass(self):
        """AuditEntry is immutable after creation."""
        entry = AuditEntry(
            id="1", tenant_id="t1", actor_id="u1", actor_role="admin",
            action="create", entity_type="x", entity_id="x1",
            hash="abc123",
        )
        with pytest.raises(AttributeError):
            entry.hash = "tampered"  # type: ignore[misc]

    def test_defaults(self):
        entry = AuditEntry()
        assert entry.tenant_id == ""
        assert entry.previous_hash is None
        assert entry.hash == ""


# ============================================================================
# 4. BACKWARD COMPATIBILITY
# ============================================================================

class TestBackwardCompatibility:
    """Ensure old AuditLog callers don't break."""

    def test_alias_exists(self):
        """AuditLog is an alias for AuditLedger."""
        assert AuditLog is AuditLedger

    def test_old_api_signature_accepted(self):
        """Old callers pass actor_type, action_detail, success, etc."""
        # Mock dependencies using patch.dict to avoid poisoning the rest of the test suite
        from unittest.mock import patch

        mock_psycopg2_extras = MagicMock()
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            None,                       # No previous hash (genesis)
            {"id": 42},                 # RETURNING id
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_db_service = MagicMock()
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_ctx.__exit__ = MagicMock(return_value=False)
        mock_db_service.get_db_connection.return_value = mock_db_ctx
        mock_db_service.get_tenant_db_connection.return_value = mock_db_ctx

        # Mock tenant context resolution to avoid importing security
        mock_security = MagicMock()
        mock_security.get_current_tenant_id.return_value = "test_tenant"

        modules_to_patch = {
            "psycopg2": MagicMock(),
            "psycopg2.extras": mock_psycopg2_extras,
            "server.db_service": mock_db_service,
            "server.core.security": mock_security,
        }

        with patch.dict(sys.modules, modules_to_patch):
            # This is how existing callers invoke the method:
            entry = AuditLog.log(
                action=AuditAction.LOCK_TRIGGERED,
                actor_id="admin-1",
                actor_type="human",          # OLD kwarg
                actor_role="super_admin",    # NEW kwarg (takes priority)
                entity_type="lockdown",
                entity_id="evt-123",
                action_detail="Lockdown ACTIVATED: breach",  # OLD kwarg
                success=True,
                metadata={"reason": "breach"},
            )

            assert entry.actor_role == "super_admin"
            assert entry.id == "42"


# ============================================================================
# 5. EXPORT HELPERS
# ============================================================================

class TestExportHelpers:
    def _sample_rows(self):
        return [
            {
                "id": 1,
                "tenant_id": "t1",
                "actor_id": "u1",
                "actor_role": "admin",
                "action": "create",
                "entity_type": "student",
                "entity_id": "s001",
                "metadata": {"field": "value"},
                "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "previous_hash": None,
                "hash": "aaa",
            },
            {
                "id": 2,
                "tenant_id": "t1",
                "actor_id": "u2",
                "actor_role": "staff",
                "action": "update",
                "entity_type": "student",
                "entity_id": "s001",
                "metadata": None,
                "timestamp": datetime(2025, 1, 2, tzinfo=timezone.utc),
                "previous_hash": "aaa",
                "hash": "bbb",
            },
        ]

    def test_json_export(self):
        output = _rows_to_json(self._sample_rows())
        parsed = json.loads(output)
        assert len(parsed) == 2
        assert parsed[0]["actor_id"] == "u1"

    def test_csv_export(self):
        output = _rows_to_csv(self._sample_rows())
        lines = output.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "tenant_id" in lines[0]
        assert "u1" in lines[1]


# ============================================================================
# 6. VERIFY CHAIN INTEGRITY (mocked DB)
# ============================================================================

class TestVerifyChainIntegrity:
    """Test verify_chain_integrity with mocked DB rows."""

    @pytest.fixture(autouse=True)
    def _mock_db_service(self):
        """Mock server.db_service and restore sys.modules after test."""
        from unittest.mock import patch
        self.mock_db_service = MagicMock()
        
        # Capture current modules to prevent permanent poisoning
        with patch.dict(sys.modules, {"server.db_service": self.mock_db_service}):
            yield

    def test_empty_ledger_is_valid(self):
        self.mock_db_service.execute_system_query.return_value = []
        result = AuditLedger.verify_chain_integrity("t1")
        assert result["valid"] is True
        assert result["total_entries"] == 0

    def test_valid_chain(self):
        """Build a real 3-entry chain and verify it passes."""
        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        ts3 = datetime(2025, 1, 3, tzinfo=timezone.utc)

        base = dict(tenant_id="t1", actor_id="u1", actor_role="admin",
                    entity_type="x", entity_id="x1")

        h1 = compute_entry_hash(previous_hash=None, action="create",
                                timestamp=ts1, **base)
        h2 = compute_entry_hash(previous_hash=h1, action="update",
                                timestamp=ts2, **base)
        h3 = compute_entry_hash(previous_hash=h2, action="delete",
                                timestamp=ts3, **base)

        self.mock_db_service.execute_system_query.return_value = [
            {**base, "id": 1, "action": "create", "metadata": None,
             "timestamp": ts1, "previous_hash": None, "hash": h1},
            {**base, "id": 2, "action": "update", "metadata": None,
             "timestamp": ts2, "previous_hash": h1, "hash": h2},
            {**base, "id": 3, "action": "delete", "metadata": None,
             "timestamp": ts3, "previous_hash": h2, "hash": h3},
        ]

        result = AuditLedger.verify_chain_integrity("t1")
        assert result["valid"] is True
        assert result["total_entries"] == 3

    def test_tampered_hash_detected(self):
        """If a stored hash is tampered, verification must fail."""
        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        base = dict(tenant_id="t1", actor_id="u1", actor_role="admin",
                    entity_type="x", entity_id="x1")

        self.mock_db_service.execute_system_query.return_value = [
            {**base, "id": 1, "action": "create", "metadata": None,
             "timestamp": ts1, "previous_hash": None,
             "hash": "aaaa_tampered_hash_aaaa"},
        ]

        result = AuditLedger.verify_chain_integrity("t1")
        assert result["valid"] is False
        assert result["first_invalid_id"] == 1

    def test_broken_chain_link_detected(self):
        """If previous_hash does not match, verification must fail."""
        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        base = dict(tenant_id="t1", actor_id="u1", actor_role="admin",
                    entity_type="x", entity_id="x1")

        h1 = compute_entry_hash(previous_hash=None, action="create",
                                timestamp=ts1, **base)
        # Entry 2 claims a wrong previous_hash
        h2 = compute_entry_hash(previous_hash="WRONG", action="update",
                                timestamp=ts2, **base)

        self.mock_db_service.execute_system_query.return_value = [
            {**base, "id": 1, "action": "create", "metadata": None,
             "timestamp": ts1, "previous_hash": None, "hash": h1},
            {**base, "id": 2, "action": "update", "metadata": None,
             "timestamp": ts2, "previous_hash": "WRONG", "hash": h2},
        ]

        result = AuditLedger.verify_chain_integrity("t1")
        assert result["valid"] is False
        assert result["first_invalid_id"] == 2

