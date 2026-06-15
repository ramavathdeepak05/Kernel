"""BillingEngine — apply a normalized billing event to the entitlement store (WS-C).

Provider-neutral: it consumes a verified `BillingEvent` (produced by a `BillingPort` adapter) and
maps it to the existing fail-closed plan mutations on `EntitlementStore`:

  - SUBSCRIPTION_ACTIVE     → set the tenant's tier to ``target_tier`` and mark the plan ACTIVE,
                              stamping the billing provider + subscription ref.
  - PAYMENT_FAILED          → SUSPEND the plan (fail-closed: a suspended plan is not entitled).
  - PAYMENT_RECOVERED       → reactivate (status ACTIVE).
  - SUBSCRIPTION_CANCELLED  → downgrade to the free STARTER tier, ACTIVE (self-serve fallback rather
                              than bricking the tenant).

A tenant with no plan yet (e.g. a webhook arriving before signup completed) is provisioned a plan on
the first SUBSCRIPTION_ACTIVE; other event types for an unknown tenant are a no-op (nothing to
suspend). Idempotent by construction — applying the same event twice converges to the same state.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone

from core.billing.model import BillingEvent, BillingEventType
from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.entitlements.store import EntitlementStore
from core.errors import BillingEventError
from core.types import TenantId

log = logging.getLogger("quaicu.billing")


class BillingEngine:
    """Translate verified billing events into entitlement-store mutations."""

    def __init__(self, entitlements: EntitlementStore) -> None:
        self._entitlements = entitlements

    async def apply(self, event: BillingEvent) -> CustomerPlan | None:
        """Apply ``event`` to the entitlement store. Returns the resulting plan, or None for no-ops."""
        if not event.is_actionable:
            return None
        if event.tenant_id is None:
            raise BillingEventError(
                f"{event.provider} {event.event_type.value} event has no resolvable tenant.",
                detail={"provider": event.provider, "event_id": event.event_id},
            )
        tenant = event.tenant_id

        if event.event_type is BillingEventType.SUBSCRIPTION_ACTIVE:
            return await self._activate(event, tenant)
        if event.event_type is BillingEventType.PAYMENT_FAILED:
            return await self._set_status_if_present(tenant, PlanStatus.SUSPENDED)
        if event.event_type is BillingEventType.PAYMENT_RECOVERED:
            return await self._set_status_if_present(tenant, PlanStatus.ACTIVE)
        if event.event_type is BillingEventType.SUBSCRIPTION_CANCELLED:
            return await self._downgrade_to_free(tenant)
        return None

    async def _activate(self, event: BillingEvent, tenant: TenantId) -> CustomerPlan:
        if event.target_tier is None:
            raise BillingEventError(
                f"{event.provider} subscription event for {tenant!r} maps to no known tier.",
                detail={"provider": event.provider, "external_ref": event.external_ref},
            )
        now = datetime.now(timezone.utc)
        current = self._entitlements.get(tenant)
        if current is None:
            plan = CustomerPlan(
                tenant_id=tenant,
                tier=event.target_tier,
                status=PlanStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                billing_provider=event.provider,
                billing_ref=event.external_ref,
            )
        else:
            plan = dataclasses.replace(
                current,
                tier=event.target_tier,
                status=PlanStatus.ACTIVE,
                updated_at=now,
                billing_provider=event.provider,
                billing_ref=event.external_ref or current.billing_ref,
            )
        result = await self._entitlements.upsert_persisted(plan)
        log.info(
            "billing activate: tenant=%s tier=%s provider=%s ref=%s",
            tenant, event.target_tier.value, event.provider, event.external_ref,
        )
        return result

    async def _set_status_if_present(self, tenant: TenantId, status: PlanStatus) -> CustomerPlan | None:
        if self._entitlements.get(tenant) is None:
            log.warning("billing status %s for unknown tenant=%s — no-op", status.value, tenant)
            return None
        return await self._entitlements.set_status_persisted(tenant, status)

    async def _downgrade_to_free(self, tenant: TenantId) -> CustomerPlan | None:
        current = self._entitlements.get(tenant)
        if current is None:
            return None
        now = datetime.now(timezone.utc)
        plan = dataclasses.replace(
            current,
            tier=FeatureTier.STARTER,
            status=PlanStatus.ACTIVE,
            updated_at=now,
        )
        result = await self._entitlements.upsert_persisted(plan)
        log.info("billing cancel → downgrade to STARTER: tenant=%s", tenant)
        return result
