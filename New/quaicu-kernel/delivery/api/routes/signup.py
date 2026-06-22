"""Self-serve signup routes (ADR-0010) — verified, two-step.

  POST /v1/signup/start  → collect customer details, email a 6-digit OTP, return a signed token (201)
  POST /v1/signup/verify → exchange (token + OTP) for a provisioned STARTER tenant + API key (201)
  POST /v1/signup        → legacy one-step provisioning; ENABLED ONLY when no email sender is wired
                           (dev / no-email deploys). In production (email configured) it returns 409
                           pointing at the verified flow, so OTP can't be bypassed.

These are the only intentionally **unauthenticated** write endpoints — how a new customer onboards
without a pre-existing identity. They are rate-limit-sensitive (WS-D); handlers stay thin. Signup
requires a **company email** (free/personal providers are rejected) and proof of email control (OTP).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.account.model import Account, SignupDetails
from core.account.passwords import PasswordError
from core.email import EmailMessage
from core.entitlements import CustomerPlan, FeatureTier, PlanStatus
from core.billing.coupons import CouponError
from core.errors import (
    AccountExistsError,
    CheckoutError,
    EmailDomainNotAllowedError,
    SignupVerificationError,
)

router = APIRouter(prefix="/v1", tags=["signup"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class SignupStartRequest(BaseModel):
    full_name: str = Field(..., min_length=1, description="Name of the person signing up.")
    email: str = Field(..., description="Company email (free/personal providers are rejected).")
    company_name: str = Field(..., min_length=1, description="Organisation / workspace name.")
    password: str = Field(..., min_length=8, description="Console login password (min 8 chars).")
    job_title: str = Field(..., min_length=1, description="Role, e.g. 'Compliance Lead'.")
    phone: str = Field(..., min_length=1, description="Contact number.")
    # Onboarding survey — all required.
    use_case: str = Field(..., min_length=1, description="How they plan to use the kernel.")
    industry: str = Field(..., min_length=1, description="Industry / sector.")
    company_size: str = Field(..., min_length=1, description="Headcount band.")
    regulations: list[str] = Field(..., min_length=1, description="Regulations of interest (>=1).")


class SignupStartResponse(BaseModel):
    verification_token: str = Field(..., description="Opaque token to return with the OTP on /verify.")
    email: str
    expires_in: int = Field(..., description="Seconds until the OTP/token expires.")


class SignupVerifyRequest(BaseModel):
    verification_token: str
    otp: str = Field(..., description="The 6-digit code emailed to the customer.")
    coupon_code: str | None = Field(None, description="Optional discount code applied to the fee.")


class SignupVerifyResponse(BaseModel):
    # When no fee is configured (or after payment), the account is provisioned and a session returned:
    requires_payment: bool = False
    account_id: str | None = None
    tenant_id: str | None = None
    tier: str | None = None
    session_token: str | None = Field(None, description="Session JWT — the console auto-logs-in.")
    expires_in: int | None = None
    # When a fee is configured, /verify returns an order to pay before the account is created:
    order_id: str | None = None
    razorpay_key_id: str | None = None
    amount_paise: int | None = None
    currency: str | None = None
    payment_token: str | None = Field(None, description="Return with the payment result on /complete.")
    # Set when a coupon was applied — the console shows the saving and the discounted total.
    coupon_code: str | None = None
    discount_paise: int | None = None


class SignupCompleteRequest(BaseModel):
    payment_token: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class SignupResponse(BaseModel):
    """Legacy one-step response (dev / no-email) — returns the API key, since no password is set."""

    account_id: str
    tenant_id: str
    tier: str
    api_key: str = Field(..., description="Plaintext API key — shown ONCE; store it securely.")


class SignupRequest(BaseModel):
    """Legacy one-step (no-OTP) request, kept for dev / no-email deploys."""

    email: str = Field(..., description="Account owner email (unique).")
    name: str = Field(..., description="Organisation / workspace name.")


# ── OTP email body ───────────────────────────────────────────────────────────────


def _otp_email(otp: str, company: str) -> EmailMessage:
    html = (
        '<div style="font-family:system-ui,sans-serif;max-width:480px">'
        '<h2 style="margin:0 0 8px">Verify your email</h2>'
        f"<p>Use this code to finish creating your QUAICU workspace for <strong>{company}</strong>:</p>"
        f'<p style="font-size:32px;font-weight:700;letter-spacing:6px;margin:16px 0">{otp}</p>'
        '<p style="color:#666;font-size:13px">This code expires in 10 minutes. '
        "If you didn't request it, you can ignore this email.</p></div>"
    )
    return EmailMessage(
        to="",  # set by the caller
        subject=f"Your QUAICU verification code: {otp}",
        html=html,
        text=f"Your QUAICU verification code is {otp}. It expires in 10 minutes.",
    )


# ── Routes ───────────────────────────────────────────────────────────────────────


def _require_engine(request: Request):
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Signup is not enabled on this deployment", "code": "SIGNUP_DISABLED"},
        )
    return engine


async def _persist_starter_plan(request: Request, account: Account) -> None:
    """Durably persist the new tenant's STARTER plan.

    `AccountEngine.signup` only writes the plan to the entitlement *cache* (its durable write is async,
    the engine is sync). Without this, the plan is lost on the next restart/redeploy and tenant→kernel
    routing fails PLAN_NOT_FOUND (dashboard/audit/approvals 503). Persisting here (the route is async)
    closes that gap. Idempotent re-cache of what the engine already cached this process.
    """
    store = getattr(request.app.state, "entitlement_store", None)
    if store is None or not hasattr(store, "upsert_persisted"):
        return
    now = datetime.now(timezone.utc)
    await store.upsert_persisted(
        CustomerPlan(
            tenant_id=account.tenant_id,
            tier=FeatureTier.STARTER,
            status=PlanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )


@router.post(
    "/signup/start",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupStartResponse,
    summary="Begin verified signup — emails a one-time code",
)
async def signup_start(body: SignupStartRequest, request: Request) -> SignupStartResponse:
    engine = _require_engine(request)
    sender = getattr(request.app.state, "email_sender", None)
    details = SignupDetails(
        full_name=body.full_name.strip(),
        email=body.email.strip(),
        company_name=body.company_name.strip(),
        password=body.password,
        job_title=body.job_title.strip(),
        phone=body.phone.strip(),
        use_case=body.use_case.strip(),
        industry=body.industry.strip(),
        company_size=body.company_size.strip(),
        regulations=tuple(r.strip() for r in body.regulations if r.strip()),
    )
    try:
        token, otp = engine.start_signup(details)
    except EmailDomainNotAllowedError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc), "code": exc.code})
    except PasswordError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc), "code": "PASSWORD_TOO_WEAK"})
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})

    if sender is not None:
        await sender.send(replace(_otp_email(otp, details.company_name), to=details.email))

    return SignupStartResponse(verification_token=token, email=details.email, expires_in=600)


@router.post(
    "/signup/verify",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupVerifyResponse,
    summary="Complete verified signup — provision the tenant and return a session (auto-login)",
)
async def signup_verify(body: SignupVerifyRequest, request: Request) -> SignupVerifyResponse:
    engine = _require_engine(request)
    gateway = getattr(request.app.state, "signup_payment", None)

    # No fee configured → provision immediately on a valid OTP (auto-login).
    if gateway is None:
        try:
            account = engine.verify_signup(verification_token=body.verification_token, otp=body.otp)
        except SignupVerificationError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
        except AccountExistsError as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})
        return await _provisioned_response(request, engine, account)

    # Fee configured → validate the OTP, then mint a payment order; provisioning happens on /complete.
    try:
        details = engine.details_after_otp(verification_token=body.verification_token, otp=body.otp)
    except SignupVerificationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    if engine.email_exists(str(details.get("email", ""))):
        raise HTTPException(
            status_code=409,
            detail={"error": "An account already exists for that email.", "code": "ACCOUNT_EXISTS"},
        )
    # Apply a discount coupon (if any) to the fee before creating the order. An invalid code fails
    # the request so the console can show the error and let the user fix or drop it.
    amount_paise = gateway.amount_paise
    coupon_code: str | None = None
    discount_paise: int | None = None
    book = getattr(request.app.state, "coupon_book", None)
    if body.coupon_code and book is not None:
        try:
            applied = book.apply(body.coupon_code, gateway.amount_paise, "starter")
        except CouponError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc), "code": exc.code})
        amount_paise = applied.final_paise
        coupon_code = applied.code
        discount_paise = applied.discount_paise

    try:
        order_id = await gateway.create_order(
            receipt=f"signup-{details.get('email', '')}", amount_paise=amount_paise
        )
    except CheckoutError as exc:
        raise HTTPException(status_code=502, detail={"error": str(exc), "code": exc.code})

    payment_token = engine.seal_order_token(details=details, order_id=order_id)
    return SignupVerifyResponse(
        requires_payment=True,
        order_id=order_id,
        razorpay_key_id=gateway.key_id,
        amount_paise=amount_paise,
        currency=gateway.currency,
        payment_token=payment_token,
        coupon_code=coupon_code,
        discount_paise=discount_paise,
    )


async def _provisioned_response(request: Request, engine, account) -> SignupVerifyResponse:
    """Persist the plan, mint a session, and shape the auto-login response."""
    await _persist_starter_plan(request, account)
    session_token, expires_in = engine.mint_session(account)
    return SignupVerifyResponse(
        requires_payment=False,
        account_id=account.account_id,
        tenant_id=str(account.tenant_id),
        tier="STARTER",
        session_token=session_token,
        expires_in=expires_in,
    )


@router.post(
    "/signup/complete",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupVerifyResponse,
    summary="Complete a fee-gated signup — verify the ₹2 payment, then provision (auto-login)",
)
async def signup_complete(body: SignupCompleteRequest, request: Request) -> SignupVerifyResponse:
    engine = _require_engine(request)
    gateway = getattr(request.app.state, "signup_payment", None)
    if gateway is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "No signup fee is configured on this deployment.", "code": "NO_FEE"},
        )
    paid_until = datetime.now(timezone.utc) + timedelta(days=365)
    try:
        account = engine.complete_paid_signup(
            payment_token=body.payment_token,
            order_id=body.razorpay_order_id,
            verify_payment=lambda: gateway.verify_payment(
                order_id=body.razorpay_order_id,
                payment_id=body.razorpay_payment_id,
                signature=body.razorpay_signature,
            ),
            paid_until=paid_until,
        )
    except SignupVerificationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})
    return await _provisioned_response(request, engine, account)


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupResponse,
    summary="Legacy one-step signup (only on deploys without email/OTP)",
)
async def signup(body: SignupRequest, request: Request) -> SignupResponse:
    engine = _require_engine(request)
    # In production an email sender is wired → the OTP flow is mandatory; refuse the no-OTP path.
    if getattr(request.app.state, "email_sender", None) is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Use the verified signup flow (/v1/signup/start then /v1/signup/verify).",
                "code": "SIGNUP_VERIFICATION_REQUIRED",
            },
        )
    try:
        account, api_key = engine.signup(email=body.email, name=body.name)
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})

    await _persist_starter_plan(request, account)
    return SignupResponse(
        account_id=account.account_id,
        tenant_id=str(account.tenant_id),
        tier="STARTER",
        api_key=api_key,
    )
