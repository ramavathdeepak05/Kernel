"""Entitlement engine — tier resolution, feature gating, and quota enforcement (ADR-0009).

Fail-closed is the core property: an unprovisioned or non-ACTIVE tenant is entitled to nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.entitlements import (
    CustomerPlan,
    EntitlementEngine,
    EntitlementStore,
    FeatureTier,
    PlanStatus,
)
from core.errors import (
    FeatureNotEntitledError,
    PlanNotFoundError,
    QuotaExceededError,
)


def _plan(tenant: str, tier: FeatureTier, status: PlanStatus = PlanStatus.ACTIVE, **kw) -> CustomerPlan:
    now = datetime.now(timezone.utc)
    return CustomerPlan(tenant_id=tenant, tier=tier, status=status, created_at=now, updated_at=now, **kw)


def _engine(*plans: CustomerPlan) -> EntitlementEngine:
    store = EntitlementStore()
    for p in plans:
        store.upsert(p)
    return EntitlementEngine(store)


def test_tier_resolves_for_provisioned_tenant():
    e = _engine(_plan("t", FeatureTier.BUSINESS))
    assert e.tier_for("t") is FeatureTier.BUSINESS


def test_unprovisioned_tenant_is_denied():
    e = _engine()
    with pytest.raises(PlanNotFoundError):
        e.tier_for("ghost")


def test_suspended_plan_is_denied():
    e = _engine(_plan("t", FeatureTier.BUSINESS, status=PlanStatus.SUSPENDED))
    with pytest.raises(FeatureNotEntitledError):
        e.resolve_plan("t")


def test_starter_adapter_gating():
    e = _engine(_plan("t", FeatureTier.STARTER))
    assert e.is_adapter_allowed("t", "always_allow")
    assert e.is_adapter_allowed("t", "memory_ledger")
    assert not e.is_adapter_allowed("t", "cel_policy")
    assert not e.is_adapter_allowed("t", "openbao_ledger")


def test_business_includes_cel_but_not_openbao():
    e = _engine(_plan("t", FeatureTier.BUSINESS))
    e.assert_adapter_allowed("t", "cel_policy")          # no raise
    e.assert_adapter_allowed("t", "postgres_ledger")     # no raise
    with pytest.raises(FeatureNotEntitledError):
        e.assert_adapter_allowed("t", "openbao_ledger")  # ENTERPRISE only


def test_enterprise_includes_openbao():
    e = _engine(_plan("t", FeatureTier.ENTERPRISE))
    e.assert_adapter_allowed("t", "openbao_ledger")      # no raise


def test_profile_gating():
    e = _engine(_plan("t", FeatureTier.STARTER))
    e.assert_profile_allowed("t", "audit_only")          # no raise
    with pytest.raises(FeatureNotEntitledError):
        e.assert_profile_allowed("t", "all")             # not on STARTER


def test_policy_quota_enforced_for_business():
    e = _engine(_plan("t", FeatureTier.BUSINESS))        # max_policies = 200
    e.assert_within_quota("t", current_policies=199)     # no raise
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=200)


def test_starter_cannot_author_policies():
    e = _engine(_plan("t", FeatureTier.STARTER))         # max_policies = 0
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=0)


def test_enterprise_quota_unbounded():
    e = _engine(_plan("t", FeatureTier.ENTERPRISE))      # -1 == unbounded
    e.assert_within_quota("t", current_policies=10_000, actions_today=10_000_000)  # no raise


def test_quota_override_beats_tier_default():
    e = _engine(_plan("t", FeatureTier.BUSINESS, quota_overrides={"max_policies": 5}))
    e.assert_within_quota("t", current_policies=4)
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=5)
