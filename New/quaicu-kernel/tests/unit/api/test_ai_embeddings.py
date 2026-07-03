"""D2-2: governed embeddings endpoint — ai.embed seal + PII masking + budget + provider support."""

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
_PII = "email me at bob@acme.io"


class _EmbedClient:
    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _EmbedClient.captured = {"url": url, "body": json, "headers": headers}

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"object": "list", "data": [{"embedding": [0.1, 0.2], "index": 0}]}

            text = ""

        return _Resp()


def _build(policy, *, provider="openai", base_url="https://api.openai.com/v1", mask_pii=False):
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme", tenant_id=TenantId(_TENANT), email="acme@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    eng.set_ai_connection(
        TenantId(_TENANT), provider=provider, base_url=base_url, api_key="sk-tenant",
        default_model="text-embedding-3-small", mask_pii=mask_pii,
    )
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT), policy=policy, hitl=FakeHITL(), ledger=FakeLedger(),
        events=FakeEvents(), identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))
    return app, eng, key


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "X-Tenant-Id": _TENANT}


async def _embed(app, key, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/ai/embeddings", headers=_auth(key), json=body)


async def test_embeddings_allowed_forwards_and_returns_vectors(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _EmbedClient)
    app, _, key = _build(FakePolicy(decision=Decision.ALLOW))
    resp = await _embed(app, key, {"input": ["hello"]})
    assert resp.status_code == 200
    assert resp.json()["data"][0]["embedding"] == [0.1, 0.2]
    assert _EmbedClient.captured["url"] == "https://api.openai.com/v1/embeddings"


async def test_embeddings_denied_by_governance_returns_403(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _EmbedClient)
    app, _, key = _build(FakePolicy(decision=Decision.DENY))
    resp = await _embed(app, key, {"input": ["hello"]})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "GOVERNANCE_DENIED"


async def test_embeddings_masks_pii_before_forwarding(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _EmbedClient)
    app, _, key = _build(FakePolicy(decision=Decision.ALLOW), mask_pii=True)
    resp = await _embed(app, key, {"input": [_PII]})
    assert resp.status_code == 200
    forwarded = json.dumps(_EmbedClient.captured["body"])
    assert "bob@acme.io" not in forwarded and "[MASKED:" in forwarded


async def test_embeddings_budget_exhaustion_returns_429(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _EmbedClient)
    app, _, key = _build(FakePolicy(decision=Decision.ALLOW))
    app.state.ai_budget.set_budget(TenantId(_TENANT), max_tokens=1)
    resp = await _embed(app, key, {"input": ["x" * 400]})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "BUDGET_EXCEEDED"


async def test_embeddings_unsupported_provider_returns_501(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _EmbedClient)
    app, _, key = _build(FakePolicy(decision=Decision.ALLOW),
                         provider="anthropic", base_url="https://api.anthropic.com")
    resp = await _embed(app, key, {"input": ["hello"]})
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_SUPPORTED"
