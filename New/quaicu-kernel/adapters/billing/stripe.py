"""Stripe BillingPort adapter (WS-C).

Verifies the ``Stripe-Signature`` header per Stripe's scheme (HMAC-SHA256 over ``"{t}.{payload}"``,
within a timestamp tolerance) and maps the event to a provider-neutral `BillingEvent`. No ``stripe``
SDK dependency — verification is plain ``hmac``/``hashlib`` so the path is auditable and testable.

Tenant resolution: the kernel stamps ``metadata.tenant`` on the Stripe subscription at checkout; this
adapter reads it back. Tier resolution: an injected ``price_to_tier`` map (Stripe price id → tier).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping

from core.billing.model import BillingEvent, BillingEventType
from core.entitlements.model import FeatureTier
from core.errors import BillingEventError, WebhookVerificationError

# Subscription statuses Stripe considers "paid and serving".
_ACTIVE_STATUSES = frozenset({"active", "trialing"})


class StripeBillingAdapter:
    """Verify Stripe webhooks and normalize them to `BillingEvent`s."""

    provider = "stripe"

    def __init__(
        self,
        *,
        webhook_secret: str,
        price_to_tier: Mapping[str, FeatureTier],
        tolerance_seconds: int = 300,
    ) -> None:
        if not webhook_secret:
            raise ValueError("StripeBillingAdapter requires a webhook_secret.")
        self._secret = webhook_secret
        self._price_to_tier = dict(price_to_tier)
        self._tolerance = tolerance_seconds

    # ── Signature verification ───────────────────────────────────────────────────

    def _verify_signature(self, payload: bytes, header: str) -> None:
        if not header:
            raise WebhookVerificationError("Missing Stripe-Signature header.")
        parts = dict(
            kv.split("=", 1) for kv in header.split(",") if "=" in kv
        )
        timestamp = parts.get("t")
        provided = parts.get("v1")
        if not timestamp or not provided:
            raise WebhookVerificationError("Malformed Stripe-Signature header.")
        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise WebhookVerificationError("Stripe-Signature timestamp is not an integer.") from exc
        if abs(time.time() - ts) > self._tolerance:
            raise WebhookVerificationError(
                "Stripe webhook timestamp outside tolerance (possible replay).",
                detail={"tolerance_s": self._tolerance},
            )
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(self._secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, provided):
            raise WebhookVerificationError("Stripe webhook signature does not verify.")

    # ── Parse ────────────────────────────────────────────────────────────────────

    def verify_and_parse(self, *, payload: bytes, headers: Mapping[str, str]) -> BillingEvent:
        header = headers.get("stripe-signature") or headers.get("Stripe-Signature") or ""
        self._verify_signature(payload, header)

        try:
            doc = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WebhookVerificationError("Stripe webhook body is not valid JSON.") from exc

        event_type = str(doc.get("type", ""))
        event_id = doc.get("id")
        obj = (doc.get("data") or {}).get("object") or {}

        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            status = str(obj.get("status", ""))
            if status not in _ACTIVE_STATUSES:
                # past_due / unpaid / incomplete → treat as a payment failure (fail-closed).
                if status in ("past_due", "unpaid", "incomplete_expired"):
                    return self._event(BillingEventType.PAYMENT_FAILED, obj, event_id)
                return self._ignored(event_id)
            return self._active_event(obj, event_id)

        if event_type == "customer.subscription.deleted":
            return self._event(BillingEventType.SUBSCRIPTION_CANCELLED, obj, event_id)

        if event_type == "invoice.payment_failed":
            return self._event(BillingEventType.PAYMENT_FAILED, obj, event_id)

        return self._ignored(event_id)

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _active_event(self, obj: dict, event_id: str | None) -> BillingEvent:
        price_id = self._price_id(obj)
        tier = self._price_to_tier.get(price_id) if price_id else None
        if tier is None:
            raise BillingEventError(
                f"Stripe price {price_id!r} is not mapped to any tier.",
                detail={"price_id": price_id, "known": sorted(self._price_to_tier)},
            )
        return BillingEvent(
            provider=self.provider,
            event_type=BillingEventType.SUBSCRIPTION_ACTIVE,
            tenant_id=self._tenant(obj),
            target_tier=tier,
            external_ref=obj.get("id"),
            event_id=event_id,
            raw=obj,
        )

    def _event(self, etype: BillingEventType, obj: dict, event_id: str | None) -> BillingEvent:
        return BillingEvent(
            provider=self.provider,
            event_type=etype,
            tenant_id=self._tenant(obj),
            external_ref=obj.get("id") or obj.get("subscription"),
            event_id=event_id,
            raw=obj,
        )

    def _ignored(self, event_id: str | None) -> BillingEvent:
        return BillingEvent(provider=self.provider, event_type=BillingEventType.IGNORED, event_id=event_id)

    @staticmethod
    def _price_id(obj: dict) -> str | None:
        items = ((obj.get("items") or {}).get("data")) or []
        if items:
            price = items[0].get("price") or {}
            return price.get("id")
        # invoice line fallback
        lines = ((obj.get("lines") or {}).get("data")) or []
        if lines:
            price = lines[0].get("price") or {}
            return price.get("id")
        return None

    @staticmethod
    def _tenant(obj: dict):
        from core.types import TenantId

        meta = obj.get("metadata") or {}
        tenant = meta.get("tenant") or meta.get("tenant_id")
        if not tenant:
            sub_details = obj.get("subscription_details") or {}
            tenant = (sub_details.get("metadata") or {}).get("tenant")
        return TenantId(str(tenant)) if tenant else None
