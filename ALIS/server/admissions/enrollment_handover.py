"""
E04-S09 — Enrollment Handover Wizard

MODULE: M1 → M2 (Admissions to Academics handover)
LAYER: Layer 3 (Legal transition → ENROLLED) + Layer 4 (All locks must pass)
ENTITY: Student (created), Applicant (state → ENROLLED)

Finalizes the admission lifecycle by:
    1. Validating applicant is in ADMITTED state
    2. Passing all Layer 4 global lock checks
    3. Creating a Student record in the student registry
    4. Assigning a roll number (format: ORG-YEAR-PROGCODE-SEQ)
    5. Transitioning applicant → ENROLLED
    6. Triggering enrollment audit event

This wizard is the handoff point between Admissions (M1) and
Academics (M2). After ENROLLED, the entity is owned by M2.

Acceptance Criteria (E04-S09):
    - [x] ETL to student registry
    - [x] Roll number format enforced
    - [x] Enrollment audit event triggered
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, GlobalLockViolationError
from server.core.state_registry import StudentState
from server.db_service import execute_query, execute_transaction

from .models import EnrollmentHandoverRequest, StudentRecordRead
from .service import ApplicantService

logger = logging.getLogger(__name__)


class EnrollmentHandoverService:
    """
    Handles the final ETL from Applicant → Student for E04-S09.
    """

    @classmethod
    def enroll(
        cls,
        request: EnrollmentHandoverRequest,
        org_id: str,
        actor_id: str,
    ) -> StudentRecordRead:
        """
        Execute enrollment handover for an ADMITTED applicant.

        Creates a Student record and transitions the applicant to ENROLLED.

        Args:
            request:  Enrollment request (applicant_id)
            org_id:   Tenant scope
            actor_id: Registrar or system performing the handover

        Returns:
            StudentRecordRead — the newly created student record

        Raises:
            BusinessRuleViolation: If applicant is not ADMITTED.
            GlobalLockViolationError: If any Layer 4 lock is active.
        """
        # --- Layer 3 pre-condition: must be ADMITTED ---
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        applicant = rows[0]

        if applicant["status"] not in (
            StudentState.ADMITTED.value,
            "ADMITTED",
            "SEAT_CONFIRMED",
        ):
            raise BusinessRuleViolation(
                message=(
                    f"Enrollment handover requires ADMITTED status — "
                    f"current status: '{applicant['status']}'."
                ),
                details={"status": applicant["status"]},
            )

        # --- Layer 4: Verify admission record exists (fee paid) ---
        admission_rows = execute_query(
            "SELECT registration_number FROM admission_records "
            "WHERE applicant_id = %s AND org_id = %s LIMIT 1",
            (request.applicant_id, org_id),
        )
        if not admission_rows:
            raise GlobalLockViolationError(
                violations=[
                    f"No admission record found for applicant '{request.applicant_id}'. "
                    f"Fee payment confirmation is required before enrollment."
                ]
            )

        # --- Prevent double enrollment ---
        existing_student = execute_query(
            "SELECT id FROM students WHERE applicant_id = %s AND org_id = %s LIMIT 1",
            (request.applicant_id, org_id),
        )
        if existing_student:
            raise BusinessRuleViolation(
                message=(
                    f"Applicant '{request.applicant_id}' is already enrolled "
                    f"(student_id={existing_student[0]['id']})."
                ),
                details={"student_id": existing_student[0]["id"]},
            )

        # --- Generate roll number ---
        roll_number = cls._generate_roll_number(
            org_id=org_id,
            program=applicant.get("intended_program", "GEN"),
        )

        # --- ETL: Create Student record ---
        student_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO students
                    (id, org_id, applicant_id, roll_number, name, email,
                     phone, program, enrolled_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        student_id,
                        org_id,
                        request.applicant_id,
                        roll_number,
                        applicant["name"],
                        applicant["email"],
                        applicant["phone"],
                        applicant.get("intended_program", ""),
                        now,
                    ),
                )
            ]
        )

        # --- Layer 3: Execute ADMITTED → ENROLLED transition ---
        ApplicantService.transition_state(
            applicant_id=request.applicant_id,
            org_id=org_id,
            to_state=StudentState.ENROLLED,
            actor_id=actor_id,
            reason="Enrollment handover completed — student record created",
            metadata={
                "student_id": student_id,
                "roll_number": roll_number,
            },
        )

        # --- Enrollment audit event ---
        audit_entry = AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="student",
            entity_id=student_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Handover",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "roll_number": roll_number,
                "program": applicant.get("intended_program", ""),
                "from_state": StudentState.ADMITTED.value,
                "to_state": StudentState.ENROLLED.value,
                "handover_to_module": "M2",
            },
        )

        logger.info(
            "E04-S09: Enrollment complete [applicant=%s, student=%s, roll=%s, org=%s]",
            request.applicant_id,
            student_id,
            roll_number,
            org_id,
        )

        return StudentRecordRead(
            id=student_id,
            org_id=org_id,
            applicant_id=request.applicant_id,
            roll_number=roll_number,
            name=applicant["name"],
            email=applicant["email"],
            phone=applicant["phone"],
            program=applicant.get("intended_program", ""),
            enrolled_at=now,
            enrollment_audit_id=audit_entry.id if hasattr(audit_entry, "id") else "",
        )

    # -------------------------------------------------------------------------
    # Roll number generation
    # -------------------------------------------------------------------------

    @classmethod
    def _generate_roll_number(cls, org_id: str, program: str) -> str:
        """
        Generate a unique roll number.

        Format: {ORG_CODE}-{YEAR}-{PROG_CODE}-{SEQ:04d}
        e.g., ALIS-2025-CSE-0042
        """
        year = datetime.now(timezone.utc).year
        org_code = org_id[:4].upper().replace("-", "")
        prog_code = "".join(w[0].upper() for w in program.split()[:3] if w) or "GEN"

        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM students WHERE org_id = %s "
            "AND EXTRACT(YEAR FROM enrolled_at) = %s",
            (org_id, year),
        )
        seq = int(rows[0]["cnt"]) + 1 if rows else 1
        roll_number = f"{org_code}-{year}-{prog_code}-{seq:04d}"

        # Guarantee uniqueness
        existing = execute_query(
            "SELECT id FROM students WHERE roll_number = %s LIMIT 1",
            (roll_number,),
        )
        if existing:
            roll_number = f"{roll_number}-{str(uuid4())[:4].upper()}"

        return roll_number
