"""
Tests for ALIS Field-Level Change Tracking (E00-S08)

Run:  PYTHONPATH=. pytest tests/test_field_diff_tracking.py -v

Tests cover:
  1. Field diff computation (pure logic, no DB)
  2. Encryption/decryption of previous values
  3. Tracked entity registry
  4. compute_and_log_field_diffs (mocked DB)
  5. get_decrypted_field_diffs (mocked DB)
  6. Edge cases (no changes, untracked entity, empty data)
"""

import sys
import os
import importlib.util
import json
import base64
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

# ---------------------------------------------------------------------------
# Direct-load modules without triggering core/__init__.py
# (same pattern as test_audit_ledger.py)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 1. Load exceptions.py
_EXCEPTIONS_PATH = os.path.join(_PROJECT_ROOT, "server", "core", "exceptions.py")
spec_exc = importlib.util.spec_from_file_location("server.core.exceptions", _EXCEPTIONS_PATH)
exceptions_mod = importlib.util.module_from_spec(spec_exc)
sys.modules["server.core.exceptions"] = exceptions_mod
spec_exc.loader.exec_module(exceptions_mod)

DiffTrackingError = exceptions_mod.DiffTrackingError
TenantIsolationError = exceptions_mod.TenantIsolationError

# 2. Load audit.py
_AUDIT_PATH = os.path.join(_PROJECT_ROOT, "server", "core", "audit.py")
spec_audit = importlib.util.spec_from_file_location("server.core.audit", _AUDIT_PATH)
audit_mod = importlib.util.module_from_spec(spec_audit)
sys.modules["server.core.audit"] = audit_mod
spec_audit.loader.exec_module(audit_mod)

AuditAction = audit_mod.AuditAction
AuditEntry = audit_mod.AuditEntry
AuditLedger = audit_mod.AuditLedger
compute_entry_hash = audit_mod.compute_entry_hash

# 3. Load tenant_crypto.py (mock its audit import)
_CRYPTO_PATH = os.path.join(_PROJECT_ROOT, "server", "core", "tenant_crypto.py")
spec_crypto = importlib.util.spec_from_file_location("server.core.tenant_crypto", _CRYPTO_PATH)
crypto_mod = importlib.util.module_from_spec(spec_crypto)
sys.modules["server.core.tenant_crypto"] = crypto_mod
spec_crypto.loader.exec_module(crypto_mod)

TenantKeyManager = crypto_mod.TenantKeyManager

# 4. Load diff_tracker.py
_DIFF_PATH = os.path.join(_PROJECT_ROOT, "server", "core", "diff_tracker.py")
spec_diff = importlib.util.spec_from_file_location("server.core.diff_tracker", _DIFF_PATH)
diff_mod = importlib.util.module_from_spec(spec_diff)
sys.modules["server.core.diff_tracker"] = diff_mod
spec_diff.loader.exec_module(diff_mod)

# Import the functions we're testing
_compute_field_diffs = diff_mod._compute_field_diffs
_encrypt_old_value = diff_mod._encrypt_old_value
_decrypt_old_value = diff_mod._decrypt_old_value
compute_and_log_field_diffs = diff_mod.compute_and_log_field_diffs
get_decrypted_field_diffs = diff_mod.get_decrypted_field_diffs
TRACKED_ENTITIES = diff_mod.TRACKED_ENTITIES
is_tracked_entity = diff_mod.is_tracked_entity
get_tracked_fields = diff_mod.get_tracked_fields


# ============================================================================
# 1. FIELD DIFF COMPUTATION (pure logic — no DB, no encryption)
# ============================================================================

class TestFieldDiffComputation:
    """Tests for _compute_field_diffs — pure dict comparison."""

    def test_detects_changed_fields(self):
        """Changed values are captured with old and new."""
        old = {"score": 85, "grade": "B", "remarks": "Good"}
        new = {"score": 92, "grade": "A", "remarks": "Good"}
        diffs = _compute_field_diffs(old, new)
        assert "score" in diffs
        assert diffs["score"]["old"] == 85
        assert diffs["score"]["new"] == 92
        assert "grade" in diffs
        assert diffs["grade"]["old"] == "B"
        assert diffs["grade"]["new"] == "A"

    def test_ignores_unchanged_fields(self):
        """Unchanged fields are not included in diffs."""
        old = {"score": 85, "grade": "B"}
        new = {"score": 85, "grade": "B"}
        diffs = _compute_field_diffs(old, new)
        assert len(diffs) == 0

    def test_detects_added_fields(self):
        """Fields present only in new_data are captured."""
        old = {"score": 85}
        new = {"score": 85, "moderation_applied": True}
        diffs = _compute_field_diffs(old, new)
        assert "moderation_applied" in diffs
        assert diffs["moderation_applied"]["old"] is None
        assert diffs["moderation_applied"]["new"] is True

    def test_detects_removed_fields(self):
        """Fields present only in old_data are captured."""
        old = {"score": 85, "bonus": 5}
        new = {"score": 85}
        diffs = _compute_field_diffs(old, new)
        assert "bonus" in diffs
        assert diffs["bonus"]["old"] == 5
        assert diffs["bonus"]["new"] is None

    def test_tracked_fields_filter(self):
        """Only tracked fields are compared when filter is provided."""
        old = {"score": 85, "grade": "B", "internal_notes": "Draft"}
        new = {"score": 92, "grade": "B", "internal_notes": "Final"}
        tracked = {"score", "grade"}
        diffs = _compute_field_diffs(old, new, tracked_fields=tracked)
        assert "score" in diffs
        assert "internal_notes" not in diffs

    def test_empty_inputs(self):
        """Empty dicts produce no diffs."""
        diffs = _compute_field_diffs({}, {})
        assert len(diffs) == 0

    def test_none_to_value_change(self):
        """None -> value is treated as a change."""
        old = {"fee_amount": None}
        new = {"fee_amount": 50000}
        diffs = _compute_field_diffs(old, new)
        assert "fee_amount" in diffs
        assert diffs["fee_amount"]["old"] is None
        assert diffs["fee_amount"]["new"] == 50000


# ============================================================================
# 2. TRACKED ENTITY REGISTRY
# ============================================================================

class TestTrackedEntityRegistry:
    """Tests for entity type registration."""

    def test_marks_is_tracked(self):
        assert is_tracked_entity("marks") is True

    def test_payroll_is_tracked(self):
        assert is_tracked_entity("payroll") is True

    def test_fee_is_tracked(self):
        assert is_tracked_entity("fee") is True

    def test_transcript_is_tracked(self):
        assert is_tracked_entity("transcript") is True

    def test_case_insensitive(self):
        assert is_tracked_entity("MARKS") is True
        assert is_tracked_entity("Payroll") is True

    def test_untracked_entity(self):
        assert is_tracked_entity("student_profile") is False
        assert is_tracked_entity("random") is False

    def test_tracked_fields_returns_set(self):
        fields = get_tracked_fields("marks")
        assert isinstance(fields, set)
        assert "score" in fields
        assert "grade" in fields

    def test_tracked_fields_empty_for_untracked(self):
        fields = get_tracked_fields("nonexistent")
        assert len(fields) == 0


# ============================================================================
# 3. ENCRYPTION / DECRYPTION OF PREVIOUS VALUES
# ============================================================================

class TestEncryptionOfPreviousValues:
    """Tests for _encrypt_old_value and _decrypt_old_value."""

    def setup_method(self):
        """Generate a fresh tenant key for each test."""
        # Clear any existing keys
        TenantKeyManager._keys.clear()
        TenantKeyManager._key_material.clear()

    def test_encrypt_decrypt_roundtrip_with_key(self):
        """Value survives encrypt -> decrypt cycle when tenant has a key."""
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except ImportError:
            pytest.skip("cryptography library not installed")

        TenantKeyManager.generate_tenant_key("t_test", actor_id="system")
        original = 85000
        encrypted = _encrypt_old_value("t_test", original)
        # Encrypted value should not be the same as original JSON
        assert encrypted != json.dumps(original)
        decrypted = _decrypt_old_value("t_test", encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_string_value(self):
        """String values survive roundtrip."""
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except ImportError:
            pytest.skip("cryptography library not installed")

        TenantKeyManager.generate_tenant_key("t_str", actor_id="system")
        original = "Grade A+"
        encrypted = _encrypt_old_value("t_str", original)
        decrypted = _decrypt_old_value("t_str", encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_none_value(self):
        """None values survive roundtrip."""
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except ImportError:
            pytest.skip("cryptography library not installed")

        TenantKeyManager.generate_tenant_key("t_none", actor_id="system")
        original = None
        encrypted = _encrypt_old_value("t_none", original)
        decrypted = _decrypt_old_value("t_none", encrypted)
        assert decrypted is None

    def test_no_key_stores_plaintext(self):
        """Without a tenant key, value is stored as plain JSON."""
        # No key generated for this tenant
        original = 42
        encrypted = _encrypt_old_value("t_no_key", original)
        assert encrypted == "42"

    def test_decrypt_plaintext_fallback(self):
        """Decrypting a plain JSON string (no encryption) works."""
        result = _decrypt_old_value("t_no_key", "42")
        assert result == 42

    def test_decrypt_plain_string_fallback(self):
        """Decrypting a raw non-JSON string returns it as-is."""
        result = _decrypt_old_value("t_no_key", "not_json_at_all")
        assert result == "not_json_at_all"


# ============================================================================
# 4. COMPUTE AND LOG FIELD DIFFS (mocked DB)
# ============================================================================

class TestComputeAndLogFieldDiffs:
    """Tests for the primary API: compute_and_log_field_diffs."""

    def _mock_audit_ledger(self):
        """
        Mock AuditLedger.log to capture calls without hitting DB.
        Returns the mock so assertions can be made on it.
        """
        mock_entry = AuditEntry(
            id="test-entry-1",
            tenant_id="t1",
            actor_id="faculty_1",
            actor_role="faculty",
            action="field_change",
            entity_type="marks",
            entity_id="m001",
            hash="abc123",
        )
        patcher = patch.object(AuditLedger, "log", return_value=mock_entry)
        mock_log = patcher.start()
        return mock_log, patcher

    def test_logs_field_changes(self):
        """Changed fields are encrypted and logged via AuditLedger."""
        mock_log, patcher = self._mock_audit_ledger()
        try:
            old_data = {"score": 85, "grade": "B"}
            new_data = {"score": 92, "grade": "A"}

            entry = compute_and_log_field_diffs(
                tenant_id="t1",
                actor_id="faculty_1",
                actor_role="faculty",
                entity_type="marks",
                entity_id="m001",
                old_data=old_data,
                new_data=new_data,
            )

            assert entry is not None
            assert entry.action == "field_change"

            # Verify AuditLedger.log was called with correct action
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.FIELD_CHANGE
            assert call_kwargs.kwargs["entity_type"] == "marks"
            assert call_kwargs.kwargs["entity_id"] == "m001"

            # Verify metadata contains field_diffs
            meta = call_kwargs.kwargs["metadata"]
            assert meta["diff_type"] == "field_level"
            assert "score" in meta["field_diffs"]
            assert "grade" in meta["field_diffs"]
            assert meta["change_count"] == 2
        finally:
            patcher.stop()

    def test_returns_none_when_no_changes(self):
        """If old_data == new_data, no audit entry is created."""
        mock_log, patcher = self._mock_audit_ledger()
        try:
            old_data = {"score": 85, "grade": "B"}
            new_data = {"score": 85, "grade": "B"}

            entry = compute_and_log_field_diffs(
                tenant_id="t1",
                actor_id="faculty_1",
                actor_role="faculty",
                entity_type="marks",
                entity_id="m001",
                old_data=old_data,
                new_data=new_data,
            )

            assert entry is None
            mock_log.assert_not_called()
        finally:
            patcher.stop()

    def test_raises_for_untracked_entity(self):
        """Unregistered entity types raise DiffTrackingError."""
        with pytest.raises(DiffTrackingError) as exc_info:
            compute_and_log_field_diffs(
                tenant_id="t1",
                actor_id="admin",
                actor_role="admin",
                entity_type="student_profile",
                entity_id="sp001",
                old_data={"name": "Old"},
                new_data={"name": "New"},
            )
        assert "not registered" in str(exc_info.value)

    def test_only_tracked_fields_are_diffed(self):
        """Untracked fields within a tracked entity are ignored."""
        mock_log, patcher = self._mock_audit_ledger()
        try:
            # "internal_notes" is NOT in TRACKED_ENTITIES["marks"]
            old_data = {"score": 85, "internal_notes": "Draft"}
            new_data = {"score": 92, "internal_notes": "Final"}

            compute_and_log_field_diffs(
                tenant_id="t1",
                actor_id="faculty_1",
                actor_role="faculty",
                entity_type="marks",
                entity_id="m001",
                old_data=old_data,
                new_data=new_data,
            )

            meta = mock_log.call_args.kwargs["metadata"]
            assert "score" in meta["field_diffs"]
            assert "internal_notes" not in meta["field_diffs"]
        finally:
            patcher.stop()

    def test_module_and_wizard_in_metadata(self):
        """Optional module/wizard params are included in metadata."""
        mock_log, patcher = self._mock_audit_ledger()
        try:
            compute_and_log_field_diffs(
                tenant_id="t1",
                actor_id="faculty_1",
                actor_role="faculty",
                entity_type="marks",
                entity_id="m001",
                old_data={"score": 85},
                new_data={"score": 92},
                module="M3_Examinations",
                wizard="Evaluation_Logic",
            )

            meta = mock_log.call_args.kwargs["metadata"]
            assert meta["module"] == "M3_Examinations"
            assert meta["wizard"] == "Evaluation_Logic"
        finally:
            patcher.stop()


# ============================================================================
# 5. GET DECRYPTED FIELD DIFFS (admin console query)
# ============================================================================

class TestGetDecryptedFieldDiffs:
    """Tests for get_decrypted_field_diffs — admin console read path."""

    def test_decrypts_and_formats_diffs(self):
        """Encrypted old values are decrypted for admin viewing."""
        # Simulate raw audit history rows from DB
        mock_rows = [
            {
                "id": 1,
                "actor_id": "faculty_1",
                "actor_role": "faculty",
                "timestamp": datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
                "hash": "abc123",
                "metadata": {
                    "diff_type": "field_level",
                    "fields_changed": ["score", "grade"],
                    "change_count": 2,
                    "field_diffs": {
                        "score": {"old_encrypted": "85", "new": 92},
                        "grade": {"old_encrypted": '"B"', "new": "A"},
                    },
                },
            },
        ]

        with patch.object(AuditLedger, "get_entity_history", return_value=mock_rows):
            results = get_decrypted_field_diffs(
                tenant_id="t1",
                entity_type="marks",
                entity_id="m001",
            )

        assert len(results) == 1
        result = results[0]
        assert result["audit_id"] == 1
        assert result["actor_id"] == "faculty_1"
        assert result["change_count"] == 2
        assert result["field_diffs"]["score"]["old"] == 85
        assert result["field_diffs"]["score"]["new"] == 92
        assert result["field_diffs"]["grade"]["old"] == "B"
        assert result["field_diffs"]["grade"]["new"] == "A"

    def test_filters_non_diff_entries(self):
        """Non-field-diff audit entries are excluded."""
        mock_rows = [
            {
                "id": 1,
                "actor_id": "admin",
                "actor_role": "admin",
                "timestamp": datetime(2025, 6, 1, tzinfo=timezone.utc),
                "hash": "xxx",
                "metadata": {"action_detail": "Some other action"},
            },
            {
                "id": 2,
                "actor_id": "faculty_1",
                "actor_role": "faculty",
                "timestamp": datetime(2025, 6, 2, tzinfo=timezone.utc),
                "hash": "yyy",
                "metadata": {
                    "diff_type": "field_level",
                    "fields_changed": ["score"],
                    "change_count": 1,
                    "field_diffs": {
                        "score": {"old_encrypted": "85", "new": 92},
                    },
                },
            },
        ]

        with patch.object(AuditLedger, "get_entity_history", return_value=mock_rows):
            results = get_decrypted_field_diffs(
                tenant_id="t1",
                entity_type="marks",
                entity_id="m001",
            )

        # Only the field_level entry should be returned
        assert len(results) == 1
        assert results[0]["audit_id"] == 2

    def test_handles_string_metadata(self):
        """Metadata stored as JSON string (not dict) is parsed correctly."""
        mock_rows = [
            {
                "id": 1,
                "actor_id": "faculty_1",
                "actor_role": "faculty",
                "timestamp": datetime(2025, 6, 1, tzinfo=timezone.utc),
                "hash": "aaa",
                "metadata": json.dumps({
                    "diff_type": "field_level",
                    "fields_changed": ["score"],
                    "change_count": 1,
                    "field_diffs": {
                        "score": {"old_encrypted": "85", "new": 92},
                    },
                }),
            },
        ]

        with patch.object(AuditLedger, "get_entity_history", return_value=mock_rows):
            results = get_decrypted_field_diffs(
                tenant_id="t1",
                entity_type="marks",
                entity_id="m001",
            )

        assert len(results) == 1
        assert results[0]["field_diffs"]["score"]["old"] == 85

    def test_empty_history(self):
        """Empty audit history returns empty list."""
        with patch.object(AuditLedger, "get_entity_history", return_value=[]):
            results = get_decrypted_field_diffs(
                tenant_id="t1",
                entity_type="marks",
                entity_id="m001",
            )
        assert results == []


# ============================================================================
# 6. AUDIT ACTION ENUM
# ============================================================================

class TestAuditActionEnum:
    """Verify FIELD_CHANGE was added to AuditAction."""

    def test_field_change_exists(self):
        assert hasattr(AuditAction, "FIELD_CHANGE")
        assert AuditAction.FIELD_CHANGE.value == "field_change"
