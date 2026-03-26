"""
Public Intake & Webhook Router — E04-S14 + E04-S15

E04-S14: Public application intake — no JWT auth, org API key in header.
         Used by the institution's website form to submit applications directly.

E04-S15: Razorpay webhook handler — payment.captured → auto-confirm + enroll.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from server.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intake"])


# =============================================================================
# E04-S14 — Public Intake
# =============================================================================

class IntakeFormPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=254)
    phone: str = Field(..., min_length=5, max_length=20)
    intended_program: str = Field(..., min_length=1, max_length=200)
    academic_percentage: float | None = Field(None, ge=0, le=100)
    entrance_score: float | None = Field(None, ge=0)
    metadata: dict = {}

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = re.sub(r"[\s\-+(). ]", "", v)
        if not digits.isdigit() or len(digits) < 7:
            raise ValueError("Invalid phone number")
        return v.strip()

    @field_validator("name", "intended_program")
    @classmethod
    def no_script_tags(cls, v: str) -> str:
        if re.search(r"<[^>]+>", v):
            raise ValueError("HTML tags are not allowed")
        return v.strip()


def _resolve_org_from_api_key(api_key: str) -> str | None:
    """Look up org_id from a hashed API key in org_api_keys table."""
    from server.db_service import execute_query
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    rows = execute_query(
        "SELECT org_id FROM org_api_keys WHERE key_hash = %s AND is_active = TRUE",
        (key_hash,),
    )
    if not rows:
        return None
    # Update last_used_at async (fire-and-forget via execute_transaction)
    try:
        from server.db_service import execute_transaction
        execute_transaction([
            ("UPDATE org_api_keys SET last_used_at = NOW() WHERE key_hash = %s", (key_hash,))
        ])
    except Exception:
        pass
    return str(rows[0]["org_id"])


@router.post("/api/v1/intake/apply", status_code=202)
async def public_intake(
    body: IntakeFormPayload,
    x_api_key: str = Header(..., description="Organisation API key"),
) -> JSONResponse:
    """
    Public application intake — called by the institution's website form.
    No JWT required; authenticated by org API key.

    Returns 202 Accepted immediately; processing happens async via Celery.
    """
    org_id = _resolve_org_from_api_key(x_api_key)
    if not org_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    payload = body.model_dump()
    if body.academic_percentage is not None:
        payload["metadata"]["academic_percentage"] = body.academic_percentage
    if body.entrance_score is not None:
        payload["metadata"]["entrance_score"] = body.entrance_score

    from server.tasks.admissions import process_intake
    process_intake.delay(org_id=org_id, payload=payload)

    logger.info("intake: queued application for org=%s email=%s", org_id, body.email)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Your application is being processed."},
    )


# Admin endpoint to generate an API key for an org
class ApiKeyCreateRequest(BaseModel):
    org_id: str
    label: str


@router.post("/api/v1/admin/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    authorization: str = Header(..., description="Bearer token — SUPER_ADMIN required"),
) -> JSONResponse:
    """
    Generate an API key for an organisation's public intake form.
    Requires SUPER_ADMIN JWT.
    """
    from server.core.security import SessionManager
    from server.core.rbac import Role
    from server.db_service import execute_query, execute_transaction

    # Auth
    parts = authorization.split(" ", 1)
    token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else None
    session = SessionManager.validate_token(token) if token else None
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Role check — SUPER_ADMIN only
    rows = execute_query(
        "SELECT role FROM users WHERE id = %s AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=session.tenant_id,
    )
    if not rows or Role(rows[0]["role"]) != Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="SUPER_ADMIN role required")

    raw_key = f"alis_{uuid.uuid4().hex}_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    execute_transaction([
        (
            "INSERT INTO org_api_keys (id, org_id, key_hash, label, created_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), body.org_id, key_hash, body.label, session.user_id),
        )
    ])

    logger.info("API key created for org=%s label=%s by=%s", body.org_id, body.label, session.user_id)

    # Return the raw key ONCE — it is never stored in plaintext
    return JSONResponse(
        status_code=201,
        content={
            "api_key": raw_key,
            "label": body.label,
            "warning": "Store this key securely — it will not be shown again.",
        },
    )


# =============================================================================
# E04-S15 — Razorpay Webhook
# =============================================================================

@router.post("/api/v1/webhooks/razorpay")
async def razorpay_webhook(request: Request) -> JSONResponse:
    """
    Razorpay payment webhook — E04-S15 (admissions intake).

    Security: HMAC-SHA256 signature verified against RAZORPAY_WEBHOOK_SECRET
    before any processing.

    Idempotency: deduplicates via payment_webhook_log UNIQUE(gateway, event_id).
    Razorpay guarantees at-least-once delivery; duplicate deliveries are
    detected and ack'd with 200 immediately without re-processing.

    Flow on payment.captured:
      1. Signature verified
      2. Idempotency check — if already PROCESSED → return 200 duplicate
      3. Insert RECEIVED record atomically in payment_webhook_log
      4. Look up applicant by razorpay order_id
      5. Call AdmissionConfirmationService.confirm()
      6. Queue advance_pipeline → enrollment
      7. Mark PROCESSED in payment_webhook_log
    """
    body_bytes = await request.body()

    # ── 1. Signature verification ────────────────────────────────────────────
    signature = request.headers.get("x-razorpay-signature", "")
    if not _verify_razorpay_signature(body_bytes, signature):
        logger.warning("razorpay_webhook: signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event      = payload.get("event")
    payment    = payload.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id = payment.get("id") or payload.get("id") or str(hash(body_bytes))
    gateway    = "razorpay"
    event_type = event or "unknown"

    logger.info("razorpay_webhook: received event=%s payment_id=%s", event_type, payment_id)

    # ── 2 & 3. Idempotency — atomic check-and-insert ─────────────────────────
    # Use payment_id as the canonical event_id (unique per Razorpay payment).
    from server.db_service import execute_query, execute_transaction

    existing = execute_query(
        "SELECT id, status FROM payment_webhook_log WHERE gateway=%s AND event_id=%s",
        (gateway, payment_id),
    )
    if existing:
        if existing[0]["status"] == "PROCESSED":
            logger.info("razorpay_webhook: duplicate event for payment_id=%s — already processed", payment_id)
            return JSONResponse(content={"status": "duplicate", "payment_id": payment_id})
        log_id = existing[0]["id"]
    else:
        # Atomically insert; ON CONFLICT DO NOTHING handles the race between
        # two simultaneous deliveries of the same event from Razorpay.
        inserted = execute_query(
            """
            INSERT INTO payment_webhook_log
                (gateway, event_id, event_type, payload, status)
            VALUES (%s, %s, %s, %s, 'RECEIVED')
            ON CONFLICT (gateway, event_id) DO UPDATE
                SET status = payment_webhook_log.status
            RETURNING id
            """,
            (gateway, payment_id, event_type, body_bytes.decode("utf-8", errors="replace")),
        )
        if not inserted:
            # Conflict resolved by concurrent request — treat as duplicate
            return JSONResponse(content={"status": "duplicate", "payment_id": payment_id})
        log_id = inserted[0]["id"]

    # ── 4. Only process payment.captured ────────────────────────────────────
    if event != "payment.captured":
        execute_transaction([(
            "UPDATE payment_webhook_log SET status='PROCESSED', processed_at=NOW() WHERE id=%s",
            (log_id,),
        )])
        return JSONResponse(content={"status": "ignored", "event": event})

    order_id     = payment.get("order_id")
    amount_paise = payment.get("amount", 0)
    amount_inr   = amount_paise / 100

    if not order_id:
        execute_transaction([(
            "UPDATE payment_webhook_log SET status='FAILED', error_detail=%s WHERE id=%s",
            ("Missing order_id in payment payload", log_id),
        )])
        raise HTTPException(status_code=400, detail="Missing order_id in payment payload")

    # ── 5. Look up applicant by razorpay_order_id ───────────────────────────
    rows = execute_query(
        "SELECT id, org_id FROM applicants WHERE metadata->>'razorpay_order_id' = %s",
        (order_id,),
    )
    if not rows:
        logger.warning("razorpay_webhook: no applicant found for order_id=%s", order_id)
        execute_transaction([(
            "UPDATE payment_webhook_log SET status='PROCESSED', processed_at=NOW(), "
            "error_detail=%s WHERE id=%s",
            (f"unmatched order_id={order_id}", log_id),
        )])
        return JSONResponse(content={"status": "unmatched", "order_id": order_id})

    applicant_id = str(rows[0]["id"])
    org_id       = str(rows[0]["org_id"])

    # ── 6. Confirm admission + queue pipeline ────────────────────────────────
    from server.admissions.confirmation import AdmissionConfirmationService
    from server.admissions.models import AdmissionConfirmRequest
    try:
        AdmissionConfirmationService.confirm(
            request=AdmissionConfirmRequest(
                applicant_id=applicant_id,
                payment_reference=payment_id,
                fee_amount=amount_inr,
            ),
            org_id=org_id,
            actor_id="razorpay_webhook",
        )
    except Exception as exc:
        logger.error("razorpay_webhook: confirm failed for applicant=%s: %s", applicant_id, exc)
        execute_transaction([(
            "UPDATE payment_webhook_log SET status='FAILED', error_detail=%s WHERE id=%s",
            (str(exc), log_id),
        )])
        raise HTTPException(status_code=500, detail=str(exc))

    # ── 7. Mark PROCESSED then queue enrollment pipeline ────────────────────
    execute_transaction([(
        "UPDATE payment_webhook_log SET status='PROCESSED', processed_at=NOW() WHERE id=%s",
        (log_id,),
    )])

    from server.tasks.admissions import advance_pipeline
    advance_pipeline.delay(org_id=org_id, applicant_id=applicant_id)

    logger.info(
        "razorpay_webhook: confirmed admission for applicant=%s payment=%s",
        applicant_id, payment_id,
    )
    return JSONResponse(content={"status": "ok", "applicant_id": applicant_id})


def _verify_razorpay_signature(body: bytes, signature: str) -> bool:
    """Verify Razorpay HMAC-SHA256 webhook signature."""
    if not settings.razorpay_webhook_secret:
        # Fail closed: never accept unsigned webhooks in production.
        # Set RAZORPAY_WEBHOOK_SECRET in environment to enable webhook processing.
        logger.error("razorpay_webhook_secret not configured — rejecting webhook")
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        body,
        "sha256",
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
