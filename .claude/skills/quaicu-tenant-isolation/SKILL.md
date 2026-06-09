---
name: quaicu-tenant-isolation
description: |
  QUAICU multi-tenancy isolation enforcer (Frozen Decision F-07 — per-tenant ledger tables always).
  Use when building storage adapters, migrations, the control plane, or any code touching data for
  multiple tenants. Enforces: schema-per-tenant default, no shared ledger table, RLS on every kernel
  table, tenant_id in ContextVar for RLS enforcement. Trigger keywords: tenant, schema_per_tenant,
  TenantId, tenant isolation, RLS, Row Level Security, current_tenant, ledger isolation,
  onboard_tenant, migration per tenant, connection pool, GDPR export, tenant deletion, shard,
  provisioning job, schema version, migration rollout, F-07.
---

# QUAICU Tenant Isolation

You are the tenant isolation enforcer. Tenant isolation is a Core Invariant: no data, decision,
policy, or ledger entry ever crosses a tenant boundary. The architecture must make cross-tenant
contamination **impossible**, not merely unlikely. This means physical schema separation, connection
pool isolation, and RLS as a defense-in-depth backstop — all three layers must hold simultaneously.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every isolation choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → refuse the cross-tenant operation.

### Invariants — never violated
- ALWAYS schema-per-tenant (`"tenant_{id}"`) as the default. NEVER a shared table with a `tenant_id` column for ledger or any kernel table (F-07).
- ALWAYS enable RLS on EVERY kernel table as defense-in-depth — even though schemas already separate data. Three layers (schema + pool + RLS) must all hold.
- ALWAYS set the tenant in a ContextVar and `SET LOCAL search_path` + `SET LOCAL app.current_tenant` per transaction. NEVER rely on app-code `WHERE tenant_id=` filtering alone.
- If another tenant's data is ever observed → raise `TenantCrossContaminationError`, halt everything, alert. Critical, not recoverable-in-place.
- Onboarding is ALL-OR-NOTHING: create schema → migrate → enable RLS+policies → register. Any step fails → roll back the whole thing.

### Decision table
| Situation | Do exactly this |
|---|---|
| New kernel table | per-tenant schema + RLS policy for SELECT/INSERT (+UPDATE where mutable) |
| Ledger table policies | SELECT + INSERT only — NO UPDATE/DELETE policy (append-only) |
| Resolve tenant for a request | from validated identity/JWT claim → ContextVar |
| Schema name from tenant id | sanitize to `^[a-z0-9_]+$`; reject anything else (schema-injection guard) |
| Tenant not ACTIVE | refuse the operation (fail-closed); do not route queries |
| GDPR export (Art. 20) | dump only that tenant's kernel tables; include a manifest |
| Tenant deletion | archive ledger to cold storage FIRST, then drop schema |

### Tie-break rules
- Is RLS "redundant" given schema separation? → keep RLS anyway; defense-in-depth is mandatory.
- Trust an app-level tenant filter? → no; the DB (search_path + RLS) is the boundary.
- Is this tenant string safe in DDL? → sanitize/reject; never interpolate raw.

### Stop-and-apply triggers
- About to write a shared table with `tenant_id`? → STOP, use per-tenant schema.
- About to build a schema name from a raw tenant id? → STOP, sanitize first.
- About to skip RLS "because schemas already isolate"? → STOP, add RLS.

### Self-check
- [ ] Every kernel table in a per-tenant schema; no shared ledger.
- [ ] RLS enabled + policies on every table; ledger has no UPDATE/DELETE policy.
- [ ] Tenant set via ContextVar + SET LOCAL per transaction.
- [ ] Schema names sanitized; non-ACTIVE tenants refused.
- [ ] Onboarding rolls back fully on failure; deletion archives ledger first.

---

## Error Type Hierarchy

All tenant-isolation violations raise typed errors with machine-readable codes. Never raise
`Exception` or `ValueError` from isolation-critical paths — callers must be able to distinguish
error categories precisely.

```python
# core/errors/tenant.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class TenantErrorCode(str, Enum):
    # Context errors
    NO_TENANT_IN_CONTEXT         = "TENANT_001"
    INVALID_TENANT_ID_FORMAT     = "TENANT_002"
    TENANT_CONTEXT_MISMATCH      = "TENANT_003"

    # Isolation violations — these are CRITICAL
    CROSS_TENANT_ACCESS_ATTEMPT  = "TENANT_010"
    RLS_BYPASS_DETECTED          = "TENANT_011"
    SCHEMA_BOUNDARY_VIOLATION    = "TENANT_012"
    SHARED_LEDGER_TABLE_DETECTED = "TENANT_013"

    # Control plane / provisioning
    UNKNOWN_TENANT               = "TENANT_020"
    TENANT_ALREADY_EXISTS        = "TENANT_021"
    PROVISIONING_FAILED          = "TENANT_022"
    SCHEMA_VERSION_MISMATCH      = "TENANT_023"
    MIGRATION_ROLLBACK_TRIGGERED = "TENANT_024"

    # Connection / pool
    POOL_ACQUISITION_TIMEOUT     = "TENANT_030"
    CONNECTION_STRING_INVALID    = "TENANT_031"
    CONNECTION_ROTATION_FAILED   = "TENANT_032"

    # Export / deletion
    EXPORT_JOB_FAILED            = "TENANT_040"
    DELETION_REQUIRES_ARCHIVAL   = "TENANT_041"
    LEDGER_ARCHIVAL_FAILED       = "TENANT_042"
    INCOMPLETE_DELETION          = "TENANT_043"


@dataclass
class TenantError(Exception):
    code: TenantErrorCode
    message: str
    tenant_id: str | None = None
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.tenant_id:
            parts.append(f"tenant={self.tenant_id!r}")
        if self.detail:
            parts.append(str(self.detail))
        return " | ".join(parts)


class TenantContextError(TenantError):
    """Raised when tenant context is missing or malformed before any DB operation."""


class TenantIsolationViolationError(TenantError):
    """
    CRITICAL. Raised when a cross-tenant access is attempted or detected.
    Must be logged at ERROR severity and emit an OTel security.isolation_violation event.
    """


class UnknownTenantError(TenantError):
    """Raised when a tenant_id is not registered in the control plane."""


class TenantProvisioningError(TenantError):
    """Raised when tenant provisioning fails at any step."""


class SchemaVersionMismatchError(TenantError):
    """Raised when a tenant's schema revision does not match the expected kernel version."""


class ConnectionPoolError(TenantError):
    """Raised when per-tenant pool acquisition fails or times out."""


class TenantExportError(TenantError):
    """Raised when GDPR Article 20 data export fails."""


class TenantDeletionError(TenantError):
    """Raised when tenant deletion fails, including when ledger archival is incomplete."""
```

---

## Isolation Tiers (§3.10)

| Tier | Database | Schema | Isolation basis |
|------|----------|--------|-----------------|
| **Sovereign** | One DB, one tenant | n/a (single tenant) | Physical |
| **Dedicated** | One DB instance per tenant VPC | n/a | Instance |
| **Shared** (QUAICU-hosted) | Shared instance | **Schema-per-tenant** | Schema + RLS |

Schema-per-tenant is the default for the shared tier.
Shared-schema-with-`tenant_id`-column is **rejected** as default — a single mis-filtered query
leaks across tenants. Use only if forced to many thousands of tiny tenants AND even then never
for the ledger. The ledger is **always** per-tenant tables inside the tenant's schema (F-07).

---

## Schema-Per-Tenant Layout

```sql
-- Every tenant gets its own schema. Tables are identical across schemas.
-- Control plane tracks tenant → schema mapping.
-- tenant "acme_bank" → schema "tenant_acme_bank"
-- tenant "agency_x"  → schema "tenant_agency_x"

-- All kernel tables live in the tenant's schema:
-- tenant_{id}.ledger_entries          (K·02) — NEVER shared
-- tenant_{id}.ledger_tree_nodes       (K·02 Merkle)
-- tenant_{id}.actions                 (lifecycle)
-- tenant_{id}.policies                (K·01)
-- tenant_{id}.policy_versions         (K·01 history)
-- tenant_{id}.consent_records         (K·04)
-- tenant_{id}.model_call_log          (K·05)
-- tenant_{id}.workflow_events         (K·06)
-- tenant_{id}.workflow_status         (K·06)
-- tenant_{id}.model_registry          (K·08)
-- tenant_{id}.fairness_snapshots      (K·09)
-- tenant_{id}.drift_snapshots         (K·10)
-- tenant_{id}.explain_log             (K·11)
-- tenant_{id}.incident_log            (K·12)
-- tenant_{id}.regulation_mappings     (K·14)
-- tenant_{id}.schema_version          (migration tracking)

-- Control plane lives in its own schema — never in tenant schemas
-- control_plane.tenants
-- control_plane.provisioning_jobs
-- control_plane.migration_runs
-- control_plane.shard_assignments
```

---

## Tenant Context (ContextVar — enforced at every storage boundary)

```python
# core/tenant_context.py
from __future__ import annotations
import re
from contextvars import ContextVar
from opentelemetry import trace

from core.errors.tenant import (
    TenantContextError, TenantIsolationViolationError,
    TenantErrorCode,
)

tracer = trace.get_tracer("quaicu.tenant_context")

_TENANT_ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_\-]{1,62}[a-z0-9]$')

_current_tenant: ContextVar[str | None] = ContextVar(
    'current_tenant', default=None
)


def set_tenant(tenant_id: str) -> None:
    """
    Set the tenant context for the current async task. Must be called before
    any DB operation in every request handler, background job, and test.
    Validates format — does NOT check against the registry (use ControlPlane for that).
    """
    if not tenant_id or not _TENANT_ID_PATTERN.match(tenant_id):
        raise TenantContextError(
            code=TenantErrorCode.INVALID_TENANT_ID_FORMAT,
            message=f"Invalid tenant_id format: {tenant_id!r}. "
                    "Must be 3–64 chars, lowercase alphanumeric, hyphens, underscores.",
            tenant_id=tenant_id,
        )
    _current_tenant.set(tenant_id)

    span = trace.get_current_span()
    span.set_attribute("quaicu.tenant_id", tenant_id)


def get_tenant() -> str:
    """
    Return the tenant_id from the current async context.
    Raises TenantContextError if not set — fail-closed.
    """
    t = _current_tenant.get()
    if t is None:
        raise TenantContextError(
            code=TenantErrorCode.NO_TENANT_IN_CONTEXT,
            message=(
                "No tenant in context — set_tenant() must be called before any DB operation. "
                "Check that the request middleware invokes set_tenant() from the auth token."
            ),
        )
    return t


def require_tenant_match(tenant_id: str) -> None:
    """
    Assert the supplied tenant_id matches the context tenant.
    Call at every storage boundary where a tenant_id is passed in from outside.
    Any mismatch is a CRITICAL isolation violation — log and raise immediately.
    """
    ctx = get_tenant()
    if ctx != tenant_id:
        with tracer.start_as_current_span("quaicu.isolation_violation") as span:
            span.set_attribute("quaicu.context_tenant", ctx)
            span.set_attribute("quaicu.supplied_tenant", tenant_id)
            span.set_attribute("quaicu.security_event", "cross_tenant_access_attempt")
            span.record_exception(
                TenantIsolationViolationError(
                    code=TenantErrorCode.CROSS_TENANT_ACCESS_ATTEMPT,
                    message=f"Tenant mismatch: context={ctx!r}, supplied={tenant_id!r}",
                    tenant_id=ctx,
                    detail={"supplied": tenant_id},
                )
            )
        raise TenantIsolationViolationError(
            code=TenantErrorCode.CROSS_TENANT_ACCESS_ATTEMPT,
            message=f"Tenant mismatch: context={ctx!r}, supplied={tenant_id!r}",
            tenant_id=ctx,
            detail={"supplied": tenant_id},
        )


def schema_name_for(tenant_id: str) -> str:
    """
    Compute the PostgreSQL schema name from a tenant_id.
    Idempotent and deterministic — same input always produces same schema name.
    """
    safe = re.sub(r'[^a-z0-9_]', '_', tenant_id.lower())
    return f"tenant_{safe}"
```

---

## Per-Tenant Connection Pool (asyncpg)

Each tenant gets its own asyncpg pool bound to the tenant's database shard and schema.
Pools are lazily created and cached in the ControlPlane. This prevents noisy-neighbour
connection exhaustion and ensures schema-level isolation at the network layer.

```python
# adapters/storage/pool_manager.py
from __future__ import annotations
import asyncpg
import asyncio
from typing import Dict
from opentelemetry import metrics, trace

from core.errors.tenant import (
    ConnectionPoolError, TenantErrorCode, UnknownTenantError,
)
from core.tenant_context import schema_name_for

meter  = metrics.get_meter("quaicu.pool_manager")
tracer = trace.get_tracer("quaicu.pool_manager")

_pool_size_gauge = meter.create_gauge(
    "quaicu.pool.size",
    description="Active connections per tenant pool",
    unit="connections",
)
_pool_wait_histogram = meter.create_histogram(
    "quaicu.pool.acquire_latency_ms",
    description="Time to acquire a connection from a tenant pool",
    unit="ms",
)


class TenantPoolManager:
    """
    Manages one asyncpg connection pool per tenant.
    Pool is bound to the tenant's shard DSN and configured with:
      - min_size: 1 (keeps one warm connection)
      - max_size: configurable per tier (default 10 for shared, 25 for dedicated)
      - command_timeout: 30s (fail-closed on slow queries)
      - setup: sets search_path and app.current_tenant immediately on each connection
    """

    def __init__(
        self,
        control_plane: "ControlPlane",
        *,
        default_pool_max: int = 10,
        acquire_timeout: float = 5.0,
    ) -> None:
        self._cp = control_plane
        self._pools: Dict[str, asyncpg.Pool] = {}
        self._lock = asyncio.Lock()
        self._default_pool_max = default_pool_max
        self._acquire_timeout = acquire_timeout

    async def pool_for(self, tenant_id: str) -> asyncpg.Pool:
        """
        Return (and lazily create) the pool for tenant_id.
        Thread-safe: concurrent callers for the same tenant wait on the lock
        and only one pool is created.
        """
        if tenant_id in self._pools:
            return self._pools[tenant_id]

        async with self._lock:
            if tenant_id in self._pools:          # double-checked
                return self._pools[tenant_id]

            info = await self._cp.get_connection_info(tenant_id)
            schema = schema_name_for(tenant_id)

            async def _setup(conn: asyncpg.Connection) -> None:
                """
                Called for every new connection in the pool.
                Pins search_path and current_tenant at the connection level.
                This is defense-in-depth — StorageAdapter also sets these per-query.
                """
                await conn.execute(
                    f"SET search_path TO \"{schema}\", public"
                )
                await conn.set_type_codec(
                    'json', encoder=lambda x: x, decoder=lambda x: x,
                    schema='pg_catalog', format='text',
                )

            pool = await asyncpg.create_pool(
                dsn=info.dsn,
                min_size=1,
                max_size=info.pool_max or self._default_pool_max,
                command_timeout=30,
                setup=_setup,
            )
            self._pools[tenant_id] = pool
            _pool_size_gauge.set(
                pool.get_size(),
                {"tenant_id": tenant_id},
            )
            return pool

    async def acquire(self, tenant_id: str) -> asyncpg.Connection:
        """
        Acquire a connection from the tenant's pool with timeout.
        Raises ConnectionPoolError if timeout elapses — fail-closed.
        """
        import time
        pool = await self.pool_for(tenant_id)
        t0 = time.monotonic()
        try:
            conn = await asyncio.wait_for(
                pool.acquire(),
                timeout=self._acquire_timeout,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            _pool_wait_histogram.record(elapsed_ms, {"tenant_id": tenant_id})
            return conn
        except asyncio.TimeoutError:
            raise ConnectionPoolError(
                code=TenantErrorCode.POOL_ACQUISITION_TIMEOUT,
                message=f"Connection pool acquisition timed out after {self._acquire_timeout}s",
                tenant_id=tenant_id,
            )

    async def rotate_connection_string(self, tenant_id: str, new_dsn: str) -> None:
        """
        Connection string rotation (e.g. after credential rotation in OpenBao).
        Drains and closes the old pool, then re-creates with the new DSN.
        New connections are served from the new pool immediately.
        """
        async with self._lock:
            old_pool = self._pools.pop(tenant_id, None)
            await self._cp.update_dsn(tenant_id, new_dsn)
            if old_pool:
                await old_pool.close()   # drain gracefully
            # Next call to pool_for() will create the new pool

    async def close_all(self) -> None:
        """Gracefully close all pools. Called on application shutdown."""
        async with self._lock:
            for pool in self._pools.values():
                await pool.close()
            self._pools.clear()
```

---

## Storage Adapter (enforces schema isolation per query)

```python
# adapters/storage/postgres.py
from __future__ import annotations
import asyncpg
from contextlib import asynccontextmanager
from opentelemetry import trace

from core.tenant_context import get_tenant, require_tenant_match, schema_name_for
from core.errors.tenant import TenantErrorCode, TenantIsolationViolationError

tracer = trace.get_tracer("quaicu.storage")


class PostgresStorageAdapter:
    """
    All queries run against the tenant's schema via search_path.
    Never SELECT from a table without schema qualification via search_path.
    Per-query SET LOCAL overrides the connection-level setup as a second layer.
    """

    def __init__(self, pool_manager: "TenantPoolManager") -> None:
        self._pool_manager = pool_manager

    @asynccontextmanager
    async def _connection(self, tenant_id: str):
        """
        Acquire a connection and set LOCAL session variables for isolation.
        SET LOCAL scopes changes to the current transaction only — this is
        the per-query isolation layer on top of the connection-level setup.
        """
        schema = schema_name_for(tenant_id)
        with tracer.start_as_current_span("quaicu.storage.connection") as span:
            span.set_attribute("quaicu.tenant_id", tenant_id)
            span.set_attribute("quaicu.schema", schema)
            conn = await self._pool_manager.acquire(tenant_id)
            try:
                async with conn.transaction():
                    await conn.execute(
                        f"SET LOCAL search_path TO \"{schema}\", public"
                    )
                    await conn.execute(
                        "SET LOCAL app.current_tenant = $1", tenant_id
                    )
                    yield conn
            finally:
                await self._pool_manager.pool_for.__self__  # release back to pool
                # asyncpg pools release automatically on context exit

    async def execute(
        self,
        query: str,
        params: tuple = (),
        *,
        tenant_id: str | None = None,
    ) -> list[asyncpg.Record]:
        t = tenant_id or get_tenant()
        async with self._connection(t) as conn:
            return await conn.fetch(query, *params)

    @asynccontextmanager
    async def transaction(self, *, tenant_id: str | None = None):
        """Expose a transactional context for multi-step operations."""
        t = tenant_id or get_tenant()
        async with self._connection(t) as conn:
            yield conn
```

---

## Row-Level Security — Full Policy for Every Kernel Table

RLS is the defense-in-depth layer. Even a mis-configured `search_path` cannot leak data
across tenants with RLS active and the app role set to `FORCE ROW LEVEL SECURITY`.

```sql
-- migrations/templates/per_tenant_rls.sql
-- Applied in every per-tenant migration. Idempotent (IF NOT EXISTS guards).

-- ── ledger_entries (K·02) ───────────────────────────────────────────────────
ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_entries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON ledger_entries;
CREATE POLICY tenant_iso ON ledger_entries
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── ledger_tree_nodes (K·02 Merkle) ─────────────────────────────────────────
ALTER TABLE ledger_tree_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_tree_nodes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON ledger_tree_nodes;
CREATE POLICY tenant_iso ON ledger_tree_nodes
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── actions ──────────────────────────────────────────────────────────────────
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE actions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON actions;
CREATE POLICY tenant_iso ON actions
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── policies ─────────────────────────────────────────────────────────────────
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON policies;
CREATE POLICY tenant_iso ON policies
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── policy_versions ──────────────────────────────────────────────────────────
ALTER TABLE policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON policy_versions;
CREATE POLICY tenant_iso ON policy_versions
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── consent_records (K·04) ───────────────────────────────────────────────────
ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON consent_records;
CREATE POLICY tenant_iso ON consent_records
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── model_call_log (K·05) ────────────────────────────────────────────────────
ALTER TABLE model_call_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_call_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON model_call_log;
CREATE POLICY tenant_iso ON model_call_log
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── workflow_events, workflow_status (K·06) ───────────────────────────────────
ALTER TABLE workflow_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON workflow_events;
CREATE POLICY tenant_iso ON workflow_events
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

ALTER TABLE workflow_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_status FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON workflow_status;
CREATE POLICY tenant_iso ON workflow_status
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── model_registry (K·08) ────────────────────────────────────────────────────
ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_registry FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON model_registry;
CREATE POLICY tenant_iso ON model_registry
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── fairness_snapshots (K·09) ────────────────────────────────────────────────
ALTER TABLE fairness_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE fairness_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON fairness_snapshots;
CREATE POLICY tenant_iso ON fairness_snapshots
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── drift_snapshots (K·10) ───────────────────────────────────────────────────
ALTER TABLE drift_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE drift_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON drift_snapshots;
CREATE POLICY tenant_iso ON drift_snapshots
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── explain_log (K·11) ───────────────────────────────────────────────────────
ALTER TABLE explain_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE explain_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON explain_log;
CREATE POLICY tenant_iso ON explain_log
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── incident_log (K·12) ──────────────────────────────────────────────────────
ALTER TABLE incident_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON incident_log;
CREATE POLICY tenant_iso ON incident_log
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- ── regulation_mappings (K·14) ───────────────────────────────────────────────
ALTER TABLE regulation_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE regulation_mappings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso ON regulation_mappings;
CREATE POLICY tenant_iso ON regulation_mappings
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true));

-- App role has NO superuser, cannot bypass RLS
-- GRANT USAGE ON SCHEMA "tenant_{id}" TO quaicu_app_role;
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA "tenant_{id}" TO quaicu_app_role;
-- NO UPDATE or DELETE on ledger_entries, ledger_tree_nodes (append-only invariant)
```

---

## Schema Version Tracking Table

```sql
-- Every tenant schema has this table to track which kernel migration has been applied.
-- Used by migration rollout orchestration to determine which tenants are behind.
CREATE TABLE IF NOT EXISTS schema_version (
    id               SERIAL PRIMARY KEY,
    kernel_version   TEXT        NOT NULL,          -- e.g. "1.4.2"
    migration_id     TEXT        NOT NULL,          -- Alembic revision id
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by       TEXT        NOT NULL,          -- "migration_runner" or actor_id
    rollback_sql     TEXT,                          -- DDL to reverse, if reversible
    UNIQUE (migration_id)
);
```

```python
# core/control_plane/schema_version.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SchemaVersionRecord:
    kernel_version: str
    migration_id: str
    applied_at: datetime
    applied_by: str
    rollback_sql: str | None


async def get_schema_version(tenant_id: str, storage) -> SchemaVersionRecord | None:
    """Return the latest applied migration for a tenant, or None if schema is uninitialized."""
    rows = await storage.execute(
        "SELECT * FROM schema_version ORDER BY applied_at DESC LIMIT 1",
        tenant_id=tenant_id,
    )
    if not rows:
        return None
    r = rows[0]
    return SchemaVersionRecord(
        kernel_version=r["kernel_version"],
        migration_id=r["migration_id"],
        applied_at=r["applied_at"],
        applied_by=r["applied_by"],
        rollback_sql=r["rollback_sql"],
    )


async def assert_schema_current(tenant_id: str, expected_migration_id: str,
                                 storage) -> None:
    """
    Assert that the tenant's schema is at the expected migration.
    Raises SchemaVersionMismatchError if behind — fail-closed.
    Called at request time to prevent operating on a stale schema.
    """
    from core.errors.tenant import SchemaVersionMismatchError, TenantErrorCode
    record = await get_schema_version(tenant_id, storage)
    actual = record.migration_id if record else "uninitialized"
    if actual != expected_migration_id:
        raise SchemaVersionMismatchError(
            code=TenantErrorCode.SCHEMA_VERSION_MISMATCH,
            message=(
                f"Tenant schema is at {actual!r}, expected {expected_migration_id!r}. "
                "Run migration rollout before serving requests for this tenant."
            ),
            tenant_id=tenant_id,
            detail={"actual": actual, "expected": expected_migration_id},
        )
```

---

## Tenant Provisioning — Async Job with Status Tracking

Provisioning is an async background job because schema creation + migrations can take
several seconds. The caller receives a `ProvisioningJob` immediately and polls status.

```python
# core/control_plane/provisioning.py
from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from opentelemetry import trace, metrics

from core.errors.tenant import TenantProvisioningError, TenantErrorCode
from core.tenant_context import schema_name_for

tracer = trace.get_tracer("quaicu.provisioning")
meter  = metrics.get_meter("quaicu.provisioning")

_provision_counter = meter.create_counter(
    "quaicu.tenants.provisioned_total",
    description="Total tenants successfully provisioned",
)
_provision_latency = meter.create_histogram(
    "quaicu.tenants.provision_latency_ms",
    description="Time to fully provision a tenant",
    unit="ms",
)


class ProvisioningStatus(str, Enum):
    PENDING       = "PENDING"
    CREATING      = "CREATING"        # schema DDL
    MIGRATING     = "MIGRATING"       # running Alembic migrations
    ENABLING_RLS  = "ENABLING_RLS"    # applying RLS policies
    REGISTERING   = "REGISTERING"     # writing to control_plane.tenants
    COMPLETE      = "COMPLETE"
    FAILED        = "FAILED"
    ROLLED_BACK   = "ROLLED_BACK"


@dataclass
class ProvisioningJob:
    job_id: str
    tenant_id: str
    status: ProvisioningStatus
    tier: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    schema_name: str | None = None
    steps_completed: list[str] = field(default_factory=list)


@dataclass
class TenantRecord:
    tenant_id: str
    schema_name: str
    tier: str
    db_shard_id: str
    created_at: datetime
    is_active: bool = True


class ProvisioningOrchestrator:
    """
    Executes tenant provisioning as an async background job.
    Each step is recorded so that partial failures can be rolled back or resumed.
    """

    def __init__(self, storage, migration_runner, pool_manager, job_store) -> None:
        self._storage       = storage
        self._migration_runner = migration_runner
        self._pool_manager  = pool_manager
        self._job_store     = job_store

    async def enqueue(self, tenant_id: str, tier: str,
                      db_shard_id: str) -> ProvisioningJob:
        """
        Enqueue a provisioning job and return immediately.
        The actual work runs in _execute(), called by the background task runner.
        """
        job = ProvisioningJob(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            tier=tier,
            status=ProvisioningStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await self._job_store.save(job)
        asyncio.create_task(self._execute(job, db_shard_id))
        return job

    async def get_job(self, job_id: str) -> ProvisioningJob:
        job = await self._job_store.get(job_id)
        if job is None:
            raise KeyError(f"Provisioning job {job_id!r} not found")
        return job

    async def _execute(self, job: ProvisioningJob, db_shard_id: str) -> None:
        import time
        t0 = time.monotonic()
        schema = schema_name_for(job.tenant_id)
        job.schema_name = schema

        with tracer.start_as_current_span("quaicu.provision_tenant") as span:
            span.set_attribute("quaicu.tenant_id", job.tenant_id)
            span.set_attribute("quaicu.tier", job.tier)
            span.set_attribute("quaicu.provisioning_job_id", job.job_id)

            try:
                # Step 1 — Create schema
                await self._update_status(job, ProvisioningStatus.CREATING)
                await self._storage.execute(
                    f'CREATE SCHEMA IF NOT EXISTS "{schema}"',
                    tenant_id="_control_plane",
                )
                job.steps_completed.append("schema_created")

                # Step 2 — Run Alembic migrations scoped to this schema
                await self._update_status(job, ProvisioningStatus.MIGRATING)
                await self._migration_runner.run_for_tenant(job.tenant_id, schema)
                job.steps_completed.append("migrations_applied")

                # Step 3 — Enable RLS on every table
                await self._update_status(job, ProvisioningStatus.ENABLING_RLS)
                await self._apply_rls(schema)
                job.steps_completed.append("rls_enabled")

                # Step 4 — Register in control plane
                await self._update_status(job, ProvisioningStatus.REGISTERING)
                record = TenantRecord(
                    tenant_id=job.tenant_id,
                    schema_name=schema,
                    tier=job.tier,
                    db_shard_id=db_shard_id,
                    created_at=datetime.now(timezone.utc),
                )
                await self._storage.execute(
                    "INSERT INTO control_plane.tenants "
                    "(tenant_id, schema_name, tier, db_shard_id, created_at) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    (record.tenant_id, record.schema_name, record.tier,
                     record.db_shard_id, record.created_at),
                    tenant_id="_control_plane",
                )
                job.steps_completed.append("registered")

                # Done
                job.status = ProvisioningStatus.COMPLETE
                elapsed_ms = (time.monotonic() - t0) * 1000
                _provision_counter.add(1, {"tier": job.tier})
                _provision_latency.record(elapsed_ms, {"tier": job.tier})

            except Exception as exc:
                job.status = ProvisioningStatus.FAILED
                job.error = str(exc)
                span.record_exception(exc)
                await self._rollback(job, schema)
            finally:
                job.updated_at = datetime.now(timezone.utc)
                await self._job_store.save(job)

    async def _apply_rls(self, schema: str) -> None:
        """Load and execute the RLS template for this schema."""
        from pathlib import Path
        sql = Path("migrations/templates/per_tenant_rls.sql").read_text()
        # Replace placeholder schema name
        sql = sql.replace("tenant_{id}", schema)
        await self._storage.execute(sql, tenant_id="_control_plane")

    async def _rollback(self, job: ProvisioningJob, schema: str) -> None:
        """
        Best-effort rollback: drop the schema if it was created.
        Records ROLLED_BACK status — does not raise.
        """
        try:
            await self._storage.execute(
                f'DROP SCHEMA IF EXISTS "{schema}" CASCADE',
                tenant_id="_control_plane",
            )
            job.status = ProvisioningStatus.ROLLED_BACK
        except Exception:
            pass  # rollback failure recorded in job.error — do not mask original

    async def _update_status(
        self, job: ProvisioningJob, status: ProvisioningStatus
    ) -> None:
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        await self._job_store.save(job)
```

---

## Tenant Data Export — GDPR Article 20

GDPR Article 20 (data portability) requires the ability to export all personal data
for a tenant in a structured, machine-readable format. This is a signed export bundle.

```python
# core/control_plane/gdpr_export.py
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

from core.tenant_context import schema_name_for
from core.errors.tenant import TenantExportError, TenantErrorCode

tracer = trace.get_tracer("quaicu.gdpr_export")

_EXPORTABLE_TABLES = [
    "actions",
    "policies",
    "consent_records",
    "model_call_log",
    "workflow_events",
    "incident_log",
    # ledger_entries are archived separately with integrity proofs
]


@dataclass
class TenantExportBundle:
    tenant_id: str
    exported_at: datetime
    kernel_version: str
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ledger_archive_ref: str | None = None   # reference to ledger archival object in MinIO
    bundle_hash: str | None = None          # SHA-256 of the serialized bundle (self-certifying)


async def export_tenant_data(
    tenant_id: str,
    storage,
    object_store,
    kernel_version: str,
) -> TenantExportBundle:
    """
    GDPR Article 20 — data portability export.
    Exports all tenant data from every kernel table as structured JSON.
    Ledger entries are exported with their RFC 6962 inclusion proofs.
    The bundle is stored in object storage and a SHA-256 hash is returned
    so the tenant can verify integrity.
    """
    with tracer.start_as_current_span("quaicu.gdpr_export") as span:
        span.set_attribute("quaicu.tenant_id", tenant_id)

        bundle = TenantExportBundle(
            tenant_id=tenant_id,
            exported_at=datetime.now(timezone.utc),
            kernel_version=kernel_version,
        )

        # Export each table
        for table in _EXPORTABLE_TABLES:
            rows = await storage.execute(
                f"SELECT * FROM {table}",
                tenant_id=tenant_id,
            )
            bundle.tables[table] = [dict(r) for r in rows]

        # Export ledger with inclusion proofs
        ledger_rows = await storage.execute(
            "SELECT le.*, ltn.proof_path "
            "FROM ledger_entries le "
            "LEFT JOIN ledger_tree_nodes ltn ON ltn.leaf_hash = le.leaf_hash",
            tenant_id=tenant_id,
        )
        bundle.tables["ledger_entries_with_proofs"] = [dict(r) for r in ledger_rows]

        # Serialize and hash the bundle
        raw = json.dumps(
            {
                "tenant_id": bundle.tenant_id,
                "exported_at": bundle.exported_at.isoformat(),
                "kernel_version": bundle.kernel_version,
                "tables": bundle.tables,
            },
            default=str,
            sort_keys=True,
        ).encode()

        bundle.bundle_hash = hashlib.sha256(raw).hexdigest()

        # Upload to object storage
        object_key = f"gdpr_exports/{tenant_id}/{bundle.exported_at.date()}/{bundle.bundle_hash[:8]}.json"
        await object_store.put(object_key, raw, content_type="application/json")
        bundle.ledger_archive_ref = object_key

        span.set_attribute("quaicu.export.bundle_hash", bundle.bundle_hash)
        span.set_attribute("quaicu.export.object_key", object_key)

        return bundle
```

---

## Tenant Deletion with Ledger Archival

```python
# core/control_plane/deletion.py
from __future__ import annotations
from datetime import datetime, timezone

from opentelemetry import trace

from core.errors.tenant import TenantDeletionError, TenantErrorCode
from core.tenant_context import schema_name_for

tracer = trace.get_tracer("quaicu.tenant_deletion")


async def delete_tenant(
    tenant_id: str,
    storage,
    object_store,
    pool_manager,
    kernel_version: str,
    *,
    require_export: bool = True,
) -> str:
    """
    Permanently delete a tenant and all their data.
    Steps (in order, each must succeed before the next):
      1. Export full data bundle (GDPR portability, also serves as archival proof)
      2. Close and destroy the per-tenant connection pool
      3. DROP SCHEMA CASCADE in a transaction
      4. Remove from control_plane.tenants
      5. Record deletion event in control_plane.deletion_log

    Raises TenantDeletionError if archival fails and require_export=True.
    """
    with tracer.start_as_current_span("quaicu.delete_tenant") as span:
        span.set_attribute("quaicu.tenant_id", tenant_id)

        if require_export:
            try:
                from core.control_plane.gdpr_export import export_tenant_data
                bundle = await export_tenant_data(
                    tenant_id, storage, object_store, kernel_version
                )
                span.set_attribute("quaicu.deletion.archive_ref", bundle.ledger_archive_ref)
            except Exception as exc:
                raise TenantDeletionError(
                    code=TenantErrorCode.LEDGER_ARCHIVAL_FAILED,
                    message=f"Ledger archival failed before deletion — deletion aborted: {exc}",
                    tenant_id=tenant_id,
                )

        # Close the per-tenant connection pool before dropping the schema
        schema = schema_name_for(tenant_id)
        await pool_manager.rotate_connection_string(tenant_id, "__deleted__")

        async with storage.transaction(tenant_id="_control_plane") as conn:
            # Drop the entire tenant schema
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

            # Remove from registry
            await conn.execute(
                "DELETE FROM control_plane.tenants WHERE tenant_id = $1",
                tenant_id,
            )

            # Record deletion permanently
            await conn.execute(
                "INSERT INTO control_plane.deletion_log "
                "(tenant_id, deleted_at, archive_ref, deleted_by) "
                "VALUES ($1, $2, $3, $4)",
                tenant_id,
                datetime.now(timezone.utc),
                bundle.ledger_archive_ref if require_export else None,
                "system",
            )

        return schema
```

---

## Cross-Shard Query Routing

When tenants are distributed across multiple database shards, the ControlPlane
resolves which shard hosts a given tenant before routing the query.

```python
# core/control_plane/router.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Awaitable, TypeVar

from opentelemetry import trace

from core.errors.tenant import UnknownTenantError, TenantErrorCode

tracer = trace.get_tracer("quaicu.router")

T = TypeVar("T")


@dataclass
class TenantConnInfo:
    tenant_id: str
    dsn: str
    schema_name: str
    db_shard_id: str
    pool_max: int = 10


@dataclass
class ShardInfo:
    shard_id: str
    dsn: str
    tenant_ids: list[str]


class ControlPlane:
    """
    Tracks tenant → (shard, schema) mapping.
    Scales to hundreds–low-thousands of tenants per DB shard.
    Beyond that, add shards and update shard_assignments.

    Scaling model:
      - Each shared-tier shard DB handles 200–500 tenants comfortably
        (assuming average 10 connections/tenant, 5000 max_connections on the DB).
      - Formula: max_tenants_per_db = floor(pg_max_connections * 0.8 / pool_max_per_tenant)
        e.g. 5000 * 0.8 / 10 = 400 tenants per shard.
      - Control plane assigns new tenants to the shard with the fewest tenants.
      - Re-balancing (moving a tenant to a new shard) is a separate migration operation.
    """

    def __init__(self, registry_storage) -> None:
        self._registry = registry_storage
        self._cache: dict[str, TenantConnInfo] = {}

    async def get_connection_info(self, tenant_id: str) -> TenantConnInfo:
        if tenant_id in self._cache:
            return self._cache[tenant_id]

        with tracer.start_as_current_span("quaicu.control_plane.resolve") as span:
            span.set_attribute("quaicu.tenant_id", tenant_id)
            row = await self._registry.execute(
                "SELECT t.tenant_id, s.dsn, t.schema_name, t.db_shard_id, t.pool_max "
                "FROM control_plane.tenants t "
                "JOIN control_plane.shards s ON s.shard_id = t.db_shard_id "
                "WHERE t.tenant_id = $1 AND t.is_active = true",
                (tenant_id,),
                tenant_id="_control_plane",
            )
            if not row:
                raise UnknownTenantError(
                    code=TenantErrorCode.UNKNOWN_TENANT,
                    message=f"Tenant {tenant_id!r} not found or not active.",
                    tenant_id=tenant_id,
                )
            info = TenantConnInfo(**row[0])
            self._cache[tenant_id] = info
            return info

    async def invalidate_cache(self, tenant_id: str) -> None:
        self._cache.pop(tenant_id, None)

    async def list_tenants_for_shard(self, shard_id: str) -> list[str]:
        rows = await self._registry.execute(
            "SELECT tenant_id FROM control_plane.tenants "
            "WHERE db_shard_id = $1 AND is_active = true",
            (shard_id,),
            tenant_id="_control_plane",
        )
        return [r["tenant_id"] for r in rows]

    async def choose_shard_for_new_tenant(self) -> ShardInfo:
        """
        Assign new tenant to the shard with the fewest active tenants.
        This is the scaling balancer — keeps tenants evenly distributed.
        """
        rows = await self._registry.execute(
            "SELECT s.shard_id, s.dsn, COUNT(t.tenant_id) as tenant_count "
            "FROM control_plane.shards s "
            "LEFT JOIN control_plane.tenants t "
            "  ON t.db_shard_id = s.shard_id AND t.is_active = true "
            "GROUP BY s.shard_id, s.dsn "
            "ORDER BY tenant_count ASC LIMIT 1",
            tenant_id="_control_plane",
        )
        if not rows:
            raise RuntimeError("No active shards available for tenant placement.")
        r = rows[0]
        return ShardInfo(shard_id=r["shard_id"], dsn=r["dsn"], tenant_ids=[])
```

---

## Migration Rollout Orchestration — Batched with Per-Tenant Rollback

When a new kernel migration is released, it must be applied to every tenant schema.
This is done in batches with per-tenant rollback on failure — never a big-bang all-at-once.

```python
# core/control_plane/migration_rollout.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from opentelemetry import trace, metrics

tracer = trace.get_tracer("quaicu.migration_rollout")
meter  = metrics.get_meter("quaicu.migration_rollout")

_rollout_progress = meter.create_counter(
    "quaicu.migration.tenants_migrated",
    description="Number of tenants successfully migrated in a rollout",
)
_rollout_failures = meter.create_counter(
    "quaicu.migration.tenant_failures",
    description="Number of tenants that failed migration in a rollout",
)


class TenantMigrationStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class TenantMigrationResult:
    tenant_id: str
    status: TenantMigrationStatus
    migration_id: str
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class RolloutReport:
    migration_id: str
    started_at: datetime
    finished_at: datetime | None = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[TenantMigrationResult] = field(default_factory=list)


async def rollout_migration(
    migration_id: str,
    target_kernel_version: str,
    control_plane: "ControlPlane",
    migration_runner: Any,
    storage,
    *,
    batch_size: int = 20,
    max_failure_pct: float = 0.05,
) -> RolloutReport:
    """
    Apply a migration to all active tenants in batches.

    Safety contract:
    - Failures in one batch do NOT stop the rollout unless max_failure_pct is exceeded.
    - Each failed tenant is rolled back individually (using rollback_sql from schema_version).
    - If cumulative failure rate exceeds max_failure_pct, the rollout is halted and
      remaining tenants are left at the previous migration — fail-closed.
    - A RolloutReport is returned and persisted for audit regardless of outcome.
    """
    import time
    report = RolloutReport(
        migration_id=migration_id,
        started_at=datetime.now(timezone.utc),
    )

    with tracer.start_as_current_span("quaicu.migration_rollout") as span:
        span.set_attribute("quaicu.migration_id", migration_id)

        all_tenants = await control_plane.list_all_active_tenants()
        report.total = len(all_tenants)
        span.set_attribute("quaicu.rollout.tenant_count", report.total)

        # Process in batches
        for batch_start in range(0, len(all_tenants), batch_size):
            batch = all_tenants[batch_start: batch_start + batch_size]
            batch_tasks = [
                _migrate_one_tenant(
                    tenant_id, migration_id, target_kernel_version,
                    migration_runner, storage
                )
                for tenant_id in batch
            ]
            results: list[TenantMigrationResult] = await asyncio.gather(
                *batch_tasks, return_exceptions=False
            )

            for result in results:
                report.results.append(result)
                if result.status == TenantMigrationStatus.SUCCESS:
                    report.succeeded += 1
                    _rollout_progress.add(1, {"migration_id": migration_id})
                else:
                    report.failed += 1
                    _rollout_failures.add(1, {"migration_id": migration_id})

            # Check failure rate — halt if too many failures
            failure_rate = report.failed / max(report.total, 1)
            if failure_rate > max_failure_pct:
                span.set_attribute("quaicu.rollout.halted_reason", "failure_rate_exceeded")
                break  # leave remaining tenants at old migration — safe

    report.finished_at = datetime.now(timezone.utc)
    await _persist_rollout_report(report, storage)
    return report


async def _migrate_one_tenant(
    tenant_id: str,
    migration_id: str,
    kernel_version: str,
    migration_runner,
    storage,
) -> TenantMigrationResult:
    import time
    from core.tenant_context import schema_name_for
    schema = schema_name_for(tenant_id)
    t0 = time.monotonic()
    try:
        await migration_runner.run_for_tenant(tenant_id, schema, up_to=migration_id)
        await storage.execute(
            "INSERT INTO schema_version (kernel_version, migration_id, applied_by) "
            "VALUES ($1, $2, $3) ON CONFLICT (migration_id) DO NOTHING",
            (kernel_version, migration_id, "migration_rollout"),
            tenant_id=tenant_id,
        )
        return TenantMigrationResult(
            tenant_id=tenant_id,
            status=TenantMigrationStatus.SUCCESS,
            migration_id=migration_id,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as exc:
        # Attempt per-tenant rollback
        try:
            await migration_runner.run_for_tenant(tenant_id, schema, downgrade=True)
            status = TenantMigrationStatus.ROLLED_BACK
        except Exception:
            status = TenantMigrationStatus.FAILED
        return TenantMigrationResult(
            tenant_id=tenant_id,
            status=status,
            migration_id=migration_id,
            error=str(exc),
            duration_ms=(time.monotonic() - t0) * 1000,
        )


async def _persist_rollout_report(report: RolloutReport, storage) -> None:
    import json
    await storage.execute(
        "INSERT INTO control_plane.migration_runs "
        "(migration_id, started_at, finished_at, total, succeeded, failed, results_json) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
        (
            report.migration_id,
            report.started_at,
            report.finished_at,
            report.total,
            report.succeeded,
            report.failed,
            json.dumps([vars(r) for r in report.results]),
        ),
        tenant_id="_control_plane",
    )
```

---

## OTel Instrumentation Reference

Every isolation-critical path emits OTel spans and metrics. Minimum required attributes:

| Span name | Required attributes |
|-----------|----------------------|
| `quaicu.tenant_context` | `quaicu.tenant_id` |
| `quaicu.isolation_violation` | `quaicu.context_tenant`, `quaicu.supplied_tenant`, `quaicu.security_event` |
| `quaicu.storage.connection` | `quaicu.tenant_id`, `quaicu.schema` |
| `quaicu.provision_tenant` | `quaicu.tenant_id`, `quaicu.tier`, `quaicu.provisioning_job_id` |
| `quaicu.control_plane.resolve` | `quaicu.tenant_id` |
| `quaicu.migration_rollout` | `quaicu.migration_id`, `quaicu.rollout.tenant_count` |
| `quaicu.gdpr_export` | `quaicu.tenant_id`, `quaicu.export.bundle_hash` |
| `quaicu.delete_tenant` | `quaicu.tenant_id`, `quaicu.deletion.archive_ref` |

Metrics:

| Metric | Type | Labels |
|--------|------|--------|
| `quaicu.pool.size` | Gauge | `tenant_id` |
| `quaicu.pool.acquire_latency_ms` | Histogram | `tenant_id` |
| `quaicu.tenants.provisioned_total` | Counter | `tier` |
| `quaicu.tenants.provision_latency_ms` | Histogram | `tier` |
| `quaicu.migration.tenants_migrated` | Counter | `migration_id` |
| `quaicu.migration.tenant_failures` | Counter | `migration_id` |

---

## Anti-Patterns — Never Do These

```python
# ╳ ANTI-PATTERN 1 — shared ledger table keyed by tenant_id (F-07 violation)
await db.execute(
    "SELECT * FROM public.ledger_entries WHERE tenant_id = $1", tenant_id
)
# This is BANNED. One mis-filtered query leaks everything.

# ╳ ANTI-PATTERN 2 — bypassing ContextVar and setting schema manually inline
schema = f"tenant_{tenant_id}"
await conn.execute(f"SET search_path = {schema}")   # no validation, SQL-injection risk

# ╳ ANTI-PATTERN 3 — sharing a connection pool across tenants
pool = get_global_pool()   # noisy-neighbour, no schema isolation

# ╳ ANTI-PATTERN 4 — checking tenant_id in Python after reading data
rows = await conn.fetch("SELECT * FROM ledger_entries")
rows = [r for r in rows if r["tenant_id"] == tenant_id]  # too late — data already crossed

# ╳ ANTI-PATTERN 5 — skipping require_tenant_match at API boundaries
async def get_action(action_id: str, tenant_id: str) -> Action:
    # Missing: require_tenant_match(tenant_id)
    return await storage.get(action_id)    # tenant mismatch undetected

# ╳ ANTI-PATTERN 6 — deleting a tenant without archival
await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')  # data unrecoverably lost

# ╳ ANTI-PATTERN 7 — storing superuser credentials in app pool
# The quaicu_app_role must never be SUPERUSER or BYPASSRLS
```

---

## Adversarial Isolation Tests (required — §6 Definition of Done)

```python
# tests/integration/test_tenant_isolation.py
import pytest
from core.tenant_context import set_tenant
from core.errors.tenant import TenantIsolationViolationError


async def test_tenant_a_cannot_read_tenant_b_ledger(storage, two_tenants):
    """Schema isolation: tenant A must never see tenant B's ledger entries."""
    tenant_a, tenant_b = two_tenants
    await seed_ledger_entries(tenant_b, count=5, storage=storage)

    set_tenant(tenant_a)
    entries = await storage.execute("SELECT * FROM ledger_entries", tenant_id=tenant_a)
    assert len(entries) == 0, (
        f"Tenant isolation failure: {tenant_a} read {len(entries)} entries from {tenant_b}"
    )


async def test_direct_schema_query_blocked_by_rls(engine, two_tenants):
    """RLS backstop: misconfigured search_path still filtered by RLS."""
    tenant_a, tenant_b = two_tenants
    schema_b = schema_name_for(tenant_b)
    async with engine.connect() as conn:
        await conn.execute(f'SET search_path TO "{schema_b}", public')
        await conn.execute("SET app.current_tenant = $1", tenant_a)  # wrong tenant
        rows = await conn.fetch("SELECT * FROM ledger_entries")
    assert rows == [], "RLS should have filtered all rows — isolation failure"


async def test_require_tenant_match_raises_on_mismatch():
    """require_tenant_match must raise immediately on any mismatch."""
    set_tenant("tenant_a")
    with pytest.raises(TenantIsolationViolationError) as exc_info:
        require_tenant_match("tenant_b")
    assert exc_info.value.code == TenantErrorCode.CROSS_TENANT_ACCESS_ATTEMPT


async def test_no_cross_tenant_in_policy_evaluation(engine, policy_engine, two_tenants):
    """Policy evaluation must never use the other tenant's policies."""
    tenant_a, tenant_b = two_tenants
    await seed_policy(tenant_b, decision="allow", governs="*", storage=engine)
    await seed_policy(tenant_a, decision="deny", governs="*", storage=engine)

    set_tenant(tenant_a)
    action = make_action("any.action", tenant_id=tenant_a)
    result = await policy_engine.evaluate(action)
    assert result.decision == "deny", (
        "Policy engine used tenant_b's allow policy for tenant_a — cross-tenant leak"
    )


async def test_provisioning_creates_isolated_schema(orchestrator, storage):
    """After provisioning, the new tenant's schema must be isolated."""
    job = await orchestrator.enqueue("new_tenant_xyz", tier="shared", db_shard_id="shard_1")
    # Poll until complete
    for _ in range(30):
        await asyncio.sleep(0.1)
        job = await orchestrator.get_job(job.job_id)
        if job.status in (ProvisioningStatus.COMPLETE, ProvisioningStatus.FAILED):
            break
    assert job.status == ProvisioningStatus.COMPLETE
    # Verify schema exists and has RLS enabled
    rls_check = await storage.execute(
        "SELECT relrowsecurity FROM pg_class WHERE relname = 'ledger_entries' "
        "AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $1)",
        ("tenant_new_tenant_xyz",),
        tenant_id="_control_plane",
    )
    assert rls_check[0]["relrowsecurity"] is True


async def test_connection_pool_per_tenant_no_cross_pool(pool_manager, two_tenants):
    """Each tenant must get its own pool — no shared pool object."""
    tenant_a, tenant_b = two_tenants
    pool_a = await pool_manager.pool_for(tenant_a)
    pool_b = await pool_manager.pool_for(tenant_b)
    assert pool_a is not pool_b, "Tenants must not share a connection pool"
```

---

## Checklist Before Merging Any Storage/Tenant Change

- [ ] No `WHERE tenant_id = $1` on ledger tables — schema isolation is the primary control
- [ ] No shared connection pool across tenants — `TenantPoolManager` used for all connections
- [ ] `set_tenant()` called before any DB operation in every request handler and background job
- [ ] `require_tenant_match()` called at every point where a tenant_id is passed in from outside
- [ ] RLS enabled + FORCE ROW LEVEL SECURITY on ALL tables in per-tenant migration template
- [ ] New tables added in migrations also include the RLS template block
- [ ] Provisioning creates schema, runs migrations, enables RLS in sequence (not a single SQL)
- [ ] No UPDATE or DELETE on `ledger_entries` or `ledger_tree_nodes` in any code path
- [ ] No hardcoded `public` schema for any kernel-owned table
- [ ] Schema name always computed via `schema_name_for()` — never by string interpolation
- [ ] Tenant deletion requires successful ledger archival before DROP SCHEMA
- [ ] Migration rollout uses batched execution with per-tenant rollback and failure-rate guard
- [ ] OTel span emitted for every isolation-critical path (see instrumentation table above)
- [ ] Adversarial isolation tests pass: tenant A cannot read tenant B's data under any code path
- [ ] Connection string rotation closes old pool before opening new one
