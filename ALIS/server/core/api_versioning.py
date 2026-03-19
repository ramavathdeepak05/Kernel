"""API Versioning Strategy (§29)

VersionedRouter helper — wraps APIRouter with version prefix.
Deprecation header middleware — adds 'Sunset' header for v1 endpoints.
Both v1 and v2 prefixes registered on the FastAPI app.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse


class VersionedRouter:
    """Wraps FastAPI APIRouter with a versioned prefix.

    Provides two pre-built routers (v1 and v2) that share the same logical
    resource path but are mounted under separate version prefixes.  Callers
    register routes on `router.v1` or `router.v2`; both routers are then
    included in the FastAPI app independently.

    Usage::

        router = VersionedRouter("v2", prefix="/phd", tags=["PhD"])

        @router.v1.get("/scholars")
        async def list_scholars_v1(): ...   # → /api/v1/phd/scholars

        @router.v2.get("/scholars")
        async def list_scholars_v2(): ...   # → /api/v2/phd/scholars

    The ``current_version`` attribute records the version considered stable,
    useful for generating OpenAPI descriptions or Deprecation hints.
    """

    def __init__(self, current_version: str, prefix: str, tags: List[str]) -> None:
        self.current_version = current_version
        self.v1 = APIRouter(prefix=f"/api/v1{prefix}", tags=tags)
        self.v2 = APIRouter(prefix=f"/api/v2{prefix}", tags=tags)


class DeprecationMiddleware:
    """Adds Sunset/Deprecation headers to v1 API responses.

    Sunset header tells API consumers the scheduled date for v1 removal.
    See RFC 8594.

    All ``/api/v1/`` responses receive three additional headers:

    * ``Sunset`` — ISO 8601 date after which the v1 API will be decommissioned.
    * ``Deprecation`` — literal ``"true"`` to signal active deprecation.
    * ``Link`` — points callers to the ``/api/v2/`` equivalent for discoverability.

    The sunset date is read from the ``API_V1_SUNSET_DATE`` environment variable
    and defaults to ``"2027-01-01"`` if not set.
    """

    def __init__(self, app: Any, sunset_date: str = "2027-01-01") -> None:
        self.app = app
        # Prefer env-override so ops can adjust without a code redeploy.
        self.sunset_date: str = os.environ.get("API_V1_SUNSET_DATE", sunset_date)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        is_v1 = path.startswith("/api/v1/")

        async def send_with_deprecation(message: Any) -> None:
            if is_v1 and message["type"] == "http.response.start":
                # Build the v2 equivalent link by replacing the version segment.
                v2_path = path.replace("/api/v1/", "/api/v2/", 1)
                headers: List[tuple] = list(message.get("headers", []))
                headers += [
                    (b"sunset", self.sunset_date.encode()),
                    (b"deprecation", b"true"),
                    (b"link", f'<{v2_path}>; rel="successor-version"'.encode()),
                ]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_deprecation)


def get_api_v2_router() -> APIRouter:
    """Return the base v2 API router.

    Includes a health-check endpoint at ``GET /api/v2/health`` so tooling
    can confirm the v2 surface is reachable before routing traffic to it.
    Additional v2 routers should be included on the FastAPI app directly
    using their own ``/api/v2/...`` prefixes.

    Returns:
        Configured APIRouter ready to be passed to ``app.include_router()``.
    """
    v2_router = APIRouter(prefix="/api/v2", tags=["v2"])

    @v2_router.get("/health", summary="v2 API health probe")
    async def v2_health() -> Dict[str, str]:
        """Confirm the v2 API surface is reachable."""
        return {"status": "ok", "version": "v2", "note": "v2 API — stable"}

    return v2_router
