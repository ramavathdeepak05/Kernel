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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

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
    actor_role: str | None = None

    # Target Entity
    entity_type: str = ""  # e.g., "student", "payment"
    entity_id: str = ""

    # Tenant
    tenant_id: str = ""

    # Organization
    org_id: str | None = None

    # Additional data for lock checks and business logic
    data: dict[str, Any] = field(default_factory=dict)

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
    message: str | None = None
    data: dict[str, Any] | None = None
    lock_violations: list[str] | None = None


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
    ai_role: str | None = None  # Infer | Score | Plan | Execute
    confidence: ConfidenceLevel | None = None
    authority_required: AuthorityLevel = AuthorityLevel.AUTO

    # State transition proposal
    proposed_state: WorkflowState | None = None

    # Metadata
    rationale: str | None = None
    metadata: dict[str, Any] | None = None


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
    context: WorkflowContext | None = None

    # Roles authorised to approve this instance (set by domain subclass)
    approver_roles: list[str] = field(default_factory=list)

    # History
    step_history: list[StepResult] = field(default_factory=list)
    decision: WorkflowDecision | None = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    # Audit
    audit_trail: list[str] = field(default_factory=list)  # List of audit entry IDs
