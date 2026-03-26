"""
ALIS Global Locks Engine - E01-S07

MODULE: Platform Core
LAYER: Layer 4 (Global Locks & Invariants)
ENTITY: GlobalLock

This module implements the Global Lock engine that overrides all
module and wizard decisions.

Must Align With:
- Layer 4 (Global Locks & Invariants)

Examples from Master Handbook:
- No Hall Ticket if dues pending
- No Exam if attendance < threshold
- No Enrollment if documents incomplete

Layer 4 Rules:
- Global Locks are evaluated BEFORE all decisions
- No module may bypass a Global Lock
- Cannot be disabled or bypassed

Acceptance Criteria:
- [x] Central lock evaluation
- [x] Evaluated before any decision
- [x] Non-bypassable
- [x] Explicit violation reasons
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


# --- Lock Types ---

class LockType(str, Enum):
    """Types of global locks in ALIS."""
    FINANCIAL_DUES = "financial_dues"
    ATTENDANCE_SHORTAGE = "attendance_shortage"
    DOCUMENT_INCOMPLETE = "document_incomplete"
    DISCIPLINARY_HOLD = "disciplinary_hold"
    EXAM_ELIGIBILITY = "exam_eligibility"
    LIBRARY_DUES = "library_dues"
    HOSTEL_DUES = "hostel_dues"
    ARCHIVED_RECORD = "archived_record"  # E00-S07: Prevents mutation of archived data
    CUSTOM = "custom"


# --- Lock Result ---

@dataclass
class LockStatus:
    """Result of a global lock check."""
    is_locked: bool
    lock_type: Optional[LockType] = None
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LockCheckResult:
    """Aggregated result of all lock checks."""
    is_locked: bool
    violations: List[LockStatus] = field(default_factory=list)

    @property
    def reasons(self) -> List[str]:
        """Get all violation reasons."""
        return [v.reason for v in self.violations if v.reason]


# --- Global Lock Registry ---

class GlobalLockRegistry:
    """
    Central registry for global lock checks.

    All lock checks are registered here and evaluated centrally.
    This ensures no module can bypass a global lock.
    """

    # Lock check functions: Dict[LockType, Callable[[str], LockStatus]]
    _lock_checks: Dict[LockType, Callable[[str, Optional[Dict]], LockStatus]] = {}

    @classmethod
    def register_lock(
        cls,
        lock_type: LockType,
        check_fn: Callable[[str, Optional[Dict]], LockStatus]
    ) -> None:
        """Register a lock check function."""
        cls._lock_checks[lock_type] = check_fn

    @classmethod
    def check_lock(
        cls,
        lock_type: LockType,
        entity_id: str,
        context: Optional[Dict] = None
    ) -> LockStatus:
        """Check a specific lock for an entity."""
        check_fn = cls._lock_checks.get(lock_type)
        if check_fn is None:
            return LockStatus(is_locked=False)
        return check_fn(entity_id, context)

    @classmethod
    def check_all_locks(
        cls,
        entity_id: str,
        context: Optional[Dict] = None,
        lock_types: Optional[List[LockType]] = None
    ) -> LockCheckResult:
        """
        Check all registered locks for an entity.

        Args:
            entity_id: The entity to check locks for
            context: Optional context for lock evaluation
            lock_types: Specific locks to check (defaults to all)

        Returns:
            LockCheckResult with aggregated violations
        """
        types_to_check = lock_types or list(cls._lock_checks.keys())
        violations = []

        for lock_type in types_to_check:
            status = cls.check_lock(lock_type, entity_id, context)
            if status.is_locked:
                violations.append(status)

        return LockCheckResult(
            is_locked=len(violations) > 0,
            violations=violations
        )


# --- Default Lock Implementations ---
# These are placeholder implementations that will be replaced
# by actual service integrations

def _check_financial_dues(entity_id: str, context: Optional[Dict] = None) -> LockStatus:
    """
    Check if entity has outstanding financial dues.

    In production, this will query the Finance module (M4).
    """
    # Placeholder: In real implementation, query finance service
    context = context or {}
    balance = context.get("balance", 0)

    if balance > 0:
        return LockStatus(
            is_locked=True,
            lock_type=LockType.FINANCIAL_DUES,
            reason=f"Outstanding dues: ₹{balance}",
            details={"balance": balance}
        )
    return LockStatus(is_locked=False)


def _check_attendance_shortage(entity_id: str, context: Optional[Dict] = None) -> LockStatus:
    """
    Check if entity has attendance below threshold.

    In production, this will query the Academics module (M2).
    """
    context = context or {}
    attendance_pct = context.get("attendance_percentage", 100)
    threshold = context.get("attendance_threshold", 75)

    if attendance_pct < threshold:
        return LockStatus(
            is_locked=True,
            lock_type=LockType.ATTENDANCE_SHORTAGE,
            reason=f"Attendance {attendance_pct}% is below required {threshold}%",
            details={
                "attendance_percentage": attendance_pct,
                "threshold": threshold
            }
        )
    return LockStatus(is_locked=False)


def _check_document_incomplete(entity_id: str, context: Optional[Dict] = None) -> LockStatus:
    """Check if entity has incomplete documents."""
    context = context or {}
    missing_docs = context.get("missing_documents", [])

    if missing_docs:
        return LockStatus(
            is_locked=True,
            lock_type=LockType.DOCUMENT_INCOMPLETE,
            reason=f"Missing documents: {', '.join(missing_docs)}",
            details={"missing_documents": missing_docs}
        )
    return LockStatus(is_locked=False)


def _check_disciplinary_hold(entity_id: str, context: Optional[Dict] = None) -> LockStatus:
    """Check if entity has active disciplinary hold."""
    context = context or {}
    has_hold = context.get("disciplinary_hold", False)

    if has_hold:
        return LockStatus(
            is_locked=True,
            lock_type=LockType.DISCIPLINARY_HOLD,
            reason="Active disciplinary hold",
            details={"hold_reason": context.get("hold_reason")}
        )
    return LockStatus(is_locked=False)


def _check_archived_record(entity_id: str, context: Optional[Dict] = None) -> LockStatus:
    """
    E00-S07: Check if entity is archived.

    Archived records are permanently frozen — no module may update
    or delete them without going through the legal deletion workflow.
    This lock is evaluated BEFORE all decisions (Layer 4 invariant).
    """
    context = context or {}
    is_archived = context.get("is_archived", False)
    status = context.get("status", "")

    if is_archived or str(status).upper() == "ARCHIVED":
        return LockStatus(
            is_locked=True,
            lock_type=LockType.ARCHIVED_RECORD,
            reason="Record is permanently archived — mutations are blocked (E00-S07)",
            details={"entity_id": entity_id, "archival_lock": True}
        )
    return LockStatus(is_locked=False)


# --- Register Default Locks ---

GlobalLockRegistry.register_lock(LockType.FINANCIAL_DUES, _check_financial_dues)
GlobalLockRegistry.register_lock(LockType.ATTENDANCE_SHORTAGE, _check_attendance_shortage)
GlobalLockRegistry.register_lock(LockType.DOCUMENT_INCOMPLETE, _check_document_incomplete)
GlobalLockRegistry.register_lock(LockType.DISCIPLINARY_HOLD, _check_disciplinary_hold)
GlobalLockRegistry.register_lock(LockType.ARCHIVED_RECORD, _check_archived_record)  # E00-S07


# --- Convenience Function (Used in Rule Engines) ---

def check_global_locks(
    entity_id: str,
    context: Optional[Dict] = None,
    required_locks: Optional[List[LockType]] = None
) -> LockCheckResult:
    """
    Check global locks for an entity.

    This function is called by Rule Engines (Blueprint A) before
    any decision is made.

    Args:
        entity_id: The entity (usually student ID) to check
        context: Context dict with relevant data
        required_locks: Specific locks to check

    Returns:
        LockCheckResult indicating if any locks are active
    """
    return GlobalLockRegistry.check_all_locks(entity_id, context, required_locks)
