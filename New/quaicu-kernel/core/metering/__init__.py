"""Usage metering (WS-C) — the per-tenant daily request counter the access log feeds.

The metering layer turns the structured access log (`delivery/api/observability`) into a billable
record of *how much* each tenant used the kernel. It is deliberately tiny and dependency-free: an
in-process per-tenant, per-UTC-day counter that the request-logging middleware increments and the
admin API / daily-quota enforcement read.
"""

from core.metering.meter import UsageMeter, UsageSnapshot

__all__ = ["UsageMeter", "UsageSnapshot"]
