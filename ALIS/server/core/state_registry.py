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

from enum import Enum
from typing import Dict, Set, Optional, List
from dataclasses import dataclass


# --- Student State Machine (Canonical) ---

class StudentState(str, Enum):
    """
    Student lifecycle states as defined in the ALIS Master Handbook.

    Allowed Transitions:
        LEAD → APPLIED
        APPLIED → ELIGIBLE | NOT_ELIGIBLE | PROVISIONALLY_ELIGIBLE
        ELIGIBLE → ADMITTED
        PROVISIONALLY_ELIGIBLE → ELIGIBLE | NOT_ELIGIBLE
        ADMITTED → ENROLLED
        ANY → ANNULLED

    Forbidden:
        ENROLLED → APPLIED
        ADMITTED → ELIGIBLE
    """
    LEAD = "LEAD"
    APPLIED = "APPLIED"
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PROVISIONALLY_ELIGIBLE = "PROVISIONALLY_ELIGIBLE"
    ADMITTED = "ADMITTED"
    ENROLLED = "ENROLLED"
    ANNULLED = "ANNULLED"  # Forward-only invalidation


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
    StudentState.LEAD: {StudentState.APPLIED, StudentState.ANNULLED},
    StudentState.APPLIED: {
        StudentState.ELIGIBLE,
        StudentState.NOT_ELIGIBLE,
        StudentState.PROVISIONALLY_ELIGIBLE,
        StudentState.ANNULLED
    },
    StudentState.ELIGIBLE: {StudentState.ADMITTED, StudentState.ANNULLED},
    StudentState.NOT_ELIGIBLE: {StudentState.ANNULLED},
    StudentState.PROVISIONALLY_ELIGIBLE: {
        StudentState.ELIGIBLE,
        StudentState.NOT_ELIGIBLE,
        StudentState.ANNULLED
    },
    StudentState.ADMITTED: {StudentState.ENROLLED, StudentState.ANNULLED},
    StudentState.ENROLLED: {StudentState.ANNULLED},
    StudentState.ANNULLED: set(),  # Terminal state, no transitions allowed
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
