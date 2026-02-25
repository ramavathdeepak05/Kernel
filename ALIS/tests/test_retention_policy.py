"""
ALIS Data Retention & Deletion Policy Engine Tests — E00-S07

Tests cover:
  1. Layer 1 — RetentionClass metadata on EntityClassification
  2. Layer 4 — ARCHIVED_RECORD global lock blocks mutations
  3. Scheduled Archival Service — archival job logic
  4. Legal Deletion Workflow — superadmin enforcement
  5. Retention Audit Report — compliance reporting

These tests are self-contained and do NOT require a database connection.
They mock the AuditLedger.log() calls to avoid psycopg2 dependency.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Path setup — ensure `server` package is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from server.core.data_classification import (
    RetentionClass,
    EntityClassification,
    EntityClassificationRegistry,
    SensitivityLevel,
    RegulatedDataType,
    initialize_default_classifications,
    _DEFAULT_RETENTION_DAYS,
)
from server.core.locks import (
    LockType,
    GlobalLockRegistry,
    check_global_locks,
)
from server.core.audit import AuditAction
from server.core.rbac import Role, Permission
from server.core.retention_policy import (
    ArchivalService,
    ArchivalStatus,
    RetentionService,
    DeletionStatus,
    RetentionMatrix,
    RetentionAuditReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_registries():
    """Reset all class-level registries between tests."""
    EntityClassificationRegistry._reset()
    ArchivalService._reset()
    RetentionService._reset()
    # Re-register defaults needed for most tests
    initialize_default_classifications()
    yield


# ============================================================================
# 1. LAYER 1 — RETENTION CLASS METADATA
# ============================================================================

class TestRetentionClassEnum:
    """Test RetentionClass enum and default retention day mappings."""

    def test_retention_enum_values(self):
        assert RetentionClass.TEMPORARY.value == "TEMPORARY"
        assert RetentionClass.STANDARD.value == "STANDARD"
        assert RetentionClass.LONG_TERM.value == "LONG_TERM"
        assert RetentionClass.PERMANENT.value == "PERMANENT"

    def test_default_retention_days(self):
        assert _DEFAULT_RETENTION_DAYS[RetentionClass.TEMPORARY] == 90
        assert _DEFAULT_RETENTION_DAYS[RetentionClass.STANDARD] == 1825
        assert _DEFAULT_RETENTION_DAYS[RetentionClass.LONG_TERM] == 730
        assert _DEFAULT_RETENTION_DAYS[RetentionClass.PERMANENT] is None


class TestEntityClassificationRetention:
    """Test retention metadata on EntityClassification."""

    def test_default_retention_class(self):
        ec = EntityClassification(entity_type="test_entity")
        assert ec.retention_class == RetentionClass.STANDARD
        assert ec.retention_days is None
        assert ec.effective_retention_days == 1825
        assert ec.is_permanent is False

    def test_permanent_retention(self):
        ec = EntityClassification(
            entity_type="transcript",
            retention_class=RetentionClass.PERMANENT,
        )
        assert ec.effective_retention_days is None
        assert ec.is_permanent is True

    def test_custom_retention_days_override(self):
        ec = EntityClassification(
            entity_type="custom",
            retention_class=RetentionClass.STANDARD,
            retention_days=365,  # Override the 5-year default
        )
        assert ec.effective_retention_days == 365
        assert ec.is_permanent is False

    def test_long_term_biometric(self):
        ec = EntityClassification(
            entity_type="biometric",
            retention_class=RetentionClass.LONG_TERM,
        )
        assert ec.effective_retention_days == 730  # 2 years

    def test_registered_entities_have_retention_metadata(self):
        """Verify all default registered entities carry retention metadata."""
        for entity_type in EntityClassificationRegistry.list_registered():
            ec = EntityClassificationRegistry.get(entity_type)
            assert ec is not None, f"{entity_type} not registered"
            assert isinstance(ec.retention_class, RetentionClass), (
                f"{entity_type} missing retention_class"
            )


class TestRetentionMatrix:
    """Test the retention policy matrix per task description specs."""

    def test_transcript_permanent(self):
        info = RetentionMatrix.get_retention_info("generated_document")
        assert info["is_permanent"] is True
        assert info["retention_class"] == "PERMANENT"

    def test_audit_permanent(self):
        info = RetentionMatrix.get_retention_info("audit_entry")
        assert info["is_permanent"] is True

    def test_biometric_two_years(self):
        info = RetentionMatrix.get_retention_info("biometric_log")
        assert info["retention_days"] == 730
        assert info["retention_class"] == "LONG_TERM"

    def test_attendance_five_years(self):
        info = RetentionMatrix.get_retention_info("attendance_record")
        assert info["retention_days"] == 1825
        assert info["retention_class"] == "STANDARD"

    def test_financial_permanent(self):
        info = RetentionMatrix.get_retention_info("financial_record")
        assert info["is_permanent"] is True

    def test_full_matrix_returns_all_entities(self):
        matrix = RetentionMatrix.get_full_matrix()
        registered = EntityClassificationRegistry.list_registered()
        assert len(matrix) == len(registered)


# ============================================================================
# 2. LAYER 4 — ARCHIVED_RECORD GLOBAL LOCK
# ============================================================================

class TestArchivalLock:
    """Test that archived records are protected by Layer 4 lock."""

    def test_archived_record_is_locked(self):
        result = check_global_locks(
            entity_id="student_001",
            context={"is_archived": True},
        )
        assert result.is_locked is True
        assert any(
            v.lock_type == LockType.ARCHIVED_RECORD
            for v in result.violations
        )

    def test_archived_status_string(self):
        result = check_global_locks(
            entity_id="student_002",
            context={"status": "ARCHIVED"},
        )
        assert result.is_locked is True
        reasons = result.reasons
        assert any("archived" in r.lower() for r in reasons)

    def test_active_record_not_locked_by_archival(self):
        result = GlobalLockRegistry.check_lock(
            lock_type=LockType.ARCHIVED_RECORD,
            entity_id="student_003",
            context={"is_archived": False, "status": "ACTIVE"},
        )
        assert result.is_locked is False

    def test_missing_context_not_locked(self):
        result = GlobalLockRegistry.check_lock(
            lock_type=LockType.ARCHIVED_RECORD,
            entity_id="student_004",
            context={},
        )
        assert result.is_locked is False


# ============================================================================
# 3. AUDIT ACTIONS
# ============================================================================

class TestAuditActions:
    """Test that new audit actions exist."""

    def test_archive_action_exists(self):
        assert AuditAction.ARCHIVE.value == "archive"

    def test_hard_delete_action_exists(self):
        assert AuditAction.HARD_DELETE.value == "hard_delete"

    def test_retention_policy_applied_action_exists(self):
        assert AuditAction.RETENTION_POLICY_APPLIED.value == "retention_policy_applied"


# ============================================================================
# 4. RBAC — RETENTION PERMISSIONS
# ============================================================================

class TestRetentionPermissions:
    """Test that retention permissions are defined."""

    def test_retention_manage_permission(self):
        assert Permission.RETENTION_MANAGE.value == "retention:manage"

    def test_hard_delete_permission(self):
        assert Permission.HARD_DELETE.value == "retention:hard_delete"


# ============================================================================
# 5. SCHEDULED ARCHIVAL SERVICE
# ============================================================================

class TestArchivalService:
    """Test the scheduled archival job logic."""

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_archive_expired_record(self, mock_log):
        """Record past its retention period should be archived."""
        mock_log.return_value = MagicMock()

        # Task entity has TEMPORARY retention (90 days)
        records = [
            {
                "entity_type": "task",
                "entity_id": "task_001",
                "created_at": datetime.now(timezone.utc) - timedelta(days=100),
                "status": "COMPLETED",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records,
        )
        assert len(results) == 1
        assert results[0].status == ArchivalStatus.ARCHIVED
        assert mock_log.called

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_skip_permanent_record(self, mock_log):
        """Permanent records should be skipped."""
        records = [
            {
                "entity_type": "generated_document",
                "entity_id": "doc_001",
                "created_at": datetime.now(timezone.utc) - timedelta(days=36500),
                "status": "ACTIVE",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records,
        )
        assert len(results) == 1
        assert results[0].status == ArchivalStatus.SKIPPED_PERMANENT
        assert not mock_log.called

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_not_yet_eligible(self, mock_log):
        """Record within retention period should not be archived."""
        records = [
            {
                "entity_type": "task",
                "entity_id": "task_002",
                "created_at": datetime.now(timezone.utc) - timedelta(days=30),
                "status": "PENDING",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records,
        )
        # Not yet eligible — should return empty
        assert len(results) == 0

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_already_archived_skipped(self, mock_log):
        """Already archived records should be skipped."""
        records = [
            {
                "entity_type": "task",
                "entity_id": "task_003",
                "created_at": datetime.now(timezone.utc) - timedelta(days=100),
                "status": "ARCHIVED",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records,
        )
        assert len(results) == 0

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_dry_run_does_not_commit(self, mock_log):
        """Dry run should evaluate but not call audit log."""
        records = [
            {
                "entity_type": "task",
                "entity_id": "task_004",
                "created_at": datetime.now(timezone.utc) - timedelta(days=100),
                "status": "COMPLETED",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records, dry_run=True,
        )
        assert len(results) == 1
        assert results[0].status == ArchivalStatus.PENDING
        assert not mock_log.called

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_biometric_log_two_year_retention(self, mock_log):
        """Biometric logs should archive after 2 years."""
        mock_log.return_value = MagicMock()

        records = [
            {
                "entity_type": "biometric_log",
                "entity_id": "bio_001",
                "created_at": datetime.now(timezone.utc) - timedelta(days=731),
                "status": "ACTIVE",
            }
        ]
        results = ArchivalService.run_archival_job(
            tenant_id="tenant_001", records=records,
        )
        assert len(results) == 1
        assert results[0].status == ArchivalStatus.ARCHIVED


# ============================================================================
# 6. LEGAL DELETION WORKFLOW
# ============================================================================

class TestRetentionService:
    """Test the hard-delete legal workflow."""

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_superadmin_can_delete_non_permanent(self, mock_log):
        """SUPER_ADMIN should be able to delete non-permanent data."""
        mock_log.return_value = MagicMock()

        result = RetentionService.request_hard_delete(
            entity_type="task",
            entity_id="task_099",
            tenant_id="tenant_001",
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            justification="Legal compliance request #LC-2026-001",
        )
        assert result.status == DeletionStatus.EXECUTED
        assert mock_log.called

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_non_superadmin_rejected(self, mock_log):
        """Non-SUPER_ADMIN roles should be rejected."""
        mock_log.return_value = MagicMock()

        with pytest.raises(PermissionError, match="SUPER_ADMIN"):
            RetentionService.request_hard_delete(
                entity_type="task",
                entity_id="task_100",
                tenant_id="tenant_001",
                actor_id="faculty_001",
                actor_role=Role.FACULTY.value,
                justification="Want to clean up",
            )

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_admin_rejected(self, mock_log):
        """Even ADMIN (not SUPER_ADMIN) should be rejected."""
        mock_log.return_value = MagicMock()

        with pytest.raises(PermissionError, match="SUPER_ADMIN"):
            RetentionService.request_hard_delete(
                entity_type="task",
                entity_id="task_101",
                tenant_id="tenant_001",
                actor_id="admin_regular",
                actor_role=Role.ADMIN.value,
                justification="Administrative cleanup",
            )

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_empty_justification_rejected(self, mock_log):
        """Empty justification should be rejected."""
        with pytest.raises(ValueError, match="justification"):
            RetentionService.request_hard_delete(
                entity_type="task",
                entity_id="task_102",
                tenant_id="tenant_001",
                actor_id="admin_001",
                actor_role=Role.SUPER_ADMIN.value,
                justification="",
            )

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_permanent_entity_deletion_rejected(self, mock_log):
        """Permanent records (transcripts) should be rejected for deletion."""
        mock_log.return_value = MagicMock()

        result = RetentionService.request_hard_delete(
            entity_type="generated_document",  # PERMANENT retention
            entity_id="doc_001",
            tenant_id="tenant_001",
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            justification="Special legal order #SLO-2026-001",
        )
        assert result.status == DeletionStatus.REJECTED
        assert "PERMANENT" in result.rejection_reason

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_deletion_logs_snapshot(self, mock_log):
        """Deletion should log the pre-deletion entity snapshot."""
        mock_log.return_value = MagicMock()

        snapshot = {"entity_id": "task_103", "title": "Old task", "status": "COMPLETED"}
        RetentionService.request_hard_delete(
            entity_type="task",
            entity_id="task_103",
            tenant_id="tenant_001",
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            justification="Data subject erasure request",
            entity_snapshot=snapshot,
        )
        # Verify the audit log was called with the snapshot
        call_args = mock_log.call_args
        assert call_args is not None
        metadata = call_args.kwargs.get("metadata", {})
        assert "pre_deletion_snapshot" in metadata


# ============================================================================
# 7. RETENTION AUDIT REPORT
# ============================================================================

class TestRetentionAuditReport:
    """Test retention audit report generation."""

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_report_structure(self, mock_log):
        """Report should have the required top-level keys."""
        report = RetentionAuditReport.generate()
        assert "retention_matrix" in report
        assert "archival_summary" in report
        assert "deletion_summary" in report
        assert "report_generated_at" in report

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_report_matrix_covers_all_entities(self, mock_log):
        """The retention matrix should include all registered entities."""
        report = RetentionAuditReport.generate()
        registered = EntityClassificationRegistry.list_registered()
        assert len(report["retention_matrix"]) == len(registered)

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_report_reflects_archival_activity(self, mock_log):
        """Report should reflect archival actions taken."""
        mock_log.return_value = MagicMock()

        # Run an archival job first
        records = [
            {
                "entity_type": "task",
                "entity_id": "task_rpt_001",
                "created_at": datetime.now(timezone.utc) - timedelta(days=100),
                "status": "COMPLETED",
            }
        ]
        ArchivalService.run_archival_job(
            tenant_id="tenant_rpt", records=records,
        )

        report = RetentionAuditReport.generate(tenant_id="tenant_rpt")
        assert report["archival_summary"]["archived"] >= 1

    @patch("server.core.retention_policy.AuditLedger.log")
    def test_report_reflects_deletion_activity(self, mock_log):
        """Report should reflect deletion requests."""
        mock_log.return_value = MagicMock()

        RetentionService.request_hard_delete(
            entity_type="task",
            entity_id="task_rpt_002",
            tenant_id="tenant_rpt",
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            justification="Legal compliance",
        )

        report = RetentionAuditReport.generate(tenant_id="tenant_rpt")
        assert report["deletion_summary"]["executed"] >= 1
