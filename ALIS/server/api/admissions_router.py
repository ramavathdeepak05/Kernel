"""
E04 — Admissions API Router

MODULE: M1 — Admissions & Marketing
LAYER: Orchestration (FastAPI)

All E04 wizard endpoints. Every endpoint enforces RBAC, is tenant-aware,
and routes through the appropriate service layer — never directly to DB.

Endpoints:
    POST /api/v1/admissions/applicants                 — E04-S01: Create applicant
    GET  /api/v1/admissions/applicants/{id}            — Get applicant
    GET  /api/v1/admissions/applicants                 — List applicants
    POST /api/v1/admissions/leads/merge                — E04-S02: Lead de-dup
    GET  /api/v1/admissions/leads/{id}/duplicates      — Find duplicate leads
    POST /api/v1/admissions/eligibility/evaluate       — E04-S03: Eligibility eval
    POST /api/v1/admissions/documents/upload           — E04-S04: Doc upload
    POST /api/v1/admissions/documents/{id}/override    — E04-S04: Admin override
    GET  /api/v1/admissions/documents/{applicant_id}   — List documents
    POST /api/v1/admissions/counsellors/assign         — E04-S05: Counsellor allocation
    POST /api/v1/admissions/offers/generate            — E04-S06: Offer letter
    POST /api/v1/admissions/confirm                    — E04-S07: Admission confirmation
    POST /api/v1/admissions/intake/score               — E04-S08: Intake quality score
    POST /api/v1/admissions/enroll                     — E04-S09: Enrollment handover
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.exceptions import ALISError
from server.core.rbac import Permission, require_permission

from server.admissions.models import (
    ApplicantCreate,
    CounsellorAssignRequest,
    ConsultantCreate,
    DocumentUploadRequest,
    EnrollmentHandoverRequest,
    IntakeScoreRequest,
    LeadCreate,
    LeadConvertRequest,
    LeadMergeRequest,
    LeadUpdateRequest,
    LeadActivityCreate,
    OfferLetterGenerateRequest,
    OfferAcceptRequest,
    OfferDeclineRequest,
    OfferRevokeRequest,
    AdmissionConfirmRequest,
    ReferralCodeCreate,
)
from server.admissions.service import ApplicantService
from server.admissions.merit_list import (
    SeatMatrixService, SeatMatrixCreate,
    MeritListPolicyService, MeritListPolicyCreate,
    MeritListService, MeritListGenerateRequest,
)
from server.admissions.entrance_test import (
    AdmissionsTestService, AdmissionsTestCreate,
    TestSlotService, TestSlotCreate,
    TestRegistrationService, TestRegistrationCreate,
    TestScoreService, TestScoreCreate,
)
from server.admissions.interview import (
    InterviewPanelService, InterviewPanelCreate,
    InterviewScheduleService, InterviewScheduleCreate,
    InterviewScorecardService, InterviewScorecardCreate,
)
from server.admissions.application_form import (
    ApplicationFormService,
    PersonalDetailsRequest,
    AddressRequest,
    AcademicQualificationRequest,
    EntranceScoreRequest,
    ProgramPreferencesRequest,
    DeclarationRequest,
    ApplicationFeeRequest,
)
from server.admissions.lead_service import LeadService, ConsultantService, ReferralCodeService
from server.admissions.eligibility_criteria import EligibilityCriteriaService, EligibilityCriteria
from server.admissions.deduplication import LeadDeduplicationService
from server.admissions.eligibility_service import EligibilityService
from server.admissions.document_verification import DocumentVerificationService
from server.admissions.counsellor_allocation import CounsellorAllocationService
from server.admissions.counsellor_service import CounsellorService
from server.admissions.offer_letter import OfferLetterService
from server.admissions.confirmation import AdmissionConfirmationService
from server.admissions.intake_quality import IntakeQualityService
from server.admissions.enrollment_handover import EnrollmentHandoverService
from server.admissions.payment_v2 import (
    DemandDraftService, DemandDraftCreate,
    RefundRequestService, RefundRequestCreate,
)
from server.admissions.final_verification import (
    FinalVerificationService, FinalVerificationCreate,
    VerificationItemCreate,
    DiscrepancyService, DiscrepancyCreate,
)
from server.admissions.enrollment_provisioning import (
    EnrollmentProvisioningService,
    EnrollmentInitiateRequest,
    LMSProvisionRequest,
    EmailProvisionRequest,
    LibraryProvisionRequest,
    ERPSyncRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admissions", tags=["admissions"])


def _org(request: Request) -> str:
    """Extract org_id from request state (set by TenantMiddleware)."""
    return getattr(request.state, "tenant_id", "default")


def _actor(request: Request) -> str:
    return getattr(request.state, "user_id", "anonymous")


def _role(request: Request) -> Optional[str]:
    return getattr(request.state, "user_role", None)


# =============================================================================
# E04-S01: APPLICANT WIZARD
# =============================================================================

@router.post("/applicants")
@require_permission(Permission.STUDENT_CREATE)
async def create_applicant(request: Request, body: ApplicantCreate) -> JSONResponse:
    """Create a new applicant (LEAD → APPLIED)."""
    applicant = ApplicantService.create_applicant(
        data=body,
        org_id=_org(request),
        created_by=_actor(request),
    )
    return JSONResponse(status_code=201, content=applicant.model_dump(mode="json"))


@router.get("/applicants/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_applicant(request: Request, applicant_id: str) -> JSONResponse:
    applicant = ApplicantService.get_applicant(applicant_id, _org(request))
    return JSONResponse(status_code=200, content=applicant.model_dump(mode="json"))


@router.get("/applicants")
@require_permission(Permission.STUDENT_READ)
async def list_applicants(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
) -> JSONResponse:
    applicants = ApplicantService.list_applicants(
        org_id=_org(request), status=status, limit=limit, offset=offset
    )
    return JSONResponse(
        status_code=200,
        content={"applicants": [a.model_dump(mode="json") for a in applicants]},
    )


# =============================================================================
# E04-S02: LEAD DE-DUPLICATION WIZARD
# =============================================================================

@router.post("/leads/merge")
@require_permission(Permission.STUDENT_CREATE)
async def merge_leads(request: Request, body: LeadMergeRequest) -> JSONResponse:
    """Merge a duplicate lead into a primary applicant."""
    log = LeadDeduplicationService.merge(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=log.model_dump(mode="json"))


@router.get("/leads/{applicant_id}/duplicates")
@require_permission(Permission.STUDENT_READ)
async def find_duplicates(
    request: Request,
    applicant_id: str,
    top_n: int = Query(default=5, le=20),
) -> JSONResponse:
    """Find potential duplicate leads for an applicant."""
    duplicates = LeadDeduplicationService.find_duplicates(
        applicant_id=applicant_id,
        org_id=_org(request),
        top_n=top_n,
    )
    return JSONResponse(status_code=200, content={"duplicates": duplicates})


# =============================================================================
# E04-S03: ELIGIBILITY EVALUATION WIZARD
# =============================================================================

@router.post("/eligibility/evaluate")
@require_permission(Permission.AI_INVOKE)
async def evaluate_eligibility(request: Request, body: dict) -> JSONResponse:
    """
    Run AI eligibility evaluation for an applicant.

    Body:
        applicant_id: str
        marksheet_text: str   — OCR text extracted from uploaded marksheet
        admission_criteria: str (optional)
    """
    applicant_id = body.get("applicant_id")
    marksheet_text = body.get("marksheet_text", "")
    admission_criteria = body.get(
        "admission_criteria",
        "Minimum 50% aggregate in qualifying examination"
    )

    if not applicant_id:
        return JSONResponse(
            status_code=422,
            content={"detail": "applicant_id is required"},
        )

    result = EligibilityService.evaluate(
        applicant_id=applicant_id,
        org_id=_org(request),
        marksheet_text=marksheet_text,
        admission_criteria=admission_criteria,
        actor_id=_actor(request),
        actor_role=_role(request),
    )
    return JSONResponse(status_code=200, content=result)


# =============================================================================
# E04-S04: DOCUMENT VERIFICATION WIZARD
# =============================================================================

@router.post("/documents/upload")
@require_permission(Permission.STUDENT_CREATE)
async def upload_document(
    request: Request, body: DocumentUploadRequest
) -> JSONResponse:
    """Upload an application document (triggers AI verification)."""
    doc = DocumentVerificationService.upload_document(
        request=body,
        org_id=_org(request),
        uploaded_by=_actor(request),
    )
    return JSONResponse(status_code=201, content=doc.model_dump(mode="json"))


@router.post("/documents/{doc_id}/override")
@require_permission(Permission.OVERRIDE_APPROVE)
async def override_document_verification(
    request: Request, doc_id: str, body: dict
) -> JSONResponse:
    """Admin override for document verification status."""
    doc = DocumentVerificationService.admin_override(
        doc_id=doc_id,
        org_id=_org(request),
        actor_id=_actor(request),
        actor_role=_role(request),
        is_verified=body.get("is_verified", False),
        justification=body.get("justification", ""),
    )
    return JSONResponse(status_code=200, content=doc.model_dump(mode="json"))


@router.get("/documents/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def list_documents(request: Request, applicant_id: str) -> JSONResponse:
    docs = DocumentVerificationService.list_documents(
        applicant_id=applicant_id, org_id=_org(request)
    )
    return JSONResponse(
        status_code=200,
        content={"documents": [d.model_dump(mode="json") for d in docs]},
    )


# =============================================================================
# P5: DOCUMENT REVIEW WORKFLOW (Stage 3 — additional endpoints)
# =============================================================================

@router.post("/documents/{doc_id}/review/start")
@require_permission(Permission.STUDENT_CREATE)
async def submit_document_for_review(request: Request, doc_id: str) -> JSONResponse:
    """Transition doc_status PENDING → UNDER_REVIEW."""
    doc = DocumentVerificationService.submit_for_review(
        doc_id=doc_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=doc.model_dump(mode="json"))


@router.post("/documents/{doc_id}/review/approve")
@require_permission(Permission.STUDENT_CREATE)
async def approve_document(request: Request, doc_id: str) -> JSONResponse:
    """Approve a document (UNDER_REVIEW → APPROVED, is_verified=True)."""
    doc = DocumentVerificationService.approve_document(
        doc_id=doc_id,
        org_id=_org(request),
        actor_id=_actor(request),
        actor_role=_role(request),
    )
    return JSONResponse(status_code=200, content=doc.model_dump(mode="json"))


@router.post("/documents/{doc_id}/review/reject")
@require_permission(Permission.STUDENT_CREATE)
async def reject_document(request: Request, doc_id: str, body: dict) -> JSONResponse:
    """Reject a document with a reason. allow_reupload=True → REUPLOAD_REQUESTED."""
    doc = DocumentVerificationService.reject_document(
        doc_id=doc_id,
        org_id=_org(request),
        actor_id=_actor(request),
        rejection_reason=body.get("rejection_reason", ""),
        allow_reupload=body.get("allow_reupload", True),
        reupload_deadline=body.get("reupload_deadline"),
    )
    return JSONResponse(status_code=200, content=doc.model_dump(mode="json"))


@router.post("/documents/{doc_id}/reupload")
@require_permission(Permission.STUDENT_CREATE)
async def reupload_document(request: Request, doc_id: str, body: dict) -> JSONResponse:
    """Re-upload a rejected document (resets to PENDING, increments reupload_count)."""
    import base64
    file_content_b64 = body.get("file_content_base64", "")
    file_name = body.get("file_name", "document")
    try:
        file_bytes = base64.b64decode(file_content_b64)
    except Exception:
        return JSONResponse(status_code=422, content={"detail": "Invalid base64 file content"})

    doc = DocumentVerificationService.reupload_document(
        doc_id=doc_id,
        file_bytes=file_bytes,
        file_name=file_name,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=doc.model_dump(mode="json"))


# =============================================================================
# P0-S10: COUNSELLOR MANAGEMENT (CRUD + embedding ETL trigger)
# =============================================================================

from pydantic import BaseModel, EmailStr, Field

class CounsellorCreateRequest(BaseModel):
    name: str
    email: str
    specializations: list[str] = []
    programs: list[str] = []
    bio: str = ""
    phone: Optional[str] = None

class CounsellorUpdateRequest(BaseModel):
    specializations: Optional[list[str]] = None
    programs: Optional[list[str]] = None
    bio: Optional[str] = None


@router.post("/counsellors", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def create_counsellor(request: Request, body: CounsellorCreateRequest) -> JSONResponse:
    """Register a counsellor account and index their profile into PGVector."""
    result = CounsellorService.create(
        org_id=_org(request),
        name=body.name,
        email=body.email,
        specializations=body.specializations,
        programs=body.programs,
        bio=body.bio,
        phone=body.phone,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/counsellors")
@require_permission(Permission.STUDENT_READ)
async def list_counsellors(request: Request) -> JSONResponse:
    """List all active counsellors for this organisation."""
    rows = CounsellorService.list_counsellors(org_id=_org(request))
    return JSONResponse(content={"counsellors": rows, "total": len(rows)})


@router.get("/counsellors/{counsellor_id}")
@require_permission(Permission.STUDENT_READ)
async def get_counsellor(request: Request, counsellor_id: str) -> JSONResponse:
    """Get a counsellor profile."""
    row = CounsellorService.get(org_id=_org(request), counsellor_id=counsellor_id)
    return JSONResponse(content=row)


@router.patch("/counsellors/{counsellor_id}")
@require_permission(Permission.STUDENT_CREATE)
async def update_counsellor(
    request: Request, counsellor_id: str, body: CounsellorUpdateRequest
) -> JSONResponse:
    """Update counsellor profile fields and re-index their embedding."""
    result = CounsellorService.update_profile(
        org_id=_org(request),
        counsellor_id=counsellor_id,
        specializations=body.specializations,
        programs=body.programs,
        bio=body.bio,
        actor_id=_actor(request),
    )
    return JSONResponse(content=result)


# =============================================================================
# E04-S05: COUNSELLOR ALLOCATION WIZARD
# =============================================================================

@router.post("/counsellors/assign")
@require_permission(Permission.STUDENT_CREATE)
async def assign_counsellor(
    request: Request, body: CounsellorAssignRequest
) -> JSONResponse:
    """Assign a counsellor to an applicant."""
    assignment = CounsellorAllocationService.assign(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
        actor_role=_role(request),
    )
    return JSONResponse(status_code=201, content=assignment.model_dump(mode="json"))


# =============================================================================
# P9: OFFER LETTER v2 (Stage 7)
# =============================================================================

@router.post("/offers/generate")
@require_permission(Permission.STUDENT_CREATE)
async def generate_offer_letter(
    request: Request, body: OfferLetterGenerateRequest
) -> JSONResponse:
    """Generate a PDF offer letter (with acceptance deadline + fee structure)."""
    letter = OfferLetterService.generate(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=letter.model_dump(mode="json"))


@router.get("/offers/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_offer_for_applicant(request: Request, applicant_id: str) -> JSONResponse:
    """Get the current valid offer letter for an applicant."""
    letter = OfferLetterService.get_for_applicant(applicant_id, _org(request))
    if not letter:
        return JSONResponse(
            content={"detail": f"No active offer for applicant '{applicant_id}'."},
            status_code=404,
        )
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.get("/offers/{letter_id}")
@require_permission(Permission.STUDENT_READ)
async def get_offer_letter(request: Request, letter_id: str) -> JSONResponse:
    """Get an offer letter by ID."""
    letter = OfferLetterService.get(letter_id, _org(request))
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.post("/offers/{letter_id}/accept")
@require_permission(Permission.STUDENT_CREATE)
async def accept_offer(
    request: Request, letter_id: str, body: OfferAcceptRequest
) -> JSONResponse:
    """Applicant accepts their offer. Transitions → OFFER_ACCEPTED → SEAT_CONFIRMED."""
    letter = OfferLetterService.accept(
        letter_id=letter_id,
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.post("/offers/{letter_id}/decline")
@require_permission(Permission.STUDENT_CREATE)
async def decline_offer(
    request: Request, letter_id: str, body: OfferDeclineRequest
) -> JSONResponse:
    """Applicant declines their offer. Triggers waitlist cascade."""
    letter = OfferLetterService.decline(
        letter_id=letter_id,
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.post("/offers/{letter_id}/revoke")
@require_permission(Permission.OVERRIDE_APPROVE)
async def revoke_offer(
    request: Request, letter_id: str, body: OfferRevokeRequest
) -> JSONResponse:
    """Staff revokes a previously issued offer (requires OVERRIDE_APPROVE)."""
    letter = OfferLetterService.revoke(
        letter_id=letter_id,
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.post("/offers/{letter_id}/delivery")
@require_permission(Permission.STUDENT_CREATE)
async def update_offer_delivery(
    request: Request, letter_id: str, body: dict
) -> JSONResponse:
    """Update delivery status (SENT / OPENED / BOUNCED)."""
    status = body.get("status", "")
    letter = OfferLetterService.mark_delivery(
        letter_id=letter_id,
        org_id=_org(request),
        status=status,
        actor_id=_actor(request),
    )
    return JSONResponse(content=letter.model_dump(mode="json"))


@router.post("/offers/{letter_id}/reminder")
@require_permission(Permission.STUDENT_CREATE)
async def mark_offer_reminder(
    request: Request, letter_id: str, body: dict
) -> JSONResponse:
    """Mark a T-3 or T-1 day reminder as sent."""
    reminder_type = body.get("reminder_type", "")
    OfferLetterService.mark_reminder(
        letter_id=letter_id,
        org_id=_org(request),
        reminder_type=reminder_type,
        actor_id=_actor(request),
    )
    return JSONResponse(content={"letter_id": letter_id, "reminder_type": reminder_type})


@router.post("/offers/expire-overdue")
@require_permission(Permission.OVERRIDE_APPROVE)
async def expire_overdue_offers(request: Request) -> JSONResponse:
    """Batch-expire all PENDING offers past their acceptance deadline."""
    result = OfferLetterService.expire_overdue(
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(content=result)


# =============================================================================
# E04-S07: ADMISSION CONFIRMATION WIZARD
# =============================================================================

@router.post("/confirm")
@require_permission(Permission.STUDENT_CREATE)
async def confirm_admission(
    request: Request, body: AdmissionConfirmRequest
) -> JSONResponse:
    """Confirm an admission after fee payment (→ ADMITTED)."""
    record = AdmissionConfirmationService.confirm(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=record.model_dump(mode="json"))


# =============================================================================
# E04-S08: INTAKE QUALITY SCORING WIZARD
# =============================================================================

@router.post("/intake/score")
@require_permission(Permission.STUDENT_READ)
async def score_intake(request: Request, body: IntakeScoreRequest) -> JSONResponse:
    """Score an admissions intake batch on quality metrics."""
    score = IntakeQualityService.score_batch(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=score.model_dump(mode="json"))


# =============================================================================
# E04-S09: ENROLLMENT HANDOVER WIZARD
# =============================================================================

@router.post("/enroll")
@require_permission(Permission.STUDENT_CREATE)
async def enroll_student(
    request: Request, body: EnrollmentHandoverRequest
) -> JSONResponse:
    """Execute enrollment handover (ADMITTED → ENROLLED + Student record)."""
    student = EnrollmentHandoverService.enroll(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=student.model_dump(mode="json"))


# =============================================================================
# P4: APPLICATION FORM WIZARD (Stage 2)
# =============================================================================

@router.post("/applications/{applicant_id}/start")
@require_permission(Permission.STUDENT_CREATE)
async def start_application_draft(request: Request, applicant_id: str) -> JSONResponse:
    """Start the application form wizard (assigns Application ID, status → DRAFT)."""
    draft = ApplicationFormService.start_draft(
        applicant_id=applicant_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.get("/applications/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_application_draft(request: Request, applicant_id: str) -> JSONResponse:
    """Get full application form data for an applicant."""
    draft = ApplicationFormService.get_draft(applicant_id, _org(request))
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.patch("/applications/{applicant_id}/personal")
@require_permission(Permission.STUDENT_CREATE)
async def save_personal_details(
    request: Request, applicant_id: str, body: PersonalDetailsRequest
) -> JSONResponse:
    """Step 1: Save personal details (DOB, gender, category, Aadhaar)."""
    draft = ApplicationFormService.save_personal_details(
        applicant_id=applicant_id,
        org_id=_org(request),
        request=body,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.patch("/applications/{applicant_id}/address")
@require_permission(Permission.STUDENT_CREATE)
async def save_address(
    request: Request, applicant_id: str, body: AddressRequest
) -> JSONResponse:
    """Step 2: Save address information."""
    draft = ApplicationFormService.save_address(
        applicant_id=applicant_id,
        org_id=_org(request),
        request=body,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.post("/applications/{applicant_id}/qualifications")
@require_permission(Permission.STUDENT_CREATE)
async def add_academic_qualification(
    request: Request, applicant_id: str, body: AcademicQualificationRequest
) -> JSONResponse:
    """Step 3: Add or update an academic qualification record."""
    body.applicant_id = applicant_id
    qual = ApplicationFormService.add_academic_qualification(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=qual.model_dump(mode="json"))


@router.get("/applications/{applicant_id}/qualifications")
@require_permission(Permission.STUDENT_READ)
async def list_academic_qualifications(
    request: Request, applicant_id: str
) -> JSONResponse:
    """Get all academic qualifications for an applicant."""
    quals = ApplicationFormService.list_academic_qualifications(applicant_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"qualifications": [q.model_dump(mode="json") for q in quals]},
    )


@router.post("/applications/{applicant_id}/entrance-scores")
@require_permission(Permission.STUDENT_CREATE)
async def add_entrance_score(
    request: Request, applicant_id: str, body: EntranceScoreRequest
) -> JSONResponse:
    """Step 4: Add an entrance exam score (JEE/NEET/CAT/etc.)."""
    body.applicant_id = applicant_id
    score = ApplicationFormService.add_entrance_score(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=score.model_dump(mode="json"))


@router.get("/applications/{applicant_id}/entrance-scores")
@require_permission(Permission.STUDENT_READ)
async def list_entrance_scores(
    request: Request, applicant_id: str
) -> JSONResponse:
    scores = ApplicationFormService.list_entrance_scores(applicant_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"scores": [s.model_dump(mode="json") for s in scores]},
    )


@router.delete("/applications/{applicant_id}/entrance-scores/{score_id}", status_code=204)
@require_permission(Permission.STUDENT_CREATE)
async def delete_entrance_score(
    request: Request, applicant_id: str, score_id: str
) -> None:
    ApplicationFormService.delete_entrance_score(
        score_id=score_id,
        applicant_id=applicant_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )


@router.put("/applications/{applicant_id}/preferences")
@require_permission(Permission.STUDENT_CREATE)
async def set_program_preferences(
    request: Request, applicant_id: str, body: ProgramPreferencesRequest
) -> JSONResponse:
    """Step 5: Set ordered program preferences (replaces existing)."""
    body.applicant_id = applicant_id
    prefs = ApplicationFormService.set_program_preferences(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content={"preferences": prefs})


@router.get("/applications/{applicant_id}/preferences")
@require_permission(Permission.STUDENT_READ)
async def get_program_preferences(
    request: Request, applicant_id: str
) -> JSONResponse:
    prefs = ApplicationFormService.get_program_preferences(applicant_id, _org(request))
    return JSONResponse(status_code=200, content={"preferences": prefs})


@router.post("/applications/{applicant_id}/declaration")
@require_permission(Permission.STUDENT_CREATE)
async def accept_declaration(
    request: Request, applicant_id: str, body: DeclarationRequest
) -> JSONResponse:
    """Step 7: Accept declaration and provide digital signature."""
    body.applicant_id = applicant_id
    draft = ApplicationFormService.accept_declaration(
        applicant_id=applicant_id,
        org_id=_org(request),
        request=body,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.post("/applications/{applicant_id}/submit")
@require_permission(Permission.STUDENT_CREATE)
async def submit_application(request: Request, applicant_id: str) -> JSONResponse:
    """Submit the application (DRAFT → SUBMITTED). Validates completeness."""
    draft = ApplicationFormService.submit_application(
        applicant_id=applicant_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


@router.post("/applications/fee")
@require_permission(Permission.STUDENT_CREATE)
async def record_application_fee(
    request: Request, body: ApplicationFeeRequest
) -> JSONResponse:
    """Step 8: Record application fee payment (SUBMITTED → DOCUMENTS_PENDING)."""
    draft = ApplicationFormService.record_application_fee(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(mode="json"))


# =============================================================================
# P8: SEAT MATRIX + MERIT LIST ENGINE (Stage 6)
# =============================================================================

@router.post("/seats")
@require_permission(Permission.OVERRIDE_APPROVE)
async def create_seat_matrix(request: Request, body: SeatMatrixCreate) -> JSONResponse:
    """Define seat counts for a program/batch/category combination."""
    seat = SeatMatrixService.create(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=seat.model_dump(mode="json"))


@router.get("/seats")
@require_permission(Permission.STUDENT_READ)
async def list_seat_matrix(
    request: Request,
    program_name: Optional[str] = Query(default=None),
    intake_batch: Optional[str] = Query(default=None),
) -> JSONResponse:
    seats = SeatMatrixService.list(
        org_id=_org(request), program_name=program_name, intake_batch=intake_batch
    )
    return JSONResponse(status_code=200, content={"seats": [s.model_dump(mode="json") for s in seats]})


@router.post("/merit-policies")
@require_permission(Permission.OVERRIDE_APPROVE)
async def create_merit_policy(request: Request, body: MeritListPolicyCreate) -> JSONResponse:
    """Create or update the merit scoring formula for a program/batch."""
    policy = MeritListPolicyService.create(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=policy.model_dump(mode="json"))


@router.get("/merit-policies/{program_name}/{intake_batch}")
@require_permission(Permission.STUDENT_READ)
async def get_merit_policy(request: Request, program_name: str, intake_batch: str) -> JSONResponse:
    policy = MeritListPolicyService.get(_org(request), program_name, intake_batch)
    return JSONResponse(status_code=200, content=policy.model_dump(mode="json"))


@router.post("/merit-lists/generate")
@require_permission(Permission.OVERRIDE_APPROVE)
async def generate_merit_list(request: Request, body: MeritListGenerateRequest) -> JSONResponse:
    """Generate a ranked merit list for a program/batch/category."""
    result = MeritListService.generate(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/merit-lists/{merit_list_id}")
@require_permission(Permission.STUDENT_READ)
async def get_merit_list(request: Request, merit_list_id: str) -> JSONResponse:
    ml = MeritListService.get(merit_list_id, _org(request))
    return JSONResponse(status_code=200, content=ml.model_dump(mode="json"))


@router.get("/merit-lists/{merit_list_id}/entries")
@require_permission(Permission.STUDENT_READ)
async def list_merit_entries(request: Request, merit_list_id: str) -> JSONResponse:
    entries = MeritListService.list_entries(merit_list_id, _org(request))
    return JSONResponse(status_code=200, content={"entries": [e.model_dump(mode="json") for e in entries]})


@router.get("/merit-lists/{merit_list_id}/waitlist")
@require_permission(Permission.STUDENT_READ)
async def list_waitlist(request: Request, merit_list_id: str) -> JSONResponse:
    waitlist = MeritListService.list_waitlist(merit_list_id, _org(request))
    return JSONResponse(status_code=200, content={"waitlist": [w.model_dump(mode="json") for w in waitlist]})


@router.patch("/merit-lists/{merit_list_id}/status")
@require_permission(Permission.OVERRIDE_APPROVE)
async def update_merit_list_status(request: Request, merit_list_id: str, body: dict) -> JSONResponse:
    """Advance merit list: DRAFT → UNDER_REVIEW → APPROVED → PUBLISHED."""
    ml = MeritListService.update_status(
        merit_list_id=merit_list_id, org_id=_org(request),
        new_status=body.get("status", ""), actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=ml.model_dump(mode="json"))


@router.post("/merit-lists/{merit_list_id}/waitlist/{applicant_id}/activate")
@require_permission(Permission.OVERRIDE_APPROVE)
async def activate_waitlist_entry(
    request: Request, merit_list_id: str, applicant_id: str
) -> JSONResponse:
    """Activate a waitlist candidate (seat freed by decline/no-show)."""
    entry = MeritListService.activate_waitlist_entry(
        merit_list_id=merit_list_id,
        applicant_id=applicant_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=entry.model_dump(mode="json"))


# =============================================================================
# P7: ENTRANCE TESTS (Stage 5A)
# =============================================================================

@router.post("/tests")
@require_permission(Permission.STUDENT_CREATE)
async def create_admissions_test(
    request: Request, body: AdmissionsTestCreate
) -> JSONResponse:
    test = AdmissionsTestService.create(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=test.model_dump(mode="json"))


@router.get("/tests")
@require_permission(Permission.STUDENT_READ)
async def list_admissions_tests(
    request: Request,
    intake_batch: Optional[str] = Query(default=None),
    program_name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> JSONResponse:
    tests = AdmissionsTestService.list(
        org_id=_org(request), intake_batch=intake_batch,
        program_name=program_name, status=status,
    )
    return JSONResponse(status_code=200, content={"tests": [t.model_dump(mode="json") for t in tests]})


@router.get("/tests/{test_id}")
@require_permission(Permission.STUDENT_READ)
async def get_admissions_test(request: Request, test_id: str) -> JSONResponse:
    return JSONResponse(status_code=200, content=AdmissionsTestService.get(test_id, _org(request)).model_dump(mode="json"))


@router.patch("/tests/{test_id}/status")
@require_permission(Permission.OVERRIDE_APPROVE)
async def update_test_status(request: Request, test_id: str, body: dict) -> JSONResponse:
    test = AdmissionsTestService.update_status(
        test_id=test_id, org_id=_org(request),
        new_status=body.get("status", ""), actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=test.model_dump(mode="json"))


@router.post("/tests/{test_id}/slots")
@require_permission(Permission.STUDENT_CREATE)
async def add_test_slot(request: Request, test_id: str, body: TestSlotCreate) -> JSONResponse:
    body.test_id = test_id
    slot = TestSlotService.add_slot(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=slot.model_dump(mode="json"))


@router.get("/tests/{test_id}/slots")
@require_permission(Permission.STUDENT_READ)
async def list_test_slots(request: Request, test_id: str) -> JSONResponse:
    slots = TestSlotService.list_for_test(test_id, _org(request))
    return JSONResponse(status_code=200, content={"slots": [s.model_dump(mode="json") for s in slots]})


@router.post("/tests/registrations")
@require_permission(Permission.STUDENT_CREATE)
async def register_for_test(request: Request, body: TestRegistrationCreate) -> JSONResponse:
    reg = TestRegistrationService.register(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=reg.model_dump(mode="json"))


@router.get("/tests/{test_id}/registrations")
@require_permission(Permission.STUDENT_READ)
async def list_test_registrations(request: Request, test_id: str) -> JSONResponse:
    regs = TestRegistrationService.list_for_test(test_id, _org(request))
    return JSONResponse(status_code=200, content={"registrations": [r.model_dump(mode="json") for r in regs]})


@router.post("/tests/registrations/{reg_id}/admit-card")
@require_permission(Permission.STUDENT_CREATE)
async def generate_admit_card(request: Request, reg_id: str) -> JSONResponse:
    reg = TestRegistrationService.generate_admit_card(reg_id, _org(request), _actor(request))
    return JSONResponse(status_code=200, content=reg.model_dump(mode="json"))


@router.patch("/tests/registrations/{reg_id}/attendance")
@require_permission(Permission.STUDENT_CREATE)
async def record_test_attendance(request: Request, reg_id: str, body: dict) -> JSONResponse:
    reg = TestRegistrationService.record_attendance(
        reg_id, _org(request), body.get("attendance_status", ""), _actor(request)
    )
    return JSONResponse(status_code=200, content=reg.model_dump(mode="json"))


@router.post("/tests/scores")
@require_permission(Permission.STUDENT_CREATE)
async def enter_test_score(request: Request, body: TestScoreCreate) -> JSONResponse:
    score = TestScoreService.enter_score(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=score.model_dump(mode="json"))


@router.get("/tests/{test_id}/scores")
@require_permission(Permission.STUDENT_READ)
async def list_test_scores(request: Request, test_id: str) -> JSONResponse:
    scores = TestScoreService.list_for_test(test_id, _org(request))
    return JSONResponse(status_code=200, content={"scores": [s.model_dump(mode="json") for s in scores]})


# =============================================================================
# P7: INTERVIEW MANAGEMENT (Stage 5B)
# =============================================================================

@router.post("/interviews/panels")
@require_permission(Permission.OVERRIDE_APPROVE)
async def create_interview_panel(request: Request, body: InterviewPanelCreate) -> JSONResponse:
    panel = InterviewPanelService.create(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=panel.model_dump(mode="json"))


@router.get("/interviews/panels")
@require_permission(Permission.STUDENT_READ)
async def list_interview_panels(
    request: Request,
    intake_batch: Optional[str] = Query(default=None),
    program_name: Optional[str] = Query(default=None),
) -> JSONResponse:
    panels = InterviewPanelService.list(
        org_id=_org(request), intake_batch=intake_batch, program_name=program_name
    )
    return JSONResponse(status_code=200, content={"panels": [p.model_dump(mode="json") for p in panels]})


@router.post("/interviews/schedules")
@require_permission(Permission.STUDENT_CREATE)
async def schedule_interview(request: Request, body: InterviewScheduleCreate) -> JSONResponse:
    schedule = InterviewScheduleService.schedule(request=body, org_id=_org(request), actor_id=_actor(request))
    return JSONResponse(status_code=201, content=schedule.model_dump(mode="json"))


@router.get("/interviews/schedules/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def list_interviews_for_applicant(request: Request, applicant_id: str) -> JSONResponse:
    schedules = InterviewScheduleService.list_for_applicant(applicant_id, _org(request))
    return JSONResponse(status_code=200, content={"schedules": [s.model_dump(mode="json") for s in schedules]})


@router.get("/interviews/schedules/panel/{panel_id}")
@require_permission(Permission.STUDENT_READ)
async def list_interviews_for_panel(request: Request, panel_id: str) -> JSONResponse:
    schedules = InterviewScheduleService.list_for_panel(panel_id, _org(request))
    return JSONResponse(status_code=200, content={"schedules": [s.model_dump(mode="json") for s in schedules]})


@router.patch("/interviews/schedules/{schedule_id}/attendance")
@require_permission(Permission.STUDENT_CREATE)
async def update_interview_attendance(request: Request, schedule_id: str, body: dict) -> JSONResponse:
    schedule = InterviewScheduleService.update_attendance(
        schedule_id, _org(request), body.get("attendance_status", ""), _actor(request)
    )
    return JSONResponse(status_code=200, content=schedule.model_dump(mode="json"))


@router.post("/interviews/scorecards")
@require_permission(Permission.STUDENT_CREATE)
async def submit_scorecard(request: Request, body: InterviewScorecardCreate) -> JSONResponse:
    """Submit an evaluator's interview scorecard."""
    scorecard = InterviewScorecardService.submit(
        request=body, org_id=_org(request), evaluator_id=_actor(request)
    )
    return JSONResponse(status_code=201, content=scorecard.model_dump(mode="json"))


@router.get("/interviews/schedules/{schedule_id}/scorecards")
@require_permission(Permission.STUDENT_READ)
async def list_scorecards(request: Request, schedule_id: str) -> JSONResponse:
    scorecards = InterviewScorecardService.list_for_schedule(schedule_id, _org(request))
    return JSONResponse(status_code=200, content={"scorecards": [s.model_dump(mode="json") for s in scorecards]})


@router.get("/interviews/schedules/{schedule_id}/aggregate")
@require_permission(Permission.STUDENT_READ)
async def get_interview_aggregate(request: Request, schedule_id: str) -> JSONResponse:
    agg = InterviewScorecardService.get_aggregate_score(schedule_id, _org(request))
    return JSONResponse(status_code=200, content=agg)


# =============================================================================
# P3: LEAD CRM (Stage 1)
# =============================================================================

@router.post("/leads")
@require_permission(Permission.STUDENT_CREATE)
async def create_lead(request: Request, body: LeadCreate) -> JSONResponse:
    """Capture a new lead from any source channel."""
    lead = LeadService.create(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=lead.model_dump(mode="json"))


@router.get("/leads")
@require_permission(Permission.STUDENT_READ)
async def list_leads(
    request: Request,
    status: Optional[str] = Query(default=None),
    counsellor_id: Optional[str] = Query(default=None),
    source_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
) -> JSONResponse:
    leads = LeadService.list(
        org_id=_org(request),
        status=status,
        counsellor_id=counsellor_id,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        status_code=200,
        content={"leads": [l.model_dump(mode="json") for l in leads], "total": len(leads)},
    )


@router.get("/leads/{lead_id}")
@require_permission(Permission.STUDENT_READ)
async def get_lead(request: Request, lead_id: str) -> JSONResponse:
    lead = LeadService.get(lead_id, _org(request))
    return JSONResponse(status_code=200, content=lead.model_dump(mode="json"))


@router.patch("/leads/{lead_id}")
@require_permission(Permission.STUDENT_CREATE)
async def update_lead(
    request: Request, lead_id: str, body: LeadUpdateRequest
) -> JSONResponse:
    """Update lead CRM fields (status, counsellor, follow-up, notes)."""
    lead = LeadService.update(
        lead_id=lead_id,
        org_id=_org(request),
        request=body,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=lead.model_dump(mode="json"))


@router.post("/leads/{lead_id}/activities")
@require_permission(Permission.STUDENT_CREATE)
async def log_lead_activity(
    request: Request, lead_id: str, body: LeadActivityCreate
) -> JSONResponse:
    """Log a CRM activity (call, email, note, meeting) against a lead."""
    body.lead_id = lead_id  # enforce from path param
    activity = LeadService.log_activity(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=activity.model_dump(mode="json"))


@router.get("/leads/{lead_id}/activities")
@require_permission(Permission.STUDENT_READ)
async def list_lead_activities(request: Request, lead_id: str) -> JSONResponse:
    activities = LeadService.list_activities(lead_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"activities": [a.model_dump(mode="json") for a in activities]},
    )


@router.post("/leads/convert")
@require_permission(Permission.STUDENT_CREATE)
async def convert_lead(request: Request, body: LeadConvertRequest) -> JSONResponse:
    """Convert a lead into an applicant (READY_TO_APPLY → CONVERTED)."""
    result = LeadService.convert_to_applicant(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=result)


# =============================================================================
# P3: CONSULTANTS
# =============================================================================

@router.post("/consultants")
@require_permission(Permission.OVERRIDE_APPROVE)
async def create_consultant(
    request: Request, body: ConsultantCreate
) -> JSONResponse:
    """Register a third-party education consultant."""
    consultant = ConsultantService.create(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=consultant.model_dump(mode="json"))


@router.get("/consultants-ext")
@require_permission(Permission.STUDENT_READ)
async def list_consultants_ext(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
) -> JSONResponse:
    """List third-party consultants (separate from internal counsellors)."""
    consultants = ConsultantService.list(
        org_id=_org(request), status=status, limit=limit, offset=offset
    )
    return JSONResponse(
        status_code=200,
        content={"consultants": [c.model_dump(mode="json") for c in consultants]},
    )


@router.get("/consultants-ext/{consultant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_consultant_ext(request: Request, consultant_id: str) -> JSONResponse:
    consultant = ConsultantService.get(consultant_id, _org(request))
    return JSONResponse(status_code=200, content=consultant.model_dump(mode="json"))


@router.patch("/consultants-ext/{consultant_id}/status")
@require_permission(Permission.OVERRIDE_APPROVE)
async def update_consultant_status(
    request: Request, consultant_id: str, body: dict
) -> JSONResponse:
    """Update a consultant's status (ACTIVE/SUSPENDED/TERMINATED)."""
    consultant = ConsultantService.update_status(
        consultant_id=consultant_id,
        org_id=_org(request),
        new_status=body.get("status", ""),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=consultant.model_dump(mode="json"))


# =============================================================================
# P3: REFERRAL CODES
# =============================================================================

@router.post("/referral-codes")
@require_permission(Permission.STUDENT_CREATE)
async def create_referral_code(
    request: Request, body: ReferralCodeCreate
) -> JSONResponse:
    """Generate a referral code for a student, staff member, or consultant."""
    code = ReferralCodeService.create(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=code.model_dump(mode="json"))


@router.get("/referral-codes/{code}")
@require_permission(Permission.STUDENT_READ)
async def get_referral_code(request: Request, code: str) -> JSONResponse:
    rc = ReferralCodeService.get_by_code(code, _org(request))
    return JSONResponse(status_code=200, content=rc.model_dump(mode="json"))


@router.delete("/referral-codes/{code}", status_code=204)
@require_permission(Permission.OVERRIDE_APPROVE)
async def deactivate_referral_code(request: Request, code: str) -> None:
    ReferralCodeService.deactivate(code, _org(request), _actor(request))


# =============================================================================
# E04-S10: INSTITUTION POLICY STORE
# =============================================================================

from server.admissions.policy_store import PolicyStore

class PolicyUpsertRequest(BaseModel):
    key: str
    value: object
    description: str = ""
    category: str = "general"


@router.get("/policies")
@require_permission(Permission.STUDENT_READ)
async def list_policies(request: Request, category: Optional[str] = None) -> JSONResponse:
    """List all institution policies for this org."""
    import json
    from datetime import datetime
    rows = PolicyStore.get_all(org_id=_org(request), category=category)
    # Serialize datetime fields to ISO strings
    clean = []
    for r in rows:
        clean.append({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items()})
    return JSONResponse(content={"policies": clean, "total": len(clean)})


@router.put("/policies/{key:path}")
@require_permission(Permission.OVERRIDE_APPROVE)
async def upsert_policy(request: Request, key: str, body: PolicyUpsertRequest) -> JSONResponse:
    """Create or update an institution policy."""
    result = PolicyStore.upsert(
        org_id=_org(request),
        key=key,
        value=body.value,
        description=body.description,
        category=body.category,
        actor_id=_actor(request),
    )
    return JSONResponse(content=result)


@router.delete("/policies/{key:path}", status_code=204)
@require_permission(Permission.OVERRIDE_APPROVE)
async def deactivate_policy(request: Request, key: str) -> None:
    """Soft-delete a policy (sets is_active=FALSE)."""
    PolicyStore.deactivate(org_id=_org(request), key=key, actor_id=_actor(request))


# =============================================================================
# P6: ELIGIBILITY CRITERIA MANAGEMENT (Stage 4)
# =============================================================================

@router.post("/eligibility/criteria")
@require_permission(Permission.OVERRIDE_APPROVE)
async def set_eligibility_criteria(request: Request, body: EligibilityCriteria) -> JSONResponse:
    """Create or replace eligibility criteria for a program (and optional batch)."""
    result = EligibilityCriteriaService.set_criteria(
        criteria=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(content=result.model_dump(), status_code=201)


@router.get("/eligibility/criteria")
@require_permission(Permission.STUDENT_READ)
async def list_eligibility_criteria(request: Request) -> JSONResponse:
    """List all eligibility criteria for this org."""
    results = EligibilityCriteriaService.list_criteria(org_id=_org(request))
    return JSONResponse(content={"criteria": [c.model_dump() for c in results], "total": len(results)})


@router.get("/eligibility/criteria/{program_name}")
@require_permission(Permission.STUDENT_READ)
async def get_eligibility_criteria(
    request: Request,
    program_name: str,
    intake_batch: Optional[str] = None,
) -> JSONResponse:
    """Get eligibility criteria for a specific program (and optional batch)."""
    criteria = EligibilityCriteriaService.get_criteria(
        org_id=_org(request),
        program_name=program_name,
        intake_batch=intake_batch,
    )
    if not criteria:
        return JSONResponse(
            content={"detail": f"No criteria configured for '{program_name}'."},
            status_code=404,
        )
    return JSONResponse(content=criteria.model_dump())


@router.delete("/eligibility/criteria/{program_name}", status_code=204)
@require_permission(Permission.OVERRIDE_APPROVE)
async def delete_eligibility_criteria(
    request: Request,
    program_name: str,
    intake_batch: Optional[str] = None,
) -> None:
    """Deactivate eligibility criteria for a program (soft delete)."""
    EligibilityCriteriaService.delete_criteria(
        org_id=_org(request),
        program_name=program_name,
        actor_id=_actor(request),
        intake_batch=intake_batch,
    )


# =============================================================================
# E04-S12: REVIEW QUEUE
# =============================================================================

from server.admissions.review_queue import ReviewQueue

class ReviewDecisionRequest(BaseModel):
    decision: str   # "APPROVED" | "REJECTED"
    note: Optional[str] = None


@router.get("/review")
@require_permission(Permission.OVERRIDE_APPROVE)
async def list_review_items(request: Request, entity_type: Optional[str] = None) -> JSONResponse:
    """List pending review items requiring staff decision."""
    items = ReviewQueue.list_pending(org_id=_org(request), entity_type=entity_type)
    return JSONResponse(content={"items": items, "total": len(items)})


@router.get("/review/{item_id}")
@require_permission(Permission.OVERRIDE_APPROVE)
async def get_review_item(request: Request, item_id: str) -> JSONResponse:
    """Get a single review item."""
    item = ReviewQueue.get(org_id=_org(request), item_id=item_id)
    return JSONResponse(content=item)


@router.post("/review/{item_id}/decide")
@require_permission(Permission.OVERRIDE_APPROVE)
async def decide_review_item(
    request: Request, item_id: str, body: ReviewDecisionRequest
) -> JSONResponse:
    """
    Record a staff decision (APPROVED/REJECTED) on a flagged review item.
    Automatically re-queues the automation pipeline after an APPROVED decision.
    """
    from server.core.domain_events import DomainEvent, DomainEventBus

    item = ReviewQueue.decide(
        org_id=_org(request),
        item_id=item_id,
        decision=body.decision,
        decided_by=_actor(request),
        note=body.note,
    )
    # Fire event so pipeline resumes (E04-S16 handler picks this up)
    DomainEventBus.publish(DomainEvent(
        event_type="ReviewItemDecided",
        entity_type=item["entity_type"],
        entity_id=item["entity_id"],
        org_id=_org(request),
        payload={"decision": body.decision, "item_id": item_id},
        actor_id=_actor(request),
    ))
    return JSONResponse(content=item)


# =============================================================================
# P10: PAYMENT v2 — Demand Draft & Refunds (Stage 8)
# =============================================================================

class DDRejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class RefundReviewRequest(BaseModel):
    decision: str = Field(..., description="APPROVED | REJECTED")
    notes: Optional[str] = Field(default=None, max_length=2000)


class RefundProcessRequest(BaseModel):
    gateway_refund_id: str = Field(..., min_length=1)


# --- Demand Draft ---

@router.post("/payments/dd")
@require_permission(Permission.STUDENT_CREATE)
async def submit_demand_draft(request: Request, body: DemandDraftCreate) -> JSONResponse:
    """Applicant submits DD details as proof of fee payment."""
    dd = DemandDraftService.submit(body, _org(request), _actor(request))
    return JSONResponse(content=dd.model_dump(mode="json"), status_code=201)


@router.get("/payments/dd/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def list_demand_drafts(
    request: Request,
    applicant_id: str,
    status: Optional[str] = None,
) -> JSONResponse:
    """List all DDs submitted by an applicant."""
    dds = DemandDraftService.list_for_applicant(applicant_id, _org(request), status)
    return JSONResponse(content={"dds": [d.model_dump(mode="json") for d in dds], "total": len(dds)})


@router.get("/payments/dd/{dd_id}")
@require_permission(Permission.STUDENT_READ)
async def get_demand_draft(request: Request, dd_id: str) -> JSONResponse:
    """Get a demand draft by ID."""
    dd = DemandDraftService.get(dd_id, _org(request))
    return JSONResponse(content=dd.model_dump(mode="json"))


@router.post("/payments/dd/{dd_id}/verify")
@require_permission(Permission.OVERRIDE_APPROVE)
async def verify_demand_draft(request: Request, dd_id: str) -> JSONResponse:
    """Staff verifies a DD → transitions applicant to VERIFICATION_PENDING."""
    dd = DemandDraftService.verify(dd_id, _org(request), _actor(request))
    return JSONResponse(content=dd.model_dump(mode="json"))


@router.post("/payments/dd/{dd_id}/reject")
@require_permission(Permission.OVERRIDE_APPROVE)
async def reject_demand_draft(request: Request, dd_id: str, body: DDRejectRequest) -> JSONResponse:
    """Staff rejects a DD with a reason. Applicant must resubmit."""
    dd = DemandDraftService.reject(dd_id, _org(request), _actor(request), body.reason)
    return JSONResponse(content=dd.model_dump(mode="json"))


# --- Refund Requests ---

@router.post("/payments/refunds")
@require_permission(Permission.STUDENT_CREATE)
async def submit_refund_request(request: Request, body: RefundRequestCreate) -> JSONResponse:
    """Applicant submits a refund request. Amount calculated from policy slabs."""
    ref = RefundRequestService.submit(body, _org(request), _actor(request))
    return JSONResponse(content=ref.model_dump(mode="json"), status_code=201)


@router.get("/payments/refunds/pending")
@require_permission(Permission.OVERRIDE_APPROVE)
async def list_pending_refunds(request: Request) -> JSONResponse:
    """List all REQUESTED / UNDER_REVIEW refund requests for staff."""
    refs = RefundRequestService.list_pending_review(_org(request))
    return JSONResponse(content={"refunds": [r.model_dump(mode="json") for r in refs], "total": len(refs)})


@router.get("/payments/refunds/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def list_refunds_for_applicant(request: Request, applicant_id: str) -> JSONResponse:
    """List refund requests for a specific applicant."""
    refs = RefundRequestService.list_for_applicant(applicant_id, _org(request))
    return JSONResponse(content={"refunds": [r.model_dump(mode="json") for r in refs], "total": len(refs)})


@router.get("/payments/refunds/{request_id}")
@require_permission(Permission.STUDENT_READ)
async def get_refund_request(request: Request, request_id: str) -> JSONResponse:
    """Get a refund request by ID."""
    ref = RefundRequestService.get(request_id, _org(request))
    return JSONResponse(content=ref.model_dump(mode="json"))


@router.post("/payments/refunds/{request_id}/review")
@require_permission(Permission.OVERRIDE_APPROVE)
async def review_refund_request(
    request: Request, request_id: str, body: RefundReviewRequest
) -> JSONResponse:
    """Staff approves or rejects a refund request."""
    ref = RefundRequestService.review(
        request_id=request_id,
        org_id=_org(request),
        actor_id=_actor(request),
        decision=body.decision,
        notes=body.notes,
    )
    return JSONResponse(content=ref.model_dump(mode="json"))


@router.post("/payments/refunds/{request_id}/process")
@require_permission(Permission.OVERRIDE_APPROVE)
async def process_refund(
    request: Request, request_id: str, body: RefundProcessRequest
) -> JSONResponse:
    """Finance records completed refund with gateway reference → PROCESSED."""
    ref = RefundRequestService.process(
        request_id=request_id,
        org_id=_org(request),
        actor_id=_actor(request),
        gateway_refund_id=body.gateway_refund_id,
    )
    return JSONResponse(content=ref.model_dump(mode="json"))


# =============================================================================
# P11: FINAL VERIFICATION (Stage 9)
# =============================================================================

class VerificationStartRequest(BaseModel):
    assigned_officer: Optional[str] = None


class VerificationClearRequest(BaseModel):
    notes: Optional[str] = None


class VerificationUndertakingRequest(BaseModel):
    notes: str = Field(..., min_length=10)


class VerificationRejectRequest(BaseModel):
    reason: str = Field(..., min_length=10)


class DiscrepancyResolveRequest(BaseModel):
    resolution: str = Field(..., min_length=5)


class DiscrepancyEscalateRequest(BaseModel):
    escalate_to: str = Field(..., min_length=1)


# P12 — Enrollment Provisioning inline request models
class EnrollmentCompleteRequest(BaseModel):
    pass  # no body needed — service reads provisioning state


class WelcomeEmailRequest(BaseModel):
    parent: bool = False


@router.post("/verification")
@require_permission(Permission.STUDENT_CREATE)
async def initiate_verification(
    request: Request, body: FinalVerificationCreate
) -> JSONResponse:
    """Initiate a final verification session for a VERIFICATION_PENDING applicant."""
    ver = FinalVerificationService.initiate(body, _org(request), _actor(request))
    return JSONResponse(content=ver.model_dump(mode="json"), status_code=201)


@router.get("/verification/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_verification_for_applicant(request: Request, applicant_id: str) -> JSONResponse:
    """Get the verification record for an applicant."""
    ver = FinalVerificationService.get_for_applicant(applicant_id, _org(request))
    if not ver:
        return JSONResponse(
            content={"detail": f"No verification record for applicant '{applicant_id}'."},
            status_code=404,
        )
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.get("/verification/{verification_id}")
@require_permission(Permission.STUDENT_READ)
async def get_verification(request: Request, verification_id: str) -> JSONResponse:
    ver = FinalVerificationService.get(verification_id, _org(request))
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.post("/verification/{verification_id}/start")
@require_permission(Permission.OVERRIDE_APPROVE)
async def start_verification(
    request: Request, verification_id: str, body: VerificationStartRequest
) -> JSONResponse:
    """Officer starts the verification session → IN_PROGRESS."""
    ver = FinalVerificationService.start(
        verification_id, _org(request), _actor(request), body.assigned_officer
    )
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.post("/verification/{verification_id}/check")
@require_permission(Permission.OVERRIDE_APPROVE)
async def check_document(
    request: Request, verification_id: str, body: VerificationItemCreate
) -> JSONResponse:
    """Record the outcome of checking a single document."""
    item = FinalVerificationService.check_document(
        verification_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=item.model_dump(mode="json"), status_code=201)


@router.get("/verification/{verification_id}/items")
@require_permission(Permission.STUDENT_READ)
async def list_verification_items(request: Request, verification_id: str) -> JSONResponse:
    items = FinalVerificationService.list_items(verification_id, _org(request))
    return JSONResponse(content={"items": [i.model_dump(mode="json") for i in items], "total": len(items)})


@router.post("/verification/{verification_id}/clear")
@require_permission(Permission.OVERRIDE_APPROVE)
async def clear_verification(
    request: Request, verification_id: str, body: VerificationClearRequest
) -> JSONResponse:
    """All docs verified → VERIFIED → applicant READY_FOR_ENROLLMENT."""
    ver = FinalVerificationService.clear(
        verification_id, _org(request), _actor(request), body.notes
    )
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.post("/verification/{verification_id}/clear-with-undertaking")
@require_permission(Permission.OVERRIDE_APPROVE)
async def clear_with_undertaking(
    request: Request, verification_id: str, body: VerificationUndertakingRequest
) -> JSONResponse:
    """Minor issues cleared on undertaking → CLEARED_WITH_UNDERTAKING → READY_FOR_ENROLLMENT."""
    ver = FinalVerificationService.clear_with_undertaking(
        verification_id, _org(request), _actor(request), body.notes
    )
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.post("/verification/{verification_id}/reject")
@require_permission(Permission.OVERRIDE_APPROVE)
async def reject_verification(
    request: Request, verification_id: str, body: VerificationRejectRequest
) -> JSONResponse:
    """Critical discrepancy → REJECTED → applicant CANCELLED."""
    ver = FinalVerificationService.reject(
        verification_id, _org(request), _actor(request), body.reason
    )
    return JSONResponse(content=ver.model_dump(mode="json"))


@router.post("/verification/{verification_id}/discrepancies")
@require_permission(Permission.OVERRIDE_APPROVE)
async def raise_discrepancy(
    request: Request, verification_id: str, body: DiscrepancyCreate
) -> JSONResponse:
    """Raise a document discrepancy against a verification session."""
    disc = DiscrepancyService.raise_discrepancy(
        verification_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=disc.model_dump(mode="json"), status_code=201)


@router.get("/verification/{verification_id}/discrepancies")
@require_permission(Permission.STUDENT_READ)
async def list_discrepancies(
    request: Request, verification_id: str, status: Optional[str] = None
) -> JSONResponse:
    discs = DiscrepancyService.list_discrepancies(verification_id, _org(request), status)
    return JSONResponse(content={"discrepancies": [d.model_dump(mode="json") for d in discs], "total": len(discs)})


@router.post("/verification/discrepancies/{discrepancy_id}/resolve")
@require_permission(Permission.OVERRIDE_APPROVE)
async def resolve_discrepancy(
    request: Request, discrepancy_id: str, body: DiscrepancyResolveRequest
) -> JSONResponse:
    disc = DiscrepancyService.resolve_discrepancy(
        discrepancy_id, _org(request), _actor(request), body.resolution
    )
    return JSONResponse(content=disc.model_dump(mode="json"))


@router.post("/verification/discrepancies/{discrepancy_id}/escalate")
@require_permission(Permission.OVERRIDE_APPROVE)
async def escalate_discrepancy(
    request: Request, discrepancy_id: str, body: DiscrepancyEscalateRequest
) -> JSONResponse:
    disc = DiscrepancyService.escalate_discrepancy(
        discrepancy_id, _org(request), _actor(request), body.escalate_to
    )
    return JSONResponse(content=disc.model_dump(mode="json"))


# =============================================================================
# P12 — Enrollment Provisioning (Stage 10)
# =============================================================================

@router.post("/enrollment")
@require_permission(Permission.STUDENT_CREATE)
async def initiate_enrollment(
    request: Request, body: EnrollmentInitiateRequest
) -> JSONResponse:
    """Initiate enrollment provisioning — assign roll number, create record."""
    prov = EnrollmentProvisioningService.initiate(body, _org(request), _actor(request))
    return JSONResponse(content=prov.model_dump(mode="json"), status_code=201)


@router.get("/enrollment/applicant/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_enrollment_for_applicant(
    request: Request, applicant_id: str
) -> JSONResponse:
    prov = EnrollmentProvisioningService.get_for_applicant(applicant_id, _org(request))
    if not prov:
        return JSONResponse(content={"detail": "No provisioning record found."}, status_code=404)
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.get("/enrollment/{provisioning_id}")
@require_permission(Permission.STUDENT_READ)
async def get_enrollment(
    request: Request, provisioning_id: str
) -> JSONResponse:
    prov = EnrollmentProvisioningService.get(provisioning_id, _org(request))
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/lms")
@require_permission(Permission.STUDENT_CREATE)
async def provision_lms(
    request: Request, provisioning_id: str, body: LMSProvisionRequest
) -> JSONResponse:
    """Record LMS account creation."""
    prov = EnrollmentProvisioningService.provision_lms(
        provisioning_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/email")
@require_permission(Permission.STUDENT_CREATE)
async def provision_email(
    request: Request, provisioning_id: str, body: EmailProvisionRequest
) -> JSONResponse:
    """Assign university email address."""
    prov = EnrollmentProvisioningService.provision_email(
        provisioning_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/library")
@require_permission(Permission.STUDENT_CREATE)
async def provision_library(
    request: Request, provisioning_id: str, body: LibraryProvisionRequest
) -> JSONResponse:
    """Register student with library system."""
    prov = EnrollmentProvisioningService.provision_library(
        provisioning_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/id-card")
@require_permission(Permission.STUDENT_CREATE)
async def dispatch_id_card(
    request: Request, provisioning_id: str
) -> JSONResponse:
    """Mark ID card as dispatched."""
    prov = EnrollmentProvisioningService.dispatch_id_card(
        provisioning_id, _org(request), _actor(request)
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/erp")
@require_permission(Permission.STUDENT_CREATE)
async def sync_erp(
    request: Request, provisioning_id: str, body: ERPSyncRequest
) -> JSONResponse:
    """Sync student record to ERP system."""
    prov = EnrollmentProvisioningService.sync_erp(
        provisioning_id, body, _org(request), _actor(request)
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/welcome-email")
@require_permission(Permission.STUDENT_CREATE)
async def mark_welcome_email(
    request: Request, provisioning_id: str, body: WelcomeEmailRequest
) -> JSONResponse:
    """Mark welcome email (student or parent) as sent."""
    prov = EnrollmentProvisioningService.mark_welcome_email_sent(
        provisioning_id, _org(request), _actor(request), parent=body.parent
    )
    return JSONResponse(content=prov.model_dump(mode="json"))


@router.post("/enrollment/{provisioning_id}/complete")
@require_permission(Permission.STUDENT_CREATE)
async def complete_enrollment(
    request: Request, provisioning_id: str
) -> JSONResponse:
    """Complete enrollment — create student record, transition to ENROLLED."""
    student = EnrollmentProvisioningService.complete(
        provisioning_id, _org(request), _actor(request)
    )
    return JSONResponse(content=student.model_dump(mode="json"), status_code=201)


@router.get("/students/{student_id}")
@require_permission(Permission.STUDENT_READ)
async def get_student(
    request: Request, student_id: str
) -> JSONResponse:
    student = EnrollmentProvisioningService.get_student(student_id, _org(request))
    return JSONResponse(content=student.model_dump(mode="json"))


# =============================================================================
# DASHBOARD AGGREGATES
# =============================================================================

@router.get("/pipeline-summary")
@require_permission(Permission.STUDENT_READ)
async def get_pipeline_summary(request: Request) -> JSONResponse:
    """Return lead/application counts per pipeline stage for the dashboard."""
    from server.db_service import execute_query

    org = _org(request)

    # Lead stage counts
    lead_rows = execute_query(
        """
        SELECT status, COUNT(*) AS cnt
        FROM leads
        WHERE org_id = %s
        GROUP BY status
        """,
        (org,),
    )
    lead_counts: dict = {r["status"]: int(r["cnt"]) for r in (lead_rows or [])}

    # Application stage counts
    app_rows = execute_query(
        """
        SELECT status, COUNT(*) AS cnt
        FROM applicants
        WHERE org_id = %s
        GROUP BY status
        """,
        (org,),
    )
    app_counts: dict = {r["status"]: int(r["cnt"]) for r in (app_rows or [])}

    stages = [
        {"stage": "leads",        "label": "Leads",            "count": sum(lead_counts.values()),            "color": "#6366f1"},
        {"stage": "contacted",    "label": "Contacted",        "count": lead_counts.get("CONTACTED", 0),      "color": "#8b5cf6"},
        {"stage": "interested",   "label": "Interested",       "count": lead_counts.get("INTERESTED", 0),     "color": "#a78bfa"},
        {"stage": "applied",      "label": "Applied",          "count": app_counts.get("APPLIED", 0),         "color": "#3b82f6"},
        {"stage": "documents",    "label": "Docs Review",      "count": app_counts.get("DOCUMENTS_PENDING", 0) + app_counts.get("DOCUMENTS_UNDER_REVIEW", 0), "color": "#06b6d4"},
        {"stage": "eligibility",  "label": "Eligibility",      "count": app_counts.get("ELIGIBILITY_CHECK", 0), "color": "#10b981"},
        {"stage": "entrance_test","label": "Entrance Test",    "count": app_counts.get("ENTRANCE_TEST", 0),    "color": "#f59e0b"},
        {"stage": "interview",    "label": "Interview",        "count": app_counts.get("INTERVIEW", 0),        "color": "#f97316"},
        {"stage": "offer",        "label": "Offer Issued",     "count": app_counts.get("OFFER_ISSUED", 0),     "color": "#ef4444"},
        {"stage": "enrolled",     "label": "Enrolled",         "count": app_counts.get("ENROLLED", 0),         "color": "#22c55e"},
    ]
    return JSONResponse(content=stages)


@router.get("/review-queue")
@require_permission(Permission.STUDENT_READ)
async def get_review_queue(request: Request) -> JSONResponse:
    """Return up to 20 actionable items for the admissions review dashboard."""
    from server.db_service import execute_query

    org = _org(request)

    rows = execute_query(
        """
        SELECT
            id,
            name        AS title,
            intended_program AS subtitle,
            status,
            created_at
        FROM applicants
        WHERE org_id = %s
          AND status IN (
            'APPLIED', 'DOCUMENTS_PENDING', 'DOCUMENTS_UNDER_REVIEW',
            'ELIGIBILITY_CHECK', 'ENTRANCE_TEST', 'INTERVIEW',
            'OFFER_ISSUED', 'OFFER_ACCEPTED'
          )
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (org,),
    )

    STATUS_URGENCY = {
        "DOCUMENTS_UNDER_REVIEW": "high",
        "ELIGIBILITY_CHECK":      "high",
        "OFFER_ISSUED":           "high",
        "INTERVIEW":              "medium",
        "ENTRANCE_TEST":          "medium",
        "DOCUMENTS_PENDING":      "low",
        "APPLIED":                "low",
        "OFFER_ACCEPTED":         "low",
    }

    items = []
    for r in (rows or []):
        status = r["status"]
        items.append({
            "id":             str(r["id"]),
            "type":           "application",
            "title":          r["title"] or "Applicant",
            "subtitle":       r["subtitle"] or "",
            "confidence":     0.85,
            "urgency":        STATUS_URGENCY.get(status, "low"),
            "application_id": str(r["id"]),
            "status":         status,
            "created_at":     r["created_at"].isoformat() if r["created_at"] else None,
        })
    return JSONResponse(content=items)


# ---------------------------------------------------------------------------
# E17 — Re-admission & Credit Transfer Routes (P22)
# ---------------------------------------------------------------------------

@router.post("/readmission")
async def submit_readmission(request: Request, body: dict) -> JSONResponse:
    """Submit a re-admission application."""
    from server.admissions.readmission_service import ReadmissionService
    try:
        result = ReadmissionService.submit_application(
            org_id=_org(request),
            applicant_name=body["applicant_name"],
            applicant_email=body["applicant_email"],
            program_id=body["program_id"],
            gap_from=body["gap_from"],
            gap_to=body["gap_to"],
            semesters_completed=body.get("semesters_completed", 0),
            gap_reason=body["gap_reason"],
            previous_roll_number=body.get("previous_roll_number"),
            previous_institution=body.get("previous_institution"),
            applicant_phone=body.get("applicant_phone"),
        )
        return JSONResponse(content=result, status_code=201)
    except Exception as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})


@router.get("/readmission")
async def list_readmissions(
    request: Request,
    status: Optional[str] = None,
    program_id: Optional[str] = None,
) -> JSONResponse:
    from server.admissions.readmission_service import ReadmissionService
    result = ReadmissionService.list_applications(_org(request), status=status, program_id=program_id)
    return JSONResponse(content={"applications": result, "total": len(result)})


@router.get("/readmission/{application_id}")
async def get_readmission(request: Request, application_id: str) -> JSONResponse:
    from server.admissions.readmission_service import ReadmissionService
    result = ReadmissionService.get_application(application_id, _org(request))
    return JSONResponse(content=result)


@router.post("/readmission/{application_id}/review")
async def start_readmission_review(request: Request, application_id: str) -> JSONResponse:
    from server.admissions.readmission_service import ReadmissionService
    result = ReadmissionService.start_review(application_id, _org(request), _actor(request))
    return JSONResponse(content=result)


@router.post("/readmission/{application_id}/approve")
async def approve_readmission(request: Request, application_id: str, body: dict) -> JSONResponse:
    from server.admissions.readmission_service import ReadmissionService
    result = ReadmissionService.approve(application_id, _org(request), _actor(request), review_notes=body.get("notes"))
    return JSONResponse(content=result)


@router.post("/readmission/{application_id}/reject")
async def reject_readmission(request: Request, application_id: str, body: dict) -> JSONResponse:
    from server.admissions.readmission_service import ReadmissionService
    result = ReadmissionService.reject(application_id, _org(request), _actor(request), review_notes=body.get("notes", ""))
    return JSONResponse(content=result)


@router.post("/credit-transfer")
async def submit_credit_transfer(request: Request, body: dict) -> JSONResponse:
    """Submit a credit transfer request."""
    from server.admissions.credit_transfer_service import CreditTransferService
    result = CreditTransferService.submit_request(
        org_id=_org(request),
        student_id=body["student_id"],
        source_institution=body["source_institution"],
        source_course_code=body["source_course_code"],
        source_course_name=body["source_course_name"],
        source_credits=body["source_credits"],
        readmission_id=body.get("readmission_id"),
    )
    return JSONResponse(content=result, status_code=201)


@router.post("/credit-transfer/{request_id}/ai-draft")
async def generate_credit_transfer_ai_draft(request: Request, request_id: str) -> JSONResponse:
    from server.admissions.credit_transfer_service import CreditTransferService
    result = await CreditTransferService.generate_ai_draft(request_id, _org(request), _actor(request))
    return JSONResponse(content=result)


@router.post("/credit-transfer/{request_id}/decide")
async def decide_credit_transfer(request: Request, request_id: str, body: dict) -> JSONResponse:
    from server.admissions.credit_transfer_service import CreditTransferService
    result = await CreditTransferService.review_and_decide(
        request_id=request_id,
        org_id=_org(request),
        decision=body["decision"],
        decided_by=_actor(request),
        notes=body.get("notes"),
        target_course_id=body.get("target_course_id"),
        credits_awarded=body.get("credits_awarded"),
    )
    return JSONResponse(content=result)


@router.get("/credit-transfer")
async def list_credit_transfers(
    request: Request,
    student_id: Optional[str] = None,
    readmission_id: Optional[str] = None,
    status: Optional[str] = None,
) -> JSONResponse:
    from server.admissions.credit_transfer_service import CreditTransferService
    result = CreditTransferService.list_requests(
        _org(request), student_id=student_id, readmission_id=readmission_id, status=status
    )
    return JSONResponse(content={"requests": result, "total": len(result)})


# ---------------------------------------------------------------------------
# Student Deduplication Routes (P22 — distinct from lead dedup)
# ---------------------------------------------------------------------------

@router.get("/students/duplicates")
async def find_student_duplicates(
    request: Request,
    threshold: float = 0.90,
) -> JSONResponse:
    """Find potential duplicate student records using Jaro-Winkler composite scoring."""
    from server.admissions.deduplication_service import StudentDeduplicationService
    result = StudentDeduplicationService.find_duplicates(_org(request), threshold=threshold)
    return JSONResponse(content={"duplicates": result, "total": len(result)})


@router.post("/students/merge/initiate")
async def initiate_student_merge(request: Request, body: dict) -> JSONResponse:
    """Initiate dual-auth merge workflow (Registrar + Super Admin required)."""
    from server.admissions.deduplication_service import StudentDeduplicationService
    result = StudentDeduplicationService.initiate_merge(
        primary_id=body["primary_id"],
        duplicate_id=body["duplicate_id"],
        org_id=_org(request),
        initiator_id=_actor(request),
    )
    return JSONResponse(content=result, status_code=202)


@router.post("/students/merge/execute")
async def execute_student_merge(request: Request, body: dict) -> JSONResponse:
    """Execute the student merge (called after dual-auth approval)."""
    from server.admissions.deduplication_service import StudentDeduplicationService
    result = StudentDeduplicationService.execute_merge(
        primary_id=body["primary_id"],
        duplicate_id=body["duplicate_id"],
        org_id=_org(request),
        approver_id=_actor(request),
    )
    return JSONResponse(content=result)
