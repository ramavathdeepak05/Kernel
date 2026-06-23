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

import json
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

_AZURE_DEFAULT_API_VERSION = "2024-10-21"
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_DEFAULT_MAX_TOKENS = 1024


@dataclass
class UpstreamRequest:
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any]


# ── OpenAI-compatible + Azure ────────────────────────────────────────────────────


class OpenAICompatShim:
    """OpenAI-compatible endpoints and Azure OpenAI (both OpenAI-shaped)."""

    def build_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
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


class AnthropicShim:
    """Translate OpenAI chat-completions ⇄ Anthropic Messages API (text content)."""

    def build_request(self, conn: Any, model: str, body: dict[str, Any]) -> UpstreamRequest:
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
            elif role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        out: dict[str, Any] = {
            "model": model,
            "max_tokens": int(
                body.get("max_tokens") or body.get("max_completion_tokens") or _ANTHROPIC_DEFAULT_MAX_TOKENS
            ),
            "messages": messages,
        }
        if system_parts:
            out["system"] = "\n".join(system_parts)
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
        text = "".join(
            b.get("text", "")
            for b in (data.get("content") or [])
            if isinstance(b, dict) and b.get("type") == "text"
        )
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
                    "message": {"role": "assistant", "content": text},
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
            elif etype == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield _chunk({"content": delta["text"]}, None)
            elif etype == "message_delta":
                sr = (event.get("delta") or {}).get("stop_reason")
                if sr:
                    finish = _STOP_REASON.get(str(sr), "stop")
            elif etype == "message_stop":
                yield _chunk({}, finish)
                yield "data: [DONE]\n\n"


# ── Registry ──────────────────────────────────────────────────────────────────────

_OPENAI_COMPAT = OpenAICompatShim()
_ANTHROPIC = AnthropicShim()


def get_shim(conn: Any) -> Any:
    """Resolve the shim for a connection's provider (default: OpenAI-compatible)."""
    if str(getattr(conn, "provider", "")).lower() == "anthropic":
        return _ANTHROPIC
    return _OPENAI_COMPAT


def iter_to_async(lines: Iterable[str]) -> AsyncIterator[str]:
    """Adapt a sync iterable of SSE lines to an async iterator (used in tests)."""

    async def _gen() -> AsyncIterator[str]:
        for line in lines:
            yield line

    return _gen()
