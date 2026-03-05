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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.core.error_handlers import register_exception_handlers
from server.api.auth_router import router as auth_router
from server.api.users_router import router as users_router
from server.api.roles_router import router as roles_router
from server.api.organizations_router import router as organizations_router
from server.api.approvals_router import router as approvals_router
from server.api.audit_router import router as audit_router
from server.api.gateway_router import router as gateway_router
from server.api.workflows_router import router as workflows_router


def create_app() -> FastAPI:
    """
    Application factory.

    Creates and configures the FastAPI app with all routers,
    middleware, and exception handlers.
    """
    app = FastAPI(
        title="ALIS — Agentic Learning & Institutional System",
        description=(
            "Centralized platform API for ALIS. "
            "All AI invocations route through the AI Gateway (E03-S01)."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    # --- Health Check ---
    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "service": "ALIS"}

    return app


app = create_app()
