"""Governed AI-gateway BYO passthrough (W6-2): PII masking toggle + budget + streaming."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

import delivery.api.routes.ai_gateway as gw
from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.entitlements import EntitlementStore
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy

_TENANT = "acme"
_PII = "reach me at alice@acme.io"


class _FakeStream:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _FakeClient:
    """Captures the forwarded body and echoes the first user message back as the assistant content.

    ``stream_lines`` (class attr) configures the SSE lines the streaming path yields, so a test can feed
    OpenAI-shaped or Anthropic-shaped events.
    """

    captured: dict = {}
    stream_lines: list[str] = ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeClient.captured = {"url": url, "body": json, "headers": headers}
        echoed = next((m["content"] for m in json.get("messages", []) if m.get("role") == "user"), "")

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"choices": [{"message": {"role": "assistant", "content": echoed}}]}

            text = ""

        return _Resp()

    def stream(self, method, url, json=None, headers=None):
        _FakeClient.captured = {"url": url, "body": json, "headers": headers}
        return _FakeStream(list(_FakeClient.stream_lines))


def _build(mask_pii: bool, *, provider="openai", base_url="https://api.openai.com/v1", api_version=""):
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme",
            tenant_id=TenantId(_TENANT),
            email="acme@b.io",
            name="acme",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    eng.set_ai_connection(
        TenantId(_TENANT),
        provider=provider,
        base_url=base_url,
        api_key="sk-tenant",
        default_model="gpt-4o-mini",
        mask_pii=mask_pii,
        api_version=api_version,
    )
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))
    return app, eng, key


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "X-Tenant-Id": _TENANT}


async def test_masking_on_tokenizes_outbound_and_rehydrates_response(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(mask_pii=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": _PII}], "stream": False},
        )
    assert resp.status_code == 200
    # Provider received a masked prompt (no raw email)...
    forwarded = json.dumps(_FakeClient.captured["body"])
    assert "alice@acme.io" not in forwarded and "[MASKED:" in forwarded
    # ...but the client got the original PII back (rehydrated).
    assert resp.json()["choices"][0]["message"]["content"] == _PII


async def test_masking_off_forwards_verbatim(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(mask_pii=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": _PII}]},
        )
    assert resp.status_code == 200
    assert "alice@acme.io" in json.dumps(_FakeClient.captured["body"])


async def test_budget_exhaustion_returns_429(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(mask_pii=False)
    app.state.ai_budget.set_budget(TenantId(_TENANT), max_tokens=1)  # tiny cap
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": "x" * 400}]},  # ~100 est tokens > 1
        )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "BUDGET_EXCEEDED"


async def test_streaming_passthrough_returns_sse(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(mask_pii=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert "delta" in resp.text and "[DONE]" in resp.text


async def test_connection_status_exposes_mask_pii():
    _, eng, _ = _build(mask_pii=True)
    status = eng.ai_connection_status(TenantId(_TENANT))
    assert status["mask_pii"] is True


async def test_route_uses_pluggable_masking_port(monkeypatch):
    # W6-3: when mask_pii is on, the route delegates to app.state.masking_port (regex by default;
    # swappable to Cloud DLP). Inject a fake port and assert it's invoked.
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(mask_pii=True)

    class _FakePort:
        calls = 0

        async def mask(self, text, *, config, ctx):
            _FakePort.calls += 1
            return "REDACTED"

    app.state.masking_port = _FakePort()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": _PII}]},
        )
    assert resp.status_code == 200 and _FakePort.calls == 1
    # The forwarded body carried what the port returned (not the raw PII).
    forwarded = json.dumps(_FakeClient.captured["body"])
    assert "REDACTED" in forwarded and "alice@acme.io" not in forwarded


class _AnthropicFakeClient(_FakeClient):
    """Returns an Anthropic-shaped non-stream response so the route's translate_response runs."""

    async def post(self, url, json=None, headers=None):
        _FakeClient.captured = {"url": url, "body": json, "headers": headers}

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {
                    "id": "msg_1",
                    "model": "claude-3-5",
                    "content": [{"type": "text", "text": "hi there"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                }

            text = ""

        return _Resp()


async def test_anthropic_end_to_end_translates_request_and_response(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _AnthropicFakeClient)
    app, _, key = _build(mask_pii=False, provider="anthropic", base_url="https://api.anthropic.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={
                "model": "claude-3-5",
                "messages": [
                    {"role": "system", "content": "be terse"},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
    assert resp.status_code == 200
    cap = _FakeClient.captured
    # Request was translated to the Anthropic Messages shape.
    assert cap["url"] == "https://api.anthropic.com/v1/messages"
    assert cap["headers"]["x-api-key"] == "sk-tenant" and "Authorization" not in cap["headers"]
    assert cap["body"]["system"] == "be terse" and cap["body"]["max_tokens"] == 1024
    # Response was translated back to OpenAI shape for the client.
    out = resp.json()
    assert out["object"] == "chat.completion"
    assert out["choices"][0]["message"]["content"] == "hi there"
    assert out["usage"]["total_tokens"] == 5


async def test_vertex_end_to_end_oauth_and_url(monkeypatch):
    import json as _json

    import delivery.api.ai_providers as ap

    monkeypatch.setattr(ap, "_vertex_access_token", lambda sa: ("ya29.fake", 9_999_999_999.0))
    ap._vertex_token_cache.clear()
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)

    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme",
            tenant_id=TenantId(_TENANT),
            email="acme@b.io",
            name="acme",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    eng.set_ai_connection(
        TenantId(_TENANT),
        provider="vertex",
        base_url="",
        api_key=_json.dumps({"client_email": "svc@proj.iam", "type": "service_account"}),
        default_model="google/gemini-2.0-flash-001",
        project="proj",
        location="us-central1",
    )
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    cap = _FakeClient.captured
    assert cap["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/proj"
        "/locations/us-central1/endpoints/openapi/chat/completions"
    )
    assert cap["headers"]["Authorization"] == "Bearer ya29.fake"


async def test_bedrock_end_to_end_via_injected_client(monkeypatch):
    import delivery.api.ai_providers as ap

    class _FakeBedrock:
        def converse(self, modelId, **kw):
            _FakeBedrock.last = {"modelId": modelId, **kw}
            return {
                "output": {"message": {"content": [{"text": "hi from bedrock"}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 4, "outputTokens": 3},
            }

    # Swap the registry singleton for one with an injected (no-boto3) client.
    monkeypatch.setattr(ap, "_BEDROCK", ap.BedrockShim(client_factory=lambda conn: _FakeBedrock()))

    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme", tenant_id=TenantId(_TENANT), email="acme@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    eng.set_ai_connection(
        TenantId(_TENANT), provider="bedrock", base_url="", api_key="aws-secret",
        default_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        location="us-east-1", aws_access_key_id="AKIA_TEST",
    )
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT), policy=FakePolicy(decision=Decision.ALLOW), hitl=FakeHITL(),
        ledger=FakeLedger(), events=FakeEvents(), identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"messages": [{"role": "system", "content": "be nice"}, {"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    out = resp.json()
    assert out["object"] == "chat.completion"
    assert out["choices"][0]["message"]["content"] == "hi from bedrock"
    # Request was translated to Converse (system hoisted, content blocks).
    assert _FakeBedrock.last["system"] == [{"text": "be nice"}]
    assert _FakeBedrock.last["modelId"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"


async def test_azure_shim_uses_deployment_url_and_api_key_header(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _FakeClient)
    app, _, key = _build(
        mask_pii=False,
        provider="azure",
        base_url="https://my-res.openai.azure.com",
        api_version="2024-10-21",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ai/chat/completions",
            headers=_auth(key),
            json={"model": "gpt-4o-dep", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    cap = _FakeClient.captured
    assert cap["url"] == (
        "https://my-res.openai.azure.com/openai/deployments/gpt-4o-dep/chat/completions"
        "?api-version=2024-10-21"
    )
    # Azure auth = api-key header, NOT Authorization: Bearer.
    assert cap["headers"].get("api-key") == "sk-tenant"
    assert "Authorization" not in cap["headers"]
