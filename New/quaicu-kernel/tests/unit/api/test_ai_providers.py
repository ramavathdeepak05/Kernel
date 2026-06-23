"""Provider-shim translations (W6-2): Anthropic ⇄ OpenAI (request / response / stream)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import delivery.api.ai_providers as ap
from delivery.api.ai_providers import (
    AnthropicShim,
    OpenAICompatShim,
    VertexShim,
    get_shim,
    iter_to_async,
)


@dataclass
class _Conn:
    provider: str
    base_url: str
    api_key: str = "sk-x"
    api_version: str = ""
    project: str = ""
    location: str = ""


def test_registry_routes_provider():
    assert isinstance(get_shim(_Conn("anthropic", "https://api.anthropic.com")), AnthropicShim)
    assert isinstance(get_shim(_Conn("openai", "https://api.openai.com/v1")), OpenAICompatShim)
    assert isinstance(get_shim(_Conn("azure", "https://x.openai.azure.com")), OpenAICompatShim)
    assert isinstance(get_shim(_Conn("vertex", "")), VertexShim)


async def test_anthropic_build_request_hoists_system_and_defaults_max_tokens():
    shim = AnthropicShim()
    body = {
        "messages": [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
        "temperature": 0.5,
        "stop": "END",
    }
    req = await shim.build_request(_Conn("anthropic", "https://api.anthropic.com", api_key="ak"), "claude-3-5", body)
    assert req.url == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "ak" and req.headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in req.headers
    assert req.json_body["system"] == "be terse"
    assert req.json_body["messages"] == [{"role": "user", "content": "hi"}]
    assert req.json_body["max_tokens"] == 1024  # defaulted (Anthropic requires it)
    assert req.json_body["temperature"] == 0.5
    assert req.json_body["stop_sequences"] == ["END"]


def test_anthropic_translate_response_to_openai():
    shim = AnthropicShim()
    anthropic = {
        "id": "msg_1",
        "model": "claude-3-5",
        "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    out = shim.translate_response(anthropic)
    assert out["object"] == "chat.completion"
    assert out["choices"][0]["message"]["content"] == "hello world"
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


async def test_anthropic_translate_stream_to_openai_chunks():
    shim = AnthropicShim()
    events = [
        'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-3-5"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hel"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
        'data: {"type":"message_stop"}',
    ]
    out = [chunk async for chunk in shim.translate_stream(iter_to_async(events))]
    blob = "".join(out)
    assert "chat.completion.chunk" in blob
    # The text deltas are surfaced as OpenAI delta.content...
    contents = []
    for line in blob.splitlines():
        line = line.strip()
        if line.startswith("data:") and "[DONE]" not in line:
            payload = json.loads(line[len("data:"):].strip())
            contents.append(payload["choices"][0]["delta"].get("content", ""))
    assert "".join(contents) == "Hello"
    # ...and the stream terminates with a finish_reason then [DONE].
    assert '"finish_reason": "stop"' in blob or '"finish_reason":"stop"' in blob
    assert blob.rstrip().endswith("[DONE]")


def test_openai_compat_translate_is_identity_passthrough():
    shim = OpenAICompatShim()
    data = {"choices": [{"message": {"content": "x"}}]}
    assert shim.translate_response(data) is data


# ── Vertex (token minting patched — no GCP / network) ──────────────────────────────

_SA_JSON = json.dumps({"client_email": "svc@proj.iam.gserviceaccount.com", "type": "service_account"})


def _vertex_conn(**kw):
    return _Conn("vertex", "", api_key=_SA_JSON, project="proj", location="us-central1", **kw)


async def test_vertex_build_request_uses_project_location_url_and_bearer(monkeypatch):
    calls = {"n": 0}

    def _fake_token(sa_info):
        calls["n"] += 1
        return "ya29.fake", 9_999_999_999.0  # token, far-future expiry

    monkeypatch.setattr(ap, "_vertex_access_token", _fake_token)
    ap._vertex_token_cache.clear()
    shim = VertexShim()
    body = {"messages": [{"role": "user", "content": "hi"}]}
    req = await shim.build_request(_vertex_conn(), "google/gemini-2.0-flash-001", body)
    assert req.url == (
        "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/proj"
        "/locations/us-central1/endpoints/openapi/chat/completions"
    )
    assert req.headers["Authorization"] == "Bearer ya29.fake"
    assert req.json_body is body  # OpenAI-shaped passthrough
    # Second call reuses the cached token (no second mint).
    await shim.build_request(_vertex_conn(), "m", body)
    assert calls["n"] == 1


async def test_vertex_bad_sa_json_raises(monkeypatch):
    monkeypatch.setattr(ap, "_vertex_access_token", lambda sa: ("t", 9e9))
    shim = VertexShim()
    conn = _Conn("vertex", "", api_key="not-json", project="p", location="us-central1")
    try:
        await shim.build_request(conn, "m", {"messages": []})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


async def test_vertex_requires_project_and_location(monkeypatch):
    monkeypatch.setattr(ap, "_vertex_access_token", lambda sa: ("t", 9e9))
    shim = VertexShim()
    conn = _Conn("vertex", "", api_key=_SA_JSON, project="", location="us-central1")
    try:
        await shim.build_request(conn, "m", {"messages": []})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
