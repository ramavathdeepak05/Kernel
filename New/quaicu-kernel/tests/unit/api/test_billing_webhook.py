"""Billing webhook route + usage metering + daily-quota enforcement (WS-C)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from adapters.billing import StripeBillingAdapter
from core.billing import BillingEngine
from core.entitlements import CustomerPlan, EntitlementStore, FeatureTier, PlanStatus
from core.metering import UsageMeter
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy

SECRET = "whsec_test"
PRICE_MAP = {"price_business": FeatureTier.BUSINESS}


def _kernel(tenant: str) -> Kernel:
    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


def _app(*, meter: UsageMeter | None = None, plans: list[CustomerPlan] | None = None):
    ents = EntitlementStore()
    for p in plans or []:
        ents.upsert(p)
    adapter = StripeBillingAdapter(webhook_secret=SECRET, price_to_tier=PRICE_MAP)
    app = create_app(
        _kernel("ciro-bank"),
        entitlement_store=ents,
        admin_token="secret-admin",
        billing_adapters={"stripe": adapter},
        billing_engine=BillingEngine(ents),
        usage_meter=meter,
    )
    return app, ents


def _plan(tenant: str, tier=FeatureTier.STARTER, **overrides) -> CustomerPlan:
    now = datetime.now(timezone.utc)
    return CustomerPlan(
        TenantId(tenant), tier, PlanStatus.ACTIVE, now, now, quota_overrides=overrides or {}
    )


def _stripe_headers(body: bytes) -> dict[str, str]:
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}"}


def _sub_body(tenant="ciro-bank", price="price_business") -> bytes:
    obj = {
        "id": "sub_1",
        "status": "active",
        "metadata": {"tenant": tenant},
        "items": {"data": [{"price": {"id": price}}]},
    }
    return json.dumps({"id": "evt_1", "type": "customer.subscription.updated",
                       "data": {"object": obj}}).encode()


# ── Webhook → tier flip ──────────────────────────────────────────────────────────


async def test_webhook_flips_tier():
    app, ents = _app(plans=[_plan("ciro-bank")])  # starts STARTER
    body = _sub_body()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/billing/webhook/stripe", content=body, headers=_stripe_headers(body))
    assert resp.status_code == 200, resp.text
    assert resp.json()["tier"] == "BUSINESS"
    assert ents.get(TenantId("ciro-bank")).tier is FeatureTier.BUSINESS


async def test_webhook_bad_signature_returns_400_and_no_flip():
    app, ents = _app(plans=[_plan("ciro-bank")])
    body = _sub_body()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/billing/webhook/stripe", content=body, headers={"stripe-signature": "t=1,v1=bad"}
        )
    assert resp.status_code == 400
    assert ents.get(TenantId("ciro-bank")).tier is FeatureTier.STARTER  # unchanged


async def test_webhook_unknown_provider_returns_503():
    app, _ = _app()
    body = _sub_body()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/billing/webhook/paypal", content=body, headers=_stripe_headers(body))
    assert resp.status_code == 503


async def test_webhook_is_exempt_from_api_key_auth():
    # Even with require_api_key on, the signature-authenticated webhook is reachable without a key.
    ents = EntitlementStore()
    ents.upsert(_plan("ciro-bank"))
    from core.account import AccountEngine, AccountStore

    adapter = StripeBillingAdapter(webhook_secret=SECRET, price_to_tier=PRICE_MAP)
    app = create_app(
        _kernel("ciro-bank"),
        account_engine=AccountEngine(AccountStore(), ents),
        entitlement_store=ents,
        billing_adapters={"stripe": adapter},
        billing_engine=BillingEngine(ents),
        require_api_key=True,
    )
    body = _sub_body()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/billing/webhook/stripe", content=body, headers=_stripe_headers(body))
    assert resp.status_code == 200, resp.text


# ── Usage metering ───────────────────────────────────────────────────────────────


async def test_successful_request_is_metered():
    meter = UsageMeter()
    app, _ = _app(meter=meter, plans=[_plan("ciro-bank")])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/actions/propose",
            json={"type": "t", "payload": {}, "idempotency_key": "ik-1"},
            headers={"Authorization": "Bearer opaque", "X-Tenant-Id": "ciro-bank"},
        )
    assert resp.status_code == 202, resp.text
    assert meter.actions_today("ciro-bank") == 1


async def test_admin_usage_route_reports_consumption():
    meter = UsageMeter()
    app, _ = _app(meter=meter, plans=[_plan("ciro-bank")])
    meter.record("ciro-bank")
    meter.record("ciro-bank")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/admin/tenants/ciro-bank/usage", headers={"Authorization": "Bearer secret-admin"}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["actions_today"] == 2
    assert body["tier"] == "STARTER"


# ── Daily-quota enforcement ──────────────────────────────────────────────────────


async def test_daily_quota_exceeded_returns_429():
    meter = UsageMeter()
    # Plan with a max_actions_per_day override of 1.
    app, _ = _app(meter=meter, plans=[_plan("ciro-bank", max_actions_per_day=1)])
    meter.record("ciro-bank")  # already at the limit
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/actions/propose",
            json={"type": "t", "payload": {}, "idempotency_key": "ik-2"},
            headers={"Authorization": "Bearer opaque", "X-Tenant-Id": "ciro-bank"},
        )
    assert resp.status_code == 429
    assert resp.json()["code"] == "QUOTA_EXCEEDED"
