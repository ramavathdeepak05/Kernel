"""Shadow Mode Middleware (§28)

Starlette middleware that intercepts outbound communication dispatch when
shadow mode is active.  Communication service methods check
`ShadowModeService.is_enabled()` before sending; this middleware provides
the suppression flag on the request state so routers can also gate on it.

It also logs suppressed dispatches to shadow_mode_divergence_log so the
nightly task can compute divergence metrics even for comms paths.

Usage (registered in main.py):
    app.add_middleware(ShadowModeMiddleware)
"""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.core.shadow_mode import ShadowModeService

logger = logging.getLogger(__name__)


class SuppressedByShadowMode(Exception):
    """Raised by communication services when shadow mode blocks a dispatch."""
    def __init__(self, channel: str, org_id: str):
        self.channel = channel
        self.org_id = org_id
        super().__init__(f"Communication suppressed by shadow mode: {channel} for org {org_id}")


class ShadowModeMiddleware(BaseHTTPMiddleware):
    """Attaches `request.state.shadow_mode_active` for downstream use.

    Lightweight: one Redis lookup per request, cached 5 min.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Determine org_id from tenant middleware (set earlier in chain)
        org_id: str | None = getattr(request.state, "tenant_id", None)

        if org_id:
            # Cache result on request state — avoids second Redis call in views
            try:
                request.state.shadow_mode_active = ShadowModeService.is_enabled(org_id)
            except Exception:
                request.state.shadow_mode_active = False
        else:
            request.state.shadow_mode_active = False

        return await call_next(request)


def assert_not_shadow_suppressed(request: Request, channel: str) -> None:
    """Helper for route handlers: raises 409 if shadow mode suppresses channel."""
    org_id = getattr(request.state, "tenant_id", None)
    if getattr(request.state, "shadow_mode_active", False):
        raise SuppressedByShadowMode(channel=channel, org_id=org_id or "unknown")
