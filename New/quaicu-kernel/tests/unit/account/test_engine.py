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


def test_pepper_changes_stored_hash():
    """The same secret hashes to different stored values under different peppers (HMAC keying)."""
    tenant = "acme"
    rec_a, _ = AccountEngine(AccountStore(), EntitlementStore(), pepper="pepper-a").issue_api_key(tenant)
    rec_none, _ = AccountEngine(AccountStore(), EntitlementStore(), pepper="").issue_api_key(tenant)
    # Both are HMAC-SHA256 hex digests (64 chars), but distinct because the pepper differs.
    assert len(rec_a.hashed_secret) == 64
    assert rec_a.hashed_secret != rec_none.hashed_secret


def test_key_does_not_verify_under_a_different_pepper():
    """A key issued under one pepper must not validate against an engine with another pepper."""
    accounts, ents = AccountStore(), EntitlementStore()
    issuer = AccountEngine(accounts, ents, pepper="secret-1")
    _, key = issuer.signup(email="a@b.io", name="Acme")

    # A second engine over the SAME store but a different pepper recomputes a different HMAC.
    other = AccountEngine(accounts, ents, pepper="secret-2")
    with pytest.raises(ApiKeyInvalidError):
        other.verify_api_key(key)

    # Same pepper still verifies.
    same = AccountEngine(accounts, ents, pepper="secret-1")
    assert same.verify_api_key(key) is not None
