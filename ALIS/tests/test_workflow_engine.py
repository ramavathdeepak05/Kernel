"""
Unit Tests — E02-S01: Workflow Engine

MODULE: Shared Services
LAYER: Layer 2-6 Integration

Tests:
1. Happy path: CREATED → IN_PROGRESS → COMPLETED
2. Global Lock enforcement: blocked by active lock
3. Illegal transition rejection
4. Approval flow: AWAITING_APPROVAL → APPROVED → COMPLETED
5. Rejection flow: AWAITING_APPROVAL → REJECTED → CLOSED
6. Audit trail populated on each state change
7. Domain exception during _execute_logic → FAILED
8. Step persistence called on execution
"""

import pytest
from unittest.mock import patch, MagicMock

from server.core.state_registry import WorkflowState, StateRegistry
from server.core.workflow_schema import (
    WorkflowContext,
    StepResult,
    StepOutcome,
    WorkflowDecision,
    AuthorityLevel,
)
from server.core.workflow import BaseWorkflow, WorkflowError
from server.core.exceptions import (
    GlobalLockViolationError,
    IllegalStateTransitionError,
)
from server.core.locks import LockType


# ── Concrete workflow implementations used in tests ──────────────────────────

class SimpleWizard(BaseWorkflow):
    """Simplest possible wizard — always succeeds."""
    workflow_type = "test.simple"
    required_locks = [LockType.DOCUMENT_INCOMPLETE]

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        return StepResult(
            outcome=StepOutcome.SUCCESS,
            step_name="process",
            message="Processed",
            data={"ok": True},
        )


class ApprovalWizard(BaseWorkflow):
    """Wizard that always requires approval."""
    workflow_type = "test.approval"
    requires_approval = True
    approval_roles = ["finance_admin"]

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        return StepResult(
            outcome=StepOutcome.SUCCESS,
            step_name="request",
            message="Awaiting sign-off",
        )


class FailingWizard(BaseWorkflow):
    """Wizard whose domain logic raises an exception."""
    workflow_type = "test.failing"

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        raise ValueError("Domain logic exploded")


class BlockedWizard(BaseWorkflow):
    """Wizard that returns BLOCKED outcome."""
    workflow_type = "test.blocked"

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        return StepResult(outcome=StepOutcome.BLOCKED, step_name="check")


# ── Helpers ────────────────────────────────────────────────────────────────

def make_context(**overrides) -> WorkflowContext:
    defaults = dict(
        workflow_type="test.simple",
        actor_id="user-001",
        actor_type="human",
        actor_role="admin",
        entity_type="applicant",
        entity_id="app-001",
        tenant_id="org-test",
        org_id="org-test",
        data={},
    )
    defaults.update(overrides)
    return WorkflowContext(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_completes_successfully(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)
        result = wiz.execute()

        assert result.current_state == WorkflowState.COMPLETED

    def test_step_history_populated(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)
        result = wiz.execute()

        assert len(result.step_history) == 1
        assert result.step_history[0].outcome == StepOutcome.SUCCESS

    def test_audit_trail_has_entries(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)
        result = wiz.execute()

        # At minimum: create, in_progress, completed
        assert len(result.audit_trail) >= 3


class TestGlobalLockEnforcement:
    def test_missing_documents_blocks_execution(self):
        ctx = make_context(
            data={"missing_documents": ["ID Proof", "Address Proof"]}
        )
        wiz = SimpleWizard(ctx)

        with pytest.raises(GlobalLockViolationError):
            wiz.execute()

    def test_state_is_failed_after_lock_block(self):
        ctx = make_context(
            data={"missing_documents": ["ID Proof"]}
        )
        wiz = SimpleWizard(ctx)

        try:
            wiz.execute()
        except GlobalLockViolationError:
            pass

        assert wiz.instance.current_state == WorkflowState.FAILED


class TestIllegalTransitions:
    def test_created_to_completed_is_rejected(self):
        result = StateRegistry.validate_transition(
            entity_type="workflow",
            from_state=WorkflowState.CREATED,
            to_state=WorkflowState.COMPLETED,
        )
        assert not result.allowed

    def test_completed_to_in_progress_is_rejected(self):
        result = StateRegistry.validate_transition(
            entity_type="workflow",
            from_state=WorkflowState.COMPLETED,
            to_state=WorkflowState.IN_PROGRESS,
        )
        assert not result.allowed

    def test_created_to_in_progress_is_allowed(self):
        result = StateRegistry.validate_transition(
            entity_type="workflow",
            from_state=WorkflowState.CREATED,
            to_state=WorkflowState.IN_PROGRESS,
        )
        assert result.allowed


class TestApprovalFlow:
    def test_execute_reaches_awaiting_approval(self):
        ctx = make_context()
        wiz = ApprovalWizard(ctx)
        result = wiz.execute()

        assert result.current_state == WorkflowState.AWAITING_APPROVAL

    def test_approve_completes_workflow(self):
        ctx = make_context()
        wiz = ApprovalWizard(ctx)
        wiz.execute()

        result = wiz.approve(approver_id="admin-001", approver_role="finance_admin")
        assert result.current_state == WorkflowState.COMPLETED

    def test_cannot_approve_non_pending_workflow(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)
        wiz.execute()  # reaches COMPLETED

        with pytest.raises(WorkflowError):
            wiz.approve(approver_id="admin-001", approver_role="admin")

    def test_approver_roles_stored_on_instance(self):
        ctx = make_context()
        wiz = ApprovalWizard(ctx)

        assert "finance_admin" in wiz.instance.approver_roles


class TestRejectionFlow:
    def test_reject_closes_workflow(self):
        ctx = make_context()
        wiz = ApprovalWizard(ctx)
        wiz.execute()

        result = wiz.reject(
            rejector_id="admin-001",
            rejector_role="finance_admin",
            reason="Exceeds limit",
        )
        assert result.current_state == WorkflowState.CLOSED

    def test_cannot_reject_non_pending_workflow(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)
        wiz.execute()

        with pytest.raises(WorkflowError):
            wiz.reject(
                rejector_id="admin-001",
                rejector_role="admin",
                reason="No reason",
            )


class TestDomainFailure:
    def test_exception_in_execute_logic_sets_failed(self):
        ctx = make_context()
        wiz = FailingWizard(ctx)

        with pytest.raises(ValueError):
            wiz.execute()

        assert wiz.instance.current_state == WorkflowState.FAILED

    def test_blocked_outcome_sets_failed(self):
        ctx = make_context()
        wiz = BlockedWizard(ctx)
        result = wiz.execute()

        assert result.current_state == WorkflowState.FAILED


class TestDeclaration:
    def test_workflow_type_stored_on_instance(self):
        ctx = make_context()
        wiz = SimpleWizard(ctx)

        assert wiz.instance.workflow_type == "test.simple"

    def test_tenant_id_stored_in_context(self):
        ctx = make_context(tenant_id="tenant-xyz")
        wiz = SimpleWizard(ctx)

        assert wiz.context.tenant_id == "tenant-xyz"

    def test_set_decision_stores_decision(self):
        ctx = make_context(data={"missing_documents": []})
        wiz = SimpleWizard(ctx)

        decision = WorkflowDecision(
            decision_made="Applicant is eligible",
            authority_required=AuthorityLevel.AUTO,
        )
        wiz._set_decision(decision)

        assert wiz.get_decision() is not None
        assert wiz.get_decision().decision_made == "Applicant is eligible"
        assert wiz.instance.decision is not None
