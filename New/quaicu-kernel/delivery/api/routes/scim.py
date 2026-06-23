"""SCIM 2.0 User provisioning (W6-1) — enterprise IdP (Okta / Entra) provisioning endpoint.

  GET    /scim/v2/Users[?filter=userName eq "x"]   → ListResponse of this tenant's members
  POST   /scim/v2/Users                            → provision a user (201)
  GET    /scim/v2/Users/{id}                         → one user
  PUT    /scim/v2/Users/{id}                         → replace (role / displayName / active)
  PATCH  /scim/v2/Users/{id}                         → the Okta/Entra `active=false` de-provision path
  DELETE /scim/v2/Users/{id}                         → deactivate (204)

This router authenticates itself (it is NOT under the `/v1` tenant-routing middleware): it resolves the
bearer to an `AuthenticatedPrincipal` and requires the ``scim:admin`` scope. The principal's tenant is
the tenant provisioned into — a SCIM token only ever touches its own tenant (fail-closed). De-provision
(`active=false` / DELETE) deactivates the member and revokes their API keys.

Maps SCIM ⇄ Member: ``id``=member_id, ``userName``=email, ``displayName``=display_name,
``active``=status, ``externalId``=external_id, plus a top-level ``role`` attribute (default VIEWER).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from core.account.model import Member, MemberStatus
from core.account.roles import Role
from core.account.scopes import SCIM_ADMIN
from core.errors import AccountNotFoundError, ApiKeyInvalidError

router = APIRouter(prefix="/scim/v2", tags=["scim"])

_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


def _scim_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"schemas": [_ERROR_SCHEMA], "detail": detail, "status": str(status_code)},
    )


def _auth(request: Request):
    """Resolve the bearer to a principal and require scim:admin. Returns (engine, principal) or raises
    via a returned JSONResponse sentinel — callers check `isinstance(result, JSONResponse)`."""
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        return _scim_error(503, "Account management is not enabled.")
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return _scim_error(401, "Missing bearer token.")
    try:
        principal = engine.resolve_principal(token.strip())
    except ApiKeyInvalidError as exc:
        return _scim_error(401, str(exc))
    if not principal.has_scope(SCIM_ADMIN):
        return _scim_error(403, f"Token is missing the required scope {SCIM_ADMIN!r}.")
    return engine, principal


def _to_scim(member: Member, base_url: str) -> dict:
    return {
        "schemas": [_USER_SCHEMA],
        "id": member.member_id,
        "externalId": member.external_id,
        "userName": member.email,
        "displayName": member.display_name,
        "active": member.status is MemberStatus.ACTIVE,
        "role": member.role,
        "meta": {"resourceType": "User", "location": f"{base_url}/Users/{member.member_id}"},
    }


def _base_url(request: Request) -> str:
    return str(request.url).split("/Users")[0].rstrip("/")


def _requested_role(body: dict) -> str:
    """Best-effort role extraction: a top-level ``role`` string, else the first ``roles[].value``."""
    if isinstance(body.get("role"), str) and body["role"]:
        return body["role"]
    roles = body.get("roles")
    if isinstance(roles, list) and roles and isinstance(roles[0], dict) and roles[0].get("value"):
        return str(roles[0]["value"])
    return Role.VIEWER.value


@router.get("/Users", summary="List / filter users (SCIM 2.0)")
async def list_users(request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    members = engine.list_members(principal.tenant_id)

    # Minimal SCIM filter support: `userName eq "value"` (what Okta/Entra send to find a user).
    flt = request.query_params.get("filter", "")
    if "userName" in flt and " eq " in flt:
        wanted = flt.split(" eq ", 1)[1].strip().strip('"').lower()
        members = [m for m in members if m.email.lower() == wanted]

    base = _base_url(request)
    return {
        "schemas": [_LIST_SCHEMA],
        "totalResults": len(members),
        "startIndex": 1,
        "itemsPerPage": len(members),
        "Resources": [_to_scim(m, base) for m in members],
    }


@router.post("/Users", status_code=status.HTTP_201_CREATED, summary="Provision a user (SCIM 2.0)")
async def create_user(request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    body = await request.json()
    user_name = body.get("userName") or body.get("emails", [{}])[0].get("value", "")
    if not user_name:
        return _scim_error(400, "userName is required.")
    try:
        member = engine.provision_member(
            principal.tenant_id,
            email=str(user_name),
            role=_requested_role(body),
            display_name=str(body.get("displayName", "")),
            external_id=str(body.get("externalId", "")),
        )
    except ValueError as exc:
        return _scim_error(400, str(exc))
    return _to_scim(member, _base_url(request))


@router.get("/Users/{member_id}", summary="Get a user (SCIM 2.0)")
async def get_user(member_id: str, request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    try:
        member = engine.get_member(principal.tenant_id, member_id)
    except AccountNotFoundError:
        return _scim_error(404, f"User {member_id} not found.")
    return _to_scim(member, _base_url(request))


@router.put("/Users/{member_id}", summary="Replace a user (SCIM 2.0)")
async def replace_user(member_id: str, request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    body = await request.json()
    try:
        # Role update (if provided), then active state.
        engine.set_member_role(principal.tenant_id, member_id, _requested_role(body))
        if body.get("active") is False:
            member = engine.deactivate_member(principal.tenant_id, member_id)
        else:
            member = engine.get_member(principal.tenant_id, member_id)
    except AccountNotFoundError:
        return _scim_error(404, f"User {member_id} not found.")
    except ValueError as exc:
        return _scim_error(400, str(exc))
    return _to_scim(member, _base_url(request))


@router.patch("/Users/{member_id}", summary="Patch a user — the active=false de-provision path (SCIM 2.0)")
async def patch_user(member_id: str, request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    body = await request.json()
    # PatchOp: find the resulting `active` value across the Operations (path or value dict).
    active: bool | None = None
    for op in body.get("Operations", []) or []:
        if not isinstance(op, dict):
            continue
        path = str(op.get("path", "")).lower()
        value = op.get("value")
        if path == "active":
            active = _as_bool(value)
        elif isinstance(value, dict) and "active" in value:
            active = _as_bool(value["active"])
    try:
        if active is False:
            member = engine.deactivate_member(principal.tenant_id, member_id)
        else:
            member = engine.get_member(principal.tenant_id, member_id)
    except AccountNotFoundError:
        return _scim_error(404, f"User {member_id} not found.")
    return _to_scim(member, _base_url(request))


@router.delete(
    "/Users/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="De-provision a user",
)
async def delete_user(member_id: str, request: Request) -> Any:
    auth = _auth(request)
    if isinstance(auth, JSONResponse):
        return auth
    engine, principal = auth
    try:
        engine.deactivate_member(principal.tenant_id, member_id)
    except AccountNotFoundError:
        return _scim_error(404, f"User {member_id} not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return None
