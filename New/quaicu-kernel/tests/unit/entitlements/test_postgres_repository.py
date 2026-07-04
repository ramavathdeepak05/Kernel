"""Unit tests for PostgresEntitlementRepository — no real database required.

All asyncpg calls are patched with AsyncMock (mirrors test_postgres_policy.py) so these run in the
standard pytest-asyncio suite without any external services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.entitlements.postgres import PostgresEntitlementRepository, _row_to_plan
from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.errors import EntitlementPersistenceError
from core.types import TenantId

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


def _fake_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    # conn.transaction() is a SYNC call returning an async CM (real asyncpg semantics) — the
    # adapter wraps every op in a transaction so the RLS GUC (set_config) is transaction-local.
    txn_cm = MagicMock()
    txn_cm.__aenter__ = AsyncMock(return_value=None)
    txn_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn_cm)
    return pool


def _plan() -> CustomerPlan:
    return CustomerPlan(
        tenant_id=TenantId("acme"),
        tier=FeatureTier.BUSINESS,
        status=PlanStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
        billing_provider="stripe",
        billing_ref="sub_123",
        quota_overrides={"max_policies": 50},
    )


# ── Row mapper ───────────────────────────────────────────────────────────────


def test_row_to_plan_round_trip_jsonb_str() -> None:
    row = {
        "tenant_id": "acme",
        "tier": "ENTERPRISE",
        "status": "ACTIVE",
        "created_at": NOW,
        "updated_at": NOW,
        "billing_provider": "razorpay",
        "billing_ref": "sub_x",
        "quota_overrides": '{"max_actions_per_day": 100000}',  # asyncpg JSONB often arrives as str
    }
    plan = _row_to_plan(row)
    assert plan.tier is FeatureTier.ENTERPRISE
    assert plan.status is PlanStatus.ACTIVE
    assert plan.quota_overrides == {"max_actions_per_day": 100000}
    assert plan.billing_provider == "razorpay"


def test_row_to_plan_null_quota_overrides() -> None:
    row = {
        "tenant_id": "acme", "tier": "STARTER", "status": "ACTIVE",
        "created_at": NOW, "updated_at": NOW,
        "billing_provider": None, "billing_ref": None, "quota_overrides": None,
    }
    plan = _row_to_plan(row)
    assert plan.quota_overrides == {}
    assert plan.billing_provider is None


# ── save_plan ─────────────────────────────────────────────────────────────────


async def test_save_plan_executes_upsert() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    await repo.save_plan(_plan())
    # Two awaits: the RLS set_config, then the upsert (await_args = the last call).
    assert conn.execute.await_count == 2
    args = conn.execute.await_args.args
    # args[0] is the SQL; $1.. → tenant_id, tier, status, created_at, updated_at, provider, ref, qo
    assert args[1] == "acme"
    assert args[2] == "BUSINESS"
    assert args[3] == "ACTIVE"
    assert args[6] == "stripe"
    assert args[8] == '{"max_policies": 50}'  # quota_overrides serialised to JSON text


async def test_save_plan_wraps_errors() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=Exception("db down"))
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    with pytest.raises(EntitlementPersistenceError):
        await repo.save_plan(_plan())


# ── load_all ──────────────────────────────────────────────────────────────────


async def test_load_all_maps_rows() -> None:
    row = {
        "tenant_id": "acme", "tier": "BUSINESS", "status": "SUSPENDED",
        "created_at": NOW, "updated_at": NOW,
        "billing_provider": "stripe", "billing_ref": "sub_1", "quota_overrides": {},
    }
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[row])
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    plans = await repo.load_all()
    assert len(plans) == 1
    assert plans[0].status is PlanStatus.SUSPENDED
    assert plans[0].tier is FeatureTier.BUSINESS


# ── set_tier / set_status ─────────────────────────────────────────────────────


async def test_set_tier_raises_when_zero_rows() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 0")
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    with pytest.raises(EntitlementPersistenceError):
        await repo.set_tier(TenantId("missing"), FeatureTier.ENTERPRISE)


async def test_set_tier_ok_when_one_row() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    await repo.set_tier(TenantId("acme"), FeatureTier.ENTERPRISE)
    args = conn.execute.await_args.args
    assert args[1] == "acme"
    assert args[2] == "ENTERPRISE"


async def test_set_status_ok_when_one_row() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    repo = PostgresEntitlementRepository(dsn="postgresql://fake/fake")
    repo._pool = _fake_pool(conn)

    await repo.set_status(TenantId("acme"), PlanStatus.SUSPENDED)
    args = conn.execute.await_args.args
    assert args[2] == "SUSPENDED"


async def test_satisfies_entitlement_repository_protocol() -> None:
    from core.entitlements.repository import EntitlementRepository

    assert isinstance(
        PostgresEntitlementRepository(dsn="postgresql://fake/fake"), EntitlementRepository
    )
