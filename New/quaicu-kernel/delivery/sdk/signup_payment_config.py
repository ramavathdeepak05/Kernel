"""Config-driven signup-fee gateway wiring.

Returns a `SignupPaymentGateway` (Razorpay) when ``[signup_fee].enabled`` and credentials are present;
otherwise ``None`` (no fee — signup provisions directly on email verification). Keys resolve from
``${ENV}`` / ``RAZORPAY_KEY_ID`` + ``RAZORPAY_KEY_SECRET`` so secrets stay out of the file.

Config shape::

    [signup_fee]
    enabled      = true
    amount_paise = 200          # ₹2
    currency     = "INR"
    key_id       = "${RAZORPAY_KEY_ID}"
    key_secret   = "${RAZORPAY_KEY_SECRET}"
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def build_signup_payment(config: Mapping[str, Any]) -> Any | None:
    section = config.get("signup_fee", {}) or {}
    if not section.get("enabled"):
        return None
    key_id = (
        os.path.expandvars(str(section.get("key_id", ""))) or os.getenv("RAZORPAY_KEY_ID", "")
    ).strip()
    key_secret = (
        os.path.expandvars(str(section.get("key_secret", ""))) or os.getenv("RAZORPAY_KEY_SECRET", "")
    ).strip()
    if not key_id or not key_secret:
        return None

    from adapters.billing.razorpay_signup import RazorpaySignupGateway

    return RazorpaySignupGateway(
        key_id=key_id,
        key_secret=key_secret,
        amount_paise=int(section.get("amount_paise", 200)),
        currency=str(section.get("currency", "INR")),
    )
