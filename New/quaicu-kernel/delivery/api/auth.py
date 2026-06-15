"""API-key authentication + RBAC scope enforcement (ADR-0011, WS-D).

Two pieces:

- `ApiKeyAuthMiddleware` — opt-in (``create_app(..., require_api_key=True)``). For protected
  ``/v1/*`` paths it requires a ``qk_<id>_<secret>`` API key, verifies it against the wired
  `AccountEngine`, asserts the key's tenant matches the request's routing tenant, and stashes the
  resolved `AuthenticatedPrincipal` on ``request.state.principal``. It is the self-serve auth path
  for the kernel's own management surface (the alternative to bringing an external IdP token).

- `enforce_scope(request, scope)` — called inside a route to require an RBAC scope. When auth is
  **disabled** (no principal on the request) it is a no-op, so single-kernel / IdP-token deployments
  and the existing test suite are unaffected. When a principal is present it raises 403 on a missing
  scope.

Selection ≠ authorization still holds: the routing tenant is read from an unverified claim/header
only to pick the kernel; this layer additionally proves the *caller* (via the key) owns that tenant.
"""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from core.account import AuthenticatedPrincipal
from core.errors import ApiKeyInvalidError
from delivery.api.deps import extract_tenant

# Paths under /v1 that are NOT API-key protected:
#   - /v1/signup is the unauthenticated onboarding write.
#   - /v1/admin/* is guarded by its own deployment admin token, not tenant API keys.
#   - /v1/billing/webhook/* is authenticated by the payment provider's signature, not an API key.
#     (NOTE: /v1/billing/checkout IS protected — it is the tenant initiating its own upgrade.)
_EXEMPT_PREFIXES = ("/v1/signup", "/v1/admin", "/v1/billing/webhook")


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _routing_tenant(request: Request) -> str | None:
    """The tenant this request is routed to. ``kernel.tenant`` (single) or the claim/header (shared)."""
    provider = getattr(request.app.state, "provider", None)
    if provider is None:
        kernel = getattr(request.app.state, "kernel", None)
        return str(kernel.tenant) if kernel is not None else None
    tenant = extract_tenant(request)
    return str(tenant) if tenant is not None else None


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid, tenant-matched API key on protected ``/v1/*`` paths; stash the principal."""

    def __init__(self, app: ASGIApp, *, account_engine: Any) -> None:
        super().__init__(app)
        if account_engine is None:
            raise ValueError(
                "require_api_key=True needs an account_engine to verify keys against."
            )
        self._accounts = account_engine

    def _is_protected(self, path: str) -> bool:
        if not path.startswith("/v1/") and path != "/v1":
            return False
        return not any(path == p or path.startswith(p + "/") or path == p for p in _EXEMPT_PREFIXES)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # CORS preflight carries no credentials — let it through to the CORS layer.
        if request.method == "OPTIONS" or not self._is_protected(request.url.path):
            return await call_next(request)

        presented = _bearer(request)
        if presented is None:
            return _unauth("Missing API key", "API_KEY_REQUIRED")
        try:
            principal: AuthenticatedPrincipal = self._accounts.resolve_principal(presented)
        except ApiKeyInvalidError as exc:
            return _unauth(str(exc), exc.code)

        routing_tenant = _routing_tenant(request)
        if routing_tenant is None:
            return _unauth("Cannot determine tenant for routing", "TENANT_UNRESOLVED")
        if str(principal.tenant_id) != routing_tenant:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "API key does not belong to the requested tenant",
                    "code": "TENANT_ISOLATION",
                    "detail": {"key_tenant": str(principal.tenant_id), "request_tenant": routing_tenant},
                },
            )

        request.state.principal = principal
        return await call_next(request)


def _unauth(message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": message, "code": code})


def current_principal(request: Request) -> AuthenticatedPrincipal | None:
    """The `AuthenticatedPrincipal` for this request, or None when API-key auth is disabled."""
    return getattr(request.state, "principal", None)


def enforce_scope(request: Request, scope: str) -> None:
    """Require ``scope`` for this request.

    No-op when API-key auth is disabled (no principal). When a principal is present and lacks the
    scope, raises 403. Call this inside a route after the existing bearer/identity checks.
    """
    principal = current_principal(request)
    if principal is None:
        return  # auth disabled → scopes not enforced (backward compatible)
    if not principal.has_scope(scope):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail={
                "error": f"API key is missing the required scope {scope!r}",
                "code": "INSUFFICIENT_SCOPE",
                "detail": {"required": scope, "granted": sorted(principal.scopes)},
            },
        )
