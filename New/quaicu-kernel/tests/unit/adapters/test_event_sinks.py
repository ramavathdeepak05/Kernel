"""Unit tests for the event-bus sinks (LoggingEventSink / PubSubEventSink) and their config wiring."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from adapters.events.memory import InMemoryEventBusAdapter
from adapters.events.sinks import LoggingEventSink, PubSubEventSink
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    Decision,
    IdempotencyKey,
    LedgerEntry,
    TenantId,
)
from delivery.sdk.kernel import Kernel

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def _entry() -> LedgerEntry:
    return LedgerEntry(
        ledger_seq=7,
        tenant=TenantId("acme"),
        action_id=ActionId("act-1"),
        action_type="loan.approve",
        actor_id=ActorId("alice"),
        decision=Decision.ALLOW,
        policy_versions=("pol:v1",),
        leaf_hash=b"\x11" * 32,
        sealed_at=NOW,
    )


def _action() -> Action:
    return Action(
        id=ActionId("act-1"),
        type="loan.approve",
        payload={},
        actor=Actor(id=ActorId("alice"), tenant=TenantId("acme")),
        tenant=TenantId("acme"),
        idempotency_key=IdempotencyKey("ik-1"),
        state=ActionState.EXECUTING,
        proposed_at=NOW,
    )


def test_logging_sink_emits_structured_audit_line(caplog):
    caplog.set_level(logging.INFO, logger="quaicu.audit")
    LoggingEventSink()(_action(), _entry())
    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert "tenant=acme" in rec.getMessage() and "seq=7" in rec.getMessage()
    # Structured fields are attached for log-based metrics / Cloud Logging.
    assert rec.tenant == "acme"
    assert rec.decision == "allow"
    assert rec.action_type == "loan.approve"
    assert rec.leaf_hash == ("11" * 32)


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, bytes]] = []

    def publish(self, topic: str, data: bytes):
        if self.fail:
            raise RuntimeError("pubsub unavailable")
        self.published.append((topic, data))
        return object()  # a future-like; the sink does not await it


def test_pubsub_sink_publishes_json():
    pub = _FakePublisher()
    PubSubEventSink("projects/p/topics/governed", publisher=pub)(_action(), _entry())
    assert len(pub.published) == 1
    topic, data = pub.published[0]
    assert topic == "projects/p/topics/governed"
    payload = json.loads(data)
    assert payload["tenant"] == "acme"
    assert payload["ledger_seq"] == 7
    assert payload["decision"] == "allow"


def test_pubsub_sink_is_best_effort_on_failure():
    pub = _FakePublisher(fail=True)
    # Must not raise — emit is best-effort.
    PubSubEventSink("t", publisher=pub)(_action(), _entry())


async def test_wired_log_sink_records_on_emit(caplog):
    # _wire_event_sinks subscribes the logging sink; emitting then produces an audit line.
    caplog.set_level(logging.INFO, logger="quaicu.audit")
    bus = InMemoryEventBusAdapter()
    Kernel._wire_event_sinks(bus, {"events": {"log_sink": True}})
    await bus.emit(action=_action(), entry=_entry())
    assert any(r.getMessage().startswith("governed_action sealed") for r in caplog.records)


def test_wire_event_sinks_noop_without_subscribe():
    # A bus/adapter without subscribe() (e.g. a future broker adapter) is tolerated.
    class _NoSub:
        pass

    Kernel._wire_event_sinks(_NoSub(), {"events": {"log_sink": True}})  # must not raise
