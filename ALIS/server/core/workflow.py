"""
ALIS Workflow Engine - E02-S01: Workflow Engine

MODULE: Shared Services
LAYER: Layer 2-6 Integration
ENTITY: BaseWorkflow

This module implements the BaseWorkflow abstract class that all ALIS
wizards/workflows must inherit from.

Must Align With:
- Layer 2 (Wizards & Decisions) - Decision declaration mandatory
- Layer 3 (State Machines) - Transitions via StateRegistry
- Layer 4 (Global Locks) - Lock checks before execution
- Layer 5 (Authority) - Approval enforcement
- Layer 6 (Resilience) - Provisional handling

Acceptance Criteria:
- [x] Define workflow templates declaratively
- [x] Support states: CREATED, IN_PROGRESS, APPROVED, REJECTED, COMPLETED
- [x] Workflow instances are auditable
- [x] No domain logic inside engine
- [x] Illegal transitions rejected

Blueprint: This is a Rule Engine (Blueprint A) wrapper that orchestrates
domain-specific logic. The engine itself contains NO domain logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime

from .state_registry import StateRegistry, WorkflowState, TransitionResult
from .audit import AuditLog, AuditAction
from .locks import check_global_locks, LockCheckResult, LockType
from .workflow_schema import (
    WorkflowContext,
    WorkflowInstance,
    StepResult,
    StepOutcome,
    WorkflowDecision,
    AuthorityLevel,
)


class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class IllegalTransitionError(WorkflowError):
    """Raised when an illegal state transition is attempted."""
    pass


class GlobalLockViolationError(WorkflowError):
    """Raised when a global lock prevents workflow execution."""
    def __init__(self, violations: List[str]):
        self.violations = violations
        super().__init__(f"Global locks active: {', '.join(violations)}")


class BaseWorkflow(ABC):
    """
    Abstract base class for all ALIS workflows/wizards.

    This implements the Template Method pattern:
    - The engine controls the execution flow (Layer 3 compliance)
    - Subclasses implement domain-specific logic via abstract methods

    Declarative Definition:
    - Subclasses declare their behavior by overriding class attributes
      and abstract methods, NOT by external configuration files.

    Example:
        class ApplicantWizard(BaseWorkflow):
            workflow_type = "admissions.applicant"
            required_locks = [LockType.DOCUMENT_INCOMPLETE]

            def _execute_logic(self, context):
                # Domain logic here
                return StepResult(outcome=StepOutcome.SUCCESS, ...)
    """

    # --- Declarative Configuration (Override in Subclasses) ---

    workflow_type: str = "base.workflow"  # Must be overridden
    required_locks: List[LockType] = []  # Locks to check before execution
    requires_approval: bool = False  # If True, enters AWAITING_APPROVAL

    # --- Instance State ---

    def __init__(self, context: WorkflowContext):
        """
        Initialize a new workflow instance.

        Args:
            context: The WorkflowContext with actor, entity, and data.
        """
        self.context = context
        self.instance = WorkflowInstance(
            workflow_type=self.workflow_type,
            context=context,
            current_state=WorkflowState.CREATED,
        )
        self._decision: Optional[WorkflowDecision] = None

        # Audit: Log creation
        self._log_audit(
            action=AuditAction.CREATE,
            detail=f"Workflow created: {self.workflow_type}"
        )

    # --- Public API ---

    def execute(self) -> WorkflowInstance:
        """
        Execute the workflow.

        This is the main entry point. It orchestrates:
        1. Global Lock check (Layer 4)
        2. State transition to IN_PROGRESS (Layer 3)
        3. Domain logic execution (via subclass)
        4. Decision handling (Layer 2)
        5. Final state transition

        Returns:
            The completed WorkflowInstance.

        Raises:
            GlobalLockViolationError: If any global lock is active.
            IllegalTransitionError: If a state transition is invalid.
        """
        # Step 1: Check Global Locks (Layer 4 - BEFORE all decisions)
        lock_result = self._check_locks()
        if lock_result.is_locked:
            self._transition_to(WorkflowState.FAILED)
            raise GlobalLockViolationError(lock_result.reasons)

        # Step 2: Transition to IN_PROGRESS
        self._transition_to(WorkflowState.IN_PROGRESS)

        # Step 3: Execute domain logic
        try:
            step_result = self._execute_logic(self.context)
            self.instance.step_history.append(step_result)
        except Exception as e:
            # Domain logic failed, transition to FAILED
            self._transition_to(WorkflowState.FAILED)
            self._log_audit(
                action=AuditAction.STATE_TRANSITION,
                detail=f"Workflow failed: {str(e)}",
                success=False
            )
            raise

        # Step 4: Handle step outcome
        if step_result.outcome == StepOutcome.BLOCKED:
            self._transition_to(WorkflowState.FAILED)
            return self.instance

        if step_result.outcome == StepOutcome.REQUIRES_APPROVAL or self.requires_approval:
            self._transition_to(WorkflowState.AWAITING_APPROVAL)
            return self.instance

        if step_result.outcome == StepOutcome.FAILURE:
            self._transition_to(WorkflowState.FAILED)
            return self.instance

        # Step 5: Success path
        self._transition_to(WorkflowState.COMPLETED)
        return self.instance

    def approve(self, approver_id: str, approver_role: str) -> WorkflowInstance:
        """
        Approve a workflow that is AWAITING_APPROVAL.

        Args:
            approver_id: ID of the approving actor.
            approver_role: Role of the approving actor.

        Returns:
            The updated WorkflowInstance.
        """
        if self.instance.current_state != WorkflowState.AWAITING_APPROVAL:
            raise WorkflowError(
                f"Cannot approve workflow in state {self.instance.current_state}"
            )

        self._transition_to(WorkflowState.APPROVED)

        # Log approval
        self._log_audit(
            action=AuditAction.OVERRIDE_APPROVED,
            detail=f"Approved by {approver_role}:{approver_id}"
        )

        # Continue to completion
        self._transition_to(WorkflowState.COMPLETED)
        return self.instance

    def reject(self, rejector_id: str, rejector_role: str, reason: str) -> WorkflowInstance:
        """
        Reject a workflow that is AWAITING_APPROVAL.

        Args:
            rejector_id: ID of the rejecting actor.
            rejector_role: Role of the rejecting actor.
            reason: Reason for rejection.

        Returns:
            The updated WorkflowInstance.
        """
        if self.instance.current_state != WorkflowState.AWAITING_APPROVAL:
            raise WorkflowError(
                f"Cannot reject workflow in state {self.instance.current_state}"
            )

        self._transition_to(WorkflowState.REJECTED)

        # Log rejection
        self._log_audit(
            action=AuditAction.OVERRIDE_REJECTED,
            detail=f"Rejected by {rejector_role}:{rejector_id}: {reason}"
        )

        # Close workflow
        self._transition_to(WorkflowState.CLOSED)
        return self.instance

    def get_decision(self) -> Optional[WorkflowDecision]:
        """Get the decision made by this workflow (if any)."""
        return self._decision

    # --- Abstract Methods (Subclasses MUST Implement) ---

    @abstractmethod
    def _execute_logic(self, context: WorkflowContext) -> StepResult:
        """
        Execute the domain-specific workflow logic.

        This is where subclasses implement their business rules.
        The engine handles all Layer 3-6 concerns; this method
        focuses only on Layer 2 (the decision).

        Args:
            context: The workflow context.

        Returns:
            StepResult indicating the outcome of the step.
        """
        pass

    # --- Protected Methods ---

    def _check_locks(self) -> LockCheckResult:
        """
        Check global locks for the target entity.

        Layer 4 Enforcement: This is called BEFORE any decision.
        """
        if not self.context.entity_id:
            # No entity to check locks for
            return LockCheckResult(is_locked=False)

        return check_global_locks(
            entity_id=self.context.entity_id,
            context=self.context.data,
            required_locks=self.required_locks if self.required_locks else None
        )

    def _transition_to(self, new_state: WorkflowState) -> None:
        """
        Transition the workflow to a new state.

        Layer 3 Enforcement: Validates via StateRegistry.
        """
        current = self.instance.current_state
        result: TransitionResult = StateRegistry.validate_transition(
            entity_type="workflow",
            from_state=current,
            to_state=new_state
        )

        if not result.allowed:
            raise IllegalTransitionError(result.reason)

        # Execute transition
        previous_state = current.value
        self.instance.current_state = new_state
        self.instance.updated_at = datetime.utcnow()

        if new_state in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CLOSED):
            self.instance.completed_at = datetime.utcnow()

        # Audit: Log state transition
        self._log_audit(
            action=AuditAction.STATE_TRANSITION,
            detail=f"State: {previous_state} → {new_state.value}",
            previous_state=previous_state,
            new_state=new_state.value
        )

    def _log_audit(
        self,
        action: AuditAction,
        detail: str,
        success: bool = True,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None
    ) -> None:
        """Log an audit entry for this workflow."""
        entry = AuditLog.log(
            action=action,
            actor_id=self.context.actor_id,
            actor_type=self.context.actor_type,
            entity_type="workflow",
            entity_id=self.instance.id,
            success=success,
            actor_role=self.context.actor_role,
            action_detail=detail,
            org_id=self.context.org_id,
            wizard=self.workflow_type,
            previous_state=previous_state,
            new_state=new_state,
            metadata={"workflow_type": self.workflow_type}
        )
        self.instance.audit_trail.append(entry.id)

    def _set_decision(self, decision: WorkflowDecision) -> None:
        """
        Set the decision for this workflow.

        Layer 2 Mandate: Every wizard MUST end in a decision.
        """
        self._decision = decision
        self.instance.decision = decision

        self._log_audit(
            action=AuditAction.AGENT_DECISION,
            detail=f"Decision: {decision.decision_made}"
        )
