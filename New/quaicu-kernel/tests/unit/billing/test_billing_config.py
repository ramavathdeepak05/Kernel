"""Unit tests for config-driven billing wiring — build_billing (WS-C)."""

from __future__ import annotations

import pytest

from adapters.billing import RazorpayBillingAdapter, StripeBillingAdapter
from core.billing import BillingEngine
from core.billing.port import CheckoutPort
from core.entitlements import EntitlementStore, FeatureTier
from delivery.sdk.billing_config import build_billing


def _store() -> EntitlementStore:
    return EntitlementStore()


# ── Absent / empty section: billing stays disabled ─────────────────────────────────


def test_no_billing_section_is_noop():
    adapters, engine = build_billing({"tenant": {"id": "x"}}, _store())
    assert adapters == {}
    assert engine is None


def test_empty_billing_section_is_noop():
    adapters, engine = build_billing({"billing": {}}, _store())
    assert adapters == {} and engine is None


# ── Provider construction ───────────────────────────────────────────────────────────


def test_stripe_only_builds_adapter_and_engine():
    config = {
        "billing": {
            "stripe": {
                "webhook_secret": "whsec_x",
                "api_key": "sk_test",
                "price_to_tier": {"price_business": "BUSINESS", "price_enterprise": "ENTERPRISE"},
            }
        }
    }
    adapters, engine = build_billing(config, _store())
    assert set(adapters) == {"stripe"}
    assert isinstance(adapters["stripe"], StripeBillingAdapter)
    assert isinstance(adapters["stripe"], CheckoutPort)  # api_key present → checkout-capable
    assert isinstance(engine, BillingEngine)
    # The price→tier map parsed into the enum.
    assert adapters["stripe"]._price_to_tier["price_business"] is FeatureTier.BUSINESS


def test_razorpay_builds_adapter():
    config = {
        "billing": {
            "razorpay": {
                "webhook_secret": "whsec_x",
                "key_id": "rzp_id",
                "key_secret": "rzp_secret",
                "plan_to_tier": {"plan_business": "BUSINESS"},
            }
        }
    }
    adapters, engine = build_billing(config, _store())
    assert isinstance(adapters["razorpay"], RazorpayBillingAdapter)
    assert isinstance(engine, BillingEngine)


def test_both_providers_built():
    config = {
        "billing": {
            "stripe": {"webhook_secret": "a", "price_to_tier": {"price_business": "BUSINESS"}},
            "razorpay": {"webhook_secret": "b", "plan_to_tier": {"plan_business": "BUSINESS"}},
        }
    }
    adapters, _ = build_billing(config, _store())
    assert set(adapters) == {"stripe", "razorpay"}


# ── ${ENV} substitution ─────────────────────────────────────────────────────────────


def test_env_var_substitution_resolves_secrets(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_from_env")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_from_env")
    config = {
        "billing": {
            "stripe": {
                "webhook_secret": "${STRIPE_WEBHOOK_SECRET}",
                "api_key": "${STRIPE_API_KEY}",
                "price_to_tier": {"price_business": "BUSINESS"},
            }
        }
    }
    adapters, _ = build_billing(config, _store())
    adapter = adapters["stripe"]
    assert adapter._secret == "whsec_from_env"
    assert adapter._api_key == "sk_from_env"


# ── Fail-closed ─────────────────────────────────────────────────────────────────────


def test_missing_webhook_secret_raises():
    config = {"billing": {"stripe": {"price_to_tier": {"price_business": "BUSINESS"}}}}
    with pytest.raises(ValueError, match="webhook_secret"):
        build_billing(config, _store())


def test_unknown_tier_in_map_raises():
    config = {
        "billing": {"stripe": {"webhook_secret": "a", "price_to_tier": {"price_x": "PLATINUM"}}}
    }
    with pytest.raises(ValueError, match="unknown tier"):
        build_billing(config, _store())


def test_webhook_only_adapter_is_not_checkout_capable():
    # No api_key → the adapter verifies webhooks but cannot create a checkout.
    config = {"billing": {"stripe": {"webhook_secret": "a", "price_to_tier": {"price_business": "BUSINESS"}}}}
    adapters, _ = build_billing(config, _store())
    assert adapters["stripe"]._api_key is None


def test_unresolved_env_ref_raises(monkeypatch):
    # An unset ${VAR} must fail loudly, not pass the literal token through as a (truthy) secret —
    # otherwise the adapter would build with a bogus key and silently 403 every real webhook.
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    config = {
        "billing": {
            "razorpay": {
                "webhook_secret": "${RAZORPAY_WEBHOOK_SECRET}",
                "plan_to_tier": {"plan_business": "BUSINESS"},
            }
        }
    }
    with pytest.raises(ValueError, match="RAZORPAY_WEBHOOK_SECRET"):
        build_billing(config, _store())
