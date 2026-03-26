"""
ALIS State Registry - E01-S06: Central State Registry

MODULE: Platform Core
LAYER: Layer 3 (State Machines & Legality)
ENTITY: State, StateTransition

This module implements the canonical state registry and state machine
enforcement defined in Layer 3 of the ALIS Master Architecture.

Must Align With:
- Layer 3 (State Machines & Legality)

Layer 3 Global Rules (from Master Handbook):
1. All entities MUST have an explicit state machine.
2. Backward transitions are forbidden.
3. Invalidation occurs forward via annulment states.
4. Undeclared transitions MUST be rejected at runtime.

Acceptance Criteria:
- [x] Explicit state definitions
- [x] Allowed transition matrix
- [x] Runtime rejection of illegal transitions
- [x] Forward-only invalidation via ANNULLED
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Set, Optional, List
from dataclasses import dataclass


# --- Student State Machine (Canonical) ---

class StudentState(str, Enum):
    """
    Full admissions lifecycle state machine (Stages 1–10).

    Forward-only. CANCELLED is the single terminal invalidation state.

    Stage 1  — Lead
    Stage 2  — Application form (draft → submitted → fee)
    Stage 3  — Documents
    Stage 4  — Eligibility screening
    Stage 5  — Assessment (test / interview)
    Stage 6  — Merit list & selection
    Stage 7  — Offer letter
    Stage 8  — Fee payment & seat confirmation
    Stage 9  — Final document verification
    Stage 10 — Enrollment

    Allowed Transitions:
        LEAD                  → DRAFT | CANCELLED
        DRAFT                 → SUBMITTED | CANCELLED
        SUBMITTED             → PENDING_PAYMENT | DOCUMENTS_PENDING | CANCELLED
        PENDING_PAYMENT       → DOCUMENTS_PENDING | CANCELLED
        DOCUMENTS_PENDING     → UNDER_DOCUMENT_REVIEW | CANCELLED
        UNDER_DOCUMENT_REVIEW → DOCUMENTS_VERIFIED | CANCELLED
        DOCUMENTS_VERIFIED    → ELIGIBLE | NOT_ELIGIBLE | PROVISIONALLY_ELIGIBLE
        ELIGIBLE              → ASSESSMENT_SCHEDULED | MERIT_LISTED | CANCELLED
        NOT_ELIGIBLE          → CANCELLED
        PROVISIONALLY_ELIGIBLE → ELIGIBLE | NOT_ELIGIBLE | CANCELLED
        ASSESSMENT_SCHEDULED  → ASSESSMENT_COMPLETE | CANCELLED
        ASSESSMENT_COMPLETE   → MERIT_LISTED | WAITLISTED | NOT_ELIGIBLE | CANCELLED
        MERIT_LISTED          → OFFER_ISSUED | CANCELLED
        WAITLISTED            → MERIT_LISTED | CANCELLED
        OFFER_ISSUED          → OFFER_ACCEPTED | OFFER_DECLINED | CANCELLED
        OFFER_DECLINED        → CANCELLED
        OFFER_ACCEPTED        → SEAT_CONFIRMED | CANCELLED
        SEAT_CONFIRMED        → VERIFICATION_PENDING | CANCELLED
        VERIFICATION_PENDING  → READY_FOR_ENROLLMENT | CANCELLED
        READY_FOR_ENROLLMENT  → ENROLLED | CANCELLED
        ENROLLED              → CANCELLED
        CANCELLED             → (terminal)

    Legacy aliases kept for pipeline backward-compatibility:
        APPLIED              = SUBMITTED
        ADMITTED             = SEAT_CONFIRMED
        ANNULLED             = CANCELLED
    """
    # Stage 1
    LEAD = "LEAD"

    # Stage 2 — Application form
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_PAYMENT = "PENDING_PAYMENT"         # application fee unpaid

    # Stage 3 — Documents
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING"
    UNDER_DOCUMENT_REVIEW = "UNDER_DOCUMENT_REVIEW"
    DOCUMENTS_VERIFIED = "DOCUMENTS_VERIFIED"

    # Stage 4 — Eligibility
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PROVISIONALLY_ELIGIBLE = "PROVISIONALLY_ELIGIBLE"   # borderline → staff review

    # Stage 5 — Assessment
    ASSESSMENT_SCHEDULED = "ASSESSMENT_SCHEDULED"
    ASSESSMENT_COMPLETE = "ASSESSMENT_COMPLETE"

    # Stage 6 — Merit list
    MERIT_LISTED = "MERIT_LISTED"
    WAITLISTED = "WAITLISTED"

    # Stage 7 — Offer
    OFFER_ISSUED = "OFFER_ISSUED"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"

    # Stage 8 — Payment
    SEAT_CONFIRMED = "SEAT_CONFIRMED"

    # Stage 9 — Final verification
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    READY_FOR_ENROLLMENT = "READY_FOR_ENROLLMENT"

    # Stage 10 — Enrolled
    ENROLLED = "ENROLLED"

    # Terminal — withdrawn at any stage
    CANCELLED = "CANCELLED"

    # --- Legacy aliases (pipeline backward-compatibility) ---
    APPLIED = "SUBMITTED"           # maps to SUBMITTED
    ADMITTED = "SEAT_CONFIRMED"     # maps to SEAT_CONFIRMED
    ANNULLED = "CANCELLED"          # maps to CANCELLED


class ExamState(str, Enum):
    """Exam lifecycle states."""
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    IN_PROGRESS = "IN_PROGRESS"
    EVALUATION_OPEN = "EVALUATION_OPEN"
    EVALUATION_CLOSED = "EVALUATION_CLOSED"
    RESULTS_PUBLISHED = "RESULTS_PUBLISHED"
    ARCHIVED = "ARCHIVED"


class OverrideState(str, Enum):
    """Override lifecycle states (Layer 6)."""
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class WorkflowState(str, Enum):
    """
    Workflow lifecycle states for E02-S01.

    These states apply to all workflows/wizards orchestrated by the
    Shared Workflow Engine. Domain-specific state machines (e.g., Student)
    remain separate.

    Allowed Transitions:
        CREATED → IN_PROGRESS
        IN_PROGRESS → AWAITING_APPROVAL | COMPLETED | FAILED
        AWAITING_APPROVAL → APPROVED | REJECTED
        APPROVED → COMPLETED | FAILED
        REJECTED → CLOSED
        COMPLETED → CLOSED
        FAILED → CLOSED
    """
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"  # Terminal state


# --- Transition Result ---

@dataclass
class TransitionResult:
    """Result of a state transition attempt."""
    allowed: bool
    from_state: str
    to_state: str
    reason: Optional[str] = None


# --- State Transition Matrices ---

STUDENT_TRANSITIONS: Dict[StudentState, Set[StudentState]] = {
    # Stage 1
    StudentState.LEAD: {
        StudentState.DRAFT, StudentState.SUBMITTED, StudentState.CANCELLED
    },
    # Stage 2
    StudentState.DRAFT: {
        StudentState.SUBMITTED, StudentState.CANCELLED
    },
    StudentState.SUBMITTED: {
        StudentState.PENDING_PAYMENT, StudentState.DOCUMENTS_PENDING, StudentState.CANCELLED
    },
    StudentState.PENDING_PAYMENT: {
        StudentState.DOCUMENTS_PENDING, StudentState.CANCELLED
    },
    # Stage 3
    StudentState.DOCUMENTS_PENDING: {
        StudentState.UNDER_DOCUMENT_REVIEW, StudentState.CANCELLED
    },
    StudentState.UNDER_DOCUMENT_REVIEW: {
        StudentState.DOCUMENTS_VERIFIED, StudentState.CANCELLED
        # Note: document rejection is handled at document level, not applicant state.
        # Applicant stays UNDER_DOCUMENT_REVIEW until all docs approved.
    },
    # Stage 4
    StudentState.DOCUMENTS_VERIFIED: {
        StudentState.ELIGIBLE,
        StudentState.NOT_ELIGIBLE,
        StudentState.PROVISIONALLY_ELIGIBLE,
        StudentState.CANCELLED,
    },
    StudentState.ELIGIBLE: {
        StudentState.ASSESSMENT_SCHEDULED,  # if test required
        StudentState.MERIT_LISTED,          # if no test (direct merit)
        StudentState.CANCELLED,
    },
    StudentState.NOT_ELIGIBLE: {StudentState.CANCELLED},
    StudentState.PROVISIONALLY_ELIGIBLE: {
        StudentState.ELIGIBLE, StudentState.NOT_ELIGIBLE, StudentState.CANCELLED
    },
    # Stage 5
    StudentState.ASSESSMENT_SCHEDULED: {
        StudentState.ASSESSMENT_COMPLETE, StudentState.CANCELLED
    },
    StudentState.ASSESSMENT_COMPLETE: {
        StudentState.MERIT_LISTED,
        StudentState.WAITLISTED,
        StudentState.NOT_ELIGIBLE,
        StudentState.CANCELLED,
    },
    # Stage 6
    StudentState.MERIT_LISTED: {
        StudentState.OFFER_ISSUED, StudentState.CANCELLED
    },
    StudentState.WAITLISTED: {
        StudentState.MERIT_LISTED,  # waitlist activation moves to merit
        StudentState.CANCELLED,
    },
    # Stage 7
    StudentState.OFFER_ISSUED: {
        StudentState.OFFER_ACCEPTED, StudentState.OFFER_DECLINED, StudentState.CANCELLED
    },
    StudentState.OFFER_ACCEPTED: {
        StudentState.SEAT_CONFIRMED, StudentState.CANCELLED
    },
    StudentState.OFFER_DECLINED: {StudentState.CANCELLED},
    # Stage 8
    StudentState.SEAT_CONFIRMED: {
        StudentState.VERIFICATION_PENDING, StudentState.CANCELLED
    },
    # Stage 9
    StudentState.VERIFICATION_PENDING: {
        StudentState.READY_FOR_ENROLLMENT, StudentState.CANCELLED
    },
    StudentState.READY_FOR_ENROLLMENT: {
        StudentState.ENROLLED, StudentState.CANCELLED
    },
    # Stage 10
    StudentState.ENROLLED: {StudentState.CANCELLED},
    # Terminal
    StudentState.CANCELLED: set(),
}

EXAM_TRANSITIONS: Dict[ExamState, Set[ExamState]] = {
    ExamState.DRAFT: {ExamState.SCHEDULED},
    ExamState.SCHEDULED: {ExamState.REGISTRATION_OPEN},
    ExamState.REGISTRATION_OPEN: {ExamState.REGISTRATION_CLOSED},
    ExamState.REGISTRATION_CLOSED: {ExamState.IN_PROGRESS},
    ExamState.IN_PROGRESS: {ExamState.EVALUATION_OPEN},
    ExamState.EVALUATION_OPEN: {ExamState.EVALUATION_CLOSED},
    ExamState.EVALUATION_CLOSED: {ExamState.RESULTS_PUBLISHED},
    ExamState.RESULTS_PUBLISHED: {ExamState.ARCHIVED},
    ExamState.ARCHIVED: set(),  # Terminal
}

OVERRIDE_TRANSITIONS: Dict[OverrideState, Set[OverrideState]] = {
    OverrideState.REQUESTED: {
        OverrideState.APPROVED,
        OverrideState.REJECTED,
        OverrideState.EXPIRED
    },
    OverrideState.APPROVED: {OverrideState.EXECUTED, OverrideState.EXPIRED},
    OverrideState.REJECTED: {OverrideState.CLOSED},
    OverrideState.EXECUTED: {OverrideState.CLOSED},
    OverrideState.EXPIRED: {OverrideState.CLOSED},
    OverrideState.CLOSED: set(),  # Terminal
}

WORKFLOW_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.CREATED: {WorkflowState.IN_PROGRESS, WorkflowState.FAILED},
    WorkflowState.IN_PROGRESS: {
        WorkflowState.AWAITING_APPROVAL,
        WorkflowState.COMPLETED,
        WorkflowState.FAILED
    },
    WorkflowState.AWAITING_APPROVAL: {
        WorkflowState.APPROVED,
        WorkflowState.REJECTED
    },
    WorkflowState.APPROVED: {
        WorkflowState.COMPLETED,
        WorkflowState.FAILED
    },
    WorkflowState.REJECTED: {WorkflowState.CLOSED},
    WorkflowState.COMPLETED: {WorkflowState.CLOSED},
    WorkflowState.FAILED: {WorkflowState.CLOSED},
    WorkflowState.CLOSED: set(),  # Terminal
}


# --- State Registry Class ---

class StateRegistry:
    """
    Central State Registry for ALIS.

    Enforces Layer 3 rules:
    - All state transitions must be declared
    - Backward transitions are forbidden
    - Undeclared transitions are rejected at runtime
    """

    # Registry of all transition matrices
    _registries = {
        "student": STUDENT_TRANSITIONS,
        "exam": EXAM_TRANSITIONS,
        "override": OVERRIDE_TRANSITIONS,
        "workflow": WORKFLOW_TRANSITIONS,
    }

    @classmethod
    def register_entity(
        cls,
        entity_type: str,
        transitions: Dict[Enum, Set[Enum]]
    ) -> None:
        """Register a new entity type's state transitions."""
        cls._registries[entity_type] = transitions

    @classmethod
    def get_allowed_transitions(
        cls,
        entity_type: str,
        current_state: Enum
    ) -> Set[Enum]:
        """Get the set of allowed next states from current state."""
        registry = cls._registries.get(entity_type)
        if registry is None:
            return set()
        return registry.get(current_state, set())

    @classmethod
    def validate_transition(
        cls,
        entity_type: str,
        from_state: Enum,
        to_state: Enum
    ) -> TransitionResult:
        """
        Validate a state transition.

        Args:
            entity_type: Type of entity (student, exam, override, etc.)
            from_state: Current state
            to_state: Desired next state

        Returns:
            TransitionResult indicating if transition is allowed

        Layer 3 Enforcement:
            If transition is not declared, it MUST be rejected.
        """
        allowed_states = cls.get_allowed_transitions(entity_type, from_state)

        if to_state in allowed_states:
            return TransitionResult(
                allowed=True,
                from_state=from_state.value if hasattr(from_state, 'value') else str(from_state),
                to_state=to_state.value if hasattr(to_state, 'value') else str(to_state)
            )

        return TransitionResult(
            allowed=False,
            from_state=from_state.value if hasattr(from_state, 'value') else str(from_state),
            to_state=to_state.value if hasattr(to_state, 'value') else str(to_state),
            reason=f"Illegal transition: {from_state.value} → {to_state.value} is not allowed for entity type '{entity_type}'"
        )

    @classmethod
    def execute_transition(
        cls,
        entity_type: str,
        from_state: Enum,
        to_state: Enum
    ) -> TransitionResult:
        """
        Execute a state transition with validation.

        Raises:
            ValueError: If transition is illegal (Layer 3 enforcement)
        """
        result = cls.validate_transition(entity_type, from_state, to_state)

        if not result.allowed:
            raise ValueError(result.reason)

        return result


# --- Convenience Functions ---

def validate_student_transition(
    from_state: StudentState,
    to_state: StudentState
) -> TransitionResult:
    """Validate a student state transition."""
    return StateRegistry.validate_transition("student", from_state, to_state)


def validate_exam_transition(
    from_state: ExamState,
    to_state: ExamState
) -> TransitionResult:
    """Validate an exam state transition."""
    return StateRegistry.validate_transition("exam", from_state, to_state)


def validate_override_transition(
    from_state: OverrideState,
    to_state: OverrideState
) -> TransitionResult:
    """Validate an override state transition."""
    return StateRegistry.validate_transition("override", from_state, to_state)
