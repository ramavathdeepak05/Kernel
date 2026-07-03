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

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.errors import GatewayBudgetExceededError, QUAICUError
from core.gateway.masking import DEFAULT_MASKING, MaskingConfig, MaskingContext
from core.types import Actor, ActorId, RequestContext
from delivery.api.ai_providers import ProviderDependencyError, get_shim
from delivery.api.auth import current_principal
from delivery.api.deps import get_kernel
from delivery.api.routes.actions import _bearer_token
from delivery.sdk.kernel import Kernel

router = APIRouter(prefix="/v1/ai", tags=["ai-gateway"])

_FORWARD_TIMEOUT = 120.0
def _rehydrate_obj(obj: Any, ctx: MaskingContext) -> Any:
    """Recursively restore masked tokens to their original PII values in a provider response."""
    if isinstance(obj, str):
        return ctx.rehydrate(obj)
    if isinstance(obj, dict):
        return {k: _rehydrate_obj(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rehydrate_obj(v, ctx) for v in obj]
    return obj


def _tool_calls_from_choices(data: Any) -> list[dict[str, Any]]:
    """Collect OpenAI ``message.tool_calls`` across all choices in a chat.completion response."""
    out: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return out
    for choice in data.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        for tc in (choice.get("message") or {}).get("tool_calls") or []:
            if isinstance(tc, dict):
                out.append(tc)
    return out


async def _govern_tool_calls(
    kernel: Kernel, *, tenant: Any, req_ctx: RequestContext, tool_calls: list[dict[str, Any]]
) -> tuple[bool, str, str]:
    """Seal each tool call as an ``ai.tool_call`` action. Fail-closed: any non-ALLOW (or infra
    error) blocks the whole response. Returns ``(ok, error_code, message)``.

    The sealed payload is a non-PII summary (tool name + argument length + call id) — the same
    shape discipline as ``ai.chat`` (message_count/prompt_chars), keeping the ledger PII-free.
    """
    placeholder_actor = Actor(id=ActorId("unresolved"), tenant=tenant)
    for tc in tool_calls:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        name = str(fn.get("name") or "")
        args = fn.get("arguments") or ""
        try:
            result = await kernel.check(
                action_type="ai.tool_call",
                actor=placeholder_actor,
                payload={
                    "tool_name": name,
                    "call_id": str(tc.get("id") or ""),
                    "arguments_chars": len(str(args)),
                },
                context=req_ctx,
                record=True,
                tenant=tenant,
            )
        except QUAICUError as exc:
            return False, exc.code, str(exc)
        if not result.allowed:
            reason = (result.reason or "").strip()
            return (
                False,
                "GOVERNANCE_DENIED",
                f"Tool call '{name}' blocked by governance ({result.decision.value}). {reason}".strip(),
            )
    return True, "", ""


def _sse_data(sse: str) -> Any:
    """Parse one SSE ``data:`` line → a JSON dict, the sentinel ``"[DONE]"``, or ``None``."""
    s = sse.strip()
    if not s.startswith("data:"):
        return None
    body = s[len("data:"):].strip()
    if body == "[DONE]":
        return "[DONE]"
    try:
        return json.loads(body)
    except ValueError:
        return None


def _sse_error(message: str, code: str) -> str:
    payload = {"error": {"message": message, "type": "quaicu_governance", "code": code}}
    return f"data: {json.dumps(payload)}\n\n"


async def _govern_tool_call_stream(
    source: Any, kernel: Kernel, *, tenant: Any, req_ctx: RequestContext
) -> Any:
    """Wrap an OpenAI SSE stream: text/role/finish chunks pass through live, but tool_call deltas are
    buffered, accumulated, and sealed at stream end. All allowed → flush the buffered chunks; any
    denied (or infra error) → emit a governance error event and stop (fail-closed)."""
    acc: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    buffered: list[str] = []
    resolved = False

    async def _resolve() -> tuple[bool, str, str]:
        calls = [
            {
                "id": acc[i]["id"],
                "function": {"name": acc[i]["name"], "arguments": acc[i]["arguments"]},
            }
            for i in order
        ]
        return await _govern_tool_calls(kernel, tenant=tenant, req_ctx=req_ctx, tool_calls=calls)

    async for sse in source:
        payload = _sse_data(sse)
        if payload is None:
            yield sse
            continue
        if payload == "[DONE]":
            if acc and not resolved:
                ok, code, msg = await _resolve()
                resolved = True
                if not ok:
                    yield _sse_error(msg, code)
                    return
                for b in buffered:
                    yield b
            yield sse
            return
        choices = payload.get("choices") or []
        delta = (choices[0].get("delta") or {}) if choices else {}
        finish = choices[0].get("finish_reason") if choices else None
        tcs = delta.get("tool_calls")
        if tcs and not resolved:
            for tc in tcs:
                idx = tc.get("index", 0) or 0
                if idx not in acc:
                    acc[idx] = {"id": "", "name": "", "arguments": ""}
                    order.append(idx)
                if tc.get("id"):
                    acc[idx]["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    acc[idx]["name"] += fn["name"]
                if fn.get("arguments"):
                    acc[idx]["arguments"] += fn["arguments"]
            buffered.append(sse)
            continue
        if finish is not None and acc and not resolved:
            ok, code, msg = await _resolve()
            resolved = True
            if not ok:
                yield _sse_error(msg, code)
                return
            for b in buffered:
                yield b
            yield sse
            continue
        yield sse

    # Source ended without an explicit [DONE] chunk — resolve any buffered tool calls now.
    if acc and not resolved:
        ok, code, msg = await _resolve()
        if not ok:
            yield _sse_error(msg, code)
            return
        for b in buffered:
            yield b


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
    req_ctx = RequestContext(
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
            context=req_ctx,
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
        # The masking engine is pluggable (W6-3): in-process regex by default, or managed Cloud DLP when
        # the deployment opts in. Resolved on app.state; defaults to regex.
        port = getattr(request.app.state, "masking_port", None) or DEFAULT_MASKING
        ctx = MaskingContext()
        cfg = MaskingConfig()
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                m["content"] = await port.mask(m["content"], config=cfg, ctx=ctx)
        body["messages"] = messages

    shim = get_shim(conn)

    # ── Self-dispatching providers (e.g. Bedrock via boto3 — the SDK owns the SigV4 call) ──
    if hasattr(shim, "complete"):
        try:
            if stream:
                async def _self_stream():
                    try:
                        governed = _govern_tool_call_stream(
                            shim.stream(conn, model, body), kernel, tenant=tenant, req_ctx=req_ctx
                        )
                        async for sse in governed:
                            yield (ctx.rehydrate(sse) if ctx is not None else sse).encode("utf-8")
                    except Exception as exc:  # noqa: BLE001 — surface as an SSE error event
                        yield (
                            'data: {"error": {"message": "provider stream failed: '
                            + str(exc).replace('"', "'") + '", "type": "upstream_error"}}\n\n'
                        ).encode("utf-8")
                return StreamingResponse(_self_stream(), media_type="text/event-stream")
            data = await shim.complete(conn, model, body)
            tool_calls = _tool_calls_from_choices(data)
            if tool_calls:
                ok, code, msg = await _govern_tool_calls(
                    kernel, tenant=tenant, req_ctx=req_ctx, tool_calls=tool_calls
                )
                if not ok:
                    return _openai_error(403 if code == "GOVERNANCE_DENIED" else 503, msg, code)
            if ctx is not None:
                data = _rehydrate_obj(data, ctx)
            return JSONResponse(status_code=200, content=data)
        except ProviderDependencyError as exc:
            return _openai_error(501, str(exc), "PROVIDER_DEPENDENCY_MISSING")
        except Exception as exc:  # noqa: BLE001 — credential / API failure
            return _openai_error(502, f"Provider call failed: {exc}", "PROVIDER_AUTH_FAILED")

    # Translate the OpenAI request to the upstream's shape (httpx-forwarded providers). For providers
    # that mint credentials (e.g. Vertex OAuth from a service-account JSON), build_request can fail on a
    # bad/missing credential — surface that as a clean provider-auth error.
    try:
        req = await shim.build_request(conn, model, body)
    except ValueError as exc:
        return _openai_error(400, str(exc), "PROVIDER_CONFIG_INVALID")
    except Exception as exc:  # noqa: BLE001 — token mint / credential failure
        return _openai_error(502, f"Provider authentication failed: {exc}", "PROVIDER_AUTH_FAILED")

    # ── Streaming (SSE) — translate the upstream stream to OpenAI chunks ──────────
    if stream:
        async def _proxy():
            try:
                async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
                    async with client.stream(
                        "POST", req.url, json=req.json_body, headers=req.headers
                    ) as upstream:
                        governed = _govern_tool_call_stream(
                            shim.translate_stream(upstream.aiter_lines()),
                            kernel,
                            tenant=tenant,
                            req_ctx=req_ctx,
                        )
                        async for sse in governed:
                            # Best-effort per-chunk rehydration (PII was masked on the way out; tokens
                            # are ASCII + chunk-local, so a stray echo rehydrates cleanly).
                            yield (ctx.rehydrate(sse) if ctx is not None else sse).encode("utf-8")
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
            upstream = await client.post(req.url, json=req.json_body, headers=req.headers)
    except httpx.TimeoutException:
        return _openai_error(504, "Upstream provider timed out.", "UPSTREAM_TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        return _openai_error(502, f"Could not reach upstream provider: {exc}", "UPSTREAM_UNREACHABLE")

    # Translate the provider response to OpenAI shape. Governance runs OUTSIDE the translate
    # try/except so an unexpected governance error fails closed (never falls through to the raw
    # upstream passthrough below).
    try:
        data = shim.translate_response(upstream.json())
    except Exception:  # noqa: BLE001 — non-OpenAI / non-JSON upstream body → passthrough error text
        text = upstream.text[:1000]
        if ctx is not None:
            text = ctx.rehydrate(text)
        return JSONResponse(
            status_code=upstream.status_code,
            content={"error": {"message": text, "type": "upstream_error"}},
        )

    tool_calls = _tool_calls_from_choices(data)
    if tool_calls:
        ok, code, msg = await _govern_tool_calls(
            kernel, tenant=tenant, req_ctx=req_ctx, tool_calls=tool_calls
        )
        if not ok:
            return _openai_error(403 if code == "GOVERNANCE_DENIED" else 503, msg, code)
    if ctx is not None:
        data = _rehydrate_obj(data, ctx)
    return JSONResponse(status_code=upstream.status_code, content=data)


@router.post("/embeddings", summary="Governed OpenAI-compatible embeddings")
async def embeddings(request: Request) -> Any:
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

    model = str(body.get("model") or conn.default_model or "")
    if not model:
        return _openai_error(400, "No 'model' in the request and no default_model on the connection.", "MODEL_REQUIRED")
    body["model"] = model

    shim = get_shim(conn)
    if not hasattr(shim, "embeddings_request"):
        return _openai_error(
            501,
            f"The '{conn.provider}' provider has no OpenAI-compatible embeddings endpoint.",
            "NOT_SUPPORTED",
        )

    raw_input = body.get("input")
    inputs = raw_input if isinstance(raw_input, list) else ([raw_input] if raw_input is not None else [])
    chars = sum(len(str(x)) for x in inputs)

    # ── Govern: an ai.embed policy decision, sealed to the tenant ledger ──────────
    kernel: Kernel = get_kernel(request)
    token = _bearer_token(request)
    if not kernel.has_identity:
        return _openai_error(503, "Identity adapter not configured.", "IDENTITY_NOT_CONFIGURED")
    req_ctx = RequestContext(
        headers=dict(request.headers),
        source_ip=request.client.host if request.client else None,
        raw_token=token,
        tenant_hint=tenant,
    )
    placeholder_actor = Actor(id=ActorId("unresolved"), tenant=tenant)
    try:
        result = await kernel.check(
            action_type="ai.embed",
            actor=placeholder_actor,
            payload={"model": model, "input_count": len(inputs), "input_chars": chars},
            context=req_ctx,
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

    # ── Budget (~4 chars/token) ──────────────────────────────────────────────────
    budget = getattr(request.app.state, "ai_budget", None)
    if budget is not None:
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

    # ── PII masking (input only; embedding vectors carry no PII to rehydrate) ──────
    if conn.mask_pii and inputs:
        port = getattr(request.app.state, "masking_port", None) or DEFAULT_MASKING
        mctx = MaskingContext()
        cfg = MaskingConfig()
        masked = [
            await port.mask(x, config=cfg, ctx=mctx) if isinstance(x, str) else x for x in inputs
        ]
        body["input"] = masked if isinstance(raw_input, list) else masked[0]

    try:
        req = await shim.embeddings_request(conn, model, body)
    except ValueError as exc:
        return _openai_error(400, str(exc), "PROVIDER_CONFIG_INVALID")
    except Exception as exc:  # noqa: BLE001 — token mint / credential failure
        return _openai_error(502, f"Provider authentication failed: {exc}", "PROVIDER_AUTH_FAILED")

    try:
        async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
            upstream = await client.post(req.url, json=req.json_body, headers=req.headers)
    except httpx.TimeoutException:
        return _openai_error(504, "Upstream provider timed out.", "UPSTREAM_TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        return _openai_error(502, f"Could not reach upstream provider: {exc}", "UPSTREAM_UNREACHABLE")

    try:
        return JSONResponse(status_code=upstream.status_code, content=upstream.json())
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=upstream.status_code,
            content={"error": {"message": upstream.text[:1000], "type": "upstream_error"}},
        )
