"""Account engine — self-serve signup, default STARTER plan, API-key auth (ADR-0010)."""

from __future__ import annotations

import pytest

from core.account import AccountEngine, AccountStore
from core.entitlements import EntitlementEngine, EntitlementStore, FeatureTier
from core.errors import AccountExistsError, ApiKeyInvalidError


def _engine() -> tuple[AccountEngine, EntitlementStore]:
    ents = EntitlementStore()
    return AccountEngine(AccountStore(), ents), ents


def test_signup_creates_starter_tenant_and_key():
    eng, ents = _engine()
    account, key = eng.signup(email="a@b.io", name="Acme")
    assert key.startswith("qk_")
    assert EntitlementEngine(ents).tier_for(account.tenant_id) is FeatureTier.STARTER


def test_signup_is_idempotent_per_email():
    eng, _ = _engine()
    eng.signup(email="a@b.io", name="Acme")
    with pytest.raises(AccountExistsError):
        eng.signup(email="a@b.io", name="Acme Again")


def test_issued_key_verifies_to_account():
    eng, _ = _engine()
    account, key = eng.signup(email="a@b.io", name="Acme")
    assert eng.verify_api_key(key).account_id == account.account_id


def test_revoked_key_rejected():
    eng, _ = _engine()
    _, key = eng.signup(email="a@b.io", name="Acme")
    eng.revoke_api_key(key.split("_")[1])
    with pytest.raises(ApiKeyInvalidError):
        eng.verify_api_key(key)


def test_malformed_or_wrong_secret_rejected():
    eng, _ = _engine()
    _, key = eng.signup(email="a@b.io", name="Acme")
    with pytest.raises(ApiKeyInvalidError):
        eng.verify_api_key("qk_bad_key")
    with pytest.raises(ApiKeyInvalidError):
        eng.verify_api_key(key + "tampered")


def test_each_signup_gets_distinct_tenant():
    eng, _ = _engine()
    a, _ = eng.signup(email="a@b.io", name="Acme")
    b, _ = eng.signup(email="c@d.io", name="Acme")  # same name, different email
    assert a.tenant_id != b.tenant_id
