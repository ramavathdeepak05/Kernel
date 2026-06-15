"""Razorpay BillingPort adapter (WS-C).

Verifies the ``X-Razorpay-Signature`` header (HMAC-SHA256 of the raw body with the webhook secret) and
maps Razorpay subscription events to provider-neutral `BillingEvent`s. No ``razorpay`` SDK dependency.

Tenant resolution: the kernel stamps ``notes.tenant`` on the Razorpay subscription at creation; this
adapter reads it back. Tier resolution: an injected ``plan_to_tier`` map (Razorpay plan id → tier).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping

from core.billing.model import BillingEvent, BillingEventType
from core.entitlements.model import FeatureTier
from core.errors import BillingEventError, WebhookVerificationError

# Razorpay event → neutral type.
_ACTIVE_EVENTS = frozenset(
    {"subscription.activated", "subscription.charged", "subscription.resumed", "subscription.updated"}
)
_FAILED_EVENTS = frozenset({"subscription.halted", "subscription.pending"})
_CANCELLED_EVENTS = frozenset({"subscription.cancelled", "subscription.completed"})


class RazorpayBillingAdapter:
    """Verify Razorpay webhooks and normalize them to `BillingEvent`s."""

    provider = "razorpay"

    def __init__(
        self,
        *,
        webhook_secret: str,
        plan_to_tier: Mapping[str, FeatureTier],
    ) -> None:
        if not webhook_secret:
            raise ValueError("RazorpayBillingAdapter requires a webhook_secret.")
        self._secret = webhook_secret
        self._plan_to_tier = dict(plan_to_tier)

    def _verify_signature(self, payload: bytes, signature: str) -> None:
        if not signature:
            raise WebhookVerificationError("Missing X-Razorpay-Signature header.")
        expected = hmac.new(self._secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise WebhookVerificationError("Razorpay webhook signature does not verify.")

    def verify_and_parse(self, *, payload: bytes, headers: Mapping[str, str]) -> BillingEvent:
        signature = headers.get("x-razorpay-signature") or headers.get("X-Razorpay-Signature") or ""
        self._verify_signature(payload, signature)

        try:
            doc = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WebhookVerificationError("Razorpay webhook body is not valid JSON.") from exc

        event_name = str(doc.get("event", ""))
        entity = (
            ((doc.get("payload") or {}).get("subscription") or {}).get("entity") or {}
        )
        external_ref = entity.get("id")
        tenant = self._tenant(entity)
        event_id = headers.get("x-razorpay-event-id") or doc.get("id")

        if event_name in _ACTIVE_EVENTS:
            plan_id = entity.get("plan_id")
            tier = self._plan_to_tier.get(plan_id) if plan_id else None
            if tier is None:
                raise BillingEventError(
                    f"Razorpay plan {plan_id!r} is not mapped to any tier.",
                    detail={"plan_id": plan_id, "known": sorted(self._plan_to_tier)},
                )
            return BillingEvent(
                provider=self.provider,
                event_type=BillingEventType.SUBSCRIPTION_ACTIVE,
                tenant_id=tenant,
                target_tier=tier,
                external_ref=external_ref,
                event_id=event_id,
                raw=entity,
            )

        if event_name in _FAILED_EVENTS:
            etype = BillingEventType.PAYMENT_FAILED
        elif event_name in _CANCELLED_EVENTS:
            etype = BillingEventType.SUBSCRIPTION_CANCELLED
        else:
            return BillingEvent(
                provider=self.provider, event_type=BillingEventType.IGNORED, event_id=event_id
            )

        return BillingEvent(
            provider=self.provider,
            event_type=etype,
            tenant_id=tenant,
            external_ref=external_ref,
            event_id=event_id,
            raw=entity,
        )

    @staticmethod
    def _tenant(entity: dict):
        from core.types import TenantId

        notes = entity.get("notes") or {}
        tenant = notes.get("tenant") or notes.get("tenant_id")
        return TenantId(str(tenant)) if tenant else None
