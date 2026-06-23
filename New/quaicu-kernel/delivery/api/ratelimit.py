"""Per-tenant, per-tier rate limiting (ADR-0011, WS-D).

A fixed-window (1-minute) counter. The limit is the tenant's ``rate_limit_per_min`` from
`TIER_MATRIX` (honoring per-tenant ``quota_overrides``), resolved through the `EntitlementEngine`. On
breach the request is rejected with **429** and a ``Retry-After`` header before it reaches any route —
quota breach fails closed (F-03) at the edge.

**Counter key (anti-DoS).** This middleware runs *after* `ApiKeyAuthMiddleware` (see the stack order
in ``delivery/api/app.py``). When a request is authenticated, the counter is keyed on the
cryptographically-**verified** tenant (``request.state.principal.tenant_id``). When auth is disabled
(IdP-token / single-kernel deployments have no middleware-level principal), the counter falls back to
the **client IP** — never the routing tenant, which comes from an *unverified* JWT claim / header
(``deps.extract_tenant``). Keying an unauthenticated counter on that spoofable tenant would let an
attacker forge a victim's tenant id and exhaust the victim's quota (DoS). The unverified tenant is
still used only to *look up the tier limit value* in the IP-keyed case — at worst that loosens the
attacker's own IP bucket, never a victim's.

Resolution is best-effort and **fails open**: if no entitlement source is wired, no key can be
determined, the tenant has no plan, or the tier is unbounded (``-1``), the request passes through. The
limiter is a quota control, not an auth control — authentication and routing still apply downstream.

The window is in-process (one counter map per app instance). A distributed deployment swaps this for a
shared store (Redis) behind the same middleware; the matrix-driven limit lookup is unchanged.

Deployment note: the IP fallback uses ``request.client.host`` — the immediate peer. Behind a load
balancer/reverse proxy this is the proxy's IP, so all unauthenticated traffic would share one bucket.
Terminate the proxy with a *trusted* forwarded-for handler (so the real client IP is set on the scope)
before relying on the IP path at scale; do NOT trust a raw ``X-Forwarded-For`` header here, as it is
itself client-spoofable. Authenticated traffic is unaffected (keyed on the verified tenant).
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
from delivery.api.deps import extract_tenant, trusted_client_ip

# Paths that are never rate-limited (infra + onboarding, which has no tenant yet; provider webhooks,
# which are signature-authenticated and carry no tenant claim). /v1/billing/checkout is NOT exempt —
# it is an authenticated tenant call and is rate-limited normally.
_EXEMPT = ("/health", "/readyz", "/docs", "/redoc", "/openapi.json", "/v1/signup", "/v1/billing/webhook")

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

    def _limit_for(self, request: Request) -> tuple[str, int, TenantId] | None:
        """Return (counter_key, limit, tenant) to enforce, or None to skip (fail-open).

        ``counter_key`` is what the fixed window is bucketed by: the **verified** tenant when the
        request is authenticated, else the client IP (never the spoofable routing tenant). ``tenant``
        is the resolved tenant used for the tier-limit lookup and the metered daily-quota check.
        """
        if any(request.url.path == p or request.url.path.startswith(p + "/") for p in _EXEMPT):
            return None
        engine = self._engine(request)
        if engine is None:
            return None

        principal = getattr(request.state, "principal", None)
        if principal is not None:
            # Authenticated: key on the cryptographically-verified tenant.
            tenant: TenantId = principal.tenant_id
            counter_key = f"tenant:{tenant}"
        else:
            # Unauthenticated (auth disabled): the routing tenant is unverified, so it must NOT be the
            # counter key. Bucket by client IP instead; use the routing tenant only to size the limit.
            tenant_or_none = extract_tenant(request)
            if tenant_or_none is None:
                return None
            tenant = tenant_or_none
            # Real client IP via the trusted edge header (falls back to the immediate peer). Behind
            # the Cloudflare Worker this is the originating client, not the Worker, so unauthenticated
            # buckets no longer collapse to a single shared (proxy) IP.
            ip = trusted_client_ip(request)
            if ip is None:
                return None  # no IP to key on → fail open
            counter_key = f"ip:{ip}"

        try:
            limit = engine.rate_limit_for(tenant)
        except EntitlementError:
            return None  # unprovisioned / inactive: routing & auth will reject downstream
        if limit < 0:
            return None  # unbounded
        return counter_key, limit, tenant

    def _check(self, key: str, limit: int) -> bool:
        """Increment the window counter for ``key``; return True if still within ``limit``."""
        now = time.monotonic()
        with self._lock:
            start, count = self._counters.get(key, (now, 0))
            if now - start >= _WINDOW_SECONDS:
                start, count = now, 0
            count += 1
            self._counters[key] = (start, count)
            return count <= limit

    def _daily_quota_exceeded(self, request: Request, tenant: TenantId) -> int | None:
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
            engine.assert_within_quota(tenant, actions_today=meter.actions_today(str(tenant)))
        except QuotaExceededError as exc:
            return int(exc.detail.get("limit")) if exc.detail else 0
        except EntitlementError:
            return None
        return None

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        target = self._limit_for(request)
        if target is None:
            return await call_next(request)
        counter_key, limit, tenant = target
        if not self._check(counter_key, limit):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(_WINDOW_SECONDS)},
                content={
                    "error": f"Rate limit exceeded ({limit}/min for this tier)",
                    "code": "RATE_LIMITED",
                    "detail": {"tenant": str(tenant), "limit_per_min": limit},
                },
            )
        daily_limit = self._daily_quota_exceeded(request, tenant)
        if daily_limit is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "error": f"Daily action quota exceeded ({daily_limit}/day for this tier)",
                    "code": "QUOTA_EXCEEDED",
                    "detail": {"tenant": str(tenant), "limit_per_day": daily_limit},
                },
            )
        return await call_next(request)
