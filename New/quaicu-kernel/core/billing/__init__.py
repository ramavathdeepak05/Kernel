"""Billing (WS-C) — map external subscription events to tier flips.

A provider-agnostic seam between a payment processor (Stripe, Razorpay) and the entitlement store.
Provider-specific signature verification + payload parsing live in `adapters/billing/*` behind the
`BillingPort` protocol; the provider-neutral `BillingEngine` translates a normalized `BillingEvent`
into `EntitlementStore` mutations (tier flip, suspend on payment failure, downgrade on cancel).
"""

from core.billing.engine import BillingEngine
from core.billing.model import BillingEvent, BillingEventType
from core.billing.port import BillingPort

__all__ = ["BillingEngine", "BillingEvent", "BillingEventType", "BillingPort"]
