"""Razorpay billing adapter (WS-C) — inbound webhooks + outbound subscription creation.

Inbound (`BillingPort.verify_and_parse`): verifies the ``X-Razorpay-Signature`` header (HMAC-SHA256 of
the raw body with the webhook secret) and maps subscription events to provider-neutral `BillingEvent`s.

Outbound (`CheckoutPort.create_checkout`): creates a Razorpay subscription via the REST API (Basic
auth) through an injectable HTTP transport, stamping ``notes.tenant`` so the resulting webhook
attributes it back to the tenant; returns the subscription's hosted ``short_url`` to redirect to.
No ``razorpay`` SDK dependency in either direction.

Tenant resolution: the kernel stamps ``notes.tenant`` at creation; this adapter reads it back. Tier
resolution: an injected ``plan_to_tier`` map (Razorpay plan id → tier), inverted for checkout.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping

from adapters.billing._http import HttpPost, urllib_post
from core.billing.model import BillingEvent, BillingEventType, CheckoutSession
from core.entitlements.model import FeatureTier
from core.errors import BillingEventError, CheckoutError, WebhookVerificationError
from core.types import TenantId

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
        key_id: str | None = None,
        key_secret: str | None = None,
        api_base: str = "https://api.razorpay.com",
        subscription_total_count: int = 12,
        http_post: HttpPost = urllib_post,
    ) -> None:
        if not webhook_secret:
            raise ValueError("RazorpayBillingAdapter requires a webhook_secret.")
        self._secret = webhook_secret
        self._plan_to_tier = dict(plan_to_tier)
        # Outbound checkout config (optional — a webhook-only deployment omits these).
        self._key_id = key_id
        self._key_secret = key_secret
        self._api_base = api_base.rstrip("/")
        self._total_count = subscription_total_count
        self._http_post = http_post
        self._tier_to_plan: dict[FeatureTier, str] = {
            tier: plan for plan, tier in self._plan_to_tier.items()
        }

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

    # ── Checkout (outbound) ───────────────────────────────────────────────────────

    async def create_checkout(
        self,
        *,
        tenant: TenantId,
        tier: FeatureTier,
        success_url: str | None = None,  # noqa: ARG002 — Razorpay hosts its own return page
        cancel_url: str | None = None,   # noqa: ARG002
        customer_email: str | None = None,
    ) -> CheckoutSession:
        if not self._key_id or not self._key_secret:
            raise CheckoutError(
                "Razorpay checkout is not configured (no key_id/key_secret).",
                detail={"provider": self.provider},
            )
        plan_id = self._tier_to_plan.get(tier)
        if plan_id is None:
            raise CheckoutError(
                f"No Razorpay plan mapped to tier {tier.value}.",
                detail={"tier": tier.value, "mapped_tiers": sorted(t.value for t in self._tier_to_plan)},
            )

        # notes.tenant is what the inbound webhook reads back (see _tenant).
        body: dict[str, object] = {
            "plan_id": plan_id,
            "total_count": self._total_count,
            "customer_notify": 1,
            "notes": {"tenant": str(tenant)},
        }
        if customer_email:
            body["notes"]["tenant_email"] = customer_email  # type: ignore[index]

        token = base64.b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        try:
            status, text = await self._http_post(
                f"{self._api_base}/v1/subscriptions", json.dumps(body).encode(), headers
            )
        except Exception as exc:  # noqa: BLE001 — surface any transport failure as a checkout error
            raise CheckoutError(f"Razorpay checkout request failed: {exc}") from exc

        if status < 200 or status >= 300:
            raise CheckoutError(
                f"Razorpay rejected the subscription request (HTTP {status}).",
                detail={"status": status, "body": text[:500]},
            )
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CheckoutError("Razorpay checkout response is not valid JSON.") from exc
        url = doc.get("short_url")
        if not url:
            raise CheckoutError(
                "Razorpay subscription response is missing short_url.", detail={"body": doc}
            )
        return CheckoutSession(
            provider=self.provider,
            tenant_id=tenant,
            tier=tier,
            url=str(url),
            reference=doc.get("id"),
        )

    @staticmethod
    def _tenant(entity: dict):
        from core.types import TenantId

        notes = entity.get("notes") or {}
        tenant = notes.get("tenant") or notes.get("tenant_id")
        return TenantId(str(tenant)) if tenant else None
