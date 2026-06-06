---
name: quaicu-governed-lifecycle
description: |
  QUAICU governed-action lifecycle enforcer. Use when building or reviewing the lifecycle spine
  (core/lifecycle/), any code that proposes, evaluates, gates, executes, seals, or emits an action,
  or any delivery adapter that surfaces the lifecycle. Enforces: fail-closed at every arrow,
  no-bypass invariant, idempotency, deterministic evaluation, correct state transitions.
  Trigger keywords: propose, evaluate, gate, execute, seal, emit, Action, Proposal, GovernedAction,
  lifecycle, ActionState, idempotency_key, PENDING_APPROVAL, EXECUTED, DENIED, HALTED, SEALED.
---

# QUAICU Governed-Action Lifecycle

You are the lifecycle correctness enforcer. Every governed action in QUAICU passes through exactly
one sequence: `propose → evaluate → gate → execute → seal → emit`. No step is optional. No step
can be skipped. Failure at any arrow → DENY or HALT, never proceed.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every lifecycle choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → choose DENY/HALT and stop.

### Invariants — never violated
- ALWAYS run the steps in this exact order: `propose → evaluate → gate → execute → seal → emit`. Never skip, reorder, or merge a step.
- NEVER call `execute` before BOTH evaluate passed AND (gate passed OR gate not required). Executing first is the no-bypass (F-04) violation.
- ALWAYS seal BEFORE marking the action COMPLETED. An executed-but-unsealed action is HALTED, never COMPLETED.
- ALWAYS treat any error/timeout/ambiguity at any arrow as DENY (governance) or HALT (infra) — never advance.
- `emit` is best-effort and runs AFTER seal; a failed emit NEVER changes the outcome (already sealed = already governed).

### Step → next-state map (apply exactly; states terminal unless marked "continue")
| At step | Outcome | Resulting state |
|---|---|---|
| propose | duplicate idempotency_key | CANCELLED (return existing action) |
| evaluate | decision = allow | continue → EXECUTING |
| evaluate | decision = deny / no policy / error / timeout | DENIED |
| evaluate | decision = require_approval | PENDING_APPROVAL |
| gate | approved | continue → EXECUTING |
| gate | rejected OR timed out | DENIED |
| gate | HITL port error | HALTED |
| execute | success | continue → SEALING |
| execute | failure | HALTED |
| seal | success | SEALED → COMPLETED |
| seal | failure | HALTED (alert: executed but unsealed) |

### Tie-break rules
- Gate runs ONLY when evaluate returned `require_approval`. If evaluate said `allow`, never add an approval step.
- HITL timeout = REJECTED → DENIED. Never auto-approve on timeout.
- Governance failure (a policy/human said no, or no clear allow) → DENIED. Infra failure (a service failed) → HALTED. Can't tell → DENIED.
- Idempotency: DB unique constraint on `(tenant_id, idempotency_key)` + INSERT…ON CONFLICT. Never SELECT-then-INSERT (it races).

### Stop-and-apply triggers
- About to write `execute`/the state change? → assert evaluate(+gate) already passed in this same run first.
- About to set state COMPLETED? → confirm a ledger entry sealed in this run; else HALTED.
- About to process the same action twice? → idempotency via ON CONFLICT; return existing state.

### Self-check
- [ ] All six steps present, in order, none optional.
- [ ] No path reaches `execute` without evaluate(+gate) passing.
- [ ] Seal-failure path → HALTED + alert, never COMPLETED.
- [ ] Every transition uses the state map; invalid ones raise `LifecycleInvalidTransitionError`.
- [ ] Evaluation logic uses no wall-clock/random/live state.

---

## The Lifecycle Contract

```
propose(action)
  → evaluate(K·01 policy + K·04 consent + K·08–K·11 assurance signals)
    → gate(K·03 HITL — only when policy returned require_approval)
      → execute(the actual state change — ONLY after evaluate + gate pass)
        → seal(K·02 TrustLedger — write immutable RFC 6962 Merkle proof)
          → emit(K·07 EventBus — structured event after seal, best-effort)

Any error / timeout / ambiguity at any arrow ⇒ DENY / HALT (never proceed to next step)
```

---

## State Transition Diagram (ASCII — full)

```
                            ┌──────────────────────────────────────────────────────┐
                            │               QUAICU ACTION STATE MACHINE            │
                            └──────────────────────────────────────────────────────┘

  [client submits]
        │
        ▼
  ┌──────────┐   duplicate idempotency_key
  │ PROPOSED │ ──────────────────────────────────────────────────► CANCELLED (terminal)
  └──────────┘
        │  idempotency clear, workflow started
        ▼
  ┌────────────┐   policy engine error / consent denied / timeout
  │ EVALUATING │ ──────────────────────────────────────────────────► DENIED (terminal)
  └────────────┘
        │                                │
        │ decision = allow               │ decision = deny
        │                                ▼
        │                          DENIED (terminal)
        │ decision = require_approval
        ▼
  ┌──────────────────┐
  │ PENDING_APPROVAL │ ──── HITL timeout / port error ──────────────► HALTED (terminal)
  └──────────────────┘
        │                            │
        │ HITL approves              │ HITL rejects
        ▼                            ▼
  ┌──────────┐                 REJECTED (terminal)
  │ APPROVED │
  └──────────┘
        │  execute() called
        ▼
  ┌───────────┐   execute() throws
  │ EXECUTING │ ──────────────────────────────────────────────────► HALTED (terminal)
  └───────────┘
        │  execute() returns
        ▼
  ┌──────────┐
  │ EXECUTED │
  └──────────┘
        │  ledger.seal() called
        ▼
  ┌─────────┐   seal() throws (CRITICAL partial failure — alert operator)
  │ SEALING │ ──────────────────────────────────────────────────────► HALTED (terminal)
  └─────────┘
        │  seal() returns entry
        ▼
  ┌────────┐
  │ SEALED │
  └────────┘
        │  event_bus.publish()
        ▼
  ┌──────────┐   publish() throws (non-fatal — action already sealed)
  │ EMITTING │ ──────────────────────── (log, do NOT un-seal) ──────► COMPLETED
  └──────────┘                                                         (terminal)
        │  publish() succeeds
        ▼
  COMPLETED (terminal)


  Terminal states: COMPLETED · DENIED · HALTED · REJECTED · CANCELLED
  From any terminal state: no further transitions are permitted.
  Attempt to transition from a terminal state raises LifecycleInvalidTransitionError.
```

---

## Core Types — Full Typed Definitions

```python
# core/lifecycle/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Literal
from uuid import UUID


class ActionState(Enum):
    PROPOSED          = auto()   # submitted, not yet evaluated
    EVALUATING        = auto()   # policy engine running
    PENDING_APPROVAL  = auto()   # require_approval → waiting at HITL gate
    APPROVED          = auto()   # HITL approved → proceed to execute
    REJECTED          = auto()   # HITL rejected → terminal deny
    EXECUTING         = auto()   # execute() running
    EXECUTED          = auto()   # execute() succeeded → proceed to seal
    SEALING           = auto()   # ledger write in progress
    SEALED            = auto()   # ledger entry written → proceed to emit
    EMITTING          = auto()   # event publishing
    COMPLETED         = auto()   # terminal success
    DENIED            = auto()   # terminal: policy denied
    HALTED            = auto()   # terminal: error/timeout at any step
    CANCELLED         = auto()   # terminal: idempotency duplicate


TERMINAL_STATES = frozenset({
    ActionState.COMPLETED,
    ActionState.DENIED,
    ActionState.HALTED,
    ActionState.REJECTED,
    ActionState.CANCELLED,
})

# Valid forward transitions — transitions NOT in this map are forbidden
VALID_TRANSITIONS: dict[ActionState, frozenset[ActionState]] = {
    ActionState.PROPOSED:         frozenset({ActionState.EVALUATING, ActionState.CANCELLED}),
    ActionState.EVALUATING:       frozenset({ActionState.PENDING_APPROVAL, ActionState.APPROVED,
                                              ActionState.DENIED}),
    ActionState.PENDING_APPROVAL: frozenset({ActionState.APPROVED, ActionState.REJECTED,
                                              ActionState.HALTED}),
    ActionState.APPROVED:         frozenset({ActionState.EXECUTING}),
    ActionState.EXECUTING:        frozenset({ActionState.EXECUTED, ActionState.HALTED}),
    ActionState.EXECUTED:         frozenset({ActionState.SEALING}),
    ActionState.SEALING:          frozenset({ActionState.SEALED, ActionState.HALTED}),
    ActionState.SEALED:           frozenset({ActionState.EMITTING}),
    ActionState.EMITTING:         frozenset({ActionState.COMPLETED}),
    # Terminal states: no further transitions
    ActionState.COMPLETED:        frozenset(),
    ActionState.DENIED:           frozenset(),
    ActionState.HALTED:           frozenset(),
    ActionState.REJECTED:         frozenset(),
    ActionState.CANCELLED:        frozenset(),
}


@dataclass
class Action:
    id: UUID
    type: str                         # e.g. "ciro.ifrs9.stage_transition"
    payload: dict[str, Any]
    actor_id: str
    tenant_id: str
    idempotency_key: str
    state: ActionState = ActionState.PROPOSED
    proposed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Populated as lifecycle progresses:
    evaluated_at: datetime | None = None
    executed_at: datetime | None = None
    sealed_at: datetime | None = None
    completed_at: datetime | None = None
    halt_reason: str | None = None
    deny_reason: str | None = None
    # Workflow tracking:
    workflow_handle_id: str | None = None


@dataclass
class EvaluationResult:
    decision: Literal["allow", "deny", "require_approval"]
    # Record ALL policy version IDs evaluated — required for deterministic replay
    policy_versions: list[str]
    consent_checked: bool
    # K·08–K·11 assurance signals — recorded, never recomputed on replay
    assurance_signals: dict[str, Any]
    approvers: list[str] = field(default_factory=list)  # populated if require_approval
    governing_policy_ids: list[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LedgerEntry:
    """
    Full sealed record of a governed action.
    Must contain everything needed to:
      (a) re-derive WHY the decision was made (decision replay),
      (b) reconstruct institutional state (state replay),
      (c) prove the entry's inclusion in the Merkle tree (RFC 6962).
    """
    action_id: UUID
    tenant_id: str
    # Full inputs — required for replay; never record only outcomes
    action_type: str
    action_payload: dict[str, Any]
    actor_id: str
    # Full evaluation record — required for decision replay
    evaluation_result: EvaluationResult
    # Non-deterministic results from K·05 Gateway — recorded, NEVER recomputed on replay
    recorded_model_outputs: dict[str, Any]
    # Execution result (the outcome of the state change)
    execution_result: Any
    # Ledger integrity fields (RFC 6962)
    ledger_seq: int               # monotonic DB sequence — not wall-clock
    leaf_hash: str                # SHA-256 of this entry's canonical serialisation
    tree_head_hash: str           # Merkle tree head at time of append
    inclusion_proof: list[str]    # RFC 6962 inclusion proof nodes
    # Metadata
    sealed_at: datetime
    schema_version: int = 1       # increment if LedgerEntry shape changes; old entries stay verifiable


@dataclass
class GovernedActionEvent:
    """Published to K·07 EventBus after a successful seal."""
    action_id: str
    action_type: str
    tenant_id: str
    actor_id: str
    decision: str
    ledger_seq: int
    leaf_hash: str
    occurred_at: datetime
```

---

## Lifecycle Engine — Complete Implementation

```python
# core/lifecycle/engine.py
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from uuid import UUID

from core.errors import (
    LifecycleDeniedError, LifecycleHaltedError, LifecycleIdempotencyError,
    LifecycleBypassAttemptError, LifecycleInvalidTransitionError,
    PortContractError, StoragePortError,
)
from core.lifecycle.types import (
    Action, ActionState, EvaluationResult, LedgerEntry, GovernedActionEvent,
    TERMINAL_STATES, VALID_TRANSITIONS,
)
from core.ports import HITLPort, WorkflowPort, StoragePort
from core.telemetry import (
    tracer, Spans, Attrs, record_lifecycle_step,
    actions_proposed_counter, actions_denied_counter, actions_completed_counter,
    actions_pending_approval_gauge,
)

ExecuteFn = Callable[[Action], Awaitable[Any]]

GOVERNED_ACTION_WORKFLOW = "quaicu.governed_action"


class LifecycleEngine:
    """
    The lifecycle spine. Every governed action flows through exactly this path.
    No shortcuts. No customer branches. No fail-open paths.

    All dependencies are injected via ports — this class never imports a concrete adapter.
    """

    def __init__(
        self,
        *,
        policy_engine,          # core.policy.engine.PolicyEngine (typed at import-time)
        hitl_port: HITLPort,
        workflow_port: WorkflowPort,
        ledger,                 # core.ledger.trust_ledger.TrustLedger
        event_bus,              # core.events.bus.EventBus
        identity_port,          # core.ports.identity.IdentityPort
        storage: StoragePort,
    ) -> None:
        self._policy_engine = policy_engine
        self._hitl = hitl_port
        self._workflow = workflow_port
        self._ledger = ledger
        self._event_bus = event_bus
        self._identity = identity_port
        self._storage = storage

    # ── Public entry point ────────────────────────────────────────────────────

    async def propose(self, action: Action) -> Action:
        """
        Entry point for all governed actions.

        Idempotency check is the FIRST operation — before any storage write,
        before any policy evaluation, before any workflow start.

        Returns the action (possibly with CANCELLED state if idempotent duplicate).
        Raises LifecycleDeniedError or LifecycleHaltedError on unrecoverable failure.
        """
        with tracer.start_as_current_span(Spans.LIFECYCLE_PROPOSE) as span:
            t_start = time.monotonic()
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))
            span.set_attribute(Attrs.ACTION_TYPE, action.type)
            span.set_attribute(Attrs.IDEMPOTENCY_KEY, action.idempotency_key)

            actions_proposed_counter.add(
                1, {Attrs.TENANT_ID: action.tenant_id, Attrs.ACTION_TYPE: action.type}
            )

            # ── Step 1: idempotency check (atomic via ON CONFLICT) ────────────
            try:
                existing = await self._storage_insert_or_get_idempotent(action)
            except StoragePortError as exc:
                action.state = ActionState.HALTED
                action.halt_reason = f"Storage error during idempotency check: {exc}"
                raise LifecycleHaltedError(str(exc)) from exc

            if existing is not None:
                # Duplicate submission — return the existing action, do NOT re-execute
                action.state = ActionState.CANCELLED
                span.set_attribute(Attrs.ACTION_STATE, "CANCELLED")
                return existing

            # ── Step 2: transition to EVALUATING and persist ──────────────────
            self._transition(action, ActionState.EVALUATING)
            try:
                async with self._storage.transaction() as tx:
                    await tx.save_action(action)
            except StoragePortError as exc:
                action.state = ActionState.HALTED
                raise LifecycleHaltedError(f"Failed to persist action: {exc}") from exc

            # ── Step 3: hand to workflow engine — durable from here ───────────
            try:
                handle = await self._workflow.start(
                    definition=GOVERNED_ACTION_WORKFLOW,
                    payload={"action_id": str(action.id), "tenant_id": action.tenant_id},
                    tenant=action.tenant_id,
                )
                action.workflow_handle_id = str(handle.id)
                async with self._storage.transaction() as tx:
                    await tx.save_action(action)
            except Exception as exc:
                action.state = ActionState.HALTED
                action.halt_reason = f"Workflow start failed: {exc}"
                raise LifecycleHaltedError(f"Workflow start failed — action halted: {exc}") from exc

            duration_ms = (time.monotonic() - t_start) * 1000
            record_lifecycle_step(
                span, "propose", action.tenant_id, str(action.id),
                action.type, "EVALUATING", duration_ms,
            )
            return action

    async def run(self, action: Action, execute_fn: ExecuteFn) -> LedgerEntry:
        """
        Full lifecycle run: evaluate → gate → execute → seal → emit.
        Called by the workflow engine after propose() has handed off.

        This is the no-bypass path. execute_fn is ONLY called after evaluate AND gate succeed.
        """
        eval_result = await self._evaluate(action)
        await self._gate(action, eval_result)
        exec_result = await self._execute(action, execute_fn)
        entry = await self._seal(action, eval_result, exec_result)
        await self._emit(action, entry)
        return entry

    # ── Internal lifecycle steps ──────────────────────────────────────────────

    async def _evaluate(self, action: Action) -> EvaluationResult:
        """
        Fail-closed: ANY exception → DENY.
        None result → DENY.
        Policy engine is never optional.
        """
        with tracer.start_as_current_span(Spans.LIFECYCLE_EVALUATE) as span:
            t_start = time.monotonic()
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))

            try:
                result: EvaluationResult | None = await self._policy_engine.evaluate(action)
            except Exception as exc:
                action.state = ActionState.DENIED
                action.deny_reason = f"Policy evaluation failed: {exc}"
                await self._persist_state(action)
                actions_denied_counter.add(
                    1, {Attrs.TENANT_ID: action.tenant_id, "reason": "eval_error"}
                )
                raise LifecycleDeniedError(
                    "Policy evaluation failed — fail-closed",
                    detail={"action_id": str(action.id), "cause": str(exc)},
                ) from exc

            if result is None:
                action.state = ActionState.DENIED
                action.deny_reason = "Policy engine returned None — port contract violation"
                await self._persist_state(action)
                raise LifecycleDeniedError(
                    "Policy engine returned None — port contract violation",
                    detail={"action_id": str(action.id)},
                )

            action.evaluated_at = datetime.now(timezone.utc)
            span.set_attribute(Attrs.POLICY_DECISION, result.decision)
            span.set_attribute(
                "quaicu.policy_versions_evaluated", ",".join(result.policy_versions)
            )
            duration_ms = (time.monotonic() - t_start) * 1000
            record_lifecycle_step(
                span, "evaluate", action.tenant_id, str(action.id),
                action.type, action.state.name, duration_ms,
            )
            return result

    async def _gate(self, action: Action, result: EvaluationResult) -> None:
        """
        HITL gate. Only entered when decision == require_approval.
        Deny on HITL timeout — never allow on timeout.
        """
        if result.decision == "deny":
            action.state = ActionState.DENIED
            action.deny_reason = f"Denied by policies: {result.governing_policy_ids}"
            await self._persist_state(action)
            actions_denied_counter.add(
                1, {Attrs.TENANT_ID: action.tenant_id, "reason": "policy_deny"}
            )
            raise LifecycleDeniedError(
                f"Policy denied action — governing policies: {result.governing_policy_ids}",
                detail={"action_id": str(action.id), "policies": result.governing_policy_ids},
            )

        if result.decision == "allow":
            # No gate needed. Directly approve.
            self._transition(action, ActionState.APPROVED)
            await self._persist_state(action)
            return

        # decision == require_approval
        with tracer.start_as_current_span(Spans.HITL_REQUEST) as span:
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))

            self._transition(action, ActionState.PENDING_APPROVAL)
            await self._persist_state(action)
            actions_pending_approval_gauge.add(
                1, {Attrs.TENANT_ID: action.tenant_id}
            )

            try:
                handle = await self._hitl.request_approval(
                    action=action,
                    approvers=result.approvers,
                    tenant=action.tenant_id,
                )
            except Exception as exc:
                action.state = ActionState.HALTED
                action.halt_reason = f"HITL request failed: {exc}"
                await self._persist_state(action)
                actions_pending_approval_gauge.add(
                    -1, {Attrs.TENANT_ID: action.tenant_id}
                )
                raise LifecycleHaltedError(
                    f"HITL request failed — action halted: {exc}",
                    detail={"action_id": str(action.id)},
                ) from exc

            # Wait for approval decision (durable: done via workflow signal in production)
            decision = await self._wait_for_approval(handle, action)
            actions_pending_approval_gauge.add(
                -1, {Attrs.TENANT_ID: action.tenant_id}
            )

            if decision.value not in ("APPROVED",):
                action.state = ActionState.REJECTED
                action.deny_reason = f"HITL decision: {decision.value}"
                await self._persist_state(action)
                actions_denied_counter.add(
                    1, {Attrs.TENANT_ID: action.tenant_id, "reason": "hitl_rejected"}
                )
                raise LifecycleDeniedError(
                    f"HITL rejected or timed out — fail-closed: {decision.value}",
                    detail={"action_id": str(action.id), "hitl_decision": decision.value},
                )

            self._transition(action, ActionState.APPROVED)
            await self._persist_state(action)

    async def _execute(self, action: Action, execute_fn: ExecuteFn) -> Any:
        """
        The actual state change. ONLY reachable via _evaluate() + _gate().
        Any attempt to call _execute() directly without those steps raises LifecycleBypassAttemptError.
        """
        if action.state != ActionState.APPROVED:
            raise LifecycleBypassAttemptError(
                f"execute() called with state={action.state.name} — expected APPROVED. "
                f"This is a F-04 violation. No bypass is ever permitted.",
                detail={"action_id": str(action.id), "current_state": action.state.name},
            )

        with tracer.start_as_current_span(Spans.LIFECYCLE_EXECUTE) as span:
            t_start = time.monotonic()
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))

            self._transition(action, ActionState.EXECUTING)
            await self._persist_state(action)

            try:
                result = await execute_fn(action)
            except Exception as exc:
                action.state = ActionState.HALTED
                action.halt_reason = f"Execute raised: {type(exc).__name__}: {exc}"
                await self._persist_state(action)
                raise LifecycleHaltedError(
                    f"Execute failed — action halted: {exc}",
                    detail={"action_id": str(action.id), "cause": str(exc)},
                ) from exc

            self._transition(action, ActionState.EXECUTED)
            action.executed_at = datetime.now(timezone.utc)
            await self._persist_state(action)

            duration_ms = (time.monotonic() - t_start) * 1000
            record_lifecycle_step(
                span, "execute", action.tenant_id, str(action.id),
                action.type, "EXECUTED", duration_ms,
            )
            return result

    async def _seal(
        self, action: Action, eval_result: EvaluationResult, exec_result: Any
    ) -> LedgerEntry:
        """
        Write to TrustLedger.

        CRITICAL: if seal fails after execute succeeded, the action is in a partial
        failure state (external change happened, no ledger record). Set HALTED and alert.
        Never mark EXECUTED without a sealed ledger entry.
        """
        with tracer.start_as_current_span(Spans.LIFECYCLE_SEAL) as span:
            t_start = time.monotonic()
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))

            self._transition(action, ActionState.SEALING)
            await self._persist_state(action)

            try:
                entry = await self._ledger.seal(action, eval_result, exec_result)
            except Exception as exc:
                # CRITICAL partial failure: execute ran, seal did not.
                action.state = ActionState.HALTED
                action.halt_reason = f"Ledger seal failed: {exc}"
                await self._persist_state(action)
                # Alert operator — this requires manual reconciliation.
                await self._alert_partial_failure(action, exec_result, exc)
                raise LifecycleHaltedError(
                    "Ledger seal failed — action HALTED, not COMPLETED. "
                    "Operator reconciliation required.",
                    detail={
                        "action_id": str(action.id),
                        "cause": str(exc),
                        "exec_result_recorded": True,
                    },
                ) from exc

            self._transition(action, ActionState.SEALED)
            action.sealed_at = datetime.now(timezone.utc)
            await self._persist_state(action)

            span.set_attribute(Attrs.LEDGER_SEQ, entry.ledger_seq)
            duration_ms = (time.monotonic() - t_start) * 1000
            record_lifecycle_step(
                span, "seal", action.tenant_id, str(action.id),
                action.type, "SEALED", duration_ms,
            )
            return entry

    async def _emit(self, action: Action, entry: LedgerEntry) -> None:
        """
        Publish structured event after seal.
        Emit failure is logged but does NOT un-seal.
        The action is already SEALED — the state change is confirmed.
        Consumers can rebuild from ledger if they miss an event.
        """
        with tracer.start_as_current_span(Spans.LIFECYCLE_EMIT) as span:
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))
            span.set_attribute(Attrs.LEDGER_SEQ, entry.ledger_seq)

            self._transition(action, ActionState.EMITTING)
            await self._persist_state(action)

            event = GovernedActionEvent(
                action_id=str(action.id),
                action_type=action.type,
                tenant_id=action.tenant_id,
                actor_id=action.actor_id,
                decision=entry.evaluation_result.decision,
                ledger_seq=entry.ledger_seq,
                leaf_hash=entry.leaf_hash,
                occurred_at=entry.sealed_at,
            )

            try:
                await self._event_bus.publish(event)
            except Exception as exc:
                # Emit failure: log, do NOT reverse seal, do NOT halt.
                span.record_exception(exc)
                span.add_event("emit_failed_non_fatal", {"cause": str(exc)})

            self._transition(action, ActionState.COMPLETED)
            action.completed_at = datetime.now(timezone.utc)
            await self._persist_state(action)

            actions_completed_counter.add(
                1, {Attrs.TENANT_ID: action.tenant_id, Attrs.ACTION_TYPE: action.type}
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _transition(self, action: Action, target: ActionState) -> None:
        """Enforce valid state transitions. Raise on invalid."""
        allowed = VALID_TRANSITIONS.get(action.state, frozenset())
        if target not in allowed:
            raise LifecycleInvalidTransitionError(
                f"Invalid transition: {action.state.name} → {target.name}",
                detail={
                    "action_id": str(action.id),
                    "from": action.state.name,
                    "to": target.name,
                    "allowed": [s.name for s in allowed],
                },
            )
        action.state = target

    async def _persist_state(self, action: Action) -> None:
        try:
            async with self._storage.transaction() as tx:
                await tx.save_action(action)
        except StoragePortError as exc:
            # Storage failure during state persist. If in a terminal state, swallow and log.
            # If mid-flow, escalate.
            if action.state not in TERMINAL_STATES:
                raise LifecycleHaltedError(
                    f"State persist failed mid-lifecycle: {exc}",
                    detail={"action_id": str(action.id), "state": action.state.name},
                ) from exc

    async def _storage_insert_or_get_idempotent(self, action: Action) -> Action | None:
        """
        Atomically insert action or detect existing record for this idempotency key.
        Uses DB-level INSERT ... ON CONFLICT to avoid SELECT-then-INSERT race.
        Returns None if insert succeeded (new action), or existing Action if duplicate.
        """
        async with self._storage.transaction() as tx:
            result = await tx.insert_action_idempotent(action)
            return result  # None = new; Action = existing

    async def _wait_for_approval(self, handle, action: Action):
        """
        Poll for HITL decision. In production, this is driven by a workflow signal.
        Timeout is policy-configured; timeout → TIMED_OUT decision → fail-closed.
        """
        from core.types import ApprovalDecision
        while True:
            decision = await self._hitl.poll(handle)
            if decision != ApprovalDecision.PENDING:
                return decision
            # In the Postgres state-machine adapter this loop yields to the workflow;
            # in the Temporal adapter this is a workflow.wait_condition().

    async def _alert_partial_failure(
        self, action: Action, exec_result: Any, exc: Exception
    ) -> None:
        """
        CRITICAL alert: execute succeeded but seal failed.
        The external state change happened but is unrecorded.
        This requires operator attention and reconciliation.
        """
        import logging
        logger = logging.getLogger("quaicu.kernel.lifecycle")
        logger.critical(
            "PARTIAL FAILURE: action executed but seal failed. "
            "Operator reconciliation required. action_id=%s tenant_id=%s error=%s",
            action.id, action.tenant_id, exc,
            extra={"action_id": str(action.id), "tenant_id": action.tenant_id},
        )
        try:
            await self._event_bus.publish_alert({
                "type": "quaicu.kernel.partial_failure",
                "action_id": str(action.id),
                "tenant_id": action.tenant_id,
                "error": str(exc),
                "severity": "CRITICAL",
            })
        except Exception:
            pass  # alert publish failure should not mask the original error
```

---

## Idempotency — Concurrent Submission Safety

The idempotency check must be atomic. A SELECT followed by INSERT in two separate statements will
race under concurrent submissions. The only safe approach is a DB-level unique constraint with
`INSERT ... ON CONFLICT`.

```sql
-- migrations/versions/001_actions_table.sql

-- Schema-per-tenant: this DDL runs inside the tenant's schema.
CREATE TABLE IF NOT EXISTS actions (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    type              TEXT        NOT NULL,
    payload           JSONB       NOT NULL,
    actor_id          TEXT        NOT NULL,
    tenant_id         TEXT        NOT NULL,
    idempotency_key   TEXT        NOT NULL,
    state             TEXT        NOT NULL DEFAULT 'PROPOSED',
    workflow_handle_id TEXT,
    proposed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    evaluated_at      TIMESTAMPTZ,
    executed_at       TIMESTAMPTZ,
    sealed_at         TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    halt_reason       TEXT,
    deny_reason       TEXT,
    schema_version    INT         NOT NULL DEFAULT 1
);

-- This constraint is the idempotency enforcement. Application code does NOT enforce alone.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_idempotency
    ON actions (tenant_id, idempotency_key);

-- Performance index for lifecycle state queries
CREATE INDEX IF NOT EXISTS idx_actions_tenant_state
    ON actions (tenant_id, state, proposed_at DESC);
```

```python
# adapters/storage/postgres/actions_repo.py
"""
INSERT ... ON CONFLICT is the atomic idempotency primitive.
Never use SELECT-then-INSERT.
"""
from core.lifecycle.types import Action, ActionState


async def insert_action_idempotent(
    tx, action: Action
) -> Action | None:
    """
    Atomically insert the action.
    Returns None if successfully inserted (new action).
    Returns the existing Action record if idempotency_key already present.
    Never allows two executions for the same key.
    """
    result = await tx.execute(
        """
        INSERT INTO actions
            (id, type, payload, actor_id, tenant_id, idempotency_key, state, proposed_at)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (tenant_id, idempotency_key)
            DO NOTHING
        RETURNING id
        """,
        str(action.id), action.type, action.payload,
        action.actor_id, action.tenant_id, action.idempotency_key,
        action.state.name, action.proposed_at,
    )

    if result:
        return None  # new insertion succeeded

    # Conflict: return the existing record
    existing_row = await tx.fetch_one(
        "SELECT * FROM actions WHERE tenant_id = $1 AND idempotency_key = $2",
        action.tenant_id, action.idempotency_key,
    )
    return _row_to_action(existing_row)
```

---

## The `@governed` Decorator — Full Implementation with Retry Semantics

```python
# delivery/sdk/decorator.py
from __future__ import annotations
import asyncio
import functools
import logging
from typing import Callable, Awaitable, Any
from uuid import uuid4

from core.errors import LifecycleDeniedError, LifecycleHaltedError, LifecycleIdempotencyError
from core.lifecycle.types import Action, ActionState

logger = logging.getLogger("quaicu.sdk.governed")

_DEFAULT_RETRY_ON_HALT_MAX = 2
_DEFAULT_RETRY_BACKOFF_BASE_S = 1.0


def _make_governed_decorator(*, policy: str, kernel) -> Callable:
    """
    Factory used by Kernel.governed(). Returns the @governed(policy=...) decorator.
    Not called directly by user code.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(
            *args: Any,
            actor,
            idempotency_key: str | None = None,
            _retry_halted: bool = True,
            **kwargs: Any,
        ) -> Any:
            """
            Wraps fn in the full governed lifecycle.

            Args:
                actor: Resolved Actor. Mandatory — cannot propose without identity.
                idempotency_key: Caller-supplied key for deduplication.
                    If not supplied, a random UUID is generated (not idempotent across calls).
                _retry_halted: If True (default), retry once on HALTED with backoff.
                    Set False for tests or when caller wants explicit control.
            """
            if actor is None:
                raise LifecycleDeniedError(
                    "actor is required for a governed action. "
                    "Ensure the caller resolves identity before proposing.",
                )

            effective_key = idempotency_key or str(uuid4())

            action = Action(
                id=uuid4(),
                type=policy,
                payload={"args": list(args), "kwargs": kwargs},
                actor_id=actor.id,
                tenant_id=actor.tenant_id,
                idempotency_key=effective_key,
            )

            # Retry loop — only retries on HALTED (transient infra errors), never on DENIED.
            max_attempts = _DEFAULT_RETRY_ON_HALT_MAX if _retry_halted else 1
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    entry = await kernel._lifecycle.run(
                        action=action,
                        execute_fn=lambda a: fn(*args, **kwargs),
                    )
                    return entry
                except LifecycleDeniedError:
                    # DENIED is terminal. Never retry a denial.
                    raise
                except LifecycleHaltedError as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        backoff = _DEFAULT_RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1))
                        logger.warning(
                            "Governed action HALTED on attempt %d/%d — retrying in %.1fs. "
                            "action_id=%s cause=%s",
                            attempt, max_attempts, backoff, action.id, exc,
                        )
                        await asyncio.sleep(backoff)
                        # Reset action state for retry — idempotency key ensures no double-execute
                        action.state = ActionState.PROPOSED
                    else:
                        raise

            raise last_exc  # unreachable but makes type checker happy

        return wrapper
    return decorator
```

---

## REST Surface — Full Error Codes

```
POST /kernel/v1/actions/propose
  Body:    { type: str, payload: dict, idempotency_key: str }
  Headers: Authorization: Bearer <token>

  200 OK        { action_id, state: "COMPLETED", ledger_seq, leaf_hash }
                 (synchronous path — fast actions that don't require HITL)
  202 Accepted  { action_id, state: "PENDING_APPROVAL" }
                 (action requires HITL — client polls or receives webhook)
  400 Bad Request  { error: "VALIDATION_ERROR", detail: "..." }
                 (payload fails JSON schema for this action type)
  401 Unauthorized { error: "AUTH_REQUIRED" }
                 (no valid bearer token)
  403 Forbidden    { error: "TENANT_MISMATCH" }
                 (token tenant claim does not match path tenant)
  409 Conflict     { error: "LIFECYCLE_IDEMPOTENT", action_id: "...", state: "..." }
                 (idempotency_key already used — returns existing action state)
  422 Unprocessable { error: "POLICY_NOT_FOUND", detail: "No policy governs action type X" }
                 (no ACTIVATED policy for this action type — fail-closed deny)
  503 Service Unavailable { error: "PORT_UNAVAILABLE", detail: "..." }
                 (policy engine, ledger, or workflow engine unreachable)


POST /kernel/v1/actions/{id}/approve
  Body:    { decision: "approve" | "reject", approver_id: str, note: str | null }

  200 OK        { state: "COMPLETED" | "REJECTED", ledger_seq?, leaf_hash? }
  400 Bad Request  { error: "VALIDATION_ERROR", detail: "decision must be approve or reject" }
  403 Forbidden    { error: "NOT_AUTHORIZED_APPROVER", detail: "approver_id not in approvers list" }
  404 Not Found    { error: "ACTION_NOT_FOUND" }
  409 Conflict     { error: "LIFECYCLE_INVALID_TRANSITION",
                     detail: "action is in state COMPLETED, not PENDING_APPROVAL" }
  503 Service Unavailable { error: "PORT_UNAVAILABLE" }


GET /kernel/v1/actions/{id}
  200 OK  { action_id, type, state, proposed_at, actor_id, tenant_id, ... }
  404 Not Found
  403 Forbidden  (action belongs to a different tenant)


GET /kernel/v1/actions/{id}/trail
  200 OK  { action_id, ledger_seq, leaf_hash, inclusion_proof, evaluation_result, ... }
  404 Not Found
  404 Not Found  (action not yet sealed — no ledger trail)
```

---

## Edge Cases

### Concurrent Submissions — Same Idempotency Key, Two Concurrent Requests

Two processes may race on the same `idempotency_key`. The DB-level `UNIQUE` constraint resolves
this correctly: one INSERT succeeds, the other gets a conflict. The conflict handler returns the
existing record. Neither process double-executes.

**Test this explicitly:**
```python
# tests/conformance/lifecycle/test_idempotency.py
async def test_concurrent_same_idempotency_key_no_double_execute(engine, storage):
    """Two simultaneous proposals with the same key must produce exactly one execution."""
    key = "idempotency-test-abc"
    action_a = make_action(idempotency_key=key)
    action_b = make_action(idempotency_key=key)  # different UUID, same key

    execute_count = 0
    async def counting_execute_fn(a):
        nonlocal execute_count
        execute_count += 1
        return {"result": "ok"}

    results = await asyncio.gather(
        engine.propose(action_a),
        engine.propose(action_b),
        return_exceptions=True,
    )

    # One must succeed and one must be cancelled — never double-execute
    states = [r.state if not isinstance(r, Exception) else "ERROR" for r in results]
    assert ActionState.CANCELLED in [r.state for r in results if not isinstance(r, Exception)]
    assert execute_count <= 1, f"Double execution detected: execute_count={execute_count}"
```

### Clock Skew — Air-Gapped Deployment

The ledger sequence is a DB sequence (monotonically increasing regardless of wall clock). Timestamps
are metadata only. If a node's clock drifts backward, the ledger remains consistent.

Detect skew and record it as an event but never reject the seal:

```python
# core/ledger/trust_ledger.py — clock skew detection
async def _next_seq_and_timestamp(self, tx) -> tuple[int, datetime]:
    seq = await tx.nextval(f"ledger_seq_{self._tenant_id}")
    ts  = datetime.now(tz=timezone.utc)
    prev_ts = await tx.scalar(
        "SELECT sealed_at FROM ledger_entries WHERE tenant_id = $1 ORDER BY seq DESC LIMIT 1",
        self._tenant_id,
    )
    if prev_ts and ts < prev_ts:
        logger.warning(
            "Clock skew detected: current ts %s is before previous entry ts %s. "
            "Sequence integrity maintained via DB sequence. tenant_id=%s seq=%d",
            ts, prev_ts, self._tenant_id, seq,
        )
        # Record skew event for audit — do NOT reject the seal
        await tx.execute(
            "INSERT INTO ledger_clock_skew_events (tenant_id, seq, observed_ts, expected_min_ts)"
            " VALUES ($1, $2, $3, $4)",
            self._tenant_id, seq, ts, prev_ts,
        )
    return seq, ts
```

### Timeout Cascade — Policy Engine Times Out During High Load

If the policy engine times out, the fail-closed rule applies: DENY the action. But if many actions
are simultaneously denied due to a policy engine outage, this must be detectable (circuit-breaker
pattern on the policy engine port):

```python
# core/lifecycle/engine.py
# Use a circuit breaker on the policy engine call (implemented in the adapter, not core)
# Core sees only the port method — the adapter handles the circuit breaker internally.
# If the port raises PortUnavailableError, core's response is always DENY.

async def _evaluate(self, action: Action) -> EvaluationResult:
    try:
        return await self._policy_engine.evaluate(action)
    except PortTimeoutError as exc:
        # Timeout is unambiguous: fail-closed, DENY.
        action.state = ActionState.DENIED
        raise LifecycleDeniedError(
            "Policy engine timed out — fail-closed DENY",
            detail={"action_id": str(action.id), "timeout_ms": exc.detail.get("timeout_ms")},
        ) from exc
    except PortUnavailableError as exc:
        action.state = ActionState.DENIED
        raise LifecycleDeniedError(
            "Policy engine unavailable — fail-closed DENY",
            detail={"action_id": str(action.id)},
        ) from exc
```

### Partial Failure — Execute Succeeded, Seal Failed

This is the most dangerous partial failure in the kernel. See `_execute_then_seal()` and
`_alert_partial_failure()` above. The reconcile admin path re-attempts sealing without
re-executing:

```python
# core/lifecycle/admin.py
async def reconcile_unsealed_action(
    action_id: str,
    tenant_id: str,
    *,
    storage: StoragePort,
    ledger,
    event_bus,
) -> LedgerEntry:
    """
    Admin operation: re-attempt sealing an action stuck in HALTED after execute-then-seal failure.
    Does NOT re-execute. Records this reconciliation in its own governed audit event.
    """
    async with storage.transaction() as tx:
        action = await tx.get_action(action_id, tenant_id)

    if action.state != ActionState.HALTED:
        raise LifecycleInvalidTransitionError(
            f"reconcile only applies to HALTED actions, got {action.state.name}",
        )
    # Retrieve the execution result that was recorded before the seal failure
    recorded_exec_result = await storage.get_recorded_exec_result(action_id, tenant_id)
    if recorded_exec_result is None:
        raise LifecycleHaltedError(
            "Cannot reconcile: no recorded execution result found. "
            "Manual investigation required.",
        )
    eval_result = await storage.get_eval_result(action_id, tenant_id)
    entry = await ledger.seal(action, eval_result, recorded_exec_result)
    action.state = ActionState.SEALED
    async with storage.transaction() as tx:
        await tx.save_action(action)
    return entry
```

---

## Anti-Patterns

### Anti-pattern 1 — emit() failure un-seals the action

```python
# WRONG — if emit fails, reversing the seal destroys the audit record.
async def _emit(self, action, entry):
    try:
        await self._event_bus.publish(...)
    except Exception:
        # Catastrophic: this would un-seal a confirmed action.
        await self._ledger.rollback_seal(entry)  # NEVER
        action.state = ActionState.HALTED
        raise

# CORRECT — emit is best-effort. Sealed is sealed. Log the failure, move on.
async def _emit(self, action, entry):
    try:
        await self._event_bus.publish(...)
    except Exception as exc:
        logger.warning("Emit failed (non-fatal — action is sealed): %s", exc)
    action.state = ActionState.COMPLETED
```

### Anti-pattern 2 — Checking state with raw string comparison

```python
# WRONG — typo-prone, not exhaustive.
if action.state == "PENDING_APPROVAL":
    ...

# CORRECT — enum comparison. mypy catches typos at type-check time.
if action.state == ActionState.PENDING_APPROVAL:
    ...
```

### Anti-pattern 3 — Calling execute() before gate() (F-04 violation)

```python
# WRONG — bypasses evaluation and gate entirely.
async def fast_path(action, execute_fn):
    # "It's low-risk, skip the policy check for speed"
    return await execute_fn(action)

# CORRECT — there is no fast path. run() is the only path.
entry = await lifecycle_engine.run(action, execute_fn=execute_fn)
```

---

## Checklist Before Merging Any Lifecycle Change

- [ ] All state transitions use `_transition()` — no `action.state = X` outside that helper
- [ ] Every exception path sets correct terminal state before raising
- [ ] Idempotency check is the FIRST operation in `propose()` — before any workflow start
- [ ] `_execute()` guards against bypass: raises `LifecycleBypassAttemptError` if not APPROVED
- [ ] `_seal()` failure → HALTED + operator alert. Never silently mark EXECUTED
- [ ] Emit failure → log only. Never un-seal, never halt
- [ ] No direct DB, queue, or SDK imports in `core/lifecycle/`
- [ ] OTel span opened for every step; `Attrs.TENANT_ID` and `Attrs.ACTION_ID` set on every span
- [ ] Full type annotations on every method — mypy --strict passes
- [ ] Conformance test exists for concurrent idempotency scenario
- [ ] Replay: `LedgerEntry` records full payload, all policy versions, and all model outputs
