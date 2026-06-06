---
name: saas-multi-tenant
description: "Design and implement multi-tenant SaaS architectures with row-level security, tenant-scoped queries, shared-schema isolation, and safe cross-tenant admin patterns in PostgreSQL and TypeScript. QUAICU kernel — defaults to schema-per-tenant (not shared-schema RLS); per-tenant ledger always (F-07), RLS as defense-in-depth, ContextVar + SET LOCAL per transaction, all-or-nothing onboarding with rollback. Triggers — QUAICU, schema-per-tenant, tenant isolation, RLS, F-07, onboard tenant, control plane."
risk: safe
source: community
date_added: "2026-03-28"
tags: [multi-tenancy, saas, row-level-security, postgresql, tenant-isolation]
tools: [claude, cursor, gemini]
---

# SaaS Multi-Tenant Architecture

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific multi-tenancy choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** QUAICU defaults to SCHEMA-per-tenant, not shared-schema RLS. Missing rule → refuse the cross-tenant operation.

### Invariants — never violated
- Default is schema-per-tenant (`"tenant_{id}"`), NOT a shared table with a `tenant_id` column. The ledger is per-tenant always (F-07).
- RLS is enabled on every kernel table as defense-in-depth ON TOP of schema separation — three layers (schema + pool + RLS) all hold.
- Tenant is set per transaction via ContextVar + `SET LOCAL search_path` + `SET LOCAL app.current_tenant`. App-level `WHERE tenant_id=` is never the boundary.
- Ledger tables are append-only (no UPDATE/DELETE policy). Onboarding is all-or-nothing with rollback.
- Sanitize tenant ids used in schema names (`^[a-z0-9_]+$`); reject otherwise.

### Decision table
| Situation | Do exactly this |
|---|---|
| Cross-tenant data observed | raise critical error, halt, alert |
| Non-ACTIVE tenant | refuse the operation (fail-closed) |
| Tenant onboarding | create schema → migrate → RLS+policies → register; rollback on any failure |
| Tenant deletion | archive ledger to cold storage first, then drop schema |
| GDPR export (Art. 20) | only that tenant's tables + manifest |

### Tie-break rules
- Shared-schema-RLS (the generic SaaS default) vs schema-per-tenant? → schema-per-tenant for QUAICU.
- Is RLS redundant with schemas? → keep it; mandatory defense-in-depth.

### Self-check
- [ ] Schema-per-tenant; per-tenant ledger; no shared kernel tables.
- [ ] RLS on every table; ledger append-only.
- [ ] Tenant via ContextVar + SET LOCAL per txn.
- [ ] Schema names sanitized; non-ACTIVE refused; onboarding rolls back.

---

## When to Use This Skill

- The user is building a SaaS application where multiple customers share the same database
- The user asks about tenant isolation, row-level security, or data leakage prevention
- The user needs to scope every database query to a specific tenant without manual WHERE clauses
- The user asks about shared-schema vs schema-per-tenant vs database-per-tenant tradeoffs
- The user is implementing admin endpoints that must access data across tenants
- The user needs to add `tenant_id` columns to an existing single-tenant application
- The user asks about PostgreSQL RLS policies for tenant isolation
- The user is building tenant-aware middleware in Express, Fastify, or Next.js API routes

Do NOT use this skill when:
- The user is building a single-user application with no shared infrastructure
- The user asks about authentication only without tenant scoping (use an auth skill instead)
- The user needs general database schema design without multi-tenancy requirements

## Core Workflow

1. Determine the tenancy model. Ask the user about their scale expectations and isolation requirements. For most SaaS apps under 1000 tenants, shared-schema with a `tenant_id` column on every table is the correct default. Schema-per-tenant adds operational overhead (migrations run N times). Database-per-tenant is only justified when tenants have regulatory data residency requirements.

2. Add `tenant_id` to every tenant-scoped table. The column must be `NOT NULL`, type `UUID` or `TEXT`, and included in every composite index. Never allow a tenant-scoped table to exist without this column — a missing `tenant_id` is a data leak waiting to happen.

3. Set up PostgreSQL Row-Level Security (RLS). Create a policy on each tenant-scoped table that filters rows by `current_setting('app.current_tenant_id')`. This acts as a database-level safety net — even if application code forgets a WHERE clause, RLS blocks cross-tenant reads.

4. Build tenant-aware middleware. At the start of every request, extract the `tenant_id` from the authenticated session or JWT claims. Set it on the database connection using `SET LOCAL app.current_tenant_id = '...'` inside a transaction. Every subsequent query in that request inherits the tenant scope automatically.

5. Scope all ORM queries by tenant. If using Prisma, apply a global middleware that injects `where: { tenantId }` into every `findMany`, `findFirst`, `update`, and `delete` call. If using Drizzle, create a base query builder that includes the tenant filter. Never rely on developers remembering to add the filter manually.

6. Handle tenant-aware migrations. Every new table migration must include `tenant_id` as a column. Write a linting rule or CI check that rejects any migration creating a table without `tenant_id` unless the table is explicitly marked as global (e.g., `plans`, `feature_flags`).

7. Build cross-tenant admin routes separately. Admin endpoints that aggregate data across tenants must bypass RLS explicitly using `SET LOCAL role = 'admin_bypass'` or a dedicated database role. These routes must be protected by a separate admin authentication flow — never reuse tenant user sessions for admin access.

8. Implement tenant provisioning. When a new customer signs up, create their tenant record, seed default data (roles, settings, onboarding state), and assign the founding user. Wrap this in a database transaction so partial provisioning never leaves orphan records.

## Examples

### Example 1: PostgreSQL RLS Policy for Tenant Isolation

```sql
-- Enable RLS on the table
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;

-- Policy: users can only see rows where tenant_id matches the session variable
CREATE POLICY tenant_isolation ON projects
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Policy for INSERT: new rows must match the current tenant
CREATE POLICY tenant_insert ON projects
  FOR INSERT
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

### Example 2: Express Middleware That Sets Tenant Context per Request

```typescript
import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

async function tenantMiddleware(req, res, next) {
  const tenantId = req.auth?.tenantId; // extracted from JWT during auth
  if (!tenantId) return res.status(403).json({ error: "No tenant context" });

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // Use set_config — SET LOCAL does not accept bind placeholders ($1)
    await client.query("SELECT set_config('app.current_tenant_id', $1, true)", [tenantId]);
    req.db = client;
    req.tenantId = tenantId;

    // Cleanup on response finish — guarantees release even if handler skips next()
    res.on("finish", async () => {
      try { await client.query("COMMIT"); } catch { await client.query("ROLLBACK"); }
      client.release();
    });

    next();
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    client.release();
    next(err);
  }
}
```

### Example 3: Prisma Middleware for Automatic Tenant Scoping

```typescript
import { PrismaClient } from "@prisma/client";

// Tables that do NOT have tenant_id (global tables)
const GLOBAL_TABLES = new Set(["Plan", "FeatureFlag", "SystemConfig"]);

function createTenantPrisma(tenantId: string): PrismaClient {
  const prisma = new PrismaClient();

  prisma.$use(async (params, next) => {
    if (GLOBAL_TABLES.has(params.model ?? "")) return next(params);

    // Initialize args.where — Prisma passes undefined args for calls like findMany()
    params.args = params.args ?? {};
    params.args.where = params.args.where ?? {};

    // Inject tenant filter on reads (skip findUnique — it only accepts unique-field selectors)
    if (["findMany", "findFirst", "count", "aggregate"].includes(params.action)) {
      params.args.where = { ...params.args.where, tenantId };
    }

    // Inject tenant_id on creates
    if (["create", "createMany"].includes(params.action)) {
      params.args.data = params.args.data ?? {};
      if (params.action === "createMany") {
        params.args.data = params.args.data.map((d: any) => ({ ...d, tenantId }));
      } else {
        params.args.data = { ...params.args.data, tenantId };
      }
    }

    // Scope updates and deletes
    if (["update", "updateMany", "delete", "deleteMany"].includes(params.action)) {
      params.args.where = { ...params.args.where, tenantId };
    }

    return next(params);
  });

  return prisma;
}
```

## Never Do This

1. **Never query a tenant-scoped table without a `tenant_id` filter.** Even if your ORM middleware handles it, raw SQL queries bypass middleware entirely. Every raw query must include `WHERE tenant_id = $1` or rely on RLS. A single unscoped `SELECT * FROM invoices` leaks every customer's billing data.

2. **Never store `tenant_id` only in the application session without enforcing it at the database level.** Application-layer filtering is a suggestion. RLS is enforcement. If a bug in your middleware skips the tenant filter, only RLS prevents the data leak. Run both layers.

3. **Never use auto-incrementing integer IDs for tenant-scoped resources.** Sequential IDs (`invoice #1042`) let attackers enumerate other tenants' resources by incrementing the ID. Use UUIDs for all tenant-scoped primary keys. Reserve integer IDs for internal-only tables.

4. **Never let tenant users access admin aggregation endpoints.** A route like `GET /admin/metrics` that queries across all tenants must never be reachable with a regular tenant JWT. Use a separate authentication mechanism (API key, admin role claim with a different issuer) for cross-tenant routes.

5. **Never run migrations with RLS enabled on the migration connection.** The migration user needs to create tables, add columns, and modify policies. If RLS is active on the migration connection, `ALTER TABLE` commands may silently fail or affect only the "current tenant's" view. Use a dedicated superuser or `bypassrls` role for migrations.

6. **Never share connection pools across tenants when using `SET LOCAL`.** If you use `SET LOCAL app.current_tenant_id` inside a transaction, that setting is scoped to the transaction. But if a previous request's transaction was not properly committed or rolled back, the connection returns to the pool with stale tenant context. Always `RESET app.current_tenant_id` in the cleanup path.

## Edge Cases

1. **Tenant deletion and data retention.** When a tenant cancels their subscription, you cannot simply `DELETE FROM tenants WHERE id = $1`. Foreign key cascades may time out on large datasets. Instead, soft-delete the tenant (set `deleted_at`), revoke all user sessions, then run a background job that deletes tenant data in batches over hours or days.

2. **Tenant data export for GDPR/compliance.** When a tenant requests a full data export, you need to query every tenant-scoped table for that `tenant_id` and package it. Build a registry of all tenant-scoped tables (parse your migration files or maintain a manifest) so the export job doesn't miss tables added after the export feature was built.

3. **Shared resources between tenants.** Some features require shared state — e.g., a marketplace where Tenant A's products are visible to Tenant B's users. These tables need a different RLS policy: read access is public (no tenant filter), but write access is still scoped to the owning tenant. Model these as `owner_tenant_id` instead of `tenant_id`.

4. **Tenant-aware background jobs.** When a cron job or queue worker processes tasks, there is no HTTP request to extract `tenant_id` from. The job payload must include `tenant_id`, and the worker must set the database session variable before processing. Never run background jobs without tenant context — they will either fail on RLS or bypass it entirely.

5. **Connection pool exhaustion with schema-per-tenant.** If you use one PostgreSQL schema per tenant and each schema requires its own connection pool, 500 tenants means 500 pools. This exhausts `max_connections` fast. Use a connection pooler like PgBouncer in transaction mode, or switch to shared-schema before hitting this wall.

## Best Practices

1. **Create a `tenants` table as the single source of truth.** Every `tenant_id` foreign key in every table points back to `tenants.id`. Include columns for `name`, `slug` (for subdomain routing), `plan_id`, `created_at`, and `deleted_at`. This table is the root of your entire data model.

2. **Index `tenant_id` as the first column in every composite index.** PostgreSQL uses leftmost prefix matching for composite indexes. An index on `(tenant_id, created_at)` serves both "all items for tenant X" and "items for tenant X sorted by date." An index on `(created_at, tenant_id)` only helps date-range queries across all tenants.

3. **Use subdomains or path prefixes for tenant routing.** `acme.yourapp.com` or `yourapp.com/org/acme` — both work. Map the subdomain or path to a `tenant_id` lookup at the edge (middleware or reverse proxy). This lookup should be cached (Redis or in-memory with 60s TTL) since it runs on every single request.

4. **Separate tenant-scoped tables from global tables explicitly.** Maintain a list (code constant or database table) of which tables are global (no `tenant_id`) and which are tenant-scoped. Use this list in your ORM middleware, your migration linter, and your data export job. If a table isn't in either list, the CI check should fail.

5. **Test with at least 3 tenants in your seed data.** A single tenant in development hides every multi-tenancy bug. Two tenants hides bugs where the first tenant's data leaks to the second but not vice versa. Three tenants catches ordering and filtering bugs that only appear with multiple peers.

6. **Rate-limit and quota per tenant, not globally.** A global rate limit of 1000 requests/minute means one noisy tenant can exhaust the quota for everyone. Implement per-tenant rate limiting using a Redis key pattern like `ratelimit:{tenant_id}:{endpoint}` with a sliding window counter.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.

---

# QUAICU Governance Kernel — Multi-Tenancy Implementation Guide

This section is the canonical reference for schema-per-tenant multi-tenancy in the QUAICU governance kernel. The spec (§3.10) mandates schema-per-tenant as the default for the shared tier, with RLS as defense-in-depth. The ledger is always per-tenant tables — never a shared ledger table keyed by `tenant_id` (ADR F-07).

## 1. Tenancy Tiers and Isolation Model

| Tier | Database | Schema | Isolation basis | Notes |
|------|----------|--------|-----------------|-------|
| Sovereign | Dedicated DB, customer's hardware | n/a (single tenant) | Physical | Air-gapped installs; one tenant, one DB instance |
| Dedicated | One DB instance per tenant in their VPC | n/a (single tenant) | Instance | Bank/regulated; customer controls their instance |
| Shared (QUAICU-hosted) | Shared PostgreSQL instance | Schema-per-tenant | Schema + RLS | Small customers, QUAICU manages the host |

The kernel's multi-tenancy logic applies only to the Shared tier. Sovereign and Dedicated tiers are single-tenant — no schema isolation logic needed in those deployments.

---

## 2. Control Plane Tenant Registry Schema

The control plane lives in a dedicated `_quaicu_control` schema (or a separate database for larger deployments). It records every tenant, their database placement, and their current lifecycle state.

```sql
-- migrations/control_plane/001_tenant_registry.sql

CREATE SCHEMA IF NOT EXISTS _quaicu_control;

CREATE TABLE _quaicu_control.tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,           -- used as the PostgreSQL schema name
    display_name    TEXT NOT NULL,
    tier            TEXT NOT NULL CHECK (tier IN ('sovereign', 'dedicated', 'shared')),
    db_shard_id     TEXT NOT NULL,                  -- which DB shard this tenant is on
    schema_name     TEXT NOT NULL UNIQUE,           -- e.g. "tenant_acme_bank"
    state           TEXT NOT NULL DEFAULT 'PROVISIONING'
                        CHECK (state IN ('PROVISIONING', 'ACTIVE', 'SUSPENDED', 'DELETING', 'DELETED')),
    adapter_config  JSONB NOT NULL DEFAULT '{}',    -- inference, hitl, identity, workflow adapter selections
    policy_packs    TEXT[] NOT NULL DEFAULT '{}',   -- loaded content packs for this tenant
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at    TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    CONSTRAINT slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{1,61}[a-z0-9]$')
);

CREATE INDEX idx_tenants_shard ON _quaicu_control.tenants (db_shard_id);
CREATE INDEX idx_tenants_state  ON _quaicu_control.tenants (state) WHERE state != 'DELETED';

-- DB shard registry: maps shard_id → connection DSN (DSN itself stored in OpenBao)
CREATE TABLE _quaicu_control.db_shards (
    id              TEXT PRIMARY KEY,
    openbao_path    TEXT NOT NULL,                  -- path in OpenBao where the DSN is stored
    region          TEXT,
    max_tenants     INT NOT NULL DEFAULT 200,
    current_tenants INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 3. Per-Tenant Schema Structure

Each tenant gets its own PostgreSQL schema. Every kernel table is created inside that schema. The schema name is derived from the tenant slug: `tenant_<slug>`.

```sql
-- Template DDL for a tenant schema (executed by the provisioning service)
-- This runs inside migrations/tenant_template/

CREATE SCHEMA IF NOT EXISTS tenant_{{slug}};

-- Search path is set per connection — never changed globally
-- SET search_path = tenant_{{slug}};

-- ── Actions table ────────────────────────────────────────────────────────────
CREATE TABLE tenant_{{slug}}.actions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type                TEXT NOT NULL,
    payload             JSONB NOT NULL,
    actor_id            TEXT NOT NULL,
    idempotency_key     UUID NOT NULL UNIQUE,
    state               TEXT NOT NULL DEFAULT 'PROPOSED'
                            CHECK (state IN ('PROPOSED','EVALUATING','PENDING_APPROVAL',
                                             'APPROVED','EXECUTING','SEALED','EMITTED',
                                             'DENIED','HALTED','REJECTED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Policy evaluations (for replay) ─────────────────────────────────────────
CREATE TABLE tenant_{{slug}}.policy_evaluations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id           UUID NOT NULL REFERENCES tenant_{{slug}}.actions(id),
    policy_id           TEXT NOT NULL,
    policy_version      INT NOT NULL,
    decision            TEXT NOT NULL CHECK (decision IN ('ALLOW','DENY','REQUIRE_APPROVAL')),
    cel_expression      TEXT NOT NULL,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── TrustLedger — RFC 6962-style transparency log ───────────────────────────
-- Per ADR F-07: ledger is always per-tenant tables, NEVER a shared table.
CREATE TABLE tenant_{{slug}}.ledger_entries (
    seq                 BIGSERIAL PRIMARY KEY,          -- monotonic sequence within tenant
    action_id           UUID NOT NULL UNIQUE,
    action_type         TEXT NOT NULL,
    action_payload      JSONB NOT NULL,                 -- captured for replay (spec §3.13)
    actor_id            TEXT NOT NULL,
    policy_versions     JSONB NOT NULL,                 -- all versions evaluated
    evaluation_result   TEXT NOT NULL,
    consent_state       TEXT NOT NULL,
    assurance_signals   JSONB NOT NULL DEFAULT '{}',    -- K·08–K·11 outputs
    leaf_hash           BYTEA NOT NULL,
    tree_size           BIGINT NOT NULL,
    root_hash           BYTEA NOT NULL,
    proof_path          BYTEA[] NOT NULL,
    sealed_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ledger_action_id ON tenant_{{slug}}.ledger_entries (action_id);
CREATE INDEX idx_ledger_sealed_at ON tenant_{{slug}}.ledger_entries (sealed_at);

-- ── HITL approvals ───────────────────────────────────────────────────────────
CREATE TABLE tenant_{{slug}}.hitl_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id           UUID NOT NULL REFERENCES tenant_{{slug}}.actions(id),
    approvers           JSONB NOT NULL,
    outcome             TEXT CHECK (outcome IN ('APPROVED','REJECTED','TIMED_OUT')),
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at          TIMESTAMPTZ,
    decided_by          TEXT
);

-- ── Consent records (K·04) ───────────────────────────────────────────────────
CREATE TABLE tenant_{{slug}}.consent_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_subject_id     TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    legal_basis         TEXT NOT NULL,
    state               TEXT NOT NULL CHECK (state IN ('GRANTED','WITHDRAWN')),
    granted_at          TIMESTAMPTZ,
    withdrawn_at        TIMESTAMPTZ,
    recorded_action_id  UUID REFERENCES tenant_{{slug}}.actions(id)
);

CREATE INDEX idx_consent_subject ON tenant_{{slug}}.consent_records (data_subject_id);
```

---

## 4. Row-Level Security — Full Policy Statements

RLS is a defense-in-depth layer even under schema-per-tenant. Enable it on every table so that a schema-path misconfiguration cannot leak data to a connection that has the wrong search_path.

```sql
-- Run for each tenant schema after creating tables.
-- Replace tenant_{{slug}} with the actual schema name.

-- ── actions ──────────────────────────────────────────────────────────────────
ALTER TABLE tenant_{{slug}}.actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_{{slug}}.actions FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_actions_select ON tenant_{{slug}}.actions
    FOR SELECT
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_actions_insert ON tenant_{{slug}}.actions
    FOR INSERT
    WITH CHECK (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_actions_update ON tenant_{{slug}}.actions
    FOR UPDATE
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

-- ── ledger_entries (append-only; no UPDATE or DELETE policies) ───────────────
ALTER TABLE tenant_{{slug}}.ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_{{slug}}.ledger_entries FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_ledger_select ON tenant_{{slug}}.ledger_entries
    FOR SELECT
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_ledger_insert ON tenant_{{slug}}.ledger_entries
    FOR INSERT
    WITH CHECK (current_setting('quaicu.current_tenant', true) = '{{slug}}');

-- No UPDATE or DELETE policy — ledger is append-only.
-- Any attempt to UPDATE/DELETE ledger_entries will be rejected by RLS.

-- ── hitl_requests ────────────────────────────────────────────────────────────
ALTER TABLE tenant_{{slug}}.hitl_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_{{slug}}.hitl_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_hitl_select ON tenant_{{slug}}.hitl_requests
    FOR SELECT
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_hitl_insert ON tenant_{{slug}}.hitl_requests
    FOR INSERT
    WITH CHECK (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_hitl_update ON tenant_{{slug}}.hitl_requests
    FOR UPDATE
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

-- ── consent_records ──────────────────────────────────────────────────────────
ALTER TABLE tenant_{{slug}}.consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_{{slug}}.consent_records FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_consent_select ON tenant_{{slug}}.consent_records
    FOR SELECT
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_consent_insert ON tenant_{{slug}}.consent_records
    FOR INSERT
    WITH CHECK (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_consent_update ON tenant_{{slug}}.consent_records
    FOR UPDATE
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

-- ── policy_evaluations ───────────────────────────────────────────────────────
ALTER TABLE tenant_{{slug}}.policy_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_{{slug}}.policy_evaluations FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_eval_select ON tenant_{{slug}}.policy_evaluations
    FOR SELECT
    USING (current_setting('quaicu.current_tenant', true) = '{{slug}}');

CREATE POLICY rls_eval_insert ON tenant_{{slug}}.policy_evaluations
    FOR INSERT
    WITH CHECK (current_setting('quaicu.current_tenant', true) = '{{slug}}');
```

---

## 5. Tenant ContextVar Enforcement in Python

Use a Python `contextvars.ContextVar` as the in-process tenant guard. Every async task that runs in the kernel must have this set before it touches the database. It is not a substitute for schema isolation and RLS — it is the first line of defense in the application layer.

```python
# core/tenant_context.py
from __future__ import annotations

from contextvars import ContextVar
from typing import AsyncGenerator
from contextlib import asynccontextmanager

_CURRENT_TENANT: ContextVar[str | None] = ContextVar("quaicu_tenant", default=None)


def get_current_tenant() -> str:
    """
    Return the active tenant slug for the current async context.
    Raises if no tenant is set — fail-closed: operations without tenant context are denied.
    """
    tenant = _CURRENT_TENANT.get()
    if tenant is None:
        raise RuntimeError(
            "No tenant context set. All kernel operations require an active tenant. "
            "Use set_tenant_context() before any database or lifecycle call."
        )
    return tenant


@asynccontextmanager
async def set_tenant_context(tenant_slug: str) -> AsyncGenerator[None, None]:
    """
    Async context manager that sets the tenant for the duration of the block.
    Resets to None on exit — no tenant context leaks to the next coroutine.

    Usage:
        async with set_tenant_context("tenant-acme-bank"):
            result = await propose_action(action, ports=ports)
    """
    token = _CURRENT_TENANT.set(tenant_slug)
    try:
        yield
    finally:
        _CURRENT_TENANT.reset(token)


def require_tenant_matches(expected_slug: str) -> None:
    """
    Assert that the current async context's tenant matches expected_slug.
    Call this at the start of any function that accepts a tenant parameter
    to guard against mismatched context.
    """
    actual = get_current_tenant()
    if actual != expected_slug:
        raise PermissionError(
            f"Tenant context mismatch: context={actual!r}, parameter={expected_slug!r}. "
            "Tenant isolation violation prevented."
        )
```

---

## 6. Per-Tenant asyncpg Connection Pool

Each tenant gets a connection pool whose connections always set `search_path` and the `quaicu.current_tenant` session variable before any query. The pool is created lazily on first use and cached in the control plane.

```python
# adapters/storage/tenant_pool.py
from __future__ import annotations

import asyncio
import asyncpg
from typing import AsyncGenerator
from contextlib import asynccontextmanager

_POOLS: dict[str, asyncpg.Pool] = {}
_POOL_LOCK = asyncio.Lock()


async def get_tenant_pool(
    tenant_slug: str,
    dsn: str,
    *,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """
    Return (creating if necessary) the asyncpg pool for tenant_slug.
    Each connection in the pool has search_path set to the tenant's schema.
    """
    if tenant_slug not in _POOLS:
        async with _POOL_LOCK:
            if tenant_slug not in _POOLS:
                schema = f"tenant_{tenant_slug}"
                pool = await asyncpg.create_pool(
                    dsn,
                    min_size=min_size,
                    max_size=max_size,
                    init=_make_init(schema, tenant_slug),
                )
                _POOLS[tenant_slug] = pool
    return _POOLS[tenant_slug]


def _make_init(schema: str, tenant_slug: str):
    async def init(conn: asyncpg.Connection) -> None:
        # Set search_path so unqualified table names resolve to the tenant schema.
        # Also set the RLS guard variable.
        await conn.execute(
            f"SET search_path = {schema}, public; "
            f"SET quaicu.current_tenant = '{tenant_slug}';"
        )
    return init


@asynccontextmanager
async def tenant_connection(tenant_slug: str, dsn: str) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Acquire a connection from the tenant's pool, wrapped in a transaction.
    The search_path and RLS variable are guaranteed to be correct.
    """
    pool = await get_tenant_pool(tenant_slug, dsn)
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


async def close_tenant_pool(tenant_slug: str) -> None:
    """
    Gracefully close and remove the pool for a tenant (used during tenant deletion).
    """
    pool = _POOLS.pop(tenant_slug, None)
    if pool:
        await pool.close()
```

---

## 7. Full Tenant Onboarding Flow

Onboarding is a multi-step transaction. If any step fails, the whole onboarding rolls back so no orphan schema or partial record is left.

```python
# core/tenancy/onboarding.py
from __future__ import annotations

import asyncpg
from dataclasses import dataclass


@dataclass
class TenantOnboardingRequest:
    slug: str
    display_name: str
    tier: str
    db_shard_id: str
    adapter_config: dict
    policy_packs: list[str]


async def onboard_tenant(
    request: TenantOnboardingRequest,
    *,
    control_conn: asyncpg.Connection,
    shard_dsn: str,
) -> str:
    """
    Full tenant onboarding sequence. Returns the new tenant_id on success.

    Steps:
    1. Register in control plane (state=PROVISIONING)
    2. Create tenant schema on shard DB
    3. Run Alembic migrations for tenant schema
    4. Enable RLS on all kernel tables
    5. Create RLS policies
    6. Mark tenant ACTIVE in control plane

    All DDL steps run in the shard connection; the control-plane update
    is held until all DDL succeeds. On any failure, control record is
    deleted (no orphan).
    """
    schema_name = f"tenant_{request.slug}"

    # Step 1: register in control plane (PROVISIONING)
    async with control_conn.transaction():
        tenant_id = await control_conn.fetchval(
            """
            INSERT INTO _quaicu_control.tenants
                (slug, display_name, tier, db_shard_id, schema_name, adapter_config, policy_packs)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            request.slug,
            request.display_name,
            request.tier,
            request.db_shard_id,
            schema_name,
            request.adapter_config,
            request.policy_packs,
        )

    shard_conn = await asyncpg.connect(shard_dsn)
    try:
        # Step 2: create schema
        await shard_conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

        # Step 3: run Alembic migrations scoped to this schema
        await _run_tenant_migrations(schema_name, shard_dsn)

        # Step 4 + 5: enable RLS and create policies
        await _enable_rls(shard_conn, schema_name, request.slug)

        # Step 6: mark ACTIVE
        await control_conn.execute(
            """
            UPDATE _quaicu_control.tenants
               SET state = 'ACTIVE', activated_at = now()
             WHERE id = $1
            """,
            tenant_id,
        )
        return str(tenant_id)

    except Exception:
        # Rollback: remove partial schema and control record
        await shard_conn.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        await control_conn.execute(
            "DELETE FROM _quaicu_control.tenants WHERE id = $1", tenant_id
        )
        raise

    finally:
        await shard_conn.close()


async def _run_tenant_migrations(schema_name: str, dsn: str) -> None:
    """
    Run Alembic migrations for a single tenant schema.
    Alembic uses a per-schema version table so migrations are tracked independently.
    """
    import subprocess
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        env={
            "DATABASE_URL": dsn,
            "ALEMBIC_SCHEMA": schema_name,
        },
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migration failed for schema {schema_name!r}: {result.stderr}"
        )


KERNEL_TABLES = [
    "actions",
    "policy_evaluations",
    "ledger_entries",
    "hitl_requests",
    "consent_records",
]

RLS_POLICIES = {
    "actions": ["SELECT", "INSERT", "UPDATE"],
    "policy_evaluations": ["SELECT", "INSERT"],
    "ledger_entries": ["SELECT", "INSERT"],   # no UPDATE/DELETE — append-only
    "hitl_requests": ["SELECT", "INSERT", "UPDATE"],
    "consent_records": ["SELECT", "INSERT", "UPDATE"],
}


async def _enable_rls(
    conn: asyncpg.Connection,
    schema_name: str,
    tenant_slug: str,
) -> None:
    """Enable RLS and create all policies for a tenant schema."""
    for table in KERNEL_TABLES:
        fqt = f"{schema_name}.{table}"
        await conn.execute(f"ALTER TABLE {fqt} ENABLE ROW LEVEL SECURITY")
        await conn.execute(f"ALTER TABLE {fqt} FORCE ROW LEVEL SECURITY")

        ops = RLS_POLICIES[table]
        for op in ops:
            policy_name = f"rls_{table}_{op.lower()}"
            if op == "INSERT":
                await conn.execute(
                    f"""
                    CREATE POLICY {policy_name} ON {fqt}
                        FOR INSERT
                        WITH CHECK (
                            current_setting('quaicu.current_tenant', true) = '{tenant_slug}'
                        )
                    """
                )
            else:
                await conn.execute(
                    f"""
                    CREATE POLICY {policy_name} ON {fqt}
                        FOR {op}
                        USING (
                            current_setting('quaicu.current_tenant', true) = '{tenant_slug}'
                        )
                    """
                )
```

---

## 8. Dynamic Alembic Per-Tenant Migration

Alembic's `env.py` must support targeting a single tenant schema. Use the `ALEMBIC_SCHEMA` environment variable.

```python
# migrations/env.py
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
fileConfig(config.config_file_name)

target_schema = os.environ.get("ALEMBIC_SCHEMA", "public")


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=os.environ["DATABASE_URL"],
    )

    with connectable.connect() as connection:
        # Set search_path to the target schema BEFORE running migrations
        connection.execute(f"SET search_path = {target_schema}")
        connection.execute(f"SET quaicu.current_tenant = 'migration_bypass'")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=f"alembic_version",  # one version table per schema
            version_table_schema=target_schema,
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()
```

---

## 9. Batched Migration Rollout Across All Tenants

When a migration must be applied to all tenants (e.g., adding a new column to the ledger), run it in batches with rollback on first failure.

```python
# core/tenancy/migration_rollout.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RolloutResult:
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.succeeded) + len(self.failed)

    @property
    def is_clean(self) -> bool:
        return len(self.failed) == 0


async def rollout_migration_to_all_tenants(
    migration_revision: str,
    *,
    control_conn,
    get_shard_dsn,
    batch_size: int = 10,
    stop_on_first_failure: bool = True,
) -> RolloutResult:
    """
    Apply an Alembic migration to every ACTIVE tenant schema, in batches.

    On failure, logs the failing tenant and either continues (stop_on_first_failure=False)
    or halts and returns a partial result for remediation.

    Safe to re-run — Alembic is idempotent (already-applied revisions are no-ops).
    """
    tenants = await control_conn.fetch(
        "SELECT slug, schema_name, db_shard_id FROM _quaicu_control.tenants WHERE state = 'ACTIVE'"
    )

    result = RolloutResult()

    for i in range(0, len(tenants), batch_size):
        batch = tenants[i : i + batch_size]
        tasks = [
            _migrate_one_tenant(t["slug"], t["schema_name"], t["db_shard_id"],
                                migration_revision, get_shard_dsn)
            for t in batch
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for tenant, outcome in zip(batch, outcomes):
            if isinstance(outcome, Exception):
                logger.error("Migration failed for tenant %s: %s", tenant["slug"], outcome)
                result.failed.append((tenant["slug"], str(outcome)))
                if stop_on_first_failure:
                    logger.error(
                        "Halting rollout after first failure. "
                        "%d tenants migrated, %d failed.",
                        len(result.succeeded),
                        len(result.failed),
                    )
                    return result
            else:
                result.succeeded.append(tenant["slug"])

    return result


async def _migrate_one_tenant(
    slug: str,
    schema_name: str,
    shard_id: str,
    revision: str,
    get_shard_dsn,
) -> None:
    dsn = await get_shard_dsn(shard_id)
    import subprocess
    proc = subprocess.run(
        ["alembic", "upgrade", revision],
        env={"DATABASE_URL": dsn, "ALEMBIC_SCHEMA": schema_name},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed for {slug}: {proc.stderr}")
```

---

## 10. GDPR Article 20 — Tenant Data Export

When a tenant requests a full data export (right to data portability), the export service must traverse every kernel table in the tenant's schema and package the data.

```python
# core/tenancy/gdpr_export.py
from __future__ import annotations

import asyncpg
import json
import zipfile
import io
from datetime import datetime, timezone

EXPORTABLE_TABLES = [
    ("actions", ["id", "type", "payload", "actor_id", "state", "created_at"]),
    ("ledger_entries", ["seq", "action_id", "action_type", "actor_id",
                        "evaluation_result", "sealed_at"]),
    ("hitl_requests", ["id", "action_id", "outcome", "requested_at", "decided_at"]),
    ("consent_records", ["id", "data_subject_id", "purpose", "legal_basis",
                         "state", "granted_at", "withdrawn_at"]),
]


async def export_tenant_data(
    tenant_slug: str,
    *,
    conn: asyncpg.Connection,
) -> bytes:
    """
    Export all tenant data as a ZIP archive containing one JSON file per table.
    Implements GDPR Article 20 (right to data portability).

    The export uses the tenant's own schema — no cross-tenant query possible.
    Returns the ZIP bytes for upload to tenant-controlled storage.
    """
    schema = f"tenant_{tenant_slug}"
    export_manifest = {
        "tenant": tenant_slug,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": [],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for table_name, columns in EXPORTABLE_TABLES:
            col_list = ", ".join(columns)
            rows = await conn.fetch(
                f"SELECT {col_list} FROM {schema}.{table_name} ORDER BY 1"
            )
            table_data = [dict(row) for row in rows]

            # Serialize datetimes
            for record in table_data:
                for k, v in record.items():
                    if isinstance(v, datetime):
                        record[k] = v.isoformat()

            zf.writestr(
                f"{table_name}.json",
                json.dumps(table_data, indent=2, default=str),
            )
            export_manifest["tables"].append({"table": table_name, "row_count": len(table_data)})

        zf.writestr("manifest.json", json.dumps(export_manifest, indent=2))

    return buf.getvalue()
```

---

## 11. Tenant Deletion with Ledger Archival

Tenant deletion is irreversible. The ledger must be archived before the schema is dropped — a deleted tenant's audit trail may be required for regulatory inspection.

```python
# core/tenancy/deletion.py
from __future__ import annotations

import asyncpg
import logging

logger = logging.getLogger(__name__)


async def delete_tenant(
    tenant_slug: str,
    *,
    control_conn: asyncpg.Connection,
    shard_dsn: str,
    archive_storage,   # a StoragePort adapter pointing to cold/object storage
) -> None:
    """
    Safe tenant deletion sequence:
    1. Mark tenant state=DELETING (rejects new requests)
    2. Archive ledger to cold storage (object store / encrypted backup)
    3. Revoke active sessions
    4. Drop tenant schema (CASCADE — all tables, indexes, policies)
    5. Remove connection pool entry
    6. Mark tenant state=DELETED in control plane

    The ledger archive step is mandatory — it must succeed before schema drop.
    If archive fails, deletion halts and state remains DELETING for retry.
    """
    schema = f"tenant_{tenant_slug}"

    # Step 1: mark as DELETING
    await control_conn.execute(
        "UPDATE _quaicu_control.tenants SET state='DELETING' WHERE slug=$1",
        tenant_slug,
    )
    logger.info("Tenant %s marked DELETING", tenant_slug)

    shard_conn = await asyncpg.connect(shard_dsn)
    try:
        # Step 2: archive ledger before any data is destroyed
        await _archive_ledger(tenant_slug, schema, shard_conn, archive_storage)
        logger.info("Ledger archived for tenant %s", tenant_slug)

        # Step 3: drop schema (CASCADE removes all tables, indexes, RLS policies)
        await shard_conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        logger.info("Schema %s dropped", schema)

    except Exception as exc:
        logger.error("Tenant deletion failed for %s at archival step: %s", tenant_slug, exc)
        # Leave state=DELETING — operator must retry or investigate
        raise

    finally:
        await shard_conn.close()

    # Step 4: close and evict the connection pool for this tenant
    from adapters.storage.tenant_pool import close_tenant_pool
    await close_tenant_pool(tenant_slug)

    # Step 5: mark as DELETED (soft delete — record kept for audit trail)
    await control_conn.execute(
        "UPDATE _quaicu_control.tenants SET state='DELETED', deleted_at=now() WHERE slug=$1",
        tenant_slug,
    )
    logger.info("Tenant %s deletion complete", tenant_slug)


async def _archive_ledger(
    tenant_slug: str,
    schema: str,
    conn: asyncpg.Connection,
    archive_storage,
) -> None:
    import json
    from datetime import datetime, timezone

    rows = await conn.fetch(
        f"SELECT * FROM {schema}.ledger_entries ORDER BY seq"
    )
    archive = {
        "tenant": tenant_slug,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(rows),
        "entries": [dict(r) for r in rows],
    }

    key = f"ledger-archive/{tenant_slug}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    await archive_storage.put(key, json.dumps(archive, default=str).encode())
```

---

## 12. Connection String Rotation Without Downtime

When a database password or DSN changes (credential rotation), update the pool without dropping existing connections.

```python
# adapters/storage/tenant_pool.py (rotation extension)

async def rotate_tenant_dsn(tenant_slug: str, new_dsn: str) -> None:
    """
    Rotate the DSN for a tenant's pool without downtime.

    Strategy:
    1. Create a new pool with the new DSN.
    2. Swap the reference in _POOLS atomically.
    3. Drain and close the old pool gracefully.

    In-flight queries on the old pool complete normally.
    New queries go to the new pool.
    """
    async with _POOL_LOCK:
        old_pool = _POOLS.get(tenant_slug)
        schema = f"tenant_{tenant_slug}"
        new_pool = await asyncpg.create_pool(
            new_dsn,
            min_size=2,
            max_size=10,
            init=_make_init(schema, tenant_slug),
        )
        _POOLS[tenant_slug] = new_pool

    if old_pool:
        # Close old pool — waits for in-flight queries to finish
        await old_pool.close()
```

---

## 13. Cross-Shard Query Routing

When tenants are distributed across multiple database shards, the control plane provides routing. Core never talks to shards directly — it goes through the control plane's resolver.

```python
# core/tenancy/routing.py
from __future__ import annotations

import asyncpg
from functools import lru_cache


class TenantRouter:
    """
    Resolves tenant_slug → (shard_dsn, schema_name).
    Cached in-process with a TTL; control plane is the source of truth.
    """

    def __init__(self, control_dsn: str, openbao_client):
        self._control_dsn = control_dsn
        self._openbao = openbao_client
        self._cache: dict[str, dict] = {}

    async def resolve(self, tenant_slug: str) -> tuple[str, str]:
        """
        Return (shard_dsn, schema_name) for tenant_slug.
        Raises if tenant is not ACTIVE — fail-closed.
        """
        if tenant_slug in self._cache:
            return self._cache[tenant_slug]["dsn"], self._cache[tenant_slug]["schema"]

        conn = await asyncpg.connect(self._control_dsn)
        try:
            row = await conn.fetchrow(
                """
                SELECT t.schema_name, t.state, s.openbao_path
                  FROM _quaicu_control.tenants t
                  JOIN _quaicu_control.db_shards s ON s.id = t.db_shard_id
                 WHERE t.slug = $1
                """,
                tenant_slug,
            )
        finally:
            await conn.close()

        if row is None:
            raise KeyError(f"Unknown tenant: {tenant_slug!r}")
        if row["state"] != "ACTIVE":
            raise PermissionError(
                f"Tenant {tenant_slug!r} is not ACTIVE (state={row['state']!r}). "
                "Fail-closed: inactive tenants are denied."
            )

        dsn = await self._openbao.read_secret(row["openbao_path"])
        self._cache[tenant_slug] = {"dsn": dsn, "schema": row["schema_name"]}
        return dsn, row["schema_name"]

    def invalidate(self, tenant_slug: str) -> None:
        """Invalidate cache entry (call after credential rotation or state change)."""
        self._cache.pop(tenant_slug, None)
```

---

## 14. Scaling Model — Tenants per Database

Schema-per-tenant scales comfortably to hundreds–low-thousands of tenants per PostgreSQL instance. The practical limits:

| Factor | Guideline |
|--------|-----------|
| Schemas per database | Comfortable to ~1 000; PostgreSQL supports thousands, but catalog bloat grows |
| Tables per database | Each tenant adds ~8 kernel tables; 1 000 tenants = ~8 000 tables — within PostgreSQL limits |
| Connection pools | Use PgBouncer in transaction mode; each tenant pool maps to 2–10 server connections |
| Migration time | A schema-targeted Alembic run takes ~100–500 ms; 1 000 tenants = ~5–8 min total with batching |
| Shard boundary | Add a new shard at ~200–300 tenants per instance for comfortable operational headroom |

The control plane's `db_shards.max_tenants` column enforces shard capacity. The provisioning service checks capacity before assigning a shard.

---

## 15. Testing Tenant Isolation

Always test with three tenants. Two tenants can hide asymmetric bugs.

```python
# tests/integration/test_tenant_isolation.py
import pytest

@pytest.mark.integration
@pytest.mark.tenant_isolation
async def test_three_tenant_complete_isolation(db_pool):
    """
    End-to-end isolation test using three tenants on a real PostgreSQL instance.
    Verifies schema isolation, RLS enforcement, and ContextVar guard all work together.
    """
    tenants = ["tenant-alpha", "tenant-beta", "tenant-gamma"]

    # Seed one action per tenant
    for slug in tenants:
        async with tenant_connection(slug, dsn=...) as conn:
            await conn.execute(
                "INSERT INTO actions (type, payload, actor_id, idempotency_key, state) "
                "VALUES ($1, $2, $3, gen_random_uuid(), 'PROPOSED')",
                "test.isolation_probe",
                f'{{"owner": "{slug}"}}',
                f"actor-{slug}",
            )

    # Verify each tenant sees only its own actions
    for slug in tenants:
        async with tenant_connection(slug, dsn=...) as conn:
            rows = await conn.fetch("SELECT payload FROM actions WHERE type = $1",
                                     "test.isolation_probe")
            payloads = [r["payload"]["owner"] for r in rows]
            assert payloads == [slug], (
                f"Tenant {slug!r} saw actions from other tenants: {payloads}. "
                "Schema/RLS isolation failed."
            )
            assert len(rows) == 1, (
                f"Tenant {slug!r} expected 1 action, found {len(rows)}."
            )
```
