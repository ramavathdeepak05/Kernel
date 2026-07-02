"""Console auth routes (ADR-0011) — email + password login → session JWT.

  POST /v1/auth/login → verify email+password, return a short-lived session token (the bearer the
  console uses thereafter). Unauthenticated (it's how you obtain a token); exempt from the API-key
  middleware (see delivery/api/auth.py `_EXEMPT_PREFIXES`).

The API key issued at signup remains for programmatic access; this is the human console login.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.account.passwords import PasswordError
from core.email import EmailMessage
from core.errors import AccountNotFoundError, SignupVerificationError

router = APIRouter(prefix="/v1", tags=["auth"])


def _require_engine(request: Request):
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Login is not enabled on this deployment", "code": "LOGIN_DISABLED"},
        )
    return engine


class LoginRequest(BaseModel):
    email: str = Field(..., description="Account email.")
    password: str = Field(..., description="Account password.")


class LoginResponse(BaseModel):
    session_token: str = Field(..., description="Short-lived JWT — send as the Bearer token.")
    tenant_id: str
    expires_in: int = Field(..., description="Seconds until the session expires.")


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in with email + password → session token",
)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    engine = _require_engine(request)
    email, password = body.email.strip(), body.password
    # Try the account owner first, then a member (D1-5) — one uniform error, no enumeration.
    try:
        account = engine.authenticate(email=email, password=password)
        token, expires_in = engine.mint_session(account)
        return LoginResponse(
            session_token=token, tenant_id=str(account.tenant_id), expires_in=expires_in
        )
    except AccountNotFoundError:
        pass
    try:
        member = engine.authenticate_member(email=email, password=password)
    except AccountNotFoundError:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
        )
    token, expires_in = engine.mint_member_session(member)
    return LoginResponse(
        session_token=token, tenant_id=str(member.tenant_id), expires_in=expires_in
    )


class SetPasswordRequest(BaseModel):
    token: str = Field(..., description="The signed set-password token from the invite email.")
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars).")


@router.post(
    "/auth/set-password",
    response_model=LoginResponse,
    summary="Set a member's password with the invite token → session token (auto-login)",
)
async def set_password(body: SetPasswordRequest, request: Request) -> LoginResponse:
    """A member sets their password via the emailed link, then is logged straight in."""
    engine = _require_engine(request)
    try:
        member = engine.set_member_password(token=body.token, new_password=body.new_password)
    except (SignupVerificationError, AccountNotFoundError):
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid or expired set-password link.", "code": "SET_PASSWORD_INVALID"},
        )
    except PasswordError as exc:
        raise HTTPException(
            status_code=422, detail={"error": str(exc), "code": "PASSWORD_TOO_WEAK"}
        )
    token, expires_in = engine.mint_member_session(member)
    return LoginResponse(
        session_token=token, tenant_id=str(member.tenant_id), expires_in=expires_in
    )


# ── Password reset (forgot password → email OTP → new password) ──────────────────


class ForgotRequest(BaseModel):
    email: str = Field(..., description="Account email.")


class ForgotResponse(BaseModel):
    reset_token: str = Field(..., description="Return with the OTP + new password on /auth/reset.")
    expires_in: int = 900


class ResetRequest(BaseModel):
    reset_token: str
    otp: str = Field(..., description="The 6-digit code emailed to the account.")
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars).")


def _reset_email(otp: str) -> EmailMessage:
    html = (
        '<div style="font-family:system-ui,sans-serif;max-width:480px">'
        '<h2 style="margin:0 0 8px">Reset your password</h2>'
        "<p>Use this code to set a new QUAICU password:</p>"
        f'<p style="font-size:32px;font-weight:700;letter-spacing:6px;margin:16px 0">{otp}</p>'
        '<p style="color:#666;font-size:13px">This code expires in 15 minutes. '
        "If you didn't request it, you can ignore this email.</p></div>"
    )
    return EmailMessage(
        to="",
        subject=f"Your QUAICU password reset code: {otp}",
        html=html,
        text=f"Your QUAICU password reset code is {otp}. It expires in 15 minutes.",
    )


@router.post("/auth/forgot", response_model=ForgotResponse, summary="Request a password-reset code")
async def forgot_password(body: ForgotRequest, request: Request) -> ForgotResponse:
    engine = _require_engine(request)
    # Always returns a token (no account enumeration); only emails a code if the account exists.
    reset_token, otp = engine.start_password_reset(email=body.email.strip())
    sender = getattr(request.app.state, "email_sender", None)
    if otp is not None and sender is not None:
        await sender.send(replace(_reset_email(otp), to=body.email.strip()))
    return ForgotResponse(reset_token=reset_token)


@router.post(
    "/auth/reset",
    response_model=LoginResponse,
    summary="Set a new password with the reset code → session token (auto-login)",
)
async def reset_password(body: ResetRequest, request: Request) -> LoginResponse:
    engine = _require_engine(request)
    try:
        account = engine.complete_password_reset(
            reset_token=body.reset_token, otp=body.otp, new_password=body.new_password
        )
    except SignupVerificationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    except PasswordError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc), "code": "PASSWORD_TOO_WEAK"})
    except AccountNotFoundError:
        raise HTTPException(
            status_code=400, detail={"error": "Reset failed.", "code": "RESET_FAILED"}
        )
    token, expires_in = engine.mint_session(account)
    return LoginResponse(
        session_token=token, tenant_id=str(account.tenant_id), expires_in=expires_in
    )
