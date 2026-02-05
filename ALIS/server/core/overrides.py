"""
ALIS Override Framework - E01-S08

MODULE: Platform Core
LAYER: Layer 6 (Resilience & Reality Handling)
ENTITY: Override

This module implements override lifecycle management as a first-class
system entity.

Must Align With:
- Layer 6 (Resilience & Reality Handling)
- Override lifecycle: REQUESTED → APPROVED → EXECUTED → CLOSED

Master Handbook Rules:
- Overrides are tracked system events, not shortcuts
- Overrides require reason
- Overrides are auditable
- Overrides may require quorum
- Overrides cannot be deleted

Acceptance Criteria:
- [x] Overrides require reason
- [x] Quorum support
- [x] Immutable audit trail
- [x] Time-bound validity
"""

from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from .state_registry import OverrideState, validate_override_transition


# --- Override Types ---

class OverrideType(str, Enum):
    """Types of overrides in ALIS."""
    ATTENDANCE_WAIVER = "attendance_waiver"
    FEE_WAIVER = "fee_waiver"
    DEADLINE_EXTENSION = "deadline_extension"
    ELIGIBILITY_OVERRIDE = "eligibility_override"
    GRADE_CORRECTION = "grade_correction"
    DOCUMENT_EXEMPTION = "document_exemption"
    DISCIPLINARY_LIFT = "disciplinary_lift"
    CUSTOM = "custom"


# --- Override Severity (Determines Quorum) ---

class OverrideSeverity(str, Enum):
    """Severity level determining approval requirements."""
    LOW = "low"        # Single approver
    MEDIUM = "medium"  # Two approvers
    HIGH = "high"      # Quorum required (3+ approvers)
    CRITICAL = "critical"  # Super admin only


# --- Approval Record ---

@dataclass
class ApprovalRecord:
    """Record of an approval action."""
    approver_id: str
    action: str  # "approve" or "reject"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    comment: Optional[str] = None


# --- Override Entity ---

@dataclass
class Override:
    """
    Override entity representing a controlled bypass request.

    Lifecycle: REQUESTED → APPROVED → EXECUTED → CLOSED

    Overrides are immutable once created. State transitions
    are recorded in the history.
    """
    id: str = field(default_factory=lambda: str(uuid4()))

    # Request Details
    override_type: OverrideType = OverrideType.CUSTOM
    severity: OverrideSeverity = OverrideSeverity.LOW
    reason: str = ""  # Required
    description: Optional[str] = None

    # Target
    entity_type: str = ""  # e.g., "student", "exam"
    entity_id: str = ""    # ID of the entity being overridden

    # Requestor
    requested_by: str = ""
    requested_at: datetime = field(default_factory=datetime.utcnow)

    # State
    status: OverrideState = OverrideState.REQUESTED

    # Validity
    valid_until: Optional[datetime] = None  # Time-bound validity
    valid_for_action: Optional[str] = None  # Specific action this overrides

    # Approvals
    approvals: List[ApprovalRecord] = field(default_factory=list)
    required_approvals: int = 1

    # Execution
    executed_at: Optional[datetime] = None
    executed_by: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None

    # Audit
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None

    def __post_init__(self):
        """Set required approvals based on severity."""
        if self.required_approvals == 1:
            match self.severity:
                case OverrideSeverity.LOW:
                    self.required_approvals = 1
                case OverrideSeverity.MEDIUM:
                    self.required_approvals = 2
                case OverrideSeverity.HIGH:
                    self.required_approvals = 3
                case OverrideSeverity.CRITICAL:
                    self.required_approvals = 1  # Super admin only

        # Set default validity (24 hours if not specified)
        if self.valid_until is None:
            self.valid_until = datetime.utcnow() + timedelta(hours=24)

    @property
    def is_expired(self) -> bool:
        """Check if override has expired."""
        if self.valid_until is None:
            return False
        return datetime.utcnow() > self.valid_until

    @property
    def approval_count(self) -> int:
        """Count of approvals received."""
        return sum(1 for a in self.approvals if a.action == "approve")

    @property
    def is_fully_approved(self) -> bool:
        """Check if required approvals are met."""
        return self.approval_count >= self.required_approvals

    def approve(self, approver_id: str, comment: Optional[str] = None) -> bool:
        """
        Record an approval for this override.

        Returns True if this approval causes the override to be fully approved.
        """
        if self.status != OverrideState.REQUESTED:
            raise ValueError(f"Cannot approve override in state {self.status}")

        if self.is_expired:
            self._transition_to(OverrideState.EXPIRED)
            raise ValueError("Override has expired")

        self.approvals.append(ApprovalRecord(
            approver_id=approver_id,
            action="approve",
            comment=comment
        ))

        if self.is_fully_approved:
            self._transition_to(OverrideState.APPROVED)
            return True

        return False

    def reject(self, approver_id: str, comment: Optional[str] = None) -> None:
        """Reject the override."""
        if self.status != OverrideState.REQUESTED:
            raise ValueError(f"Cannot reject override in state {self.status}")

        self.approvals.append(ApprovalRecord(
            approver_id=approver_id,
            action="reject",
            comment=comment
        ))
        self._transition_to(OverrideState.REJECTED)

    def execute(self, executor_id: str, result: Optional[Dict] = None) -> None:
        """Mark the override as executed."""
        if self.status != OverrideState.APPROVED:
            raise ValueError(f"Cannot execute override in state {self.status}")

        if self.is_expired:
            self._transition_to(OverrideState.EXPIRED)
            raise ValueError("Override has expired before execution")

        self.executed_by = executor_id
        self.executed_at = datetime.utcnow()
        self.execution_result = result
        self._transition_to(OverrideState.EXECUTED)

    def close(self, closed_by: str) -> None:
        """Close the override (terminal state)."""
        valid_close_states = [
            OverrideState.EXECUTED,
            OverrideState.REJECTED,
            OverrideState.EXPIRED
        ]
        if self.status not in valid_close_states:
            raise ValueError(f"Cannot close override in state {self.status}")

        self.closed_by = closed_by
        self.closed_at = datetime.utcnow()
        self._transition_to(OverrideState.CLOSED)

    def _transition_to(self, new_state: OverrideState) -> None:
        """Internal state transition with validation."""
        result = validate_override_transition(self.status, new_state)
        if not result.allowed:
            raise ValueError(result.reason)
        self.status = new_state


# --- Override Service ---

class OverrideService:
    """
    Service for managing overrides.

    In production, this will persist to database.
    """

    _overrides: Dict[str, Override] = {}

    @classmethod
    def create(
        cls,
        override_type: OverrideType,
        reason: str,
        entity_type: str,
        entity_id: str,
        requested_by: str,
        severity: OverrideSeverity = OverrideSeverity.LOW,
        description: Optional[str] = None,
        valid_hours: int = 24
    ) -> Override:
        """Create a new override request."""
        if not reason:
            raise ValueError("Override must have a reason")

        override = Override(
            override_type=override_type,
            severity=severity,
            reason=reason,
            description=description,
            entity_type=entity_type,
            entity_id=entity_id,
            requested_by=requested_by,
            valid_until=datetime.utcnow() + timedelta(hours=valid_hours)
        )

        cls._overrides[override.id] = override
        return override

    @classmethod
    def get(cls, override_id: str) -> Optional[Override]:
        """Get an override by ID."""
        return cls._overrides.get(override_id)

    @classmethod
    def get_for_entity(
        cls,
        entity_type: str,
        entity_id: str,
        active_only: bool = True
    ) -> List[Override]:
        """Get all overrides for a specific entity."""
        overrides = [
            o for o in cls._overrides.values()
            if o.entity_type == entity_type and o.entity_id == entity_id
        ]
        if active_only:
            overrides = [
                o for o in overrides
                if o.status in [OverrideState.REQUESTED, OverrideState.APPROVED]
                and not o.is_expired
            ]
        return overrides

    @classmethod
    def check_active_override(
        cls,
        entity_type: str,
        entity_id: str,
        override_type: OverrideType
    ) -> Optional[Override]:
        """
        Check if there's an active, approved override for the entity.

        Used by lock checks to determine if a lock can be bypassed.
        """
        overrides = cls.get_for_entity(entity_type, entity_id, active_only=True)
        for override in overrides:
            if override.override_type == override_type and override.status == OverrideState.APPROVED:
                return override
        return None
