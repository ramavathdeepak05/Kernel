"""Per-tenant, per-tier rate limiting middleware (ADR-0011, WS-D)."""

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


def _kernel(tenant: str) -> Kernel:
    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


def _provider_app(tenant: str, *, limit_override: int | None):
    ents = EntitlementStore()
    now = datetime.now(timezone.utc)
    overrides = {"rate_limit_per_min": limit_override} if limit_override is not None else {}
    ents.upsert(
        CustomerPlan(
            tenant_id=TenantId(tenant),
            tier=FeatureTier.STARTER,
            status=PlanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            quota_overrides=overrides,
        )
    )
    provider = TieredKernelProvider(
        {FeatureTier.STARTER: _kernel(tenant)}, EntitlementEngine(ents)
    )
    return create_app(provider=provider)  # rate_limit defaults True


async def test_requests_within_limit_pass_then_429():
    app = _provider_app("rl-co", limit_override=2)
    headers = {"Authorization": "Bearer opaque", "X-Tenant-Id": "rl-co"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/v1/ledger/rl-co/trail", headers=headers)
        second = await client.get("/v1/ledger/rl-co/trail", headers=headers)
        third = await client.get("/v1/ledger/rl-co/trail", headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMITED"
    assert third.headers["retry-after"] == "60"


async def test_health_is_exempt_from_rate_limit():
    app = _provider_app("rl-co", limit_override=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.get("/health")
            assert resp.status_code == 200


async def test_no_entitlement_source_means_no_rate_limit():
    # Single-kernel app with no entitlement store → limiter is a no-op even under repeated calls.
    app = create_app(_kernel("solo"))
    headers = {"Authorization": "Bearer opaque"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.get("/v1/ledger/solo/trail", headers=headers)
            assert resp.status_code == 200, resp.text
