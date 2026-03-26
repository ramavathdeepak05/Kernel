"""E21 — DPDP Consent Middleware

MODULE: Consent Management (E21)
LAYER: Layer 4 (cross-cutting enforcement)

Blocks data-module access when the authenticated user has not given consent
for the module being accessed, as required by the Digital Personal Data
Protection Act 2023 (India).

HTTP 451 ("Unavailable For Legal Reasons") is returned to signal that the
block is a legal/compliance constraint, not a generic access-denied.

Ordering in main.py:
    app.add_middleware(TenantMiddleware)   ← sets X-Tenant-ID / state.tenant_id
    app.add_middleware(ConsentMiddleware)  ← runs AFTER TenantMiddleware

Only authenticated requests (those that carry a valid session recognised by
TenantMiddleware) are checked.  Unauthenticated requests pass through here
and are rejected by the downstream auth guards.
"""
from __future__ import annotations

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths that are ALWAYS allowed regardless of consent status
# ---------------------------------------------------------------------------
CONSENT_EXEMPT_PREFIXES = [
    "/api/v1/auth/",
    "/api/auth/",          # legacy prefix (auth_router uses /api/auth)
    "/api/v1/consent/",
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
]

# ---------------------------------------------------------------------------
# Map URL path prefix → required consent purpose
# ---------------------------------------------------------------------------
PURPOSE_MAP = {
    "/api/v1/admissions":    "ADMISSIONS",
    "/api/v1/academics":     "ACADEMICS",
    "/api/v1/finance":       "FINANCE",
    "/api/v1/hr":            "HR",
    "/api/v1/communication": "COMMUNICATIONS",
    "/api/v1/reporting":     "ANALYTICS",
    "/api/v1/alumni":        "ANALYTICS",
}


class ConsentMiddleware(BaseHTTPMiddleware):
    """
    DPDP Act 2023 — blocks data access if the user has not given consent
    for the module being accessed.

    Only applies to authenticated requests (X-User-ID / state.user_id set
    by TenantMiddleware).  Unauthenticated requests pass through — the
    downstream auth guard will reject them.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path

        # --- Skip exempt paths ---
        for prefix in CONSENT_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # --- Determine required purpose ---
        required_purpose: str | None = None
        for prefix, purpose in PURPOSE_MAP.items():
            if path.startswith(prefix):
                required_purpose = purpose
                break

        if required_purpose is None:
            # No consent mapping for this path — allow through
            return await call_next(request)

        # --- Resolve user + tenant identities ---
        # TenantMiddleware sets these on request.state (via scope["state"])
        # and also forwards them as custom headers for downstream services.
        user_id: Optional[str] = (
            getattr(request.state, "user_id", None)
            or request.headers.get("X-User-ID")
        )
        org_id: Optional[str] = (
            getattr(request.state, "tenant_id", None)
            or request.headers.get("X-Tenant-ID")
        )

        if not user_id or not org_id:
            # Cannot determine identity — let downstream auth handle it
            return await call_next(request)

        # --- Consent gate ---
        try:
            from server.consent.consent_service import ConsentService
            has_consent = ConsentService.has_consent(org_id, user_id, required_purpose)
        except Exception:
            logger.exception(
                "ConsentMiddleware: error checking consent for user=%s org=%s purpose=%s — failing open",
                user_id, org_id, required_purpose,
            )
            # Fail open: don't block users if the consent table is temporarily
            # unreachable (e.g., during a rolling DB migration).
            return await call_next(request)

        if not has_consent:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=451,   # 451 Unavailable For Legal Reasons
                content={
                    "error": "CONSENT_REQUIRED",
                    "message": (
                        f"Consent for {required_purpose} is required under DPDP Act 2023."
                    ),
                    "purpose": required_purpose,
                    "consent_url": "/api/v1/consent/give",
                },
            )

        return await call_next(request)
