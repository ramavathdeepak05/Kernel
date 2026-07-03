"""Provider shims for the governed AI gateway (W6-2).

The BYO gateway speaks OpenAI chat-completions to the client. A *shim* maps that to/from a specific
upstream provider so masking/budget/streaming in the route stay provider-agnostic. Each shim:

  - ``build_request(conn, model, openai_body)`` → the upstream ``UpstreamRequest`` (url, headers, body)
  - ``translate_response(data)``               → an OpenAI ``chat.completion`` dict
  - ``translate_stream(lines)``                → an async iterator of OpenAI SSE ``data: …`` strings

``OpenAICompatShim`` covers OpenAI-compatible endpoints (OpenAI/Together/Groq/Mistral/OpenRouter/vLLM)
**and Azure OpenAI** (api-key header + deployment URL + api-version) — body/response/stream are already
OpenAI-shaped, so its translate_* are identity/passthrough. ``AnthropicShim`` translates the Messages
API both ways (incl. its SSE event format). Later providers (Vertex, Bedrock) add their own shims here.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

_AZURE_DEFAULT_API_VERSION = "2024-10-21"
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_DEFAULT_MAX_TOKENS = 1024
_GCP_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


@dataclass
class UpstreamRequest:
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any]


# ── OpenAI-compatible + Azure ────────────────────────────────────────────────────


class OpenAICompatShim:
    """OpenAI-compatible endpoints and Azure OpenAI (both OpenAI-shaped)."""

    async def build_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
        json_ct = {"Content-Type": "application/json"}
        if str(getattr(conn, "provider", "")).lower() == "azure":
            api_version = getattr(conn, "api_version", "") or _AZURE_DEFAULT_API_VERSION
            url = (
                f"{conn.base_url}/openai/deployments/{model}/chat/completions"
                f"?api-version={api_version}"
            )
            return UpstreamRequest(url, {"api-key": conn.api_key, **json_ct}, body)
        url = f"{conn.base_url}/chat/completions"
        return UpstreamRequest(url, {"Authorization": f"Bearer {conn.api_key}", **json_ct}, body)

    async def embeddings_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
        json_ct = {"Content-Type": "application/json"}
        if str(getattr(conn, "provider", "")).lower() == "azure":
            api_version = getattr(conn, "api_version", "") or _AZURE_DEFAULT_API_VERSION
            url = f"{conn.base_url}/openai/deployments/{model}/embeddings?api-version={api_version}"
            return UpstreamRequest(url, {"api-key": conn.api_key, **json_ct}, body)
        url = f"{conn.base_url}/embeddings"
        return UpstreamRequest(url, {"Authorization": f"Bearer {conn.api_key}", **json_ct}, body)

    def translate_response(self, data: dict[str, Any]) -> dict[str, Any]:
        return data  # already OpenAI-shaped

    async def translate_stream(self, lines: AsyncIterator[str]) -> AsyncIterator[str]:
        # Passthrough: the upstream already emits OpenAI SSE chunks. Re-attach the SSE framing the
        # route strips when iterating lines.
        async for line in lines:
            if line:
                yield line + "\n\n" if not line.endswith("\n") else line


# ── Anthropic Messages API ────────────────────────────────────────────────────────

_STOP_REASON = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


def _load_args(arguments: Any) -> dict[str, Any]:
    """Parse an OpenAI tool_call's ``arguments`` (a JSON string) into a dict; tolerate junk."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _openai_tools_to_anthropic(tools: Any) -> list[dict[str, Any]]:
    """OpenAI ``tools`` (function schemas) → Anthropic ``tools`` (name/description/input_schema)."""
    out: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function") or {}
        out.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def _anthropic_tool_choice(choice: Any) -> dict[str, Any] | None:
    """OpenAI ``tool_choice`` → Anthropic ``tool_choice`` (auto/any/tool)."""
    if choice in (None, "auto"):
        return None
    if choice in ("required", "any"):
        return {"type": "any"}
    if choice == "none":
        return None
    if isinstance(choice, dict) and choice.get("type") == "function":
        name = (choice.get("function") or {}).get("name")
        if name:
            return {"type": "tool", "name": name}
    return None


class AnthropicShim:
    """Translate OpenAI chat-completions ⇄ Anthropic Messages API (text + tool use)."""

    async def build_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for m in body.get("messages", []) or []:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                if isinstance(content, str):
                    system_parts.append(content)
            elif role == "assistant":
                # An assistant turn may carry text and/or OpenAI tool_calls → Anthropic tool_use blocks.
                blocks: list[dict[str, Any]] = []
                if isinstance(content, str) and content:
                    blocks.append({"type": "text", "text": content})
                for tc in m.get("tool_calls") or []:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", "") if isinstance(tc, dict) else "",
                            "name": fn.get("name", ""),
                            "input": _load_args(fn.get("arguments")),
                        }
                    )
                messages.append({"role": "assistant", "content": blocks or content})
            elif role == "tool":
                # An OpenAI tool result → an Anthropic user turn with a tool_result block.
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.get("tool_call_id", ""),
                                "content": content if isinstance(content, str) else json.dumps(content),
                            }
                        ],
                    }
                )
            elif role == "user":
                messages.append({"role": "user", "content": content})

        out: dict[str, Any] = {
            "model": model,
            "max_tokens": int(
                body.get("max_tokens") or body.get("max_completion_tokens") or _ANTHROPIC_DEFAULT_MAX_TOKENS
            ),
            "messages": messages,
        }
        if system_parts:
            out["system"] = "\n".join(system_parts)
        tools = _openai_tools_to_anthropic(body.get("tools"))
        if tools:
            out["tools"] = tools
            choice = _anthropic_tool_choice(body.get("tool_choice"))
            if choice is not None:
                out["tool_choice"] = choice
        for src, dst in (("temperature", "temperature"), ("top_p", "top_p")):
            if body.get(src) is not None:
                out[dst] = body[src]
        if body.get("stop") is not None:
            stop = body["stop"]
            out["stop_sequences"] = stop if isinstance(stop, list) else [stop]
        if body.get("stream"):
            out["stream"] = True

        headers = {
            "x-api-key": conn.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        return UpstreamRequest(f"{conn.base_url}/v1/messages", headers, out)

    def translate_response(self, data: dict[str, Any]) -> dict[str, Any]:
        blocks = data.get("content") or []
        text = "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        )
        tool_calls: list[dict[str, Any]] = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": b.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": b.get("name", ""),
                            "arguments": json.dumps(b.get("input") or {}),
                        },
                    }
                )
        message: dict[str, Any] = {"role": "assistant", "content": text or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        usage = data.get("usage") or {}
        prompt = int(usage.get("input_tokens", 0) or 0)
        completion = int(usage.get("output_tokens", 0) or 0)
        return {
            "id": data.get("id", ""),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": _STOP_REASON.get(str(data.get("stop_reason")), "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        }

    async def translate_stream(self, lines: AsyncIterator[str]) -> AsyncIterator[str]:
        """Anthropic SSE events → OpenAI chat.completion.chunk SSE strings."""
        msg_id = ""
        model = ""
        finish = "stop"
        created = int(time.time())
        # Anthropic block index → sequential OpenAI tool_call index (text blocks don't count).
        tool_block_index: dict[int, int] = {}
        next_tool_idx = 0

        def _chunk(delta: dict[str, Any], finish_reason: Any) -> str:
            payload = {
                "id": msg_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }
            return f"data: {json.dumps(payload)}\n\n"

        async for raw in lines:
            line = raw.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            try:
                event = json.loads(data_str)
            except ValueError:
                continue
            etype = event.get("type")
            if etype == "message_start":
                msg = event.get("message") or {}
                msg_id = msg.get("id", msg_id)
                model = msg.get("model", model)
                yield _chunk({"role": "assistant", "content": ""}, None)
            elif etype == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    tc_idx = next_tool_idx
                    next_tool_idx += 1
                    tool_block_index[event.get("index")] = tc_idx
                    yield _chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": tc_idx,
                                    "id": block.get("id", ""),
                                    "type": "function",
                                    "function": {"name": block.get("name", ""), "arguments": ""},
                                }
                            ]
                        },
                        None,
                    )
            elif etype == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield _chunk({"content": delta["text"]}, None)
                elif delta.get("type") == "input_json_delta" and event.get("index") in tool_block_index:
                    yield _chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": tool_block_index[event.get("index")],
                                    "function": {"arguments": delta.get("partial_json", "")},
                                }
                            ]
                        },
                        None,
                    )
            elif etype == "message_delta":
                sr = (event.get("delta") or {}).get("stop_reason")
                if sr:
                    finish = _STOP_REASON.get(str(sr), "stop")
            elif etype == "message_stop":
                yield _chunk({}, finish)
                yield "data: [DONE]\n\n"


# ── Google Vertex AI (OpenAI-compatible endpoint, OAuth from a service-account JSON) ─

# Cache minted OAuth tokens per service account (keyed on client_email) to avoid a token-endpoint
# round-trip on every request. Tokens live ~1h; we refresh within 60s of expiry.
_vertex_token_cache: dict[str, tuple[str, float]] = {}
_vertex_token_lock = threading.Lock()


def _vertex_access_token(sa_info: dict[str, Any]) -> tuple[str, float]:
    """Mint a GCP OAuth access token from a service-account dict. Returns (token, expiry_epoch).

    Blocking (does a token-endpoint HTTP refresh) — callers run it off the event loop. Patched in
    tests so no network/credentials are needed. google-auth is imported lazily.
    """
    from google.auth.transport.requests import Request  # lazy: only needed for Vertex
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=[_GCP_SCOPE])
    creds.refresh(Request())
    expiry = creds.expiry.timestamp() if creds.expiry else (time.time() + 3300)
    return creds.token, expiry


class VertexShim:
    """Google Vertex AI via its OpenAI-compatible endpoint (auth = OAuth token from a SA JSON).

    Body/response/stream are OpenAI-shaped (identity/passthrough); the work is per-tenant SA-JSON →
    cached OAuth token + the project/location-scoped URL.
    """

    async def build_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
        try:
            sa_info = json.loads(conn.api_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("Vertex connection's service-account JSON is not valid JSON.") from exc
        project = (getattr(conn, "project", "") or "").strip()
        location = (getattr(conn, "location", "") or "").strip()
        if not project or not location:
            raise ValueError("Vertex connection requires both 'project' and 'location'.")

        token = await self._token(sa_info)
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}"
            f"/locations/{location}/endpoints/openapi/chat/completions"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return UpstreamRequest(url, headers, body)

    async def embeddings_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
        try:
            sa_info = json.loads(conn.api_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("Vertex connection's service-account JSON is not valid JSON.") from exc
        project = (getattr(conn, "project", "") or "").strip()
        location = (getattr(conn, "location", "") or "").strip()
        if not project or not location:
            raise ValueError("Vertex connection requires both 'project' and 'location'.")
        token = await self._token(sa_info)
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}"
            f"/locations/{location}/endpoints/openapi/embeddings"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return UpstreamRequest(url, headers, body)

    async def _token(self, sa_info: dict[str, Any]) -> str:
        key = str(sa_info.get("client_email", "")) or json.dumps(sa_info, sort_keys=True)
        now = time.time()
        with _vertex_token_lock:
            cached = _vertex_token_cache.get(key)
            if cached and cached[1] - 60 > now:
                return cached[0]
        # Mint off the event loop (blocking refresh).
        token, expiry = await asyncio.to_thread(_vertex_access_token, sa_info)
        with _vertex_token_lock:
            _vertex_token_cache[key] = (token, expiry)
        return token

    def translate_response(self, data: dict[str, Any]) -> dict[str, Any]:
        return data  # OpenAI-shaped

    async def translate_stream(self, lines: AsyncIterator[str]) -> AsyncIterator[str]:
        async for line in lines:
            if line:
                yield line + "\n\n" if not line.endswith("\n") else line


# ── AWS Bedrock (Converse API via boto3; self-dispatching — boto3 owns the SigV4 call) ─


class ProviderDependencyError(RuntimeError):
    """Raised when a provider's optional SDK isn't installed (e.g. boto3 for Bedrock)."""


def openai_to_converse(body: dict[str, Any]) -> dict[str, Any]:
    """OpenAI chat-completions → Bedrock Converse request fields (messages/system/inference/tools)."""
    system: list[dict[str, str]] = []
    messages: list[dict[str, Any]] = []
    for m in body.get("messages", []) or []:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content", "")
        if role == "system":
            if isinstance(content, str) and content:
                system.append({"text": content})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                blocks.append({"text": content})
            for tc in m.get("tool_calls") or []:
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                blocks.append(
                    {
                        "toolUse": {
                            "toolUseId": tc.get("id", "") if isinstance(tc, dict) else "",
                            "name": fn.get("name", ""),
                            "input": _load_args(fn.get("arguments")),
                        }
                    }
                )
            if blocks:
                messages.append({"role": "assistant", "content": blocks})
        elif role == "user" and isinstance(content, str):
            messages.append({"role": "user", "content": [{"text": content}]})
        elif role == "tool":
            # Bedrock carries a tool result in a user turn; merge into the trailing user turn if any.
            block = {
                "toolResult": {
                    "toolUseId": m.get("tool_call_id", ""),
                    "content": [{"text": content if isinstance(content, str) else json.dumps(content)}],
                }
            }
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"].append(block)
            else:
                messages.append({"role": "user", "content": [block]})

    inference: dict[str, Any] = {}
    if body.get("max_tokens") or body.get("max_completion_tokens"):
        inference["maxTokens"] = int(body.get("max_tokens") or body.get("max_completion_tokens"))
    if body.get("temperature") is not None:
        inference["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        inference["topP"] = body["top_p"]
    if body.get("stop") is not None:
        stop = body["stop"]
        inference["stopSequences"] = stop if isinstance(stop, list) else [stop]

    out: dict[str, Any] = {"messages": messages}
    if system:
        out["system"] = system
    if inference:
        out["inferenceConfig"] = inference
    tool_config = _openai_tools_to_converse(body.get("tools"), body.get("tool_choice"))
    if tool_config:
        out["toolConfig"] = tool_config
    return out


def _openai_tools_to_converse(tools: Any, tool_choice: Any) -> dict[str, Any] | None:
    """OpenAI ``tools``/``tool_choice`` → Bedrock Converse ``toolConfig``."""
    specs: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function") or {}
        specs.append(
            {
                "toolSpec": {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "inputSchema": {"json": fn.get("parameters") or {"type": "object", "properties": {}}},
                }
            }
        )
    if not specs:
        return None
    out: dict[str, Any] = {"tools": specs}
    if tool_choice in ("required", "any"):
        out["toolChoice"] = {"any": {}}
    elif tool_choice == "auto":
        out["toolChoice"] = {"auto": {}}
    elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        name = (tool_choice.get("function") or {}).get("name")
        if name:
            out["toolChoice"] = {"tool": {"name": name}}
    return out


def converse_to_openai(resp: dict[str, Any], model: str = "") -> dict[str, Any]:
    """Bedrock Converse response → OpenAI chat.completion."""
    blocks = (((resp.get("output") or {}).get("message") or {}).get("content")) or []
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    tool_calls: list[dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, dict) and "toolUse" in b:
            tu = b["toolUse"] or {}
            tool_calls.append(
                {
                    "id": tu.get("toolUseId", ""),
                    "type": "function",
                    "function": {"name": tu.get("name", ""), "arguments": json.dumps(tu.get("input") or {})},
                }
            )
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    usage = resp.get("usage") or {}
    prompt = int(usage.get("inputTokens", 0) or 0)
    completion = int(usage.get("outputTokens", 0) or 0)
    return {
        "id": "",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _BEDROCK_STOP.get(str(resp.get("stopReason")), "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


_BEDROCK_STOP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "content_filtered": "content_filter",
}


class BedrockShim:
    """AWS Bedrock via the Converse API (boto3). Self-dispatching: boto3 makes the SigV4 call, so this
    shim exposes ``complete``/``stream`` (not the httpx ``build_request`` path). ``client_factory`` is
    injectable for tests so no boto3 / AWS creds are needed.
    """

    def __init__(self, client_factory: Any | None = None) -> None:
        self._client_factory = client_factory

    def _client(self, conn: Any) -> Any:
        if self._client_factory is not None:
            return self._client_factory(conn)
        try:
            import boto3  # lazy ([aws] extra)
        except ImportError as exc:  # pragma: no cover - exercised via the route's error path
            raise ProviderDependencyError(
                "AWS Bedrock requires the 'aws' extra: pip install quaicu-kernel[aws]."
            ) from exc
        return boto3.client(
            "bedrock-runtime",
            region_name=conn.location or None,
            aws_access_key_id=conn.aws_access_key_id or None,
            aws_secret_access_key=conn.api_key or None,
        )

    async def complete(self, conn: Any, model: str, body: dict[str, Any]) -> dict[str, Any]:
        client = self._client(conn)
        req = openai_to_converse(body)
        resp = await asyncio.to_thread(client.converse, modelId=model, **req)
        return converse_to_openai(resp, model)

    async def stream(self, conn: Any, model: str, body: dict[str, Any]) -> AsyncIterator[str]:
        client = self._client(conn)
        req = openai_to_converse(body)
        created = int(time.time())

        def _chunk(delta: dict[str, Any], finish: Any) -> str:
            payload = {
                "id": "",
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(payload)}\n\n"

        # boto3's converse_stream EventStream is blocking — drain it in a worker thread onto a queue.
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _drain() -> None:
            try:
                resp = client.converse_stream(modelId=model, **req)
                for event in resp.get("stream", []):
                    loop.call_soon_threadsafe(queue.put_nowait, ("event", event))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        worker = asyncio.create_task(asyncio.to_thread(_drain))
        finish = "stop"
        # Bedrock contentBlockIndex → sequential OpenAI tool_call index (text blocks don't count).
        tool_block_index: dict[int, int] = {}
        next_tool_idx = 0
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "done":
                    break
                if kind == "error":
                    yield (
                        'data: {"error": {"message": "bedrock stream failed: '
                        + str(payload).replace('"', "'") + '", "type": "upstream_error"}}\n\n'
                    )
                    break
                ev = payload
                if "messageStart" in ev:
                    yield _chunk({"role": "assistant", "content": ""}, None)
                elif "contentBlockStart" in ev:
                    start = (ev["contentBlockStart"].get("start") or {}).get("toolUse")
                    if start:
                        block_idx = ev["contentBlockStart"].get("contentBlockIndex")
                        tc_idx = next_tool_idx
                        next_tool_idx += 1
                        tool_block_index[block_idx] = tc_idx
                        yield _chunk(
                            {
                                "tool_calls": [
                                    {
                                        "index": tc_idx,
                                        "id": start.get("toolUseId", ""),
                                        "type": "function",
                                        "function": {"name": start.get("name", ""), "arguments": ""},
                                    }
                                ]
                            },
                            None,
                        )
                elif "contentBlockDelta" in ev:
                    delta = ev["contentBlockDelta"].get("delta") or {}
                    txt = delta.get("text")
                    if txt:
                        yield _chunk({"content": txt}, None)
                    tu = delta.get("toolUse")
                    if tu is not None:
                        block_idx = ev["contentBlockDelta"].get("contentBlockIndex")
                        tc_idx = tool_block_index.get(block_idx, 0)
                        yield _chunk(
                            {"tool_calls": [{"index": tc_idx, "function": {"arguments": tu.get("input", "")}}]},
                            None,
                        )
                elif "messageStop" in ev:
                    finish = _BEDROCK_STOP.get(str(ev["messageStop"].get("stopReason")), "stop")
            yield _chunk({}, finish)
            yield "data: [DONE]\n\n"
        finally:
            await worker


# ── Registry ──────────────────────────────────────────────────────────────────────

_OPENAI_COMPAT = OpenAICompatShim()
_ANTHROPIC = AnthropicShim()
_VERTEX = VertexShim()
_BEDROCK = BedrockShim()


def get_shim(conn: Any) -> Any:
    """Resolve the shim for a connection's provider (default: OpenAI-compatible)."""
    provider = str(getattr(conn, "provider", "")).lower()
    if provider == "anthropic":
        return _ANTHROPIC
    if provider == "vertex":
        return _VERTEX
    if provider == "bedrock":
        return _BEDROCK
    return _OPENAI_COMPAT


def iter_to_async(lines: Iterable[str]) -> AsyncIterator[str]:
    """Adapt a sync iterable of SSE lines to an async iterator (used in tests)."""

    async def _gen() -> AsyncIterator[str]:
        for line in lines:
            yield line

    return _gen()
