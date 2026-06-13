"""Per-tenant, per-tier rate limiting (ADR-0011, WS-D).

A fixed-window (1-minute) counter keyed by tenant. The limit is the tenant's
``rate_limit_per_min`` from `TIER_MATRIX` (honoring per-tenant ``quota_overrides``), resolved through
the `EntitlementEngine`. On breach the request is rejected with **429** and a ``Retry-After`` header
before it reaches any route — quota breach fails closed (F-03) at the edge.

Resolution is best-effort and **fails open**: if no entitlement source is wired, the tenant cannot be
determined, the tenant has no plan, or the tier is unbounded (``-1``), the request passes through. The
limiter is a quota control, not an auth control — authentication and routing still apply downstream.

The window is in-process (one counter map per app instance). A distributed deployment swaps this for a
shared store (Redis) behind the same middleware; the matrix-driven limit lookup is unchanged.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from core.entitlements import EntitlementEngine
from core.errors import EntitlementError, QuotaExceededError
from core.types import TenantId
from delivery.api.deps import extract_tenant

# Paths that are never rate-limited (infra + onboarding, which has no tenant yet; provider webhooks,
# which are signature-authenticated and carry no tenant claim).
_EXEMPT = ("/health", "/docs", "/redoc", "/openapi.json", "/v1/signup", "/v1/billing")

_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests that exceed the tenant's tier rate limit with 429 (fixed 1-minute window)."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # tenant -> (window_start_epoch, count)
        self._counters: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _engine(self, request: Request) -> EntitlementEngine | None:
        """The entitlement engine for limit lookups: the provider's, else a wired store's, else None."""
        provider = getattr(request.app.state, "provider", None)
        if provider is not None:
            return provider.entitlements
        store = getattr(request.app.state, "entitlement_store", None)
        return EntitlementEngine(store) if store is not None else None

    def _limit_for(self, request: Request) -> tuple[str, int] | None:
        """Return (tenant, limit) to enforce, or None to skip (fail-open)."""
        if any(request.url.path == p or request.url.path.startswith(p + "/") for p in _EXEMPT):
            return None
        engine = self._engine(request)
        if engine is None:
            return None
        tenant = extract_tenant(request)
        if tenant is None:
            return None
        try:
            limit = engine.rate_limit_for(tenant)
        except EntitlementError:
            return None  # unprovisioned / inactive: routing & auth will reject downstream
        if limit < 0:
            return None  # unbounded
        return str(tenant), limit

    def _check(self, tenant: str, limit: int) -> bool:
        """Increment the tenant's window counter; return True if still within ``limit``."""
        now = time.monotonic()
        with self._lock:
            start, count = self._counters.get(tenant, (now, 0))
            if now - start >= _WINDOW_SECONDS:
                start, count = now, 0
            count += 1
            self._counters[tenant] = (start, count)
            return count <= limit

    def _daily_quota_exceeded(self, request: Request, tenant: str) -> int | None:
        """Return the daily action limit if the tenant has met/exceeded it, else None (fail-open).

        Reads usage from the wired `UsageMeter` and enforces the tier's ``max_actions_per_day`` via
        the entitlement engine's public quota check. No meter / unbounded tier / unresolved plan →
        skip.
        """
        meter = getattr(request.app.state, "usage_meter", None)
        if meter is None:
            return None
        engine = self._engine(request)
        if engine is None:
            return None
        try:
            engine.assert_within_quota(TenantId(tenant), actions_today=meter.actions_today(tenant))
        except QuotaExceededError as exc:
            return int(exc.detail.get("limit")) if exc.detail else 0
        except EntitlementError:
            return None
        return None

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        target = self._limit_for(request)
        if target is None:
            return await call_next(request)
        tenant, limit = target
        if not self._check(tenant, limit):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(_WINDOW_SECONDS)},
                content={
                    "error": f"Rate limit exceeded ({limit}/min for this tier)",
                    "code": "RATE_LIMITED",
                    "detail": {"tenant": tenant, "limit_per_min": limit},
                },
            )
        daily_limit = self._daily_quota_exceeded(request, tenant)
        if daily_limit is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "error": f"Daily action quota exceeded ({daily_limit}/day for this tier)",
                    "code": "QUOTA_EXCEEDED",
                    "detail": {"tenant": tenant, "limit_per_day": daily_limit},
                },
            )
        return await call_next(request)
