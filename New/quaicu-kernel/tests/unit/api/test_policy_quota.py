"""max_policies tier-quota enforcement on POST /v1/policies (shared durable plane, D0-5 / 5b).

The shared durable kernel serves all self-serve tiers, so the structural wall that used to keep STARTER
out of BUSINESS features is gone — the tier feature-gate is now enforced explicitly at the edge by the
EntitlementEngine. A self-serve tenant may author up to its tier's ``max_policies``. A STARTER→BUSINESS
upgrade lifts the cap (via the tier default) with **no data migration** (feature unlock).

The blocking tests use a small ``quota_overrides`` cap to stay fast + independent of the (large) tier
defaults; the feature-unlock test uses the real STARTER default so the upgrade genuinely lifts it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from adapters.policy.memory import InMemoryPolicyRepository
from core.entitlements import (
    CustomerPlan,
    EntitlementEngine,
    EntitlementStore,
    FeatureTier,
    PlanStatus,
    TIER_MATRIX,
)
from core.policy.model import PolicyEnvelope, PolicyLifecycle
from core.policy.store import PolicyStore
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from delivery.sdk.provider import TieredKernelProvider
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy

TENANT = "acme"
ADMIN = {"Authorization": "Bearer t", "X-Tenant-Id": TENANT}


def _kernel() -> Kernel:
    repo = InMemoryPolicyRepository()
    return Kernel.from_parts(
        tenant=TenantId(TENANT),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(roles=("role:policy_admin",)),
        policy_store=PolicyStore(repository=repo),
        policy_repository=repo,
    )


def _app(tier: FeatureTier, *, max_policies: int | None = None):
    ents = EntitlementStore()
    now = datetime.now(timezone.utc)
    # A small max_policies override keeps the blocking tests fast + independent of the tier default.
    overrides = {"max_policies": max_policies} if max_policies is not None else {}
    ents.upsert(
        CustomerPlan(
            tenant_id=TenantId(TENANT),
            tier=tier,
            status=PlanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            quota_overrides=overrides,
        )
    )
    kernel = _kernel()
    # One durable kernel serves BOTH tiers (shared plane) — so set_tier resolves to the same kernel and
    # the tenant's data is untouched by an upgrade.
    provider = TieredKernelProvider(
        {FeatureTier.STARTER: kernel, FeatureTier.BUSINESS: kernel}, EntitlementEngine(ents)
    )
    return create_app(provider=provider, rate_limit=False), ents, kernel


def _seed_owned_policies(kernel: Kernel, n: int) -> None:
    """Pre-seed ``n`` policies owned by TENANT directly into the store (fast path, no HTTP)."""
    assert kernel.policy_store is not None
    for i in range(n):
        kernel.policy_store.register(
            PolicyEnvelope(
                id=f"seed{i}",
                version=1,
                governs="*",
                scope={"tenant": TENANT},
                condition="true",
                decision=Decision.ALLOW,
                approvers=(),
                regulatory_refs=(),
                lifecycle=PolicyLifecycle.ACTIVATED,
            )
        )


def _body(pid: str, version: int = 1) -> dict:
    return {
        "id": pid,
        "version": version,
        "governs": "payments.wire",
        "scope": {"tenant": "*"},  # the server overrides this with the authenticated tenant
        "condition": "true",
        "decision": "allow",
        "approvers": [],
        "regulatory_refs": [],
    }


async def _register(client: AsyncClient, pid: str, version: int = 1):
    return await client.post("/v1/policies", json=_body(pid, version), headers=ADMIN)


async def test_starter_blocked_at_max_policies() -> None:
    app, _, _ = _app(FeatureTier.STARTER, max_policies=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await _register(c, "p0")).status_code == 201
        assert (await _register(c, "p1")).status_code == 201
        third = await _register(c, "p2")
        assert third.status_code == 429
        assert third.json()["detail"]["code"] == "QUOTA_EXCEEDED"


async def test_scope_tenant_is_stamped_to_caller() -> None:
    app, _, _ = _app(FeatureTier.STARTER, max_policies=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await _register(c, "p0")
        assert r.status_code == 201
        # The server stamps the authenticated tenant, ignoring the caller-supplied "*".
        assert r.json()["scope"]["tenant"] == TENANT


async def test_new_version_of_existing_policy_does_not_consume_quota() -> None:
    app, _, _ = _app(FeatureTier.STARTER, max_policies=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await _register(c, "p0")).status_code == 201
        assert (await _register(c, "p1")).status_code == 201
        # A new VERSION of an already-owned policy id is not a new policy → allowed at the cap.
        assert (await _register(c, "p0", version=2)).status_code == 201


async def test_business_allows_more_than_a_small_starter_cap() -> None:
    app, _, _ = _app(FeatureTier.BUSINESS, max_policies=None)  # default 1000
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for i in range(6):
            assert (await _register(c, f"p{i}")).status_code == 201, f"p{i}"


async def test_upgrade_is_a_feature_unlock_not_a_migration() -> None:
    # No override → the *tier default* drives the cap, so the upgrade genuinely lifts it.
    app, ents, kernel = _app(FeatureTier.STARTER, max_policies=None)
    starter_cap = TIER_MATRIX[FeatureTier.STARTER].max_policies
    _seed_owned_policies(kernel, starter_cap - 1)  # one slot left under the STARTER cap
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await _register(c, "last")).status_code == 201  # fills the STARTER cap
        assert (await _register(c, "over")).status_code == 429  # at the STARTER cap → blocked
        # Upgrade: flip the tier only — no data moves, the seeded policies remain on the same kernel.
        await ents.set_tier_persisted(TenantId(TENANT), FeatureTier.BUSINESS)
        unlocked = await _register(c, "over")
        assert unlocked.status_code == 201, unlocked.text  # cap lifted by the tier default
