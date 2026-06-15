"""Unit tests for the per-tenant, per-UTC-day UsageMeter (WS-C)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.metering import UsageMeter
from core.types import TenantId

T = TenantId("ciro-bank")


def test_record_increments():
    m = UsageMeter()
    assert m.record(T) == 1
    assert m.record(T) == 2
    assert m.actions_today(T) == 2


def test_tenants_counted_independently():
    m = UsageMeter()
    m.record("a")
    m.record("a")
    m.record("b")
    assert m.actions_today("a") == 2
    assert m.actions_today("b") == 1


def test_counter_resets_on_new_utc_day():
    m = UsageMeter()
    day1 = datetime(2026, 6, 13, 23, 59, tzinfo=timezone.utc)
    day2 = day1 + timedelta(minutes=2)  # crosses midnight UTC
    m.record(T, now=day1)
    m.record(T, now=day1)
    assert m.actions_today(T, now=day1) == 2
    assert m.actions_today(T, now=day2) == 0  # rolled over
    assert m.record(T, now=day2) == 1


def test_snapshot_reports_day_and_count():
    m = UsageMeter()
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    m.record(T, now=now)
    snap = m.snapshot(T, now=now)
    assert snap.tenant_id == "ciro-bank"
    assert snap.day == "2026-06-13"
    assert snap.actions_today == 1


def test_reset_clears_tenant():
    m = UsageMeter()
    m.record(T)
    m.reset(T)
    assert m.actions_today(T) == 0
