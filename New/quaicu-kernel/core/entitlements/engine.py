"""Entitlement & tiering — the engine (ADR-0009).

`EntitlementEngine` answers the only questions the rest of the kernel asks about commercial tiers:
  - what tier is this tenant on?            → ``tier_for`` / ``spec_for``
  - may this tenant use this adapter?       → ``assert_adapter_allowed``
  - may this tenant run this profile?       → ``assert_profile_allowed``
  - is this tenant within its quota?        → ``assert_within_quota``

Every check is **fail-closed** (F-03): an unprovisioned or non-ACTIVE plan grants nothing. The engine
is a thin query layer over the `EntitlementStore`; it imports no `core/lifecycle` or adapter code, so
it stays usable from the SDK composition root and the API edge alike.
"""

from __future__ import annotations

import logging

from core.entitlements.model import CustomerPlan, FeatureTier, TierSpec
from core.entitlements.store import EntitlementStore
from core.errors import (
    FeatureNotEntitledError,
    PlanNotFoundError,
    QuotaExceededError,
)
from core.types import TenantId

log = logging.getLogger("quaicu.entitlements")


class EntitlementEngine:
    """Read-only entitlement decisions over a customer-plan store."""

    def __init__(self, store: EntitlementStore) -> None:
        self._store = store

    # ── Resolution ───────────────────────────────────────────────────────────────

    def resolve_plan(self, tenant: TenantId) -> CustomerPlan:
        """Return the tenant's ACTIVE plan, or raise. Fail-closed on missing/inactive plans."""
        plan = self._store.get(tenant)
        if plan is None:
            raise PlanNotFoundError(
                f"Tenant {tenant!r} has no provisioned plan.",
                detail={"tenant": str(tenant)},
            )
        if not plan.is_active:
            raise FeatureNotEntitledError(
                f"Tenant {tenant!r} plan is {plan.status.value}, not ACTIVE.",
                detail={"tenant": str(tenant), "status": plan.status.value},
            )
        return plan

    def tier_for(self, tenant: TenantId) -> FeatureTier:
        """The tenant's tier. Raises if unprovisioned/inactive."""
        return self.resolve_plan(tenant).tier

    def spec_for(self, tenant: TenantId) -> TierSpec:
        """The tier grants (adapters, profiles, quotas) for the tenant."""
        return self.resolve_plan(tenant).spec

    def _quota(self, plan: CustomerPlan, name: str) -> int:
        """A quota value, honoring per-tenant overrides (Enterprise contracts) over the tier default."""
        if name in plan.quota_overrides:
            return plan.quota_overrides[name]
        return getattr(plan.spec, name)

    # ── Feature gating ─────────────────────────────────────────────────────────────

    def is_adapter_allowed(self, tenant: TenantId, adapter: str) -> bool:
        return adapter in self.resolve_plan(tenant).spec.allowed_adapters

    def assert_adapter_allowed(self, tenant: TenantId, adapter: str) -> None:
        """Raise FeatureNotEntitledError if the tenant's tier may not use ``adapter``."""
        plan = self.resolve_plan(tenant)
        if adapter not in plan.spec.allowed_adapters:
            raise FeatureNotEntitledError(
                f"Tier {plan.tier.value} does not include adapter {adapter!r}.",
                detail={"tenant": str(tenant), "tier": plan.tier.value, "adapter": adapter},
            )

    def is_profile_allowed(self, tenant: TenantId, profile_name: str) -> bool:
        return profile_name in self.resolve_plan(tenant).spec.allowed_profiles

    def assert_profile_allowed(self, tenant: TenantId, profile_name: str) -> None:
        """Raise FeatureNotEntitledError if the tenant's tier may not run ``profile_name``."""
        plan = self.resolve_plan(tenant)
        if profile_name not in plan.spec.allowed_profiles:
            raise FeatureNotEntitledError(
                f"Tier {plan.tier.value} does not include governance profile {profile_name!r}.",
                detail={"tenant": str(tenant), "tier": plan.tier.value, "profile": profile_name},
            )

    def rate_limit_for(self, tenant: TenantId) -> int:
        """The tenant's per-minute request rate limit (``-1`` = unbounded).

        Honors per-tenant ``quota_overrides`` over the tier default. Raises (fail-closed) if the
        tenant is unprovisioned/inactive; the rate-limit middleware treats that as "skip".
        """
        return self._quota(self.resolve_plan(tenant), "rate_limit_per_min")

    # ── Quota enforcement ──────────────────────────────────────────────────────────

    def assert_within_quota(
        self,
        tenant: TenantId,
        *,
        current_policies: int | None = None,
        actions_today: int | None = None,
    ) -> None:
        """Raise QuotaExceededError if any supplied usage figure meets/exceeds the tier's limit.

        Only the figures the caller supplies are checked; ``-1`` limits are unbounded and skipped.
        """
        plan = self.resolve_plan(tenant)

        if current_policies is not None:
            limit = self._quota(plan, "max_policies")
            if limit != -1 and current_policies >= limit:
                raise QuotaExceededError(
                    f"Tier {plan.tier.value} permits at most {limit} policies (have {current_policies}).",
                    detail={"tenant": str(tenant), "limit": limit, "metric": "max_policies"},
                )

        if actions_today is not None:
            limit = self._quota(plan, "max_actions_per_day")
            if limit != -1 and actions_today >= limit:
                raise QuotaExceededError(
                    f"Tier {plan.tier.value} permits at most {limit} actions/day (have {actions_today}).",
                    detail={"tenant": str(tenant), "limit": limit, "metric": "max_actions_per_day"},
                )
