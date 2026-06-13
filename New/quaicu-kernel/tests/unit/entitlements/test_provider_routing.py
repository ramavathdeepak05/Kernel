"""TieredKernelProvider routing — a tenant lands on the kernel its tier is served by (ADR-0009).

Uses stand-in kernels: routing depends only on the entitlement tier, not on kernel internals, so the
test stays fast and focused on the routing contract and its fail-closed boundaries.
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
from core.errors import FeatureNotEntitledError, PlanNotFoundError
from delivery.sdk.provider import TieredKernelProvider


class _StubKernel:
    def __init__(self, name: str) -> None:
        self.name = name


def _plan(tenant: str, tier: FeatureTier, status: PlanStatus = PlanStatus.ACTIVE) -> CustomerPlan:
    now = datetime.now(timezone.utc)
    return CustomerPlan(tenant, tier, status, now, now)


def _saas_provider(*plans: CustomerPlan) -> TieredKernelProvider:
    store = EntitlementStore()
    for p in plans:
        store.upsert(p)
    kernels = {
        FeatureTier.STARTER: _StubKernel("starter"),
        FeatureTier.BUSINESS: _StubKernel("business"),
    }
    return TieredKernelProvider(kernels, EntitlementEngine(store))


def test_starter_tenant_routes_to_starter_kernel():
    prov = _saas_provider(_plan("t", FeatureTier.STARTER))
    assert prov.kernel_for("t").name == "starter"


def test_business_tenant_routes_to_business_kernel():
    prov = _saas_provider(_plan("t", FeatureTier.BUSINESS))
    assert prov.kernel_for("t").name == "business"


def test_enterprise_tenant_on_saas_plane_is_denied():
    prov = _saas_provider(_plan("t", FeatureTier.ENTERPRISE))
    with pytest.raises(FeatureNotEntitledError):
        prov.kernel_for("t")


def test_suspended_tenant_denied():
    prov = _saas_provider(_plan("t", FeatureTier.BUSINESS, status=PlanStatus.SUSPENDED))
    with pytest.raises(FeatureNotEntitledError):
        prov.kernel_for("t")


def test_unprovisioned_tenant_denied():
    prov = _saas_provider()
    with pytest.raises(PlanNotFoundError):
        prov.kernel_for("ghost")


def test_served_tiers_reports_built_kernels():
    prov = _saas_provider()
    assert prov.served_tiers() == frozenset({FeatureTier.STARTER, FeatureTier.BUSINESS})


def test_for_saas_rejects_enterprise_config():
    with pytest.raises(ValueError):
        TieredKernelProvider.for_saas(
            tier_config_paths={FeatureTier.ENTERPRISE: "x.toml"},
            entitlement_store=EntitlementStore(),
        )
