"""Unit tests for BillingEngine — event → entitlement-store mutation (WS-C)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.billing import BillingEngine, BillingEvent, BillingEventType
from core.entitlements import CustomerPlan, EntitlementStore, FeatureTier, PlanStatus
from core.errors import BillingEventError
from core.types import TenantId

T = TenantId("acme-co")


def _store_with_plan(tier=FeatureTier.STARTER, status=PlanStatus.ACTIVE) -> EntitlementStore:
    s = EntitlementStore()
    now = datetime.now(timezone.utc)
    s.upsert(CustomerPlan(T, tier, status, now, now))
    return s


def _ev(etype, *, tier=None, ref="sub_1"):
    return BillingEvent(
        provider="stripe", event_type=etype, tenant_id=T, target_tier=tier, external_ref=ref
    )


async def test_subscription_active_flips_tier_and_activates():
    s = _store_with_plan()
    plan = await BillingEngine(s).apply(
        _ev(BillingEventType.SUBSCRIPTION_ACTIVE, tier=FeatureTier.BUSINESS)
    )
    assert plan.tier is FeatureTier.BUSINESS
    assert plan.status is PlanStatus.ACTIVE
    assert plan.billing_provider == "stripe"
    assert plan.billing_ref == "sub_1"


async def test_subscription_active_provisions_plan_when_absent():
    s = EntitlementStore()  # no plan yet (webhook before signup)
    plan = await BillingEngine(s).apply(
        _ev(BillingEventType.SUBSCRIPTION_ACTIVE, tier=FeatureTier.BUSINESS)
    )
    assert plan is not None
    assert s.get(T).tier is FeatureTier.BUSINESS


async def test_payment_failed_suspends():
    s = _store_with_plan(tier=FeatureTier.BUSINESS)
    plan = await BillingEngine(s).apply(_ev(BillingEventType.PAYMENT_FAILED))
    assert plan.status is PlanStatus.SUSPENDED
    assert plan.tier is FeatureTier.BUSINESS  # tier preserved; only status changes


async def test_payment_recovered_reactivates():
    s = _store_with_plan(tier=FeatureTier.BUSINESS, status=PlanStatus.SUSPENDED)
    plan = await BillingEngine(s).apply(_ev(BillingEventType.PAYMENT_RECOVERED))
    assert plan.status is PlanStatus.ACTIVE


async def test_cancel_downgrades_to_starter_active():
    s = _store_with_plan(tier=FeatureTier.BUSINESS)
    plan = await BillingEngine(s).apply(_ev(BillingEventType.SUBSCRIPTION_CANCELLED))
    assert plan.tier is FeatureTier.STARTER
    assert plan.status is PlanStatus.ACTIVE


async def test_payment_failed_for_unknown_tenant_is_noop():
    s = EntitlementStore()
    plan = await BillingEngine(s).apply(_ev(BillingEventType.PAYMENT_FAILED))
    assert plan is None


async def test_ignored_event_is_noop():
    s = _store_with_plan()
    plan = await BillingEngine(s).apply(
        BillingEvent(provider="stripe", event_type=BillingEventType.IGNORED)
    )
    assert plan is None


async def test_active_without_tenant_raises():
    s = _store_with_plan()
    bad = BillingEvent(
        provider="stripe",
        event_type=BillingEventType.SUBSCRIPTION_ACTIVE,
        tenant_id=None,
        target_tier=FeatureTier.BUSINESS,
    )
    with pytest.raises(BillingEventError):
        await BillingEngine(s).apply(bad)


async def test_active_without_tier_raises():
    s = _store_with_plan()
    with pytest.raises(BillingEventError):
        await BillingEngine(s).apply(_ev(BillingEventType.SUBSCRIPTION_ACTIVE, tier=None))


async def test_apply_is_idempotent():
    s = _store_with_plan()
    eng = BillingEngine(s)
    ev = _ev(BillingEventType.SUBSCRIPTION_ACTIVE, tier=FeatureTier.BUSINESS)
    first = await eng.apply(ev)
    second = await eng.apply(ev)
    assert first.tier is second.tier is FeatureTier.BUSINESS
    assert second.status is PlanStatus.ACTIVE
