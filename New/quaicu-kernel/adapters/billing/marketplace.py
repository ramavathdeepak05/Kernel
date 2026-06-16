"""Cloud Marketplace usage metering (WS-C follow-up / ADR-0012 §5) — SCAFFOLD.

The *outbound usage-reporting* half of marketplace billing: it reads each tenant's consumption from a
`UsageMeter` and reports the **delta since the last report** to the cloud marketplace's metering API,
so customers are billed through their AWS/GCP commit credits (the inbound *entitlement* half — tier
changes — arrives as a provider webhook and reuses the existing `BillingEvent` → `BillingEngine` path,
exactly like Stripe/Razorpay).

Design:
- `MarketplaceMeteringReporter` (provider-neutral, fully implemented + tested) computes per-tenant
  daily deltas and is **best-effort** — a metering failure is logged and retried next cycle, never
  raised into the request path.
- The actual cloud API call is an injected ``send`` callable — the integration seam. `gcp_sender` /
  `aws_sender` build one by lazily importing the cloud SDK (optional ``[gcp]`` / ``[aws]`` extra). They
  are scaffolds: the request shape is sketched and the client is injectable for tests; wire the real
  SDK call where marked before production.

A scheduler (Cloud Scheduler / EventBridge / ARQ cron) calls `report_all(meter, tenants)` periodically
(e.g. hourly). This module deliberately owns no scheduler.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.metering.meter import UsageSnapshot, _utc_day

log = logging.getLogger("quaicu.billing")

# A ``send`` reports one usage record to the marketplace; returns True on success. Must not raise for
# expected failures (the reporter treats False as "retry next cycle").
SendFn = Callable[["MeteringRecord"], bool]


@dataclass(frozen=True)
class MeteringRecord:
    """One usage delta to report to a marketplace metering API."""

    tenant_id: str
    dimension: str          # the marketplace metering dimension / metric (e.g. "governed_actions")
    quantity: int           # delta since the last successful report (for the current UTC day)
    day: str                # UTC day the quantity accrued in
    reported_at: datetime
    ok: bool = False        # set True once the cloud API accepted it


class MarketplaceMeteringReporter:
    """Compute per-tenant usage deltas from a `UsageMeter` and report them, best-effort."""

    def __init__(self, *, send: SendFn, dimension: str = "governed_actions") -> None:
        self._send = send
        self._dimension = dimension
        self._lock = threading.Lock()
        # tenant -> (utc_day, last_reported_cumulative_count)
        self._baseline: dict[str, tuple[str, int]] = {}

    def _delta(self, tenant: str, day: str, actions_today: int) -> int:
        """Delta to report = current cumulative count − last reported (reset on a new UTC day)."""
        prev_day, prev_count = self._baseline.get(tenant, (day, 0))
        if prev_day != day:
            prev_count = 0  # new day → the day's counter restarted at 0
        return max(0, actions_today - prev_count)

    def report_tenant(
        self, tenant: str, actions_today: int, *, now: datetime | None = None
    ) -> MeteringRecord | None:
        """Report ``tenant``'s delta. Returns the record (``ok`` reflects success), or None if nothing
        to report. Best-effort: a `send` exception is logged, not raised, and the baseline is NOT
        advanced so the delta is retried next cycle."""
        day = _utc_day(now)
        with self._lock:
            delta = self._delta(tenant, day, actions_today)
            if delta <= 0:
                return None
            record = MeteringRecord(
                tenant_id=tenant,
                dimension=self._dimension,
                quantity=delta,
                day=day,
                reported_at=now or datetime.now(timezone.utc),
            )
            try:
                accepted = bool(self._send(record))
            except Exception as exc:  # noqa: BLE001 — metering must never break the caller
                log.warning("marketplace metering send failed for tenant=%s: %s", tenant, exc)
                accepted = False
            if accepted:
                self._baseline[tenant] = (day, actions_today)  # advance only on success
                log.info("metered tenant=%s dimension=%s qty=%s", tenant, self._dimension, delta)
            return MeteringRecord(**{**record.__dict__, "ok": accepted})

    def report_all(
        self, meter: Any, tenants: Iterable[str], *, now: datetime | None = None
    ) -> list[MeteringRecord]:
        """Report deltas for every tenant in ``tenants`` (any `UsageMeter`-compatible meter)."""
        out: list[MeteringRecord] = []
        for tenant in tenants:
            snap: UsageSnapshot = meter.snapshot(tenant, now=now)
            rec = self.report_tenant(tenant, snap.actions_today, now=now)
            if rec is not None:
                out.append(rec)
        return out


# ── Cloud send seams (SCAFFOLD — wire the real SDK call where marked) ──────────


def gcp_sender(service_name: str, *, client: Any | None = None) -> SendFn:
    """Build a `send` that reports usage to GCP Marketplace via the Service Control API.

    ``service_name`` is the producer's managed service (e.g. ``my-saas.endpoints.PROJECT.cloud.goog``).
    The client is lazily imported (``[gcp]`` extra) and injectable for tests.
    """

    def _send(record: MeteringRecord) -> bool:
        nonlocal client
        if client is None:
            from google.cloud import servicecontrol_v1  # lazy ([gcp] extra)

            client = servicecontrol_v1.ServiceControllerClient()
        # SEAM: build the Operation with a MetricValueSet for `record.dimension`/`record.quantity`
        # keyed by the tenant's consumer id, and call client.report(service_name=service_name, ...).
        # Returns True when the API accepts the operation. Left unimplemented in the scaffold.
        raise NotImplementedError(
            "Wire the GCP Service Control report call here (scaffold)."
        )

    return _send


def aws_sender(product_code: str, *, client: Any | None = None) -> SendFn:
    """Build a `send` that reports usage to AWS Marketplace via ``BatchMeterUsage``.

    ``product_code`` is the marketplace product code. boto3 is lazily imported (``[aws]`` extra) and
    the client is injectable for tests.
    """

    def _send(record: MeteringRecord) -> bool:
        nonlocal client
        if client is None:
            import boto3  # lazy ([aws] extra)

            client = boto3.client("meteringmarketplace")
        # SEAM: client.batch_meter_usage(ProductCode=product_code, UsageRecords=[{
        #   "Timestamp": record.reported_at, "CustomerIdentifier": record.tenant_id,
        #   "Dimension": record.dimension, "Quantity": record.quantity}])
        # Return True when the record lands in Results (not UnprocessedRecords).
        raise NotImplementedError(
            "Wire the AWS BatchMeterUsage call here (scaffold)."
        )

    return _send
