"""API-key management routes (ADR-0011) — the console's "API Keys" page.

  GET  /v1/keys                 → list the caller's tenant's keys (metadata only; secrets never stored)
  POST /v1/keys                 → mint a new key (plaintext returned ONCE)
  POST /v1/keys/{key_id}/revoke → revoke a key the caller's tenant owns

Authenticated (protected /v1/* path): the `AuthenticatedPrincipal` set by the API-key middleware
scopes every operation to the caller's tenant — a tenant can only see/mint/revoke its own keys.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.account.roles import role_scopes
from core.account.scopes import MEMBERS_ADMIN
from core.errors import ApiKeyInvalidError, QUAICUError
from delivery.api.auth import current_principal, enforce_scope

router = APIRouter(prefix="/v1", tags=["keys"])


class ApiKeyInfo(BaseModel):
    key_id: str
    created_at: str
    revoked: bool
    scopes: list[str]


class ApiKeyList(BaseModel):
    keys: list[ApiKeyInfo]


class CreatedApiKey(BaseModel):
    key_id: str
    api_key: str = Field(..., description="Plaintext key — shown ONCE; store it securely.")
    created_at: str


class CreateKeyRequest(BaseModel):
    member_id: str | None = Field(
        None,
        description="Bind the key to this member (W6-1): the key acts AS that member — a distinct "
        "governance actor with the member's role + scopes (so a member can approve an action the "
        "owner proposed). Requires the members:admin scope. Omit for an account-level (owner) key.",
    )


def _principal(request: Request):
    p = current_principal(request)
    if p is None:
        raise HTTPException(
            status_code=401, detail={"error": "Authentication required", "code": "AUTH_REQUIRED"}
        )
    return p


def _engine(request: Request):
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Account management is not enabled", "code": "ACCOUNTS_DISABLED"},
        )
    return engine


@router.get("/keys", response_model=ApiKeyList, summary="List this tenant's API keys")
async def list_keys(request: Request) -> ApiKeyList:
    principal = _principal(request)
    engine = _engine(request)
    keys = engine.list_api_keys(principal.tenant_id)
    return ApiKeyList(
        keys=[
            ApiKeyInfo(
                key_id=k.key_id,
                created_at=k.created_at.isoformat(),
                revoked=k.revoked,
                scopes=sorted(k.scopes),
            )
            for k in sorted(keys, key=lambda k: k.created_at, reverse=True)
        ]
    )


@router.post(
    "/keys", response_model=CreatedApiKey, status_code=status.HTTP_201_CREATED, summary="Mint an API key"
)
async def create_key(
    request: Request, body: CreateKeyRequest | None = Body(default=None)
) -> CreatedApiKey:
    principal = _principal(request)
    engine = _engine(request)
    member_id = body.member_id if body else None
    if member_id:
        # Binding a key to a member mints a credential that acts as that member — gate on members:admin.
        enforce_scope(request, MEMBERS_ADMIN)
        try:
            member = engine.get_member(principal.tenant_id, member_id)
        except QUAICUError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
        record, plaintext = engine.issue_api_key(
            principal.tenant_id, scopes=role_scopes(member.role), member_id=member_id
        )
    else:
        record, plaintext = engine.issue_api_key(principal.tenant_id)
    return CreatedApiKey(
        key_id=record.key_id, api_key=plaintext, created_at=record.created_at.isoformat()
    )


@router.post("/keys/{key_id}/revoke", summary="Revoke an API key")
async def revoke_key(key_id: str, request: Request) -> dict:
    principal = _principal(request)
    engine = _engine(request)
    try:
        engine.revoke_api_key(key_id, tenant=principal.tenant_id)
    except ApiKeyInvalidError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
    return {"key_id": key_id, "revoked": True}
