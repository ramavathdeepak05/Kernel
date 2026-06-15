"""Unit tests for POST /v1/billing/checkout (WS-C, outbound).

The route is the authenticated, tenant-isolated, scoped counterpart to the signature-authenticated
webhook. A fake CheckoutPort adapter stands in for Stripe/Razorpay so no network is touched.
"""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.billing.model import CheckoutSession
from core.entitlements import EntitlementStore
from core.errors import CheckoutError
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import (
    FakeEvents,
    FakeHITL,
    FakeIdentity,
    FakeLedger,
    FakePolicy,
)

TENANT = "acme"
AUTH = {"Authorization": "Bearer test-token"}


class FakeCheckout:
    """A CheckoutPort stand-in (structural: has `provider` + async `create_checkout`)."""

    provider = "stripe"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.received: dict | None = None

    async def create_checkout(self, *, tenant, tier, success_url=None, cancel_url=None, customer_email=None):
        if self.fail:
            raise CheckoutError("provider rejected the request")
        self.received = {"tenant": str(tenant), "tier": tier.value, "success_url": success_url}
        return CheckoutSession(
            provider=self.provider, tenant_id=tenant, tier=tier, url="https://pay/x", reference="ref_1"
        )


def _kernel(tenant: str = TENANT) -> Kernel:
    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


def _app(adapter=None, **kw):
    return create_app(_kernel(), billing_adapters={"stripe": adapter} if adapter else {}, **kw)


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


_BODY = {"provider": "stripe", "tier": "BUSINESS", "success_url": "https://a/ok", "cancel_url": "https://a/no"}


async def test_checkout_without_token_is_401():
    async with _client(_app(FakeCheckout())) as c:
        resp = await c.post("/v1/billing/checkout", json=_BODY)
    assert resp.status_code == 401


async def test_checkout_happy_path_returns_url_for_authed_tenant():
    adapter = FakeCheckout()
    async with _client(_app(adapter)) as c:
        resp = await c.post("/v1/billing/checkout", json=_BODY, headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == "https://pay/x"
    assert body["reference"] == "ref_1"
    assert body["tenant"] == TENANT
    assert body["tier"] == "BUSINESS"
    # The checkout is for the *authenticated* tenant, not anything in the body.
    assert adapter.received["tenant"] == TENANT
    assert adapter.received["success_url"] == "https://a/ok"


async def test_checkout_unknown_tier_is_422():
    async with _client(_app(FakeCheckout())) as c:
        resp = await c.post("/v1/billing/checkout", json={**_BODY, "tier": "GOLD"}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "UNKNOWN_TIER"


async def test_checkout_starter_is_422():
    async with _client(_app(FakeCheckout())) as c:
        resp = await c.post("/v1/billing/checkout", json={**_BODY, "tier": "STARTER"}, headers=AUTH)
    assert resp.status_code == 422


async def test_checkout_unknown_provider_is_503():
    async with _client(_app(FakeCheckout())) as c:
        resp = await c.post("/v1/billing/checkout", json={**_BODY, "provider": "paypal"}, headers=AUTH)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "BILLING_DISABLED"


async def test_checkout_provider_failure_is_502():
    async with _client(_app(FakeCheckout(fail=True))) as c:
        resp = await c.post("/v1/billing/checkout", json=_BODY, headers=AUTH)
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "CHECKOUT_FAILED"


# ── Auth middleware: checkout is protected, webhook stays exempt ─────────────────────


def _add_account(accounts: AccountStore, tenant: str) -> None:
    accounts.add_account(
        Account(
            account_id=f"acct_{tenant}",
            tenant_id=TenantId(tenant),
            email=f"{tenant}@b.io",
            name=tenant,
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )


async def test_checkout_is_api_key_protected_when_auth_enabled():
    eng = AccountEngine(accounts := AccountStore(), EntitlementStore())
    _add_account(accounts, TENANT)
    app = create_app(
        _kernel(),
        billing_adapters={"stripe": FakeCheckout()},
        account_engine=eng,
        require_api_key=True,
        rate_limit=False,
    )
    async with _client(app) as c:
        # No API key → checkout is rejected by the middleware (it is NOT exempt).
        checkout = await c.post("/v1/billing/checkout", json=_BODY)
        # The webhook path stays exempt (no API key required) — reaches the route, 503 (no engine wired).
        webhook = await c.post("/v1/billing/webhook/stripe", content=b"{}")
    assert checkout.status_code == 401
    assert checkout.json()["code"] == "API_KEY_REQUIRED"
    assert webhook.status_code != 401
