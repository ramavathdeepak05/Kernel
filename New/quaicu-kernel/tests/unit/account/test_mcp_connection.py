"""Per-tenant BYO downstream MCP connection storage: round-trip + secret encrypted at rest."""

from __future__ import annotations

from datetime import datetime, timezone

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.entitlements import EntitlementStore
from core.types import TenantId

_TENANT = TenantId("acme")


def _engine() -> AccountEngine:
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="a", tenant_id=_TENANT, email="a@b.io", name="acme",
            status=AccountStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        )
    )
    return AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")


def test_set_get_roundtrip_decrypts_secret():
    eng = _engine()
    eng.set_mcp_connection(_TENANT, url="https://tools.acme.io/mcp/", auth_value="Bearer sekret", name="acme")
    conn = eng.get_mcp_connection(_TENANT)
    assert conn is not None
    assert conn.url == "https://tools.acme.io/mcp"  # trailing slash stripped
    assert conn.auth_value == "Bearer sekret"
    assert conn.auth_header == "Authorization"
    assert conn.transport == "streamable_http"


def test_status_masks_the_secret():
    eng = _engine()
    eng.set_mcp_connection(_TENANT, url="https://tools.acme.io/mcp", auth_value="Bearer sekret")
    status = eng.mcp_connection_status(_TENANT)
    assert status["connected"] is True and status["auth_set"] is True
    assert "sekret" not in str(status)  # secret never surfaced


def test_secret_encrypted_at_rest():
    eng = _engine()
    eng.set_mcp_connection(_TENANT, url="https://x/mcp", auth_value="Bearer topsecret")
    account = eng._accounts.get_account_by_tenant(_TENANT)  # type: ignore[attr-defined]
    raw = account.profile["mcp_connection"]
    assert "topsecret" not in str(raw)  # stored ciphertext, not plaintext
    assert raw["enc_auth"]  # an encrypted blob is present


def test_clear_removes_connection():
    eng = _engine()
    eng.set_mcp_connection(_TENANT, url="https://x/mcp")
    assert eng.clear_mcp_connection(_TENANT) is True
    assert eng.get_mcp_connection(_TENANT) is None
    assert eng.clear_mcp_connection(_TENANT) is False  # idempotent


def test_no_connection_returns_none():
    assert _engine().get_mcp_connection(_TENANT) is None
    assert _engine().mcp_connection_status(_TENANT) is None
