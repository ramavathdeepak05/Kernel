"""
Unit Tests for ALIS Incident Response & Lockdown Mode - E00-S05

Tests:
1. Lockdown Activation (flag, audit, permissions)
2. Session Invalidation (non-admin revocation)
3. Write Gate (db_service transaction blocking)
4. AI Gate (ai_gateway invocation blocking)
5. Lockdown Deactivation (release and restore)
6. Edge Cases (double-activate, unauthorized trigger)
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from server.core.lockdown import LockdownManager, LockdownEvent, LOCKDOWN_IMMUNE_ROLES
from server.core.security import SessionManager, Session
from server.core.rbac import Role, Permission
from server.core.audit import AuditLog, AuditAction
from server.core.config import ConfigRegistry
from server.core.exceptions import (
    PermissionDeniedError,
    LockdownActiveError,
)


# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_services(fake_redis_global):
    """Reset all services before each test."""
    LockdownManager._reset()
    fake_redis_global.flushall()  # clear session/rate state
    AuditLog._entries = []
    ConfigRegistry._configs = {}
    ConfigRegistry.initialize_defaults()
    yield


# ===========================================================
# TEST CLASS 1: LOCKDOWN ACTIVATION
# ===========================================================

class TestLockdownActivation:
    """Tests for activating lockdown mode."""

    def test_activate_sets_global_flag(self):
        """Test that activation sets the global lockdown flag to True."""
        assert LockdownManager.is_active() is False

        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Security breach detected",
        )

        assert LockdownManager.is_active() is True

    def test_activate_returns_event(self):
        """Test that activation returns a LockdownEvent record."""
        event = LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Drill",
        )

        assert isinstance(event, LockdownEvent)
        assert event.event_type == "activated"
        assert event.actor_id == "admin_001"
        assert event.reason == "Drill"
        assert event.timestamp is not None

    def test_activate_creates_audit_entry(self):
        """Test that activation writes to the immutable audit log."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Audit test",
        )

        entries = AuditLog.query(action=AuditAction.LOCK_TRIGGERED)
        assert len(entries) == 1
        assert entries[0].actor_id == "admin_001"
        assert entries[0].entity_type == "lockdown"
        assert "ACTIVATED" in entries[0].action_detail

    def test_activate_records_metadata(self):
        """Test that custom metadata is captured in the event."""
        event = LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.ADMIN.value,
            reason="Test with metadata",
            metadata={"incident_ticket": "INC-2026-001"},
        )

        assert event.metadata["incident_ticket"] == "INC-2026-001"

    def test_activate_denied_for_non_admin(self):
        """Test that non-admin roles cannot activate lockdown."""
        with pytest.raises(PermissionDeniedError, match="ADMIN"):
            LockdownManager.activate(
                actor_id="faculty_001",
                actor_role=Role.FACULTY.value,
                reason="Should fail",
            )

        assert LockdownManager.is_active() is False

    def test_activate_denied_for_student(self):
        """Test that students cannot trigger lockdown."""
        with pytest.raises(PermissionDeniedError):
            LockdownManager.activate(
                actor_id="student_001",
                actor_role=Role.STUDENT.value,
                reason="Should fail",
            )

    def test_double_activate_raises_error(self):
        """Test that activating lockdown when already active raises ValueError."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="First",
        )

        with pytest.raises(ValueError, match="already active"):
            LockdownManager.activate(
                actor_id="admin_002",
                actor_role=Role.SUPER_ADMIN.value,
                reason="Second",
            )

    def test_get_status(self):
        """Test that get_status returns structured data."""
        status_before = LockdownManager.get_status()
        assert status_before["is_active"] is False
        assert status_before["activated_by"] is None

        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Status test",
        )

        status_after = LockdownManager.get_status()
        assert status_after["is_active"] is True
        assert status_after["activated_by"] == "admin_001"
        assert status_after["reason"] == "Status test"
        assert status_after["event_count"] == 1


# ===========================================================
# TEST CLASS 2: SESSION INVALIDATION
# ===========================================================

class TestSessionInvalidation:
    """Tests for mass session revocation during lockdown."""

    def test_sessions_revoked_on_activation(self):
        """Test that all sessions are revoked when lockdown activates."""
        s1, _ = SessionManager.create_session(user_id="student_001")
        s2, _ = SessionManager.create_session(user_id="faculty_001")
        s3, _ = SessionManager.create_session(user_id="admin_001")

        assert s1.is_active is True
        assert s2.is_active is True
        assert s3.is_active is True

        event = LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Session test",
        )

        # Reload from Redis to check persisted state
        assert SessionManager.get_session(s1.id).is_active is False
        assert SessionManager.get_session(s2.id).is_active is False
        assert SessionManager.get_session(s3.id).is_active is False
        assert event.sessions_revoked == 3

    def test_revoke_count_is_accurate(self):
        """Test that the revoked session count matches reality."""
        # Create 5 active sessions
        for i in range(5):
            SessionManager.create_session(user_id=f"user_{i}")

        event = LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Count test",
        )

        assert event.sessions_revoked == 5

    def test_already_revoked_sessions_not_counted(self):
        """Test that already-revoked sessions are skipped."""
        s1, _ = SessionManager.create_session(user_id="user_001")
        s2, _ = SessionManager.create_session(user_id="user_002")

        # Pre-revoke one via the proper API (persists to Redis)
        SessionManager.revoke_session(s1.id, reason="Manual revoke")

        event = LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Pre-revoke test",
        )

        assert event.sessions_revoked == 1  # Only s2


# ===========================================================
# TEST CLASS 3: WRITE GATE (LAYER 4)
# ===========================================================

class TestWriteGate:
    """Tests for blocking non-admin writes during lockdown."""

    def test_write_allowed_when_not_in_lockdown(self):
        """Test that assert_write_allowed passes in normal mode."""
        # Should not raise
        LockdownManager.assert_write_allowed(
            actor_role=Role.STUDENT.value,
            actor_id="student_001",
        )

    def test_write_blocked_for_student(self):
        """Test that student writes are blocked during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Write gate test",
        )

        with pytest.raises(LockdownActiveError, match="lockdown"):
            LockdownManager.assert_write_allowed(
                actor_role=Role.STUDENT.value,
                actor_id="student_001",
            )

    def test_write_blocked_for_faculty(self):
        """Test that faculty writes are blocked during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Write gate test",
        )

        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_write_allowed(
                actor_role=Role.FACULTY.value,
                actor_id="faculty_001",
            )

    def test_write_allowed_for_admin_during_lockdown(self):
        """Test that ADMIN can still write during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Admin bypass test",
        )

        # Should not raise
        LockdownManager.assert_write_allowed(
            actor_role=Role.ADMIN.value,
            actor_id="admin_001",
        )

    def test_write_allowed_for_super_admin_during_lockdown(self):
        """Test that SUPER_ADMIN can still write during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="SuperAdmin bypass test",
        )

        LockdownManager.assert_write_allowed(
            actor_role=Role.SUPER_ADMIN.value,
            actor_id="admin_002",
        )

    def test_write_allowed_for_system_during_lockdown(self):
        """Test that SYSTEM role can still write during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="System bypass test",
        )

        LockdownManager.assert_write_allowed(
            actor_role=Role.SYSTEM.value,
            actor_id="system",
        )

    def test_blocked_write_creates_audit_entry(self):
        """Test that a blocked write attempt is audit-logged."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Audit denial test",
        )

        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_write_allowed(
                actor_role=Role.FACULTY.value,
                actor_id="faculty_001",
            )

        denied = AuditLog.query(action=AuditAction.ACCESS_DENIED)
        # Filter to lockdown-specific denials
        lockdown_denied = [
            e for e in denied if e.entity_type == "lockdown_write_gate"
        ]
        assert len(lockdown_denied) == 1
        assert lockdown_denied[0].actor_id == "faculty_001"

    def test_write_blocked_for_unknown_role(self):
        """Test that unknown/None roles are blocked during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Unknown role test",
        )

        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_write_allowed(
                actor_role=None,
                actor_id="rogue_process",
            )


# ===========================================================
# TEST CLASS 4: AI GATE (GLOBAL AI PAUSE)
# ===========================================================

class TestAIGate:
    """Tests for blocking AI invocations during lockdown."""

    def test_ai_allowed_when_not_in_lockdown(self):
        """Test that assert_ai_allowed passes in normal mode."""
        LockdownManager.assert_ai_allowed(actor_id="agent_001")

    def test_ai_blocked_during_lockdown(self):
        """Test that ALL AI invocations are blocked during lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="AI pause test",
        )

        with pytest.raises(LockdownActiveError, match="AI invocations"):
            LockdownManager.assert_ai_allowed(actor_id="agent_001")

    def test_ai_blocked_even_for_admin(self):
        """Test that AI invocations are blocked for admins too (§27 compliance)."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Total AI freeze",
        )

        # AI should be blocked regardless of who invokes
        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_ai_allowed(actor_id="admin_001")

    def test_blocked_ai_creates_audit_entry(self):
        """Test that a blocked AI attempt is audit-logged."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="AI audit test",
        )

        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_ai_allowed(actor_id="agent_m1")

        denied = AuditLog.query(action=AuditAction.ACCESS_DENIED)
        ai_denied = [
            e for e in denied if e.entity_type == "lockdown_ai_gate"
        ]
        assert len(ai_denied) == 1
        assert ai_denied[0].actor_id == "agent_m1"


# ===========================================================
# TEST CLASS 5: LOCKDOWN DEACTIVATION
# ===========================================================

class TestLockdownDeactivation:
    """Tests for deactivating lockdown and restoring operations."""

    def test_deactivate_clears_flag(self):
        """Test that deactivation sets the global flag to False."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )
        assert LockdownManager.is_active() is True

        LockdownManager.deactivate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Incident resolved",
        )
        assert LockdownManager.is_active() is False

    def test_deactivate_returns_event(self):
        """Test that deactivation returns a LockdownEvent record."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )

        event = LockdownManager.deactivate(
            actor_id="admin_002",
            actor_role=Role.ADMIN.value,
            reason="All clear",
        )

        assert isinstance(event, LockdownEvent)
        assert event.event_type == "deactivated"
        assert event.actor_id == "admin_002"
        assert event.reason == "All clear"

    def test_deactivate_creates_audit_entry(self):
        """Test that deactivation writes to the audit log."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )

        LockdownManager.deactivate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Resolved",
        )

        entries = AuditLog.query(action=AuditAction.LOCK_CLEARED)
        assert len(entries) == 1
        assert "DEACTIVATED" in entries[0].action_detail

    def test_writes_restored_after_deactivation(self):
        """Test that non-admin writes work again after deactivation."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )

        # Blocked during lockdown
        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_write_allowed(
                actor_role=Role.FACULTY.value,
                actor_id="faculty_001",
            )

        LockdownManager.deactivate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Resolved",
        )

        # Should work now
        LockdownManager.assert_write_allowed(
            actor_role=Role.FACULTY.value,
            actor_id="faculty_001",
        )

    def test_ai_restored_after_deactivation(self):
        """Test that AI invocations work again after deactivation."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )

        with pytest.raises(LockdownActiveError):
            LockdownManager.assert_ai_allowed(actor_id="agent_001")

        LockdownManager.deactivate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Resolved",
        )

        # Should work now
        LockdownManager.assert_ai_allowed(actor_id="agent_001")

    def test_deactivate_denied_for_non_admin(self):
        """Test that non-admin roles cannot deactivate lockdown."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Setup",
        )

        with pytest.raises(PermissionDeniedError):
            LockdownManager.deactivate(
                actor_id="faculty_001",
                actor_role=Role.FACULTY.value,
                reason="Should fail",
            )

        assert LockdownManager.is_active() is True

    def test_deactivate_when_not_active_raises_error(self):
        """Test that deactivating when not in lockdown raises ValueError."""
        with pytest.raises(ValueError, match="not currently active"):
            LockdownManager.deactivate(
                actor_id="admin_001",
                actor_role=Role.SUPER_ADMIN.value,
                reason="Nothing to deactivate",
            )


# ===========================================================
# TEST CLASS 6: EVENT HISTORY
# ===========================================================

class TestEventHistory:
    """Tests for lockdown event history tracking."""

    def test_event_history_accumulates(self):
        """Test that activate/deactivate events build up in history."""
        LockdownManager.activate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Event 1",
        )
        LockdownManager.deactivate(
            actor_id="admin_001",
            actor_role=Role.SUPER_ADMIN.value,
            reason="Event 2",
        )

        history = LockdownManager.get_event_history()
        assert len(history) == 2
        assert history[0].event_type == "activated"
        assert history[1].event_type == "deactivated"

    def test_immune_roles_are_correct(self):
        """Test that LOCKDOWN_IMMUNE_ROLES contains exactly the expected roles."""
        assert Role.ADMIN in LOCKDOWN_IMMUNE_ROLES
        assert Role.SUPER_ADMIN in LOCKDOWN_IMMUNE_ROLES
        assert Role.SYSTEM in LOCKDOWN_IMMUNE_ROLES
        assert Role.STUDENT not in LOCKDOWN_IMMUNE_ROLES
        assert Role.FACULTY not in LOCKDOWN_IMMUNE_ROLES
        assert Role.AI_AGENT not in LOCKDOWN_IMMUNE_ROLES
