"""
ALIS Workflow Schema - E02-S01: Workflow Engine

MODULE: Shared Services
LAYER: Layer 2 (Wizards & Decisions)
ENTITY: WorkflowInstance, WorkflowStep, WorkflowDecision

This module defines the Pydantic models for declarative workflow definitions.

Must Align With:
- Layer 2 (Agentic Decisions & Wizards)
- Layer 3 (State Machines via StateRegistry)

Acceptance Criteria:
- [x] Define workflow templates declaratively
- [x] Workflow instances are auditable
- [x] No domain logic inside schema
"""

from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .state_registry import WorkflowState


# --- Workflow Context ---

@dataclass
class WorkflowContext:
    """
    Immutable context passed through a workflow execution.

    This carries actor information, entity references, and any
    context needed for lock checks and audit logging.
    """
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    workflow_type: str = ""  # e.g., "admissions.applicant", "finance.refund"

    # Actor (who triggered this workflow)
    actor_id: str = ""
    actor_type: str = "human"  # human, ai_agent, system
    actor_role: Optional[str] = None

    # Target Entity
    entity_type: str = ""  # e.g., "student", "payment"
    entity_id: str = ""

    # Organization
    org_id: Optional[str] = None

    # Additional data for lock checks and business logic
    data: Dict[str, Any] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Step Result ---

class StepOutcome(str, Enum):
    """Possible outcomes of a workflow step."""
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"  # Blocked by Global Lock
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class StepResult:
    """
    Result of executing a single workflow step.

    Steps do not determine workflow state directly; the engine
    interprets these results and transitions accordingly.
    """
    outcome: StepOutcome
    step_name: str = ""
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    lock_violations: Optional[List[str]] = None


# --- Workflow Decision (Layer 2 Mandate) ---

class ConfidenceLevel(str, Enum):
    """Confidence levels for AI-assisted decisions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuthorityLevel(str, Enum):
    """Authority required for decision execution."""
    AUTO = "auto"  # System can execute automatically
    APPROVE = "approve"  # Requires single human approval
    QUORUM = "quorum"  # Requires multi-signature approval


@dataclass
class WorkflowDecision:
    """
    Represents the decision made by a workflow/wizard.

    Every wizard MUST end in a decision (Layer 2 mandate).
    This decision either advances state, blocks, or enters provisional path.
    """
    decision_made: str  # Single sentence institutional truth
    ai_role: Optional[str] = None  # Infer | Score | Plan | Execute
    confidence: Optional[ConfidenceLevel] = None
    authority_required: AuthorityLevel = AuthorityLevel.AUTO

    # State transition proposal
    proposed_state: Optional[WorkflowState] = None

    # Metadata
    rationale: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# --- Workflow Instance ---

@dataclass
class WorkflowInstance:
    """
    Represents a running or completed workflow instance.

    This is the persistent record of a workflow execution.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    workflow_type: str = ""
    current_state: WorkflowState = WorkflowState.CREATED

    # Context
    context: Optional[WorkflowContext] = None

    # History
    step_history: List[StepResult] = field(default_factory=list)
    decision: Optional[WorkflowDecision] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # Audit
    audit_trail: List[str] = field(default_factory=list)  # List of audit entry IDs
