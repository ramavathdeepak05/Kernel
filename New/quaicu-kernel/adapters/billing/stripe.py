"""Stripe billing adapter (WS-C) — inbound webhooks + outbound checkout.

Inbound (`BillingPort.verify_and_parse`): verifies the ``Stripe-Signature`` header per Stripe's scheme
(HMAC-SHA256 over ``"{t}.{payload}"``, within a timestamp tolerance) and maps the event to a
provider-neutral `BillingEvent`. No ``stripe`` SDK — plain ``hmac``/``hashlib``, auditable and testable.

Outbound (`CheckoutPort.create_checkout`): creates a Stripe Checkout Session (``mode=subscription``)
via the REST API through an injectable HTTP transport (still no SDK), stamping ``metadata.tenant`` on
the subscription so the resulting webhook attributes it back to the tenant.

Tenant resolution: the kernel stamps ``metadata.tenant`` at checkout; this adapter reads it back.
Tier resolution: an injected ``price_to_tier`` map (Stripe price id → tier), inverted for checkout.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from urllib.parse import urlencode

from adapters.billing._http import HttpPost, urllib_post
from core.billing.model import BillingEvent, BillingEventType, CheckoutSession
from core.entitlements.model import FeatureTier
from core.errors import BillingEventError, CheckoutError, WebhookVerificationError
from core.types import TenantId

# Subscription statuses Stripe considers "paid and serving".
_ACTIVE_STATUSES = frozenset({"active", "trialing"})


class StripeBillingAdapter:
    """Verify Stripe webhooks and create Stripe Checkout Sessions."""

    provider = "stripe"

    def __init__(
        self,
        *,
        webhook_secret: str,
        price_to_tier: Mapping[str, FeatureTier],
        tolerance_seconds: int = 300,
        api_key: str | None = None,
        api_base: str = "https://api.stripe.com",
        http_post: HttpPost = urllib_post,
    ) -> None:
        if not webhook_secret:
            raise ValueError("StripeBillingAdapter requires a webhook_secret.")
        self._secret = webhook_secret
        self._price_to_tier = dict(price_to_tier)
        self._tolerance = tolerance_seconds
        # Outbound checkout config (optional — a webhook-only deployment omits these).
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._http_post = http_post
        # Invert the price→tier map for checkout (tier → price). 1:1 in a normal setup.
        self._tier_to_price: dict[FeatureTier, str] = {
            tier: price for price, tier in self._price_to_tier.items()
        }

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

    # ── Checkout (outbound) ───────────────────────────────────────────────────────

    async def create_checkout(
        self,
        *,
        tenant: TenantId,
        tier: FeatureTier,
        success_url: str | None = None,
        cancel_url: str | None = None,
        customer_email: str | None = None,
    ) -> CheckoutSession:
        if not self._api_key:
            raise CheckoutError(
                "Stripe checkout is not configured (no api_key).",
                detail={"provider": self.provider},
            )
        price_id = self._tier_to_price.get(tier)
        if price_id is None:
            raise CheckoutError(
                f"No Stripe price mapped to tier {tier.value}.",
                detail={"tier": tier.value, "mapped_tiers": sorted(t.value for t in self._tier_to_price)},
            )
        if not success_url or not cancel_url:
            raise CheckoutError(
                "Stripe checkout requires success_url and cancel_url.",
                detail={"provider": self.provider},
            )

        # Stripe's API is form-encoded with bracketed nested keys. metadata.tenant on the subscription
        # is what the inbound webhook reads back (see _tenant); client_reference_id is a redundant copy.
        form: dict[str, str] = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(tenant),
            "subscription_data[metadata][tenant]": str(tenant),
        }
        if customer_email:
            form["customer_email"] = customer_email

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            status, text = await self._http_post(
                f"{self._api_base}/v1/checkout/sessions", urlencode(form).encode(), headers
            )
        except Exception as exc:  # noqa: BLE001 — surface any transport failure as a checkout error
            raise CheckoutError(f"Stripe checkout request failed: {exc}") from exc

        if status < 200 or status >= 300:
            raise CheckoutError(
                f"Stripe rejected the checkout request (HTTP {status}).",
                detail={"status": status, "body": text[:500]},
            )
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CheckoutError("Stripe checkout response is not valid JSON.") from exc
        url = doc.get("url")
        if not url:
            raise CheckoutError("Stripe checkout response is missing a redirect url.", detail={"body": doc})
        return CheckoutSession(
            provider=self.provider,
            tenant_id=tenant,
            tier=tier,
            url=str(url),
            reference=doc.get("id"),
        )

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
