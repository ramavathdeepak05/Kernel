"""Unit tests for RedisUsageMeter — a minimal in-memory fake stands in for the redis client, so no
real Redis is required. Verifies the meter is a behavioral drop-in for the in-process UsageMeter."""

from __future__ import annotations

from datetime import datetime, timezone

from adapters.metering import RedisUsageMeter

DAY1 = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)


class _FakePipeline:
    def __init__(self, store: dict, expires: dict) -> None:
        self._store = store
        self._expires = expires
        self._ops: list = []

    def incr(self, key: str):
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", key, ttl))
        return self

    def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "incr":
                self._store[op[1]] = self._store.get(op[1], 0) + 1
                results.append(self._store[op[1]])
            elif op[0] == "expire":
                self._expires[op[1]] = op[2]
                results.append(True)
        self._ops.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store, self.expires)

    def get(self, key: str):
        v = self.store.get(key)
        return None if v is None else str(v).encode()

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


def _meter() -> tuple[RedisUsageMeter, _FakeRedis]:
    fake = _FakeRedis()
    return RedisUsageMeter(client=fake, namespace="t:usage", ttl_seconds=100), fake


def test_record_increments_and_returns_count():
    meter, _ = _meter()
    assert meter.record("acme", now=DAY1) == 1
    assert meter.record("acme", now=DAY1) == 2
    assert meter.actions_today("acme", now=DAY1) == 2


def test_record_sets_ttl():
    meter, fake = _meter()
    meter.record("acme", now=DAY1)
    assert fake.expires["t:usage:acme:2026-06-16"] == 100


def test_counts_are_isolated_per_tenant():
    meter, _ = _meter()
    meter.record("acme", now=DAY1)
    meter.record("acme", now=DAY1)
    meter.record("globex", now=DAY1)
    assert meter.actions_today("acme", now=DAY1) == 2
    assert meter.actions_today("globex", now=DAY1) == 1


def test_counter_rolls_over_at_utc_day():
    meter, _ = _meter()
    meter.record("acme", now=DAY1)
    assert meter.actions_today("acme", now=DAY1) == 1
    assert meter.actions_today("acme", now=DAY2) == 0  # different day key → fresh


def test_snapshot_and_reset():
    meter, _ = _meter()
    meter.record("acme", now=DAY1)
    snap = meter.snapshot("acme", now=DAY1)
    assert snap.tenant_id == "acme" and snap.day == "2026-06-16" and snap.actions_today == 1
    meter.reset("acme", now=DAY1)
    assert meter.actions_today("acme", now=DAY1) == 0
