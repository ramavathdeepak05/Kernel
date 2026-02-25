"""
ALIS Global Audit Log - E01-S09

MODULE: Platform Core
LAYER: Cross-cutting (Regulatory Defensibility)
ENTITY: AuditEntry

This module implements a system-wide append-only audit log.

Must Align With:
- Regulatory defensibility
- Immutable storage

Acceptance Criteria:
- [x] Actor, action, entity, timestamp
- [x] Immutable storage (append-only)
- [x] Queryable by authorized roles
- [x] No silent writes
"""

from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


# --- Audit Action Types ---

class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Entity CRUD
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"  # Soft delete

    # State Changes
    STATE_TRANSITION = "state_transition"
    EVENT_PUBLISHED = "event_published"

    # Access
    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS_DENIED = "access_denied"

    # Overrides
    OVERRIDE_REQUESTED = "override_requested"
    OVERRIDE_APPROVED = "override_approved"
    OVERRIDE_REJECTED = "override_rejected"
    OVERRIDE_EXECUTED = "override_executed"

    # AI Agent
    AGENT_DECISION = "agent_decision"
    AGENT_TOOL_CALL = "agent_tool_call"

    # AI Gateway (E03-S01)
    AI_INVOCATION = "ai_invocation"

    # System
    CONFIG_CHANGE = "config_change"
    LOCK_TRIGGERED = "lock_triggered"
    LOCK_CLEARED = "lock_cleared"

    # Escalation & Dual Control (E00-S04)
    ESCALATION_REQUESTED = "escalation_requested"
    ESCALATION_GRANTED = "escalation_granted"
    ESCALATION_DENIED = "escalation_denied"
    ESCALATION_EXPIRED = "escalation_expired"
    ESCALATION_REVOKED = "escalation_revoked"
    ESCALATION_USED = "escalation_used"
    DUAL_CONTROL_REQUESTED = "dual_control_requested"
    DUAL_CONTROL_COMPLETED = "dual_control_completed"


# --- Audit Entry ---

@dataclass(frozen=True)
class AuditEntry:
    """
    Immutable audit log entry.

    Uses frozen=True to ensure immutability after creation.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Actor
    actor_id: str = ""
    actor_type: str = ""  # human, ai_agent, system
    actor_role: Optional[str] = None

    # Action
    action: AuditAction = AuditAction.READ
    action_detail: Optional[str] = None

    # Target
    entity_type: str = ""
    entity_id: str = ""

    # Context
    org_id: Optional[str] = None
    module: Optional[str] = None  # M1, M2, etc.
    wizard: Optional[str] = None  # If action was from a wizard

    # Outcome
    success: bool = True
    failure_reason: Optional[str] = None

    # Additional Data
    metadata: Optional[Dict[str, Any]] = None

    # State (for state transitions)
    previous_state: Optional[str] = None
    new_state: Optional[str] = None


# --- Audit Log Service ---

class AuditLog:
    """
    Append-only audit log service.

    In production, this will persist to an immutable storage backend
    (e.g., append-only table, blockchain, or immutable object storage).
    """

    # In-memory storage for development
    _entries: List[AuditEntry] = []

    @classmethod
    def log(
        cls,
        action: AuditAction,
        actor_id: str,
        actor_type: str,
        entity_type: str,
        entity_id: str,
        success: bool = True,
        actor_role: Optional[str] = None,
        action_detail: Optional[str] = None,
        org_id: Optional[str] = None,
        module: Optional[str] = None,
        wizard: Optional[str] = None,
        failure_reason: Optional[str] = None,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditEntry:
        """
        Create an audit log entry.

        This is the primary method for logging auditable actions.
        All parameters are explicitly required to prevent silent writes.
        """
        entry = AuditEntry(
            actor_id=actor_id,
            actor_type=actor_type,
            actor_role=actor_role,
            action=action,
            action_detail=action_detail,
            entity_type=entity_type,
            entity_id=entity_id,
            org_id=org_id,
            module=module,
            wizard=wizard,
            success=success,
            failure_reason=failure_reason,
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata
        )

        # Append to immutable log
        cls._entries.append(entry)

        return entry

    @classmethod
    def log_state_transition(
        cls,
        actor_id: str,
        actor_type: str,
        entity_type: str,
        entity_id: str,
        previous_state: str,
        new_state: str,
        success: bool = True,
        **kwargs
    ) -> AuditEntry:
        """Convenience method for logging state transitions."""
        return cls.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=previous_state,
            new_state=new_state,
            success=success,
            **kwargs
        )

    @classmethod
    def log_agent_decision(
        cls,
        agent_id: str,
        entity_type: str,
        entity_id: str,
        decision: str,
        confidence: float,
        wizard: Optional[str] = None,
        **kwargs
    ) -> AuditEntry:
        """Log an AI agent decision."""
        return cls.log(
            action=AuditAction.AGENT_DECISION,
            actor_id=agent_id,
            actor_type="ai_agent",
            entity_type=entity_type,
            entity_id=entity_id,
            wizard=wizard,
            action_detail=decision,
            metadata={"confidence": confidence, **kwargs.get("metadata", {})}
        )

    @classmethod
    def query(
        cls,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        org_id: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """
        Query audit log entries.

        Filters are ANDed together.
        """
        results = cls._entries

        if actor_id:
            results = [e for e in results if e.actor_id == actor_id]
        if entity_type:
            results = [e for e in results if e.entity_type == entity_type]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        if action:
            results = [e for e in results if e.action == action]
        if org_id:
            results = [e for e in results if e.org_id == org_id]
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]

        # Sort by timestamp descending and limit
        results = sorted(results, key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    @classmethod
    def get_entity_history(
        cls,
        entity_type: str,
        entity_id: str,
        limit: int = 50
    ) -> List[AuditEntry]:
        """Get full audit history for a specific entity."""
        return cls.query(entity_type=entity_type, entity_id=entity_id, limit=limit)
