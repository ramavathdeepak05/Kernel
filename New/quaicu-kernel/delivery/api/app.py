"""FastAPI application factory for the QUAICU Kernel REST API.

Usage::

    from delivery.api.app import create_app
    from delivery.sdk.kernel import Kernel

    kernel = Kernel.from_parts(tenant="ciro-bank", policy=..., ...)
    app = create_app(kernel)

Or from config::

    kernel = Kernel.from_config("kernel.toml")
    app = create_app(kernel)

The app stores the ``Kernel`` instance on ``app.state.kernel`` so routes can
retrieve it via ``request.app.state.kernel`` without global state.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.errors import (
    LifecycleDeniedError,
    LifecycleHaltedError,
    QUAICUError,
    SubjectErasedError,
    TenantIsolationError,
)
from core.account import AccountEngine
from core.entitlements import EntitlementStore
from core.gateway.budget import InMemoryBudgetTracker
from delivery.api.auth import ApiKeyAuthMiddleware
from delivery.api.middleware import GovernanceMiddleware
from delivery.api.observability import RequestLoggingMiddleware
from delivery.api.ratelimit import RateLimitMiddleware
from delivery.api.routes.actions import router as actions_router
from delivery.api.routes.approvals import router as approvals_router
from delivery.api.routes.authorize import router as authorize_router
from delivery.api.routes.billing import router as billing_router
from delivery.api.routes.dashboard import router as dashboard_router
from delivery.api.routes.entitlements import router as entitlements_router
from delivery.api.routes.inference import router as inference_router
from delivery.api.routes.ai_gateway import router as ai_gateway_router
from delivery.api.routes.admin import router as admin_router
from delivery.api.routes.erasure import router as erasure_router
from delivery.api.routes.ledger import router as ledger_router
from delivery.api.routes.policies import router as policies_router
from delivery.api.routes.policy_packs import router as policy_packs_router
from delivery.api.routes.auth import router as auth_router
from delivery.api.routes.consultation import router as consultation_router
from delivery.api.routes.keys import router as keys_router
from delivery.api.routes.members import router as members_router
from delivery.api.routes.scim import router as scim_router
from delivery.api.routes.signup import router as signup_router
from delivery.sdk.kernel import Kernel
from delivery.sdk.provider import TieredKernelProvider


def create_app(
    kernel: Kernel | None = None,
    *,
    provider: "TieredKernelProvider | None" = None,
    account_engine: "AccountEngine | None" = None,
    entitlement_store: "EntitlementStore | None" = None,
    admin_token: str | None = None,
    billing_adapters: "dict[str, object] | None" = None,
    billing_engine: "object | None" = None,
    email_sender: "object | None" = None,
    signup_payment: "object | None" = None,
    consultation: "dict | None" = None,
    coupon_book: "object | None" = None,
    usage_meter: "object | None" = None,
    erasure_engine: "object | None" = None,
    enforce_paths: list[tuple[str, str]] | None = None,
    cors_origins: list[str] | None = None,
    require_api_key: bool = False,
    rate_limit: bool = True,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Provide exactly one of:
      - ``kernel``: a single wired ``Kernel`` (dedicated / legacy single-tenant deployment), or
      - ``provider``: a ``TieredKernelProvider`` for the shared SaaS plane, which routes each request
        to the tenant's tier kernel (see ``delivery/api/deps.py``).

    Args:
        kernel: A fully wired ``Kernel`` instance (single-kernel mode).
        provider: A tiered kernel provider (shared-plane mode).
        enforce_paths: Optional reference-PEP enforcement-point path globs.
        cors_origins: Browser origins allowed to call the API (the operator console runs on a
            separate origin). Defaults to the Vite dev server (``http://localhost:5173``).
        require_api_key: When True, protected ``/v1/*`` routes require a valid, tenant-matched API
            key (`ApiKeyAuthMiddleware`); requires ``account_engine``. Off by default so IdP-token
            and single-kernel deployments are unaffected.
        rate_limit: When True (default), enforce per-tenant tier rate limits at the edge. No-ops when
            no entitlement source (provider or ``entitlement_store``) is wired.

    Returns:
        A configured ``FastAPI`` app ready to serve.
    """
    if (kernel is None) == (provider is None):
        raise ValueError("create_app requires exactly one of `kernel` or `provider`.")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Initialise async resources (e.g. hydrate the durable policy store) before serving.
        target = provider if provider is not None else kernel
        await target.startup()
        # Repopulate the entitlement cache from its durable repository (if one is wired) so a
        # restarted kernel resolves the same tiers a billing webhook last persisted. No-op for an
        # in-memory store, so every existing deployment is unaffected.
        if entitlement_store is not None:
            await entitlement_store.hydrate()
        # Repopulate the account/API-key cache from its durable store (if wired) so self-serve signups
        # survive a restart / scale-out. Sync (psycopg2) + off the hot path; no-op when in-memory.
        if account_engine is not None and hasattr(account_engine, "hydrate"):
            account_engine.hydrate()
        # Startup hydration done → /readyz reports ready. Flipped back off during shutdown so a
        # draining instance fails readiness while still answering liveness.
        _app.state.ready = True
        try:
            yield
        finally:
            _app.state.ready = False
            await target.shutdown()

    app = FastAPI(
        title="QUAICU Governance Kernel",
        version="0.1.0",
        description=(
            "Sovereign-tier AI governance kernel. "
            "All actions are governed: evaluate → gate → execute → seal → emit."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Attach the request-resolution target to app state (no globals). Exactly one is non-None;
    # routes resolve the serving kernel via delivery/api/deps.get_kernel.
    app.state.kernel = kernel
    app.state.provider = provider
    # Readiness gate: false until lifespan startup hydration completes (see lifespan above). /readyz
    # reads this; /health (liveness) ignores it.
    app.state.ready = False
    # Per-tenant token budget for the BYO AI-gateway passthrough (W6-2). Default unlimited; an optional
    # default cap (QUAICU_AI_DEFAULT_MAX_TOKENS) is applied per-tenant lazily by the route.
    app.state.ai_budget = InMemoryBudgetTracker()
    # Control-plane singletons (signup / admin / billing). Routes 503 when their dependency is absent.
    app.state.account_engine = account_engine
    app.state.entitlement_store = entitlement_store
    app.state.admin_token = admin_token
    # Billing (WS-C): provider adapters keyed by name + the apply engine; usage meter for metering.
    app.state.billing_adapters = billing_adapters or {}
    app.state.billing_engine = billing_engine
    # Transactional email (verified-signup OTP / recovery). None → /v1/signup/start emails nothing and
    # the legacy one-step /v1/signup stays open; a wired sender makes the OTP flow mandatory.
    app.state.email_sender = email_sender
    # Signup-fee gateway (₹2 at signup). None → no fee; /v1/signup/verify provisions on OTP directly.
    app.state.signup_payment = signup_payment
    # Business/Enterprise consultation config ({amount_paise, notify_email}). Empty → defaults apply.
    app.state.consultation = consultation or {}
    # Discount coupons applied to the signup fee / consultation before the Razorpay order is created.
    app.state.coupon_book = coupon_book
    app.state.usage_meter = usage_meter
    # Erasure (WS-G): crypto-shredding engine for the GDPR/DPDP right-to-erasure routes.
    app.state.erasure_engine = erasure_engine

    # Routers
    app.include_router(actions_router)
    app.include_router(authorize_router)
    app.include_router(inference_router)
    app.include_router(ai_gateway_router)
    app.include_router(ledger_router)
    app.include_router(policies_router)
    app.include_router(policy_packs_router)
    app.include_router(dashboard_router)
    app.include_router(entitlements_router)
    app.include_router(approvals_router)
    app.include_router(signup_router)
    app.include_router(auth_router)
    app.include_router(keys_router)
    app.include_router(members_router)
    app.include_router(scim_router)
    app.include_router(consultation_router)
    app.include_router(admin_router)
    app.include_router(billing_router)
    app.include_router(erasure_router)

    # ── Middleware stack ──────────────────────────────────────────────────────
    # Starlette runs middleware in REVERSE order of registration (last added = outermost = runs
    # first). We register inner→outer so the effective execution order is:
    #   CORS → RequestLogging → ApiKeyAuth → RateLimit → GovernancePEP → routes
    # i.e. CORS preflight is handled first; every request is logged; AUTH runs BEFORE the rate
    # limiter so the limiter can key its per-tenant counter on the cryptographically-verified
    # principal (not a spoofable JWT/header claim, which would let an attacker exhaust a victim
    # tenant's quota — see delivery/api/ratelimit.py). The reference PEP (if any) is innermost.

    # Optional reference PEP: governance enforcement middleware (single-kernel only).
    if enforce_paths:
        if kernel is None:
            raise ValueError("enforce_paths (reference PEP) is only supported in single-kernel mode.")
        app.add_middleware(GovernanceMiddleware, kernel=kernel, enforce_paths=enforce_paths)

    # Per-tenant tier rate limiting (no-op without an entitlement source). Registered BEFORE auth so
    # it executes AFTER auth (Starlette reverses order): it reads request.state.principal to key the
    # counter on the verified tenant, falling back to client IP when auth is disabled.
    if rate_limit:
        app.add_middleware(RateLimitMiddleware)

    # API-key authentication (opt-in). Requires an account engine to verify keys.
    if require_api_key:
        if account_engine is None:
            raise ValueError("require_api_key=True requires an account_engine.")
        app.add_middleware(ApiKeyAuthMiddleware, account_engine=account_engine)

    # Structured access logging + correlation ids (always on).
    app.add_middleware(RequestLoggingMiddleware)

    # CORS so the operator console (a separate origin) can call the API. Outermost so preflight is
    # answered before any auth/rate-limit logic. The Authorization bearer header is the credential.
    # allow_headers is listed explicitly rather than "*": per the Fetch spec the wildcard does not
    # match Authorization, so a strict browser would drop it from a cross-origin preflight. These are
    # exactly the request headers the console sends (see console/src/api/client.ts).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(LifecycleDeniedError)
    async def _denied_handler(request: Request, exc: LifecycleDeniedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    @app.exception_handler(LifecycleHaltedError)
    async def _halted_handler(request: Request, exc: LifecycleHaltedError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    @app.exception_handler(TenantIsolationError)
    async def _tenant_handler(request: Request, exc: TenantIsolationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    @app.exception_handler(SubjectErasedError)
    async def _erased_handler(request: Request, exc: SubjectErasedError) -> JSONResponse:
        # 410 Gone: the data was crypto-shredded — its absence is the correct, intended state.
        return JSONResponse(
            status_code=410,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    @app.exception_handler(QUAICUError)
    async def _kernel_error_handler(request: Request, exc: QUAICUError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    # ── Health endpoints ──────────────────────────────────────────────────────
    # /health = liveness (process up); /readyz = readiness (startup hydration done). Both are
    # unauthenticated (outside /v1/*) and rate-limit exempt, for orchestrator probes + uptime
    # monitors. The Helm chart's probes hit /health (delivery/docker/helm/values.yaml).

    @app.get("/health", tags=["system"], summary="Liveness / health check")
    async def health() -> dict:
        if provider is not None:
            return {"ok": True, "mode": "shared-plane",
                    "served_tiers": sorted(t.value for t in provider.served_tiers())}
        return {"ok": True, "mode": "single-kernel", "tenant": str(kernel.tenant)}

    @app.get("/readyz", tags=["system"], summary="Readiness check")
    async def readyz(response: Response) -> dict:
        # 200 only once lifespan startup hydration completed (app.state.ready); 503 while booting or
        # draining, so an orchestrator/load balancer routes traffic only to ready instances.
        if getattr(app.state, "ready", False):
            return {"ok": True, "status": "ready"}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ok": False, "status": "not-ready"}

    return app
