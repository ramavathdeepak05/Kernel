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
    # Shared durable plane: STARTER runs on the SAME durable kernel as BUSINESS, so it is entitled to
    # the durable adapters (Postgres + KMS ledger). The tier difference is now QUOTAS + premium
    # capabilities, not the data store — which is what makes upgrade a feature unlock, not a migration.
    assert e.is_adapter_allowed("t", "cel_policy")
    assert e.is_adapter_allowed("t", "postgres_storage")
    assert e.is_adapter_allowed("t", "postgres_ledger")
    assert e.is_adapter_allowed("t", "gcp_kms_ledger")
    # ...but NOT premium-only adapters: the AI gateway (BUSINESS) and OpenBao (ENTERPRISE) stay gated.
    assert not e.is_adapter_allowed("t", "openai_compat")
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
    e.assert_profile_allowed("t", "standard")            # no raise (enforcing default on STARTER)
    e.assert_profile_allowed("t", "audit_only")          # no raise
    with pytest.raises(FeatureNotEntitledError):
        e.assert_profile_allowed("t", "all")             # consent layer is BUSINESS+ only


def test_policy_quota_enforced_for_business():
    e = _engine(_plan("t", FeatureTier.BUSINESS))        # max_policies = 1000
    e.assert_within_quota("t", current_policies=999)     # no raise
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=1000)


def test_starter_policy_quota_is_generous_but_bounded():
    e = _engine(_plan("t", FeatureTier.STARTER))         # max_policies = 200
    e.assert_within_quota("t", current_policies=199)     # no raise (room for one more)
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=200)  # at the cap


def test_enterprise_quota_unbounded():
    e = _engine(_plan("t", FeatureTier.ENTERPRISE))      # -1 == unbounded
    e.assert_within_quota("t", current_policies=10_000, actions_today=10_000_000)  # no raise


def test_quota_override_beats_tier_default():
    e = _engine(_plan("t", FeatureTier.BUSINESS, quota_overrides={"max_policies": 5}))
    e.assert_within_quota("t", current_policies=4)
    with pytest.raises(QuotaExceededError):
        e.assert_within_quota("t", current_policies=5)
