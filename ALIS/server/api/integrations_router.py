"""P14 -- Integrations Router"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from server.core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/integrations", tags=["P14 Integrations"])

class DigiLockerAuthRequest(BaseModel):
    applicant_id: str
    state: str

class DigiLockerCallbackRequest(BaseModel):
    applicant_id: str
    code: str
    state: str

class NTAImportRequest(BaseModel):
    applicant_id: str
    exam_type: str
    application_number: str
    dob: str

class SMSOTPRequest(BaseModel):
    phone: str
    otp_length: int = Field(default=6, ge=4, le=8)
    expiry_minutes: int = Field(default=10, ge=1, le=30)

class SMSVerifyRequest(BaseModel):
    phone: str
    otp: str
    request_id: Optional[str] = None

@router.get("/health")
@require_permission(Permission.STUDENT_READ)
async def get_integrations_health(request: Request) -> JSONResponse:
    from server.core.settings import settings
    statuses = [
        {"name": "DigiLocker", "enabled": settings.digilocker_enabled,
         "status": "configured" if settings.digilocker_enabled else "disabled",
         "detail": "Set DIGILOCKER_CLIENT_ID" if not settings.digilocker_enabled else "OAuth2 vault"},
        {"name": "NTA Score Import", "enabled": settings.nta_enabled,
         "status": "configured" if settings.nta_enabled else "disabled",
         "detail": "Set NTA_API_KEY" if not settings.nta_enabled else "JEE/NEET/CUET"},
        {"name": "LMS (Moodle)", "enabled": settings.lms_enabled,
         "status": "configured" if settings.lms_enabled else "disabled",
         "detail": "Set LMS_BASE_URL" if not settings.lms_enabled else settings.lms_base_url},
        {"name": "Email Provisioning", "enabled": settings.email_provision_enabled,
         "status": "configured" if settings.email_provision_enabled else "disabled",
         "detail": settings.email_provider if settings.email_provision_enabled else "Set EMAIL_PROVIDER"},
        {"name": "Payment Gateway", "enabled": settings.payment_gateway_enabled,
         "status": "configured" if settings.payment_gateway_enabled else "disabled",
         "detail": settings.payment_gateway_provider if settings.payment_gateway_enabled else "Set PAYMENT_GATEWAY_ENABLED"},
        {"name": "SMS Gateway", "enabled": settings.sms_gateway_enabled,
         "status": "configured" if settings.sms_gateway_enabled else "disabled",
         "detail": settings.sms_provider if settings.sms_gateway_enabled else "Set SMS_GATEWAY_ENABLED"},
        {"name": "Document Storage", "enabled": True, "status": "configured",
         "detail": f"Provider: {settings.storage_provider}"},
    ]
    return JSONResponse({"integrations": statuses})

@router.post("/digilocker/auth-url")
@require_permission(Permission.STUDENT_CREATE)
async def get_digilocker_auth_url(request: Request, body: DigiLockerAuthRequest) -> JSONResponse:
    from server.admissions.integrations.digilocker import DigiLockerClient
    client = DigiLockerClient()
    if not client.is_enabled():
        raise HTTPException(status_code=503, detail="DigiLocker not configured.")
    auth_url = client.get_auth_url(state=body.state)
    return JSONResponse({"auth_url": auth_url, "state": body.state})

@router.post("/digilocker/callback")
@require_permission(Permission.STUDENT_CREATE)
async def digilocker_callback(request: Request, body: DigiLockerCallbackRequest) -> JSONResponse:
    from server.admissions.integrations.digilocker import DigiLockerClient
    client = DigiLockerClient()
    if not client.is_enabled():
        raise HTTPException(status_code=503, detail="DigiLocker not configured.")
    try:
        token_data = client.exchange_code(code=body.code)
        access_token = token_data.get("access_token", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DigiLocker token exchange failed: {exc}")
    result = client.pull_documents(access_token=access_token)
    if not result.success:
        return JSONResponse({"success": False, "documents_pulled": 0, "documents": [], "error": result.error})
    docs = [{"doc_type": d.doc_type, "name": d.name, "issuer": d.issuer,
              "is_valid": d.is_valid, "mime_type": d.mime_type, "uri": d.uri} for d in result.documents]
    return JSONResponse({"success": True, "documents_pulled": len(docs), "documents": docs})

@router.post("/nta/import-score")
@require_permission(Permission.STUDENT_CREATE)
async def import_nta_score(request: Request, body: NTAImportRequest) -> JSONResponse:
    from server.admissions.integrations.nta_scores import NTAScoreClient
    client = NTAScoreClient()
    if not client.is_enabled():
        raise HTTPException(status_code=503, detail="NTA integration not configured. Set NTA_API_KEY.")
    result = client.fetch_score(exam_type=body.exam_type, application_number=body.application_number, dob=body.dob)
    if not result.success:
        return JSONResponse({"success": False, "applicant_id": body.applicant_id, "exam_type": body.exam_type, "error": result.error})
    sc = result.score_card
    return JSONResponse({"success": True, "applicant_id": body.applicant_id, "exam_type": body.exam_type,
                         "total_marks": sc.total_marks, "percentile": sc.percentile, "rank": sc.rank, "subject_scores": sc.subject_scores})

@router.post("/sms/send-otp")
@require_permission(Permission.STUDENT_CREATE)
async def send_otp(request: Request, body: SMSOTPRequest) -> JSONResponse:
    from server.admissions.integrations.sms_gateway import SMSGatewayClient
    client = SMSGatewayClient()
    result = client.send_otp(phone=body.phone, otp_length=body.otp_length, expiry_minutes=body.expiry_minutes)
    return JSONResponse({"success": result.success, "request_id": result.request_id, "provider": result.provider, "error": result.error})

@router.post("/sms/verify-otp")
@require_permission(Permission.STUDENT_CREATE)
async def verify_otp(request: Request, body: SMSVerifyRequest) -> JSONResponse:
    from server.admissions.integrations.sms_gateway import SMSGatewayClient
    client = SMSGatewayClient()
    result = client.verify_otp(phone=body.phone, otp=body.otp, request_id=body.request_id)
    return JSONResponse({"is_valid": result.is_valid, "phone": result.phone, "error": result.error})

@router.post("/lms/provision/{student_id}")
@require_permission(Permission.STUDENT_CREATE)
async def lms_provision_student(request: Request, student_id: str) -> JSONResponse:
    """
    Manually trigger Moodle provisioning for a single student.

    Requires ADMIN permission. Idempotent — safe to call multiple times;
    if the account already exists in Moodle it will be updated rather than
    duplicated.
    """
    from server.integrations.lms_service import MoodleLMSService
    org_id   = getattr(request.state, "tenant_id", "default")
    actor_id = getattr(request.state, "user_id", "anonymous")
    service  = MoodleLMSService()
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="LMS integration not configured. Set LMS_BASE_URL and LMS_API_TOKEN.")
    result = service.provision_student(org_id=org_id, student_id=student_id, actor_id=actor_id)
    return JSONResponse(result)


@router.get("/lms/status/{student_id}")
@require_permission(Permission.STUDENT_READ)
async def lms_student_status(request: Request, student_id: str) -> JSONResponse:
    """
    Check whether a student has an active Moodle account and return
    their last grade-sync timestamp.
    """
    from server.db_service import execute_query
    from server.integrations.lms_service import MoodleLMSService
    org_id = getattr(request.state, "tenant_id", "default")

    service = MoodleLMSService()
    if not service.is_enabled():
        return JSONResponse({
            "student_id": student_id,
            "lms_enabled": False,
            "detail": "LMS not configured",
        })

    # Grade sync record tells us we've provisioned + synced before
    rows = execute_query(
        "SELECT moodle_user_id, synced_at FROM lms_grade_sync WHERE org_id=%s AND student_id=%s",
        (org_id, student_id),
    )
    if rows:
        return JSONResponse({
            "student_id":     student_id,
            "lms_enabled":    True,
            "provisioned":    True,
            "moodle_user_id": rows[0]["moodle_user_id"],
            "last_synced_at": str(rows[0]["synced_at"]) if rows[0]["synced_at"] else None,
        })

    return JSONResponse({
        "student_id":  student_id,
        "lms_enabled": True,
        "provisioned": False,
        "detail":      "No LMS provisioning record found; call POST /lms/provision/{student_id}",
    })


@router.get("/storage/presign")
@require_permission(Permission.STUDENT_CREATE)
async def get_presigned_upload_url(
    request: Request, org_id: str = Query(...), applicant_id: str = Query(...),
    doc_type: str = Query(default="OTHER"), file_name: str = Query(...), expires_in: int = Query(default=3600)
) -> JSONResponse:
    from server.admissions.integrations.document_storage import DocumentStorageClient
    client = DocumentStorageClient()
    safe_name = file_name.replace(" ", "_").replace("/", "_")
    storage_key = f"{org_id}/{applicant_id}/{doc_type}/{uuid4().hex[:8]}_{safe_name}"
    url_obj = client.get_upload_url(storage_key=storage_key, expires_in=expires_in)
    if url_obj is None:
        raise HTTPException(status_code=501, detail=f"Pre-signed URLs not supported for provider {client.provider!r}.")
    return JSONResponse({"url": url_obj.url, "storage_key": url_obj.storage_key,
                         "expires_in_seconds": url_obj.expires_in_seconds, "method": url_obj.method})
