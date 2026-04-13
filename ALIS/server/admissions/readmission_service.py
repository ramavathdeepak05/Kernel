"""E17 — Re-admission Workflow Service

Re-admission workflow: SUBMITTED → UNDER_REVIEW → APPROVED/REJECTED → ENROLLED
On approval: RE-prefixed roll number, completed semester lock, catch-up assessment.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class ReadmissionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ENROLLED = "ENROLLED"


# =============================================================================
# RE-ADMISSION SERVICE
# =============================================================================


class ReadmissionService:
    """
    Manages the re-admission workflow for students returning after a gap.

    Lifecycle: SUBMITTED → UNDER_REVIEW → APPROVED/REJECTED → ENROLLED

    Rules (R1, R7):
    - Maximum gap years is governed by policy_engine (no hardcoded threshold).
    - On approval, a RE-prefixed roll number is generated and the event is fired
      for downstream enrollment provisioning.
    """

    # -------------------------------------------------------------------------
    # Submit
    # -------------------------------------------------------------------------

    @classmethod
    def submit_application(
        cls,
        org_id: str,
        applicant_name: str,
        applicant_email: str,
        program_id: str,
        gap_from: datetime,
        gap_to: datetime,
        semesters_completed: int,
        gap_reason: str,
        previous_roll_number: str | None = None,
        previous_institution: str | None = None,
        applicant_phone: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit a re-admission application.

        Validates the gap duration against the institution policy before
        persisting. Fires admissions.readmission_submitted on success.

        Args:
            org_id:               Tenant ID.
            applicant_name:       Full name of the returning student.
            applicant_email:      Contact email.
            program_id:           Program UUID they wish to re-join.
            gap_from:             Date the student left / last enrolled.
            gap_to:               Today (or intended re-admission date).
            semesters_completed:  Number of semesters already completed.
            gap_reason:           Free-text explanation for the gap.
            previous_roll_number: Optional — roll number from prior enrollment.
            previous_institution: Optional — if transferring from another institution.
            applicant_phone:      Optional contact phone.

        Returns:
            Application record dict.

        Raises:
            BusinessRuleViolation: If gap_years exceeds the policy maximum.
        """
        # R1 / R7 — policy-governed threshold, never hardcoded
        max_gap_years = policy_engine.get_value(
            "admissions.readmission_max_gap_years", org_id, default=5
        )
        gap_years = (gap_to - gap_from).days / 365.25

        if gap_years > max_gap_years:
            raise BusinessRuleViolation(
                message=(
                    f"Gap of {gap_years:.1f} years exceeds the maximum allowed "
                    f"{max_gap_years} years for re-admission."
                ),
                details={
                    "gap_years": round(gap_years, 2),
                    "max_gap_years": max_gap_years,
                },
            )

        app_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO readmission_applications (
                    id, org_id, applicant_name, applicant_email, applicant_phone,
                    program_id, gap_from, gap_to, gap_years, semesters_completed,
                    gap_reason, previous_roll_number, previous_institution,
                    status, submitted_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                    (
                        app_id,
                        org_id,
                        applicant_name,
                        applicant_email,
                        applicant_phone,
                        program_id,
                        gap_from,
                        gap_to,
                        round(gap_years, 4),
                        semesters_completed,
                        gap_reason,
                        previous_roll_number,
                        previous_institution,
                        ReadmissionStatus.SUBMITTED.value,
                        now,
                        now,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            entity_type="readmission_application",
            entity_id=app_id,
            org_id=org_id,
            module="M1",
            wizard="Re-admission Workflow",
            success=True,
            metadata={
                "applicant_email": applicant_email,
                "program_id": program_id,
                "gap_years": round(gap_years, 2),
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.readmission_submitted",
                org_id=org_id,
                entity_type="readmission_application",
                entity_id=app_id,
                payload={
                    "application_id": app_id,
                    "org_id": org_id,
                    "applicant_email": applicant_email,
                    "program_id": program_id,
                    "gap_years": round(gap_years, 2),
                    "semesters_completed": semesters_completed,
                },
            )
        )

        logger.info(
            "E17: Re-admission application submitted [id=%s, email=%s, program=%s, gap=%.1f yrs]",
            app_id,
            applicant_email,
            program_id,
            gap_years,
        )
        return cls.get_application(app_id, org_id)

    # -------------------------------------------------------------------------
    # Start Review
    # -------------------------------------------------------------------------

    @classmethod
    def start_review(
        cls,
        application_id: str,
        org_id: str,
        reviewer_id: str,
    ) -> dict[str, Any]:
        """
        Transition application from SUBMITTED to UNDER_REVIEW.

        Args:
            application_id: UUID of the readmission application.
            org_id:         Tenant ID.
            reviewer_id:    Actor performing the review.

        Returns:
            Updated application dict.
        """
        app = cls._require(application_id, org_id)

        if app["status"] != ReadmissionStatus.SUBMITTED.value:
            raise BusinessRuleViolation(
                message=(
                    f"Re-admission application '{application_id}' cannot be moved to "
                    f"UNDER_REVIEW — current status: '{app['status']}'."
                ),
                details={"current_status": app["status"]},
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                UPDATE readmission_applications
                SET status = %s, reviewed_by = %s, review_started_at = %s, updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        ReadmissionStatus.UNDER_REVIEW.value,
                        reviewer_id,
                        now,
                        now,
                        application_id,
                        org_id,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=reviewer_id,
            entity_type="readmission_application",
            entity_id=application_id,
            org_id=org_id,
            module="M1",
            wizard="Re-admission Workflow",
            success=True,
            metadata={"action": "start_review", "reviewer_id": reviewer_id},
        )

        logger.info(
            "E17: Re-admission review started [id=%s, reviewer=%s]",
            application_id,
            reviewer_id,
        )
        return cls.get_application(application_id, org_id)

    # -------------------------------------------------------------------------
    # Approve
    # -------------------------------------------------------------------------

    @classmethod
    def approve(
        cls,
        application_id: str,
        org_id: str,
        reviewer_id: str,
        review_notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Approve a re-admission application.

        Generates a RE-prefixed roll number (RE-{YEAR}-{SEQ:06d}),
        updates the application record to APPROVED, and fires the
        admissions.readmission_approved event. The actual enrollment
        provisioning is handled downstream by the event handler.

        Args:
            application_id: UUID of the readmission application.
            org_id:         Tenant ID.
            reviewer_id:    Actor approving the application.
            review_notes:   Optional notes from the reviewer.

        Returns:
            Updated application dict with new_roll_number set.

        Raises:
            BusinessRuleViolation: If application is not in UNDER_REVIEW status.
        """
        app = cls._require(application_id, org_id)

        if app["status"] != ReadmissionStatus.UNDER_REVIEW.value:
            raise BusinessRuleViolation(
                message=(
                    f"Re-admission application '{application_id}' cannot be approved — "
                    f"current status: '{app['status']}'. Must be UNDER_REVIEW."
                ),
                details={"current_status": app["status"]},
            )

        # Generate RE-prefixed roll number: RE-{year}-{seq:06d}
        year = datetime.now(timezone.utc).year
        count_rows = execute_query(
            """
            SELECT COUNT(*) AS cnt
            FROM readmission_applications
            WHERE org_id = %s
              AND status IN (%s, %s)
              AND EXTRACT(YEAR FROM approved_at) = %s
            """,
            (
                org_id,
                ReadmissionStatus.APPROVED.value,
                ReadmissionStatus.ENROLLED.value,
                year,
            ),
        )
        seq = (count_rows[0]["cnt"] if count_rows else 0) + 1
        new_roll_number = f"RE-{year}-{seq:06d}"

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                UPDATE readmission_applications
                SET status = %s,
                    reviewed_by = %s,
                    review_notes = %s,
                    approved_at = %s,
                    new_roll_number = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        ReadmissionStatus.APPROVED.value,
                        reviewer_id,
                        review_notes,
                        now,
                        new_roll_number,
                        now,
                        application_id,
                        org_id,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=reviewer_id,
            entity_type="readmission_application",
            entity_id=application_id,
            org_id=org_id,
            module="M1",
            wizard="Re-admission Workflow",
            success=True,
            metadata={
                "action": "approved",
                "new_roll_number": new_roll_number,
                "reviewer_id": reviewer_id,
            },
        )

        # Downstream provisioning is event-driven — fire and let handlers do the work
        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.readmission_approved",
                org_id=org_id,
                entity_type="readmission_application",
                entity_id=application_id,
                actor_id=reviewer_id,
                payload={
                    "application_id": application_id,
                    "org_id": org_id,
                    "applicant_email": app["applicant_email"],
                    "applicant_name": app["applicant_name"],
                    "program_id": app["program_id"],
                    "new_roll_number": new_roll_number,
                    "semesters_completed": app["semesters_completed"],
                    "previous_roll_number": app.get("previous_roll_number"),
                    # Semester lock payload — provisioning handler inserts into
                    # readmission_semester_locks (table created via migration)
                    "completed_semesters_to_lock": app["semesters_completed"],
                    "reviewer_id": reviewer_id,
                },
            )
        )

        logger.info(
            "E17: Re-admission approved [id=%s, roll=%s, reviewer=%s]",
            application_id,
            new_roll_number,
            reviewer_id,
        )
        return cls.get_application(application_id, org_id)

    # -------------------------------------------------------------------------
    # Reject
    # -------------------------------------------------------------------------

    @classmethod
    def reject(
        cls,
        application_id: str,
        org_id: str,
        reviewer_id: str,
        review_notes: str,
    ) -> dict[str, Any]:
        """
        Reject a re-admission application.

        Args:
            application_id: UUID of the readmission application.
            org_id:         Tenant ID.
            reviewer_id:    Actor rejecting the application.
            review_notes:   Mandatory rejection reason.

        Returns:
            Updated application dict.

        Raises:
            BusinessRuleViolation: If not in UNDER_REVIEW, or notes are too short.
        """
        if not review_notes or len(review_notes.strip()) < 10:
            raise BusinessRuleViolation(
                message="Rejection notes are required (minimum 10 characters)."
            )

        app = cls._require(application_id, org_id)

        if app["status"] != ReadmissionStatus.UNDER_REVIEW.value:
            raise BusinessRuleViolation(
                message=(
                    f"Re-admission application '{application_id}' cannot be rejected — "
                    f"current status: '{app['status']}'. Must be UNDER_REVIEW."
                ),
                details={"current_status": app["status"]},
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                UPDATE readmission_applications
                SET status = %s,
                    reviewed_by = %s,
                    review_notes = %s,
                    rejected_at = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        ReadmissionStatus.REJECTED.value,
                        reviewer_id,
                        review_notes.strip(),
                        now,
                        now,
                        application_id,
                        org_id,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=reviewer_id,
            entity_type="readmission_application",
            entity_id=application_id,
            org_id=org_id,
            module="M1",
            wizard="Re-admission Workflow",
            success=True,
            metadata={
                "action": "rejected",
                "reviewer_id": reviewer_id,
                "review_notes": review_notes,
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.readmission_rejected",
                org_id=org_id,
                entity_type="readmission_application",
                entity_id=application_id,
                actor_id=reviewer_id,
                payload={
                    "application_id": application_id,
                    "org_id": org_id,
                    "applicant_email": app["applicant_email"],
                    "program_id": app["program_id"],
                    "review_notes": review_notes,
                },
            )
        )

        logger.info(
            "E17: Re-admission rejected [id=%s, reviewer=%s]",
            application_id,
            reviewer_id,
        )
        return cls.get_application(application_id, org_id)

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get_application(cls, application_id: str, org_id: str) -> dict[str, Any]:
        """
        Fetch a re-admission application by ID, including associated credit transfers.

        Args:
            application_id: UUID of the readmission application.
            org_id:         Tenant ID.

        Returns:
            Application dict with a 'credit_transfers' key (may be empty list).

        Raises:
            NotFoundError: If application does not exist for this tenant.
        """
        rows = execute_query(
            "SELECT * FROM readmission_applications WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(
                message=f"Re-admission application '{application_id}' not found.",
                details={"application_id": application_id, "org_id": org_id},
            )

        app = dict(rows[0])

        # Fetch any linked credit transfer requests
        credit_transfers = execute_query(
            "SELECT * FROM credit_transfer_requests WHERE readmission_id = %s AND org_id = %s",
            (application_id, org_id),
        )
        app["credit_transfers"] = (
            [dict(r) for r in credit_transfers] if credit_transfers else []
        )

        return app

    @classmethod
    def list_applications(
        cls,
        org_id: str,
        status: str | None = None,
        program_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List re-admission applications for a tenant with optional filters.

        Args:
            org_id:     Tenant ID.
            status:     Optional ReadmissionStatus value to filter by.
            program_id: Optional program UUID to filter by.

        Returns:
            List of application dicts ordered by submitted_at descending.
        """
        conditions = ["org_id = %s"]
        params: list = [org_id]

        if status:
            conditions.append("status = %s")
            params.append(status)

        if program_id:
            conditions.append("program_id = %s")
            params.append(program_id)

        rows = execute_query(
            f"SELECT * FROM readmission_applications WHERE {' AND '.join(conditions)} "  # noqa: S608
            "ORDER BY submitted_at DESC",
            tuple(params),
        )
        return [dict(r) for r in rows] if rows else []

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _require(cls, application_id: str, org_id: str) -> dict[str, Any]:
        """Fetch application or raise NotFoundError."""
        rows = execute_query(
            "SELECT * FROM readmission_applications WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(
                message=f"Re-admission application '{application_id}' not found.",
                details={"application_id": application_id, "org_id": org_id},
            )
        return dict(rows[0])
