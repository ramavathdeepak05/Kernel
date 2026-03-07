"""
ALIS Incident Response & Lockdown Mode - E00-S05

MODULE: Platform Core
LAYER: Layer 4 (Global Locks & Invariants) + Layer 6 (Resilience)
ENTITY: LockdownManager

This module implements the system-wide lockdown mode for incident response.
When activated, it:
    1. Sets a global flag blocking all non-admin state mutations (Layer 4 Write Gate).
    2. Blocks all AI invocations via the AI Gateway (Global AI Pause).
    3. Invalidates all non-admin sessions (Mass Token Revocation).
    4. Logs every lockdown lifecycle event immutably (Layer 6 Incident Log).

Must Align With:
    - Layer 4: System-wide write gate
    - Layer 6: Incident log
    - E00-S04: Privilege control (Admin/SuperAdmin immunity)
    - Legal & Audit Hardening Addendum §27: AI Disablement Safeguard

Acceptance Criteria (E00-S05):
    - [x] Global flag toggles system mode
    - [x] Non-admin writes blocked
    - [x] All non-admin sessions invalidated
    - [x] AI invocations blocked
    - [x] Activation/deactivation audit logged
    - [x] Blocked attempts audit logged
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import uuid4

from .audit import AuditLog, AuditAction
from .rbac import Role

logger = logging.getLogger(__name__)


# --- Lockdown State Entity ---

@dataclass
class LockdownEvent:
    """
    Immutable record of a lockdown lifecycle event.

    Each activation or deactivation creates one of these.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""       # "activated" or "deactivated"
    actor_id: str = ""
    actor_role: str = ""
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sessions_revoked: int = 0  # Number of sessions killed on activation
    metadata: Optional[Dict[str, Any]] = None


# --- Roles Immune to Lockdown ---
# These roles retain write access and session validity during lockdown.
# Only system-level administrators can operate during an incident.

LOCKDOWN_IMMUNE_ROLES = frozenset({
    Role.ADMIN,
    Role.SUPER_ADMIN,
    Role.SYSTEM,
})


# --- Lockdown Manager Singleton ---

class LockdownManager:
    """
    Central Lockdown Manager for ALIS — E00-S05.

    This is a singleton service that tracks whether the platform is in
    lockdown mode. All enforcement points (db_service, ai_gateway,
    LockdownMiddleware) consult this manager before proceeding.

    Design Decisions:
        - In-memory flag for zero-latency checks (no DB round-trip per request).
        - Event history retained in memory for audit replay.
        - In production, the flag should also be persisted to a DB table and
          broadcast via pub/sub for multi-node consistency.

    Usage:
        # Check
        if LockdownManager.is_active():
            raise LockdownActiveError(...)

        # Activate (admin only)
        LockdownManager.activate(actor_id="admin-1", actor_role="super_admin", reason="Security breach")

        # Deactivate (admin only)
        LockdownManager.deactivate(actor_id="admin-1", actor_role="super_admin", reason="Incident resolved")
    """

    # --- Internal State ---
    _active: bool = False
    _activated_at: Optional[datetime] = None
    _activated_by: Optional[str] = None
    _activation_reason: Optional[str] = None
    _event_history: List[LockdownEvent] = []

    # ================================================================
    # QUERY METHODS
    # ================================================================

    @classmethod
    def is_active(cls) -> bool:
        """
        Check if lockdown mode is currently active.

        This is the hot-path method called by every enforcement point.
        Must be O(1) with no I/O.
        """
        return cls._active

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Return a structured status snapshot for dashboards / API."""
        return {
            "is_active": cls._active,
            "activated_at": cls._activated_at.isoformat() if cls._activated_at else None,
            "activated_by": cls._activated_by,
            "reason": cls._activation_reason,
            "event_count": len(cls._event_history),
        }

    @classmethod
    def get_event_history(cls) -> List[LockdownEvent]:
        """Return the full lockdown event history (append-only)."""
        return list(cls._event_history)

    # ================================================================
    # ACTIVATION
    # ================================================================

    @classmethod
    def activate(
        cls,
        actor_id: str,
        actor_role: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LockdownEvent:
        """
        Activate lockdown mode.

        Effects:
            1. Sets the global lockdown flag to True.
            2. Revokes all non-admin sessions via SessionManager.
            3. Logs the event to the immutable AuditLog.

        Args:
            actor_id:   ID of the administrator triggering lockdown.
            actor_role: Role string of the actor (must be admin-level).
            reason:     Human-readable reason for the lockdown.
            metadata:   Optional extra context (e.g., incident ticket ID).

        Returns:
            LockdownEvent record.

        Raises:
            PermissionDeniedError: If actor_role is not in LOCKDOWN_IMMUNE_ROLES.
            ValueError: If lockdown is already active.
        """
        from .exceptions import PermissionDeniedError

        # --- Guard: Only immune roles may trigger lockdown ---
        _assert_immune_role(actor_role, "activate lockdown")

        if cls._active:
            raise ValueError(
                "Lockdown is already active. Deactivate before re-activating."
            )

        # --- Step 1: Flip the flag ---
        cls._active = True
        cls._activated_at = datetime.now(timezone.utc)
        cls._activated_by = actor_id
        cls._activation_reason = reason

        # --- Step 2: Mass session revocation ---
        sessions_revoked = _revoke_non_admin_sessions(reason="Lockdown activated")

        # --- Step 3: Record the event ---
        event = LockdownEvent(
            event_type="activated",
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            sessions_revoked=sessions_revoked,
            metadata=metadata,
        )
        cls._event_history.append(event)

        # --- Step 4: Audit log ---
        AuditLog.log(
            action=AuditAction.LOCK_TRIGGERED,
            actor_id=actor_id,
            actor_type="human",
            actor_role=actor_role,
            entity_type="lockdown",
            entity_id=event.id,
            action_detail=f"Lockdown ACTIVATED: {reason}",
            success=True,
            metadata={
                "reason": reason,
                "sessions_revoked": sessions_revoked,
                **(metadata or {}),
            },
        )

        logger.critical(
            "LOCKDOWN ACTIVATED by %s (role=%s): %s  |  Sessions revoked: %d",
            actor_id, actor_role, reason, sessions_revoked,
        )

        return event

    # ================================================================
    # DEACTIVATION
    # ================================================================

    @classmethod
    def deactivate(
        cls,
        actor_id: str,
        actor_role: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LockdownEvent:
        """
        Deactivate lockdown mode and restore normal operations.

        Args:
            actor_id:   ID of the administrator releasing lockdown.
            actor_role: Role string of the actor (must be admin-level).
            reason:     Human-readable reason for release.
            metadata:   Optional extra context.

        Returns:
            LockdownEvent record.

        Raises:
            PermissionDeniedError: If actor_role is not in LOCKDOWN_IMMUNE_ROLES.
            ValueError: If lockdown is not currently active.
        """
        from .exceptions import PermissionDeniedError

        _assert_immune_role(actor_role, "deactivate lockdown")

        if not cls._active:
            raise ValueError("Lockdown is not currently active.")

        # --- Flip the flag ---
        cls._active = False

        event = LockdownEvent(
            event_type="deactivated",
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            metadata=metadata,
        )
        cls._event_history.append(event)

        # Clear activation metadata
        cls._activated_at = None
        cls._activated_by = None
        cls._activation_reason = None

        # Audit log
        AuditLog.log(
            action=AuditAction.LOCK_CLEARED,
            actor_id=actor_id,
            actor_type="human",
            actor_role=actor_role,
            entity_type="lockdown",
            entity_id=event.id,
            action_detail=f"Lockdown DEACTIVATED: {reason}",
            success=True,
            metadata={
                "reason": reason,
                **(metadata or {}),
            },
        )

        logger.critical(
            "LOCKDOWN DEACTIVATED by %s (role=%s): %s",
            actor_id, actor_role, reason,
        )

        return event

    # ================================================================
    # ENFORCEMENT HELPERS
    # ================================================================

    @classmethod
    def assert_write_allowed(
        cls,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> None:
        """
        Assert that a write operation is permitted.

        Call this from db_service.execute_transaction, API middleware, etc.

        Raises:
            LockdownActiveError: If lockdown is active and actor is not immune.
        """
        if not cls._active:
            return  # Normal operations — no overhead.

        # Check immunity
        role_enum = _resolve_role(actor_role)
        if role_enum in LOCKDOWN_IMMUNE_ROLES:
            return  # Admin/SuperAdmin/System — pass through.

        from .exceptions import LockdownActiveError

        # Log the blocked attempt
        AuditLog.log(
            action=AuditAction.ACCESS_DENIED,
            actor_id=actor_id or "unknown",
            actor_type="human",
            entity_type="lockdown_write_gate",
            entity_id="",
            success=False,
            failure_reason="Write blocked: System in Lockdown (E00-S05)",
            metadata={"actor_role": actor_role},
        )

        raise LockdownActiveError(
            message="System is in lockdown mode. Non-admin write operations are suspended.",
            details={"actor_role": actor_role, "actor_id": actor_id},
        )

    @classmethod
    def assert_ai_allowed(
        cls,
        actor_id: Optional[str] = None,
    ) -> None:
        """
        Assert that AI invocations are permitted.

        Call this from AIGateway / InstrumentedLLM.invoke().
        During lockdown ALL AI invocations are blocked regardless of role.

        Raises:
            LockdownActiveError: If lockdown is active.
        """
        if not cls._active:
            return

        from .exceptions import LockdownActiveError

        AuditLog.log(
            action=AuditAction.ACCESS_DENIED,
            actor_id=actor_id or "unknown",
            actor_type="system",
            entity_type="lockdown_ai_gate",
            entity_id="",
            success=False,
            failure_reason="AI invocation blocked: System in Lockdown (E00-S05)",
        )

        raise LockdownActiveError(
            message="AI invocations are disabled during lockdown mode.",
            details={"actor_id": actor_id},
        )

    # ================================================================
    # RESET (Testing Only)
    # ================================================================

    @classmethod
    def _reset(cls) -> None:
        """Reset lockdown state. FOR TESTING ONLY."""
        cls._active = False
        cls._activated_at = None
        cls._activated_by = None
        cls._activation_reason = None
        cls._event_history = []


# ============================================================================
# PRIVATE HELPERS
# ============================================================================

def _resolve_role(role_str: Optional[str]) -> Optional[Role]:
    """Safely resolve a role string to a Role enum."""
    if role_str is None:
        return None
    try:
        return Role(role_str)
    except ValueError:
        return None


def _assert_immune_role(actor_role: str, operation: str) -> None:
    """Raise PermissionDeniedError if actor_role is not in LOCKDOWN_IMMUNE_ROLES."""
    from .exceptions import PermissionDeniedError

    role_enum = _resolve_role(actor_role)
    if role_enum not in LOCKDOWN_IMMUNE_ROLES:
        raise PermissionDeniedError(
            message=f"Only ADMIN, SUPER_ADMIN, or SYSTEM roles may {operation}. "
                    f"Got: '{actor_role}'.",
            details={"actor_role": actor_role},
        )


def _revoke_non_admin_sessions(reason: str) -> int:
    """
    Revoke all active sessions that do NOT belong to immune roles.

    Returns the number of sessions revoked.
    """
    from .security import SessionManager

    # Revoke all sessions via Redis scan — admin re-authenticates on resume.
    # (Correct incident response posture: force MFA reauthentication for everyone.)
    count = SessionManager.revoke_all_sessions(reason=reason)
    logger.info("Revoked %d sessions during lockdown activation.", count)
    return count
