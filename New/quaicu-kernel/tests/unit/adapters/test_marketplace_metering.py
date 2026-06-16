"""Unit tests for MarketplaceMeteringReporter — the provider-neutral delta logic + meter integration.
The cloud `send` is a fake; the GCP/AWS senders are scaffolds and not exercised against real SDKs."""

from __future__ import annotations

from datetime import datetime, timezone

from adapters.billing import MarketplaceMeteringReporter, MeteringRecord
from core.metering import UsageMeter

DAY1 = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)


class _CapturingSend:
    """A fake marketplace send that records what it received and can be told to fail."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[MeteringRecord] = []

    def __call__(self, record: MeteringRecord) -> bool:
        if self.fail:
            return False
        self.sent.append(record)
        return True


def test_reports_delta_since_last_report():
    send = _CapturingSend()
    r = MarketplaceMeteringReporter(send=send, dimension="governed_actions")
    rec1 = r.report_tenant("acme", 10, now=DAY1)
    assert rec1 is not None and rec1.ok and rec1.quantity == 10
    # Next cycle: cumulative 15 → only the delta of 5 is reported.
    rec2 = r.report_tenant("acme", 15, now=DAY1)
    assert rec2 is not None and rec2.quantity == 5
    assert [s.quantity for s in send.sent] == [10, 5]


def test_no_delta_reports_nothing():
    send = _CapturingSend()
    r = MarketplaceMeteringReporter(send=send)
    r.report_tenant("acme", 10, now=DAY1)
    assert r.report_tenant("acme", 10, now=DAY1) is None  # unchanged → nothing to bill
    assert len(send.sent) == 1


def test_day_rollover_resets_baseline():
    send = _CapturingSend()
    r = MarketplaceMeteringReporter(send=send)
    r.report_tenant("acme", 100, now=DAY1)         # day 1: report 100
    rec = r.report_tenant("acme", 7, now=DAY2)     # day 2: counter restarted → report 7, not -93
    assert rec is not None and rec.quantity == 7


def test_failed_send_does_not_advance_baseline():
    send = _CapturingSend(fail=True)
    r = MarketplaceMeteringReporter(send=send)
    rec = r.report_tenant("acme", 10, now=DAY1)
    assert rec is not None and rec.ok is False
    # Baseline not advanced → the full delta is retried when send recovers.
    send.fail = False
    retry = r.report_tenant("acme", 10, now=DAY1)
    assert retry is not None and retry.ok and retry.quantity == 10


def test_send_exception_is_swallowed_best_effort():
    def _boom(_record: MeteringRecord) -> bool:
        raise RuntimeError("marketplace API down")

    r = MarketplaceMeteringReporter(send=_boom)
    rec = r.report_tenant("acme", 10, now=DAY1)  # must not raise
    assert rec is not None and rec.ok is False


def test_report_all_reads_from_a_usage_meter():
    meter = UsageMeter()
    meter.record("acme", now=DAY1)
    meter.record("acme", now=DAY1)
    meter.record("globex", now=DAY1)
    send = _CapturingSend()
    r = MarketplaceMeteringReporter(send=send)
    records = r.report_all(meter, ["acme", "globex", "initech"], now=DAY1)
    by_tenant = {rec.tenant_id: rec.quantity for rec in records}
    assert by_tenant == {"acme": 2, "globex": 1}  # initech has no usage → omitted
