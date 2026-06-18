"""Console auth routes (ADR-0011) — email + password login → session JWT.

  POST /v1/auth/login → verify email+password, return a short-lived session token (the bearer the
  console uses thereafter). Unauthenticated (it's how you obtain a token); exempt from the API-key
  middleware (see delivery/api/auth.py `_EXEMPT_PREFIXES`).

The API key issued at signup remains for programmatic access; this is the human console login.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.errors import AccountNotFoundError

router = APIRouter(prefix="/v1", tags=["auth"])


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
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Login is not enabled on this deployment", "code": "LOGIN_DISABLED"},
        )
    try:
        account = engine.authenticate(email=body.email.strip(), password=body.password)
    except AccountNotFoundError:
        # Uniform error — never reveal whether the email exists.
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
        )
    token, expires_in = engine.mint_session(account)
    return LoginResponse(
        session_token=token, tenant_id=str(account.tenant_id), expires_in=expires_in
    )
