"""
E04-S01 — Applicant Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 3 (State Machine) + Layer 4 (Locks)
ENTITY: Applicant

Handles applicant creation (LEAD → APPLIED state transition),
duplicate detection, and applicant CRUD operations.

Acceptance Criteria (E04-S01):
    - [x] API: POST /applicants
    - [x] Duplicate detection enforced (email + phone uniqueness per tenant)
    - [x] State transition: LEAD → APPLIED
    - [x] Transition logged to audit
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, IllegalStateTransitionError
from server.core.state_registry import StudentState, validate_student_transition
from server.db_service import execute_query, execute_transaction

from .models import ApplicantCreate, ApplicantRead, ApplicantStatus

logger = logging.getLogger(__name__)


class ApplicantService:
    """
    Manages applicant creation and lifecycle for E04-S01.

    Hard Constraints:
    - State transitions are enforced by state_registry (Layer 3).
    - Duplicate check on (email OR phone) per tenant (Layer 4 block).
    - All mutations are logged to the audit ledger.
    """

    # -------------------------------------------------------------------------
    # S01: Create Applicant (LEAD → APPLIED)
    # -------------------------------------------------------------------------

    @classmethod
    def create_applicant(
        cls,
        data: ApplicantCreate,
        org_id: str,
        created_by: str,
    ) -> ApplicantRead:
        """
        Create a new applicant and transition state from LEAD → APPLIED.

        Enforces:
        - Email + phone uniqueness per tenant (Layer 4 duplicate block)
        - Legal state transition LEAD → APPLIED (Layer 3)
        - Audit log entry

        Args:
            data:       Validated applicant input
            org_id:     Tenant ID
            created_by: Actor ID performing the action

        Returns:
            ApplicantRead — the persisted applicant record

        Raises:
            BusinessRuleViolation: If a duplicate email or phone exists
        """
        # --- Layer 4: Duplicate detection ---
        existing = cls._find_duplicate(data.email, data.phone, org_id)
        if existing:
            raise BusinessRuleViolation(
                message=(
                    f"Duplicate applicant detected — "
                    f"an applicant with this email or phone already exists "
                    f"(id={existing['id']})."
                ),
                details={"existing_id": existing["id"], "status": existing["status"]},
            )

        # --- Layer 3: Validate LEAD → APPLIED ---
        transition = validate_student_transition(
            StudentState.LEAD, StudentState.APPLIED
        )
        if not transition.allowed:
            raise IllegalStateTransitionError(
                message=f"Cannot transition LEAD → APPLIED: {transition.reason}",
            )

        applicant_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO applicants
                    (id, org_id, name, email, phone, intended_program,
                     source_channel, status, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    applicant_id,
                    org_id,
                    data.name,
                    data.email,
                    data.phone,
                    data.intended_program,
                    data.source_channel.value,
                    ApplicantStatus.APPLIED.value,
                    _json_dumps(data.metadata or {}),
                    now,
                    now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=created_by,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Applicant Wizard",
            success=True,
            metadata={
                "from_state": StudentState.LEAD.value,
                "to_state": StudentState.APPLIED.value,
                "email": data.email,
                "intended_program": data.intended_program,
            },
        )

        logger.info("E04-S01: Applicant created [id=%s, org=%s]", applicant_id, org_id)
        return cls.get_applicant(applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get_applicant(cls, applicant_id: str, org_id: str) -> ApplicantRead:
        """Fetch a single applicant by ID."""
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{applicant_id}' not found.",
                details={"applicant_id": applicant_id},
            )
        return ApplicantRead(**rows[0])

    @classmethod
    def list_applicants(
        cls,
        org_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ApplicantRead]:
        """List applicants for a tenant, optionally filtered by status."""
        if status:
            rows = execute_query(
                "SELECT * FROM applicants WHERE org_id = %s AND status = %s "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (org_id, status, limit, offset),
            )
        else:
            rows = execute_query(
                "SELECT * FROM applicants WHERE org_id = %s "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (org_id, limit, offset),
            )
        return [ApplicantRead(**r) for r in rows]

    # -------------------------------------------------------------------------
    # State transition (used by other wizards)
    # -------------------------------------------------------------------------

    @classmethod
    def transition_state(
        cls,
        applicant_id: str,
        org_id: str,
        to_state: StudentState,
        actor_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApplicantRead:
        """
        Execute a state transition for an applicant.

        Called by orchestrator services (eligibility, confirmation, enrollment).
        Validates legality via Layer 3 before writing.
        """
        rows = execute_query(
            "SELECT status FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{applicant_id}' not found.",
            )

        current = StudentState(rows[0]["status"])
        transition = validate_student_transition(current, to_state)
        if not transition.allowed:
            raise IllegalStateTransitionError(
                message=(
                    f"Illegal state transition for applicant {applicant_id}: "
                    f"{current.value} → {to_state.value}. {transition.reason or ''}"
                ),
                details={"from": current.value, "to": to_state.value},
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE applicants SET status = %s, updated_at = %s WHERE id = %s AND org_id = %s",
                (to_state.value, now, applicant_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            success=True,
            metadata={
                "from_state": current.value,
                "to_state": to_state.value,
                "reason": reason,
                **(metadata or {}),
            },
        )

        logger.info(
            "E04: Applicant %s → %s [id=%s]", current.value, to_state.value, applicant_id
        )
        return cls.get_applicant(applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _find_duplicate(
        cls, email: str, phone: str, org_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check for existing applicant with same email or phone in tenant."""
        rows = execute_query(
            "SELECT id, status FROM applicants "
            "WHERE org_id = %s AND (email = %s OR phone = %s) "
            "AND status != %s LIMIT 1",
            (org_id, email, phone, ApplicantStatus.ANNULLED.value),
        )
        return rows[0] if rows else None


# =============================================================================
# Helpers
# =============================================================================

def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, default=str)
