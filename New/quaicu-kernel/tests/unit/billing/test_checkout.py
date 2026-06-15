"""Unit tests for outbound checkout creation — Stripe + Razorpay (WS-C).

The provider HTTP call is injected (`http_post`) so these run with no network and assert the exact
request the adapter builds: the tenant stamped into provider metadata/notes (so the inbound webhook
can attribute it back), the tier→price/plan mapping, and the auth header.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import pytest

from adapters.billing import RazorpayBillingAdapter, StripeBillingAdapter
from core.billing.model import CheckoutSession
from core.entitlements import FeatureTier
from core.errors import CheckoutError
from core.types import TenantId

TENANT = TenantId("acme-co")


class FakeHttp:
    """Records the last POST and returns a canned (status, body)."""

    def __init__(self, status: int = 200, body: str = "{}") -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, bytes, dict]] = []

    async def __call__(self, url: str, body: bytes, headers):
        self.calls.append((url, body, dict(headers)))
        return self.status, self.body


# ── Stripe ────────────────────────────────────────────────────────────────────────

STRIPE_PRICES = {"price_business": FeatureTier.BUSINESS, "price_enterprise": FeatureTier.ENTERPRISE}


def _stripe(http: FakeHttp, *, api_key: str | None = "sk_test") -> StripeBillingAdapter:
    return StripeBillingAdapter(
        webhook_secret="whsec_x",
        price_to_tier=STRIPE_PRICES,
        api_key=api_key,
        http_post=http,
    )


async def test_stripe_checkout_builds_session_and_stamps_tenant():
    http = FakeHttp(body=json.dumps({"id": "cs_1", "url": "https://checkout.stripe.com/pay/cs_1"}))
    adapter = _stripe(http)
    session = await adapter.create_checkout(
        tenant=TENANT,
        tier=FeatureTier.BUSINESS,
        success_url="https://app/ok",
        cancel_url="https://app/no",
        customer_email="ceo@acme.co",
    )
    assert isinstance(session, CheckoutSession)
    assert session.url == "https://checkout.stripe.com/pay/cs_1"
    assert session.reference == "cs_1"
    assert session.tier is FeatureTier.BUSINESS

    url, body, headers = http.calls[-1]
    assert url == "https://api.stripe.com/v1/checkout/sessions"
    assert headers["Authorization"] == "Bearer sk_test"
    form = parse_qs(body.decode())
    assert form["mode"] == ["subscription"]
    assert form["line_items[0][price]"] == ["price_business"]
    # The tenant is stamped where the inbound webhook reads it back.
    assert form["subscription_data[metadata][tenant]"] == ["acme-co"]
    assert form["client_reference_id"] == ["acme-co"]
    assert form["customer_email"] == ["ceo@acme.co"]


async def test_stripe_checkout_not_configured_raises():
    adapter = _stripe(FakeHttp(), api_key=None)
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(
            tenant=TENANT, tier=FeatureTier.BUSINESS, success_url="a", cancel_url="b"
        )


async def test_stripe_checkout_unmapped_tier_raises():
    adapter = _stripe(FakeHttp())
    with pytest.raises(CheckoutError):
        # STARTER has no price in the map.
        await adapter.create_checkout(
            tenant=TENANT, tier=FeatureTier.STARTER, success_url="a", cancel_url="b"
        )


async def test_stripe_checkout_requires_return_urls():
    adapter = _stripe(FakeHttp())
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(tenant=TENANT, tier=FeatureTier.BUSINESS)


async def test_stripe_checkout_provider_error_raises():
    adapter = _stripe(FakeHttp(status=400, body='{"error":{"message":"bad price"}}'))
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(
            tenant=TENANT, tier=FeatureTier.BUSINESS, success_url="a", cancel_url="b"
        )


# ── Razorpay ────────────────────────────────────────────────────────────────────────

RZP_PLANS = {"plan_business": FeatureTier.BUSINESS, "plan_enterprise": FeatureTier.ENTERPRISE}


def _razorpay(http: FakeHttp, *, key_id="rzp_key", key_secret="rzp_secret") -> RazorpayBillingAdapter:
    return RazorpayBillingAdapter(
        webhook_secret="whsec_x",
        plan_to_tier=RZP_PLANS,
        key_id=key_id,
        key_secret=key_secret,
        http_post=http,
    )


async def test_razorpay_checkout_builds_subscription_and_stamps_tenant():
    http = FakeHttp(body=json.dumps({"id": "sub_1", "short_url": "https://rzp.io/i/abc"}))
    adapter = _razorpay(http)
    session = await adapter.create_checkout(tenant=TENANT, tier=FeatureTier.ENTERPRISE)
    assert session.url == "https://rzp.io/i/abc"
    assert session.reference == "sub_1"
    assert session.tier is FeatureTier.ENTERPRISE

    url, body, headers = http.calls[-1]
    assert url == "https://api.razorpay.com/v1/subscriptions"
    expected_auth = "Basic " + base64.b64encode(b"rzp_key:rzp_secret").decode()
    assert headers["Authorization"] == expected_auth
    doc = json.loads(body)
    assert doc["plan_id"] == "plan_enterprise"
    assert doc["notes"]["tenant"] == "acme-co"


async def test_razorpay_checkout_not_configured_raises():
    adapter = _razorpay(FakeHttp(), key_id=None, key_secret=None)
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(tenant=TENANT, tier=FeatureTier.BUSINESS)


async def test_razorpay_checkout_unmapped_tier_raises():
    adapter = _razorpay(FakeHttp())
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(tenant=TENANT, tier=FeatureTier.STARTER)


async def test_razorpay_checkout_provider_error_raises():
    adapter = _razorpay(FakeHttp(status=401, body='{"error":{"description":"unauthorized"}}'))
    with pytest.raises(CheckoutError):
        await adapter.create_checkout(tenant=TENANT, tier=FeatureTier.BUSINESS)
