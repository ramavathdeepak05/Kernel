"""
P4 — Application Form Service (Stage 2)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 3 (State Machine) + Layer 6 (Audit)

Manages the multi-step application form wizard:

    Step 1 — Personal details (DOB, gender, category, Aadhaar)
    Step 2 — Address details (permanent, correspondence, emergency contact)
    Step 3 — Academic qualifications (10th/12th/UG per normalized table)
    Step 4 — Entrance exam scores (JEE/NEET/CAT/state CET)
    Step 5 — Program preferences (ordered list)
    Step 6 — Documents (handled by DocumentVerificationService)
    Step 7 — Declaration + digital signature
    Step 8 — Application fee payment

State transitions owned by this service:
    LEAD / APPLIED → DRAFT         (form started)
    DRAFT          → SUBMITTED     (declaration accepted + fee triggered)
    SUBMITTED      → PENDING_PAYMENT  (fee payment initiated)
    PENDING_PAYMENT → DOCUMENTS_PENDING (fee confirmed)

Application ID format: APP-{YEAR}-{6-digit-zero-padded-seq}
e.g. APP-2025-000047
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, IllegalStateTransitionError
from server.core.state_registry import StudentState, validate_student_transition
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# States that are allowed to be "in-form"
_FORM_EDITABLE_STATES = {
    "LEAD", "APPLIED", "DRAFT", "SUBMITTED", "PENDING_PAYMENT",
}


# =============================================================================
# Pydantic Models — Stage 2
# =============================================================================

class PersonalDetailsRequest(BaseModel):
    """Step 1: Personal identity fields."""
    date_of_birth: Optional[str] = Field(
        default=None, description="ISO date: YYYY-MM-DD"
    )
    gender: Optional[str] = Field(
        default=None, description="MALE | FEMALE | OTHER | PREFER_NOT_TO_SAY"
    )
    nationality: Optional[str] = None
    category: Optional[str] = Field(
        default=None, description="GENERAL | SC | ST | OBC_NCL | EWS | PWD"
    )
    aadhaar_number: Optional[str] = Field(
        default=None, min_length=12, max_length=12
    )
    has_disability: Optional[bool] = None
    special_requirements: Optional[str] = None


class AddressRequest(BaseModel):
    """Step 2: Address information."""
    permanent_address: Optional[Dict[str, Any]] = Field(
        default=None,
        description="{line1, line2, city, state, pincode, country}"
    )
    correspondence_address: Optional[Dict[str, Any]] = None
    emergency_contact: Optional[Dict[str, Any]] = Field(
        default=None,
        description="{name, relation, phone, email}"
    )


class AcademicQualificationRequest(BaseModel):
    """Step 3: One academic level record (10th / 12th / UG / PG)."""
    applicant_id: str
    level: str = Field(..., description="CLASS_10 | CLASS_12 | DIPLOMA | UG | PG | OTHER")
    board_or_university: str = Field(..., min_length=2, max_length=200)
    institution_name: str = Field(..., min_length=2, max_length=300)
    year_of_passing: int = Field(..., ge=1980, le=2030)
    stream_or_subject: Optional[str] = None
    marks_obtained: Optional[int] = None
    max_marks: Optional[int] = None
    percentage: Optional[float] = Field(default=None, ge=0, le=100)
    cgpa: Optional[float] = Field(default=None, ge=0, le=10)
    grade_scale: Optional[float] = Field(default=None, ge=0)
    pass_status: str = Field(default="PASSED")


class AcademicQualificationRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    level: str
    board_or_university: str
    institution_name: str
    year_of_passing: int
    stream_or_subject: Optional[str] = None
    marks_obtained: Optional[int] = None
    max_marks: Optional[int] = None
    percentage: Optional[float] = None
    cgpa: Optional[float] = None
    grade_scale: Optional[float] = None
    pass_status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class EntranceScoreRequest(BaseModel):
    """Step 4: One entrance exam score record."""
    applicant_id: str
    exam_name: str = Field(
        ..., description="JEE_MAINS | NEET | CAT | MAT | XAT | SAT | STATE_CET | OTHER"
    )
    exam_roll_number: Optional[str] = None
    exam_year: Optional[int] = Field(default=None, ge=2000, le=2030)
    score: Optional[float] = None
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    rank: Optional[int] = Field(default=None, ge=1)
    score_detail: Optional[Dict[str, Any]] = Field(default_factory=dict)


class EntranceScoreRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    exam_name: str
    exam_roll_number: Optional[str] = None
    exam_year: Optional[int] = None
    score: Optional[float] = None
    percentile: Optional[float] = None
    rank: Optional[int] = None
    score_detail: Optional[Dict[str, Any]] = None
    is_verified: bool
    verified_method: Optional[str] = None
    created_at: datetime


class ProgramPreferenceItem(BaseModel):
    """One program preference entry (ordered)."""
    program_name: str = Field(..., min_length=2, max_length=200)
    specialization: Optional[str] = None
    intake_batch: Optional[str] = None


class ProgramPreferencesRequest(BaseModel):
    """Step 5: Full ordered list of program preferences (replaces existing)."""
    applicant_id: str
    preferences: List[ProgramPreferenceItem] = Field(..., min_length=1, max_length=5)


class DeclarationRequest(BaseModel):
    """Step 7: Accept declaration and provide digital signature."""
    applicant_id: str
    digital_signature: str = Field(
        ..., min_length=2,
        description="Typed full name as digital signature"
    )


class ApplicationFeeRequest(BaseModel):
    """Step 8: Record application fee payment."""
    applicant_id: str
    payment_reference: str = Field(..., min_length=3, max_length=100)
    fee_amount: float = Field(..., gt=0)


class ApplicationDraftRead(BaseModel):
    """Full application form read model (with extended fields)."""
    id: str
    org_id: str
    name: str
    email: str
    phone: str
    intended_program: str
    source_channel: str
    status: str
    application_id: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    category: Optional[str] = None
    aadhaar_number: Optional[str] = None
    permanent_address: Optional[Dict[str, Any]] = None
    correspondence_address: Optional[Dict[str, Any]] = None
    emergency_contact: Optional[Dict[str, Any]] = None
    hostel_required: bool = False
    scholarship_required: bool = False
    has_disability: bool = False
    special_requirements: Optional[str] = None
    declaration_accepted: bool = False
    declaration_accepted_at: Optional[datetime] = None
    digital_signature: Optional[str] = None
    submitted_at: Optional[datetime] = None
    application_fee_paid: bool = False
    application_fee_amount: Optional[float] = None
    application_fee_ref: Optional[str] = None
    study_mode: Optional[str] = None
    intake_batch: Optional[str] = None
    work_experience_months: Optional[int] = None
    lead_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# =============================================================================
# APPLICATION FORM SERVICE
# =============================================================================

class ApplicationFormService:
    """
    Multi-step application form wizard.

    Each method corresponds to one form step and can be called
    independently — progress is persisted to DB after each step.
    """

    # -------------------------------------------------------------------------
    # Draft initiation
    # -------------------------------------------------------------------------

    @classmethod
    def start_draft(cls, applicant_id: str, org_id: str, actor_id: str) -> ApplicationDraftRead:
        """
        Transition an applicant into DRAFT state and assign an Application ID.

        Idempotent — if already in DRAFT or further, returns current record.
        Application ID format: APP-{YEAR}-{6-digit-seq}
        """
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant '{applicant_id}' not found.")

        applicant = rows[0]
        current_status = applicant["status"]

        # If already in DRAFT or further, just return current
        if current_status not in ("LEAD", "APPLIED"):
            return cls._to_draft_read(applicant)

        # Generate Application ID if not set
        app_id = applicant.get("application_id")
        if not app_id:
            app_id = cls._generate_application_id(org_id)

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE applicants SET status = %s, application_id = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                ("DRAFT", app_id, now, applicant_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={
                "from_state": current_status,
                "to_state": "DRAFT",
                "application_id": app_id,
            },
        )

        logger.info("Application draft started: %s [app_id=%s]", applicant_id, app_id)
        return cls.get_draft(applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Step-by-step form save
    # -------------------------------------------------------------------------

    @classmethod
    def save_personal_details(
        cls,
        applicant_id: str,
        org_id: str,
        request: PersonalDetailsRequest,
        actor_id: str,
    ) -> ApplicationDraftRead:
        """Step 1: Save personal identity fields."""
        cls._assert_form_editable(applicant_id, org_id)

        updates: Dict[str, Any] = {}
        if request.date_of_birth is not None:
            updates["date_of_birth"] = request.date_of_birth
        if request.gender is not None:
            updates["gender"] = request.gender
        if request.nationality is not None:
            updates["nationality"] = request.nationality
        if request.category is not None:
            updates["category"] = request.category
        if request.aadhaar_number is not None:
            updates["aadhaar_number"] = request.aadhaar_number
        if request.has_disability is not None:
            updates["has_disability"] = request.has_disability
        if request.special_requirements is not None:
            updates["special_requirements"] = request.special_requirements

        cls._update_applicant(applicant_id, org_id, updates)
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"step": "personal_details", "fields": list(updates.keys())},
        )
        return cls.get_draft(applicant_id, org_id)

    @classmethod
    def save_address(
        cls,
        applicant_id: str,
        org_id: str,
        request: AddressRequest,
        actor_id: str,
    ) -> ApplicationDraftRead:
        """Step 2: Save address information."""
        cls._assert_form_editable(applicant_id, org_id)

        updates: Dict[str, Any] = {}
        if request.permanent_address is not None:
            updates["permanent_address"] = json.dumps(request.permanent_address)
        if request.correspondence_address is not None:
            updates["correspondence_address"] = json.dumps(request.correspondence_address)
        if request.emergency_contact is not None:
            updates["emergency_contact"] = json.dumps(request.emergency_contact)

        cls._update_applicant(applicant_id, org_id, updates)
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"step": "address"},
        )
        return cls.get_draft(applicant_id, org_id)

    @classmethod
    def accept_declaration(
        cls,
        applicant_id: str,
        org_id: str,
        request: DeclarationRequest,
        actor_id: str,
    ) -> ApplicationDraftRead:
        """Step 7: Record declaration acceptance and digital signature."""
        cls._assert_form_editable(applicant_id, org_id)

        now = datetime.now(timezone.utc)
        cls._update_applicant(applicant_id, org_id, {
            "declaration_accepted": True,
            "declaration_accepted_at": now,
            "digital_signature": request.digital_signature,
        })

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"step": "declaration", "digital_signature": request.digital_signature[:50]},
        )
        return cls.get_draft(applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Submit
    # -------------------------------------------------------------------------

    @classmethod
    def submit_application(
        cls,
        applicant_id: str,
        org_id: str,
        actor_id: str,
    ) -> ApplicationDraftRead:
        """
        Submit the application: DRAFT → SUBMITTED.

        Pre-conditions:
        - declaration_accepted = TRUE
        - At least one academic qualification on record
        - Applicant is in DRAFT state
        """
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant '{applicant_id}' not found.")

        applicant = rows[0]

        if applicant["status"] != "DRAFT":
            raise BusinessRuleViolation(
                message=f"Application must be in DRAFT state to submit. "
                        f"Current: {applicant['status']}",
                details={"status": applicant["status"]},
            )

        if not applicant.get("declaration_accepted"):
            raise BusinessRuleViolation(
                message="Declaration must be accepted before submitting the application.",
                details={"applicant_id": applicant_id},
            )

        # Verify at least one academic qualification exists
        qual_rows = execute_query(
            "SELECT id FROM academic_qualifications WHERE applicant_id = %s LIMIT 1",
            (applicant_id,),
        )
        if not qual_rows:
            raise BusinessRuleViolation(
                message="At least one academic qualification must be added before submitting.",
                details={"applicant_id": applicant_id},
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE applicants SET status = %s, submitted_at = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                ("SUBMITTED", now, now, applicant_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={
                "from_state": "DRAFT",
                "to_state": "SUBMITTED",
                "application_id": applicant.get("application_id"),
                "submitted_at": now.isoformat(),
            },
        )

        logger.info("Application submitted: %s [app_id=%s]", applicant_id, applicant.get("application_id"))
        return cls.get_draft(applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Application fee
    # -------------------------------------------------------------------------

    @classmethod
    def record_application_fee(
        cls,
        request: ApplicationFeeRequest,
        org_id: str,
        actor_id: str,
    ) -> ApplicationDraftRead:
        """
        Record application fee payment (SUBMITTED → PENDING_PAYMENT → DOCUMENTS_PENDING).

        Marks fee as paid and advances state to DOCUMENTS_PENDING.
        """
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant '{request.applicant_id}' not found.")

        applicant = rows[0]

        if applicant["status"] not in ("SUBMITTED", "PENDING_PAYMENT"):
            raise BusinessRuleViolation(
                message=f"Application fee can only be recorded in SUBMITTED or PENDING_PAYMENT state. "
                        f"Current: {applicant['status']}",
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                UPDATE applicants
                SET application_fee_paid = TRUE,
                    application_fee_amount = %s,
                    application_fee_ref = %s,
                    status = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    request.fee_amount,
                    request.payment_reference,
                    "DOCUMENTS_PENDING",
                    now,
                    request.applicant_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=request.applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={
                "from_state": applicant["status"],
                "to_state": "DOCUMENTS_PENDING",
                "fee_amount": request.fee_amount,
                "payment_reference": request.payment_reference,
            },
        )

        logger.info(
            "Application fee recorded: %s [ref=%s amount=%.2f]",
            request.applicant_id, request.payment_reference, request.fee_amount,
        )
        return cls.get_draft(request.applicant_id, org_id)

    # -------------------------------------------------------------------------
    # Academic Qualifications
    # -------------------------------------------------------------------------

    @classmethod
    def add_academic_qualification(
        cls,
        request: AcademicQualificationRequest,
        org_id: str,
        actor_id: str,
    ) -> AcademicQualificationRead:
        """Add or replace an academic qualification for a given level."""
        cls._assert_form_editable(request.applicant_id, org_id)

        qual_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Upsert: delete existing for same applicant+level, then insert
        execute_transaction([
            (
                "DELETE FROM academic_qualifications "
                "WHERE applicant_id = %s AND org_id = %s AND level = %s",
                (request.applicant_id, org_id, request.level),
            ),
            (
                """
                INSERT INTO academic_qualifications (
                    id, org_id, applicant_id, level,
                    board_or_university, institution_name,
                    year_of_passing, stream_or_subject,
                    marks_obtained, max_marks,
                    percentage, cgpa, grade_scale,
                    pass_status, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    qual_id, org_id,
                    request.applicant_id, request.level,
                    request.board_or_university,
                    request.institution_name,
                    request.year_of_passing,
                    request.stream_or_subject,
                    request.marks_obtained,
                    request.max_marks,
                    request.percentage,
                    request.cgpa,
                    request.grade_scale,
                    request.pass_status,
                    now, now,
                ),
            ),
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="academic_qualification",
            entity_id=qual_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"applicant_id": request.applicant_id, "level": request.level},
        )

        rows = execute_query(
            "SELECT * FROM academic_qualifications WHERE id = %s",
            (qual_id,),
        )
        return AcademicQualificationRead(**rows[0])

    @classmethod
    def list_academic_qualifications(
        cls, applicant_id: str, org_id: str
    ) -> List[AcademicQualificationRead]:
        rows = execute_query(
            "SELECT * FROM academic_qualifications "
            "WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY year_of_passing ASC",
            (applicant_id, org_id),
        )
        return [AcademicQualificationRead(**r) for r in rows]

    # -------------------------------------------------------------------------
    # Entrance Exam Scores
    # -------------------------------------------------------------------------

    @classmethod
    def add_entrance_score(
        cls,
        request: EntranceScoreRequest,
        org_id: str,
        actor_id: str,
    ) -> EntranceScoreRead:
        """Add an entrance exam score. Multiple exams per applicant allowed."""
        cls._assert_form_editable(request.applicant_id, org_id)

        score_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO entrance_exam_scores (
                    id, org_id, applicant_id,
                    exam_name, exam_roll_number, exam_year,
                    score, percentile, rank, score_detail,
                    is_verified, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (
                    score_id, org_id, request.applicant_id,
                    request.exam_name,
                    request.exam_roll_number,
                    request.exam_year,
                    request.score,
                    request.percentile,
                    request.rank,
                    json.dumps(request.score_detail or {}),
                    False,
                    now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="entrance_exam_score",
            entity_id=score_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"applicant_id": request.applicant_id, "exam": request.exam_name},
        )

        rows = execute_query(
            "SELECT * FROM entrance_exam_scores WHERE id = %s",
            (score_id,),
        )
        return EntranceScoreRead(**rows[0])

    @classmethod
    def list_entrance_scores(
        cls, applicant_id: str, org_id: str
    ) -> List[EntranceScoreRead]:
        rows = execute_query(
            "SELECT * FROM entrance_exam_scores "
            "WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY created_at ASC",
            (applicant_id, org_id),
        )
        return [EntranceScoreRead(**r) for r in rows]

    @classmethod
    def delete_entrance_score(
        cls, score_id: str, applicant_id: str, org_id: str, actor_id: str
    ) -> None:
        """Remove an entrance score entry (only while form is editable)."""
        cls._assert_form_editable(applicant_id, org_id)
        execute_transaction([
            (
                "DELETE FROM entrance_exam_scores "
                "WHERE id = %s AND applicant_id = %s AND org_id = %s",
                (score_id, applicant_id, org_id),
            )
        ])
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="entrance_exam_score",
            entity_id=score_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"action": "deleted"},
        )

    # -------------------------------------------------------------------------
    # Program Preferences
    # -------------------------------------------------------------------------

    @classmethod
    def set_program_preferences(
        cls,
        request: ProgramPreferencesRequest,
        org_id: str,
        actor_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Set ordered program preferences (replaces all existing for applicant).

        Max 5 preferences. Preference order is 1-indexed.
        """
        cls._assert_form_editable(request.applicant_id, org_id)

        now = datetime.now(timezone.utc)
        inserts = []
        for i, pref in enumerate(request.preferences, start=1):
            inserts.append((
                """
                INSERT INTO program_preferences
                    (id, org_id, applicant_id, preference_order, program_name,
                     specialization, intake_batch, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid4()), org_id, request.applicant_id,
                    i, pref.program_name, pref.specialization,
                    pref.intake_batch, now,
                ),
            ))

        execute_transaction([
            (
                "DELETE FROM program_preferences WHERE applicant_id = %s AND org_id = %s",
                (request.applicant_id, org_id),
            ),
            *inserts,
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="program_preferences",
            entity_id=request.applicant_id,
            org_id=org_id,
            module="M1",
            wizard="Application Form",
            success=True,
            metadata={"count": len(request.preferences)},
        )

        rows = execute_query(
            "SELECT * FROM program_preferences "
            "WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY preference_order ASC",
            (request.applicant_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def get_program_preferences(
        cls, applicant_id: str, org_id: str
    ) -> List[Dict[str, Any]]:
        rows = execute_query(
            "SELECT * FROM program_preferences "
            "WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY preference_order ASC",
            (applicant_id, org_id),
        )
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    @classmethod
    def get_draft(cls, applicant_id: str, org_id: str) -> ApplicationDraftRead:
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant '{applicant_id}' not found.")
        return cls._to_draft_read(rows[0])

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    @classmethod
    def _assert_form_editable(cls, applicant_id: str, org_id: str) -> None:
        rows = execute_query(
            "SELECT status FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant '{applicant_id}' not found.")
        status = rows[0]["status"]
        if status not in _FORM_EDITABLE_STATES:
            raise BusinessRuleViolation(
                message=f"Application form cannot be edited in status '{status}'.",
                details={"status": status, "editable_statuses": list(_FORM_EDITABLE_STATES)},
            )

    @classmethod
    def _update_applicant(
        cls, applicant_id: str, org_id: str, updates: Dict[str, Any]
    ) -> None:
        if not updates:
            return
        updates["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        execute_transaction([
            (
                f"UPDATE applicants SET {set_clause} WHERE id = %s AND org_id = %s",
                (*updates.values(), applicant_id, org_id),
            )
        ])

    @classmethod
    def _generate_application_id(cls, org_id: str) -> str:
        """Generate next sequential Application ID: APP-{YEAR}-{6-digit-seq}."""
        year = datetime.now(timezone.utc).year
        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM applicants "
            "WHERE org_id = %s AND application_id IS NOT NULL "
            "AND application_id LIKE %s",
            (org_id, f"APP-{year}-%"),
        )
        seq = (rows[0]["cnt"] if rows else 0) + 1
        return f"APP-{year}-{seq:06d}"

    @classmethod
    def _to_draft_read(cls, row: Dict[str, Any]) -> ApplicationDraftRead:
        # Handle JSONB fields that may come back as dicts or strings
        for field in ("permanent_address", "correspondence_address", "emergency_contact"):
            val = row.get(field)
            if isinstance(val, str):
                try:
                    row[field] = json.loads(val)
                except (ValueError, TypeError):
                    row[field] = None
        return ApplicationDraftRead(**{
            k: v for k, v in row.items()
            if k in ApplicationDraftRead.model_fields
        })
