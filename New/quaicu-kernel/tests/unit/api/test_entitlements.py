"""Unit tests for GET /v1/me/entitlements — the console's per-tier UI gating source (WS-D).

Covers the three resolution shapes: no entitlement source (dedicated single-kernel → everything on),
a wired store with an ACTIVE plan (features derived from TIER_MATRIX), an unprovisioned tenant
(fail-closed → everything off), and the shared-plane provider path.
"""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.entitlements import (
    CustomerPlan,
    EntitlementEngine,
    EntitlementStore,
    FeatureTier,
    PlanStatus,
)
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from delivery.sdk.provider import TieredKernelProvider
from tests.unit.lifecycle.fakes import (
    FakeEvents,
    FakeHITL,
    FakeIdentity,
    FakeLedger,
    FakePolicy,
)

TENANT = TenantId("acme")
AUTH = {"Authorization": "Bearer test-token"}


def _kernel(tenant: TenantId = TENANT) -> Kernel:
    return Kernel.from_parts(
        tenant=tenant,
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


def _store_with(tier: FeatureTier, *, tenant: TenantId = TENANT, status=PlanStatus.ACTIVE) -> EntitlementStore:
    store = EntitlementStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        CustomerPlan(
            tenant_id=tenant,
            tier=tier,
            status=status,
            created_at=now,
            updated_at=now,
        )
    )
    return store


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Auth ─────────────────────────────────────────────────────────────────────────


async def test_without_token_returns_401():
    async with _client(create_app(_kernel())) as c:
        resp = await c.get("/v1/me/entitlements")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── No entitlement source: dedicated single-kernel, not tier-limited ────────────────


async def test_no_entitlement_source_is_unlimited():
    async with _client(create_app(_kernel())) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant"] == "acme"
    assert body["tier"] is None
    assert body["status"] is None
    # Everything is shown on a dedicated deploy.
    assert all(body["features"].values())
    assert body["quotas"] == {}
    # No billing wired → no providers to offer.
    assert body["billing_providers"] == []


# ── Wired store: features derived from TIER_MATRIX ──────────────────────────────────


async def test_starter_governs_but_hides_inference():
    app = create_app(_kernel(), entitlement_store=_store_with(FeatureTier.STARTER))
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "STARTER"
    assert body["status"] == "ACTIVE"
    f = body["features"]
    # STARTER is now governance-capable (in-memory CEL engine + a small policy allowance).
    assert f["policies"] is True           # max_policies = 200 (shared durable plane)
    assert f["policy_simulate"] is True    # CEL engine present
    assert f["approvals"] is True          # the enforcing `standard` profile is allowed
    assert f["inference"] is False         # still no inference adapter on the free tier
    assert f["dashboard"] is True and f["audit"] is True
    assert body["quotas"]["max_policies"] == 200
    assert body["quotas"]["rate_limit_per_min"] == 60


async def test_business_enables_policy_and_gateway_features():
    app = create_app(_kernel(), entitlement_store=_store_with(FeatureTier.BUSINESS))
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    body = resp.json()
    assert body["tier"] == "BUSINESS"
    f = body["features"]
    assert f["policies"] is True
    assert f["policy_simulate"] is True
    assert f["inference"] is True
    assert f["approvals"] is True
    assert body["quotas"]["max_policies"] == 1000


async def test_enterprise_is_unbounded():
    app = create_app(_kernel(), entitlement_store=_store_with(FeatureTier.ENTERPRISE))
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    body = resp.json()
    assert body["tier"] == "ENTERPRISE"
    assert all(body["features"].values())
    assert body["quotas"]["max_actions_per_day"] == -1


# ── Fail-closed: provisioned source, but no ACTIVE plan for the tenant ──────────────


async def test_unprovisioned_tenant_fails_closed():
    # Store exists but holds a *different* tenant's plan → this tenant resolves to nothing.
    store = _store_with(FeatureTier.BUSINESS, tenant=TenantId("someone-else"))
    app = create_app(_kernel(), entitlement_store=store)
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] is None
    assert body["status"] == "NO_ACTIVE_PLAN"
    assert not any(body["features"].values())  # nothing tier-gated is shown


async def test_suspended_plan_fails_closed():
    store = _store_with(FeatureTier.BUSINESS, status=PlanStatus.SUSPENDED)
    app = create_app(_kernel(), entitlement_store=store)
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    body = resp.json()
    assert body["status"] == "NO_ACTIVE_PLAN"
    assert not any(body["features"].values())


# ── Shared-plane provider mode ──────────────────────────────────────────────────────


class _FakeCheckout:
    """A checkout-capable billing adapter stand-in (structural CheckoutPort)."""

    provider = "stripe"

    async def create_checkout(self, *, tenant, tier, success_url=None, cancel_url=None, customer_email=None):
        raise NotImplementedError  # presence is enough for the providers list


async def test_billing_providers_reported_when_checkout_wired():
    app = create_app(
        _kernel(),
        entitlement_store=_store_with(FeatureTier.BUSINESS),
        billing_adapters={"stripe": _FakeCheckout()},
    )
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["billing_providers"] == ["stripe"]


async def test_provider_mode_resolves_tenant_tier():
    tenant = TenantId("biz-co")
    store = _store_with(FeatureTier.BUSINESS, tenant=tenant)
    provider = TieredKernelProvider(
        {FeatureTier.BUSINESS: _kernel(tenant)}, EntitlementEngine(store)
    )
    app = create_app(provider=provider)
    headers = {"Authorization": "Bearer opaque", "X-Tenant-Id": "biz-co"}
    async with _client(app) as c:
        resp = await c.get("/v1/me/entitlements", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant"] == "biz-co"
    assert body["tier"] == "BUSINESS"
    assert body["features"]["policies"] is True
