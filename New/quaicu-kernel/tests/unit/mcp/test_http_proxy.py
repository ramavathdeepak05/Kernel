"""BYO-downstream proxy wiring: per-request resolver (auth → tenant downstream) + app mount."""

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
from delivery.mcp.auth import MCPAuthenticator  # noqa: E402
from delivery.mcp.downstream import HttpDownstream  # noqa: E402
from delivery.mcp.http import build_proxy_resolver  # noqa: E402
from delivery.mcp.proxy import GovernedMCPProxy, ProxySession  # noqa: E402
from delivery.sdk.kernel import Kernel  # noqa: E402
from tests.unit.lifecycle.fakes import FakeEvents, FakeLedger, FakePolicy  # noqa: E402

_TENANT = "acme"


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def _kernel() -> Kernel:
    return Kernel.from_parts(
        tenant=_TENANT, policy=FakePolicy(decision=Decision.ALLOW), hitl=InProcessHITLPort(),
        ledger=FakeLedger(), events=FakeEvents(),
    )


class _StubProvider:
    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel
        self.entitlements = None

    def kernel_for(self, tenant):
        return self._kernel

    def served_tiers(self):
        return set()

    async def startup(self):
        pass

    async def shutdown(self):
        pass


def _engine_with_key() -> tuple[AccountEngine, str]:
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme", tenant_id=TenantId(_TENANT), email="acme@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    _, key = eng.issue_api_key(TenantId(_TENANT))
    return eng, key


def test_proxy_resolver_fails_closed_without_downstream():
    eng, key = _engine_with_key()
    resolve = build_proxy_resolver(MCPAuthenticator(eng, _StubProvider(_kernel())), eng)
    with pytest.raises(RuntimeError, match="no downstream"):
        resolve(_FakeRequest({"authorization": f"Bearer {key}"}))


def test_proxy_resolver_builds_session_from_connection():
    eng, key = _engine_with_key()
    eng.set_mcp_connection(TenantId(_TENANT), url="https://tools.acme.io/mcp", auth_value="Bearer sk")
    resolve = build_proxy_resolver(MCPAuthenticator(eng, _StubProvider(_kernel())), eng)

    session = resolve(_FakeRequest({"authorization": f"Bearer {key}"}))

    assert isinstance(session, ProxySession)
    assert isinstance(session.downstream, HttpDownstream)
    assert str(session.actor.tenant) == _TENANT


def test_create_app_rejects_both_server_and_proxy():
    eng, _ = _engine_with_key()
    with pytest.raises(ValueError, match="at most one"):
        create_app(
            provider=_StubProvider(_kernel()), account_engine=eng,
            mcp_server=GovernedMCPProxy(name="x"), mcp_proxy=GovernedMCPProxy(name="y"),
        )


def test_proxy_endpoint_unauthenticated_is_rejected():
    eng, _ = _engine_with_key()
    proxy = GovernedMCPProxy(name="hosted", default_policy="mcp.tool")
    app = create_app(
        provider=_StubProvider(_kernel()), account_engine=eng, mcp_proxy=proxy, rate_limit=False
    )
    with TestClient(app) as client:  # runs the lifespan (session manager)
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r.status_code == 401
    assert r.json()["code"] == "API_KEY_REQUIRED"
