"""Discount coupon book — percent/flat math, validation, the ₹1 floor, and config loading."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.billing.coupons import Coupon, CouponBook, CouponError

_BASE = 1_000_000  # ₹10,000 in paise


def _book(**over) -> CouponBook:
    base = dict(code="LAUNCH50", kind="percent", value=50, applies_to="starter")
    base.update(over)
    return CouponBook([Coupon(**base)])


def test_percent_discount():
    applied = _book().apply("LAUNCH50", _BASE, "starter")
    assert applied.final_paise == 500_000
    assert applied.discount_paise == 500_000


def test_flat_discount_capped_at_base():
    book = CouponBook([Coupon(code="FLAT", kind="flat", value=2_000_000, applies_to="all")])
    applied = book.apply("FLAT", _BASE, "starter")
    assert applied.final_paise == 100  # base - base, floored at ₹1


def test_full_discount_floors_at_one_rupee():
    book = CouponBook([Coupon(code="FREE", kind="percent", value=100, applies_to="all")])
    applied = book.apply("FREE", _BASE, "consultation")
    assert applied.final_paise == 100  # never zero — Razorpay minimum


def test_code_is_case_insensitive_and_trimmed():
    assert _book().apply("  launch50 ", _BASE, "starter").final_paise == 500_000


def test_unknown_code_raises():
    with pytest.raises(CouponError):
        _book().apply("NOPE", _BASE, "starter")


def test_wrong_target_raises():
    with pytest.raises(CouponError):
        _book(applies_to="starter").apply("LAUNCH50", _BASE, "consultation")


def test_all_target_applies_everywhere():
    book = _book(applies_to="all")
    assert book.apply("LAUNCH50", _BASE, "starter").final_paise == 500_000
    assert book.apply("LAUNCH50", _BASE, "consultation").final_paise == 500_000


def test_expired_coupon_raises():
    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(CouponError):
        _book(valid_until=yesterday).apply("LAUNCH50", _BASE, "starter")


def test_valid_until_is_inclusive_today():
    today = date.today()
    assert _book(valid_until=today).apply("LAUNCH50", _BASE, "starter", today=today).final_paise == 500_000


def test_from_config_parses_entries():
    book = CouponBook.from_config([
        {"code": "A", "kind": "percent", "value": 25, "applies_to": "all", "valid_until": "2099-01-01"},
        {"code": "", "kind": "flat", "value": 100},  # blank code skipped
    ])
    assert len(book) == 1
    assert book.apply("a", _BASE, "starter").final_paise == 750_000
