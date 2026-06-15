"""Billing seams (WS-C) — two protocols, one direction each.

- `BillingPort` (inbound): given the **raw** body + headers of a webhook, it (1) verifies the
  provider's signature — fail-closed, raising `WebhookVerificationError` on any mismatch — and (2)
  distills the payload into a provider-neutral `BillingEvent`. The kernel never trusts a webhook it
  cannot cryptographically attribute to the provider. This path is intentionally synchronous and
  **pure** (HMAC + JSON only); no network calls, no SDK — auditable and testable without a processor.

- `CheckoutPort` (outbound): create a provider-hosted checkout/subscription so a tenant can start or
  upgrade a paid plan. This one *does* call the provider's REST API, so it is async and goes through
  an injectable HTTP transport (still no SDK). It stamps the tenant id into the provider metadata so
  the eventual webhook (the inbound side above) attributes the subscription back to the tenant.

An adapter may implement one or both. Keeping the two seams separate preserves the documented purity
guarantee of the verification path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from core.billing.model import BillingEvent, CheckoutSession
from core.entitlements.model import FeatureTier
from core.types import TenantId


@runtime_checkable
class BillingPort(Protocol):
    """Verify a provider webhook and normalize it to a `BillingEvent`."""

    #: The provider key this adapter handles ("stripe", "razorpay"). Used to route the webhook.
    provider: str

    def verify_and_parse(self, *, payload: bytes, headers: Mapping[str, str]) -> BillingEvent:
        """Verify the webhook signature and return a normalized event.

        Raises:
            WebhookVerificationError: signature missing/invalid/stale — MUST NOT mutate state.
            BillingEventError: signature valid but the payload references an unknown plan/tenant.
        """
        ...


@runtime_checkable
class CheckoutPort(Protocol):
    """Create a provider-hosted checkout/subscription for a tenant (outbound)."""

    provider: str

    async def create_checkout(
        self,
        *,
        tenant: TenantId,
        tier: FeatureTier,
        success_url: str | None = None,
        cancel_url: str | None = None,
        customer_email: str | None = None,
    ) -> CheckoutSession:
        """Create the session and return where to redirect the tenant to pay.

        Raises:
            CheckoutError: the adapter is not configured for checkout (no API key / unmapped tier),
                or the provider rejected the request. MUST stamp the tenant into provider metadata.
        """
        ...
