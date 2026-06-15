"""In-process usage meter — per-tenant, per-UTC-day governed-request counter (WS-C).

`UsageMeter` is the substrate for billing usage and daily-quota enforcement. The request-logging
middleware calls `record(tenant)` once per metered request; the entitlement layer reads
`actions_today(tenant)` to enforce ``max_actions_per_day``; the admin API reads `snapshot()` to report
consumption. Counts roll over automatically at the UTC day boundary.

Thread-safe (a `threading.Lock` guards the map). Single-process, like the rate limiter — a horizontal
deployment swaps the in-memory map for a shared store (Redis) behind the same surface; the call sites
are unchanged. Counting is intentionally best-effort: a meter failure must never fail a request, so
callers swallow exceptions at the edge.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from core.types import TenantId


def _utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class UsageSnapshot:
    """A point-in-time read of one tenant's usage."""

    tenant_id: str
    day: str
    actions_today: int


class UsageMeter:
    """Per-tenant, per-UTC-day request counter."""

    def __init__(self) -> None:
        # tenant -> (utc_day, count)
        self._counts: dict[str, tuple[str, int]] = {}
        self._lock = threading.Lock()

    def record(self, tenant: TenantId | str, *, now: datetime | None = None) -> int:
        """Increment ``tenant``'s counter for the current UTC day; return the new count."""
        key = str(tenant)
        day = _utc_day(now)
        with self._lock:
            cur_day, count = self._counts.get(key, (day, 0))
            if cur_day != day:  # new day → reset
                count = 0
            count += 1
            self._counts[key] = (day, count)
            return count

    def actions_today(self, tenant: TenantId | str, *, now: datetime | None = None) -> int:
        """Return ``tenant``'s count for the current UTC day (0 if none / rolled over)."""
        key = str(tenant)
        day = _utc_day(now)
        with self._lock:
            cur_day, count = self._counts.get(key, (day, 0))
            return count if cur_day == day else 0

    def snapshot(self, tenant: TenantId | str, *, now: datetime | None = None) -> UsageSnapshot:
        """A `UsageSnapshot` for ``tenant`` (current UTC day)."""
        day = _utc_day(now)
        return UsageSnapshot(tenant_id=str(tenant), day=day, actions_today=self.actions_today(tenant, now=now))

    def reset(self, tenant: TenantId | str) -> None:
        """Drop a tenant's counter (e.g. on plan change / test cleanup)."""
        with self._lock:
            self._counts.pop(str(tenant), None)
