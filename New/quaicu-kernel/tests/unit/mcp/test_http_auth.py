"""Per-tenant MCP authenticator: API key → (tenant, actor, kernel). Fail-closed on bad/missing key."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.entitlements import EntitlementStore
from core.errors import ApiKeyInvalidError
from core.types import TenantId
from delivery.mcp.auth import MCPAuthenticator


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _StubProvider:
    """Records the tenant kernel_for was asked for; returns a sentinel kernel."""

    def __init__(self, kernel: object) -> None:
        self.kernel = kernel
        self.asked: list[str] = []

    def kernel_for(self, tenant: TenantId) -> object:
        self.asked.append(str(tenant))
        return self.kernel


def _engine_with_key(tenant: str) -> tuple[AccountEngine, str]:
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id=f"acct_{tenant}", tenant_id=TenantId(tenant), email=f"{tenant}@b.io",
            name=tenant, status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    _, key = eng.issue_api_key(TenantId(tenant))
    return eng, key


def test_resolve_valid_key_yields_tenant_actor_kernel():
    eng, key = _engine_with_key("acme")
    sentinel = object()
    provider = _StubProvider(sentinel)
    auth = MCPAuthenticator(eng, provider)

    session = auth.resolve(_FakeRequest({"authorization": f"Bearer {key}"}))

    assert str(session.tenant) == "acme"
    assert session.kernel is sentinel
    assert provider.asked == ["acme"]
    assert str(session.actor.tenant) == "acme"
    assert str(session.actor.id)  # a concrete actor id (subject / account id)


def test_missing_bearer_raises():
    eng, _ = _engine_with_key("acme")
    auth = MCPAuthenticator(eng, _StubProvider(object()))
    with pytest.raises(ApiKeyInvalidError):
        auth.resolve(_FakeRequest({}))


def test_unknown_key_raises():
    eng, _ = _engine_with_key("acme")
    auth = MCPAuthenticator(eng, _StubProvider(object()))
    with pytest.raises(ApiKeyInvalidError):
        auth.resolve(_FakeRequest({"authorization": "Bearer qk_bogus_nope"}))
