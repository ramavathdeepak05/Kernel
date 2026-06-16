"""Redis-backed usage meter — exact per-tenant, per-UTC-day counts across workers/replicas.

Drop-in for the in-process `core.metering.UsageMeter`: same `record` / `actions_today` / `snapshot` /
`reset` surface, so the call sites (`RequestLoggingMiddleware`, `RateLimitMiddleware`, the admin API)
are unchanged. Use this in a horizontally-scaled SaaS deployment where the in-memory meter would
under-count (each worker keeps its own map). Counts live in Redis as ``<ns>:<tenant>:<utc-day>``
integers with a TTL so old days expire automatically.

The ``redis`` client is imported lazily (optional ``[redis]`` extra). Methods are synchronous to match
the meter surface; INCR/GET are sub-millisecond, so the brief call inside the async middleware is
acceptable. Counting is best-effort — a Redis blip must never fail a request, so callers already
swallow exceptions at the edge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.metering.meter import UsageSnapshot
from core.types import TenantId


def _utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


class RedisUsageMeter:
    """`UsageMeter`-compatible counter backed by Redis (shared across replicas)."""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        namespace: str = "quaicu:usage",
        ttl_seconds: int = 172_800,  # 48h: comfortably past the UTC-day boundary
    ) -> None:
        if client is None:
            # Lazy import: keeps redis an optional ([redis]) dependency, out of core.
            import redis

            client = redis.Redis.from_url(url or "redis://localhost:6379/0")
        self._r = client
        self._ns = namespace
        self._ttl = ttl_seconds

    def _key(self, tenant: str, day: str) -> str:
        return f"{self._ns}:{tenant}:{day}"

    def record(self, tenant: TenantId | str, *, now: datetime | None = None) -> int:
        """Atomically increment ``tenant``'s counter for the current UTC day; return the new count."""
        key = self._key(str(tenant), _utc_day(now))
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, self._ttl)
        count, _ = pipe.execute()
        return int(count)

    def actions_today(self, tenant: TenantId | str, *, now: datetime | None = None) -> int:
        """Return ``tenant``'s count for the current UTC day (0 if none / rolled over)."""
        val = self._r.get(self._key(str(tenant), _utc_day(now)))
        return int(val) if val is not None else 0

    def snapshot(self, tenant: TenantId | str, *, now: datetime | None = None) -> UsageSnapshot:
        """A `UsageSnapshot` for ``tenant`` (current UTC day)."""
        day = _utc_day(now)
        return UsageSnapshot(
            tenant_id=str(tenant), day=day, actions_today=self.actions_today(tenant, now=now)
        )

    def reset(self, tenant: TenantId | str, *, now: datetime | None = None) -> None:
        """Drop ``tenant``'s counter for the current UTC day (e.g. on plan change / test cleanup)."""
        self._r.delete(self._key(str(tenant), _utc_day(now)))
