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
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class _FakeClient:
    """Captures the forwarded body and echoes the first user message back as the assistant content."""

    captured: dict = {}

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
        return _FakeStream([b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n', b"data: [DONE]\n\n"])


def _build(mask_pii: bool):
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
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-tenant",
        default_model="gpt-4o-mini",
        mask_pii=mask_pii,
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
