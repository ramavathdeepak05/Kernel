"""
P11 — Final Verification (Stage 9)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 3 (State Transitions) + Layer 6 (Audit)
ENTITIES: FinalVerification, FinalVerificationItem, VerificationDiscrepancy

Orchestrates the in-person/DigiLocker/courier document verification that
happens after payment is confirmed (VERIFICATION_PENDING state).

Workflow:
    1. initiate()          — Create verification record for the applicant
    2. start()             — Officer starts session → IN_PROGRESS
    3. check_document()    — Record per-document outcome (VERIFIED / DISCREPANCY / NOT_PRODUCED)
    4a. clear()            — All docs OK → VERIFIED → READY_FOR_ENROLLMENT
    4b. clear_with_undertaking() — Minor issues cleared on undertaking → CLEARED_WITH_UNDERTAKING → READY_FOR_ENROLLMENT
    4c. reject()           — Critical discrepancy → REJECTED → CANCELLED
    5. raise_discrepancy() — Create a discrepancy record with severity/type
    6. resolve_discrepancy() / escalate_discrepancy() — Manage discrepancies

State transitions owned here:
    VERIFICATION_PENDING → (clear / clear_with_undertaking) → READY_FOR_ENROLLMENT
    VERIFICATION_PENDING → reject → CANCELLED
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation
from server.core.state_registry import StudentState
from server.db_service import execute_query, execute_transaction

from .service import ApplicantService

logger = logging.getLogger(__name__)

# Valid statuses
_VERIFICATION_STATUSES = {
    "PENDING", "IN_PROGRESS", "VERIFIED",
    "DISCREPANCY_FOUND", "CLEARED_WITH_UNDERTAKING", "REJECTED",
}
_ITEM_OUTCOMES = {"PENDING", "VERIFIED", "DISCREPANCY", "NOT_PRODUCED"}
_DISCREPANCY_TYPES = {
    "DATA_MISMATCH", "SUSPECTED_FRAUD", "DOCUMENT_MISSING",
    "DOCUMENT_EXPIRED", "UNRECOGNIZED_BOARD",
}
_SEVERITY_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_DISCREPANCY_STATUSES = {"OPEN", "UNDER_REVIEW", "RESOLVED", "ESCALATED", "CLOSED_REJECTED"}

# Statuses from which a verification can be cleared/rejected
_ACTIONABLE = {"IN_PROGRESS", "DISCREPANCY_FOUND", "PENDING"}


# =============================================================================
# Pydantic Models
# =============================================================================

class FinalVerificationCreate(BaseModel):
    applicant_id: str
    verification_mode: str = Field(
        default="IN_PERSON",
        description="IN_PERSON | DIGILOCKER | COURIER"
    )
    reporting_date: Optional[str] = Field(
        default=None,
        description="ISO date YYYY-MM-DD (for IN_PERSON appointments)"
    )
    assigned_officer: Optional[str] = None
    notes: Optional[str] = None


class FinalVerificationRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    verification_mode: str
    reporting_date: Optional[str] = None
    status: str
    assigned_officer: Optional[str] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class VerificationItemCreate(BaseModel):
    doc_type: str = Field(..., min_length=2, max_length=100)
    outcome: str = Field(..., description="VERIFIED | DISCREPANCY | NOT_PRODUCED")
    discrepancy_detail: Optional[str] = None
    officer_notes: Optional[str] = None


class VerificationItemRead(BaseModel):
    id: str
    org_id: str
    verification_id: str
    doc_type: str
    outcome: str
    discrepancy_detail: Optional[str] = None
    officer_notes: Optional[str] = None
    checked_at: Optional[datetime] = None
    checked_by: Optional[str] = None


class DiscrepancyCreate(BaseModel):
    doc_type: str = Field(..., min_length=2)
    discrepancy_type: str = Field(
        ..., description="DATA_MISMATCH | SUSPECTED_FRAUD | DOCUMENT_MISSING | DOCUMENT_EXPIRED | UNRECOGNIZED_BOARD"
    )
    description: str = Field(..., min_length=10, max_length=2000)
    severity: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH | CRITICAL")
    escalated_to: Optional[str] = None


class DiscrepancyRead(BaseModel):
    id: str
    org_id: str
    verification_id: str
    applicant_id: str
    doc_type: str
    discrepancy_type: str
    description: str
    severity: str
    escalated_to: Optional[str] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


# =============================================================================
# FINAL VERIFICATION SERVICE
# =============================================================================

class FinalVerificationService:
    """
    Manages the final document verification session per applicant (Stage 9).

    One verification record per applicant (UNIQUE constraint). Re-initiating
    is blocked if a non-rejected record already exists.
    """

    @classmethod
    def initiate(
        cls,
        request: FinalVerificationCreate,
        org_id: str,
        actor_id: str,
    ) -> FinalVerificationRead:
        """
        Create a verification record for an applicant.

        Pre-condition: applicant must be VERIFICATION_PENDING.
        Idempotent: returns existing record if already initiated.
        """
        # Idempotency
        existing = execute_query(
            "SELECT * FROM final_verifications WHERE applicant_id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if existing and existing[0]["status"] != "REJECTED":
            return cls._row_to_read(existing[0])

        # Pre-condition
        app_rows = execute_query(
            "SELECT status FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        status = app_rows[0]["status"]
        if status not in (StudentState.VERIFICATION_PENDING.value, "VERIFICATION_PENDING"):
            raise BusinessRuleViolation(
                message=(
                    f"Final verification requires VERIFICATION_PENDING status — "
                    f"current status: '{status}'."
                ),
                details={"status": status},
            )

        ver_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO final_verifications (
                    id, org_id, applicant_id, verification_mode,
                    reporting_date, status, assigned_officer, notes,
                    created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    ver_id, org_id,
                    request.applicant_id,
                    request.verification_mode,
                    request.reporting_date,
                    "PENDING",
                    request.assigned_officer,
                    request.notes,
                    now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="final_verification",
            entity_id=ver_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "mode": request.verification_mode,
                "reporting_date": request.reporting_date,
            },
        )

        logger.info(
            "P11: Verification initiated [id=%s, applicant=%s, mode=%s]",
            ver_id, request.applicant_id, request.verification_mode,
        )
        return cls.get(ver_id, org_id)

    @classmethod
    def start(
        cls,
        verification_id: str,
        org_id: str,
        actor_id: str,
        assigned_officer: Optional[str] = None,
    ) -> FinalVerificationRead:
        """Mark verification as IN_PROGRESS. Optionally assign/reassign officer."""
        ver = cls._require(verification_id, org_id)

        if ver["status"] not in ("PENDING", "DISCREPANCY_FOUND"):
            raise BusinessRuleViolation(
                message=f"Verification '{verification_id}' cannot be started — status: '{ver['status']}'."
            )

        now = datetime.now(timezone.utc)
        officer = assigned_officer or ver.get("assigned_officer") or actor_id

        execute_transaction([
            (
                "UPDATE final_verifications SET status = 'IN_PROGRESS', "
                "assigned_officer = %s, updated_at = %s WHERE id = %s AND org_id = %s",
                (officer, now, verification_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="final_verification",
            entity_id=verification_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={"action": "started", "assigned_officer": officer},
        )

        return cls.get(verification_id, org_id)

    @classmethod
    def check_document(
        cls,
        verification_id: str,
        item: VerificationItemCreate,
        org_id: str,
        actor_id: str,
    ) -> VerificationItemRead:
        """
        Record the outcome of checking a single document.

        Upserts by (verification_id, doc_type) — re-checking overwrites.
        If any item is DISCREPANCY → sets verification status to DISCREPANCY_FOUND.
        """
        if item.outcome not in _ITEM_OUTCOMES - {"PENDING"}:
            raise BusinessRuleViolation(
                message=f"Invalid outcome '{item.outcome}'.",
                details={"valid": ["VERIFIED", "DISCREPANCY", "NOT_PRODUCED"]},
            )

        ver = cls._require(verification_id, org_id)
        if ver["status"] not in ("IN_PROGRESS", "DISCREPANCY_FOUND"):
            raise BusinessRuleViolation(
                message=f"Cannot check documents — verification status: '{ver['status']}'."
            )

        now = datetime.now(timezone.utc)
        item_id = str(uuid4())

        execute_transaction([
            (
                "DELETE FROM final_verification_items "
                "WHERE verification_id = %s AND doc_type = %s AND org_id = %s",
                (verification_id, item.doc_type, org_id),
            ),
            (
                """
                INSERT INTO final_verification_items (
                    id, org_id, verification_id, doc_type, outcome,
                    discrepancy_detail, officer_notes, checked_at, checked_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    item_id, org_id,
                    verification_id,
                    item.doc_type,
                    item.outcome,
                    item.discrepancy_detail,
                    item.officer_notes,
                    now,
                    actor_id,
                ),
            ),
        ])

        # Auto-escalate verification status if discrepancy found
        if item.outcome in ("DISCREPANCY", "NOT_PRODUCED"):
            execute_transaction([
                (
                    "UPDATE final_verifications SET status = 'DISCREPANCY_FOUND', updated_at = %s "
                    "WHERE id = %s AND org_id = %s AND status NOT IN ('VERIFIED', 'REJECTED', 'CLEARED_WITH_UNDERTAKING')",
                    (now, verification_id, org_id),
                )
            ])

        rows = execute_query(
            "SELECT * FROM final_verification_items WHERE id = %s",
            (item_id,),
        )
        return VerificationItemRead(**rows[0])

    @classmethod
    def clear(
        cls,
        verification_id: str,
        org_id: str,
        actor_id: str,
        notes: Optional[str] = None,
    ) -> FinalVerificationRead:
        """
        All documents verified — mark VERIFIED → transition applicant → READY_FOR_ENROLLMENT.
        """
        ver = cls._require(verification_id, org_id)

        if ver["status"] not in _ACTIONABLE:
            raise BusinessRuleViolation(
                message=f"Cannot clear verification — status: '{ver['status']}'."
            )

        # Ensure no open DISCREPANCY items remain
        open_issues = execute_query(
            "SELECT COUNT(*) as cnt FROM final_verification_items "
            "WHERE verification_id = %s AND outcome IN ('DISCREPANCY', 'NOT_PRODUCED')",
            (verification_id,),
        )
        if open_issues and open_issues[0]["cnt"] > 0:
            raise BusinessRuleViolation(
                message="Cannot clear verification — unresolved discrepancy items remain.",
                details={"open_discrepancy_count": open_issues[0]["cnt"]},
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE final_verifications SET status = 'VERIFIED', "
                "completed_at = %s, notes = COALESCE(%s, notes), updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, notes, now, verification_id, org_id),
            )
        ])

        ApplicantService.transition_state(
            applicant_id=ver["applicant_id"],
            org_id=org_id,
            to_state=StudentState.READY_FOR_ENROLLMENT,
            actor_id=actor_id,
            reason="Final verification completed — all documents verified.",
            metadata={"verification_id": verification_id},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="final_verification",
            entity_id=verification_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={"action": "cleared", "applicant_id": ver["applicant_id"]},
        )

        logger.info("P11: Verification cleared [id=%s, applicant=%s]", verification_id, ver["applicant_id"])
        return cls.get(verification_id, org_id)

    @classmethod
    def clear_with_undertaking(
        cls,
        verification_id: str,
        org_id: str,
        actor_id: str,
        notes: str,
    ) -> FinalVerificationRead:
        """
        Minor issues cleared on a signed undertaking.
        Transitions applicant → READY_FOR_ENROLLMENT with a note.
        """
        if not notes or len(notes.strip()) < 10:
            raise BusinessRuleViolation(
                message="Undertaking notes are required (min 10 chars) for CLEARED_WITH_UNDERTAKING."
            )

        ver = cls._require(verification_id, org_id)

        if ver["status"] not in _ACTIONABLE:
            raise BusinessRuleViolation(
                message=f"Cannot clear verification — status: '{ver['status']}'."
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE final_verifications SET status = 'CLEARED_WITH_UNDERTAKING', "
                "completed_at = %s, notes = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, notes.strip(), now, verification_id, org_id),
            )
        ])

        ApplicantService.transition_state(
            applicant_id=ver["applicant_id"],
            org_id=org_id,
            to_state=StudentState.READY_FOR_ENROLLMENT,
            actor_id=actor_id,
            reason="Verification cleared with signed undertaking.",
            metadata={"verification_id": verification_id, "undertaking_notes": notes},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="final_verification",
            entity_id=verification_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={
                "action": "cleared_with_undertaking",
                "applicant_id": ver["applicant_id"],
                "notes": notes,
            },
        )

        logger.info(
            "P11: Verification cleared with undertaking [id=%s]", verification_id
        )
        return cls.get(verification_id, org_id)

    @classmethod
    def reject(
        cls,
        verification_id: str,
        org_id: str,
        actor_id: str,
        reason: str,
    ) -> FinalVerificationRead:
        """
        Critical discrepancy — reject applicant.
        Transitions applicant → CANCELLED.
        """
        if not reason or len(reason.strip()) < 10:
            raise BusinessRuleViolation(
                message="Rejection reason required (min 10 chars)."
            )

        ver = cls._require(verification_id, org_id)

        if ver["status"] in ("VERIFIED", "CLEARED_WITH_UNDERTAKING", "REJECTED"):
            raise BusinessRuleViolation(
                message=f"Cannot reject — verification status: '{ver['status']}'."
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE final_verifications SET status = 'REJECTED', "
                "completed_at = %s, notes = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, reason.strip(), now, verification_id, org_id),
            )
        ])

        ApplicantService.transition_state(
            applicant_id=ver["applicant_id"],
            org_id=org_id,
            to_state=StudentState.CANCELLED,
            actor_id=actor_id,
            reason=f"Final verification rejected: {reason}",
            metadata={"verification_id": verification_id, "rejection_reason": reason},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="final_verification",
            entity_id=verification_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={
                "action": "rejected",
                "applicant_id": ver["applicant_id"],
                "reason": reason,
            },
        )

        logger.info("P11: Verification rejected [id=%s]", verification_id)
        return cls.get(verification_id, org_id)

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get(cls, verification_id: str, org_id: str) -> FinalVerificationRead:
        rows = execute_query(
            "SELECT * FROM final_verifications WHERE id = %s AND org_id = %s",
            (verification_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Final verification '{verification_id}' not found."
            )
        return cls._row_to_read(rows[0])

    @classmethod
    def get_for_applicant(cls, applicant_id: str, org_id: str) -> Optional[FinalVerificationRead]:
        rows = execute_query(
            "SELECT * FROM final_verifications WHERE applicant_id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        return cls._row_to_read(rows[0]) if rows else None

    @classmethod
    def list_items(cls, verification_id: str, org_id: str) -> List[VerificationItemRead]:
        rows = execute_query(
            "SELECT * FROM final_verification_items "
            "WHERE verification_id = %s AND org_id = %s ORDER BY checked_at ASC",
            (verification_id, org_id),
        )
        return [VerificationItemRead(**r) for r in rows]

    @classmethod
    def _require(cls, verification_id: str, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM final_verifications WHERE id = %s AND org_id = %s",
            (verification_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Final verification '{verification_id}' not found."
            )
        return rows[0]

    @classmethod
    def _row_to_read(cls, row: Dict[str, Any]) -> FinalVerificationRead:
        data = dict(row)
        if hasattr(data.get("reporting_date"), "isoformat"):
            data["reporting_date"] = data["reporting_date"].isoformat()
        return FinalVerificationRead(**data)


# =============================================================================
# DISCREPANCY SERVICE
# =============================================================================

class DiscrepancyService:
    """
    Manages document discrepancy records raised during final verification.

    Lifecycle: OPEN → UNDER_REVIEW → RESOLVED | ESCALATED | CLOSED_REJECTED
    """

    @classmethod
    def raise_discrepancy(
        cls,
        verification_id: str,
        request: DiscrepancyCreate,
        org_id: str,
        actor_id: str,
    ) -> DiscrepancyRead:
        """
        Raise a discrepancy against a document in a verification session.

        HIGH/CRITICAL severity discrepancies automatically set verification
        status to DISCREPANCY_FOUND.
        """
        if request.discrepancy_type not in _DISCREPANCY_TYPES:
            raise BusinessRuleViolation(
                message=f"Invalid discrepancy_type '{request.discrepancy_type}'.",
                details={"valid": list(_DISCREPANCY_TYPES)},
            )
        if request.severity not in _SEVERITY_LEVELS:
            raise BusinessRuleViolation(
                message=f"Invalid severity '{request.severity}'.",
                details={"valid": list(_SEVERITY_LEVELS)},
            )

        ver = cls._require_ver(verification_id, org_id)

        disc_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO verification_discrepancies (
                    id, org_id, verification_id, applicant_id, doc_type,
                    discrepancy_type, description, severity, escalated_to,
                    status, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    disc_id, org_id,
                    verification_id,
                    ver["applicant_id"],
                    request.doc_type,
                    request.discrepancy_type,
                    request.description,
                    request.severity,
                    request.escalated_to,
                    "OPEN",
                    now, now,
                ),
            )
        ])

        # Escalate verification status for HIGH/CRITICAL
        if request.severity in ("HIGH", "CRITICAL"):
            execute_transaction([
                (
                    "UPDATE final_verifications SET status = 'DISCREPANCY_FOUND', updated_at = %s "
                    "WHERE id = %s AND org_id = %s "
                    "AND status NOT IN ('VERIFIED', 'REJECTED', 'CLEARED_WITH_UNDERTAKING')",
                    (now, verification_id, org_id),
                )
            ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="verification_discrepancy",
            entity_id=disc_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={
                "verification_id": verification_id,
                "doc_type": request.doc_type,
                "type": request.discrepancy_type,
                "severity": request.severity,
            },
        )

        logger.info(
            "P11: Discrepancy raised [id=%s, ver=%s, severity=%s]",
            disc_id, verification_id, request.severity,
        )
        return cls.get_discrepancy(disc_id, org_id)

    @classmethod
    def resolve_discrepancy(
        cls,
        discrepancy_id: str,
        org_id: str,
        actor_id: str,
        resolution: str,
    ) -> DiscrepancyRead:
        """Mark a discrepancy as RESOLVED with a resolution note."""
        if not resolution or len(resolution.strip()) < 5:
            raise BusinessRuleViolation(message="Resolution note required (min 5 chars).")

        disc = cls._require_disc(discrepancy_id, org_id)

        if disc["status"] in ("RESOLVED", "CLOSED_REJECTED"):
            raise BusinessRuleViolation(
                message=f"Discrepancy '{discrepancy_id}' is already closed."
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE verification_discrepancies "
                "SET status = 'RESOLVED', resolution = %s, resolved_at = %s, "
                "resolved_by = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (resolution.strip(), now, actor_id, now, discrepancy_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="verification_discrepancy",
            entity_id=discrepancy_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={"action": "resolved", "resolution": resolution},
        )

        return cls.get_discrepancy(discrepancy_id, org_id)

    @classmethod
    def escalate_discrepancy(
        cls,
        discrepancy_id: str,
        org_id: str,
        actor_id: str,
        escalate_to: str,
    ) -> DiscrepancyRead:
        """Escalate a discrepancy to a specific officer/role."""
        if not escalate_to or not escalate_to.strip():
            raise BusinessRuleViolation(message="escalate_to is required.")

        disc = cls._require_disc(discrepancy_id, org_id)

        if disc["status"] in ("RESOLVED", "CLOSED_REJECTED"):
            raise BusinessRuleViolation(
                message=f"Discrepancy '{discrepancy_id}' is already closed."
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE verification_discrepancies "
                "SET status = 'ESCALATED', escalated_to = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (escalate_to.strip(), now, discrepancy_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="verification_discrepancy",
            entity_id=discrepancy_id,
            org_id=org_id,
            module="M1",
            wizard="Final Verification",
            success=True,
            metadata={"action": "escalated", "escalated_to": escalate_to},
        )

        return cls.get_discrepancy(discrepancy_id, org_id)

    @classmethod
    def get_discrepancy(cls, discrepancy_id: str, org_id: str) -> DiscrepancyRead:
        rows = execute_query(
            "SELECT * FROM verification_discrepancies WHERE id = %s AND org_id = %s",
            (discrepancy_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Discrepancy '{discrepancy_id}' not found."
            )
        return DiscrepancyRead(**rows[0])

    @classmethod
    def list_discrepancies(
        cls,
        verification_id: str,
        org_id: str,
        status: Optional[str] = None,
    ) -> List[DiscrepancyRead]:
        conditions = ["verification_id = %s", "org_id = %s"]
        params: list = [verification_id, org_id]
        if status:
            conditions.append("status = %s")
            params.append(status)
        rows = execute_query(
            f"SELECT * FROM verification_discrepancies WHERE {' AND '.join(conditions)} "
            "ORDER BY created_at ASC",
            tuple(params),
        )
        return [DiscrepancyRead(**r) for r in rows]

    @classmethod
    def _require_ver(cls, verification_id: str, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM final_verifications WHERE id = %s AND org_id = %s",
            (verification_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Final verification '{verification_id}' not found."
            )
        return rows[0]

    @classmethod
    def _require_disc(cls, discrepancy_id: str, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM verification_discrepancies WHERE id = %s AND org_id = %s",
            (discrepancy_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Discrepancy '{discrepancy_id}' not found."
            )
        return rows[0]
