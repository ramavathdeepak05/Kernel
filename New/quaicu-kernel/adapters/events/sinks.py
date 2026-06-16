"""Event-bus sinks — record every sealed governed action to an external stream (K·07).

These are `EventBus` subscribers (``Callable[[Action, LedgerEntry], Any]``) registered via
``event_bus.subscribe(...)``. They give a **durable, queryable record of every governed decision even
when the ledger is in-memory** (the free tier): the kernel emits a `LedgerEntry` after each seal, and
these sinks fan it out off-box.

- `LoggingEventSink` — writes one structured audit line per action to the ``quaicu.audit`` logger. On
  Cloud Run / Kubernetes the stdout line is captured by the platform's logging (Cloud Logging), so no
  database is required to see "what each client's product is doing". Pure stdlib, zero dependencies.
- `PubSubEventSink` — publishes each action as JSON to a GCP Pub/Sub topic for fan-out to BigQuery /
  SIEM / Chronicle. Lazy ``google-cloud-pubsub`` (``[gcp]`` extra); publisher injectable for tests.

Both are **best-effort** (the contract for K·07 emit): a sink failure is logged, never raised into the
seal path. Wire them config-driven via ``[events].log_sink`` / ``[events].pubsub_topic`` (see
``Kernel.from_config``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.types import Action, Decision, LedgerEntry

audit_log = logging.getLogger("quaicu.audit")
log = logging.getLogger("quaicu.events")


def _entry_record(entry: LedgerEntry) -> dict[str, Any]:
    """A JSON-serializable record of a sealed governed action (the durable audit shape)."""
    decision = entry.decision.value if isinstance(entry.decision, Decision) else str(entry.decision)
    return {
        "event": "governed_action",
        "ledger_seq": entry.ledger_seq,
        "tenant": str(entry.tenant),
        "action_id": str(entry.action_id),
        "action_type": entry.action_type,
        "actor_id": str(entry.actor_id),
        "decision": decision,
        "policy_versions": list(entry.policy_versions),
        "leaf_hash": entry.leaf_hash.hex(),
        "sealed_at": entry.sealed_at.isoformat(),
    }


class LoggingEventSink:
    """Log one structured audit line per sealed governed action (→ Cloud Logging on managed hosts)."""

    def __init__(self, *, logger: logging.Logger | None = None, level: int = logging.INFO) -> None:
        self._log = logger or audit_log
        self._level = level

    def __call__(self, action: Action, entry: LedgerEntry) -> None:
        rec = _entry_record(entry)
        # Human-readable message + structured `extra` (mirrors RequestLoggingMiddleware's pattern).
        self._log.log(
            self._level,
            "governed_action sealed seq=%s tenant=%s action=%s type=%s decision=%s",
            rec["ledger_seq"], rec["tenant"], rec["action_id"], rec["action_type"], rec["decision"],
            extra=rec,
        )


class PubSubEventSink:
    """Publish each sealed governed action as JSON to a GCP Pub/Sub topic (best-effort)."""

    def __init__(self, topic: str, *, publisher: Any | None = None) -> None:
        self._topic = topic
        if publisher is None:
            from google.cloud import pubsub_v1  # lazy ([gcp] extra)

            publisher = pubsub_v1.PublisherClient()
        self._publisher = publisher

    def __call__(self, action: Action, entry: LedgerEntry) -> None:
        data = json.dumps(_entry_record(entry)).encode("utf-8")
        try:
            self._publisher.publish(self._topic, data)  # fire-and-forget; returns a future
        except Exception as exc:  # noqa: BLE001 — emit must never fail on a best-effort sink
            log.warning("PubSubEventSink publish failed (topic=%s): %s", self._topic, exc)
