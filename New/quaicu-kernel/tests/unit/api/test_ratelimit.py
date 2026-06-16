"""Per-tenant, per-tier rate limiting middleware (ADR-0011, WS-D)."""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.account import Account, AccountEngine, AccountStatus, AccountStore
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


def _starter_plan(ents: EntitlementStore, tenant: str, *, limit: int) -> None:
    now = datetime.now(timezone.utc)
    ents.upsert(
        CustomerPlan(
            tenant_id=TenantId(tenant),
            tier=FeatureTier.STARTER,
            status=PlanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            quota_overrides={"rate_limit_per_min": limit},
        )
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


async def test_spoofed_tenant_header_cannot_dos_a_victim():
    # Anti-DoS regression: when unauthenticated, the limiter keys on client IP, NOT the spoofable
    # X-Tenant-Id header. An attacker flooding with a victim's tenant id exhausts only their own IP
    # bucket; the victim, from a different IP, is unaffected.
    app = _provider_app("victim", limit_override=2)
    # The spoofing vector is the unverified X-Tenant-Id; the bearer is accepted by FakeIdentity.
    spoof = {"Authorization": "Bearer opaque", "X-Tenant-Id": "victim"}

    # Attacker (IP 9.9.9.9) floods past the limit using the victim's tenant id.
    attacker = ASGITransport(app=app, client=("9.9.9.9", 0))
    async with AsyncClient(transport=attacker, base_url="http://test") as client:
        await client.get("/v1/ledger/victim/trail", headers=spoof)
        await client.get("/v1/ledger/victim/trail", headers=spoof)
        flooded = await client.get("/v1/ledger/victim/trail", headers=spoof)
    assert flooded.status_code == 429  # attacker's own IP bucket is exhausted

    # The victim, from a different IP, still gets a fresh bucket — no cross-tenant poisoning.
    victim = ASGITransport(app=app, client=("1.1.1.1", 0))
    async with AsyncClient(transport=victim, base_url="http://test") as client:
        resp = await client.get("/v1/ledger/victim/trail", headers=spoof)
    assert resp.status_code == 200, resp.text


async def test_authenticated_limit_keys_on_verified_tenant():
    # When API-key auth is on, the limiter runs after auth and keys on the cryptographically-verified
    # tenant (request.state.principal), enforcing the tier's per-minute quota.
    ents = EntitlementStore()
    _starter_plan(ents, "acme", limit=2)
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme",
            tenant_id=TenantId("acme"),
            email="acme@b.io",
            name="acme",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, ents)
    _, key = eng.issue_api_key(TenantId("acme"))
    app = create_app(
        _kernel("acme"),
        account_engine=eng,
        entitlement_store=ents,
        require_api_key=True,
        rate_limit=True,
    )
    headers = {"Authorization": f"Bearer {key}", "X-Tenant-Id": "acme"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/v1/ledger/acme/trail", headers=headers)
        second = await client.get("/v1/ledger/acme/trail", headers=headers)
        third = await client.get("/v1/ledger/acme/trail", headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMITED"
