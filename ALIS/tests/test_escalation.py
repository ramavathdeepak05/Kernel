"""
Unit Tests for ALIS Privilege Escalation & Dual Control - E00-S04

Tests:
1. Escalation Lifecycle (request, grant, deny, expire, revoke)
2. Dual Control Guard (register, require, verify, enforce)
3. Token Validation (scope, permission, expiry checks)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from server.core.escalation import (
    EscalationService,
    EscalationState,
    ElevatedAccessToken,
    DualControlGuard,
    CriticalOperation,
)
from server.core.rbac import Role, Permission
from server.core.approvals import ApprovalService, ApprovalState
from server.core.audit import AuditLog, AuditAction
from server.core.config import ConfigRegistry
from server.core.exceptions import EscalationDeniedError, DualControlRequiredError


# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_services():
    """Reset all services before each test."""
    EscalationService._tokens = {}
    DualControlGuard._operations = {}
    DualControlGuard._initialized = False
    ApprovalService._requests = {}
    ApprovalService._configs = {}
    AuditLog._entries = []
    # Re-initialize config defaults
    ConfigRegistry._configs = {}
    ConfigRegistry.initialize_defaults()
    yield


# ===========================================================
# TEST CLASS 1: ESCALATION LIFECYCLE
# ===========================================================

class TestEscalationLifecycle:
    """Tests for the full escalation token lifecycle."""

    def test_request_escalation(self):
        """Test creating an escalation request."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="End-of-term finalization",
            scope="marks:COURSE-2024",
            tenant_id="ORG-001"
        )

        assert token.id is not None
        assert token.state == EscalationState.REQUESTED
        assert token.user_id == "faculty_001"
        assert token.granted_permissions == [Permission.MARKS_FINALIZE]
        assert token.scope == "marks:COURSE-2024"
        assert token.reason == "End-of-term finalization"
        assert token.tenant_id == "ORG-001"
        assert token.ttl_minutes == 30  # Default TTL
        assert token.granted_by is None
        assert token.expires_at is None

    def test_grant_escalation(self):
        """Test granting an escalation request transitions to ACTIVE."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Testing grant"
        )

        granted = EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        assert granted.state == EscalationState.ACTIVE
        assert granted.granted_by == "admin_001"
        assert granted.granted_at is not None
        assert granted.expires_at is not None
        assert granted.is_active() is True
        # Expiry should be ~30 minutes from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        assert abs((granted.expires_at - expected_expiry).total_seconds()) < 5

    def test_escalation_auto_expires(self):
        """Test that a token past TTL is treated as expired."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Testing expiry",
            ttl_minutes=5
        )

        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        # Manually set expiry to the past
        token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        # Check-on-use should detect expiry
        result = EscalationService.check_escalation(
            user_id="faculty_001",
            permission=Permission.MARKS_FINALIZE
        )

        assert result is None
        assert token.state == EscalationState.EXPIRED

    def test_revoke_escalation(self):
        """Test manual revocation of an active token."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Testing revoke"
        )

        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        revoked = EscalationService.revoke_escalation(
            token_id=token.id,
            actor_id="admin_001",
            reason="No longer needed"
        )

        assert revoked.state == EscalationState.REVOKED
        assert revoked.revoked_by == "admin_001"
        assert revoked.revoked_at is not None
        assert revoked.is_active() is False

    def test_self_grant_denied(self):
        """Test that a user cannot grant escalation to themselves."""
        token = EscalationService.request_escalation(
            user_id="admin_001",
            requested_permissions=[Permission.CONFIG_WRITE],
            reason="Self-test"
        )

        with pytest.raises(EscalationDeniedError, match="Self-grant denied"):
            EscalationService.grant_escalation(
                token_id=token.id,
                grantor_id="admin_001",  # Same as requestor!
                grantor_role=Role.ADMIN
            )

    def test_grant_requires_permission(self):
        """Test that only roles with ESCALATION_GRANT can grant."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Testing permission check"
        )

        # STUDENT does not have ESCALATION_GRANT
        with pytest.raises(EscalationDeniedError, match="lacks ESCALATION_GRANT"):
            EscalationService.grant_escalation(
                token_id=token.id,
                grantor_id="student_001",
                grantor_role=Role.STUDENT
            )

    def test_ttl_respects_max(self):
        """Test that requested TTL is capped at max_ttl_minutes."""
        max_ttl = ConfigRegistry.get(ConfigRegistry.ESCALATION_MAX_TTL)

        with pytest.raises(EscalationDeniedError, match="exceeds maximum"):
            EscalationService.request_escalation(
                user_id="faculty_001",
                requested_permissions=[Permission.MARKS_FINALIZE],
                reason="Too long TTL",
                ttl_minutes=max_ttl + 60  # Exceeds max
            )

    def test_escalation_logged(self):
        """Test that audit entries are created at each lifecycle step."""
        # Request
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Audit test"
        )

        request_logs = AuditLog.query(action=AuditAction.ESCALATION_REQUESTED)
        assert len(request_logs) == 1
        assert request_logs[0].entity_id == token.id

        # Grant
        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        grant_logs = AuditLog.query(action=AuditAction.ESCALATION_GRANTED)
        assert len(grant_logs) == 1
        assert grant_logs[0].actor_id == "admin_001"

        # Revoke
        EscalationService.revoke_escalation(
            token_id=token.id,
            actor_id="admin_001",
            reason="Test complete"
        )

        revoke_logs = AuditLog.query(action=AuditAction.ESCALATION_REVOKED)
        assert len(revoke_logs) == 1

    def test_deny_escalation(self):
        """Test denying an escalation request."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Testing deny"
        )

        denied = EscalationService.deny_escalation(
            token_id=token.id,
            denier_id="admin_001",
            reason="Not justified"
        )

        assert denied.state == EscalationState.DENIED
        deny_logs = AuditLog.query(action=AuditAction.ESCALATION_DENIED)
        assert len(deny_logs) == 1


# ===========================================================
# TEST CLASS 2: DUAL CONTROL GUARD
# ===========================================================

class TestDualControl:
    """Tests for dual approval enforcement on critical operations."""

    def test_register_critical_operation(self):
        """Test that registration creates an approval config."""
        DualControlGuard.initialize_defaults()

        assert DualControlGuard.is_critical_operation("result_publish")
        assert DualControlGuard.is_critical_operation("payroll_release")
        assert DualControlGuard.is_critical_operation("transcript_seal")

        op = DualControlGuard.get_operation("result_publish")
        assert op is not None
        assert op.name == "Result Publication"
        assert Role.DEAN in op.required_roles
        assert Role.REGISTRAR in op.required_roles

    def test_dual_control_required(self):
        """Test that critical op without approval raises DualControlRequiredError."""
        DualControlGuard.initialize_defaults()

        with pytest.raises(DualControlRequiredError, match="result_publish"):
            DualControlGuard.enforce_dual_control(
                operation_id="result_publish",
                entity_type="exam",
                entity_id="EXAM-2024"
            )

    def test_dual_control_partial_approval(self):
        """Test that one approval is not sufficient for ALL mode."""
        DualControlGuard.initialize_defaults()

        # Initiate dual control request
        request_id = DualControlGuard.require_dual_control(
            operation_id="result_publish",
            actor_id="registrar_001",
            entity_type="exam",
            entity_id="EXAM-2024"
        )

        # Only DEAN approves (need DEAN + REGISTRAR)
        ApprovalService.approve(
            request_id=request_id,
            approver_id="dean_001",
            approver_role=Role.DEAN
        )

        # Should still not be verified
        assert DualControlGuard.verify_dual_control(
            operation_id="result_publish",
            entity_type="exam",
            entity_id="EXAM-2024"
        ) is False

    def test_dual_control_full_approval(self):
        """Test that both roles approving passes dual control."""
        DualControlGuard.initialize_defaults()

        # Initiate
        request_id = DualControlGuard.require_dual_control(
            operation_id="result_publish",
            actor_id="registrar_001",
            entity_type="exam",
            entity_id="EXAM-2024"
        )

        # DEAN approves
        ApprovalService.approve(
            request_id=request_id,
            approver_id="dean_001",
            approver_role=Role.DEAN
        )

        # REGISTRAR approves
        ApprovalService.approve(
            request_id=request_id,
            approver_id="registrar_001",
            approver_role=Role.REGISTRAR
        )

        # Should pass
        assert DualControlGuard.verify_dual_control(
            operation_id="result_publish",
            entity_type="exam",
            entity_id="EXAM-2024"
        ) is True

        # Enforcement should not raise
        DualControlGuard.enforce_dual_control(
            operation_id="result_publish",
            entity_type="exam",
            entity_id="EXAM-2024"
        )

    def test_non_critical_operation_passes(self):
        """Test that unregistered operations skip dual control."""
        DualControlGuard.initialize_defaults()

        # This should not raise — "student_create" is not a critical operation
        DualControlGuard.enforce_dual_control(
            operation_id="student_create",
            entity_type="student",
            entity_id="STU-001"
        )

    def test_dual_control_logged(self):
        """Test that dual control events are audit-logged."""
        DualControlGuard.initialize_defaults()

        request_id = DualControlGuard.require_dual_control(
            operation_id="result_publish",
            actor_id="registrar_001",
            entity_type="exam",
            entity_id="EXAM-2024"
        )

        dc_logs = AuditLog.query(action=AuditAction.DUAL_CONTROL_REQUESTED)
        assert len(dc_logs) == 1
        assert dc_logs[0].entity_id == "EXAM-2024"

    def test_critical_operations_from_config(self):
        """Test that default critical operations are loaded from config."""
        # Verify config exists
        critical_ops = ConfigRegistry.get(ConfigRegistry.ESCALATION_CRITICAL_OPERATIONS)
        assert critical_ops is not None
        assert "result_publish" in critical_ops
        assert "payroll_release" in critical_ops
        assert "transcript_seal" in critical_ops


# ===========================================================
# TEST CLASS 3: TOKEN VALIDATION
# ===========================================================

class TestTokenValidation:
    """Tests for token scope, permission, and expiry validation."""

    def test_check_escalation_returns_active_token(self):
        """Test that check_escalation finds a valid active token."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Validation test"
        )

        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        result = EscalationService.check_escalation(
            user_id="faculty_001",
            permission=Permission.MARKS_FINALIZE
        )

        assert result is not None
        assert result.id == token.id
        assert result.is_active()

    def test_check_escalation_expired_returns_none(self):
        """Test that expired tokens return None."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Expiry test"
        )

        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        # Force expire
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        result = EscalationService.check_escalation(
            user_id="faculty_001",
            permission=Permission.MARKS_FINALIZE
        )

        assert result is None

    def test_check_escalation_wrong_permission_returns_none(self):
        """Test that scoped tokens don't match wrong permissions."""
        token = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Scope test"
        )

        EscalationService.grant_escalation(
            token_id=token.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        # Check for a DIFFERENT permission
        result = EscalationService.check_escalation(
            user_id="faculty_001",
            permission=Permission.RESULT_PUBLISH  # Not what was granted!
        )

        assert result is None

    def test_multiple_active_tokens(self):
        """Test that a user can have multiple scoped tokens."""
        # Token 1: MARKS_FINALIZE
        token1 = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.MARKS_FINALIZE],
            reason="Token 1"
        )
        EscalationService.grant_escalation(
            token_id=token1.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        # Token 2: RESULT_PUBLISH
        token2 = EscalationService.request_escalation(
            user_id="faculty_001",
            requested_permissions=[Permission.RESULT_PUBLISH],
            reason="Token 2"
        )
        EscalationService.grant_escalation(
            token_id=token2.id,
            grantor_id="admin_001",
            grantor_role=Role.ADMIN
        )

        active = EscalationService.get_active_tokens("faculty_001")
        assert len(active) == 2

        # Both should individually resolve
        r1 = EscalationService.check_escalation(
            "faculty_001", Permission.MARKS_FINALIZE
        )
        r2 = EscalationService.check_escalation(
            "faculty_001", Permission.RESULT_PUBLISH
        )
        assert r1 is not None
        assert r2 is not None
        assert r1.id != r2.id
