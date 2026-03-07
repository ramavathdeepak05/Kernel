"""
E04 — Admissions Entity Models

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity Definitions)

Defines all Pydantic models and DB-level entity structures for the
Admissions epic. These models represent the canonical Layer 1 entities
per the ALIS architecture — they carry no business logic.

Entities:
    Applicant            — E04-S01: Applicant Wizard
    LeadMergeLog         — E04-S02: Lead De-duplication Wizard
    ApplicationDocument  — E04-S04: Document Verification Wizard
    CounsellorAssignment — E04-S05: Counsellor Allocation Wizard
    OfferLetter          — E04-S06: Offer Letter Generation Wizard
    AdmissionRecord      — E04-S07: Admission Confirmation Wizard
    IntakeQualityScore   — E04-S08: Intake Quality Scoring Wizard
    StudentRecord        — E04-S09: Enrollment Handover Wizard
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class ApplicantStatus(str, Enum):
    """
    Applicant lifecycle states — mirrors StudentState in state_registry.py.
    Full 10-stage admissions pipeline (Stages 1–10).

    Old values (APPLIED, ADMITTED, ANNULLED) retained for backward-compat
    with existing pipeline code and any data already in the DB.
    """
    # Stage 1
    LEAD = "LEAD"
    # Stage 2
    DRAFT = "DRAFT"
    APPLIED = "APPLIED"             # legacy alias for SUBMITTED
    SUBMITTED = "SUBMITTED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    # Stage 3
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING"
    UNDER_DOCUMENT_REVIEW = "UNDER_DOCUMENT_REVIEW"
    DOCUMENTS_VERIFIED = "DOCUMENTS_VERIFIED"
    # Stage 4
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PROVISIONALLY_ELIGIBLE = "PROVISIONALLY_ELIGIBLE"
    # Stage 5
    ASSESSMENT_SCHEDULED = "ASSESSMENT_SCHEDULED"
    ASSESSMENT_COMPLETE = "ASSESSMENT_COMPLETE"
    # Stage 6
    MERIT_LISTED = "MERIT_LISTED"
    WAITLISTED = "WAITLISTED"
    # Stage 7
    OFFER_ISSUED = "OFFER_ISSUED"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"
    # Stage 8
    ADMITTED = "ADMITTED"           # legacy alias for SEAT_CONFIRMED
    SEAT_CONFIRMED = "SEAT_CONFIRMED"
    # Stage 9
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    READY_FOR_ENROLLMENT = "READY_FOR_ENROLLMENT"
    # Stage 10
    ENROLLED = "ENROLLED"
    # Terminal
    CANCELLED = "CANCELLED"
    ANNULLED = "ANNULLED"           # legacy alias for CANCELLED


class SourceChannel(str, Enum):
    """How the lead / applicant was acquired."""
    WEBSITE = "WEBSITE"
    REFERRAL_STUDENT = "REFERRAL_STUDENT"
    REFERRAL_STAFF = "REFERRAL_STAFF"
    CONSULTANT = "CONSULTANT"
    SOCIAL_AD = "SOCIAL_AD"
    EDUCATION_FAIR = "EDUCATION_FAIR"
    THIRD_PARTY_PORTAL = "THIRD_PARTY_PORTAL"   # Shiksha, CollegeDekho, etc.
    WALK_IN = "WALK_IN"
    AGENT_ASSISTED = "AGENT_ASSISTED"           # counsellor submitted on behalf
    CSV_IMPORT = "CSV_IMPORT"                   # NTA / state CET import
    OTHER = "OTHER"


class DocumentType(str, Enum):
    """Document types required during the admissions process (Stages 3 & 9)."""
    MARKSHEET_10 = "MARKSHEET_10"
    MARKSHEET_12 = "MARKSHEET_12"
    TRANSFER_CERTIFICATE = "TRANSFER_CERTIFICATE"
    CHARACTER_CERTIFICATE = "CHARACTER_CERTIFICATE"
    MIGRATION_CERTIFICATE = "MIGRATION_CERTIFICATE"
    CATEGORY_CERTIFICATE = "CATEGORY_CERTIFICATE"       # SC/ST/OBC/EWS
    PHOTO = "PHOTO"
    GOVT_ID = "GOVT_ID"                                 # Aadhaar / Passport
    ENTRANCE_SCORECARD = "ENTRANCE_SCORECARD"           # JEE/NEET/CAT result
    GAP_CERTIFICATE = "GAP_CERTIFICATE"
    DEGREE_CERTIFICATE = "DEGREE_CERTIFICATE"           # UG degree for PG applicants
    EXPERIENCE_LETTER = "EXPERIENCE_LETTER"             # for MBA/executive programs
    MEDICAL_FITNESS = "MEDICAL_FITNESS"
    PASSPORT = "PASSPORT"                               # NRI / international
    EQUIVALENCY_CERTIFICATE = "EQUIVALENCY_CERTIFICATE" # foreign qualifications
    OTHER = "OTHER"


class DocumentStatus(str, Enum):
    """Per-document lifecycle status."""
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REUPLOAD_REQUESTED = "REUPLOAD_REQUESTED"


class DocumentVerificationMethod(str, Enum):
    """How a document was verified."""
    AI_AUTO = "ai_auto"
    MANUAL_OFFICER = "manual_officer"
    ADMIN_OVERRIDE = "admin_override"


class AllocationMethod(str, Enum):
    """How counsellor was matched to applicant."""
    VECTOR_SEARCH = "vector_search"
    LOAD_BALANCED = "load_balanced"
    MANUAL = "manual"


# =============================================================================
# E04-S01: APPLICANT
# =============================================================================

class ApplicantCreate(BaseModel):
    """Input schema for creating a new applicant (LEAD → APPLIED)."""
    name: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., description="Primary contact email")
    phone: str = Field(..., min_length=7, max_length=20)
    intended_program: str = Field(..., min_length=2, max_length=200)
    source_channel: SourceChannel = Field(default=SourceChannel.WEBSITE)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 7:
            raise ValueError("Phone number must contain at least 7 digits")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.strip().lower()


class ApplicantRead(BaseModel):
    """Output schema for an applicant record."""
    id: str
    org_id: str
    name: str
    email: str
    phone: str
    intended_program: str
    source_channel: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# E04-S02: LEAD MERGE LOG
# =============================================================================

class LeadMergeRequest(BaseModel):
    """Input for initiating a lead merge."""
    primary_applicant_id: str
    duplicate_applicant_id: str
    justification: Optional[str] = Field(
        default=None,
        description="Required for manual merges (confidence < 0.9)"
    )


class LeadMergeLog(BaseModel):
    """Audit record of a lead merge operation."""
    id: str
    org_id: str
    primary_id: str
    merged_id: str
    similarity_score: float
    method: str   # "auto" | "admin_approved"
    justification: Optional[str]
    merged_by: str
    created_at: datetime


# =============================================================================
# E04-S04: APPLICATION DOCUMENT
# =============================================================================

class DocumentUploadRequest(BaseModel):
    """Input for uploading an application document."""
    applicant_id: str
    doc_type: DocumentType
    file_name: str = Field(..., min_length=1, max_length=255)
    file_content_base64: str = Field(
        ..., description="Base64-encoded file content"
    )


class ApplicationDocumentRead(BaseModel):
    """Output schema for a document record."""
    id: str
    org_id: str
    applicant_id: str
    doc_type: str
    file_path: str
    is_verified: bool
    verification_method: Optional[str] = None
    verification_detail: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime


# =============================================================================
# E04-S05: COUNSELLOR ASSIGNMENT
# =============================================================================

class CounsellorAssignRequest(BaseModel):
    """Input for requesting counsellor allocation."""
    applicant_id: str
    preferred_counsellor_id: Optional[str] = Field(
        default=None,
        description="Optional manual preference — triggers admin override path"
    )
    justification: Optional[str] = None


class CounsellorAssignmentRead(BaseModel):
    """Output schema for a counsellor assignment."""
    id: str
    org_id: str
    applicant_id: str
    counsellor_id: str
    method: str
    similarity_score: Optional[float]
    assigned_by: str
    created_at: datetime


# =============================================================================
# E04-S06: OFFER LETTER
# =============================================================================

class OfferLetterGenerateRequest(BaseModel):
    """Input for generating an offer letter."""
    applicant_id: str
    program_name: str
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{4}$")
    template_version: int = Field(default=1, ge=1)


class OfferLetterRead(BaseModel):
    """Output schema for an offer letter record."""
    id: str
    org_id: str
    applicant_id: str
    program_name: str
    academic_year: str
    template_version: int
    content_hash: str
    pdf_path: str
    issued_at: datetime
    is_valid: bool


# =============================================================================
# E04-S07: ADMISSION CONFIRMATION
# =============================================================================

class AdmissionConfirmRequest(BaseModel):
    """Input for confirming an admission (fee paid → ADMITTED)."""
    applicant_id: str
    payment_reference: str = Field(..., min_length=3, max_length=100)
    fee_amount: float = Field(..., gt=0)


class AdmissionRecordRead(BaseModel):
    """Output schema for an admission record."""
    id: str
    org_id: str
    applicant_id: str
    registration_number: str
    payment_reference: str
    fee_amount: float
    admitted_at: datetime
    admitted_by: str


# =============================================================================
# E04-S08: INTAKE QUALITY SCORE
# =============================================================================

class IntakeScoreRequest(BaseModel):
    """Input for scoring an intake batch."""
    batch_id: str = Field(
        ...,
        description="Intake batch identifier (e.g., 'AY2025-26-Q1')"
    )
    program: Optional[str] = None


class IntakeQualityScoreRead(BaseModel):
    """Output schema for an intake quality score."""
    id: str
    org_id: str
    batch_id: str
    program: Optional[str]
    quality_score: float
    factors: Dict[str, Any]
    alert_triggered: bool
    scored_at: datetime


# =============================================================================
# E04-S09: STUDENT RECORD (Post-Enrollment)
# =============================================================================

class EnrollmentHandoverRequest(BaseModel):
    """Input for triggering enrollment handover for an admitted applicant."""
    applicant_id: str


class StudentRecordRead(BaseModel):
    """Output schema for a newly created student record."""
    id: str
    org_id: str
    applicant_id: str
    roll_number: str
    name: str
    email: str
    phone: str
    program: str
    enrolled_at: datetime
    enrollment_audit_id: str
