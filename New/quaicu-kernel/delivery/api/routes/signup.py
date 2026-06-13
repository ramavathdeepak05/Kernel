"""Self-serve signup route (ADR-0010).

POST /v1/signup → 201 — provisions a STARTER tenant and returns a one-time API key.

This is the only intentionally **unauthenticated** write endpoint: it is how a new customer onboards
without a pre-existing identity. It is rate-limit-sensitive (see WS-D); the handler stays thin.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.errors import AccountExistsError

router = APIRouter(prefix="/v1", tags=["signup"])


class SignupRequest(BaseModel):
    email: str = Field(..., description="Account owner email (unique).")
    name: str = Field(..., description="Organisation / workspace name.")


class SignupResponse(BaseModel):
    account_id: str
    tenant_id: str
    tier: str
    api_key: str = Field(..., description="Plaintext API key — shown ONCE; store it securely.")


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupResponse,
    summary="Self-serve signup (creates a STARTER tenant + API key)",
)
async def signup(body: SignupRequest, request: Request) -> SignupResponse:
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Signup is not enabled on this deployment", "code": "SIGNUP_DISABLED"},
        )
    try:
        account, api_key = engine.signup(email=body.email, name=body.name)
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc), "code": exc.code})

    return SignupResponse(
        account_id=account.account_id,
        tenant_id=str(account.tenant_id),
        tier="STARTER",
        api_key=api_key,
    )
