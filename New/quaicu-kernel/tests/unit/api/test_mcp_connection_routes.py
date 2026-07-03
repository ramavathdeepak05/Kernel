"""/v1/mcp/connection — set/get/delete the tenant's BYO downstream MCP server (secret masked)."""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.entitlements import EntitlementStore
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy

_TENANT = "acme"


def _build():
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme", tenant_id=TenantId(_TENANT), email="acme@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT), policy=FakePolicy(decision=Decision.ALLOW), hitl=FakeHITL(),
        ledger=FakeLedger(), events=FakeEvents(), identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))
    return app, eng, key


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "X-Tenant-Id": _TENANT}


async def test_put_get_delete_roundtrip_masks_secret():
    app, _, key = _build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Not connected yet.
        r0 = await client.get("/v1/mcp/connection", headers=_auth(key))
        assert r0.json() == {"connected": False}

        # Register a downstream.
        r1 = await client.put(
            "/v1/mcp/connection", headers=_auth(key),
            json={"url": "https://tools.acme.io/mcp/", "auth_value": "Bearer sekret", "name": "acme"},
        )
        assert r1.status_code == 200
        body = r1.json()
        assert body["connected"] is True and body["url"] == "https://tools.acme.io/mcp"
        assert body["auth_set"] is True and "sekret" not in str(body)  # secret masked

        # Get echoes the masked status.
        r2 = await client.get("/v1/mcp/connection", headers=_auth(key))
        assert r2.json()["url"] == "https://tools.acme.io/mcp"

        # Delete removes it.
        r3 = await client.delete("/v1/mcp/connection", headers=_auth(key))
        assert r3.json() == {"connected": False, "removed": True}
        r4 = await client.get("/v1/mcp/connection", headers=_auth(key))
        assert r4.json() == {"connected": False}


async def test_put_requires_url():
    app, _, key = _build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.put("/v1/mcp/connection", headers=_auth(key), json={"url": "   "})
    assert r.status_code == 422


async def test_sse_transport_roundtrips():
    app, _, key = _build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.put(
            "/v1/mcp/connection", headers=_auth(key),
            json={"url": "https://tools.acme.io/sse", "transport": "sse"},
        )
        assert r.status_code == 200 and r.json()["transport"] == "sse"


async def test_invalid_transport_rejected():
    app, _, key = _build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.put(
            "/v1/mcp/connection", headers=_auth(key),
            json={"url": "https://x/mcp", "transport": "websocket"},
        )
    assert r.status_code == 422
