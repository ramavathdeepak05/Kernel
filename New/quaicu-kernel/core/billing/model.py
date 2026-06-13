"""Billing — the normalized event a provider adapter produces (WS-C).

Every payment provider has its own event vocabulary; a `BillingPort` adapter verifies the webhook and
distills it into one of these provider-neutral `BillingEvent`s, which the `BillingEngine` knows how to
apply. Keeping the engine event-driven (not provider-driven) means adding a third processor is a new
adapter, not a change to the entitlement-mutation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.entitlements.model import FeatureTier
from core.types import TenantId


class BillingEventType(str, Enum):
    """The provider-neutral billing events the engine acts on.

    Anything an adapter cannot map to one of these (or to a tier) it drops as a no-op — webhooks are
    chatty and most events are irrelevant to entitlement state.
    """

    SUBSCRIPTION_ACTIVE = "SUBSCRIPTION_ACTIVE"     # new/renewed/updated paid subscription → set tier + ACTIVE
    PAYMENT_FAILED = "PAYMENT_FAILED"               # dunning → SUSPEND (fail-closed)
    PAYMENT_RECOVERED = "PAYMENT_RECOVERED"         # dunning resolved → reactivate
    SUBSCRIPTION_CANCELLED = "SUBSCRIPTION_CANCELLED"  # ended → downgrade to free (STARTER)
    IGNORED = "IGNORED"                              # a verified-but-irrelevant event


@dataclass(frozen=True)
class BillingEvent:
    """A verified, provider-neutral billing event.

    ``tenant_id`` is resolved by the adapter from the provider's metadata/notes (where the kernel
    stamped it at checkout). ``target_tier`` is set for SUBSCRIPTION_ACTIVE events (mapped from the
    provider's price/plan id). ``external_ref`` is the subscription id, recorded on the plan.
    """

    provider: str                                   # "stripe" | "razorpay"
    event_type: BillingEventType
    tenant_id: TenantId | None = None
    target_tier: FeatureTier | None = None
    external_ref: str | None = None
    event_id: str | None = None                     # provider event id (idempotency / audit)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """True if the engine should mutate state for this event."""
        return self.event_type is not BillingEventType.IGNORED
