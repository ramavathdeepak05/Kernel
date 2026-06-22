"""Governed AI gateway — a drop-in OpenAI-compatible endpoint (BYO upstream key).

    GET    /v1/ai/connection            → masked status of the tenant's upstream connection
    PUT    /v1/ai/connection            → set/replace it (provider, base_url, api_key, default_model)
    DELETE /v1/ai/connection            → remove it
    POST   /v1/ai/chat/completions      → governed passthrough to the tenant's provider

The customer points their OpenAI SDK's ``base_url`` at ``…/v1/ai`` and authenticates with their
QUAICU key. The kernel governs the call (policy decision sealed to the tenant ledger as an
``ai.chat`` action) and, if allowed, forwards the *verbatim* request to the tenant's own provider
with the tenant's own key — so sampling params / multi-message / tools are preserved. The customer
pays their provider directly; QUAICU never holds or resells inference.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.errors import QUAICUError
from core.types import Actor, ActorId, RequestContext
from delivery.api.auth import current_principal
from delivery.api.deps import get_kernel
from delivery.api.routes.actions import _bearer_token
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/ai", tags=["ai-gateway"])

_FORWARD_TIMEOUT = 120.0


def _principal(request: Request):
    p = current_principal(request)
    if p is None:
        raise HTTPException(
            status_code=401, detail={"error": "Authentication required", "code": "AUTH_REQUIRED"}
        )
    return p


def _engine(request: Request):
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Account management is not enabled", "code": "ACCOUNTS_DISABLED"},
        )
    return engine


# ── Connection management ─────────────────────────────────────────────────────


class ConnectionBody(BaseModel):
    provider: str = Field("openai", description="Display label, e.g. openai | together | azure | custom")
    base_url: str = Field(..., description="OpenAI-compatible base URL, e.g. https://api.openai.com/v1")
    api_key: str = Field(..., description="Your provider key (stored encrypted; shown back only masked)")
    default_model: str = Field("", description="Model used when a request omits 'model'")


@router.get("/connection", summary="Get this tenant's upstream AI connection (masked)")
async def get_connection(request: Request) -> dict:
    principal = _principal(request)
    status = _engine(request).ai_connection_status(principal.tenant_id)
    return status or {"connected": False}


@router.put("/connection", summary="Set/replace this tenant's upstream AI connection")
async def put_connection(body: ConnectionBody, request: Request) -> dict:
    principal = _principal(request)
    if not body.base_url.strip() or not body.api_key.strip():
        raise HTTPException(
            status_code=422,
            detail={"error": "base_url and api_key are required", "code": "AI_CONNECTION_INVALID"},
        )
    engine = _engine(request)
    try:
        engine.set_ai_connection(
            principal.tenant_id,
            provider=body.provider.strip() or "openai",
            base_url=body.base_url.strip(),
            api_key=body.api_key.strip(),
            default_model=body.default_model.strip(),
        )
    except QUAICUError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    return engine.ai_connection_status(principal.tenant_id) or {"connected": False}


@router.delete("/connection", summary="Remove this tenant's upstream AI connection")
async def delete_connection(request: Request) -> dict:
    principal = _principal(request)
    removed = _engine(request).clear_ai_connection(principal.tenant_id)
    return {"connected": False, "removed": removed}


# ── Governed passthrough ──────────────────────────────────────────────────────


def _openai_error(status_code: int, message: str, code: str) -> JSONResponse:
    """Shape an error the way an OpenAI SDK expects (so client error handling works)."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": "quaicu_governance", "code": code}},
    )


@router.post("/chat/completions", summary="Governed OpenAI-compatible chat completions")
async def chat_completions(request: Request) -> Any:
    principal = _principal(request)
    tenant = principal.tenant_id
    engine = _engine(request)

    conn = engine.get_ai_connection(tenant)
    if conn is None:
        return _openai_error(
            400,
            "No AI provider connected. Add one in the console (AI gateway → Connect provider).",
            "AI_NOT_CONNECTED",
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:  # noqa: BLE001
        return _openai_error(400, "Request body is not valid JSON.", "INVALID_BODY")
    if not isinstance(body, dict):
        return _openai_error(400, "Request body must be a JSON object.", "INVALID_BODY")

    # Streaming isn't governed yet — fail clearly rather than silently buffering.
    if body.get("stream"):
        return _openai_error(400, "Streaming is not supported on the governed gateway yet; set stream=false.", "STREAM_UNSUPPORTED")

    model = str(body.get("model") or conn.default_model or "")
    if not model:
        return _openai_error(400, "No 'model' in the request and no default_model on the connection.", "MODEL_REQUIRED")
    body["model"] = model

    messages = body.get("messages") or []
    chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))

    # ── Govern: an ai.chat policy decision, sealed to the tenant ledger ──────────
    kernel: Kernel = get_kernel(request)
    token = _bearer_token(request)
    if not kernel.has_identity:
        return _openai_error(503, "Identity adapter not configured.", "IDENTITY_NOT_CONFIGURED")
    ctx = RequestContext(
        headers=dict(request.headers),
        source_ip=request.client.host if request.client else None,
        raw_token=token,
        tenant_hint=tenant,
    )
    placeholder_actor = Actor(id=ActorId("unresolved"), tenant=tenant)
    try:
        result = await kernel.check(
            action_type="ai.chat",
            actor=placeholder_actor,
            payload={"model": model, "message_count": len(messages), "prompt_chars": chars},
            context=ctx,
            record=True,
            tenant=tenant,
        )
    except QUAICUError as exc:
        return _openai_error(503, str(exc), exc.code)

    if not result.allowed:
        return _openai_error(
            403,
            f"Blocked by governance ({result.decision.value}). {result.reason or ''}".strip(),
            "GOVERNANCE_DENIED",
        )

    # ── Forward verbatim to the tenant's provider with the tenant's key ──────────
    try:
        async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
            upstream = await client.post(
                f"{conn.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {conn.api_key}", "Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        return _openai_error(504, "Upstream provider timed out.", "UPSTREAM_TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        return _openai_error(502, f"Could not reach upstream provider: {exc}", "UPSTREAM_UNREACHABLE")

    # Pass the provider's response (and status) straight back to the SDK.
    try:
        return JSONResponse(status_code=upstream.status_code, content=upstream.json())
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=upstream.status_code,
            content={"error": {"message": upstream.text[:1000], "type": "upstream_error"}},
        )
