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

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.errors import GatewayBudgetExceededError, QUAICUError
from core.gateway.masking import MaskingConfig, MaskingContext, mask_text
from core.types import Actor, ActorId, RequestContext
from delivery.api.auth import current_principal
from delivery.api.deps import get_kernel
from delivery.api.routes.actions import _bearer_token
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/ai", tags=["ai-gateway"])

_FORWARD_TIMEOUT = 120.0
# Default Azure OpenAI api-version used when the connection doesn't pin one (GA as of 2024-10-21).
_AZURE_DEFAULT_API_VERSION = "2024-10-21"


def _provider_target(conn: Any, model: str) -> tuple[str, dict[str, str]]:
    """Resolve the upstream (url, headers) for the tenant's provider.

    The body/response stay OpenAI-shaped for every provider handled here, so the rest of the route
    (masking, budget, streaming, rehydration) is provider-agnostic. This is the seam later providers
    that need request/response translation (Anthropic/Vertex/Bedrock) will extend.
    """
    json_ct = {"Content-Type": "application/json"}
    if str(getattr(conn, "provider", "")).lower() == "azure":
        # Azure OpenAI: api-key header, deployment-style path, api-version query param. The OpenAI
        # "model" maps to the Azure deployment name.
        api_version = conn.api_version or _AZURE_DEFAULT_API_VERSION
        url = (
            f"{conn.base_url}/openai/deployments/{model}/chat/completions"
            f"?api-version={api_version}"
        )
        return url, {"api-key": conn.api_key, **json_ct}
    # Default: any OpenAI-compatible endpoint (OpenAI, Together, Groq, Mistral, OpenRouter, vLLM, …).
    return f"{conn.base_url}/chat/completions", {"Authorization": f"Bearer {conn.api_key}", **json_ct}


def _rehydrate_obj(obj: Any, ctx: MaskingContext) -> Any:
    """Recursively restore masked tokens to their original PII values in a provider response."""
    if isinstance(obj, str):
        return ctx.rehydrate(obj)
    if isinstance(obj, dict):
        return {k: _rehydrate_obj(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rehydrate_obj(v, ctx) for v in obj]
    return obj


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
    mask_pii: bool = Field(False, description="Tokenize PII before it reaches your provider (all plans)")


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
            mask_pii=body.mask_pii,
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

    stream = bool(body.get("stream"))

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

    # ── Budget: estimate tokens (~4 chars/token) and check/consume the tenant's cap ──────
    budget = getattr(request.app.state, "ai_budget", None)
    if budget is not None:
        # Apply a configured default cap to a tenant the first time we see it (mechanism wired now;
        # per-tenant cap management is a later admin concern). 0 / unset → unlimited.
        default_cap = int(os.getenv("QUAICU_AI_DEFAULT_MAX_TOKENS", "0") or "0")
        if default_cap > 0 and budget.usage(tenant).get("tokens", 0) == 0:
            try:
                budget.set_budget(tenant, max_tokens=default_cap)
            except Exception:  # noqa: BLE001 — never let budget wiring break the call
                pass
        try:
            budget.check_and_consume(tenant, tokens=max(1, chars // 4))
        except GatewayBudgetExceededError as exc:
            return _openai_error(429, str(exc), "BUDGET_EXCEEDED")

    # ── PII masking (opt-in per connection, all tiers): tokenize before forwarding ──────
    ctx: MaskingContext | None = None
    if conn.mask_pii:
        ctx = MaskingContext()
        cfg = MaskingConfig()
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                m["content"] = mask_text(m["content"], cfg, ctx)
        body["messages"] = messages

    url, headers = _provider_target(conn, model)

    # ── Streaming passthrough (SSE) ──────────────────────────────────────────────
    if stream:
        async def _proxy():
            try:
                async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
                    async with client.stream("POST", url, json=body, headers=headers) as upstream:
                        async for chunk in upstream.aiter_bytes():
                            if ctx is not None:
                                # Best-effort per-chunk rehydration (a masked token rarely echoes back,
                                # since PII was tokenized on the way out; tokens are ASCII + chunk-local).
                                yield ctx.rehydrate(chunk.decode("utf-8", "ignore")).encode("utf-8")
                            else:
                                yield chunk
            except Exception as exc:  # noqa: BLE001 — surface as an SSE error event, don't 500 mid-stream
                yield (
                    'data: {"error": {"message": "upstream stream failed: '
                    + str(exc).replace('"', "'")
                    + '", "type": "upstream_error"}}\n\n'
                ).encode("utf-8")
        return StreamingResponse(_proxy(), media_type="text/event-stream")

    # ── Non-streaming forward ────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
            upstream = await client.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        return _openai_error(504, "Upstream provider timed out.", "UPSTREAM_TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        return _openai_error(502, f"Could not reach upstream provider: {exc}", "UPSTREAM_UNREACHABLE")

    # Pass the provider's response (and status) back to the SDK, rehydrating masked PII first.
    try:
        data = upstream.json()
        if ctx is not None:
            data = _rehydrate_obj(data, ctx)
        return JSONResponse(status_code=upstream.status_code, content=data)
    except Exception:  # noqa: BLE001
        text = upstream.text[:1000]
        if ctx is not None:
            text = ctx.rehydrate(text)
        return JSONResponse(
            status_code=upstream.status_code,
            content={"error": {"message": text, "type": "upstream_error"}},
        )
