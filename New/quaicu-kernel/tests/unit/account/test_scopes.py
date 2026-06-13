"""RBAC scopes on API keys (ADR-0011, WS-D)."""

from __future__ import annotations

import pytest

from core.account import (
    ALL_SCOPES,
    AccountEngine,
    AccountStore,
    AuthenticatedPrincipal,
    normalize_scopes,
)
from core.account.scopes import LEDGER_READ, POLICY_ADMIN
from core.entitlements import EntitlementStore


def _engine() -> AccountEngine:
    return AccountEngine(AccountStore(), EntitlementStore())


def test_signup_key_gets_all_scopes():
    eng = _engine()
    account, key = eng.signup(email="a@b.io", name="Acme")
    principal = eng.resolve_principal(key)
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.tenant_id == account.tenant_id
    assert principal.scopes == ALL_SCOPES
    assert principal.has_scope(POLICY_ADMIN)


def test_issue_key_with_subset_scopes():
    eng = _engine()
    account, _ = eng.signup(email="a@b.io", name="Acme")
    _, narrow = eng.issue_api_key(account.tenant_id, scopes={LEDGER_READ})
    principal = eng.resolve_principal(narrow)
    assert principal.scopes == frozenset({LEDGER_READ})
    assert principal.has_scope(LEDGER_READ)
    assert not principal.has_scope(POLICY_ADMIN)


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError):
        normalize_scopes({"ledger:read", "totally:bogus"})


def test_none_scopes_means_owner_scopes():
    assert normalize_scopes(None) == ALL_SCOPES


def test_resolve_principal_fails_closed_on_revoked_key():
    from core.errors import ApiKeyInvalidError

    eng = _engine()
    _, key = eng.signup(email="a@b.io", name="Acme")
    eng.revoke_api_key(key.split("_")[1])
    with pytest.raises(ApiKeyInvalidError):
        eng.resolve_principal(key)
