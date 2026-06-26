"""Request → kernel resolution (ADR-0010).

The API supports two deployment shapes behind one accessor:

- **Single-kernel** (legacy / dedicated): ``app.state.kernel`` is set; every request uses it and the
  tenant is the kernel's fixed ``kernel.tenant``.
- **Shared SaaS plane**: ``app.state.provider`` is a `TieredKernelProvider`; the tenant is read from
  the caller's bearer token and the request is routed to that tenant's tier kernel.

Routes call ``get_kernel(request)`` and ``get_request_tenant(request)`` instead of touching
``app.state`` directly, so the same handler works in both shapes. Routing reads the JWT tenant claim
*without* verifying the signature — that only selects which kernel handles the request; the resolved
kernel's IdentityPort still cryptographically verifies the token and enforces tenant isolation.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Request

from core.types import Actor, ActorId, TenantId
from delivery.sdk.kernel import Kernel

# Shared secret proving a request arrived via our Cloudflare Worker edge. When set, the edge-forwarded
# client IP is trusted; unset → the trusted-IP path is disabled and we fall back to the peer address.
_EDGE_SECRET = os.getenv("QUAICU_EDGE_SECRET", "")


def trusted_client_ip(request: Request) -> str | None:
    """The originating client IP, safe to use as a rate-limit key.

    The Cloud Run origin is publicly reachable, so a raw forwarded header is spoofable. Our Cloudflare
    Worker forwards the real IP as ``X-Real-Client-IP`` and authenticates itself with
    ``X-Edge-Auth == QUAICU_EDGE_SECRET`` (and strips any client-supplied copies). We therefore trust
    the forwarded IP **only** when that shared secret matches (constant-time); a direct caller to the
    run.app origin can't forge it. Falls back to the immediate peer (``request.client.host``) when the
    secret is unset or the edge header is missing/wrong.
    """
    if _EDGE_SECRET:
        edge = request.headers.get("x-edge-auth", "")
        if edge and hmac.compare_digest(edge, _EDGE_SECRET):
            real = request.headers.get("x-real-client-ip", "").strip()
            if real:
                return real
    client = request.client
    return client.host if client is not None else None


def _bearer_token_or_none(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def extract_tenant(request: Request) -> TenantId | None:
    """Best-effort tenant for routing: JWT ``tenant``/``tid`` claim, else ``X-Tenant-Id`` header.

    Signature is NOT verified here (routing only). Returns None if no tenant can be determined.
    """
    token = _bearer_token_or_none(request)
    if token is not None:
        try:
            import jwt as _jwt

            claims = _jwt.decode(token, options={"verify_signature": False})
            tenant = claims.get("tenant") or claims.get("tid")
            if tenant:
                return TenantId(str(tenant))
        except Exception:  # noqa: BLE001 — malformed token: fall through to header
            pass
    header_tenant = request.headers.get("x-tenant-id")
    return TenantId(header_tenant) if header_tenant else None


def get_kernel(request: Request) -> Kernel:
    """Resolve the kernel serving this request (provider-routed or the single kernel)."""
    provider = getattr(request.app.state, "provider", None)
    if provider is None:
        return request.app.state.kernel
    tenant = extract_tenant(request)
    if tenant is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={"error": "Cannot determine tenant for routing", "code": "TENANT_UNRESOLVED"},
        )
    return provider.kernel_for(tenant)


def resolve_governed_actor(request: Request, tenant: TenantId) -> Actor | None:
    """A host-provided governance actor derived from a verified **API-key** principal, or ``None``.

    On the SaaS plane the auth middleware verifies the bearer and stashes an ``AuthenticatedPrincipal``
    on ``request.state.principal``. A ``qk_`` API key is not a JWT, so the kernel's (JWT) IdentityPort
    can't resolve a governance actor from it — yet the principal *is* cryptographically verified
    (HMAC key lookup), so it is a trusted host identity, not a spoofable caller claim. For a ``qk_``
    bearer we therefore build the actor directly from the principal (account id + governance roles).

    Returns ``None`` for any other bearer (a session JWT / IdP token), so that path is **unchanged** —
    the kernel's IdentityPort still verifies the token and resolves the actor. Routes never accept a
    caller-supplied actor, so this never widens trust.
    """
    token = _bearer_token_or_none(request)
    if token is None or not token.startswith("qk_"):
        return None
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    return Actor(
        # The actor identity is the principal's subject — a member-bound key carries the member id
        # (distinct actor → SoD holds), the account/bootstrap key + session use the account id.
        id=ActorId(str(getattr(principal, "actor_id", None) or principal.account_id)),
        tenant=tenant,
        roles=tuple(getattr(principal, "roles", ()) or ()),
    )


def get_request_tenant(request: Request) -> TenantId:
    """The tenant to stamp on actions for this request.

    Provider mode: the token/header tenant. Single-kernel mode: the kernel's fixed tenant.
    """
    provider = getattr(request.app.state, "provider", None)
    if provider is None:
        return request.app.state.kernel.tenant
    tenant = extract_tenant(request)
    if tenant is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={"error": "Cannot determine tenant for routing", "code": "TENANT_UNRESOLVED"},
        )
    return tenant
