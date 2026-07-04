"""Cross-worker entitlement visibility (D4-1): find_plan fallback + ensure_loaded."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.entitlements.engine import EntitlementEngine
from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.entitlements.store import EntitlementStore
from core.errors import PlanNotFoundError
from core.types import TenantId

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _plan(tenant: str = "acme", tier: FeatureTier = FeatureTier.BUSINESS) -> CustomerPlan:
    return CustomerPlan(
        tenant_id=TenantId(tenant), tier=tier, status=PlanStatus.ACTIVE,
        created_at=NOW, updated_at=NOW,
    )


class _FakeRepo:
    """Durable plan store shared by 'workers'."""

    def __init__(self) -> None:
        self.plans: dict[str, CustomerPlan] = {}
        self.get_calls = 0

    async def load_all(self) -> list[CustomerPlan]:
        return list(self.plans.values())

    async def get_plan(self, tenant: TenantId) -> CustomerPlan | None:
        self.get_calls += 1
        return self.plans.get(str(tenant))

    async def save_plan(self, plan: CustomerPlan) -> None:
        self.plans[str(plan.tenant_id)] = plan


async def test_find_plan_falls_back_to_repository_and_caches() -> None:
    repo = _FakeRepo()
    repo.plans["acme"] = _plan()  # provisioned by "another worker"
    store = EntitlementStore(repository=repo)  # cold cache

    assert store.get(TenantId("acme")) is None
    plan = await store.find_plan(TenantId("acme"))
    assert plan is not None and plan.tier is FeatureTier.BUSINESS
    # Cached: subsequent sync hot-path reads hit.
    assert store.get(TenantId("acme")) is not None
    calls = repo.get_calls
    await store.find_plan(TenantId("acme"))
    assert repo.get_calls == calls  # cache fast-path, no re-read


async def test_ensure_loaded_makes_sync_resolution_work() -> None:
    repo = _FakeRepo()
    repo.plans["acme"] = _plan()
    engine = EntitlementEngine(EntitlementStore(repository=repo))

    with pytest.raises(PlanNotFoundError):
        engine.resolve_plan(TenantId("acme"))  # cold cache fails closed
    await engine.ensure_loaded(TenantId("acme"))
    assert engine.tier_for(TenantId("acme")) is FeatureTier.BUSINESS


async def test_find_plan_unprovisioned_returns_none() -> None:
    store = EntitlementStore(repository=_FakeRepo())
    assert await store.find_plan(TenantId("ghost")) is None


async def test_ensure_loaded_without_repository_is_noop() -> None:
    engine = EntitlementEngine(EntitlementStore())
    await engine.ensure_loaded(TenantId("acme"))  # must not raise
    with pytest.raises(PlanNotFoundError):
        engine.resolve_plan(TenantId("acme"))
