"""Entitlement & tiering — durable repository protocol (ADR-0009).

The `EntitlementStore` is the in-process read cache on the hot path. A durable backend implementing
`EntitlementRepository` (e.g. a Postgres adapter) persists plans so a restarted kernel resolves the
same tiers, and so billing webhooks survive a redeploy. Mirrors `core/policy/repository.py`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.types import TenantId


@runtime_checkable
class EntitlementRepository(Protocol):
    """Durable backend for customer plans. All methods are async (off the hot path)."""

    async def load_all(self) -> list[CustomerPlan]:
        """Return every persisted plan. Called once at startup to hydrate the cache."""
        ...

    async def save_plan(self, plan: CustomerPlan) -> None:
        """Upsert a plan keyed by ``tenant_id`` (idempotent)."""
        ...

    async def set_tier(self, tenant: TenantId, tier: FeatureTier) -> None:
        """Persist a tier change (the durable side of a billing-driven tier flip)."""
        ...

    async def set_status(self, tenant: TenantId, status: PlanStatus) -> None:
        """Persist a plan status change (e.g. SUSPENDED on payment failure)."""
        ...
