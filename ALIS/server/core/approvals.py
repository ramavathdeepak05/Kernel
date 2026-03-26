"""
ALIS Approval & Quorum Framework - E02-S02

MODULE: Platform Core (Shared Services)
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: ApprovalRequest, ApprovalConfig

This module implements a generic, reusable approval framework supporting:
- Single-approver workflows
- Role-based multi-approver workflows
- M-of-N quorum-based approvals

Must Align With:
- Layer 5 (Roles, Authority & Quorum)
- Event Contract Rule (explicit, auditable)

Master Handbook Rules:
- Irreversible actions require human approval
- Critical actions require multiple approvers (quorum)
- All approvals are logged
- No hard-coded approver logic

Acceptance Criteria:
- [x] Approval rules are configurable per workflow
- [x] Role-based approvers
- [x] Quorum thresholds supported
- [x] Approval actions audited
- [x] No hard-coded approver logic
"""
from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum

from .rbac import Role
from .audit import AuditLog, AuditAction
from .state_registry import StateRegistry, TransitionResult


# --- Approval State Machine ---

class ApprovalState(str, Enum):
    """
    Approval request lifecycle states.

    Allowed Transitions:
        PENDING → APPROVED | REJECTED
        APPROVED → (terminal)
        REJECTED → (terminal)
    """
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Register Approval state transitions
APPROVAL_TRANSITIONS: Dict[ApprovalState, Set[ApprovalState]] = {
    ApprovalState.PENDING: {ApprovalState.APPROVED, ApprovalState.REJECTED},
    ApprovalState.APPROVED: set(),  # Terminal
    ApprovalState.REJECTED: set(),  # Terminal
}

# Register with StateRegistry
StateRegistry.register_entity("approval", APPROVAL_TRANSITIONS)


# --- Approval Mode ---

class ApprovalMode(str, Enum):
    """
    Defines how approvals are evaluated.

    - SINGLE: One approver from any allowed role is sufficient.
    - ANY: Any N approvers from allowed roles (quorum).
    - ALL: All specified roles must approve.
    """
    SINGLE = "single"
    ANY = "any"
    ALL = "all"


# --- Approval Configuration ---

@dataclass
class ApprovalConfig:
    """
    Configuration defining approval requirements.

    This is the data-driven heart of the framework.
    Domain modules configure this per action type.
    """
    # Identifier (e.g., "refund_request", "curriculum_change")
    config_id: str

    # Which roles can approve
    allowed_roles: List[Role]

    # How approvals are evaluated
    mode: ApprovalMode = ApprovalMode.SINGLE

    # For QUORUM mode: minimum approvals needed
    quorum_count: int = 1

    # Human-readable description
    description: Optional[str] = None

    def __post_init__(self):
        """Validate configuration."""
        if not self.allowed_roles:
            raise ValueError("ApprovalConfig must have at least one allowed role")

        if self.mode == ApprovalMode.ANY and self.quorum_count < 1:
            raise ValueError("Quorum count must be at least 1 for ANY mode")

        if self.mode == ApprovalMode.ALL:
            # For ALL mode, quorum_count equals the number of unique roles
            self.quorum_count = len(self.allowed_roles)


# --- Approval Action ---

@dataclass
class ApprovalAction:
    """Record of an approval or rejection action."""
    action_id: str = field(default_factory=lambda: str(uuid4()))
    approver_id: str = ""
    approver_role: Role = Role.ADMIN
    action: str = "approve"  # "approve" or "reject"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    comment: Optional[str] = None


# --- Approval Request ---

@dataclass
class ApprovalRequest:
    """
    Tracks the state of an approval request for a specific entity.

    This is the runtime entity that moves through the approval lifecycle.
    """
    id: str = field(default_factory=lambda: str(uuid4()))

    # What is being approved
    entity_type: str = ""
    entity_id: str = ""
    action_type: str = ""  # e.g., "refund", "grade_change"

    # Configuration reference
    config_id: str = ""

    # State
    status: ApprovalState = ApprovalState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Requestor
    requested_by: str = ""

    # Approval tracking
    actions: List[ApprovalAction] = field(default_factory=list)
    required_count: int = 1
    required_roles: List[Role] = field(default_factory=list)
    mode: ApprovalMode = ApprovalMode.SINGLE

    # Resolution
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None

    # Context data (for audit)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def approval_count(self) -> int:
        """Count of approvals received."""
        return sum(1 for a in self.actions if a.action == "approve")

    @property
    def rejection_count(self) -> int:
        """Count of rejections received."""
        return sum(1 for a in self.actions if a.action == "reject")

    @property
    def approver_roles(self) -> Set[Role]:
        """Set of roles that have approved."""
        return {a.approver_role for a in self.actions if a.action == "approve"}

    @property
    def approver_ids(self) -> Set[str]:
        """Set of user IDs that have taken action."""
        return {a.approver_id for a in self.actions}


# --- Approval Service ---

class ApprovalService:
    """
    Generic Approval Service.

    This service:
    - Creates approval requests
    - Records approvals/rejections
    - Evaluates quorum/completion
    - Emits audit logs

    In production, this will persist to the database.
    """

    # In-memory storage for development
    _requests: Dict[str, ApprovalRequest] = {}
    _configs: Dict[str, ApprovalConfig] = {}

    # --- Configuration Management ---

    @classmethod
    def register_config(cls, config: ApprovalConfig) -> None:
        """
        Register an approval configuration.

        Called by domain modules during initialization.
        """
        cls._configs[config.config_id] = config

    @classmethod
    def get_config(cls, config_id: str) -> Optional[ApprovalConfig]:
        """Get a registered configuration."""
        return cls._configs.get(config_id)

    # --- Request Management ---

    @classmethod
    def create_request(
        cls,
        entity_type: str,
        entity_id: str,
        action_type: str,
        config_id: str,
        requested_by: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ApprovalRequest:
        """
        Create a new approval request.

        Args:
            entity_type: Type of entity (e.g., "invoice", "curriculum")
            entity_id: ID of the entity
            action_type: Action requiring approval (e.g., "refund")
            config_id: ID of the ApprovalConfig to use
            requested_by: User ID of the requestor
            context: Additional context for audit

        Returns:
            ApprovalRequest in PENDING state

        Raises:
            ValueError: If config_id is not registered
        """
        config = cls.get_config(config_id)
        if config is None:
            raise ValueError(f"Unknown approval config: {config_id}")

        request = ApprovalRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            action_type=action_type,
            config_id=config_id,
            requested_by=requested_by,
            required_count=config.quorum_count,
            required_roles=list(config.allowed_roles),
            mode=config.mode,
            context=context or {}
        )

        cls._requests[request.id] = request

        # Audit: Request created
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=requested_by,
            actor_type="human",
            entity_type="approval_request",
            entity_id=request.id,
            action_detail=f"Approval requested for {entity_type}:{entity_id} ({action_type})",
            metadata={
                "target_entity_type": entity_type,
                "target_entity_id": entity_id,
                "action_type": action_type,
                "config_id": config_id
            }
        )

        return request

    @classmethod
    def get_request(cls, request_id: str) -> Optional[ApprovalRequest]:
        """Get an approval request by ID."""
        return cls._requests.get(request_id)

    @classmethod
    def get_pending_for_entity(
        cls,
        entity_type: str,
        entity_id: str
    ) -> List[ApprovalRequest]:
        """Get all pending approval requests for an entity."""
        return [
            r for r in cls._requests.values()
            if r.entity_type == entity_type
            and r.entity_id == entity_id
            and r.status == ApprovalState.PENDING
        ]

    # --- Approval Actions ---

    @classmethod
    def approve(
        cls,
        request_id: str,
        approver_id: str,
        approver_role: Role,
        comment: Optional[str] = None
    ) -> ApprovalRequest:
        """
        Record an approval for a request.

        Args:
            request_id: ID of the approval request
            approver_id: User ID of the approver
            approver_role: Role of the approver
            comment: Optional comment

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found, already resolved,
                       approver not authorized, or duplicate approval
        """
        request = cls._get_and_validate_request(request_id)

        # Check if role is authorized
        if approver_role not in request.required_roles:
            raise ValueError(
                f"Role '{approver_role.value}' is not authorized to approve this request. "
                f"Required roles: {[r.value for r in request.required_roles]}"
            )

        # Check for duplicate approval by same user
        if approver_id in request.approver_ids:
            raise ValueError(f"User '{approver_id}' has already taken action on this request")

        # For ALL mode, check if this role has already approved
        if request.mode == ApprovalMode.ALL:
            if approver_role in request.approver_roles:
                raise ValueError(
                    f"Role '{approver_role.value}' has already approved. "
                    "ALL mode requires each role to approve only once."
                )

        # Record the approval
        action = ApprovalAction(
            approver_id=approver_id,
            approver_role=approver_role,
            action="approve",
            comment=comment
        )
        request.actions.append(action)

        # Audit: Approval recorded
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=approver_id,
            actor_type="human",
            actor_role=approver_role.value,
            entity_type="approval_request",
            entity_id=request_id,
            action_detail="Approval recorded",
            metadata={
                "action": "approve",
                "comment": comment,
                "approval_count": request.approval_count,
                "required_count": request.required_count
            }
        )

        # Check if quorum is met
        if cls._is_quorum_met(request):
            cls._resolve_request(request, ApprovalState.APPROVED, "Quorum met")

        return request

    @classmethod
    def reject(
        cls,
        request_id: str,
        rejector_id: str,
        rejector_role: Role,
        comment: Optional[str] = None
    ) -> ApprovalRequest:
        """
        Reject an approval request.

        A single rejection terminates the request.

        Args:
            request_id: ID of the approval request
            rejector_id: User ID of the rejector
            rejector_role: Role of the rejector
            comment: Optional comment (recommended)

        Returns:
            Updated ApprovalRequest in REJECTED state

        Raises:
            ValueError: If request not found, already resolved, or rejector not authorized
        """
        request = cls._get_and_validate_request(request_id)

        # Check if role is authorized
        if rejector_role not in request.required_roles:
            raise ValueError(
                f"Role '{rejector_role.value}' is not authorized to reject this request"
            )

        # Record the rejection
        action = ApprovalAction(
            approver_id=rejector_id,
            approver_role=rejector_role,
            action="reject",
            comment=comment
        )
        request.actions.append(action)

        # Rejection immediately terminates
        cls._resolve_request(request, ApprovalState.REJECTED, comment or "Rejected")

        # Audit: Rejection recorded
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=rejector_id,
            actor_type="human",
            actor_role=rejector_role.value,
            entity_type="approval_request",
            entity_id=request_id,
            action_detail="Request rejected",
            metadata={
                "action": "reject",
                "comment": comment
            }
        )

        return request

    # --- Status Check ---

    @classmethod
    def get_status(cls, request_id: str) -> ApprovalState:
        """
        Get the current status of an approval request.

        Raises:
            ValueError: If request not found
        """
        request = cls._requests.get(request_id)
        if request is None:
            raise ValueError(f"Approval request not found: {request_id}")
        return request.status

    @classmethod
    def is_approved(cls, request_id: str) -> bool:
        """Check if a request is approved."""
        return cls.get_status(request_id) == ApprovalState.APPROVED

    # --- Internal Methods ---

    @classmethod
    def _get_and_validate_request(cls, request_id: str) -> ApprovalRequest:
        """Get request and validate it's actionable."""
        request = cls._requests.get(request_id)
        if request is None:
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status != ApprovalState.PENDING:
            raise ValueError(
                f"Request is already resolved with status: {request.status.value}"
            )

        return request

    @classmethod
    def _is_quorum_met(cls, request: ApprovalRequest) -> bool:
        """Check if approval quorum is met based on mode."""
        match request.mode:
            case ApprovalMode.SINGLE:
                return request.approval_count >= 1

            case ApprovalMode.ANY:
                return request.approval_count >= request.required_count

            case ApprovalMode.ALL:
                # All required roles must have approved
                return request.approver_roles >= set(request.required_roles)

        return False

    @classmethod
    def _resolve_request(
        cls,
        request: ApprovalRequest,
        new_state: ApprovalState,
        reason: str
    ) -> None:
        """Transition request to terminal state."""
        # Validate state transition
        result = StateRegistry.validate_transition(
            "approval",
            request.status,
            new_state
        )
        if not result.allowed:
            raise ValueError(result.reason)

        request.status = new_state
        request.resolved_at = datetime.now(timezone.utc)
        request.resolution_reason = reason

        # Audit: State transition
        AuditLog.log_state_transition(
            actor_id="system",
            actor_type="system",
            entity_type="approval_request",
            entity_id=request.id,
            previous_state=ApprovalState.PENDING.value,
            new_state=new_state.value,
            metadata={"reason": reason}
        )


# --- Convenience Functions ---

def validate_approval_transition(
    from_state: ApprovalState,
    to_state: ApprovalState
) -> TransitionResult:
    """Validate an approval state transition."""
    return StateRegistry.validate_transition("approval", from_state, to_state)
