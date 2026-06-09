---
name: quaicu-event-bus
description: |
  QUAICU K·07 Event Bus — structured event emission after seal. Use when building core/events/, the
  event bus port/adapter, or any consumer of governed-action events. Enforces: emit happens ONLY after
  a successful K·02 seal; emit is best-effort and NEVER alters or rolls back a sealed outcome; every
  event carries tenant + action id + ledger_seq; at-least-once delivery with idempotent consumers
  (dedupe by event id). Trigger keywords: event, emit, K·07, event_bus, EventPort, action.completed,
  at_least_once, idempotent, outbox, dedupe, publish, subscribe, tenant, ledger_seq, after seal,
  best_effort.
---

# QUAICU K·07 Event Bus

You own `emit` — the final step of the lifecycle loop. Events announce what already happened; they
never change it. A failed emit must be invisible to the sealed outcome.

> Status: **scaffold.** The Deterministic Decision Contract is authoritative; flesh out the adapter
> (outbox table, broker) against spec §6 (K·07 DoD) and §10 worked example before shipping.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> **If this block conflicts with prose below, this block wins.** Missing rule → do the safe thing
> (never let emit affect seal) and stop.

### Invariants — never violated
- ALWAYS emit **only after** a successful seal (K·02). No seal → no event, ever.
- ALWAYS treat emit as **best-effort**: a failed/slow emit NEVER halts, rolls back, or mutates the sealed action.
- ALWAYS include `tenant`, `action_id`, `ledger_seq`, `event_id`, `type`, `occurred_at` on every event.
- ALWAYS deliver **at-least-once**; consumers MUST be idempotent (dedupe on `event_id`).
- NEVER put side-effecting business logic in the emit path; events are notifications, not execution.
- NEVER let an event cross a tenant boundary.

### Decision table
| Situation | Do exactly this |
|---|---|
| seal succeeded | emit the event (via outbox); state → COMPLETED regardless of emit result |
| seal failed | action HALTED; **no event** |
| emit fails / broker down | log + retry from the outbox; do NOT change the action's state or outcome |
| duplicate delivery | consumer dedupes by `event_id`; producing a duplicate is acceptable, losing one is not |

### Tie-break rules
- Choose **at-least-once over exactly-once**: prefer a possible duplicate (consumer dedupes) to a possible loss.
- Unsure whether to block the action on a failed emit? → NEVER block; emit is downstream of the sealed truth.
- Need transactional guarantee between seal and emit? → use the **transactional outbox** (write the event row in the same tx as the seal), not a direct broker publish.

### Stop-and-apply triggers
- About to `publish()` before `seal()` returns success? → STOP, reorder; emit is strictly post-seal.
- About to raise/rollback because emit failed? → STOP, swallow + retry from outbox.
- About to emit without `ledger_seq`/`tenant`? → STOP, an event that can't be traced to the ledger is malformed.

### Self-check
- [ ] Emit path runs only on seal success; HALT/DENY paths emit nothing.
- [ ] Emit failures never alter action state (proven by fault injection).
- [ ] Outbox guarantees the event is recorded in the seal transaction.
- [ ] Events carry tenant + action_id + ledger_seq + event_id; consumers dedupe.

---

## Pattern: transactional outbox
Write the event into an `events_outbox` row **inside the same transaction that seals** the ledger
entry. A separate dispatcher reads the outbox and publishes (at-least-once) to the broker. This makes
"emitted iff sealed" true without a distributed transaction, and survives crashes.

## EventPort (illustrative — define the real Protocol in core/ports/)
- `emit(*, event) -> None` — best-effort; failures are logged + retried, never surfaced to the caller as a lifecycle failure.

## Definition of Done (spec §6 — K·07)
- [ ] events emitted **only after** seal; emit best-effort and never alters a sealed outcome.
- [ ] events carry tenant + action id (+ ledger_seq, event_id, type).
- [ ] at-least-once delivery; consumers idempotent.
- [ ] fault injection: broker-down does not change any sealed action.
