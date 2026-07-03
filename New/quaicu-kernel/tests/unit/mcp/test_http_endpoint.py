"""Hosted MCP endpoint wired into the app: mounted at /mcp, lifespan runs the session manager,
unauthenticated requests are rejected (401) before reaching the transport."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("mcp")

from fastapi.testclient import TestClient  # noqa: E402

from core.account import Account, AccountEngine, AccountStatus, AccountStore  # noqa: E402
from core.entitlements import EntitlementStore  # noqa: E402
from core.hitl.engine import InProcessHITLPort  # noqa: E402
from core.types import Decision, TenantId  # noqa: E402
from delivery.api.app import create_app  # noqa: E402
from delivery.mcp.server import GovernedMCPServer  # noqa: E402
from delivery.sdk.kernel import Kernel  # noqa: E402
from tests.unit.lifecycle.fakes import FakeEvents, FakeLedger, FakePolicy  # noqa: E402

_TENANT = "acme"


class _StubProvider:
    """Minimal shared-plane provider: one kernel for every tenant (enough for the mount/auth test)."""

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel
        self.entitlements = None

    def kernel_for(self, tenant: TenantId) -> Kernel:
        return self._kernel

    def served_tiers(self):
        return set()

    async def startup(self) -> None:  # called by create_app lifespan
        pass

    async def shutdown(self) -> None:
        pass


def _build():
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme", tenant_id=TenantId(_TENANT), email="acme@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    _, key = eng.issue_api_key(TenantId(_TENANT))
    kernel = Kernel.from_parts(
        tenant=_TENANT, policy=FakePolicy(decision=Decision.ALLOW), hitl=InProcessHITLPort(),
        ledger=FakeLedger(), events=FakeEvents(),
    )
    mcp_server = GovernedMCPServer(name="hosted")
    mcp_server.register_tool("echo", handler=lambda a: {"echo": a}, policy="mcp.tool")
    app = create_app(
        provider=_StubProvider(kernel), account_engine=eng, mcp_server=mcp_server, rate_limit=False
    )
    return app, key


_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "t", "version": "1"}},
}


def test_mcp_unauthenticated_is_rejected():
    app, _ = _build()
    with TestClient(app) as client:  # context-manager form runs the lifespan (session manager)
        r = client.post("/mcp", json=_INIT)
    assert r.status_code == 401
    assert r.json()["code"] == "API_KEY_REQUIRED"


def test_mcp_authenticated_reaches_transport():
    app, key = _build()
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        r = client.post("/mcp", headers=headers, json=_INIT)
    # A valid key gets past the auth gate into the MCP transport (which answers the handshake). The
    # point is only that it is NOT the 401 the auth gate returns.
    assert r.status_code != 401
