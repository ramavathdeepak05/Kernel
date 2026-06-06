"""Lifecycle spine behavior + the fail-closed / no-bypass / idempotency invariants.

Every fault test asserts the action ends DENIED or HALTED and that `execute` did not run when it must
not — a passing test that lets an action through under a fault is itself a defect (FAIL_OPEN_DETECTED).
"""

from __future__ import annotations

from core.lifecycle.engine import LifecycleEngine
from core.types import ActionState, ApprovalDecision, Decision

from tests.unit.lifecycle.fakes import (
    Counter,
    FakeActionRepository,
    FakeEvents,
    FakeHITL,
    FakeIdentity,
    FakeLedger,
    FakePolicy,
    make_action,
)


def _engine(
    *,
    policy: FakePolicy,
    hitl: FakeHITL | None = None,
    ledger: FakeLedger | None = None,
    events: FakeEvents | None = None,
    repo: FakeActionRepository | None = None,
    identity: FakeIdentity | None = None,
) -> tuple[LifecycleEngine, FakeActionRepository, FakeLedger, FakeEvents]:
    repo = repo or FakeActionRepository()
    ledger = ledger or FakeLedger()
    events = events or FakeEvents()
    engine = LifecycleEngine(
        repository=repo,
        policy=policy,
        hitl=hitl or FakeHITL(),
        ledger=ledger,
        events=events,
        identity=identity,
    )
    return engine, repo, ledger, events


async def test_allow_runs_full_lifecycle_to_completed() -> None:
    engine, _repo, ledger, events = _engine(policy=FakePolicy(decision=Decision.ALLOW))
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.COMPLETED
    assert body.count == 1
    assert len(ledger.sealed) == 1
    assert len(events.emitted) == 1


async def test_deny_never_executes() -> None:
    engine, _repo, ledger, _events = _engine(policy=FakePolicy(decision=Decision.DENY))
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.DENIED
    assert body.count == 0  # no-bypass: denied actions never reach execute
    assert len(ledger.sealed) == 0


async def test_require_approval_approved_completes() -> None:
    engine, _repo, ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.REQUIRE_APPROVAL, approvers=("role:risk_head",)),  # type: ignore[arg-type]
        hitl=FakeHITL(decision=ApprovalDecision.APPROVED),
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.COMPLETED
    assert body.count == 1
    assert len(ledger.sealed) == 1


async def test_require_approval_rejected_denies_without_execute() -> None:
    engine, _repo, _ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.REQUIRE_APPROVAL),
        hitl=FakeHITL(decision=ApprovalDecision.REJECTED),
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.DENIED
    assert body.count == 0


async def test_hitl_timeout_denies_never_auto_approves() -> None:
    engine, _repo, _ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.REQUIRE_APPROVAL),
        hitl=FakeHITL(decision=ApprovalDecision.TIMED_OUT),
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.DENIED  # fail-closed: timeout is never an approval
    assert body.count == 0


async def test_policy_exception_denies_fail_closed() -> None:
    engine, _repo, _ledger, _events = _engine(policy=FakePolicy(raise_exc=True))
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.DENIED
    assert body.count == 0


async def test_policy_returns_none_denies() -> None:
    engine, _repo, _ledger, _events = _engine(policy=FakePolicy(return_none=True))
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.DENIED
    assert body.count == 0


async def test_execute_failure_halts_and_does_not_seal() -> None:
    engine, _repo, ledger, _events = _engine(policy=FakePolicy(decision=Decision.ALLOW))
    body = Counter(raise_exc=True)
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.HALTED
    assert body.count == 1
    assert len(ledger.sealed) == 0


async def test_seal_failure_halts_never_completes() -> None:
    engine, _repo, ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.ALLOW), ledger=FakeLedger(raise_exc=True)
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.HALTED  # executed-but-unsealed is HALTED, never COMPLETED
    assert body.count == 1
    assert len(ledger.sealed) == 0


async def test_emit_failure_still_completes() -> None:
    engine, _repo, ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.ALLOW), events=FakeEvents(raise_exc=True)
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.COMPLETED  # emit is best-effort; sealed = governed
    assert len(ledger.sealed) == 1


async def test_hitl_dispatch_error_halts() -> None:
    engine, _repo, _ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.REQUIRE_APPROVAL),
        hitl=FakeHITL(raise_exc=True),
    )
    body = Counter()
    result = await engine.run(make_action(), body)
    assert result.state is ActionState.HALTED  # HITL infra failure → HALT
    assert body.count == 0


async def test_identity_failure_denies() -> None:
    engine, _repo, _ledger, _events = _engine(
        policy=FakePolicy(decision=Decision.ALLOW), identity=FakeIdentity(raise_exc=True)
    )
    from core.types import RequestContext

    body = Counter()
    result = await engine.run(make_action(), body, context=RequestContext())
    assert result.state is ActionState.DENIED
    assert body.count == 0


async def test_idempotency_duplicate_returns_existing_without_rerun() -> None:
    repo = FakeActionRepository()
    engine, _repo, ledger, _events = _engine(policy=FakePolicy(decision=Decision.ALLOW), repo=repo)
    body = Counter()
    first = await engine.run(make_action(), body)
    assert first.state is ActionState.COMPLETED
    assert body.count == 1
    # second submission, same idempotency key → returns existing, does NOT execute again
    second = await engine.run(make_action(), body)
    assert body.count == 1  # not re-run
    assert len(ledger.sealed) == 1  # not re-sealed
    assert second.id == first.id
