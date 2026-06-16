"""build_account_engine / require_api_key — config-driven signup wiring (ADR-0010)."""

from __future__ import annotations

import pytest

from core.account import AccountEngine
from core.entitlements import EntitlementStore
from delivery.sdk.account_config import account_enabled, build_account_engine, require_api_key


def test_disabled_by_default():
    assert account_enabled({}) is False
    assert build_account_engine({}, EntitlementStore()) is None
    assert require_api_key({}) is False


def test_enabled_builds_engine_and_requires_key():
    cfg = {"account": {"enabled": True}}
    eng = build_account_engine(cfg, EntitlementStore())
    assert isinstance(eng, AccountEngine)
    assert require_api_key(cfg) is True  # defaults to the enabled flag


def test_enabled_without_entitlement_store_is_fail_closed():
    with pytest.raises(ValueError, match="entitlement source"):
        build_account_engine({"account": {"enabled": True}}, None)


def test_require_api_key_can_be_decoupled_from_enabled():
    cfg = {"account": {"enabled": True, "require_api_key": False}}
    assert build_account_engine(cfg, EntitlementStore()) is not None
    assert require_api_key(cfg) is False


def test_signup_works_when_wired_end_to_end():
    # The engine built from config provisions a STARTER tenant + key (what POST /v1/signup calls).
    ents = EntitlementStore()
    eng = build_account_engine({"account": {"enabled": True}}, ents)
    account, key = eng.signup(email="founder@acme.io", name="Acme")
    assert key.startswith("qk_")
    assert ents.get(account.tenant_id) is not None  # STARTER plan landed in the shared store
