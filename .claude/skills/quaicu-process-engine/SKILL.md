---
name: quaicu-process-engine
description: |
  QUAICU K·06 Process Engine — durable workflow execution behind WorkflowPort. Two adapters:
  Postgres state-machine (sovereign/MVP, default first) and Temporal (dedicated/cloud). Use when
  building core/process/, adapters/workflow/postgres_statemachine.py, adapters/workflow/temporal.py,
  or any code that interacts with WorkflowPort. Enforces: workflow logic never leaks into core,
  all non-determinism behind recorded activities, replay-safe deterministic workflows, Postgres
  adapter ships first (unblocks MVP), Temporal adapter alongside. Trigger keywords: WorkflowPort,
  workflow, ProcessEngine, Temporal, postgres_statemachine, ProcessDef, WorkflowHandle, ProcessState,
  signal, durable, HITL_pause, rollback, K06, process, saga, compensation, dead_letter, watchdog,
  deadlock_retry, step_loop, workflow_duration, step_failure.
---

# QUAICU K·06 Process Engine

You are the process engine architect. K·06 provides durable state for the governed-action lifecycle:
it handles HITL pauses (K·03), survives restarts, enables incident rollback (K·12), and guarantees
replay-safe execution. This document is the complete implementation reference. Every section must
be implemented exactly.

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every workflow choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → HALT the workflow.

### Invariants — never violated
- ALWAYS interact via `WorkflowPort`. NEVER import `temporalio` or a DB driver in core/ (F-08).
- ALWAYS wrap every non-deterministic operation (model call, time, random, external read) in a recorded activity. Workflow bodies are pure/deterministic (F-09).
- ON replay ALWAYS reuse the recorded activity result. NEVER recompute it.
- ALWAYS select the adapter from `kernel.toml`. NEVER `if adapter == "temporal":` in core/ (F-11).
- HITL pause that times out → REJECTED (fail-closed). NEVER auto-approve on timeout (F-03).
- Rollback/compensation is itself a governed action through the full lifecycle (F-04). No out-of-band side effects.

### Decision table
| Situation | Do exactly this |
|---|---|
| Which adapter is default / ships first | Postgres state-machine (sovereign/MVP) |
| `start()` fails | raise `WorkflowPortError`; caller does not proceed |
| `signal()` fails | raise `WorkflowPortError`; gate is NOT considered applied |
| `state()` unreachable | treat as UNKNOWN → HALT (never assume completed/approved) |
| Need time/random/IO inside a workflow | move it into an activity and record the result |
| Multi-step action needs rollback | saga/compensation, each step a governed activity |

### Tie-break rules
- Workflow body vs activity? → anything non-deterministic or with a side effect is an ACTIVITY. Workflow stays pure.
- Unknown workflow state? → HALT, never optimistically continue.
- Which adapter to default to? → Postgres state-machine first; Temporal alongside for dedicated/cloud.

### Stop-and-apply triggers
- About to call `datetime.now()`/`random`/an SDK inside workflow code? → STOP, wrap in a recorded activity.
- About to branch on adapter type in core/? → STOP, it is config-selected.
- About to auto-resume a timed-out HITL pause? → STOP, that is REJECTED.

### Self-check
- [ ] core/ uses only WorkflowPort; no temporalio/DB imports.
- [ ] No raw clock/random/IO in workflow bodies — all in recorded activities.
- [ ] Replay reuses recorded results (no recompute).
- [ ] HITL timeout → rejected; unknown state → halt.
- [ ] Adapter chosen by config; Postgres adapter present.

## Frozen Decisions That Apply Here

| ADR | Rule |
|-----|------|
| F-09 | All non-determinism recorded as activities. Replay uses recorded results — never recomputes. |
| F-08 | WorkflowPort is the only interface core uses. No Temporal SDK or postgres in core/. |
| F-11 | Adapter selected by config (kernel.toml) — never by `if adapter == "temporal":` in core. |
| F-03 | HITL timeout → fail-closed (REJECTED, not auto-approved). |
| F-04 | No bypass — every action including rollback goes through the lifecycle. |

---

## Error Type Hierarchy

```python
# core/process/errors.py

class ProcessError(Exception):
    """Base for all Process Engine errors."""
    error_code: str = "PE_000"

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context

class WorkflowStartError(ProcessError):
    """Failed to start a workflow. Fail-closed — action lifecycle halts."""
    error_code = "PE_001"

class WorkflowStepError(ProcessError):
    """A step execution failed. May be retried per retry policy."""
    error_code = "PE_002"
    def __init__(self, message: str, step_name: str, attempt: int, **ctx):
        super().__init__(message, **ctx)
        self.step_name = step_name
        self.attempt = attempt

class WorkflowDeadlockError(ProcessError):
    """Postgres deadlock detected during step execution. Retry after jitter."""
    error_code = "PE_003"

class WorkflowDeadLetterError(ProcessError):
    """Step exhausted all retries and was sent to dead letter queue."""
    error_code = "PE_004"

class WorkflowStuckError(ProcessError):
    """Watchdog timer detected a workflow stuck in a step beyond its SLA."""
    error_code = "PE_005"

class WorkflowSignalError(ProcessError):
    """Signal delivery failed — workflow may be in wrong state."""
    error_code = "PE_006"

class WorkflowReplayError(ProcessError):
    """Replay detected non-determinism: live path diverges from recorded result."""
    error_code = "PE_007"

class WorkflowCompensationError(ProcessError):
    """Saga compensation step failed. Requires manual investigation."""
    error_code = "PE_008"

class WorkflowTenantIsolationError(ProcessError):
    """Cross-tenant workflow access attempted."""
    error_code = "PE_009"

class WorkflowNotFoundError(ProcessError):
    """Workflow handle refers to a non-existent or wrong-tenant workflow."""
    error_code = "PE_010"
```

---

## WorkflowPort (core depends on this — never on Temporal SDK or postgres directly)

```python
# core/ports/workflow.py
from __future__ import annotations
from typing import Protocol, Any
from dataclasses import dataclass, field


@dataclass
class StepDef:
    """Declaration of a single step in a process definition."""
    name: str
    timeout_seconds: int = 300
    max_retries: int = 3
    retry_backoff_base_seconds: float = 1.0
    compensation_step: str | None = None    # step to run if this one fails (saga)
    is_hitl: bool = False                   # True = durable pause for human signal
    hitl_timeout_hours: int = 48            # HITL expires → fail-closed (REJECTED)
    sla_seconds: int | None = None          # watchdog threshold (None = use timeout)


@dataclass
class ProcessDef:
    """
    Declarative process definition. The DSL for declaring steps and transitions.

    Example (governed action lifecycle):
        ProcessDef(
            name="governed_action",
            version=1,
            steps=[
                StepDef("evaluate",  timeout_seconds=30,  max_retries=3),
                StepDef("gate",      timeout_seconds=10,  max_retries=1,
                        is_hitl=True, hitl_timeout_hours=48),
                StepDef("execute",   timeout_seconds=300, max_retries=2,
                        compensation_step="compensate_execute"),
                StepDef("seal",      timeout_seconds=10,  max_retries=5),
                StepDef("emit",      timeout_seconds=5,   max_retries=3),
            ],
            transitions={
                "evaluate":             {"allow": "gate",    "deny": "TERMINAL_DENIED",
                                         "require_approval": "gate"},
                "gate":                 {"approved": "execute", "rejected": "TERMINAL_REJECTED",
                                         "timeout": "TERMINAL_REJECTED"},
                "execute":              {"ok": "seal",    "error": "DEAD_LETTER"},
                "seal":                 {"ok": "emit",    "error": "DEAD_LETTER"},
                "emit":                 {"ok": "TERMINAL_COMPLETED"},
                "compensate_execute":   {"ok": "TERMINAL_COMPENSATED",
                                         "error": "TERMINAL_COMPENSATION_FAILED"},
            },
        )
    """
    name: str
    version: int
    steps: list[StepDef]
    transitions: dict[str, dict[str, str]]  # step_name → {outcome → next_step | TERMINAL_*}
    # TERMINAL_ values: TERMINAL_COMPLETED, TERMINAL_DENIED, TERMINAL_REJECTED,
    #                   TERMINAL_COMPENSATED, TERMINAL_COMPENSATION_FAILED

    def step_by_name(self, name: str) -> StepDef | None:
        return next((s for s in self.steps if s.name == name), None)

    def next_step(self, current_step: str, outcome: str) -> str:
        """Returns next step name or TERMINAL_* string."""
        step_transitions = self.transitions.get(current_step, {})
        result = step_transitions.get(outcome)
        if result is None:
            raise ProcessError(
                f"No transition defined for step={current_step!r} outcome={outcome!r}",
                error_code="PE_011",
            )
        return result


@dataclass
class WorkflowHandle:
    workflow_id: str
    tenant_id: str
    adapter: str   # "postgres_statemachine" | "temporal"


@dataclass
class Signal:
    name: str       # e.g. "hitl_approved", "hitl_rejected", "cancel"
    payload: dict


@dataclass
class ProcessState:
    status: str             # "running" | "paused_hitl" | "completed" | "failed" |
                            # "cancelled" | "compensating" | "dead_letter"
    current_step: str
    history: list[dict]     # recorded transition events (append-only)
    workflow_id: str = ""
    tenant_id: str = ""
    started_at_ms: int = 0
    updated_at_ms: int = 0
    error: str | None = None


class WorkflowPort(Protocol):
    async def start(
        self,
        *,
        definition: ProcessDef,
        payload: dict,
        tenant: str,
    ) -> WorkflowHandle: ...

    async def signal(
        self,
        handle: WorkflowHandle,
        signal: Signal,
    ) -> None: ...

    async def state(
        self,
        handle: WorkflowHandle,
    ) -> ProcessState: ...

    async def cancel(
        self,
        handle: WorkflowHandle,
    ) -> None: ...
```

---

## Process Definition DSL (how to declare steps and transitions)

```python
# core/process/definitions.py
"""
Canonical process definitions for QUAICU governed actions.
These are DATA — they live in core/process/definitions.py and are loaded
by the adapters. They contain no business logic.

Naming convention for transitions:
  "ok"              → happy path continues
  "error"           → step failed after all retries
  "deny"            → policy denied the action
  "allow"           → policy allowed with no further gate
  "require_approval"→ policy requires human approval
  "approved"        → HITL approved
  "rejected"        → HITL rejected
  "timeout"         → HITL timed out → fail-closed → REJECTED
  TERMINAL_*        → terminal states (workflow stops)
"""
from core.ports.workflow import ProcessDef, StepDef

GOVERNED_ACTION_WORKFLOW = ProcessDef(
    name="governed_action",
    version=1,
    steps=[
        StepDef("evaluate",            timeout_seconds=30,  max_retries=3,
                sla_seconds=45),
        StepDef("gate",                timeout_seconds=10,  max_retries=1,
                is_hitl=True, hitl_timeout_hours=48, sla_seconds=172_800),
        StepDef("execute",             timeout_seconds=300, max_retries=2,
                compensation_step="compensate_execute", sla_seconds=360),
        StepDef("seal",                timeout_seconds=15,  max_retries=5,
                sla_seconds=30),
        StepDef("emit",                timeout_seconds=10,  max_retries=3,
                sla_seconds=20),
        StepDef("compensate_execute",  timeout_seconds=300, max_retries=2),
    ],
    transitions={
        "evaluate": {
            "allow":            "execute",    # no gate needed
            "deny":             "TERMINAL_DENIED",
            "require_approval": "gate",
            "error":            "TERMINAL_DENIED",   # fail-closed
        },
        "gate": {
            "approved":  "execute",
            "rejected":  "TERMINAL_REJECTED",
            "timeout":   "TERMINAL_REJECTED",   # fail-closed: timeout = no approval
            "cancelled": "TERMINAL_REJECTED",
        },
        "execute": {
            "ok":    "seal",
            "error": "compensate_execute",   # trigger saga compensation
        },
        "seal": {
            "ok":    "emit",
            "error": "DEAD_LETTER",
        },
        "emit": {
            "ok":    "TERMINAL_COMPLETED",
            "error": "TERMINAL_COMPLETED",   # emit failure is non-fatal (at-least-once delivery)
        },
        "compensate_execute": {
            "ok":    "TERMINAL_COMPENSATED",
            "error": "TERMINAL_COMPENSATION_FAILED",
        },
    },
)

STATE_RECONSTRUCTION_WORKFLOW = ProcessDef(
    name="state_reconstruction",
    version=1,
    steps=[
        StepDef("load_ledger_range",   timeout_seconds=60, max_retries=3),
        StepDef("replay_transitions",  timeout_seconds=300, max_retries=1),
        StepDef("emit_reconstructed",  timeout_seconds=10,  max_retries=3),
    ],
    transitions={
        "load_ledger_range":  {"ok": "replay_transitions", "error": "TERMINAL_FAILED"},
        "replay_transitions": {"ok": "emit_reconstructed", "error": "TERMINAL_FAILED"},
        "emit_reconstructed": {"ok": "TERMINAL_COMPLETED", "error": "TERMINAL_COMPLETED"},
    },
)
```

---

## Adapter 1: Postgres State Machine (build first — unblocks MVP)

### Postgres Schema

```sql
-- migrations/versions/K06_process_engine.sql
-- Per-tenant schema.

CREATE TABLE "tenant_{tenant_id}".workflow_events (
    id              BIGSERIAL PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    tenant_id       TEXT NOT NULL CHECK (tenant_id = '{tenant_id}'),
    event_type      TEXT NOT NULL,
        -- "workflow_started" | "step_scheduled" | "step_started" | "step_completed"
        -- | "step_failed" | "step_dead_lettered" | "signal_received" | "compensation_started"
        -- | "compensation_completed" | "workflow_completed" | "workflow_failed"
        -- | "activity_{name}" (recorded non-determinism)
    event_data      JSONB NOT NULL,
    step_name       TEXT,
    is_activity     BOOLEAN NOT NULL DEFAULT false,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON "tenant_{tenant_id}".workflow_events (workflow_id, id);
CREATE INDEX ON "tenant_{tenant_id}".workflow_events (workflow_id, step_name, is_activity)
    WHERE is_activity = true;

CREATE TABLE "tenant_{tenant_id}".workflow_status (
    workflow_id         TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL CHECK (tenant_id = '{tenant_id}'),
    definition_name     TEXT NOT NULL,
    definition_version  INT NOT NULL,
    status              TEXT NOT NULL,
    current_step        TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    error               TEXT
);

-- Dead letter queue
CREATE TABLE "tenant_{tenant_id}".workflow_dead_letter (
    id              BIGSERIAL PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    tenant_id       TEXT NOT NULL CHECK (tenant_id = '{tenant_id}'),
    step_name       TEXT NOT NULL,
    last_error      TEXT NOT NULL,
    attempt_count   INT NOT NULL,
    payload         JSONB NOT NULL,
    dead_lettered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,        -- NULL until manually resolved
    resolution      TEXT                -- "resubmitted" | "abandoned" | "compensated"
);
CREATE INDEX ON "tenant_{tenant_id}".workflow_dead_letter (workflow_id);
CREATE INDEX ON "tenant_{tenant_id}".workflow_dead_letter (dead_lettered_at)
    WHERE resolved_at IS NULL;

-- Watchdog tracking
CREATE TABLE "tenant_{tenant_id}".workflow_watchdog (
    workflow_id     TEXT NOT NULL,
    step_name       TEXT NOT NULL,
    sla_deadline    TIMESTAMPTZ NOT NULL,
    alerted         BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (workflow_id, step_name)
);
CREATE INDEX ON "tenant_{tenant_id}".workflow_watchdog (sla_deadline)
    WHERE alerted = false;
```

### Step Execution Loop with Deadlock Retry

```python
# adapters/workflow/postgres_statemachine.py
from __future__ import annotations
import asyncio
import random
import time
import uuid
from typing import Any, Callable, Coroutine
from opentelemetry import trace, metrics

from core.ports.workflow import (
    WorkflowPort, ProcessDef, WorkflowHandle, Signal, ProcessState, StepDef
)
from core.process.errors import (
    WorkflowStepError, WorkflowDeadlockError, WorkflowDeadLetterError,
    WorkflowStuckError, WorkflowReplayError, WorkflowNotFoundError,
    WorkflowCompensationError,
)

tracer = trace.get_tracer("quaicu.process.postgres_sm")
meter  = metrics.get_meter("quaicu.process.postgres_sm")

_workflow_duration = meter.create_histogram(
    "process.workflow.duration_ms",
    description="End-to-end workflow duration in ms",
    unit="ms",
)
_step_failure_ctr = meter.create_counter(
    "process.step.failures",
    description="Step failures by step_name and error_code",
)
_dlq_ctr = meter.create_counter(
    "process.dead_letter.total",
    description="Steps sent to dead letter queue",
)
_deadlock_ctr = meter.create_counter(
    "process.deadlock.retries",
    description="Postgres deadlock retries",
)
_hitl_timeout_ctr = meter.create_counter(
    "process.hitl.timeout",
    description="HITL timeouts (fail-closed)",
)

POSTGRES_DEADLOCK_SQLSTATE = "40P01"
DEADLOCK_MAX_RETRIES = 5
DEADLOCK_BASE_DELAY = 0.05   # 50ms


class PostgresStateMachineAdapter:
    """
    Implements WorkflowPort. Uses PostgreSQL for durability — no extra server required.

    Design principles:
    - Event-sourced: every state change is an append-only event.
    - workflow_status is a projection rebuilt from events on demand.
    - All non-deterministic results are recorded as activity events before returning.
    - On replay, recorded activity results are returned verbatim — never recomputed.
    - HITL timeout → fail-closed (REJECTED).
    - Failed steps → dead letter queue after max_retries.
    - Compensation (saga) triggered on execute failure.
    """

    def __init__(self, storage, step_registry, watchdog):
        self.storage = storage          # StoragePort
        self.step_registry = step_registry  # maps step_name → async callable
        self.watchdog = watchdog        # WatchdogTimer

    async def start(
        self,
        *,
        definition: ProcessDef,
        payload: dict,
        tenant: str,
    ) -> WorkflowHandle:
        """Start a new workflow. Returns handle immediately — execution is async."""
        with tracer.start_as_current_span(
            "process.start",
            attributes={"tenant_id": tenant, "definition": definition.name},
        ) as span:
            workflow_id = str(uuid.uuid4())
            first_step = definition.steps[0].name

            async with self.storage.transaction() as tx:
                await tx.insert_workflow_status(
                    workflow_id=workflow_id,
                    tenant_id=tenant,
                    definition_name=definition.name,
                    definition_version=definition.version,
                    status="running",
                    current_step=first_step,
                )
                await self._record_event(tx, workflow_id, tenant, "workflow_started", {
                    "definition": definition.name,
                    "version": definition.version,
                    "payload": payload,
                    "first_step": first_step,
                })

            handle = WorkflowHandle(
                workflow_id=workflow_id,
                tenant_id=tenant,
                adapter="postgres_statemachine",
            )
            span.set_attribute("process.workflow_id", workflow_id)

            # Schedule first step (async — returns immediately)
            asyncio.create_task(
                self._run_step_loop(handle, definition, payload, first_step)
            )
            return handle

    async def signal(self, handle: WorkflowHandle, signal: Signal) -> None:
        """Deliver a signal to a paused workflow (e.g., HITL decision)."""
        with tracer.start_as_current_span(
            "process.signal",
            attributes={
                "tenant_id": handle.tenant_id,
                "workflow_id": handle.workflow_id,
                "signal_name": signal.name,
            },
        ):
            await self._assert_tenant(handle)
            async with self.storage.transaction() as tx:
                await self._record_event(
                    tx, handle.workflow_id, handle.tenant_id,
                    f"signal_{signal.name}", signal.payload,
                )
                # Wake any step waiting on this signal
                await tx.notify_workflow_signal(handle.workflow_id, signal.name)

    async def state(self, handle: WorkflowHandle) -> ProcessState:
        """Return current process state, rebuilt from events."""
        await self._assert_tenant(handle)
        events = await self.storage.get_events(
            handle.workflow_id, handle.tenant_id
        )
        return self._replay_state(events, handle.workflow_id, handle.tenant_id)

    async def cancel(self, handle: WorkflowHandle) -> None:
        """Cancel a running or paused workflow. Triggers compensation if in execute step."""
        await self._assert_tenant(handle)
        current = await self.state(handle)
        if current.status in ("completed", "failed", "cancelled"):
            return
        await self.signal(handle, Signal("cancel", {"reason": "explicit_cancel"}))

    # -----------------------------------------------------------------------
    # Internal step execution loop
    # -----------------------------------------------------------------------

    async def _run_step_loop(
        self,
        handle: WorkflowHandle,
        definition: ProcessDef,
        initial_payload: dict,
        start_step: str,
    ) -> None:
        """
        Drive the state machine from start_step to a terminal state.
        Handles: retries, deadlock, HITL pause, compensation, dead letter queue.
        """
        t0 = time.monotonic()
        current_step_name = start_step
        payload = initial_payload

        while True:
            if current_step_name.startswith("TERMINAL_"):
                status = current_step_name.removeprefix("TERMINAL_").lower()
                await self._finalize_workflow(handle, status, t0)
                return

            if current_step_name == "DEAD_LETTER":
                await self._send_to_dead_letter(
                    handle, current_step_name, "Step failed after retries", 0, payload
                )
                await self._finalize_workflow(handle, "failed", t0)
                return

            step_def = definition.step_by_name(current_step_name)
            if step_def is None:
                await self._finalize_workflow(handle, "failed", t0)
                raise ProcessError(
                    f"Unknown step {current_step_name!r} in definition "
                    f"{definition.name!r}",
                    error_code="PE_012",
                )

            # Set watchdog for this step
            if step_def.sla_seconds:
                await self.watchdog.set(handle, current_step_name, step_def.sla_seconds)

            # Execute step with retry + deadlock handling
            try:
                outcome, result = await self._execute_step_with_retry(
                    handle, step_def, payload, definition
                )
                payload = {**payload, f"{current_step_name}_result": result}
            except WorkflowDeadLetterError as exc:
                await self._send_to_dead_letter(
                    handle, current_step_name, str(exc), step_def.max_retries, payload
                )
                # Check if this step has a compensation
                if step_def.compensation_step:
                    current_step_name = step_def.compensation_step
                    continue
                current_step_name = "TERMINAL_FAILED"
                continue

            # Clear watchdog
            await self.watchdog.clear(handle, current_step_name)

            # Update workflow status
            next_step = definition.next_step(current_step_name, outcome)
            async with self.storage.transaction() as tx:
                await tx.update_workflow_status(
                    handle.workflow_id,
                    handle.tenant_id,
                    current_step=next_step if not next_step.startswith("TERMINAL_") else None,
                    status="running" if not next_step.startswith("TERMINAL_") else "completed",
                )
                await self._record_event(tx, handle.workflow_id, handle.tenant_id,
                    "step_completed", {
                        "step": current_step_name,
                        "outcome": outcome,
                        "next_step": next_step,
                    }
                )

            current_step_name = next_step

    async def _execute_step_with_retry(
        self,
        handle: WorkflowHandle,
        step_def: StepDef,
        payload: dict,
        definition: ProcessDef,
    ) -> tuple[str, Any]:
        """
        Execute a step with retry (exponential backoff), deadlock retry, and HITL pause.
        Returns (outcome, result).
        Raises WorkflowDeadLetterError after max_retries exhausted.
        """
        if step_def.is_hitl:
            return await self._execute_hitl_step(handle, step_def, payload)

        last_exc = None
        delay = step_def.retry_backoff_base_seconds

        for attempt in range(1, step_def.max_retries + 2):  # +1 for initial attempt
            with tracer.start_as_current_span(
                "process.step.execute",
                attributes={
                    "tenant_id": handle.tenant_id,
                    "step_name": step_def.name,
                    "attempt": attempt,
                },
            ) as span:
                try:
                    outcome, result = await self._execute_single_step(
                        handle, step_def, payload, attempt
                    )
                    return outcome, result

                except WorkflowDeadlockError as exc:
                    _deadlock_ctr.add(1, {
                        "tenant_id": handle.tenant_id,
                        "step_name": step_def.name,
                    })
                    span.record_exception(exc)
                    if attempt > DEADLOCK_MAX_RETRIES:
                        raise
                    jitter = random.uniform(0, DEADLOCK_BASE_DELAY)
                    await asyncio.sleep(DEADLOCK_BASE_DELAY * (2 ** attempt) + jitter)
                    continue

                except WorkflowStepError as exc:
                    last_exc = exc
                    _step_failure_ctr.add(1, {
                        "tenant_id": handle.tenant_id,
                        "step_name": step_def.name,
                        "error_code": exc.error_code,
                    })
                    span.record_exception(exc)

                    if attempt > step_def.max_retries:
                        break

                    # Record the failure as an event before retrying
                    async with self.storage.transaction() as tx:
                        await self._record_event(
                            tx, handle.workflow_id, handle.tenant_id,
                            "step_failed", {
                                "step": step_def.name,
                                "attempt": attempt,
                                "error": str(exc),
                            }
                        )

                    # Exponential backoff with jitter
                    jitter = delay * 0.25 * (random.random() * 2 - 1)
                    await asyncio.sleep(max(0, delay + jitter))
                    delay *= 2.0

        raise WorkflowDeadLetterError(
            f"Step {step_def.name!r} exhausted {step_def.max_retries} retries. "
            f"Last error: {last_exc}",
            step_name=step_def.name,
            attempt=step_def.max_retries,
        )

    async def _execute_single_step(
        self,
        handle: WorkflowHandle,
        step_def: StepDef,
        payload: dict,
        attempt: int,
    ) -> tuple[str, Any]:
        """
        Execute one attempt of a step. Normalizes postgres deadlock exceptions.
        """
        step_fn = self.step_registry.get(step_def.name)
        if step_fn is None:
            raise ProcessError(
                f"No step function registered for {step_def.name!r}",
                error_code="PE_013",
            )

        try:
            result = await asyncio.wait_for(
                step_fn(payload, handle),
                timeout=step_def.timeout_seconds,
            )
            outcome = result.get("outcome", "ok")
            return outcome, result
        except asyncio.TimeoutError:
            raise WorkflowStepError(
                f"Step {step_def.name!r} timed out after {step_def.timeout_seconds}s",
                step_name=step_def.name,
                attempt=attempt,
            )
        except Exception as exc:
            # Detect postgres deadlock
            pg_code = getattr(getattr(exc, 'pgcode', None), 'sqlstate', None)
            if POSTGRES_DEADLOCK_SQLSTATE in str(exc) or pg_code == POSTGRES_DEADLOCK_SQLSTATE:
                raise WorkflowDeadlockError(
                    f"Postgres deadlock on step {step_def.name!r} attempt {attempt}",
                    step_name=step_def.name,
                )
            raise WorkflowStepError(
                f"Step {step_def.name!r} failed: {exc}",
                step_name=step_def.name,
                attempt=attempt,
            ) from exc

    # -----------------------------------------------------------------------
    # HITL pause
    # -----------------------------------------------------------------------

    async def _execute_hitl_step(
        self,
        handle: WorkflowHandle,
        step_def: StepDef,
        payload: dict,
    ) -> tuple[str, Any]:
        """
        Durable HITL pause. Workflow suspends until a signal arrives or timeout fires.
        Timeout → fail-closed (outcome = "timeout" → TERMINAL_REJECTED).
        """
        # Mark workflow as paused_hitl
        async with self.storage.transaction() as tx:
            await tx.update_workflow_status(
                handle.workflow_id, handle.tenant_id, status="paused_hitl"
            )
            await self._record_event(
                tx, handle.workflow_id, handle.tenant_id,
                "hitl_paused", {"step": step_def.name, "payload": payload}
            )

        deadline = time.monotonic() + step_def.hitl_timeout_hours * 3600

        while True:
            # Poll for signal with short-cycle sleep
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _hitl_timeout_ctr.add(1, {"tenant_id": handle.tenant_id,
                                           "step_name": step_def.name})
                async with self.storage.transaction() as tx:
                    await self._record_event(
                        tx, handle.workflow_id, handle.tenant_id,
                        "hitl_timeout", {"step": step_def.name}
                    )
                # Fail-closed: timeout = rejected
                return "timeout", {"reason": "hitl_timeout"}

            signal_event = await self.storage.poll_signal(
                handle.workflow_id,
                handle.tenant_id,
                timeout_seconds=min(remaining, 30),  # poll in 30s cycles
            )
            if signal_event is None:
                continue

            signal_name = signal_event["name"]
            if signal_name == "hitl_approved":
                async with self.storage.transaction() as tx:
                    await tx.update_workflow_status(
                        handle.workflow_id, handle.tenant_id, status="running"
                    )
                return "approved", signal_event.get("payload", {})
            elif signal_name in ("hitl_rejected", "cancel"):
                return "rejected", signal_event.get("payload", {})
            # Ignore unknown signals — continue waiting

    # -----------------------------------------------------------------------
    # Activity recording (non-determinism rule)
    # -----------------------------------------------------------------------

    async def record_activity(
        self,
        workflow_id: str,
        tenant_id: str,
        activity_name: str,
        execute_fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        """
        If this workflow_id + activity_name already has a recorded result → return it (replay path).
        Otherwise → execute fn, record result → return it (live path).

        This is the core of replay-safety. Any non-deterministic operation — model calls,
        external API, time, randomness — MUST go through this method.

        On replay, the recorded result is returned verbatim. The fn is NEVER called on replay.
        If live execution produces a different value than recorded, that is WorkflowReplayError
        (non-determinism violation — programming error, not a retry candidate).
        """
        existing = await self.storage.get_recorded_activity(workflow_id, activity_name, tenant_id)
        if existing is not None:
            # Replay path: return recorded result
            return existing

        # Live path: execute and record before returning
        result = await execute_fn()

        async with self.storage.transaction() as tx:
            await self._record_event(
                tx, workflow_id, tenant_id,
                f"activity_{activity_name}",
                {"result": result},
                is_activity=True,
                step_name=activity_name,
            )

        return result

    # -----------------------------------------------------------------------
    # Dead Letter Queue
    # -----------------------------------------------------------------------

    async def _send_to_dead_letter(
        self,
        handle: WorkflowHandle,
        step_name: str,
        error: str,
        attempts: int,
        payload: dict,
    ) -> None:
        """
        Move a permanently failed step to the dead letter queue.
        Emits an OTel event and alert. Requires manual resolution.
        """
        with tracer.start_as_current_span(
            "process.dead_letter",
            attributes={
                "tenant_id": handle.tenant_id,
                "workflow_id": handle.workflow_id,
                "step_name": step_name,
            },
        ):
            async with self.storage.transaction() as tx:
                await tx.insert_dead_letter(
                    workflow_id=handle.workflow_id,
                    tenant_id=handle.tenant_id,
                    step_name=step_name,
                    last_error=error,
                    attempt_count=attempts,
                    payload=payload,
                )
                await self._record_event(
                    tx, handle.workflow_id, handle.tenant_id,
                    "step_dead_lettered", {
                        "step": step_name,
                        "error": error,
                        "attempts": attempts,
                    }
                )
            _dlq_ctr.add(1, {
                "tenant_id": handle.tenant_id,
                "step_name": step_name,
            })

    # -----------------------------------------------------------------------
    # State replay
    # -----------------------------------------------------------------------

    def _replay_state(
        self,
        events: list[dict],
        workflow_id: str,
        tenant_id: str,
    ) -> ProcessState:
        """
        Rebuild current ProcessState by replaying all recorded events.
        NO live external calls in this method. Deterministic — same events → same state.
        """
        state = ProcessState(
            status="running",
            current_step="",
            history=[],
            workflow_id=workflow_id,
            tenant_id=tenant_id,
        )
        for event in events:
            state = self._apply_event(state, event)
        return state

    def _apply_event(self, state: ProcessState, event: dict) -> ProcessState:
        etype = event["event_type"]
        data = event["event_data"]
        history = state.history + [event]

        if etype == "workflow_started":
            return ProcessState(
                status="running",
                current_step=data.get("first_step", ""),
                history=history,
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
            )
        if etype == "step_completed":
            return ProcessState(
                status="running",
                current_step=data.get("next_step", ""),
                history=history,
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
            )
        if etype == "hitl_paused":
            return ProcessState(
                status="paused_hitl",
                current_step=data.get("step", state.current_step),
                history=history,
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
            )
        if etype in ("workflow_completed", "workflow_failed", "workflow_cancelled",
                     "workflow_compensated"):
            return ProcessState(
                status=etype.replace("workflow_", ""),
                current_step="",
                history=history,
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
            )
        if etype == "step_failed":
            return ProcessState(
                status="running",  # may retry
                current_step=state.current_step,
                history=history,
                error=data.get("error"),
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
            )
        # Unknown event types: carry state forward (forward-compatible)
        return ProcessState(
            status=state.status,
            current_step=state.current_step,
            history=history,
            workflow_id=state.workflow_id,
            tenant_id=state.tenant_id,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    async def _assert_tenant(self, handle: WorkflowHandle) -> None:
        """Verify the handle's tenant_id matches the stored workflow's tenant_id."""
        stored = await self.storage.get_workflow_tenant(handle.workflow_id)
        if stored is None:
            raise WorkflowNotFoundError(
                f"Workflow {handle.workflow_id!r} not found",
                workflow_id=handle.workflow_id,
            )
        if stored != handle.tenant_id:
            raise WorkflowTenantIsolationError(
                f"Cross-tenant access: handle.tenant_id={handle.tenant_id!r} "
                f"!= stored tenant={stored!r}",
                workflow_id=handle.workflow_id,
            )

    async def _record_event(
        self,
        tx,
        workflow_id: str,
        tenant_id: str,
        event_type: str,
        event_data: dict,
        is_activity: bool = False,
        step_name: str | None = None,
    ) -> None:
        await tx.insert_workflow_event(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            event_type=event_type,
            event_data=event_data,
            is_activity=is_activity,
            step_name=step_name,
        )

    async def _finalize_workflow(
        self,
        handle: WorkflowHandle,
        status: str,
        t0: float,
    ) -> None:
        duration_ms = int((time.monotonic() - t0) * 1000)
        async with self.storage.transaction() as tx:
            await tx.update_workflow_status(
                handle.workflow_id, handle.tenant_id,
                status=status, current_step=None, completed_at="now()"
            )
            await self._record_event(
                tx, handle.workflow_id, handle.tenant_id,
                f"workflow_{status}", {"duration_ms": duration_ms}
            )
        _workflow_duration.record(duration_ms, {
            "tenant_id": handle.tenant_id,
            "status": status,
        })
```

---

## Saga / Compensation Pattern

When a multi-step workflow fails partway through, compensation steps undo previously completed
work in reverse order. Compensation itself is a governed action — it appears in the ledger.

```python
# core/process/saga.py
"""
Saga compensation for multi-step rollback.

Pattern:
- Each step that has side effects declares a compensation_step in StepDef.
- On step failure (after retries), the Process Engine triggers compensation.
- Compensation steps run in reverse order of the completed forward steps.
- Compensation is recorded as events — it is auditable and replay-safe.
- If compensation itself fails → TERMINAL_COMPENSATION_FAILED (manual intervention).

Compensation steps MUST be idempotent — they may be called more than once.
Compensation steps MUST NOT re-execute the forward step — only undo it.
Compensation steps MUST be side-effect-free on replay (use record_activity).

Example:
  Forward:      evaluate → gate → execute (disbursement created) → seal → emit
  On execute failure:     compensate_execute (cancel disbursement) → TERMINAL_COMPENSATED

The compensation entry in the ledger records:
  action_type = "quaicu.lifecycle.compensation"
  payload = { original_action_id, original_step, reason }
  This ensures the audit trail shows what was undone and why.
"""

from core.ports.workflow import ProcessDef, StepDef


def build_compensation_sequence(
    definition: ProcessDef,
    completed_steps: list[str],
    failed_step: str,
) -> list[str]:
    """
    Given the list of steps completed before the failure, return the compensation
    steps to run in reverse order.

    Only steps that declared a compensation_step are included.
    """
    compensation_seq: list[str] = []
    # Walk completed steps in reverse (most-recently-completed first)
    for step_name in reversed(completed_steps):
        if step_name == failed_step:
            continue
        step_def = definition.step_by_name(step_name)
        if step_def and step_def.compensation_step:
            compensation_seq.append(step_def.compensation_step)
    return compensation_seq
```

---

## Adapter 2: Temporal (dedicated/cloud tier)

```python
# adapters/workflow/temporal.py
# Imports temporalio SDK HERE ONLY — never in core/
from __future__ import annotations
from datetime import timedelta
import uuid
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import workflow, activity

from core.ports.workflow import WorkflowPort, ProcessDef, WorkflowHandle, Signal, ProcessState
from core.process.errors import WorkflowNotFoundError, WorkflowTenantIsolationError


class TemporalAdapter:
    """
    Implements WorkflowPort using Temporal.

    Temporal's execution model IS deterministic replay — this constraint is native.
    Workflow code MUST be deterministic: no direct time, random, or I/O calls.
    All non-determinism behind @activity decorators.

    HITL: implemented via Temporal signals (workflow.wait_condition or asyncio.Event).
    Signal handler updates an instance variable; wait_condition checks it.
    """

    def __init__(self, client: Client, task_queue_prefix: str = "quaicu"):
        self._client = client
        self._task_queue_prefix = task_queue_prefix

    def _task_queue(self, tenant: str) -> str:
        return f"{self._task_queue_prefix}-{tenant}"

    async def start(
        self,
        *,
        definition: ProcessDef,
        payload: dict,
        tenant: str,
    ) -> WorkflowHandle:
        workflow_id = f"{tenant}-{uuid.uuid4()}"
        handle = await self._client.start_workflow(
            definition.name,
            payload,
            id=workflow_id,
            task_queue=self._task_queue(tenant),
        )
        return WorkflowHandle(
            workflow_id=handle.id,
            tenant_id=tenant,
            adapter="temporal",
        )

    async def signal(self, handle: WorkflowHandle, signal: Signal) -> None:
        wf = self._client.get_workflow_handle(handle.workflow_id)
        await wf.signal(signal.name, signal.payload)

    async def state(self, handle: WorkflowHandle) -> ProcessState:
        wf = self._client.get_workflow_handle(handle.workflow_id)
        try:
            desc = await wf.describe()
        except Exception as exc:
            raise WorkflowNotFoundError(
                f"Temporal workflow {handle.workflow_id!r} not found: {exc}",
                workflow_id=handle.workflow_id,
            ) from exc

        status_map = {
            "RUNNING": "running",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
            "TIMED_OUT": "failed",
        }
        raw_status = desc.status.name if desc.status else "RUNNING"
        return ProcessState(
            status=status_map.get(raw_status, "running"),
            current_step="",   # Temporal doesn't expose current activity in describe
            history=[],        # Full history available via history API if needed
            workflow_id=handle.workflow_id,
            tenant_id=handle.tenant_id,
        )

    async def cancel(self, handle: WorkflowHandle) -> None:
        wf = self._client.get_workflow_handle(handle.workflow_id)
        await wf.cancel()


# ---------------------------------------------------------------------------
# Temporal workflow implementation (adapters/workflow/temporal_workflows.py)
# ---------------------------------------------------------------------------

@workflow.defn
class GovernedActionWorkflow:
    """
    Temporal workflow for the governed action lifecycle.

    Rules:
    - NO direct time.time() or datetime.now() — use workflow.now()
    - NO direct random, uuid4, or external I/O
    - ALL non-determinism behind @activity decorators
    - HITL pause uses workflow.wait_condition with timeout (fail-closed)
    - Compensation triggered via signal or on execute failure
    """

    def __init__(self):
        self._hitl_decision: dict | None = None
        self._cancelled = False

    @workflow.run
    async def run(self, payload: dict) -> dict:
        # Activity 1: Evaluate
        eval_result = await workflow.execute_activity(
            evaluate_action_activity,
            payload,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_default_retry_policy(),
        )

        decision = eval_result.get("decision")

        if decision == "deny":
            return {"state": "TERMINAL_DENIED", "eval_result": eval_result}

        if decision == "require_approval":
            # Durable HITL pause — wait for signal or timeout
            hitl_reached = await workflow.wait_condition(
                lambda: self._hitl_decision is not None,
                timeout=timedelta(hours=48),
            )
            if not hitl_reached or self._hitl_decision is None:
                # Timeout — fail-closed
                return {"state": "TERMINAL_REJECTED", "reason": "hitl_timeout"}
            if not self._hitl_decision.get("approved"):
                return {"state": "TERMINAL_REJECTED",
                        "reason": "hitl_rejected",
                        "approver": self._hitl_decision.get("approver")}

        if self._cancelled:
            return {"state": "TERMINAL_REJECTED", "reason": "cancelled"}

        # Activity 2: Execute
        try:
            exec_result = await workflow.execute_activity(
                execute_action_activity,
                {**payload, "eval_result": eval_result},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_execute_retry_policy(),
            )
        except Exception as exc:
            # Execute failed — trigger compensation
            await workflow.execute_activity(
                compensate_action_activity,
                {**payload, "reason": str(exc)},
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_default_retry_policy(),
            )
            return {"state": "TERMINAL_COMPENSATED", "reason": str(exc)}

        # Activity 3: Seal
        seal_result = await workflow.execute_activity(
            seal_action_activity,
            {**payload, "eval_result": eval_result, "exec_result": exec_result},
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=_seal_retry_policy(),
        )

        # Activity 4: Emit
        await workflow.execute_activity(
            emit_action_activity,
            {**payload, "seal_result": seal_result},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_default_retry_policy(),
        )

        return {"state": "TERMINAL_COMPLETED", "seal_result": seal_result}

    @workflow.signal
    async def hitl_decision(self, payload: dict) -> None:
        """Signal handler for HITL approve/reject decisions."""
        self._hitl_decision = payload

    @workflow.signal
    async def cancel(self, payload: dict) -> None:
        """Signal handler for workflow cancellation."""
        self._cancelled = True
        if self._hitl_decision is None:
            # Unblock wait_condition
            self._hitl_decision = {"approved": False, "reason": "cancelled"}

    @workflow.query
    def current_state(self) -> dict:
        """Query handler — returns current workflow state without side effects."""
        return {
            "hitl_pending": self._hitl_decision is None,
            "cancelled": self._cancelled,
        }


def _default_retry_policy():
    from temporalio.common import RetryPolicy
    return RetryPolicy(
        maximum_attempts=3,
        initial_interval=timedelta(seconds=1),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=30),
    )


def _execute_retry_policy():
    from temporalio.common import RetryPolicy
    return RetryPolicy(
        maximum_attempts=2,
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        non_retryable_error_types=["BusinessRuleViolation", "ConsentDenied"],
    )


def _seal_retry_policy():
    from temporalio.common import RetryPolicy
    # Seal is idempotent — retry aggressively
    return RetryPolicy(
        maximum_attempts=5,
        initial_interval=timedelta(milliseconds=500),
        backoff_coefficient=2.0,
    )


# Activity stubs — implementations live in core/ behind ports
@activity.defn
async def evaluate_action_activity(payload: dict) -> dict: ...

@activity.defn
async def execute_action_activity(payload: dict) -> dict: ...

@activity.defn
async def seal_action_activity(payload: dict) -> dict: ...

@activity.defn
async def emit_action_activity(payload: dict) -> dict: ...

@activity.defn
async def compensate_action_activity(payload: dict) -> dict: ...
```

---

## Watchdog Timer for Stuck Workflows

```python
# core/process/watchdog.py
"""
Watchdog timer for stuck workflows.

A step is "stuck" if it exceeds its SLA. The watchdog:
1. Records a "step_sla_breach" event to the workflow.
2. Emits an OTel alert span.
3. If the step is a HITL step and has timed out its SLA:
   - Does NOT automatically reject (HITL has its own timeout logic).
   - Alerts operators so they can follow up.
4. For non-HITL steps: after SLA breach + grace period, escalates to dead letter.

The watchdog runs as a background ARQ/Dramatiq job, not in the hot path.
"""
import time
from opentelemetry import trace

tracer = trace.get_tracer("quaicu.process.watchdog")
meter  = metrics.get_meter("quaicu.process.watchdog")
_watchdog_alerts = meter.create_counter(
    "process.watchdog.alerts",
    description="SLA breach alerts fired",
)


class WatchdogTimer:
    def __init__(self, storage):
        self.storage = storage

    async def set(
        self,
        handle: WorkflowHandle,
        step_name: str,
        sla_seconds: int,
    ) -> None:
        """Register a watchdog deadline for a step."""
        import datetime
        deadline = (
            datetime.datetime.utcnow()
            + datetime.timedelta(seconds=sla_seconds)
        )
        await self.storage.upsert_watchdog(
            handle.workflow_id, handle.tenant_id, step_name, deadline
        )

    async def clear(self, handle: WorkflowHandle, step_name: str) -> None:
        """Remove watchdog for a completed step."""
        await self.storage.delete_watchdog(handle.workflow_id, step_name)

    async def check_all(self, tenant_id: str) -> list[dict]:
        """
        Called by background job. Returns list of breached watchdog entries.
        Emits OTel spans and alerts for each breach.
        """
        breached = await self.storage.get_overdue_watchdogs(tenant_id)
        for entry in breached:
            with tracer.start_as_current_span(
                "process.watchdog.sla_breach",
                attributes={
                    "tenant_id": tenant_id,
                    "workflow_id": entry["workflow_id"],
                    "step_name": entry["step_name"],
                    "overdue_seconds": entry["overdue_seconds"],
                },
            ):
                _watchdog_alerts.add(1, {
                    "tenant_id": tenant_id,
                    "step_name": entry["step_name"],
                })
                # Record breach event
                async with self.storage.transaction() as tx:
                    await tx.insert_workflow_event(
                        workflow_id=entry["workflow_id"],
                        tenant_id=tenant_id,
                        event_type="step_sla_breach",
                        event_data=entry,
                    )
                    await tx.mark_watchdog_alerted(
                        entry["workflow_id"], entry["step_name"]
                    )
        return breached
```

---

## Incident Rollback (K·12 integration)

```python
# core/process/rollback.py
"""
Incident rollback via state reconstruction replay.

Three replay modes (§3.13) — all side-effect-free:
1. State reconstruction — rebuild institutional state as of ledger_seq = target_seq.
2. Decision audit replay — re-derive WHY a past action was decided as it was,
   using policy versions and recorded inputs at the time.
3. Counterfactual (Sandbox K·13) — run historical actions against candidate policies.

CRITICAL: replay NEVER re-executes external effects.
- Never re-disbursees funds.
- Never re-sends notifications.
- Never re-calls models (uses recorded model outputs from ledger).
- Never re-triggers HITL (replay is read-only).

The state reconstruction workflow reads ledger events and applies transitions
from recorded evaluation/execution results. It does not call K·01, K·05, or any
external service — only reads from the immutable ledger.
"""

async def rollback_to_seq(
    tenant_id: str,
    target_seq: int,
    workflow_port: WorkflowPort,
) -> WorkflowHandle:
    """
    Start a state reconstruction workflow targeting ledger_seq = target_seq.
    Returns the handle so callers can poll state().

    This triggers a governed action of type "quaicu.lifecycle.rollback" — it
    is recorded in the ledger like any other governed action.
    """
    from core.process.definitions import STATE_RECONSTRUCTION_WORKFLOW

    handle = await workflow_port.start(
        definition=STATE_RECONSTRUCTION_WORKFLOW,
        payload={
            "tenant_id": tenant_id,
            "target_seq": target_seq,
            "mode": "state_reconstruction",
        },
        tenant=tenant_id,
    )
    return handle
```

---

## Anti-Patterns Section

### Anti-Pattern 1: Non-determinism in workflow code (Temporal)

```python
# WRONG — calling time.time() directly in workflow breaks deterministic replay
@workflow.run
async def run(self, payload: dict) -> dict:
    now = time.time()  # NON-DETERMINISTIC — different value on each replay run
    if now > some_deadline:
        return {"state": "expired"}

# CORRECT — use workflow.now() (Temporal) or record as an activity
@workflow.run
async def run(self, payload: dict) -> dict:
    now = workflow.now()  # deterministic within workflow — Temporal handles replay
```

### Anti-Pattern 2: Re-executing external effects on replay (Postgres SM)

```python
# WRONG — calling the model again on replay defeats the non-determinism rule
async def execute_step(payload):
    # This calls the model EVERY time — on replay it will re-call the model
    # and may get a different response, breaking replay fidelity
    response = await inference_port.generate(prompt=build_prompt(payload), ...)
    return {"outcome": "ok", "model_response": response.content}

# CORRECT — use record_activity so replay returns the recorded response
async def execute_step(payload, handle):
    response = await sm_adapter.record_activity(
        handle.workflow_id, handle.tenant_id,
        "model_call",
        lambda: inference_port.generate(prompt=build_prompt(payload), ...),
    )
    return {"outcome": "ok", "model_response": response.content}
```

### Anti-Pattern 3: Auto-approving on HITL timeout

```python
# WRONG — timeout grants approval — governance bypass
async def wait_for_hitl(handle, timeout_hours):
    try:
        return await asyncio.wait_for(poll_signal(handle), timeout=timeout_hours * 3600)
    except asyncio.TimeoutError:
        return {"approved": True}  # catastrophic bug — fail-closed violation

# CORRECT — timeout = rejected (fail-closed)
    except asyncio.TimeoutError:
        return "timeout"  # transitions to TERMINAL_REJECTED
```

### Anti-Pattern 4: Importing Temporal SDK in core/

```python
# WRONG — violates F-08; core depends on a concrete adapter
# core/process/lifecycle.py
from temporalio.client import Client  # NEVER in core/

# CORRECT — core only uses WorkflowPort
# core/process/lifecycle.py
from core.ports.workflow import WorkflowPort  # the only import
```

### Anti-Pattern 5: Using wall-clock for step ordering in Postgres SM

```python
# WRONG — clock skew can reorder events incorrectly
ORDER BY recorded_at  -- unreliable if clock drifts

# CORRECT — order by BIGSERIAL id (monotonic, assigned by DB)
ORDER BY id ASC  -- authoritative ordering
```

### Anti-Pattern 6: Swallowing deadlock errors without retry

```python
# WRONG — silently marks step as failed instead of retrying the serialization conflict
try:
    await step_fn(payload)
except Exception:
    await record_failure(...)  # loses the deadlock context; no retry

# CORRECT — detect deadlock SQLSTATE and retry with jitter
except Exception as exc:
    if POSTGRES_DEADLOCK_SQLSTATE in str(exc):
        raise WorkflowDeadlockError(...)  # caller retries with backoff
    raise WorkflowStepError(...)
```

---

## OTel Instrumentation Summary

Every significant operation emits spans and metrics. Span names follow `process.<noun>.<verb>`.

| Span / Metric | Type | Key Attributes |
|---|---|---|
| `process.start` | Span | `tenant_id`, `definition`, `workflow_id` |
| `process.signal` | Span | `tenant_id`, `workflow_id`, `signal_name` |
| `process.step.execute` | Span | `tenant_id`, `step_name`, `attempt` |
| `process.dead_letter` | Span | `tenant_id`, `workflow_id`, `step_name` |
| `process.watchdog.sla_breach` | Span + Alert | `tenant_id`, `workflow_id`, `step_name`, `overdue_seconds` |
| `process.workflow.duration_ms` | Histogram | `tenant_id`, `status` |
| `process.step.failures` | Counter | `tenant_id`, `step_name`, `error_code` |
| `process.dead_letter.total` | Counter | `tenant_id`, `step_name` |
| `process.deadlock.retries` | Counter | `tenant_id`, `step_name` |
| `process.hitl.timeout` | Counter | `tenant_id`, `step_name` |
| `process.watchdog.alerts` | Counter | `tenant_id`, `step_name` |

---

## Checklist Before Merging Any Process Engine Change

- [ ] Workflow code contains NO direct `time.time()`, `random`, `uuid4()`, or external I/O
- [ ] All non-deterministic results recorded via `record_activity()` before returning
- [ ] On replay: `record_activity()` returns stored result — `execute_fn` is NOT called
- [ ] HITL timeout → `"timeout"` outcome → `TERMINAL_REJECTED` (never auto-approved)
- [ ] HITL timeout duration from `StepDef.hitl_timeout_hours` — not hardcoded
- [ ] Postgres deadlock (`40P01`) detected and retried with jitter — not treated as step failure
- [ ] Failed steps → dead letter queue after `StepDef.max_retries` — not silently dropped
- [ ] Saga compensation triggered in `StepDef.compensation_step` — tested for multi-step rollback
- [ ] `_replay_state()` rebuilds state with no live calls — deterministic for identical event list
- [ ] Watchdog timer set on step start, cleared on step completion — background job checks breaches
- [ ] `WorkflowPort` is the only interface `core/` uses — no Temporal SDK or asyncpg in `core/`
- [ ] Temporal adapter: all non-determinism behind `@activity.defn` decorators
- [ ] Temporal HITL: `@workflow.signal` handler sets `_hitl_decision`; `wait_condition` checks it
- [ ] Rollback (K·12) uses `STATE_RECONSTRUCTION_WORKFLOW` — never re-executes external effects
- [ ] Tenant isolation asserted on every `signal()` and `state()` call
- [ ] OTel spans emitted for start, signal, step execute, dead letter, watchdog, finalize
- [ ] `process.workflow.duration_ms` histogram and `process.step.failures` counter wired up
- [ ] ProcessDef declares all TERMINAL_ outcomes — no undefined transitions possible
- [ ] `ProcessDef.next_step()` raises on missing transition (fail-closed — no silent skip)
