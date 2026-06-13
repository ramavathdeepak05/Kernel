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

from fastapi import Request

from core.types import TenantId
from delivery.sdk.kernel import Kernel


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
