"""End-to-end: the real CEL PolicyEngine wired into a Kernel via from_parts.

Proves the gap is closed — a Kernel can run on the real K·01 engine, an empty store fail-closed
DENYs, and authoring a policy through the SDK write-through primitive makes the action enforceable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from adapters.policy.memory import InMemoryPolicyRepository
from core.errors import LifecycleDeniedError
from core.policy.evaluator import PolicyEngine
from core.policy.model import ImpactReport, PolicyEnvelope, PolicyLifecycle
from core.policy.store import PolicyStore
from core.types import Actor, ActorId, ApproverRef, Decision, TenantId
from delivery.sdk.kernel import Kernel

from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeLedger

TENANT = TenantId("acme")
ACTOR = Actor(id=ActorId("alice"), tenant=TENANT, roles=("role:analyst",))


def _kernel(repo=None):
    store = PolicyStore(repository=repo)
    engine = PolicyEngine(store)
    kernel = Kernel.from_parts(
        tenant=TENANT,
        policy=engine,
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        policy_store=store,
        policy_repository=repo,
    )
    return kernel, store


def _allow_envelope() -> PolicyEnvelope:
    return PolicyEnvelope(
        id="p.allow-wire",
        version=1,
        governs="payments.wire",
        scope={"tenant": "*"},
        condition="true",
        decision=Decision.ALLOW,
        approvers=(),
        regulatory_refs=(),
        lifecycle=PolicyLifecycle.ACTIVATED,
    )


# ── Wiring ─────────────────────────────────────────────────────────────────────


def test_kernel_exposes_policy_store() -> None:
    kernel, _ = _kernel()
    assert kernel.has_policy_store is True
    assert kernel.policy_store is not None


async def test_empty_store_denies_governed_action() -> None:
    """The secure default: no policies → fail-closed DENY (PolicyNotFoundError → DENY)."""
    kernel, _ = _kernel()

    @kernel.guard(policy="payments.wire", action_type="payments.wire")
    async def wire(amount: int) -> str:
        return "sent"

    with pytest.raises(LifecycleDeniedError):
        async with kernel.actor_context(ACTOR):
            await wire(amount=100)


async def test_register_policy_then_action_completes() -> None:
    kernel, _ = _kernel()
    await kernel.register_policy(_allow_envelope())

    @kernel.guard(policy="payments.wire", action_type="payments.wire")
    async def wire(amount: int) -> str:
        return "sent"

    async with kernel.actor_context(ACTOR):
        result = await wire(amount=100)
    assert result == "sent"


# ── Durability via startup() hydrate ─────────────────────────────────────────


async def test_startup_hydrates_from_repository() -> None:
    repo = InMemoryPolicyRepository()
    await repo.save_envelope(_allow_envelope())  # persisted, ACTIVATED

    kernel, store = _kernel(repo=repo)
    # Before startup the fresh store is empty.
    assert store.lookup("payments.wire", "acme") == []

    await kernel.startup()  # hydrates + recompiles
    assert len(store.lookup("payments.wire", "acme")) == 1


async def test_register_policy_without_store_raises() -> None:
    from adapters.policy.always_allow import AlwaysAllowPolicyAdapter

    kernel = Kernel.from_parts(
        tenant=TENANT,
        policy=AlwaysAllowPolicyAdapter(),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
    )
    assert kernel.has_policy_store is False
    with pytest.raises(RuntimeError, match="No policy store"):
        await kernel.register_policy(_allow_envelope())
