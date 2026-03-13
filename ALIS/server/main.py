"""
ALIS FastAPI Application Entrypoint — E03-S01

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Orchestration (FastAPI)

This is the single application entrypoint for the ALIS server.
It mounts all API routers and registers exception handlers.

Run with:
    uvicorn server.main:app --reload --host 0.0.0.0 --port 8000

Hard Constraints:
- No cloud LLM dependencies
- All AI invocations go through the AI Gateway
- All requests are tenant-aware
"""

import logging
import time
import urllib.request

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

from server.core.error_handlers import register_exception_handlers
from server.api.auth_router import router as auth_router
from server.api.users_router import router as users_router
from server.api.roles_router import router as roles_router
from server.api.organizations_router import router as organizations_router
from server.api.approvals_router import router as approvals_router
from server.api.audit_router import router as audit_router
from server.api.gateway_router import router as gateway_router
from server.api.workflows_router import router as workflows_router
from server.api.admissions_router import router as admissions_router  # E04
from server.api.intake_router import router as intake_router           # E04-S14/S15
from server.api.academics_router import router as academics_router         # E05
from server.api.examinations_router import router as examinations_router   # E06
from server.api.finance_router import router as finance_router             # E07
from server.api.hr_router import router as hr_router                       # E08
from server.api.student_services_router import router as student_services_router  # E09
from server.api.communication_router import router as communication_router         # E10
from server.api.reporting_router import router as reporting_router                 # E11
from server.api.alumni_router import router as alumni_router                       # E12
from server.api.process_engine_router import router as process_engine_router       # E13
from server.api.integrations_router import router as integrations_router           # P14
from server.tools import register_all_tools


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds secure HTTP response headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


def create_app() -> FastAPI:
    """
    Application factory.

    Creates and configures the FastAPI app with all routers,
    middleware, and exception handlers.
    """
    from server.core.settings import settings

    app = FastAPI(
        title="ALIS — Agentic Learning & Institutional System",
        description=(
            "Centralized platform API for ALIS. "
            "All AI invocations route through the AI Gateway (E03-S01)."
        ),
        version="0.1.0",
        # Disable interactive docs in production — never expose schema to the public
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # --- Security Headers ---
    app.add_middleware(SecurityHeadersMiddleware)

    # --- CORS ---
    # In production restrict to explicit methods/headers; dev keeps wildcard for convenience.
    cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] if settings.is_production else ["*"]
    cors_headers = ["Authorization", "Content-Type", "Accept", "X-Request-ID"] if settings.is_production else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=cors_methods,
        allow_headers=cors_headers,
    )

    # --- Tool Registry (E03-S05) ---
    register_all_tools()

    # --- E04 Event Handlers (M1 autonomous pipeline) ---
    from server.admissions.event_handlers import register_all as register_admissions_handlers
    register_admissions_handlers()

    # --- E05 Event Handlers (M2 academics) ---
    from server.academics.event_handlers import register_all as register_academics_handlers
    register_academics_handlers()

    # --- E06 Event Handlers (M3 examinations) ---
    from server.examinations.event_handlers import register_all as register_examinations_handlers
    register_examinations_handlers()

    # --- E07 Event Handlers (M4 finance) ---
    from server.finance.event_handlers import register_all as register_finance_handlers
    register_finance_handlers()

    # --- E08 Event Handlers (M5 HR & staff) ---
    from server.hr.event_handlers import register_all as register_hr_handlers
    register_hr_handlers()

    # --- E09 Event Handlers (M6 student services) ---
    from server.student_services.event_handlers import register_all as register_student_services_handlers
    register_student_services_handlers()

    # --- E10 Event Handlers (M7 communication hub) ---
    from server.communication.event_handlers import register_all as register_communication_handlers
    register_communication_handlers()

    # --- E12 Event Handlers (M9 alumni & placement) ---
    from server.alumni.event_handlers import register_all as register_alumni_handlers
    register_alumni_handlers()

    # --- E13 Event Handlers (Dynamic Process Engine) ---
    from server.process_engine.event_handlers import register_all as register_process_engine_handlers
    register_process_engine_handlers()

    # --- Exception Handlers ---
    register_exception_handlers(app)

    # --- Routers ---
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(organizations_router)
    app.include_router(approvals_router)
    app.include_router(audit_router)
    app.include_router(gateway_router)
    app.include_router(workflows_router)
    app.include_router(admissions_router)   # E04
    app.include_router(intake_router)       # E04-S14/S15
    app.include_router(academics_router)      # E05
    app.include_router(examinations_router)  # E06
    app.include_router(finance_router)       # E07
    app.include_router(hr_router)            # E08
    app.include_router(student_services_router)  # E09
    app.include_router(communication_router)     # E10
    app.include_router(reporting_router)         # E11
    app.include_router(alumni_router)            # E12
    app.include_router(process_engine_router)    # E13
    app.include_router(integrations_router)      # P14

    # --- Health & Readiness ---
    @app.get("/health", tags=["system"])
    async def health():
        """Liveness probe — confirms the process is running."""
        return {"status": "ok", "service": "ALIS", "version": app.version}

    @app.get("/ready", tags=["system"])
    async def ready():
        """
        Readiness probe — confirms all dependencies are reachable.
        Returns 200 only when all checks pass. Returns 503 otherwise.
        Used by nginx/load balancer before routing traffic.
        """
        from server.core.settings import settings
        checks: dict = {}
        healthy = True

        # --- PostgreSQL ---
        try:
            from server.db_service import execute_system_query
            execute_system_query("SELECT 1")
            checks["postgres"] = "ok"
        except Exception as e:
            checks["postgres"] = f"error: {e}"
            healthy = False

        # --- Redis ---
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            healthy = False

        # --- Ollama ---
        try:
            req = urllib.request.Request(
                f"{settings.ollama_base_url}/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3):
                pass
            checks["ollama"] = "ok"
        except Exception as e:
            checks["ollama"] = f"error: {e}"
            healthy = False

        # --- MinIO ---
        try:
            from minio import Minio
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            client.list_buckets()
            checks["minio"] = "ok"
        except Exception as e:
            checks["minio"] = f"error: {e}"
            healthy = False

        status_code = 200 if healthy else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if healthy else "degraded", "checks": checks},
        )

    return app


app = create_app()
