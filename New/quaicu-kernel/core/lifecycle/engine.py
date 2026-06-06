"""LifecycleEngine — orchestrates `propose → evaluate → gate → execute → seal → emit`.

Invariants this module enforces by construction (see the `quaicu-governed-lifecycle` skill contract):
- **No bypass (F-04):** `execute` is reachable only after `evaluate` (and `gate`, when required) pass.
  There is no public method that executes without evaluating.
- **Fail-closed (F-03):** any error/timeout/ambiguity → DENY (governance) or HALT (infra). Never proceed.
- **Seal before complete:** an action that executed but failed to seal is HALTED, never COMPLETED.
- **Idempotency:** a duplicate `(tenant, idempotency_key)` returns the existing action; it never re-runs.
- **Determinism:** the engine introduces no wall-clock or randomness into the decision path (the HITL
  poll loop is bounded by a count, not a clock).

`core/` purity: this module imports only `core.*` (ports, types, errors, lifecycle) and the stdlib.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.lifecycle.protocols import ActionRepository, EventBus, Ledger, PolicyEvaluator
from core.lifecycle.transitions import assert_transition
from core.ports import HITLPort, IdentityPort
from core.types import (
    Action,
    ActionState,
    ApprovalDecision,
    ApproverRef,
    Decision,
    EvaluationResult,
    RequestContext,
)

log = logging.getLogger("quaicu.lifecycle")

# The execute step: the governed body, returning the result recorded to the ledger.
ExecuteFn = Callable[[], Awaitable[Any]]


class LifecycleEngine:
    """Runs the governed-action lifecycle. One instance per process; dependencies are injected
    (no globals in core)."""

    def __init__(
        self,
        *,
        repository: ActionRepository,
        policy: PolicyEvaluator,
        hitl: HITLPort,
        ledger: Ledger,
        events: EventBus,
        identity: IdentityPort | None = None,
        max_poll_attempts: int = 1,
        poll_wait: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._repo = repository
        self._policy = policy
        self._hitl = hitl
        self._ledger = ledger
        self._events = events
        self._identity = identity
        # Bounded poll safety net. A real HITL adapter long-polls (blocks until a decision or its own
        # configured timeout); the count cap guarantees the loop terminates without a wall-clock.
        self._max_poll_attempts = max(1, max_poll_attempts)
        self._poll_wait = poll_wait

    # ── Public entry point ──────────────────────────────────────────────────────

    async def run(
        self,
        action: Action,
        execute_fn: ExecuteFn,
        *,
        context: RequestContext | None = None,
    ) -> Action:
        """Drive `action` through the full lifecycle, running `execute_fn` as the execute step.

        Returns the action in its final state (COMPLETED on success; DENIED/HALTED otherwise, or the
        pre-existing action on an idempotency hit). Never raises for an expected governance/infra
        outcome — the terminal state carries it.
        """
        # propose (identity + idempotency). proceed=False ⇒ stop and return (duplicate or denied).
        action, proceed = await self._propose(action, context)
        if not proceed:
            return action

        # evaluate
        action, evaluation = await self._evaluate(action)
        if evaluation is None:  # denied at evaluate
            return action

        # gate (only when a policy requires approval)
        approver: ApproverRef | None = None
        if evaluation.decision is Decision.REQUIRE_APPROVAL:
            action, approver = await self._gate(action, evaluation)
            if action.state is not ActionState.PENDING_APPROVAL and action.state in (
                ActionState.DENIED,
                ActionState.HALTED,
            ):
                return action

        # execute
        action, result = await self._execute(action, execute_fn)
        if action.state is ActionState.HALTED:
            return action

        # seal
        action, entry = await self._seal(action, evaluation, result, approver)
        if action.state is ActionState.HALTED:
            return action

        # emit (best-effort, after seal — never changes the outcome)
        await self._emit(action, entry)
        return action

    # ── Steps ───────────────────────────────────────────────────────────────────

    async def _propose(
        self, action: Action, context: RequestContext | None
    ) -> tuple[Action, bool]:
        # Idempotency: atomic insert. On conflict, return the existing action — never re-run it,
        # whatever state it is in.
        existing = await self._repo.insert_if_absent(action)
        if existing is not None:
            log.info(
                "idempotency hit — returning existing action %s (state=%s)",
                existing.id,
                existing.state.value,
            )
            return existing, False

        # Identity: the kernel takes identity from the host (IdentityPort). Failure → DENY.
        if context is not None and self._identity is not None:
            try:
                actor = await self._identity.resolve_actor(context=context, tenant=action.tenant)
            except Exception as exc:  # noqa: BLE001 — unresolved identity must fail closed
                denied = await self._deny(action, "identity unresolved — fail-closed", exc)
                return denied, False
            action = dataclasses.replace(action, actor=actor)

        return action, True

    async def _evaluate(self, action: Action) -> tuple[Action, EvaluationResult | None]:
        action = self._advance(action, ActionState.EVALUATING)
        await self._repo.update_state(action)
        try:
            evaluation = await self._policy.evaluate(action)
        except Exception as exc:  # noqa: BLE001 — any policy failure → DENY (fail-closed)
            return await self._deny(action, "policy evaluation failed — fail-closed", exc), None
        if evaluation is None:
            return await self._deny(action, "policy returned None — fail-closed"), None
        if evaluation.decision is Decision.DENY:
            return await self._deny(action, evaluation.reason or "policy denied"), None
        # allow or require_approval → continue (action stays EVALUATING; next step advances it)
        return action, evaluation

    async def _gate(
        self, action: Action, evaluation: EvaluationResult
    ) -> tuple[Action, ApproverRef | None]:
        action = self._advance(action, ActionState.PENDING_APPROVAL)
        await self._repo.update_state(action)
        try:
            handle = await self._hitl.request_approval(
                action=action, approvers=list(evaluation.approvers), tenant=action.tenant
            )
            decision = await self._poll_until_decided(handle)
        except Exception as exc:  # noqa: BLE001 — HITL infra failure → HALT (fail-closed)
            return await self._halt(action, "HITL port error — fail-closed halt", exc), None

        if decision is ApprovalDecision.APPROVED:
            # NOTE: the approving identity is not yet captured — `ApprovalDecision` is a status enum.
            # Recording WHO approved requires extending the frozen HITL result type; tracked as a
            # follow-up ADR (see BUILD_JOURNAL). Until then `approver` is None.
            return action, None
        # REJECTED or TIMED_OUT → fail-closed DENY (never auto-approve on timeout)
        return await self._deny(action, f"approval {decision.value.lower()}"), None

    async def _poll_until_decided(self, handle: Any) -> ApprovalDecision:
        attempts = 0
        while attempts < self._max_poll_attempts:
            decision = await self._hitl.poll(handle)
            if decision is not ApprovalDecision.PENDING:
                return decision
            attempts += 1
            if self._poll_wait is not None:
                await self._poll_wait()
        return ApprovalDecision.TIMED_OUT  # exhausted attempts → fail-closed

    async def _execute(self, action: Action, execute_fn: ExecuteFn) -> tuple[Action, Any]:
        action = self._advance(action, ActionState.EXECUTING)
        await self._repo.update_state(action)
        try:
            result = await execute_fn()
        except Exception as exc:  # noqa: BLE001 — execute body failure must HALT, never proceed
            return await self._halt(action, "execute failed", exc), None
        return action, result

    async def _seal(
        self,
        action: Action,
        evaluation: EvaluationResult,
        result: Any,
        approver: ApproverRef | None,
    ) -> tuple[Action, Any]:
        action = self._advance(action, ActionState.SEALING)
        await self._repo.update_state(action)
        try:
            entry = await self._ledger.seal(
                action=action, evaluation=evaluation, recorded_result=result, approver=approver
            )
        except Exception as exc:  # noqa: BLE001
            # CRITICAL: the state change happened but the ledger has no record. Halt + alert; the
            # action is NOT completed. A reconcile path re-attempts sealing without re-executing.
            halted = await self._halt(action, "ledger seal failed — executed but unsealed", exc)
            log.critical(
                "PARTIAL FAILURE: action %s executed but seal failed — manual reconcile required",
                action.id,
            )
            return halted, None
        action = self._advance(action, ActionState.SEALED)
        await self._repo.update_state(action)
        action = self._advance(action, ActionState.COMPLETED)
        await self._repo.update_state(action)
        return action, entry

    async def _emit(self, action: Action, entry: Any) -> None:
        try:
            await self._events.emit(action=action, entry=entry)
        except Exception as exc:  # noqa: BLE001 — emit is best-effort; outcome already sealed
            log.warning(
                "emit failed for action %s — outcome unchanged (already sealed): %s", action.id, exc
            )

    # ── Transition helpers ──────────────────────────────────────────────────────

    def _advance(self, action: Action, state: ActionState) -> Action:
        assert_transition(action.state, state)
        return action.with_state(state)

    async def _deny(self, action: Action, reason: str, cause: Exception | None = None) -> Action:
        denied = self._advance(action, ActionState.DENIED)
        await self._repo.update_state(denied)
        log.info("action %s DENIED: %s%s", action.id, reason, f" ({cause})" if cause else "")
        return denied

    async def _halt(self, action: Action, reason: str, cause: Exception | None = None) -> Action:
        halted = self._advance(action, ActionState.HALTED)
        await self._repo.update_state(halted)
        log.error("action %s HALTED: %s%s", action.id, reason, f" ({cause})" if cause else "")
        return halted
