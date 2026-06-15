"""BillingPort — the provider-specific seam (WS-C).

An adapter implements `verify_and_parse`: given the **raw** request body and headers of an inbound
webhook, it (1) verifies the provider's signature — fail-closed, raising `WebhookVerificationError` on
any mismatch — and (2) distills the payload into a provider-neutral `BillingEvent`. The kernel never
trusts a webhook it cannot cryptographically attribute to the provider.

The protocol is intentionally synchronous and pure (HMAC + JSON only); no network calls, no SDK. That
keeps the verification path auditable and the adapters testable without a live processor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from core.billing.model import BillingEvent


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
