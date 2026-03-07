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
    AdmissionConfirmRequest,
    ReferralCodeCreate,
)
from server.admissions.service import ApplicantService
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
from server.admissions.deduplication import LeadDeduplicationService
from server.admissions.eligibility_service import EligibilityService
from server.admissions.document_verification import DocumentVerificationService
from server.admissions.counsellor_allocation import CounsellorAllocationService
from server.admissions.counsellor_service import CounsellorService
from server.admissions.offer_letter import OfferLetterService
from server.admissions.confirmation import AdmissionConfirmationService
from server.admissions.intake_quality import IntakeQualityService
from server.admissions.enrollment_handover import EnrollmentHandoverService

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
    return JSONResponse(status_code=201, content=applicant.model_dump(default=str))


@router.get("/applicants/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_applicant(request: Request, applicant_id: str) -> JSONResponse:
    applicant = ApplicantService.get_applicant(applicant_id, _org(request))
    return JSONResponse(status_code=200, content=applicant.model_dump(default=str))


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
        content={"applicants": [a.model_dump(default=str) for a in applicants]},
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
    return JSONResponse(status_code=200, content=log.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=doc.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=doc.model_dump(default=str))


@router.get("/documents/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def list_documents(request: Request, applicant_id: str) -> JSONResponse:
    docs = DocumentVerificationService.list_documents(
        applicant_id=applicant_id, org_id=_org(request)
    )
    return JSONResponse(
        status_code=200,
        content={"documents": [d.model_dump(default=str) for d in docs]},
    )


# =============================================================================
# P0-S10: COUNSELLOR MANAGEMENT (CRUD + embedding ETL trigger)
# =============================================================================

from pydantic import BaseModel, EmailStr

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
    return JSONResponse(status_code=201, content=assignment.model_dump(default=str))


# =============================================================================
# E04-S06: OFFER LETTER GENERATION WIZARD
# =============================================================================

@router.post("/offers/generate")
@require_permission(Permission.STUDENT_CREATE)
async def generate_offer_letter(
    request: Request, body: OfferLetterGenerateRequest
) -> JSONResponse:
    """Generate a PDF offer letter for an eligible applicant."""
    letter = OfferLetterService.generate(
        request=body,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=letter.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=record.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=score.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=student.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


@router.get("/applications/{applicant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_application_draft(request: Request, applicant_id: str) -> JSONResponse:
    """Get full application form data for an applicant."""
    draft = ApplicationFormService.get_draft(applicant_id, _org(request))
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=qual.model_dump(default=str))


@router.get("/applications/{applicant_id}/qualifications")
@require_permission(Permission.STUDENT_READ)
async def list_academic_qualifications(
    request: Request, applicant_id: str
) -> JSONResponse:
    """Get all academic qualifications for an applicant."""
    quals = ApplicationFormService.list_academic_qualifications(applicant_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"qualifications": [q.model_dump(default=str) for q in quals]},
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
    return JSONResponse(status_code=201, content=score.model_dump(default=str))


@router.get("/applications/{applicant_id}/entrance-scores")
@require_permission(Permission.STUDENT_READ)
async def list_entrance_scores(
    request: Request, applicant_id: str
) -> JSONResponse:
    scores = ApplicationFormService.list_entrance_scores(applicant_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"scores": [s.model_dump(default=str) for s in scores]},
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
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


@router.post("/applications/{applicant_id}/submit")
@require_permission(Permission.STUDENT_CREATE)
async def submit_application(request: Request, applicant_id: str) -> JSONResponse:
    """Submit the application (DRAFT → SUBMITTED). Validates completeness."""
    draft = ApplicationFormService.submit_application(
        applicant_id=applicant_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=draft.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=lead.model_dump(default=str))


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
        content={"leads": [l.model_dump(default=str) for l in leads], "total": len(leads)},
    )


@router.get("/leads/{lead_id}")
@require_permission(Permission.STUDENT_READ)
async def get_lead(request: Request, lead_id: str) -> JSONResponse:
    lead = LeadService.get(lead_id, _org(request))
    return JSONResponse(status_code=200, content=lead.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=lead.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=activity.model_dump(default=str))


@router.get("/leads/{lead_id}/activities")
@require_permission(Permission.STUDENT_READ)
async def list_lead_activities(request: Request, lead_id: str) -> JSONResponse:
    activities = LeadService.list_activities(lead_id, _org(request))
    return JSONResponse(
        status_code=200,
        content={"activities": [a.model_dump(default=str) for a in activities]},
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
    return JSONResponse(status_code=201, content=consultant.model_dump(default=str))


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
        content={"consultants": [c.model_dump(default=str) for c in consultants]},
    )


@router.get("/consultants-ext/{consultant_id}")
@require_permission(Permission.STUDENT_READ)
async def get_consultant_ext(request: Request, consultant_id: str) -> JSONResponse:
    consultant = ConsultantService.get(consultant_id, _org(request))
    return JSONResponse(status_code=200, content=consultant.model_dump(default=str))


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
    return JSONResponse(status_code=200, content=consultant.model_dump(default=str))


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
    return JSONResponse(status_code=201, content=code.model_dump(default=str))


@router.get("/referral-codes/{code}")
@require_permission(Permission.STUDENT_READ)
async def get_referral_code(request: Request, code: str) -> JSONResponse:
    rc = ReferralCodeService.get_by_code(code, _org(request))
    return JSONResponse(status_code=200, content=rc.model_dump(default=str))


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
    rows = PolicyStore.get_all(org_id=_org(request), category=category)
    return JSONResponse(content={"policies": rows, "total": len(rows)})


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
