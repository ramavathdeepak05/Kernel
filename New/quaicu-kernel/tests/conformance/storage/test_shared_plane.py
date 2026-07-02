"""Shared-durable-plane integration proofs (D0-5 / 5c) against a real Postgres.

The self-serve plane is ONE durable kernel serving STARTER + BUSINESS; the tier is a feature gate, not a
separate data store. These tests prove the two consequences against real Postgres:

  - **Horizontal-worker correctness** — idempotency + durability hold across separate adapter instances
    ("workers") sharing one DSN, so ``--workers > 1`` is safe (original D0-5 DoD; closes D0-1 Gap 1).
  - **Upgrade = feature unlock, not migration** — a tier flip is metadata-only (``quaicu_customer_plans``
    alone); the tenant's durable data (actions, policies) is untouched.

Skipped unless ``DATABASE_URL`` is set (run ``alembic upgrade head`` first). The KMS-signed ledger is
NOT exercised here, so no Cloud KMS is required.

    DATABASE_URL=postgresql://quaicu:quaicu-dev@127.0.0.1:5433/quaicu?sslmode=disable \\
        pytest tests/conformance/storage/test_shared_plane.py -m integration -v
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from adapters.entitlements.postgres import PostgresEntitlementRepository
from adapters.hitl.postgres_store import PostgresApprovalStore
from adapters.policy.postgres import PostgresPolicyRepository
from adapters.storage.postgres import PostgresStorageAdapter
from core.entitlements import CustomerPlan, FeatureTier, PlanStatus
from core.hitl.model import ApprovalRecord
from core.policy.model import PolicyEnvelope, PolicyLifecycle
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    ApproverRef,
    Decision,
    IdempotencyKey,
    TenantId,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping integration tests"
)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
TENANT = "test-shared-acme"  # all test rows use a 'test-%' tenant / id so cleanup is safe


def _action(ikey: str, state: ActionState = ActionState.PROPOSED) -> Action:
    return Action(
        id=ActionId(f"act-{ikey}"),
        type="loan.approve",
        payload={"amount": 5000},
        actor=Actor(id=ActorId("alice"), tenant=TenantId(TENANT), roles=("role:analyst",)),
        tenant=TenantId(TENANT),
        idempotency_key=IdempotencyKey(ikey),
        state=state,
        proposed_at=NOW,
    )


async def _wipe() -> None:
    a = PostgresStorageAdapter(dsn=DATABASE_URL)
    pool = await a._get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("ALTER TABLE quaicu_actions NO FORCE ROW LEVEL SECURITY")
            await conn.execute("SET LOCAL row_security = off")
            await conn.execute("DELETE FROM quaicu_actions WHERE tenant_id LIKE 'test-%'")
            await conn.execute("ALTER TABLE quaicu_actions FORCE ROW LEVEL SECURITY")
            await conn.execute("DELETE FROM quaicu_policies WHERE id LIKE 'test-%'")
            await conn.execute("DELETE FROM quaicu_customer_plans WHERE tenant_id LIKE 'test-%'")
            await conn.execute("DELETE FROM quaicu_approvals WHERE handle_id LIKE 'test-%'")
    await a.close()


@pytest.fixture
async def clean():
    await _wipe()
    yield
    await _wipe()


@pytest.mark.integration
@skip_no_db
async def test_idempotency_holds_across_workers(clean):
    """Two adapter instances = two workers on one DB. The same idempotency key never double-inserts,
    and a state change by one worker is visible to the other (durable, shared)."""
    worker_a = PostgresStorageAdapter(dsn=DATABASE_URL)
    worker_b = PostgresStorageAdapter(dsn=DATABASE_URL)
    try:
        action = _action("ikey-1")
        first = await worker_a.insert_if_absent(action)
        assert first is None  # newly inserted on worker A

        # Worker B sees the same key already present → returns the existing action, no second execute.
        dup = await worker_b.insert_if_absent(_action("ikey-1"))
        assert dup is not None
        assert str(dup.id) == str(action.id)

        # A state change on worker A is durable + visible to worker B (shared Postgres, not per-process).
        await worker_a.update_state(_action("ikey-1", state=ActionState.COMPLETED))
        seen = await worker_b.get_by_idempotency_key(TenantId(TENANT), IdempotencyKey("ikey-1"))
        assert seen is not None and seen.state is ActionState.COMPLETED
    finally:
        await worker_a.close()
        await worker_b.close()


@pytest.mark.integration
@skip_no_db
async def test_action_survives_a_restart(clean):
    """An action persisted by one process is read back by a fresh adapter (= after a pod restart)."""
    writer = PostgresStorageAdapter(dsn=DATABASE_URL)
    await writer.insert_if_absent(_action("ikey-restart"))
    await writer.close()  # process gone

    reader = PostgresStorageAdapter(dsn=DATABASE_URL)
    try:
        back = await reader.get_by_idempotency_key(TenantId(TENANT), IdempotencyKey("ikey-restart"))
        assert back is not None
        assert str(back.id) == "act-ikey-restart"
    finally:
        await reader.close()


@pytest.mark.integration
@skip_no_db
async def test_upgrade_is_metadata_only_and_data_survives(clean):
    """A STARTER→BUSINESS upgrade flips only the plan row; the tenant's durable policy is untouched —
    the durable proof that an upgrade is a feature unlock, not a data migration."""
    ents = PostgresEntitlementRepository(dsn=DATABASE_URL)
    policies = PostgresPolicyRepository(dsn=DATABASE_URL)
    try:
        # The tenant authors a policy (durable) while on STARTER.
        envelope = PolicyEnvelope(
            id="test-shared-pol-1",
            version=1,
            governs="payments.wire",
            scope={"tenant": TENANT},
            condition="true",
            decision=Decision.ALLOW,
            approvers=(),
            regulatory_refs=(),
            lifecycle=PolicyLifecycle.ACTIVATED,
        )
        await policies.save_envelope(envelope)
        await ents.save_plan(
            CustomerPlan(
                tenant_id=TenantId(TENANT),
                tier=FeatureTier.STARTER,
                status=PlanStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )

        # Upgrade: the only mutation is the plan's tier.
        await ents.set_tier(TenantId(TENANT), FeatureTier.BUSINESS)

        # A fresh repo (= a restarted/other worker) resolves the upgraded tier.
        ents2 = PostgresEntitlementRepository(dsn=DATABASE_URL)
        try:
            plan = next(p for p in await ents2.load_all() if str(p.tenant_id) == TENANT)
            assert plan.tier is FeatureTier.BUSINESS
        finally:
            await ents2.close()

        # The policy authored on STARTER is still present + unchanged — no migration moved it.
        loaded = [e for e in await policies.load_all() if e.id == "test-shared-pol-1"]
        assert len(loaded) == 1
        assert loaded[0].scope.get("tenant") == TENANT
        assert loaded[0].condition == "true"
    finally:
        await ents.close()
        await policies.close()


@pytest.mark.integration
@skip_no_db
async def test_approval_routing_metadata_survives_restart(clean):
    """A pending approval's routing metadata + signed resume link persist durably (D1-4): a fresh store
    (= restarted process) reads back the channel/target/resume link with full fidelity."""
    writer = PostgresApprovalStore(DATABASE_URL)
    writer.put(
        ApprovalRecord(
            handle_id="test-h-routing",
            action_id=ActionId("test-act-routing"),
            tenant=TenantId(TENANT),
            required_approvers=(ApproverRef("role:approver"),),
            requested_at=NOW,
            proposed_by=ActorId("maker"),
            notify_channel="email",
            notify_target="compliance@x.io",
            resume_link="https://api.x/v1/approvals/link/signed-token",
        )
    )
    # A fresh store instance = a restarted process reading the durable record.
    got = PostgresApprovalStore(DATABASE_URL).get("test-h-routing")
    assert got is not None
    assert got.notify_channel == "email"
    assert got.notify_target == "compliance@x.io"
    assert got.resume_link == "https://api.x/v1/approvals/link/signed-token"
