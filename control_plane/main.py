"""
ALIS Control Plane — S2

Standalone FastAPI service that manages tenant lifecycle for the ALIS SaaS platform.

Responsibilities
----------------
- Provision per-tenant PostgreSQL databases + run migrations
- Serve /internal/tenants/... queries from TenantRegistry (S1)
- Expose /admin/tenants/... CRUD for superadmin portal / CLI scripts
- Trigger Redis cache invalidation on tenant config changes

Run with:
    uvicorn control_plane.main:app --host 0.0.0.0 --port 8001 --reload

In production, deploy behind Nginx with TLS + separate from data plane port.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialise control plane DB pool and schema on startup."""
    from control_plane import db as cp_db
    cp_db.init_db_pool()
    cp_db.init_schema()
    logger.info("Control plane started.")
    yield
    cp_db.close_db_pool()
    logger.info("Control plane shut down.")


def create_app() -> FastAPI:
    from control_plane.settings import settings

    app = FastAPI(
        title="ALIS Control Plane",
        description="Tenant lifecycle management for the ALIS SaaS platform.",
        version="1.0.0",
        lifespan=_lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # CORS — tight in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Internal-Token"],
    )

    # Routers
    from control_plane.router import router
    app.include_router(router)

    # Health probe — used by load balancers
    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": "control-plane"}

    # Generic error handler — never leak internal details
    @app.exception_handler(Exception)
    async def _generic_handler(request, exc):
        logger.exception("Control plane unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    return app


app = create_app()
