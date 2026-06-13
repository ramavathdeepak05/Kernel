"""EntitlementStore write-through + hydrate, and billing-driven tier/status flips (ADR-0009).

Uses a tiny in-memory repository stand-in so the persist → fresh store → hydrate loop is exercised
without a database.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.entitlements import (
    CustomerPlan,
    EntitlementStore,
    FeatureTier,
    PlanStatus,
)
from core.entitlements.repository import EntitlementRepository
from core.errors import PlanNotFoundError
from core.types import TenantId


class _MemRepo(EntitlementRepository):
    def __init__(self) -> None:
        self.rows: dict[str, CustomerPlan] = {}

    async def load_all(self) -> list[CustomerPlan]:
        return list(self.rows.values())

    async def save_plan(self, plan: CustomerPlan) -> None:
        self.rows[str(plan.tenant_id)] = plan

    async def set_tier(self, tenant: TenantId, tier: FeatureTier) -> None:
        import dataclasses

        self.rows[str(tenant)] = dataclasses.replace(self.rows[str(tenant)], tier=tier)

    async def set_status(self, tenant: TenantId, status: PlanStatus) -> None:
        import dataclasses

        self.rows[str(tenant)] = dataclasses.replace(self.rows[str(tenant)], status=status)


def _plan(tenant: str, tier: FeatureTier) -> CustomerPlan:
    now = datetime.now(timezone.utc)
    return CustomerPlan(tenant, tier, PlanStatus.ACTIVE, now, now)


async def test_write_through_then_hydrate_fresh_store():
    repo = _MemRepo()
    store = EntitlementStore(repository=repo)
    await store.upsert_persisted(_plan("t", FeatureTier.STARTER))

    fresh = EntitlementStore(repository=repo)
    assert fresh.get("t") is None
    await fresh.hydrate()
    assert fresh.get("t").tier is FeatureTier.STARTER


async def test_tier_flip_persists_and_updates_cache():
    repo = _MemRepo()
    store = EntitlementStore(repository=repo)
    await store.upsert_persisted(_plan("t", FeatureTier.STARTER))

    updated = await store.set_tier_persisted("t", FeatureTier.BUSINESS)
    assert updated.tier is FeatureTier.BUSINESS
    assert store.get("t").tier is FeatureTier.BUSINESS
    assert repo.rows["t"].tier is FeatureTier.BUSINESS


async def test_status_flip_suspends_plan():
    store = EntitlementStore()
    store.upsert(_plan("t", FeatureTier.BUSINESS))
    updated = await store.set_status_persisted("t", PlanStatus.SUSPENDED)
    assert updated.status is PlanStatus.SUSPENDED


async def test_tier_flip_on_missing_plan_raises():
    store = EntitlementStore()
    with pytest.raises(PlanNotFoundError):
        await store.set_tier_persisted("ghost", FeatureTier.BUSINESS)
