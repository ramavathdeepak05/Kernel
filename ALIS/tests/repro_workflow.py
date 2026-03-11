"""
ALIS Workflow Engine - Verification Script

This script verifies E02-S01 implementation by testing:
1. Happy path: Workflow creation → execution → completion
2. Global Lock enforcement: Workflow blocked by active lock
3. Illegal transition rejection: Invalid state transitions fail
4. Approval flow: AWAITING_APPROVAL → APPROVED → COMPLETED

Run with: python -m tests.repro_workflow
"""

import sys
from pathlib import Path

# Add server to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.core.state_registry import WorkflowState, StateRegistry
from server.core.workflow_schema import WorkflowContext, StepResult, StepOutcome, WorkflowDecision
from server.core.workflow import BaseWorkflow, GlobalLockViolationError, IllegalStateTransitionError
from server.core.locks import GlobalLockRegistry, LockType, LockStatus
from server.core.audit import AuditLog, AuditAction


# --- Test Workflow Implementations ---

class MockApplicantWizard(BaseWorkflow):
    """Test workflow: Simple admission applicant processing."""

    workflow_type = "admissions.applicant"
    required_locks = [LockType.DOCUMENT_INCOMPLETE]
    requires_approval = False

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        # Simulate processing applicant
        applicant_name = context.data.get("name", "Unknown")
        return StepResult(
            outcome=StepOutcome.SUCCESS,
            step_name="process_applicant",
            message=f"Processed applicant: {applicant_name}",
            data={"name": applicant_name, "score": 85}
        )


class MockApprovalWizard(BaseWorkflow):
    """Test workflow: Requires human approval."""

    workflow_type = "finance.refund"
    requires_approval = True

    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        amount = context.data.get("amount", 0)
        return StepResult(
            outcome=StepOutcome.SUCCESS,
            step_name="request_refund",
            message=f"Refund request: ${amount}",
            data={"amount": amount}
        )


# --- Test Functions ---

def test_happy_path():
    """Test: Workflow executes successfully."""
    print("\n" + "=" * 60)
    print("TEST 1: Happy Path (CREATED → IN_PROGRESS → COMPLETED)")
    print("=" * 60)

    context = WorkflowContext(
        workflow_type="admissions.applicant",
        actor_id="user-001",
        actor_type="human",
        actor_role="admissions_officer",
        entity_type="applicant",
        entity_id="app-12345",
        org_id="org-001",
        data={"name": "John Doe", "missing_documents": []}  # No missing docs
    )

    wizard = MockApplicantWizard(context)
    print(f"Initial State: {wizard.instance.current_state}")

    result = wizard.execute()

    print(f"Final State: {result.current_state}")
    print(f"Step History: {len(result.step_history)} steps")
    print(f"Audit Trail: {len(result.audit_trail)} entries")

    assert result.current_state == WorkflowState.COMPLETED, "Expected COMPLETED"
    print("✓ PASS: Workflow completed successfully")


def test_global_lock_enforcement():
    """Test: Global lock blocks workflow execution."""
    print("\n" + "=" * 60)
    print("TEST 2: Global Lock Enforcement")
    print("=" * 60)

    context = WorkflowContext(
        workflow_type="admissions.applicant",
        actor_id="user-001",
        actor_type="human",
        entity_type="applicant",
        entity_id="app-blocked",
        data={
            "name": "Jane Blocked",
            "missing_documents": ["ID Proof", "Address Proof"]  # This triggers lock
        }
    )

    wizard = MockApplicantWizard(context)
    print(f"Initial State: {wizard.instance.current_state}")
    print(f"Context has missing documents: {context.data['missing_documents']}")

    try:
        wizard.execute()
        print("✗ FAIL: Expected GlobalLockViolationError")
    except GlobalLockViolationError as e:
        print(f"Caught Exception: {e}")
        print(f"Final State: {wizard.instance.current_state}")
        assert wizard.instance.current_state == WorkflowState.FAILED
        print("✓ PASS: Global lock correctly blocked execution")


def test_illegal_transition():
    """Test: Illegal state transitions are rejected."""
    print("\n" + "=" * 60)
    print("TEST 3: Illegal Transition Rejection")
    print("=" * 60)

    # Try to validate an illegal transition directly
    result = StateRegistry.validate_transition(
        entity_type="workflow",
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COMPLETED  # Illegal: must go through IN_PROGRESS
    )

    print(f"Transition CREATED → COMPLETED allowed: {result.allowed}")
    print(f"Reason: {result.reason}")

    assert not result.allowed, "Expected transition to be rejected"
    print("✓ PASS: Illegal transition correctly rejected")


def test_approval_flow():
    """Test: Approval workflow requires human approval."""
    print("\n" + "=" * 60)
    print("TEST 4: Approval Flow")
    print("=" * 60)

    context = WorkflowContext(
        workflow_type="finance.refund",
        actor_id="user-002",
        actor_type="human",
        actor_role="student",
        entity_type="refund_request",
        entity_id="ref-001",
        data={"amount": 5000}
    )

    wizard = MockApprovalWizard(context)
    result = wizard.execute()

    print(f"After Execute State: {result.current_state}")
    assert result.current_state == WorkflowState.AWAITING_APPROVAL

    # Approve
    result = wizard.approve(approver_id="admin-001", approver_role="finance_admin")
    print(f"After Approve State: {result.current_state}")
    assert result.current_state == WorkflowState.COMPLETED
    print("✓ PASS: Approval flow completed correctly")


def test_rejection_flow():
    """Test: Rejection workflow."""
    print("\n" + "=" * 60)
    print("TEST 5: Rejection Flow")
    print("=" * 60)

    context = WorkflowContext(
        workflow_type="finance.refund",
        actor_id="user-003",
        actor_type="human",
        actor_role="student",
        entity_type="refund_request",
        entity_id="ref-002",
        data={"amount": 50000}  # Large amount
    )

    wizard = MockApprovalWizard(context)
    result = wizard.execute()

    print(f"After Execute State: {result.current_state}")
    assert result.current_state == WorkflowState.AWAITING_APPROVAL

    # Reject
    result = wizard.reject(
        rejector_id="admin-001",
        rejector_role="finance_admin",
        reason="Amount exceeds policy limit"
    )
    print(f"After Reject State: {result.current_state}")
    assert result.current_state == WorkflowState.CLOSED
    print("✓ PASS: Rejection flow completed correctly")


def test_audit_trail():
    """Test: Audit entries are created."""
    print("\n" + "=" * 60)
    print("TEST 6: Audit Trail Verification")
    print("=" * 60)

    # Clear existing audit entries for clean test
    AuditLog._entries = []

    context = WorkflowContext(
        workflow_type="admissions.applicant",
        actor_id="user-audit",
        actor_type="human",
        entity_type="applicant",
        entity_id="app-audit-test",
        data={"name": "Audit Test", "missing_documents": []}
    )

    wizard = MockApplicantWizard(context)
    wizard.execute()

    # Query audit entries for this entity
    entries = AuditLog.query(entity_id=wizard.instance.id)
    print(f"Audit entries created: {len(entries)}")

    for entry in entries:
        print(f"  - {entry.action.value}: {entry.action_detail}")

    assert len(entries) >= 3, "Expected at least 3 audit entries (create, in_progress, completed)"
    print("✓ PASS: Audit trail correctly populated")


# --- Main ---

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("ALIS E02-S01 WORKFLOW ENGINE - VERIFICATION SCRIPT")
    print("=" * 60)

    tests = [
        test_happy_path,
        test_global_lock_enforcement,
        test_illegal_transition,
        test_approval_flow,
        test_rejection_flow,
        test_audit_trail,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {test.__name__}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
