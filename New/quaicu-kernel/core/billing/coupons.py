"""Discount coupons — applied to the signup fee / consultation deposit before the Razorpay order.

Coupons are operator-defined (config ``[[coupon]]`` entries) and resolved entirely in the kernel: we
reduce the order ``amount_paise`` *before* creating the Razorpay Order, so Razorpay simply charges the
discounted amount and never needs to know about the code. A fully-discounting coupon floors at
``_MIN_PAISE`` (₹1, Razorpay's minimum), so the existing pay→verify→provision path is unchanged — a
"100% off" code becomes a ₹1 registration charge rather than a separate free-provisioning branch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from core.errors import QUAICUError

# Razorpay's minimum order amount. A coupon can never take the charge below this.
_MIN_PAISE = 100  # ₹1

# Valid discount targets.
TARGETS = ("starter", "consultation")


class CouponError(QUAICUError):
    code = "COUPON_INVALID"


@dataclass(frozen=True)
class Coupon:
    code: str
    kind: str  # "percent" | "flat"
    value: int  # percent (0–100) when kind=percent, else paise off when kind=flat
    applies_to: str = "all"  # "starter" | "consultation" | "all"
    valid_until: date | None = None
    description: str = ""

    def discount_paise(self, base_paise: int) -> int:
        if self.kind == "percent":
            pct = min(max(self.value, 0), 100)
            return base_paise * pct // 100
        return min(max(self.value, 0), base_paise)  # flat, never more than the base


@dataclass(frozen=True)
class AppliedCoupon:
    code: str
    description: str
    discount_paise: int  # how much was taken off (after the ₹1 floor)
    final_paise: int  # what the customer will actually be charged


class CouponBook:
    """An operator's set of coupons, looked up case-insensitively by code."""

    def __init__(self, coupons: Sequence[Coupon]) -> None:
        self._by_code: dict[str, Coupon] = {
            c.code.strip().upper(): c for c in coupons if c.code.strip()
        }

    def __len__(self) -> int:
        return len(self._by_code)

    def apply(
        self, code: str, base_paise: int, target: str, *, today: date | None = None
    ) -> AppliedCoupon:
        """Validate ``code`` for ``target`` and return the discounted charge. Raises CouponError.

        Fail-closed: an unknown / expired / wrong-target code raises rather than silently charging
        full price, so the caller can surface the error and let the user fix or drop the code.
        """
        coupon = self._by_code.get((code or "").strip().upper())
        if coupon is None:
            raise CouponError("That coupon code isn't valid.", detail={"coupon": code})
        if coupon.valid_until is not None and (today or date.today()) > coupon.valid_until:
            raise CouponError("That coupon has expired.", detail={"coupon": code})
        if coupon.applies_to not in ("all", target):
            raise CouponError(
                "That coupon doesn't apply to this purchase.",
                detail={"coupon": code, "applies_to": coupon.applies_to},
            )
        final = max(base_paise - coupon.discount_paise(base_paise), _MIN_PAISE)
        return AppliedCoupon(
            code=coupon.code,
            description=coupon.description,
            discount_paise=base_paise - final,
            final_paise=final,
        )

    @classmethod
    def from_config(cls, items: Sequence[Mapping[str, Any]] | None) -> CouponBook:
        coupons: list[Coupon] = []
        for it in items or []:
            code = str(it.get("code", "")).strip()
            if not code:
                continue
            raw_until = it.get("valid_until")
            valid_until = date.fromisoformat(str(raw_until)) if raw_until else None
            coupons.append(
                Coupon(
                    code=code,
                    kind=str(it.get("kind", "percent")).lower(),
                    value=int(it.get("value", 0)),
                    applies_to=str(it.get("applies_to", "all")).lower(),
                    valid_until=valid_until,
                    description=str(it.get("description", "")),
                )
            )
        return cls(coupons)
