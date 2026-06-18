"""Signup payment gateway port (ADR-0011) — the ₹2 registration fee collected at signup.

A tiny seam: create a one-time order for the fixed fee, and verify the provider's payment signature
(pure HMAC, no network). The kernel gates account provisioning on a verified payment — no pay, no
account. Adapter: Razorpay Orders (`adapters/billing/razorpay_signup.py`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SignupPaymentGateway(Protocol):
    """Create a one-time signup-fee order and verify its payment signature."""

    @property
    def key_id(self) -> str:
        """Public provider key id (safe to expose to the browser checkout widget)."""
        ...

    @property
    def amount_paise(self) -> int: ...

    @property
    def currency(self) -> str: ...

    async def create_order(self, *, receipt: str) -> str:
        """Create the fee order with the provider; return its order id. Raises on provider error."""
        ...

    def verify_payment(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        """True iff the provider signature authenticates ``(order_id, payment_id)``. Pure (HMAC)."""
        ...
