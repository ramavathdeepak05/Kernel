"""Build the coupon book from the plane config (``[[coupon]]`` entries). Empty book if none."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.billing.coupons import CouponBook


def build_coupon_book(config: Mapping[str, Any]) -> CouponBook:
    return CouponBook.from_config(config.get("coupon", []))
