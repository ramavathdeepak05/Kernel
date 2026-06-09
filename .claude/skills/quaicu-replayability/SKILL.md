---
name: quaicu-replayability
description: |
  QUAICU replay-safe design enforcer (Frozen Decision F-09). Use when designing or reviewing any
  component that touches state, the ledger, K·12 rollback, K·13 sandbox, or K·14 point-in-time
  evidence. Enforces: event-sourced shape, non-determinism recorded and reused (never recomputed),
  replay never causes external effects, idempotent state reconstruction, signed point-in-time
  evidence packs. Trigger keywords: replay, event_sourcing, state_reconstruction, counterfactual,
  audit_replay, side_effect_free, recorded_nondeterminism, replay_safe, rollback, sandbox,
  point_in_time, projection, F-09, snapshot, replay cursor, evidence pack, idempotent.
---

# QUAICU Replayability

You are the replayability enforcer. Replay underpins audit (K·02), rollback (K·12), sandbox (K·13),
and point-in-time evidence (K·14). A replay that causes a side effect is a **critical bug**. A
replay that recomputes non-determinism is incorrect — it may produce a different answer and
undermine the entire audit story. Every design decision in this skill flows from one rule:
**the ledger is the source of truth; everything else is a projection**.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every replay choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → make replay read-only and stop.

### Invariants — never violated
- The ledger is the source of truth; everything else is a projection. ALWAYS rebuild state from the ledger, never the reverse.
- Replay is ALWAYS side-effect-free: no model calls, no disbursements, no notifications, no writes to live tables. A side effect on replay is a CRITICAL bug.
- ALWAYS reuse recorded non-determinism (model outputs, timestamps, random) from the entry. NEVER recompute it on replay.
- Entries ALWAYS record inputs AND results (and the policy/model versions in effect). Recording only outcomes is insufficient — reject it.
- Large ledgers ALWAYS use a streaming cursor (+ snapshots). NEVER load all events into memory.

### Three replay modes (pick by intent)
| Mode | Purpose | Uses | Writes |
|---|---|---|---|
| State reconstruction | rebuild state at time T | recorded events up to T | nothing (pure) |
| Decision audit replay | re-derive the decision | policy/model **versions from the entry** | nothing |
| Counterfactual (K·13) | "what if policy X?" | recorded model outputs + new policy | shadow partition ONLY |

### Tie-break rules
- May replay call a model/service? → NO. Use the recorded output.
- Which policy version for audit replay? → the version recorded in the entry, NOT the current active policy.
- Where do counterfactual results go? → a shadow/sandbox partition, never the real ledger or live tables.
- Recompute a timestamp? → NO; use the recorded one (determinism).

### Stop-and-apply triggers
- About to call a model/port during replay? → STOP, read the recorded result.
- About to write to a live table during replay? → STOP, replay is read-only (counterfactual → shadow only).
- About to use the current active policy for audit replay? → STOP, use the entry's recorded version.

### Self-check
- [ ] Replay path makes zero external calls and zero live writes.
- [ ] Recorded non-determinism is reused, never recomputed.
- [ ] Audit replay uses versions from the entry, not current state.
- [ ] Counterfactual writes only to a shadow partition.
- [ ] Large-ledger path streams with a cursor + snapshots.

---

## Frozen Decision F-09

> **Replay-safe, side-effect-free execution.** Actions are re-derivable from the ledger using the
> versions/results in effect at the time; non-determinism is recorded, never recomputed; replay
> never causes an external effect.

Hard violations — raise these in code review immediately:
- "Recompute model calls on replay" — **NO. Call the model again and you get a different answer.**
- "Let replay re-trigger effects (disbursements, notifications)" — **NO. Side effects on replay is a critical bug.**
- "Record only outcomes, not inputs" — **NO. Insufficient to reconstruct the decision.**
- "Replay all events into memory before processing" — **NO for large ledgers. Use a streaming cursor.**

---

## Error Type Hierarchy

```python
# core/errors/replay.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class ReplayErrorCode(str, Enum):
    # Ledger / event store
    MISSING_AGGREGATE_SEQUENCE   = "REPLAY_001"
    SEQUENCE_GAP_DETECTED        = "REPLAY_002"
    DUPLICATE_SEQUENCE           = "REPLAY_003"
    HASH_CHAIN_BROKEN            = "REPLAY_004"

    # Non-determinism recording
    MISSING_RECORDED_NONDETERMINISM = "REPLAY_010"
    ACTIVITY_ALREADY_RECORDED    = "REPLAY_011"
    LIVE_CALL_DURING_REPLAY      = "REPLAY_012"   # CRITICAL

    # State reconstruction
    SNAPSHOT_CORRUPT             = "REPLAY_020"
    SNAPSHOT_SEQUENCE_AHEAD      = "REPLAY_021"
    RECONSTRUCTION_MISMATCH      = "REPLAY_022"   # idempotency violated

    # Counterfactual / conflict
    POLICY_CONFLICT_DETECTED     = "REPLAY_030"
    COUNTERFACTUAL_WROTE_PRODUCTION = "REPLAY_031"  # CRITICAL

    # Evidence pack
    EVIDENCE_PACK_SIGN_FAILED    = "REPLAY_040"
    EVIDENCE_PACK_VERIFY_FAILED  = "REPLAY_041"
    POLICY_VERSION_NOT_FOUND     = "REPLAY_042"

    # Side effects
    SIDE_EFFECT_DURING_REPLAY    = "REPLAY_050"   # CRITICAL


@dataclass
class ReplayError(Exception):
    code: ReplayErrorCode
    message: str
    aggregate_id: str | None = None
    sequence: int | None = None
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.aggregate_id:
            parts.append(f"aggregate={self.aggregate_id!r}")
        if self.sequence is not None:
            parts.append(f"seq={self.sequence}")
        return " | ".join(parts)


class LiveCallDuringReplayError(ReplayError):
    """
    CRITICAL. Raised when a live external call (model, API) is attempted during replay.
    Must be logged at ERROR severity. This means the replay path called execute_fn
    instead of returning the recorded result.
    """


class SideEffectDuringReplayError(ReplayError):
    """
    CRITICAL. Raised when a side effect (disbursement, notification, write to production
    ledger) is detected during a replay or counterfactual run.
    """


class CounterfactualProductionWriteError(ReplayError):
    """
    CRITICAL. Raised when a counterfactual replay attempts to write to the production ledger.
    """


class PolicyConflictError(ReplayError):
    """
    Raised when two candidate policies in a counterfactual evaluation produce
    conflicting decisions for the same action.
    """


class SnapshotCorruptError(ReplayError):
    """Raised when a snapshot's hash does not match its content at load time."""


class EvidencePackVerificationError(ReplayError):
    """Raised when a signed evidence pack fails signature or hash verification."""
```

---

## Three Replay Modes (distinct — do not conflate)

| Mode | Purpose | Input | Output |
|------|---------|-------|--------|
| **State reconstruction** | Rebuild institutional state as of time T | Ledger events up to T (via snapshot + delta) | Current state projection |
| **Decision (audit) replay** | Re-derive *why* a past decision was made | Ledger entry + policy versions + signals at time of decision | Same decision, same reasoning |
| **Counterfactual replay** | See what would change under a different policy | Ledger + candidate policy/model | Shadow impact report (K·13 Sandbox) |

---

## Full Event Store Schema (aggregate_id + sequence)

The ledger is event-sourced. Every governed action appends one or more events to the
event store. State is a projection — derived from events, never the primary record.

```sql
-- migrations/versions/xxxx_event_store.sql
-- Lives in the tenant's schema (schema-per-tenant, F-07).

CREATE TABLE events (
    -- Primary ordering
    global_seq      BIGSERIAL PRIMARY KEY,          -- global monotonic sequence across all aggregates
    tenant_id       TEXT        NOT NULL,            -- RLS enforced
    aggregate_id    UUID        NOT NULL,            -- entity being governed (action_id, workflow_id, etc.)
    aggregate_type  TEXT        NOT NULL,            -- 'action' | 'workflow' | 'policy' | 'consent'
    sequence        BIGINT      NOT NULL,            -- per-aggregate monotonic sequence (starts at 1)

    -- Event content
    event_type      TEXT        NOT NULL,            -- 'action.proposed' | 'policy.evaluated' | etc.
    event_version   INT         NOT NULL DEFAULT 1, -- event schema version for forward compatibility
    payload         JSONB       NOT NULL,            -- full event payload

    -- Replay inputs — must be sufficient to reconstruct the decision
    policy_versions JSONB,                           -- exact {policy_id: version} map evaluated
    consent_state   JSONB,                           -- K·04 state at evaluation time
    assurance_signals JSONB,                         -- K·08–K·11 signals at evaluation time
    recorded_nondeterminism JSONB,                   -- K·05 model outputs, external results, etc.

    -- Integrity
    event_hash      BYTEA       NOT NULL,            -- SHA-256(prev_hash || event_type || payload)
    prev_hash       BYTEA,                           -- null for first event of an aggregate
    actor_id        TEXT        NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Uniqueness: one sequence per aggregate
    CONSTRAINT uq_aggregate_sequence UNIQUE (tenant_id, aggregate_id, sequence)
);

CREATE INDEX idx_events_aggregate
    ON events (tenant_id, aggregate_id, sequence ASC);

CREATE INDEX idx_events_global_seq
    ON events (tenant_id, global_seq ASC);

CREATE INDEX idx_events_occurred_at
    ON events (tenant_id, occurred_at);

-- Snapshots table: checkpoint every N events for fast reconstruction
CREATE TABLE event_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT        NOT NULL,
    aggregate_id    UUID        NOT NULL,
    aggregate_type  TEXT        NOT NULL,
    snapshot_seq    BIGINT      NOT NULL,           -- the aggregate sequence at which this snapshot was taken
    state_json      JSONB       NOT NULL,           -- serialized state at snapshot_seq
    snapshot_hash   BYTEA       NOT NULL,           -- SHA-256 of state_json for integrity
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_snapshot UNIQUE (tenant_id, aggregate_id, snapshot_seq)
);

CREATE INDEX idx_snapshots_aggregate
    ON event_snapshots (tenant_id, aggregate_id, snapshot_seq DESC);
```

---

## Non-Determinism Recording Rule (mandatory everywhere)

Anything non-deterministic records its result **at original execution**. On replay, the
recorded result is returned without executing the live call.

```
Non-deterministic operations — MUST record:
  - Model calls (K·05 AI Gateway) → recorded in events.recorded_nondeterminism
  - External API lookups → recorded as workflow activity events
  - Random values (UUIDs generated in workflow steps) → recorded
  - Timestamps used in workflow branching → use workflow.now(), recorded by engine
  - Third-party risk scores, external signals → recorded as assurance_signals

Deterministic operations — no recording needed:
  - CEL policy evaluation (pure function of action + policy text — F-05)
  - State projection from event log
  - Hash computations
  - Ledger inclusion/consistency proof verification
```

```python
# core/replay/activity_recorder.py
from __future__ import annotations
import json
import hashlib
from typing import Any, Callable, Awaitable, TypeVar
from opentelemetry import trace

from core.errors.replay import (
    LiveCallDuringReplayError, ReplayErrorCode,
    ReplayError,
)

tracer = trace.get_tracer("quaicu.activity_recorder")
T = TypeVar("T")

_REPLAY_MODE_KEY = "_quaicu_replay_mode"


class ActivityRecorder:
    """
    Implements the Temporal pattern for non-determinism recording.
    In live mode: execute, record, return.
    In replay mode: return recorded result, NEVER execute the live function.
    """

    def __init__(self, event_store: "EventStore", *, replay_mode: bool = False) -> None:
        self._store = event_store
        self._replay_mode = replay_mode

    async def record_activity(
        self,
        aggregate_id: str,
        activity_name: str,
        execute_fn: Callable[[], Awaitable[T]],
        *,
        tenant_id: str,
    ) -> T:
        """
        Live path: execute execute_fn, record result, return.
        Replay path: return recorded result. If no record exists in replay mode, raise —
        this means a non-deterministic call was added to a workflow after events were
        already recorded (a workflow evolution bug).
        """
        with tracer.start_as_current_span("quaicu.record_activity") as span:
            span.set_attribute("quaicu.aggregate_id", str(aggregate_id))
            span.set_attribute("quaicu.activity_name", activity_name)
            span.set_attribute("quaicu.replay_mode", self._replay_mode)

            recorded = await self._store.get_recorded_activity(
                aggregate_id, activity_name, tenant_id=tenant_id
            )

            if recorded is not None:
                span.set_attribute("quaicu.activity_source", "recorded")
                return recorded

            if self._replay_mode:
                # We are replaying but have no recorded result — this is a critical error.
                raise LiveCallDuringReplayError(
                    code=ReplayErrorCode.LIVE_CALL_DURING_REPLAY,
                    message=(
                        f"Replay path attempted live call for activity {activity_name!r} "
                        f"on aggregate {aggregate_id!r} but no recorded result exists. "
                        "This may indicate a workflow evolution bug — a non-deterministic "
                        "activity was added after events were already sealed."
                    ),
                    aggregate_id=str(aggregate_id),
                )

            # Live path: execute and record
            span.set_attribute("quaicu.activity_source", "live")
            result = await execute_fn()
            await self._store.record_activity(
                aggregate_id, activity_name, result, tenant_id=tenant_id
            )
            return result
```

---

## Snapshot Optimization (checkpoint every N events + replay from latest snapshot)

For aggregates with many events, replaying from event zero is O(n). Snapshots
checkpoint state every N events, reducing replay to O(n mod checkpoint_interval).

```python
# core/replay/snapshot.py
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace

from core.errors.replay import SnapshotCorruptError, ReplayErrorCode

tracer = trace.get_tracer("quaicu.snapshot")

SNAPSHOT_INTERVAL = 100    # checkpoint every 100 events per aggregate


@dataclass
class Snapshot:
    aggregate_id: str
    aggregate_type: str
    snapshot_seq: int
    state: Any
    snapshot_hash: bytes


async def maybe_take_snapshot(
    aggregate_id: str,
    aggregate_type: str,
    current_seq: int,
    state: Any,
    event_store: "EventStore",
    tenant_id: str,
    *,
    interval: int = SNAPSHOT_INTERVAL,
) -> None:
    """
    Create a snapshot if current_seq is a multiple of the interval.
    Called after each event is applied during reconstruction.
    """
    if current_seq % interval == 0:
        state_bytes = json.dumps(state, default=str, sort_keys=True).encode()
        snapshot_hash = hashlib.sha256(state_bytes).digest()
        await event_store.save_snapshot(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            snapshot_seq=current_seq,
            state=state,
            snapshot_hash=snapshot_hash,
            tenant_id=tenant_id,
        )


async def load_snapshot(
    aggregate_id: str,
    at_or_before_seq: int,
    event_store: "EventStore",
    tenant_id: str,
) -> Snapshot | None:
    """
    Load the most recent snapshot at or before at_or_before_seq.
    Validates the snapshot hash before returning — fail-closed on corruption.
    """
    with tracer.start_as_current_span("quaicu.snapshot.load") as span:
        span.set_attribute("quaicu.aggregate_id", str(aggregate_id))
        span.set_attribute("quaicu.target_seq", at_or_before_seq)

        row = await event_store.get_latest_snapshot(
            aggregate_id=aggregate_id,
            at_or_before_seq=at_or_before_seq,
            tenant_id=tenant_id,
        )
        if row is None:
            return None

        # Verify integrity
        state_bytes = json.dumps(row.state, default=str, sort_keys=True).encode()
        computed_hash = hashlib.sha256(state_bytes).digest()
        if computed_hash != row.snapshot_hash:
            raise SnapshotCorruptError(
                code=ReplayErrorCode.SNAPSHOT_CORRUPT,
                message=(
                    f"Snapshot for aggregate {aggregate_id!r} at seq {row.snapshot_seq} "
                    "has a hash mismatch — snapshot may have been modified."
                ),
                aggregate_id=str(aggregate_id),
                sequence=row.snapshot_seq,
            )

        span.set_attribute("quaicu.snapshot.found_at_seq", row.snapshot_seq)
        return row
```

---

## Replay Cursor — Streaming for Large Ledgers

Never load all events into memory. Use a streaming cursor that fetches events in pages.
This is critical for large tenants with thousands of ledger entries.

```python
# core/replay/cursor.py
from __future__ import annotations
from typing import AsyncIterator, Any
from dataclasses import dataclass
from opentelemetry import trace, metrics

tracer = trace.get_tracer("quaicu.replay_cursor")
meter  = metrics.get_meter("quaicu.replay_cursor")

_events_streamed = meter.create_counter(
    "quaicu.replay.events_streamed_total",
    description="Total events streamed through replay cursors",
)


@dataclass
class ReplayCursor:
    """
    Stateful cursor over an event stream for a given aggregate (or all aggregates).
    Yields events in global_seq order. Fetches PAGE_SIZE events per DB round-trip.
    The caller applies each event and optionally snapshots — state is never accumulated
    in the cursor itself.
    """
    aggregate_id: str | None   # None = all aggregates for the tenant (full reconstruction)
    tenant_id: str
    from_seq: int              # start from this global_seq (exclusive)
    to_seq: int | None         # None = open-ended (read to current)

    PAGE_SIZE: int = 500

    async def stream(
        self, event_store: "EventStore"
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yield events one at a time. Each event is fetched in pages from the DB.
        Memory usage is O(PAGE_SIZE), not O(total events).
        """
        last_seen_seq = self.from_seq

        with tracer.start_as_current_span("quaicu.replay_cursor.stream") as span:
            span.set_attribute("quaicu.tenant_id", self.tenant_id)
            if self.aggregate_id:
                span.set_attribute("quaicu.aggregate_id", str(self.aggregate_id))
            span.set_attribute("quaicu.cursor.from_seq", self.from_seq)

            while True:
                page = await event_store.fetch_events_page(
                    tenant_id=self.tenant_id,
                    aggregate_id=self.aggregate_id,
                    after_global_seq=last_seen_seq,
                    to_global_seq=self.to_seq,
                    page_size=self.PAGE_SIZE,
                )
                if not page:
                    break  # no more events

                for event in page:
                    _events_streamed.add(1, {"tenant_id": self.tenant_id})
                    last_seen_seq = event["global_seq"]
                    yield event

                if len(page) < self.PAGE_SIZE:
                    break  # last page
```

---

## State Reconstruction (Mode 1) — Snapshot + Delta, Streaming

```python
# core/replay/reconstruction.py
from __future__ import annotations
from typing import Any
from opentelemetry import trace, metrics

from core.replay.snapshot import load_snapshot, maybe_take_snapshot, SNAPSHOT_INTERVAL
from core.replay.cursor import ReplayCursor
from core.errors.replay import ReplayError, ReplayErrorCode

tracer = trace.get_tracer("quaicu.reconstruction")
meter  = metrics.get_meter("quaicu.reconstruction")

_reconstruction_latency = meter.create_histogram(
    "quaicu.replay.reconstruction_latency_ms",
    description="Time to reconstruct aggregate state",
    unit="ms",
)


async def reconstruct_state_at(
    aggregate_id: str,
    target_seq: int,
    tenant_id: str,
    event_store: "EventStore",
    apply_fn: "Callable[[Any, dict], Any]",
    initial_state: Any = None,
) -> Any:
    """
    Rebuilds aggregate state at target_seq using snapshot + delta streaming.

    Algorithm:
      1. Load the most recent snapshot at or before target_seq (O(1) DB read).
      2. Stream remaining events from snapshot_seq + 1 to target_seq via cursor.
      3. Apply each event using apply_fn (a pure function — no I/O, no side effects).
      4. Opportunistically take new snapshots as multiples of SNAPSHOT_INTERVAL are crossed.

    Idempotency: calling this twice with the same inputs produces the same result.
    No external calls are made — all inputs come from the ledger.
    """
    import time
    t0 = time.monotonic()

    with tracer.start_as_current_span("quaicu.reconstruct_state") as span:
        span.set_attribute("quaicu.aggregate_id", str(aggregate_id))
        span.set_attribute("quaicu.target_seq", target_seq)
        span.set_attribute("quaicu.tenant_id", tenant_id)

        # Step 1 — Load snapshot
        snapshot = await load_snapshot(aggregate_id, target_seq, event_store, tenant_id)
        if snapshot:
            state = snapshot.state
            from_seq = snapshot.snapshot_seq
            span.set_attribute("quaicu.snapshot.start_seq", from_seq)
        else:
            state = initial_state
            from_seq = 0

        # Step 2 — Stream remaining events
        cursor = ReplayCursor(
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            from_seq=from_seq,
            to_seq=target_seq,
        )
        events_applied = 0
        async for event in cursor.stream(event_store):
            state = apply_fn(state, event)
            events_applied += 1
            # Opportunistic snapshot
            await maybe_take_snapshot(
                aggregate_id=aggregate_id,
                aggregate_type=event["aggregate_type"],
                current_seq=event["sequence"],
                state=state,
                event_store=event_store,
                tenant_id=tenant_id,
            )

        elapsed_ms = (time.monotonic() - t0) * 1000
        _reconstruction_latency.record(elapsed_ms, {"tenant_id": tenant_id})
        span.set_attribute("quaicu.reconstruction.events_applied", events_applied)

        return state


async def verify_reconstruction_idempotency(
    aggregate_id: str,
    target_seq: int,
    tenant_id: str,
    event_store: "EventStore",
    apply_fn,
    initial_state,
    state_eq_fn=None,
) -> bool:
    """
    Run reconstruct_state_at twice with the same inputs and assert the results are equal.
    This verifies the idempotency invariant:
      reconstruct_state_at(x) == reconstruct_state_at(x) for any x.
    Used in conformance tests and in the DoD checklist for K·02.
    """
    result_1 = await reconstruct_state_at(
        aggregate_id, target_seq, tenant_id, event_store, apply_fn, initial_state
    )
    result_2 = await reconstruct_state_at(
        aggregate_id, target_seq, tenant_id, event_store, apply_fn, initial_state
    )
    eq = state_eq_fn or (lambda a, b: a == b)
    if not eq(result_1, result_2):
        raise ReplayError(
            code=ReplayErrorCode.RECONSTRUCTION_MISMATCH,
            message=(
                f"Idempotency violated: reconstruct_state_at({aggregate_id}, {target_seq}) "
                "returned different results on two calls with identical inputs."
            ),
            aggregate_id=str(aggregate_id),
            sequence=target_seq,
        )
    return True
```

---

## Decision Audit Replay (Mode 2) — Point-in-Time Correct

```python
# core/replay/audit_replay.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace

from core.errors.replay import ReplayError, ReplayErrorCode

tracer = trace.get_tracer("quaicu.audit_replay")


@dataclass
class ReplayResult:
    action_id: str
    original_decision: str
    replayed_decision: str
    matches: bool
    policy_versions_used: list[str]
    explanation: Any


async def replay_decision(
    action_id: str,
    tenant_id: str,
    event_store: "EventStore",
    policy_store: "PolicyStore",
    policy_engine: "PolicyEngine",
) -> ReplayResult:
    """
    Re-derives the decision for a past action using EXACTLY the policy versions,
    recorded model outputs, consent state, and assurance signals that were in effect
    at the time of the original decision.

    Point-in-time correct: uses policy_versions from the sealed event, NOT current policies.
    Uses recorded_nondeterminism from the event, NOT live model calls.

    Calling this twice for the same action_id must produce the same result (idempotency).
    """
    with tracer.start_as_current_span("quaicu.audit_replay") as span:
        span.set_attribute("quaicu.action_id", str(action_id))
        span.set_attribute("quaicu.tenant_id", tenant_id)

        # Load the sealed event for this action
        events = await event_store.get_events_for_aggregate(
            aggregate_id=action_id,
            tenant_id=tenant_id,
        )
        decision_event = next(
            (e for e in events if e["event_type"] == "policy.evaluated"), None
        )
        if decision_event is None:
            raise ReplayError(
                code=ReplayErrorCode.MISSING_AGGREGATE_SEQUENCE,
                message=f"No policy.evaluated event found for action {action_id!r}",
                aggregate_id=str(action_id),
            )

        # Retrieve EXACT policy versions — never current versions
        policy_versions = decision_event.get("policy_versions", {})
        if not policy_versions:
            raise ReplayError(
                code=ReplayErrorCode.MISSING_RECORDED_NONDETERMINISM,
                message=(
                    f"Event for action {action_id!r} has no policy_versions recorded. "
                    "Cannot perform audit replay — the event was not captured completely."
                ),
                aggregate_id=str(action_id),
            )

        policies_at_time = await policy_store.get_versions(policy_versions)
        if len(policies_at_time) != len(policy_versions):
            missing = set(policy_versions.keys()) - {p.id for p in policies_at_time}
            raise ReplayError(
                code=ReplayErrorCode.POLICY_VERSION_NOT_FOUND,
                message=f"Policy versions missing from store: {missing}",
                aggregate_id=str(action_id),
            )

        # Reconstruct the action
        payload = decision_event["payload"]
        from core.domain.action import Action
        action = Action(
            action_id=action_id,
            action_type=payload["action_type"],
            payload=payload["action_payload"],
            actor_id=payload["actor_id"],
            tenant_id=tenant_id,
        )

        # Re-evaluate — deterministic (CEL) with recorded non-determinism
        # recorded_nondeterminism is provided so the engine never calls live models
        replayed_eval = await policy_engine.evaluate(
            action=action,
            policies=policies_at_time,
            consent_state=decision_event.get("consent_state"),
            assurance_signals=decision_event.get("assurance_signals"),
            recorded_nondeterminism=decision_event.get("recorded_nondeterminism", {}),
        )

        original = payload.get("evaluation_decision")
        result = ReplayResult(
            action_id=str(action_id),
            original_decision=original,
            replayed_decision=replayed_eval.decision,
            matches=replayed_eval.decision == original,
            policy_versions_used=list(policy_versions.keys()),
            explanation=replayed_eval,
        )

        span.set_attribute("quaicu.replay.original_decision", original)
        span.set_attribute("quaicu.replay.replayed_decision", replayed_eval.decision)
        span.set_attribute("quaicu.replay.matches", result.matches)

        return result
```

---

## Counterfactual Replay (Mode 3) — Conflict Detection + Shadow Only

```python
# core/replay/counterfactual.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opentelemetry import trace, metrics

from core.replay.cursor import ReplayCursor
from core.errors.replay import (
    PolicyConflictError, CounterfactualProductionWriteError,
    ReplayErrorCode,
)

tracer = trace.get_tracer("quaicu.counterfactual")
meter  = metrics.get_meter("quaicu.counterfactual")

_counterfactual_counter = meter.create_counter(
    "quaicu.counterfactual.runs_total",
    description="Total counterfactual replay runs",
)


@dataclass
class FlippedAction:
    action_id: str
    original_decision: str
    candidate_decision: str
    conflict_with: str | None = None    # set if two candidates disagree


@dataclass
class ImpactReport:
    policy_ids: list[str]
    time_range: tuple[datetime, datetime]
    total_actions_tested: int
    flip_count: int
    flip_pct: float
    flipped_actions: list[FlippedAction] = field(default_factory=list)
    conflict_count: int = 0
    fairness_delta: dict[str, Any] = field(default_factory=dict)
    shadow_partition_ref: str | None = None


async def counterfactual_replay(
    tenant_id: str,
    candidate_policies: list[Any],
    time_range: tuple[datetime, datetime],
    event_store: "EventStore",
    policy_engine: "PolicyEngine",
    shadow_store: "ShadowStore",
    *,
    action_type_filter: str | None = None,
    max_sample: int = 10_000,
) -> ImpactReport:
    """
    Runs candidate_policies against historical actions via streaming cursor.

    SIDE-EFFECT-FREE contract:
    - No production ledger writes (raises CounterfactualProductionWriteError if attempted).
    - No live model calls (recorded_nondeterminism from events used exclusively).
    - Results written to shadow_store only, never production event_store.
    - Running this function has no observable effect on production state.

    Conflict detection:
    - If multiple candidate policies evaluate the same action and disagree,
      the FlippedAction.conflict_with field is set and conflict_count incremented.
    - A PolicyConflictError is raised only if detect_conflicts=True AND all candidates
      must agree (strict mode). Default: conflicts are recorded but not raised.
    """
    with tracer.start_as_current_span("quaicu.counterfactual") as span:
        span.set_attribute("quaicu.tenant_id", tenant_id)
        span.set_attribute("quaicu.candidate_policy_count", len(candidate_policies))

        # Validate: no production store reference passed as shadow_store
        if hasattr(shadow_store, "_is_production") and shadow_store._is_production:
            raise CounterfactualProductionWriteError(
                code=ReplayErrorCode.COUNTERFACTUAL_WROTE_PRODUCTION,
                message="Counterfactual replay received a production store — safety check failed.",
            )

        total = 0
        flipped: list[FlippedAction] = []
        conflict_count = 0

        # Stream events instead of loading all into memory
        from_global_seq = await event_store.global_seq_at_time(
            tenant_id, time_range[0]
        )
        to_global_seq = await event_store.global_seq_at_time(
            tenant_id, time_range[1]
        )

        cursor = ReplayCursor(
            aggregate_id=None,   # all aggregates
            tenant_id=tenant_id,
            from_seq=from_global_seq,
            to_seq=to_global_seq,
        )

        async for event in cursor.stream(event_store):
            if event["event_type"] != "policy.evaluated":
                continue
            if action_type_filter and event["payload"].get("action_type") != action_type_filter:
                continue
            if total >= max_sample:
                break

            total += 1
            payload = event["payload"]
            from core.domain.action import Action
            action = Action(
                action_id=event["aggregate_id"],
                action_type=payload["action_type"],
                payload=payload["action_payload"],
                actor_id=payload["actor_id"],
                tenant_id=tenant_id,
            )
            original = payload.get("evaluation_decision")

            # Evaluate each candidate policy independently — using recorded nondeterminism
            candidate_decisions: list[tuple[str, str]] = []
            for cp in candidate_policies:
                eval_result = await policy_engine.evaluate(
                    action=action,
                    policies=[cp],
                    recorded_nondeterminism=event.get("recorded_nondeterminism", {}),
                )
                candidate_decisions.append((cp.id, eval_result.decision))

            # Conflict detection: do multiple candidates disagree?
            unique_decisions = {d for _, d in candidate_decisions}
            conflict_str = None
            if len(unique_decisions) > 1:
                conflict_count += 1
                conflict_str = " vs ".join(
                    f"{pid}={dec}" for pid, dec in candidate_decisions
                )

            # Use the first candidate's decision as the "candidate" result
            _, primary_candidate_decision = candidate_decisions[0]

            if primary_candidate_decision != original:
                flipped.append(FlippedAction(
                    action_id=str(event["aggregate_id"]),
                    original_decision=original,
                    candidate_decision=primary_candidate_decision,
                    conflict_with=conflict_str,
                ))

        _counterfactual_counter.add(1, {"tenant_id": tenant_id})

        report = ImpactReport(
            policy_ids=[cp.id for cp in candidate_policies],
            time_range=time_range,
            total_actions_tested=total,
            flip_count=len(flipped),
            flip_pct=len(flipped) / max(total, 1),
            flipped_actions=flipped[:500],   # sample — not all
            conflict_count=conflict_count,
        )

        # Write to SHADOW partition only — production event_store is never touched
        ref = await shadow_store.save_impact_report(report, tenant_id=tenant_id)
        report.shadow_partition_ref = ref

        span.set_attribute("quaicu.counterfactual.total_tested", total)
        span.set_attribute("quaicu.counterfactual.flip_count", len(flipped))
        span.set_attribute("quaicu.counterfactual.conflict_count", conflict_count)

        return report
```

---

## Projection Rebuild Worker (Background Job)

Materialised projections go stale when events accumulate. The rebuild worker replays
events for all aggregates and refreshes materialised views. It runs as an async
background job (ARQ) without interfering with the live path.

```python
# core/replay/projection_worker.py
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from opentelemetry import trace, metrics

from core.replay.reconstruction import reconstruct_state_at
from core.replay.cursor import ReplayCursor

tracer = trace.get_tracer("quaicu.projection_worker")
meter  = metrics.get_meter("quaicu.projection_worker")

_projections_rebuilt = meter.create_counter(
    "quaicu.projections.rebuilt_total",
    description="Total projection rebuilds completed",
)
_rebuild_latency = meter.create_histogram(
    "quaicu.projections.rebuild_latency_ms",
    description="Time to rebuild a projection",
    unit="ms",
)


async def rebuild_projection(
    projection_name: str,
    tenant_id: str,
    event_store: "EventStore",
    projection_store: "ProjectionStore",
    apply_fn: Callable[[Any, dict], Any],
    initial_state: Any,
    *,
    aggregate_type: str | None = None,
) -> None:
    """
    Rebuild a materialised projection from scratch by streaming all events.
    This is a background job — it does not block the live path.
    It writes only to projection_store, never to event_store (read-only on events).

    Called:
    - On deployment when a new projection is added.
    - When a projection is found to be corrupted or out-of-date.
    - On demand via the admin API.
    """
    import time
    t0 = time.monotonic()

    with tracer.start_as_current_span("quaicu.rebuild_projection") as span:
        span.set_attribute("quaicu.projection_name", projection_name)
        span.set_attribute("quaicu.tenant_id", tenant_id)

        # Get the list of all distinct aggregate_ids for this type
        agg_ids = await event_store.list_aggregate_ids(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
        )
        span.set_attribute("quaicu.rebuild.aggregate_count", len(agg_ids))

        # Rebuild state for each aggregate
        projection_state: dict[str, Any] = {}
        for agg_id in agg_ids:
            # Stream to the current tip
            latest_seq = await event_store.get_latest_sequence(agg_id, tenant_id)
            if latest_seq is None:
                continue

            state = await reconstruct_state_at(
                aggregate_id=agg_id,
                target_seq=latest_seq,
                tenant_id=tenant_id,
                event_store=event_store,
                apply_fn=apply_fn,
                initial_state=initial_state,
            )
            projection_state[str(agg_id)] = state

        # Atomically write the rebuilt projection
        await projection_store.upsert_projection(
            name=projection_name,
            tenant_id=tenant_id,
            state=projection_state,
            rebuilt_at=datetime.now(timezone.utc),
        )

        elapsed_ms = (time.monotonic() - t0) * 1000
        _projections_rebuilt.add(1, {"projection": projection_name})
        _rebuild_latency.record(elapsed_ms, {"projection": projection_name})
```

---

## Point-in-Time Evidence Pack (K·14) — Signed Bundle

The evidence pack for K·14 is a cryptographically signed bundle containing:
ledger proofs + policy versions at the time + human-readable document.
This is what an auditor or regulator receives.

```python
# core/replay/evidence_pack.py
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

from core.errors.replay import EvidencePackVerificationError, ReplayErrorCode

tracer = trace.get_tracer("quaicu.evidence_pack")


@dataclass
class LedgerProofRef:
    """RFC 6962 inclusion proof reference for one ledger entry."""
    action_id: str
    global_seq: int
    leaf_hash: str              # hex-encoded
    inclusion_proof: list[str]  # hex-encoded audit path nodes
    tree_head_hash: str         # hex-encoded root at the time of sealing
    tree_size: int


@dataclass
class EvidencePack:
    """
    K·14 Point-in-Time Evidence Pack.
    Signed bundle: ledger proofs + policy versions + human-readable document.
    The bundle_hash covers all machine-readable fields and is signed by the kernel's
    signing key (held in OpenBao).
    """
    pack_id: str
    tenant_id: str
    requirement_id: str             # e.g. "rbi.free_ai.sutra.3"
    time_period: tuple[datetime, datetime]
    kernel_version: str
    generated_at: datetime

    # Machine-readable manifest
    policies_active: list[dict[str, Any]] = field(default_factory=list)  # {id, version, text}
    ledger_proofs: list[LedgerProofRef] = field(default_factory=list)
    action_summary: list[dict[str, Any]] = field(default_factory=list)

    # Human-readable document (Markdown)
    narrative_md: str = ""

    # Integrity
    manifest_hash: str = ""         # SHA-256 of the machine-readable portion
    signature: str = ""             # base64-encoded signature over manifest_hash


async def generate_evidence_pack(
    requirement_id: str,
    time_period: tuple[datetime, datetime],
    tenant_id: str,
    event_store: "EventStore",
    policy_store: "PolicyStore",
    ledger: "TrustLedger",
    signer: "EvidenceSigner",
    kernel_version: str,
) -> EvidencePack:
    """
    Generate a signed evidence pack for a regulation requirement over a time period.

    Process (per §3.11):
    1. Resolve the policies mapped to the requirement that were ACTIVE during the period.
    2. Find governed actions those policy-versions evaluated within the period.
    3. Collect the corresponding ledger entries and their RFC 6962 inclusion proofs.
    4. Emit a signed evidence pack.

    This is point-in-time correct — evidence reflects rules and policies as they stood
    then, not now.
    """
    with tracer.start_as_current_span("quaicu.evidence_pack.generate") as span:
        span.set_attribute("quaicu.tenant_id", tenant_id)
        span.set_attribute("quaicu.requirement_id", requirement_id)

        import uuid
        pack_id = str(uuid.uuid4())

        # Step 1 — Resolve active policies for the requirement in the time window
        active_policies = await policy_store.get_policies_for_requirement(
            requirement_id=requirement_id,
            active_during=time_period,
            tenant_id=tenant_id,
        )
        if not active_policies:
            # Still generate the pack — but with empty policies. Honest absence of evidence.
            pass

        # Step 2 — Find actions governed by these policies in the time window
        policy_ids = [p["id"] for p in active_policies]
        actions = await event_store.get_actions_governed_by(
            policy_ids=policy_ids,
            time_range=time_period,
            tenant_id=tenant_id,
        )

        # Step 3 — Collect ledger inclusion proofs for each action
        proofs: list[LedgerProofRef] = []
        for action in actions:
            proof = await ledger.get_inclusion_proof(
                action_id=action["action_id"],
                tenant_id=tenant_id,
            )
            if proof:
                proofs.append(proof)

        # Step 4 — Build manifest and sign
        pack = EvidencePack(
            pack_id=pack_id,
            tenant_id=tenant_id,
            requirement_id=requirement_id,
            time_period=time_period,
            kernel_version=kernel_version,
            generated_at=datetime.now(timezone.utc),
            policies_active=active_policies,
            ledger_proofs=proofs,
            action_summary=[
                {
                    "action_id": a["action_id"],
                    "action_type": a["action_type"],
                    "decision": a["evaluation_decision"],
                    "occurred_at": a["occurred_at"].isoformat(),
                }
                for a in actions
            ],
            narrative_md=_render_narrative(
                requirement_id, time_period, active_policies, actions
            ),
        )

        # Compute manifest hash over all machine-readable fields
        manifest = {
            "pack_id": pack.pack_id,
            "tenant_id": pack.tenant_id,
            "requirement_id": pack.requirement_id,
            "time_period": [t.isoformat() for t in pack.time_period],
            "kernel_version": pack.kernel_version,
            "generated_at": pack.generated_at.isoformat(),
            "policies_active": pack.policies_active,
            "ledger_proofs": [
                {
                    "action_id": p.action_id,
                    "global_seq": p.global_seq,
                    "leaf_hash": p.leaf_hash,
                    "inclusion_proof": p.inclusion_proof,
                    "tree_head_hash": p.tree_head_hash,
                    "tree_size": p.tree_size,
                }
                for p in pack.ledger_proofs
            ],
            "action_summary": pack.action_summary,
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, default=str).encode()
        pack.manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        pack.signature = await signer.sign(pack.manifest_hash)

        span.set_attribute("quaicu.evidence_pack.pack_id", pack_id)
        span.set_attribute("quaicu.evidence_pack.action_count", len(actions))
        span.set_attribute("quaicu.evidence_pack.proof_count", len(proofs))

        return pack


async def verify_evidence_pack(pack: EvidencePack, verifier: "EvidenceVerifier") -> bool:
    """
    Verify the signature and hash of a previously generated evidence pack.
    Called by an auditor or regulator receiving the pack.
    Raises EvidencePackVerificationError if verification fails.
    """
    manifest = {
        "pack_id": pack.pack_id,
        "tenant_id": pack.tenant_id,
        "requirement_id": pack.requirement_id,
        "time_period": [t.isoformat() for t in pack.time_period],
        "kernel_version": pack.kernel_version,
        "generated_at": pack.generated_at.isoformat(),
        "policies_active": pack.policies_active,
        "ledger_proofs": [
            {
                "action_id": p.action_id,
                "global_seq": p.global_seq,
                "leaf_hash": p.leaf_hash,
                "inclusion_proof": p.inclusion_proof,
                "tree_head_hash": p.tree_head_hash,
                "tree_size": p.tree_size,
            }
            for p in pack.ledger_proofs
        ],
        "action_summary": pack.action_summary,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, default=str).encode()
    computed_hash = hashlib.sha256(manifest_bytes).hexdigest()

    if computed_hash != pack.manifest_hash:
        raise EvidencePackVerificationError(
            code=ReplayErrorCode.EVIDENCE_PACK_VERIFY_FAILED,
            message=(
                f"Evidence pack {pack.pack_id!r} hash mismatch: "
                f"computed={computed_hash!r}, stored={pack.manifest_hash!r}. "
                "Pack may have been modified."
            ),
        )

    if not await verifier.verify(pack.manifest_hash, pack.signature):
        raise EvidencePackVerificationError(
            code=ReplayErrorCode.EVIDENCE_PACK_VERIFY_FAILED,
            message=f"Evidence pack {pack.pack_id!r} signature verification failed.",
        )

    return True


def _render_narrative(requirement_id, time_period, policies, actions) -> str:
    """Render a human-readable Markdown document for the evidence pack."""
    start, end = time_period
    return (
        f"# Evidence Pack — {requirement_id}\n\n"
        f"**Period:** {start.date()} to {end.date()}\n\n"
        f"**Policies active during period:** {len(policies)}\n\n"
        f"**Governed actions in period:** {len(actions)}\n\n"
        "## Policy Versions\n\n"
        + "\n".join(f"- `{p['id']}` v{p['version']}" for p in policies)
        + "\n\n## Decision Summary\n\n"
        + "\n".join(
            f"- Action `{a['action_id']}` ({a['action_type']}): {a['evaluation_decision']}"
            for a in actions[:50]
        )
    )
```

---

## Ledger Entry — Must Capture Enough to Reconstruct

```python
# core/domain/ledger_entry.py
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LedgerEntry:
    """
    A sealed ledger entry. Must contain everything needed to:
    1. Reconstruct the decision (audit replay, Mode 2).
    2. Rebuild institutional state (state reconstruction, Mode 1).
    3. Run counterfactual without live calls (Mode 3).
    4. Generate evidence packs (K·14).

    An entry that records only "approved by policy X" is NOT replayable.
    """
    # Identity
    action_id: uuid.UUID
    tenant_id: str
    global_seq: int          # ledger global sequence
    aggregate_id: uuid.UUID  # same as action_id for action events
    aggregate_type: str      # "action"
    sequence: int            # per-aggregate sequence

    # Full action — to replay the input exactly
    action_type: str
    action_payload: dict     # complete payload
    actor_id: str

    # Evaluation context — to replay the decision point-in-time
    policy_versions: dict[str, int]    # {policy_id: version_number}
    consent_state: dict[str, Any]      # K·04 state at evaluation time
    assurance_signals: dict[str, Any]  # K·08–K·11 results at evaluation time

    # Non-deterministic results — to replay without recomputing
    recorded_model_outputs: dict[str, Any]    # {call_id: {prompt_hash, response_hash, content}}
    recorded_external_lookups: dict[str, Any] # {lookup_key: result}

    # Outcome
    evaluation_decision: str           # "allow" | "deny" | "require_approval"
    hitl_decision: str | None          # "approved" | "rejected" | None
    execution_result: Any

    # Integrity (RFC 6962)
    event_hash: bytes
    prev_hash: bytes | None
    leaf_hash: bytes
    inclusion_proof: list[bytes] = field(default_factory=list)
    tree_head_hash: bytes | None = None
```

---

## OTel Instrumentation Reference

| Span name | Required attributes |
|-----------|----------------------|
| `quaicu.reconstruct_state` | `quaicu.aggregate_id`, `quaicu.target_seq`, `quaicu.tenant_id` |
| `quaicu.snapshot.load` | `quaicu.aggregate_id`, `quaicu.target_seq`, `quaicu.snapshot.found_at_seq` |
| `quaicu.replay_cursor.stream` | `quaicu.tenant_id`, `quaicu.cursor.from_seq` |
| `quaicu.audit_replay` | `quaicu.action_id`, `quaicu.tenant_id`, `quaicu.replay.matches` |
| `quaicu.counterfactual` | `quaicu.tenant_id`, `quaicu.counterfactual.flip_count`, `quaicu.counterfactual.conflict_count` |
| `quaicu.evidence_pack.generate` | `quaicu.tenant_id`, `quaicu.requirement_id`, `quaicu.evidence_pack.action_count` |
| `quaicu.record_activity` | `quaicu.aggregate_id`, `quaicu.activity_name`, `quaicu.replay_mode`, `quaicu.activity_source` |
| `quaicu.rebuild_projection` | `quaicu.projection_name`, `quaicu.tenant_id`, `quaicu.rebuild.aggregate_count` |

---

## Anti-Patterns — Never Do These

```python
# ╳ ANTI-PATTERN 1 — recomputing model output on replay
async def replay_action(event):
    response = await inference_port.generate(prompt=event["payload"]["prompt"])  # WRONG
    # Must use: event["recorded_nondeterminism"]["model_output"]

# ╳ ANTI-PATTERN 2 — loading all events into memory
events = await event_store.get_all_events(tenant_id)   # WRONG for large tenants
for e in events: ...   # use ReplayCursor.stream() instead

# ╳ ANTI-PATTERN 3 — writing to production ledger during counterfactual
async def counterfactual_replay(..., event_store):
    await event_store.append_event(shadow_result)   # WRONG — production store
    # Must: await shadow_store.save_impact_report(...)

# ╳ ANTI-PATTERN 4 — using current policy version for audit replay
current_policy = await policy_store.get_current(policy_id)   # WRONG
# Must: await policy_store.get_versions(entry.policy_versions)  # exact historical version

# ╳ ANTI-PATTERN 5 — not recording activity before returning
result = await external_api.call(...)
return result   # WRONG — not recorded, so replay will call live
# Must: return await activity_recorder.record_activity(agg_id, "api_call", lambda: external_api.call(...))

# ╳ ANTI-PATTERN 6 — state as primary record (not projections)
await db.execute("UPDATE current_state SET value = $1 WHERE id = $2", val, id)
# State is a projection of events — the events table is the source of truth

# ╳ ANTI-PATTERN 7 — not verifying idempotency in tests
# reconstruct_state_at must produce the same result on every call for the same inputs
# Always run verify_reconstruction_idempotency in conformance tests
```

---

## Side-Effect-Free Replay Tests (required per §6 DoD)

```python
# tests/conformance/test_replay_side_effects.py
import pytest


async def test_state_reconstruction_causes_no_side_effects(
    event_store, effect_tracker, tenant_id
):
    """
    Replaying a loan reclassification must not re-disburse.
    Replaying a notification must not re-send.
    """
    await seed_event(event_store, action_type="loan.disburse", tenant_id=tenant_id)

    await reconstruct_state_at(
        aggregate_id=seeded_agg_id,
        target_seq=1,
        tenant_id=tenant_id,
        event_store=event_store,
        apply_fn=loan_apply_fn,
        initial_state={},
    )

    assert effect_tracker.disbursements == [], (
        "State reconstruction triggered a disbursement — replay side-effect bug"
    )
    assert effect_tracker.notifications == []


async def test_counterfactual_does_not_write_production_ledger(event_store, tenant_id):
    """Counterfactual must write only to shadow_store, never production event_store."""
    count_before = await event_store.count_events(tenant_id)
    await counterfactual_replay(
        tenant_id=tenant_id,
        candidate_policies=[candidate],
        time_range=(start, end),
        event_store=event_store,
        policy_engine=policy_engine,
        shadow_store=in_memory_shadow_store,
    )
    count_after = await event_store.count_events(tenant_id)
    assert count_before == count_after, (
        "Counterfactual replay wrote to the production event store — critical bug"
    )


async def test_reconstruct_state_at_is_idempotent(event_store, tenant_id):
    """Running reconstruct_state_at twice with the same arguments produces identical state."""
    await verify_reconstruction_idempotency(
        aggregate_id=test_agg_id,
        target_seq=5,
        tenant_id=tenant_id,
        event_store=event_store,
        apply_fn=apply_fn,
        initial_state={},
    )


async def test_audit_replay_uses_historical_policy_versions(
    event_store, policy_store, policy_engine, tenant_id
):
    """Audit replay must use policy versions from the event, not current active policies."""
    # Seed an event with a specific policy version
    old_policy = await seed_policy_version(policy_store, version=1, decision="deny")
    await seed_evaluated_event(
        event_store, policy_versions={old_policy.id: 1}, decision="deny",
        tenant_id=tenant_id
    )
    # Update the policy to allow — audit replay must still return deny
    await update_policy_version(policy_store, old_policy.id, version=2, decision="allow")

    result = await replay_decision(
        action_id=seeded_action_id,
        tenant_id=tenant_id,
        event_store=event_store,
        policy_store=policy_store,
        policy_engine=policy_engine,
    )
    assert result.replayed_decision == "deny", (
        "Audit replay used current policy version instead of historical version"
    )
    assert result.matches is True
```

---

## Checklist Before Merging Anything That Touches State

- [ ] Non-deterministic results (model calls, external lookups, random) recorded via `ActivityRecorder`
- [ ] Replay paths return recorded results — no live `inference_port.generate()` during replay
- [ ] `ReplayCursor` used for large ledgers — no `get_all_events()` calls
- [ ] State reconstruction reads event store only — no live external service calls
- [ ] Counterfactual replay writes to shadow_store only — production event_store not touched
- [ ] `LedgerEntry` records `policy_versions` (exact version map), `recorded_model_outputs`, `recorded_external_lookups`, full `action_payload`
- [ ] Decision audit replay uses `entry.policy_versions` — NOT current active policies
- [ ] `verify_reconstruction_idempotency` passes for all aggregates in conformance suite
- [ ] `generate_evidence_pack` output passes `verify_evidence_pack` independently
- [ ] Projection rebuild worker writes only to `projection_store`, not `event_store`
- [ ] Snapshot hash validated on load — `SnapshotCorruptError` raised on mismatch
- [ ] OTel span emitted for every replay path (see instrumentation table above)
- [ ] Side-effect-free tests pass: disbursement action does not re-disburse on replay
