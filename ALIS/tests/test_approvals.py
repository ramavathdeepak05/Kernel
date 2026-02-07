"""
Unit Tests for ALIS Approval & Quorum Framework

Tests:
1. Single approver workflow
2. Quorum (M-of-N) workflow
3. ALL roles must approve workflow
4. Rejection terminates request
5. Unauthorized approver error
6. Duplicate approval error
"""

import pytest
from datetime import datetime

from server.core.approvals import (
    ApprovalService,
    ApprovalConfig,
    ApprovalRequest,
    ApprovalState,
    ApprovalMode,
)
from server.core.rbac import Role


# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_service():
    """Reset the service state before each test."""
    ApprovalService._requests = {}
    ApprovalService._configs = {}
    yield


@pytest.fixture
def single_approver_config():
    """Config requiring a single approver from HOD or DEAN."""
    config = ApprovalConfig(
        config_id="single_approver_test",
        allowed_roles=[Role.HOD, Role.DEAN],
        mode=ApprovalMode.SINGLE,
        description="Single approver test config"
    )
    ApprovalService.register_config(config)
    return config


@pytest.fixture
def quorum_config():
    """Config requiring 2 approvals from HOD, DEAN, or REGISTRAR."""
    config = ApprovalConfig(
        config_id="quorum_test",
        allowed_roles=[Role.HOD, Role.DEAN, Role.REGISTRAR],
        mode=ApprovalMode.ANY,
        quorum_count=2,
        description="Quorum (2-of-3) test config"
    )
    ApprovalService.register_config(config)
    return config


@pytest.fixture
def all_roles_config():
    """Config requiring ALL listed roles to approve."""
    config = ApprovalConfig(
        config_id="all_roles_test",
        allowed_roles=[Role.HOD, Role.DEAN],
        mode=ApprovalMode.ALL,
        description="All roles required test config"
    )
    ApprovalService.register_config(config)
    return config


# --- Test: Single Approver Workflow ---

class TestSingleApproverWorkflow:
    """Tests for single approver mode."""

    def test_create_request(self, single_approver_config):
        """Test creating an approval request."""
        request = ApprovalService.create_request(
            entity_type="invoice",
            entity_id="INV-001",
            action_type="refund",
            config_id="single_approver_test",
            requested_by="user_001"
        )

        assert request.id is not None
        assert request.status == ApprovalState.PENDING
        assert request.entity_type == "invoice"
        assert request.entity_id == "INV-001"
        assert request.mode == ApprovalMode.SINGLE

    def test_single_approval_resolves(self, single_approver_config):
        """Test that a single approval resolves the request."""
        request = ApprovalService.create_request(
            entity_type="invoice",
            entity_id="INV-002",
            action_type="refund",
            config_id="single_approver_test",
            requested_by="user_001"
        )

        # Approve
        updated = ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD,
            comment="Approved"
        )

        assert updated.status == ApprovalState.APPROVED
        assert updated.approval_count == 1
        assert ApprovalService.is_approved(request.id)


# --- Test: Quorum Workflow ---

class TestQuorumWorkflow:
    """Tests for M-of-N quorum mode."""

    def test_quorum_not_met_with_one_approval(self, quorum_config):
        """Test that one approval does not meet quorum."""
        request = ApprovalService.create_request(
            entity_type="curriculum",
            entity_id="CURR-001",
            action_type="change",
            config_id="quorum_test",
            requested_by="faculty_001"
        )

        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # Still pending (need 2)
        assert ApprovalService.get_status(request.id) == ApprovalState.PENDING
        assert request.approval_count == 1

    def test_quorum_met_with_two_approvals(self, quorum_config):
        """Test that two approvals meet quorum."""
        request = ApprovalService.create_request(
            entity_type="curriculum",
            entity_id="CURR-002",
            action_type="change",
            config_id="quorum_test",
            requested_by="faculty_001"
        )

        # First approval
        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # Second approval
        ApprovalService.approve(
            request_id=request.id,
            approver_id="dean_001",
            approver_role=Role.DEAN
        )

        assert ApprovalService.get_status(request.id) == ApprovalState.APPROVED
        assert request.approval_count == 2


# --- Test: ALL Roles Workflow ---

class TestAllRolesWorkflow:
    """Tests for ALL roles must approve mode."""

    def test_all_roles_not_met_with_one(self, all_roles_config):
        """Test that one role is not enough for ALL mode."""
        request = ApprovalService.create_request(
            entity_type="policy",
            entity_id="POL-001",
            action_type="update",
            config_id="all_roles_test",
            requested_by="admin_001"
        )

        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # Still pending (need both HOD and DEAN)
        assert request.status == ApprovalState.PENDING

    def test_all_roles_met(self, all_roles_config):
        """Test that all roles approving resolves request."""
        request = ApprovalService.create_request(
            entity_type="policy",
            entity_id="POL-002",
            action_type="update",
            config_id="all_roles_test",
            requested_by="admin_001"
        )

        # HOD approves
        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # DEAN approves
        ApprovalService.approve(
            request_id=request.id,
            approver_id="dean_001",
            approver_role=Role.DEAN
        )

        assert request.status == ApprovalState.APPROVED


# --- Test: Rejection ---

class TestRejection:
    """Tests for rejection workflow."""

    def test_rejection_terminates_request(self, single_approver_config):
        """Test that rejection immediately terminates."""
        request = ApprovalService.create_request(
            entity_type="invoice",
            entity_id="INV-003",
            action_type="refund",
            config_id="single_approver_test",
            requested_by="user_001"
        )

        ApprovalService.reject(
            request_id=request.id,
            rejector_id="hod_001",
            rejector_role=Role.HOD,
            comment="Invalid request"
        )

        assert request.status == ApprovalState.REJECTED
        assert request.rejection_count == 1


# --- Test: Error Cases ---

class TestErrorCases:
    """Tests for error handling."""

    def test_unauthorized_approver(self, single_approver_config):
        """Test that unauthorized role cannot approve."""
        request = ApprovalService.create_request(
            entity_type="invoice",
            entity_id="INV-004",
            action_type="refund",
            config_id="single_approver_test",
            requested_by="user_001"
        )

        # STUDENT is not an allowed role
        with pytest.raises(ValueError, match="not authorized"):
            ApprovalService.approve(
                request_id=request.id,
                approver_id="student_001",
                approver_role=Role.STUDENT
            )

    def test_duplicate_approval(self, quorum_config):
        """Test that same user cannot approve twice."""
        request = ApprovalService.create_request(
            entity_type="curriculum",
            entity_id="CURR-003",
            action_type="change",
            config_id="quorum_test",
            requested_by="faculty_001"
        )

        # First approval
        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # Same user tries again
        with pytest.raises(ValueError, match="already taken action"):
            ApprovalService.approve(
                request_id=request.id,
                approver_id="hod_001",
                approver_role=Role.DEAN  # Different role, same user
            )

    def test_approve_resolved_request(self, single_approver_config):
        """Test that resolved request cannot be approved."""
        request = ApprovalService.create_request(
            entity_type="invoice",
            entity_id="INV-005",
            action_type="refund",
            config_id="single_approver_test",
            requested_by="user_001"
        )

        # Approve to resolve
        ApprovalService.approve(
            request_id=request.id,
            approver_id="hod_001",
            approver_role=Role.HOD
        )

        # Try to approve again
        with pytest.raises(ValueError, match="already resolved"):
            ApprovalService.approve(
                request_id=request.id,
                approver_id="dean_001",
                approver_role=Role.DEAN
            )

    def test_unknown_config(self):
        """Test that unknown config raises error."""
        with pytest.raises(ValueError, match="Unknown approval config"):
            ApprovalService.create_request(
                entity_type="test",
                entity_id="TEST-001",
                action_type="test",
                config_id="nonexistent_config",
                requested_by="user_001"
            )
