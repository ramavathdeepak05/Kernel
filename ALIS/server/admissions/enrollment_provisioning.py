"""
P12 — Enrollment Provisioning (Stage 10)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 3 (State Transitions) + Layer 6 (Audit)
ENTITIES: EnrollmentProvisioning → students

Orchestrates the technical provisioning work that converts an accepted
applicant into an active student across all institutional systems.

Workflow:
    1. initiate()          — Create provisioning record, assign roll number
    2. provision_lms()     — Create LMS account, store account ID
    3. provision_email()   — Assign university email address
    4. provision_library() — Register with library system
    5. dispatch_id_card()  — Trigger ID card printing/dispatch
    6. sync_erp()          — Push to ERP/student information system
    7. send_welcome_email() / send_parent_email() — Mark comms sent
    8. complete()          — All systems done → create student record → ENROLLED

State transitions owned here:
    READY_FOR_ENROLLMENT → complete() → ENROLLED
    READY_FOR_ENROLLMENT → cancel()  → CANCELLED
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

_PROV_STATUS = {"PENDING", "SYNCED", "EXPORT_READY", "FAILED"}
_SUBSYSTEM_STATUS = {"PENDING", "DONE", "SKIPPED", "FAILED"}

# =============================================================================
# Roll Number Generation
# =============================================================================

def _generate_roll_number(org_id: str, program: str, batch_year: int) -> str:
    """
    Generate a unique roll number: {PROGRAM_PREFIX}-{YEAR}-{SEQ:04d}

    Sequence is determined by counting existing enrollment records for the
    same org + program + batch year (atomic gap-free within a transaction).
    We use a DB counter approach: count existing roll numbers matching the
    prefix and add 1.

    Format examples: CS-2025-0001, MBA-2025-0042, BBA-2025-0003
    """
    prefix = _program_prefix(program)
    roll_prefix = f"{prefix}-{batch_year}-"

    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM enrollment_provisioning "
        "WHERE org_id = %s AND roll_number LIKE %s",
        (org_id, roll_prefix + "%"),
    )
    seq = (rows[0]["cnt"] if rows else 0) + 1
    return f"{roll_prefix}{seq:04d}"


def _program_prefix(program: str) -> str:
    """Derive a short uppercase prefix from program name."""
    if not program:
        return "GEN"
    words = program.upper().split()
    if len(words) == 1:
        return words[0][:6]
    # Acronym from first letters (max 4 chars)
    return "".join(w[0] for w in words if w)[:4]


# =============================================================================
# Pydantic Models
# =============================================================================

class EnrollmentInitiateRequest(BaseModel):
    applicant_id: str
    batch_year: int = Field(..., ge=2000, le=2100, description="Enrollment batch year e.g. 2025")
    university_reg_number: Optional[str] = Field(
        default=None,
        description="Pre-assigned university registration number (if any)"
    )
    notes: Optional[str] = None


class EnrollmentProvisioningRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    student_id: Optional[str] = None
    roll_number: Optional[str] = None
    university_reg_number: Optional[str] = None
    # LMS
    lms_status: str
    lms_account_id: Optional[str] = None
    lms_created_at: Optional[datetime] = None
    # Email
    email_status: str
    university_email: Optional[str] = None
    email_created_at: Optional[datetime] = None
    # Library
    library_status: str
    library_member_id: Optional[str] = None
    library_created_at: Optional[datetime] = None
    # ID Card
    id_card_status: str
    id_card_dispatched_at: Optional[datetime] = None
    # ERP
    erp_status: str
    erp_synced_at: Optional[datetime] = None
    erp_export_path: Optional[str] = None
    # Welcome comms
    welcome_email_sent: bool
    parent_email_sent: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class LMSProvisionRequest(BaseModel):
    lms_account_id: str = Field(..., min_length=1)
    status: str = Field(default="DONE", description="DONE | SKIPPED | FAILED")


class EmailProvisionRequest(BaseModel):
    university_email: str = Field(..., min_length=5)
    status: str = Field(default="DONE")


class LibraryProvisionRequest(BaseModel):
    library_member_id: str = Field(..., min_length=1)
    status: str = Field(default="DONE")


class ERPSyncRequest(BaseModel):
    status: str = Field(default="SYNCED", description="SYNCED | EXPORT_READY | FAILED")
    erp_export_path: Optional[str] = None


# =============================================================================
# Student Record (created on complete())
# =============================================================================

class StudentRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    roll_number: str
    name: str
    email: str
    phone: Optional[str] = None
    program: str
    enrolled_at: datetime


# =============================================================================
# ENROLLMENT PROVISIONING SERVICE
# =============================================================================

class EnrollmentProvisioningService:
    """
    Manages the step-by-step technical provisioning of a new student.

    One provisioning record per applicant (UNIQUE). Calling initiate()
    on an already-initiated applicant returns the existing record.

    Only complete() creates the student record and transitions the
    applicant to ENROLLED.
    """

    @classmethod
    def initiate(
        cls,
        request: EnrollmentInitiateRequest,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """
        Create enrollment provisioning record and assign roll number.

        Pre-condition: applicant must be READY_FOR_ENROLLMENT.
        Idempotent: returns existing record if already initiated.
        """
        # Idempotency
        existing = execute_query(
            "SELECT * FROM enrollment_provisioning WHERE applicant_id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if existing:
            return cls._row_to_read(existing[0])

        # Pre-condition
        app_rows = execute_query(
            "SELECT status, name, email, phone, intended_program "
            "FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        app = app_rows[0]
        if app["status"] not in (StudentState.READY_FOR_ENROLLMENT.value, "READY_FOR_ENROLLMENT"):
            raise BusinessRuleViolation(
                message=(
                    f"Enrollment provisioning requires READY_FOR_ENROLLMENT status — "
                    f"current: '{app['status']}'."
                ),
                details={"status": app["status"]},
            )

        # Generate roll number
        program = app.get("intended_program") or "GEN"
        roll_number = _generate_roll_number(org_id, program, request.batch_year)

        prov_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO enrollment_provisioning (
                    id, org_id, applicant_id,
                    roll_number, university_reg_number,
                    lms_status, email_status, library_status,
                    id_card_status, erp_status,
                    welcome_email_sent, parent_email_sent,
                    created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    prov_id, org_id, request.applicant_id,
                    roll_number, request.university_reg_number,
                    "PENDING", "PENDING", "PENDING",
                    "PENDING", "PENDING",
                    False, False,
                    now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=prov_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "roll_number": roll_number,
                "batch_year": request.batch_year,
            },
        )

        logger.info(
            "P12: Enrollment provisioning initiated [id=%s, applicant=%s, roll=%s]",
            prov_id, request.applicant_id, roll_number,
        )
        return cls.get(prov_id, org_id)

    @classmethod
    def provision_lms(
        cls,
        provisioning_id: str,
        request: LMSProvisionRequest,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """Record LMS account creation."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE enrollment_provisioning "
                "SET lms_status = %s, lms_account_id = %s, lms_created_at = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (request.status, request.lms_account_id, now, now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "lms", "lms_account_id": request.lms_account_id, "status": request.status},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def provision_email(
        cls,
        provisioning_id: str,
        request: EmailProvisionRequest,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """Record university email assignment."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE enrollment_provisioning "
                "SET email_status = %s, university_email = %s, email_created_at = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (request.status, request.university_email, now, now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "email", "university_email": request.university_email},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def provision_library(
        cls,
        provisioning_id: str,
        request: LibraryProvisionRequest,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """Record library membership creation."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE enrollment_provisioning "
                "SET library_status = %s, library_member_id = %s, library_created_at = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (request.status, request.library_member_id, now, now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "library", "library_member_id": request.library_member_id},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def dispatch_id_card(
        cls,
        provisioning_id: str,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """Mark ID card as dispatched."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE enrollment_provisioning "
                "SET id_card_status = 'DONE', id_card_dispatched_at = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "id_card", "dispatched_at": now.isoformat()},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def sync_erp(
        cls,
        provisioning_id: str,
        request: ERPSyncRequest,
        org_id: str,
        actor_id: str,
    ) -> EnrollmentProvisioningRead:
        """Record ERP sync status."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE enrollment_provisioning "
                "SET erp_status = %s, erp_synced_at = %s, erp_export_path = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (request.status, now, request.erp_export_path, now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "erp", "status": request.status, "export_path": request.erp_export_path},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def mark_welcome_email_sent(
        cls,
        provisioning_id: str,
        org_id: str,
        actor_id: str,
        parent: bool = False,
    ) -> EnrollmentProvisioningRead:
        """Mark welcome email (student or parent) as sent."""
        cls._require(provisioning_id, org_id)
        now = datetime.now(timezone.utc)

        field = "parent_email_sent" if parent else "welcome_email_sent"
        execute_transaction([
            (
                f"UPDATE enrollment_provisioning SET {field} = TRUE, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, provisioning_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="enrollment_provisioning",
            entity_id=provisioning_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={"step": "welcome_email", "parent": parent},
        )
        return cls.get(provisioning_id, org_id)

    @classmethod
    def complete(
        cls,
        provisioning_id: str,
        org_id: str,
        actor_id: str,
    ) -> StudentRead:
        """
        Finalize enrollment:
          1. Verify mandatory provisioning steps are done (LMS + email at minimum)
          2. Create student record
          3. Link student_id back to provisioning record
          4. Transition applicant → ENROLLED

        Returns the newly created StudentRead.
        """
        prov = cls._require(provisioning_id, org_id)

        # Mandatory gates
        if prov["lms_status"] not in ("DONE", "SKIPPED"):
            raise BusinessRuleViolation(
                message="Cannot complete enrollment — LMS provisioning is not done.",
                details={"lms_status": prov["lms_status"]},
            )
        if prov["email_status"] not in ("DONE", "SKIPPED"):
            raise BusinessRuleViolation(
                message="Cannot complete enrollment — Email provisioning is not done.",
                details={"email_status": prov["email_status"]},
            )
        if not prov.get("roll_number"):
            raise BusinessRuleViolation(
                message="Cannot complete enrollment — roll number not assigned."
            )

        # Load applicant details
        app_rows = execute_query(
            "SELECT name, email, phone, intended_program "
            "FROM applicants WHERE id = %s AND org_id = %s",
            (prov["applicant_id"], org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{prov['applicant_id']}' not found."
            )
        app = app_rows[0]

        now = datetime.now(timezone.utc)
        student_id = str(uuid4())

        execute_transaction([
            # Create student record
            (
                """
                INSERT INTO students (
                    id, org_id, applicant_id, roll_number,
                    name, email, phone, program, enrolled_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    student_id, org_id, prov["applicant_id"],
                    prov["roll_number"],
                    app["name"], app["email"], app.get("phone"),
                    app.get("intended_program") or "GENERAL",
                    now,
                ),
            ),
            # Link student_id back to provisioning
            (
                "UPDATE enrollment_provisioning SET student_id = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (student_id, now, provisioning_id, org_id),
            ),
        ])

        # Transition applicant → ENROLLED
        ApplicantService.transition_state(
            applicant_id=prov["applicant_id"],
            org_id=org_id,
            to_state=StudentState.ENROLLED,
            actor_id=actor_id,
            reason="Enrollment provisioning completed — student record created.",
            metadata={
                "provisioning_id": provisioning_id,
                "student_id": student_id,
                "roll_number": prov["roll_number"],
            },
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="student",
            entity_id=student_id,
            org_id=org_id,
            module="M1",
            wizard="Enrollment Provisioning",
            success=True,
            metadata={
                "applicant_id": prov["applicant_id"],
                "provisioning_id": provisioning_id,
                "roll_number": prov["roll_number"],
            },
        )

        logger.info(
            "P12: Student enrolled [student_id=%s, applicant=%s, roll=%s]",
            student_id, prov["applicant_id"], prov["roll_number"],
        )

        rows = execute_query(
            "SELECT * FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        return StudentRead(**rows[0])

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get(cls, provisioning_id: str, org_id: str) -> EnrollmentProvisioningRead:
        rows = execute_query(
            "SELECT * FROM enrollment_provisioning WHERE id = %s AND org_id = %s",
            (provisioning_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Enrollment provisioning '{provisioning_id}' not found."
            )
        return cls._row_to_read(rows[0])

    @classmethod
    def get_for_applicant(
        cls, applicant_id: str, org_id: str
    ) -> Optional[EnrollmentProvisioningRead]:
        rows = execute_query(
            "SELECT * FROM enrollment_provisioning WHERE applicant_id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        return cls._row_to_read(rows[0]) if rows else None

    @classmethod
    def get_student(cls, student_id: str, org_id: str) -> StudentRead:
        rows = execute_query(
            "SELECT * FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Student '{student_id}' not found."
            )
        return StudentRead(**rows[0])

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _require(cls, provisioning_id: str, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM enrollment_provisioning WHERE id = %s AND org_id = %s",
            (provisioning_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Enrollment provisioning '{provisioning_id}' not found."
            )
        return rows[0]

    @classmethod
    def _row_to_read(cls, row: Dict[str, Any]) -> EnrollmentProvisioningRead:
        return EnrollmentProvisioningRead(**dict(row))
