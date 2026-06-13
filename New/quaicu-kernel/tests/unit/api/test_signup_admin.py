"""Signup + admin API routes, and shared-plane provider wiring (ADR-0009 / ADR-0010)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from core.account import AccountEngine, AccountStore
from core.entitlements import EntitlementEngine, EntitlementStore, FeatureTier
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


def _kernel(tenant: str, *, with_policy_store: bool = False) -> Kernel:
    from core.policy import PolicyStore

    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
        policy_store=PolicyStore() if with_policy_store else None,
    )


def _control_plane_app(admin_token: str | None = "secret-admin"):
    """Single-kernel app with the control-plane singletons attached (signup + admin enabled)."""
    ents = EntitlementStore()
    accounts = AccountStore()
    return (
        create_app(
            _kernel("ciro-bank"),
            account_engine=AccountEngine(accounts, ents),
            entitlement_store=ents,
            admin_token=admin_token,
        ),
        ents,
    )


# ── Signup ─────────────────────────────────────────────────────────────────────


async def test_signup_returns_201_with_key_and_starter():
    app, ents = _control_plane_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/signup", json={"email": "a@b.io", "name": "Acme"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["tier"] == "STARTER"
    assert data["api_key"].startswith("qk_")
    assert EntitlementEngine(ents).tier_for(TenantId(data["tenant_id"])) is FeatureTier.STARTER


async def test_duplicate_signup_returns_409():
    app, _ = _control_plane_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/signup", json={"email": "a@b.io", "name": "Acme"})
        resp = await client.post("/v1/signup", json={"email": "a@b.io", "name": "Acme"})
    assert resp.status_code == 409


async def test_signup_disabled_returns_503():
    app = create_app(_kernel("ciro-bank"))  # no account_engine wired
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/signup", json={"email": "a@b.io", "name": "Acme"})
    assert resp.status_code == 503


# ── Admin ──────────────────────────────────────────────────────────────────────


async def test_admin_set_tier_flow():
    app, _ = _control_plane_app()
    admin = {"Authorization": "Bearer secret-admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        signup = (await client.post("/v1/signup", json={"email": "a@b.io", "name": "Acme"})).json()
        tenant = signup["tenant_id"]

        listed = await client.get("/v1/admin/tenants", headers=admin)
        assert listed.status_code == 200
        assert any(t["tenant_id"] == tenant for t in listed.json())

        upgraded = await client.post(
            f"/v1/admin/tenants/{tenant}/tier", json={"tier": "BUSINESS"}, headers=admin
        )
        assert upgraded.status_code == 200
        assert upgraded.json()["tier"] == "BUSINESS"


async def test_admin_requires_token():
    app, _ = _control_plane_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/tenants")  # no token
    assert resp.status_code == 401


async def test_admin_wrong_token_forbidden():
    app, _ = _control_plane_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/tenants", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 403


async def test_admin_disabled_when_no_token_configured():
    app, _ = _control_plane_app(admin_token=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/tenants", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 503


# ── Shared-plane provider wiring ─────────────────────────────────────────────────


def _saas_app():
    ents = EntitlementStore()
    from datetime import datetime, timezone

    from core.entitlements import CustomerPlan, PlanStatus

    now = datetime.now(timezone.utc)
    ents.upsert(CustomerPlan("starter-co", FeatureTier.STARTER, PlanStatus.ACTIVE, now, now))
    ents.upsert(CustomerPlan("biz-co", FeatureTier.BUSINESS, PlanStatus.ACTIVE, now, now))
    provider = TieredKernelProvider(
        {
            FeatureTier.STARTER: _kernel("starter-co", with_policy_store=False),
            FeatureTier.BUSINESS: _kernel("biz-co", with_policy_store=True),
        },
        EntitlementEngine(ents),
    )
    return create_app(provider=provider), provider


async def test_health_reports_shared_plane():
    app, _ = _saas_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "shared-plane"
    assert set(body["served_tiers"]) == {"STARTER", "BUSINESS"}


async def test_provider_routes_by_tier_with_structural_isolation():
    _, provider = _saas_app()
    # Starter tenant lands on a kernel that physically lacks the CEL policy store...
    assert provider.kernel_for(TenantId("starter-co")).has_policy_store is False
    # ...while the Business tenant's kernel has it. Tier isolation is structural, not a flag.
    assert provider.kernel_for(TenantId("biz-co")).has_policy_store is True


async def test_propose_in_provider_mode_without_tenant_returns_401():
    app, _ = _saas_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # bearer token is not a JWT and no X-Tenant-Id header → tenant cannot be resolved for routing
        resp = await client.post(
            "/v1/actions/propose",
            json={"type": "t", "payload": {}, "idempotency_key": "ik-1"},
            headers={"Authorization": "Bearer opaque"},
        )
    assert resp.status_code == 401


async def test_propose_routes_to_tenant_kernel_and_stamps_request_tenant():
    app, _ = _saas_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for tenant in ("biz-co", "starter-co"):
            resp = await client.post(
                "/v1/actions/propose",
                json={"type": "t", "payload": {}, "idempotency_key": f"ik-{tenant}"},
                headers={"Authorization": "Bearer opaque", "X-Tenant-Id": tenant},
            )
            assert resp.status_code == 202, resp.text
            # The action is stamped with the REQUEST tenant, not the tier kernel's fixed tenant.
            assert resp.json()["tenant"] == tenant


async def test_ledger_isolation_uses_request_tenant_in_provider_mode():
    app, _ = _saas_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Routed to the business kernel (X-Tenant-Id), but asking for another tenant's trail → 403.
        resp = await client.get(
            "/v1/ledger/starter-co/trail",
            headers={"Authorization": "Bearer opaque", "X-Tenant-Id": "biz-co"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "TENANT_ISOLATION"
