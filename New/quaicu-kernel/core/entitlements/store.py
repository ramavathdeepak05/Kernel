"""Entitlement & tiering — in-memory plan store (ADR-0009).

Holds one `CustomerPlan` per tenant. Thread-safe (a `threading.Lock` guards mutations), with an
optional durable `EntitlementRepository` write-through + `hydrate()` on startup — the same shape as
`core/policy/store.py`. The hot-path reads (`get`) never touch the repository.
"""

from __future__ import annotations

import logging
import threading

from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.entitlements.repository import EntitlementRepository
from core.types import TenantId

log = logging.getLogger("quaicu.entitlements")


class EntitlementStore:
    """In-process registry of customer plans, keyed by tenant id."""

    def __init__(self, repository: EntitlementRepository | None = None) -> None:
        self._plans: dict[str, CustomerPlan] = {}
        self._lock = threading.Lock()
        self._repository = repository

    # ── Reads (hot path) ─────────────────────────────────────────────────────────

    def get(self, tenant: TenantId) -> CustomerPlan | None:
        """Return the plan for ``tenant``, or None if unprovisioned."""
        with self._lock:
            return self._plans.get(str(tenant))

    def list_plans(self) -> list[CustomerPlan]:
        """Return every plan, sorted by tenant id."""
        with self._lock:
            plans = list(self._plans.values())
        return sorted(plans, key=lambda p: str(p.tenant_id))

    # ── Cache mutations ──────────────────────────────────────────────────────────

    def upsert(self, plan: CustomerPlan) -> CustomerPlan:
        """Insert or replace a plan in the cache."""
        with self._lock:
            self._plans[str(plan.tenant_id)] = plan
        log.info("plan upserted: tenant=%s tier=%s status=%s", plan.tenant_id, plan.tier.value, plan.status.value)
        return plan

    async def find_plan(self, tenant: TenantId) -> CustomerPlan | None:
        """Authoritative plan lookup: cache fast-path, durable-repository fallback (D4-1).

        A tenant provisioned on another worker/instance isn't in this cache until the next
        re-hydrate; the fallback closes that window (mirrors `AccountStore.find_api_key`).
        A found plan is cached. Store faults propagate (fail-closed — no tier is granted on
        an unverifiable plan).
        """
        cached = self.get(tenant)
        if cached is not None:
            return cached
        getter = getattr(self._repository, "get_plan", None)
        if getter is None:
            return None
        plan = await getter(tenant)
        if plan is not None:
            self.upsert(plan)
        return plan

    # ── Durable write-through (async; off the hot path) ──────────────────────────

    async def hydrate(self) -> None:
        """Repopulate the cache from the durable repository. No-op when none is wired."""
        if self._repository is None:
            return
        plans = await self._repository.load_all()
        for plan in plans:
            self.upsert(plan)
        log.info("entitlement store hydrated: %d plan(s)", len(plans))

    async def upsert_persisted(self, plan: CustomerPlan) -> CustomerPlan:
        """Persist a plan to the durable store, then cache it (persist-first)."""
        if self._repository is not None:
            await self._repository.save_plan(plan)
        return self.upsert(plan)

    async def set_tier_persisted(self, tenant: TenantId, tier: FeatureTier) -> CustomerPlan:
        """Flip a tenant's tier (billing-driven), persisting first. Raises if no plan exists."""
        from datetime import datetime, timezone

        current = self.get(tenant)
        if current is None:
            from core.errors import PlanNotFoundError

            raise PlanNotFoundError(
                f"No plan for tenant {tenant!r}; cannot change tier.",
                detail={"tenant": str(tenant)},
            )
        import dataclasses

        updated = dataclasses.replace(current, tier=tier, updated_at=datetime.now(timezone.utc))
        if self._repository is not None:
            await self._repository.set_tier(tenant, tier)
        return self.upsert(updated)

    async def set_status_persisted(self, tenant: TenantId, status: PlanStatus) -> CustomerPlan:
        """Change a tenant's plan status (e.g. SUSPENDED), persisting first."""
        from datetime import datetime, timezone

        current = self.get(tenant)
        if current is None:
            from core.errors import PlanNotFoundError

            raise PlanNotFoundError(
                f"No plan for tenant {tenant!r}; cannot change status.",
                detail={"tenant": str(tenant)},
            )
        import dataclasses

        updated = dataclasses.replace(current, status=status, updated_at=datetime.now(timezone.utc))
        if self._repository is not None:
            await self._repository.set_status(tenant, status)
        return self.upsert(updated)
