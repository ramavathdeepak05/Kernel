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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.errors import (
    LifecycleDeniedError,
    LifecycleHaltedError,
    QUAICUError,
    TenantIsolationError,
)
from delivery.api.routes.actions import router as actions_router
from delivery.api.routes.ledger import router as ledger_router
from delivery.sdk.kernel import Kernel


def create_app(kernel: Kernel) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        kernel: A fully wired ``Kernel`` instance.

    Returns:
        A configured ``FastAPI`` app ready to serve.
    """
    app = FastAPI(
        title="QUAICU Governance Kernel",
        version="0.1.0",
        description=(
            "Sovereign-tier AI governance kernel. "
            "All actions are governed: evaluate → gate → execute → seal → emit."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Attach kernel to app state (no globals)
    app.state.kernel = kernel

    # Routers
    app.include_router(actions_router)
    app.include_router(ledger_router)

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

    @app.exception_handler(QUAICUError)
    async def _kernel_error_handler(request: Request, exc: QUAICUError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "code": exc.code, "detail": exc.detail or {}},
        )

    # ── Health endpoint ───────────────────────────────────────────────────────

    @app.get("/health", tags=["system"], summary="Health check")
    async def health() -> dict:
        return {"ok": True, "tenant": str(kernel.tenant)}

    return app
