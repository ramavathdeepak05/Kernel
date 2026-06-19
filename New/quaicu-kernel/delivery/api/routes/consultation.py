"""Business / Enterprise consultation routes (ADR-0011).

High-touch upgrade path — these tiers are quote-based, not self-serve. A prospect pays a fixed
consultation deposit (₹50,000) to connect with the integrations team:

  POST /v1/consultation/start    → create the ₹50,000 Razorpay order, return it for checkout
  POST /v1/consultation/complete → verify the payment, email the integrations team the lead, ack

Unauthenticated (a prospect doesn't have an account yet) → exempt from the API-key middleware. The
tier is NOT changed here; the team consults, scopes the custom plan, and onboards manually.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.email import EmailMessage
from core.errors import CheckoutError

router = APIRouter(prefix="/v1", tags=["consultation"])

_TIERS = {"BUSINESS", "ENTERPRISE"}


class ConsultLead(BaseModel):
    tier: str = Field(..., description="BUSINESS or ENTERPRISE.")
    full_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    company_name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)


class ConsultStartResponse(BaseModel):
    order_id: str
    razorpay_key_id: str
    amount_paise: int
    currency: str


class ConsultCompleteRequest(ConsultLead):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


def _gateway(request: Request):
    gw = getattr(request.app.state, "signup_payment", None)
    if gw is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Payments are not enabled on this deployment", "code": "PAYMENTS_DISABLED"},
        )
    return gw


def _consult_cfg(request: Request) -> dict:
    return getattr(request.app.state, "consultation", None) or {}


def _amount(request: Request) -> int:
    return int(_consult_cfg(request).get("amount_paise", 5_000_000))  # ₹50,000 default


@router.post("/consultation/start", response_model=ConsultStartResponse, summary="Start a consultation")
async def consultation_start(body: ConsultLead, request: Request) -> ConsultStartResponse:
    if body.tier.upper() not in _TIERS:
        raise HTTPException(status_code=422, detail={"error": "tier must be BUSINESS or ENTERPRISE", "code": "UNKNOWN_TIER"})
    gw = _gateway(request)
    amount = _amount(request)
    try:
        order_id = await gw.create_order(receipt=f"consult-{body.tier}-{body.email}", amount_paise=amount)
    except CheckoutError as exc:
        raise HTTPException(status_code=502, detail={"error": str(exc), "code": exc.code})
    return ConsultStartResponse(
        order_id=order_id, razorpay_key_id=gw.key_id, amount_paise=amount, currency=gw.currency
    )


@router.post("/consultation/complete", summary="Verify the consultation payment + notify the team")
async def consultation_complete(body: ConsultCompleteRequest, request: Request) -> dict:
    gw = _gateway(request)
    if not gw.verify_payment(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    ):
        raise HTTPException(status_code=400, detail={"error": "Payment could not be verified.", "code": "PAYMENT_INVALID"})

    sender = getattr(request.app.state, "email_sender", None)
    notify = _consult_cfg(request).get("notify_email") or "ceo@quaicu.org"
    if sender is not None:
        html = (
            f"<h2>New {body.tier} consultation (paid)</h2>"
            f"<p><strong>{body.full_name}</strong> — {body.email}</p>"
            f"<p>Company: {body.company_name} · Phone: {body.phone}</p>"
            f"<p>Tier: <strong>{body.tier}</strong> · Razorpay payment: {body.razorpay_payment_id} "
            f"(order {body.razorpay_order_id})</p>"
            "<p>Reach out to scope the custom plan and onboard.</p>"
        )
        msg = EmailMessage(
            to=notify,
            subject=f"[QUAICU] {body.tier} consultation — {body.company_name}",
            html=html,
            text=f"{body.full_name} ({body.email}, {body.company_name}, {body.phone}) paid for a {body.tier} consultation. Payment {body.razorpay_payment_id}.",
        )
        try:
            await sender.send(replace(msg, to=notify))
        except Exception:  # noqa: BLE001 — notification is best-effort; the payment already succeeded
            pass

    return {"ok": True, "tier": body.tier}
