"""Request logging + correlation IDs (ADR-0011, WS-D).

`RequestLoggingMiddleware` is always on (it changes no behavior). For every request it:

  - assigns a correlation id (honoring an inbound ``X-Request-ID``, else a fresh uuid4) and exposes
    it on ``request.state.request_id`` and the ``X-Request-ID`` response header;
  - emits one structured access-log record on completion — method, path, status, duration, the
    routing tenant, and the request id.

This is the audit/compliance edge the metering and billing workstreams (WS-C) build on: the access
log is the durable record of *who called what, when*. Keeping it as a thin middleware means every
route — present and future — is covered without per-handler wiring.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from delivery.api.deps import extract_tenant

log = logging.getLogger("quaicu.api.access")

_REQUEST_ID_HEADER = "x-request-id"

# Paths whose traffic is not metered against a tenant's daily usage (infra + onboarding/webhooks,
# which either have no tenant or are provider-authenticated).
_UNMETERED = ("/health", "/docs", "/redoc", "/openapi.json", "/v1/signup", "/v1/admin", "/v1/billing")


def _is_metered(path: str) -> bool:
    if not (path == "/v1" or path.startswith("/v1/")):
        return False
    return not any(path == p or path.startswith(p + "/") for p in _UNMETERED)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id and emit a structured access log line per request."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        # Best-effort tenant for the log line; never let it break the request.
        try:
            tenant = extract_tenant(request)
        except Exception:  # noqa: BLE001 — observability must not affect request handling
            tenant = None

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            # Meter successful governed requests against the tenant's daily usage (WS-C). Best-effort:
            # a metering failure must never affect the response.
            meter = getattr(request.app.state, "usage_meter", None)
            if meter is not None and tenant is not None and status_code < 400 and _is_metered(request.url.path):
                try:
                    meter.record(tenant)
                except Exception:  # noqa: BLE001 — observability must not affect request handling
                    pass
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            log.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                status_code,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "tenant": str(tenant) if tenant is not None else None,
                },
            )
