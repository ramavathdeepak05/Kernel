"""Team-member management routes (W6-1) — the console's "Team" page.

  GET   /v1/members                    → list this tenant's members
  POST  /v1/members                    → invite a member (email + role)
  PATCH /v1/members/{member_id}         → change a member's role
  POST  /v1/members/{member_id}/deactivate → deactivate (revokes their API keys)

Authenticated (protected /v1/* path) and gated on the ``members:admin`` scope. The principal scopes
every operation to the caller's tenant — a tenant can only manage its own members. (SCIM 2.0
provisioning for enterprise IdPs is the separate `/scim/v2` router.)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.account.roles import Role
from core.account.scopes import MEMBERS_ADMIN
from core.errors import AccountNotFoundError
from delivery.api.auth import current_principal, enforce_scope

router = APIRouter(prefix="/v1", tags=["members"])


class MemberInfo(BaseModel):
    member_id: str
    email: str
    display_name: str
    role: str
    status: str
    external_id: str
    created_at: str


class MemberList(BaseModel):
    members: list[MemberInfo]
    roles: list[str] = Field(default_factory=lambda: [r.value for r in Role])


class InviteMemberBody(BaseModel):
    email: str
    role: str = Role.VIEWER.value
    display_name: str = ""


class SetRoleBody(BaseModel):
    role: str


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


def _info(m) -> MemberInfo:
    return MemberInfo(
        member_id=m.member_id,
        email=m.email,
        display_name=m.display_name,
        role=m.role,
        status=m.status.value,
        external_id=m.external_id,
        created_at=m.created_at.isoformat(),
    )


@router.get("/members", response_model=MemberList, summary="List this tenant's members")
async def list_members(request: Request) -> MemberList:
    principal = _principal(request)
    enforce_scope(request, MEMBERS_ADMIN)
    engine = _engine(request)
    members = engine.list_members(principal.tenant_id)
    return MemberList(members=[_info(m) for m in members])


@router.post(
    "/members", response_model=MemberInfo, status_code=status.HTTP_201_CREATED, summary="Invite a member"
)
async def invite_member(body: InviteMemberBody, request: Request) -> MemberInfo:
    principal = _principal(request)
    enforce_scope(request, MEMBERS_ADMIN)
    engine = _engine(request)
    try:
        member = engine.provision_member(
            principal.tenant_id, email=body.email, role=body.role, display_name=body.display_name
        )
    except ValueError as exc:  # unknown role (fail-closed)
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": "INVALID_ROLE"})
    return _info(member)


@router.patch("/members/{member_id}", response_model=MemberInfo, summary="Change a member's role")
async def set_member_role(member_id: str, body: SetRoleBody, request: Request) -> MemberInfo:
    principal = _principal(request)
    enforce_scope(request, MEMBERS_ADMIN)
    engine = _engine(request)
    try:
        member = engine.set_member_role(principal.tenant_id, member_id, body.role)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": "INVALID_ROLE"})
    return _info(member)


@router.post("/members/{member_id}/deactivate", response_model=MemberInfo, summary="Deactivate a member")
async def deactivate_member(member_id: str, request: Request) -> MemberInfo:
    principal = _principal(request)
    enforce_scope(request, MEMBERS_ADMIN)
    engine = _engine(request)
    try:
        member = engine.deactivate_member(principal.tenant_id, member_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
    return _info(member)
