from __future__ import annotations

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


import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
import uuid  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sentry (optional — graceful if sentry-sdk not installed or DSN not set)
# ---------------------------------------------------------------------------
def _init_sentry() -> None:
    """Initialise Sentry SDK if DSN is configured and sdk is installed."""
    try:
        from server.core.settings import settings as _s

        if not _s.sentry_enabled:
            return
        import logging as _logging

        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=_s.sentry_dsn,
            environment=_s.app_env,
            release=f"alis@{0.1}",
            traces_sample_rate=_s.sentry_traces_sample_rate,
            profiles_sample_rate=_s.sentry_profiles_sample_rate,
            integrations=[
                FastApiIntegration(),
                AsyncioIntegration(),
                LoggingIntegration(
                    level=_logging.WARNING,  # capture WARNING+ as breadcrumbs
                    event_level=_logging.ERROR,  # send ERROR+ as Sentry events
                ),
            ],
            # Never send PII (student data) to Sentry
            send_default_pii=False,
            # Ignore noisy client-facing 4xx errors
            ignore_errors=[
                "fastapi.exceptions.RequestValidationError",
                "starlette.exceptions.HTTPException",
            ],
        )
        logger.info(
            "Sentry initialised (env=%s, sample_rate=%.2f)",
            _s.app_env,
            _s.sentry_traces_sample_rate,
        )
    except ImportError:
        logger.debug("sentry-sdk not installed — error tracking disabled")
    except Exception as exc:
        logger.warning("Sentry init failed: %s", exc)


_init_sentry()

# ---------------------------------------------------------------------------
# Prometheus metrics (optional — graceful if prometheus_client not installed)
# ---------------------------------------------------------------------------
from server.core.metrics import (  # noqa: E402
    ACTIVE_REQUESTS as _ACTIVE_REQUESTS,
)
from server.core.metrics import (  # noqa: E402
    AVAILABLE as _PROMETHEUS_AVAILABLE,
)
from server.core.metrics import (  # noqa: E402
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from server.core.metrics import (  # noqa: E402
    HTTP_REQUEST_DURATION as _HTTP_REQUEST_DURATION,
)
from server.core.metrics import (  # noqa: E402
    HTTP_REQUESTS_TOTAL as _HTTP_REQUESTS_TOTAL,
)

if not _PROMETHEUS_AVAILABLE:
    logger.warning("prometheus_client not installed — metrics endpoint will return 501")

from server.api.academics_router import router as academics_router  # E05  # noqa: E402
from server.api.admin_router import (  # noqa: E402
    router as admin_router,
)  # P21 Admin (shadow mode, migration, webhooks)
from server.api.admissions_router import (  # noqa: E402
    router as admissions_router,
)  # E04  # noqa: E402
from server.api.ai_providers_router import (  # noqa: E402
    router as ai_providers_router,
)  # AI Provider extensibility
from server.api.alumni_router import router as alumni_router  # E12  # noqa: E402
from server.api.approvals_router import router as approvals_router  # noqa: E402
from server.api.audit_router import router as audit_router  # noqa: E402
from server.api.auth_router import router as auth_router  # noqa: E402
from server.api.communication_router import (  # noqa: E402
    router as communication_router,
)  # E10  # noqa: E402
from server.api.consent_router import router as consent_router  # E21 DPDP  # noqa: E402
from server.api.convocation_router import (  # noqa: E402
    router as convocation_router,
)  # E18 Convocation
from server.api.examinations_router import (  # noqa: E402
    router as examinations_router,
)  # E06  # noqa: E402
from server.api.feature_flags_router import (  # noqa: E402
    router as feature_flags_router,
)  # §12 Feature Flags
from server.api.finance_router import router as finance_router  # E07  # noqa: E402
from server.api.gateway_router import router as gateway_router  # noqa: E402
from server.api.hr_router import router as hr_router  # E08  # noqa: E402
from server.api.intake_router import (  # noqa: E402
    router as intake_router,
)  # E04-S14/S15  # noqa: E402
from server.api.integrations_router import (  # noqa: E402
    router as integrations_router,
)  # P14  # noqa: E402
from server.api.learning_router import (  # noqa: E402
    router as learning_router,
)  # P40 In-house LMS  # noqa: E402
from server.api.organizations_router import router as organizations_router  # noqa: E402
from server.api.phd_router import (  # noqa: E402
    router as phd_router,
)  # E15 PhD / Doctoral  # noqa: E402
from server.api.process_engine_router import (  # noqa: E402
    router as process_engine_router,
)  # E13  # noqa: E402
from server.api.regulatory_router import (  # noqa: E402
    router as regulatory_router,
)  # E14 Regulatory  # noqa: E402
from server.api.reporting_router import router as reporting_router  # E11  # noqa: E402
from server.api.roles_router import router as roles_router  # noqa: E402
from server.api.student_services_router import (  # noqa: E402
    router as student_services_router,
)  # E09  # noqa: E402
from server.api.users_router import router as users_router  # noqa: E402
from server.api.wifi_attendance_router import (  # noqa: E402
    router as wifi_attendance_router,
)  # P29 WiFi Attendance
from server.api.workflows_router import router as workflows_router  # noqa: E402
from server.consent.consent_middleware import (  # noqa: E402
    ConsentMiddleware,
)  # E21 DPDP  # noqa: E402
from server.core.api_versioning import (  # noqa: E402
    DeprecationMiddleware,
    get_api_v2_router,
)  # §29 API versioning
from server.core.error_handlers import register_exception_handlers  # noqa: E402
from server.core.security import SubdomainTenantMiddleware  # noqa: E402
from server.core.shadow_mode_middleware import (  # noqa: E402
    ShadowModeMiddleware,
)  # P21 Shadow mode suppression
from server.tools import register_all_tools  # noqa: E402


class SecurityHeadersMiddleware:
    """Adds secure HTTP response headers to every response (raw ASGI — preserves ContextVars)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (
                        b"permissions-policy",
                        b"geolocation=(), microphone=(), camera=()",
                    ),
                ]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class MetricsMiddleware:
    """Raw ASGI middleware: instruments HTTP requests with Prometheus metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _PROMETHEUS_AVAILABLE:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        # Collapse path params to avoid high-cardinality labels
        label_path = path.split("?")[0]

        _ACTIVE_REQUESTS.inc()
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            _ACTIVE_REQUESTS.dec()
            _HTTP_REQUESTS_TOTAL.labels(
                method=method, path=label_path, status_code=str(status_code)
            ).inc()
            _HTTP_REQUEST_DURATION.labels(method=method, path=label_path).observe(
                duration
            )


class RequestLoggingMiddleware:
    """
    Raw ASGI middleware: structured JSON request logging.

    Optimization: Skip detailed logging for lightweight probes (/health, /ready, /metrics).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Short-circuit: skip logging for health/readiness probes
        from server.core.perf import is_lightweight_request

        path = scope.get("path", "")
        method = scope.get("method", "")
        if is_lightweight_request(method, path):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        # Store request_id in scope so downstream can access it
        scope["alis_request_id"] = request_id

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                # Inject X-Request-ID response header
                resp_headers = list(message.get("headers", []))
                resp_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": resp_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.perf_counter() - start) * 1000
        path = scope.get("path", "")
        method = scope.get("method", "")

        # tenant_id and user_id are set by TenantMiddleware on scope["state"]
        state = scope.get("state", {})
        tenant_id = (
            getattr(state, "tenant_id", None) if hasattr(state, "tenant_id") else None
        )
        user_id = getattr(state, "user_id", None) if hasattr(state, "user_id") else None

        log_record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            + f".{int((time.time() % 1) * 1000):03d}Z",
            "level": "info",
            "event": "http_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "tenant_id": tenant_id,
            "request_id": request_id,
            "user_id": user_id,
        }
        logger.info(json.dumps(log_record))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """P0-1: Init asyncpg pool on startup, close on shutdown. Warm caches."""
    from server.db_service import close_pool, init_pool

    await init_pool()
    logger.info("ALIS startup: asyncpg pool ready.")

    # Warm Vault cache for non-critical secrets (non-blocking)
    try:
        from server.core.perf import warm_vault_cache

        await warm_vault_cache()
    except Exception as e:
        logger.warning("Vault warm-up skipped: %s", e)

    yield
    await close_pool()
    logger.info("ALIS shutdown: asyncpg pool closed.")


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
        lifespan=_lifespan,
        # Disable interactive docs in production — never expose schema to the public
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # --- Middleware Stack ---
    #
    # IMPORTANT: Starlette executes middleware in REVERSE add order.
    # The LAST add_middleware call is the OUTERMOST layer (first to execute).
    #
    # Desired execution order (outermost → innermost):
    #   1. Metrics (outermost — captures all requests including errors)
    #   2. RequestLogging (needs request_id, can log without tenant)
    #   3. SecurityHeaders (cheap — just appends headers on response)
    #   4. SubdomainTenant (Layer 4 Invariant — sets ContextVar for tenant)
    #   5. ShadowMode (needs tenant_id from step 4 — P21)
    #   6. Consent (needs tenant_id from step 4 — E21 DPDP, innermost)
    #
    # So we add in reverse: Consent first, Metrics last.

    # Innermost (closest to route handler)
    app.add_middleware(ConsentMiddleware)
    app.add_middleware(ShadowModeMiddleware)
    app.add_middleware(SubdomainTenantMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    # Outermost (first to execute on request, last on response)
    app.add_middleware(MetricsMiddleware)

    # --- CORS ---
    # In production restrict to explicit methods/headers; dev keeps wildcard for convenience.
    cors_methods = (
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        if settings.is_production
        else ["*"]
    )
    cors_headers = (
        ["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Tenant-ID"]
        if settings.is_production
        else ["*"]
    )
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
    from server.admissions.event_handlers import (
        register_all as register_admissions_handlers,
    )

    register_admissions_handlers()

    # --- E05 Event Handlers (M2 academics) ---
    from server.academics.event_handlers import (
        register_all as register_academics_handlers,
    )

    register_academics_handlers()

    # --- E06 Event Handlers (M3 examinations) ---
    from server.examinations.event_handlers import (
        register_all as register_examinations_handlers,
    )

    register_examinations_handlers()

    # --- E07 Event Handlers (M4 finance) ---
    from server.finance.event_handlers import register_all as register_finance_handlers

    register_finance_handlers()

    # --- E08 Event Handlers (M5 HR & staff) ---
    from server.hr.event_handlers import register_all as register_hr_handlers

    register_hr_handlers()

    # --- E09 Event Handlers (M6 student services) ---
    from server.student_services.event_handlers import (
        register_all as register_student_services_handlers,
    )

    register_student_services_handlers()

    # --- E10 Event Handlers (M7 communication hub) ---
    from server.communication.event_handlers import (
        register_all as register_communication_handlers,
    )

    register_communication_handlers()

    # --- E12 Event Handlers (M9 alumni & placement) ---
    from server.alumni.event_handlers import register_all as register_alumni_handlers

    register_alumni_handlers()

    # --- E13 Event Handlers (Dynamic Process Engine) ---
    from server.process_engine.event_handlers import (
        register_all as register_process_engine_handlers,
    )

    register_process_engine_handlers()

    # --- E14 Event Handlers (Regulatory & Accreditation) ---
    from server.regulatory.event_handlers import (
        register_all as register_regulatory_handlers,
    )

    register_regulatory_handlers()

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
    app.include_router(admissions_router)  # E04
    app.include_router(intake_router)  # E04-S14/S15
    app.include_router(academics_router)  # E05
    app.include_router(examinations_router)  # E06
    app.include_router(finance_router)  # E07
    app.include_router(hr_router)  # E08
    app.include_router(student_services_router)  # E09
    app.include_router(communication_router)  # E10
    app.include_router(reporting_router)  # E11
    app.include_router(alumni_router)  # E12
    app.include_router(process_engine_router)  # E13
    app.include_router(integrations_router)  # P14
    app.include_router(feature_flags_router)  # §12 Feature Flags
    app.include_router(regulatory_router)  # E14 Regulatory
    app.include_router(consent_router)  # E21 DPDP
    app.include_router(admin_router)  # P21 Admin (shadow mode, migration, webhooks)
    app.include_router(phd_router)  # E15 PhD / Doctoral
    app.include_router(convocation_router)  # E18 Convocation
    app.include_router(wifi_attendance_router)  # P29 WiFi Attendance
    app.include_router(learning_router)  # P40 In-house LMS
    app.include_router(ai_providers_router)  # AI Provider extensibility

    # --- API v2 mount (§29 versioning) ---
    api_v2_router = get_api_v2_router()
    app.include_router(api_v2_router)

    # --- API Deprecation Headers (v1 Sunset) ---
    app.add_middleware(DeprecationMiddleware)

    # --- Prometheus Metrics ---
    @app.get("/metrics", tags=["system"], include_in_schema=False)
    async def metrics():
        """Prometheus metrics scrape endpoint (internal only — nginx blocks external access)."""
        if not _PROMETHEUS_AVAILABLE:
            return JSONResponse(
                status_code=501, content={"error": "prometheus_client not installed"}
            )
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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
            from server.db_service import execute_system_query_async

            await execute_system_query_async("SELECT 1")
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

        # --- Vault ---
        try:
            from server.core.vault_client import get_vault_client

            vault = get_vault_client()
            if not vault._is_available():
                raise RuntimeError(
                    "Vault health check failed — service is unreachable."
                )
            checks["vault"] = "ok"
        except Exception as e:
            # Vault unavailable is warn-only in non-production (no exam PDFs)
            from server.core.settings import settings as _settings

            if _settings.is_production:
                checks["vault"] = f"error: {e}"
                healthy = False
            else:
                checks["vault"] = f"warn: {e}"

        status_code = 200 if healthy else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if healthy else "degraded", "checks": checks},
        )

    return app


app = create_app()
