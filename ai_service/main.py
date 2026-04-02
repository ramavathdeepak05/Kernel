"""
ALIS AI Service — S3

Standalone FastAPI microservice for AI inference.

Responsibilities:
- PII masking before any provider call
- Multi-provider routing: VPC Ollama → Azure OpenAI / Bedrock / Vertex
- Per-tenant monthly token budget tracking
- Prompt injection detection (re-uses ALIS gateway heuristics)

Run with:
    uvicorn ai_service.main:app --host 0.0.0.0 --port 8002

Data planes call this service via AIServiceProvider (added to AIGateway in S3).
When AI_SERVICE_URL is unset, AIGateway falls back to direct Ollama (pre-S3 behaviour).
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
    logger.info("AI Service started.")
    yield
    logger.info("AI Service shut down.")


def create_app() -> FastAPI:
    from ai_service.settings import settings

    app = FastAPI(
        title="ALIS AI Service",
        description=(
            "Centralised AI inference service for the ALIS SaaS platform. "
            "PII masking, multi-provider routing, and token budget enforcement."
        ),
        version="1.0.0",
        lifespan=_lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-AI-Token"],
    )

    from ai_service.router import router
    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": "ai-service"}

    @app.exception_handler(Exception)
    async def _generic_handler(request, exc):
        logger.exception("AI Service unhandled exception: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return app


app = create_app()
