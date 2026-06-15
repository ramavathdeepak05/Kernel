"""PostgresEntitlementRepository — durable, asyncpg-backed customer-plan persistence (ADR-0009 / WS-C).

Implements the `EntitlementRepository` Protocol structurally on a single asyncpg connection pool (one
pool per adapter instance, created lazily on first use). Mirrors `adapters/policy/postgres.py`.

Table (see migration 005_create_entitlement_tables.py):
  quaicu_customer_plans  — one row per tenant; the authoritative commercial plan.

Fail-closed contract:
  All asyncpg exceptions are caught and re-raised as `EntitlementPersistenceError`. Writes use
  INSERT … ON CONFLICT DO UPDATE so re-persisting the same tenant is idempotent — a re-delivered
  billing webhook never corrupts the durable plan.

Wired in via `EntitlementStore(repository=…)`: the store keeps the hot-path read cache, and the
billing engine's `*_persisted` mutations write through to here. `load_all()` rehydrates the cache at
startup so a redeploy resolves the same tiers.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg

from core.entitlements.model import CustomerPlan, FeatureTier, PlanStatus
from core.errors import EntitlementPersistenceError
from core.types import TenantId

# ── SQL ─────────────────────────────────────────────────────────────────────

_UPSERT_PLAN_SQL = """
INSERT INTO quaicu_customer_plans
    (tenant_id, tier, status, created_at, updated_at,
     billing_provider, billing_ref, quota_overrides)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
ON CONFLICT (tenant_id) DO UPDATE SET
    tier             = EXCLUDED.tier,
    status           = EXCLUDED.status,
    updated_at       = EXCLUDED.updated_at,
    billing_provider = EXCLUDED.billing_provider,
    billing_ref      = EXCLUDED.billing_ref,
    quota_overrides  = EXCLUDED.quota_overrides
"""

_SELECT_ALL_PLANS_SQL = """
SELECT tenant_id, tier, status, created_at, updated_at,
       billing_provider, billing_ref, quota_overrides
FROM   quaicu_customer_plans
"""

_SET_TIER_SQL = """
UPDATE quaicu_customer_plans
SET    tier = $2, updated_at = now()
WHERE  tenant_id = $1
"""

_SET_STATUS_SQL = """
UPDATE quaicu_customer_plans
SET    status = $2, updated_at = now()
WHERE  tenant_id = $1
"""


# ── Row mapper ──────────────────────────────────────────────────────────────


def _row_to_plan(row: asyncpg.Record) -> CustomerPlan:
    qo: Any = row["quota_overrides"]
    return CustomerPlan(
        tenant_id=TenantId(row["tenant_id"]),
        tier=FeatureTier(row["tier"]),
        status=PlanStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        billing_provider=row["billing_provider"],
        billing_ref=row["billing_ref"],
        quota_overrides=json.loads(qo) if isinstance(qo, str) else dict(qo or {}),
    )


# ── Adapter ─────────────────────────────────────────────────────────────────


class PostgresEntitlementRepository:
    """Asyncpg-backed `EntitlementRepository`. Pass a libpq/asyncpg DSN; pool is created lazily."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        async with self._pool_lock:
            if self._pool is None:
                try:
                    self._pool = await asyncpg.create_pool(self._dsn)
                except Exception as exc:
                    raise EntitlementPersistenceError(
                        f"Failed to create Postgres pool: {exc}",
                        detail={"dsn_prefix": self._dsn[:30]},
                    ) from exc
        return self._pool  # type: ignore[return-value]

    # ── EntitlementRepository ─────────────────────────────────────────────────

    async def load_all(self) -> list[CustomerPlan]:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(_SELECT_ALL_PLANS_SQL)
            return [_row_to_plan(r) for r in rows]
        except EntitlementPersistenceError:
            raise
        except Exception as exc:
            raise EntitlementPersistenceError(f"load_all failed: {exc}") from exc

    async def save_plan(self, plan: CustomerPlan) -> None:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    _UPSERT_PLAN_SQL,
                    str(plan.tenant_id),
                    plan.tier.value,
                    plan.status.value,
                    plan.created_at,
                    plan.updated_at,
                    plan.billing_provider,
                    plan.billing_ref,
                    json.dumps(dict(plan.quota_overrides)),
                )
        except EntitlementPersistenceError:
            raise
        except Exception as exc:
            raise EntitlementPersistenceError(
                f"save_plan failed for tenant {plan.tenant_id}: {exc}",
                detail={"tenant": str(plan.tenant_id)},
            ) from exc

    async def set_tier(self, tenant: TenantId, tier: FeatureTier) -> None:
        await self._set_column(_SET_TIER_SQL, tenant, tier.value, "set_tier")

    async def set_status(self, tenant: TenantId, status: PlanStatus) -> None:
        await self._set_column(_SET_STATUS_SQL, tenant, status.value, "set_status")

    async def _set_column(self, sql: str, tenant: TenantId, value: str, op: str) -> None:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(sql, str(tenant), value)
            count = int(result.split()[-1])
            if count == 0:
                raise EntitlementPersistenceError(
                    f"{op} affected 0 rows — no plan for tenant",
                    detail={"tenant": str(tenant)},
                )
        except EntitlementPersistenceError:
            raise
        except Exception as exc:
            raise EntitlementPersistenceError(
                f"{op} failed for tenant {tenant}: {exc}",
                detail={"tenant": str(tenant)},
            ) from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
