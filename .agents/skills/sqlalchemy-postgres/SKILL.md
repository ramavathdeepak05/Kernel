---
name: sqlalchemy-postgres
description: Expert guidance for SQLAlchemy 2.0 + Pydantic + PostgreSQL. Use when setting up database layers, defining models, creating migrations, or any database-related work. Automatically activated for DB tasks. QUAICU kernel — schema-per-tenant storage adapter, per-transaction SET LOCAL search_path plus RLS as defense-in-depth, append-only per-tenant ledger tables, Alembic per-schema migrations; used only in adapters/storage, never core. Triggers — QUAICU, schema-per-tenant, tenant isolation, RLS, StoragePort, per-tenant ledger, F-07.
---

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific DB choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** Missing rule → refuse the cross-tenant operation.

### Invariants — never violated
- Schema-per-tenant is the default. Set isolation per transaction with `SET LOCAL search_path TO "tenant_{id}"` and `SET LOCAL app.current_tenant = ...`. NEVER a shared table with a `tenant_id` column for kernel data.
- Enable RLS on every kernel table as defense-in-depth, on top of schema separation.
- Ledger tables are append-only: INSERT only; no UPDATE/DELETE; no UPDATE/DELETE RLS policy.
- SQLAlchemy/asyncpg are used ONLY inside `adapters/storage/`. NEVER import them in `core/` (use StoragePort).
- Sanitize any tenant id used in a schema name to `^[a-z0-9_]+$`; reject otherwise (schema-injection guard).

### Decision table
| Situation | Do exactly this |
|---|---|
| New kernel table | per-tenant schema + RLS policies (SELECT/INSERT, +UPDATE if mutable) |
| Set tenant on a connection | `SET LOCAL search_path` + `SET LOCAL app.current_tenant` in the txn |
| Idempotency | DB unique constraint + INSERT…ON CONFLICT (never SELECT-then-INSERT) |
| Migrations | Alembic per tenant schema; bypass RLS only as the migration role |
| Vector data (pgvector) | tenant schema like every other table; RLS applies |

### Tie-break rules
- Trust app-level `WHERE tenant_id=`? → no; search_path + RLS is the boundary.
- Is RLS redundant with schemas? → keep it; defense-in-depth is mandatory.

### Self-check
- [ ] Per-tenant schema; no shared kernel tables with tenant_id.
- [ ] search_path + app.current_tenant set per transaction.
- [ ] RLS on every table; ledger has no UPDATE/DELETE.
- [ ] asyncpg/SQLAlchemy only in adapters/storage, never core/.
- [ ] Schema names sanitized.

---

<essential_principles>
## SQLAlchemy 2.0 + Pydantic + PostgreSQL Best Practices

This skill provides expert guidance for building production-ready database layers.

### Stack
- **SQLAlchemy 2.0** with async support (asyncpg driver)
- **Pydantic v2** for validation and serialization
- **Alembic** for migrations
- **PostgreSQL** only

### Core Principles

**1. Separation of Concerns**
```
models/       # SQLAlchemy ORM models (database layer)
schemas/      # Pydantic schemas (API layer)
repositories/ # Data access patterns
services/     # Business logic
```

**2. Type Safety First**
Always use SQLAlchemy 2.0 style with `Mapped[]` type annotations:
```python
from sqlalchemy.orm import Mapped, mapped_column

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
```

**3. Async by Default**
Use async engine and sessions for FastAPI:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
engine = create_async_engine("postgresql+asyncpg://...")
```

**4. Pydantic-SQLAlchemy Bridge**
Keep models and schemas separate but mappable:
```python
# Schema reads from ORM
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

**5. Repository Pattern**
Abstract database operations for testability and clean code.
</essential_principles>

<intake>
What do you need help with?

1. **Setup database layer** - Initialize SQLAlchemy + Pydantic + Alembic from scratch
2. **Define models** - Create SQLAlchemy models with Pydantic schemas
3. **Create migration** - Generate and manage Alembic migrations
4. **Query patterns** - Async CRUD, joins, eager loading, optimization
5. **Full implementation** - Complete database layer for a feature
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "setup", "initialize", "start" | workflows/setup-database.md |
| 2, "model", "define", "create model" | workflows/define-models.md |
| 3, "migration", "alembic", "schema change" | workflows/create-migration.md |
| 4, "query", "crud", "repository" | workflows/query-patterns.md |
| 5, "full", "complete", "feature" | Run setup → define-models → create-migration |

**Auto-detection triggers (use this skill when user mentions):**
- database, db, sqlalchemy, postgres, postgresql
- model, migration, alembic
- repository, crud, query
- async session, connection pool
</routing>

<reference_index>
## Domain Knowledge

| Reference | Purpose |
|-----------|---------|
| references/best-practices.md | Production patterns, security, performance |
| references/patterns.md | Repository, Unit of Work, common queries |
| references/async-patterns.md | Async session management, FastAPI integration |
</reference_index>

<workflows_index>
| Workflow | Purpose |
|----------|---------|
| workflows/setup-database.md | Initialize complete database layer |
| workflows/define-models.md | Create models + schemas + relationships |
| workflows/create-migration.md | Alembic migration workflow |
| workflows/query-patterns.md | CRUD operations and optimization |
</workflows_index>

<quick_reference>
## File Structure
```
src/
├── db/
│   ├── __init__.py
│   ├── base.py          # DeclarativeBase
│   ├── session.py       # Engine + async session factory
│   └── dependencies.py  # FastAPI dependency
├── models/
│   ├── __init__.py
│   └── user.py          # SQLAlchemy models
├── schemas/
│   ├── __init__.py
│   └── user.py          # Pydantic schemas
├── repositories/
│   ├── __init__.py
│   ├── base.py          # Generic repository
│   └── user.py          # User repository
└── alembic/
    ├── alembic.ini
    ├── env.py
    └── versions/
```

## Essential Imports
```python
# Models
from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase

# Async
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Pydantic
from pydantic import BaseModel, ConfigDict, Field
```

## Connection String
```python
# PostgreSQL async
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
```
</quick_reference>

<success_criteria>
Database layer is complete when:
- [ ] Async engine and session factory configured
- [ ] Base model with common fields (id, created_at, updated_at)
- [ ] Models use Mapped[] type annotations
- [ ] Pydantic schemas with from_attributes=True
- [ ] Alembic configured for async
- [ ] Repository pattern implemented
- [ ] FastAPI dependency for session injection
- [ ] Connection pooling configured for production
</success_criteria>

---

## QUAICU-Specific Application

This section documents the database layer patterns required by the QUAICU governance kernel. The dominant constraints are: **schema-per-tenant** (spec §3.10, F-07), **per-tenant ledger tables that are never shared** (F-07), **event-sourced ledger shape** (§3.13), and **pgvector for semantic policy search** (§2). All patterns live in `adapters/storage/postgres/` and `migrations/`.

### Schema-Per-Tenant with SQLAlchemy: Dynamic Schema Binding

Each tenant owns an isolated PostgreSQL schema (e.g. `acme_bank`, `finco`). The `search_path` is set per session (see `fastapi-expert` QUAICU section). SQLAlchemy models reference the schema dynamically rather than hardcoding `public`.

```python
# adapters/storage/postgres/base.py
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# The canonical Base for kernel-owned tables.
# Schema is NOT set here — it is injected per-tenant at session time via search_path.
# This means all Table objects use the default schema (resolved by search_path at query time).
class KernelBase(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
```

**Per-Tenant MetaData** — used when you need to reflect or operate on a specific tenant's schema without affecting global model definitions:

```python
# adapters/storage/postgres/tenant_schema.py
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncConnection

async def get_tenant_metadata(conn: AsyncConnection, tenant_id: str) -> MetaData:
    """
    Reflects all kernel tables from the tenant's schema into a fresh MetaData instance.
    Useful for per-tenant schema inspection, audits, and migration status checks.
    """
    meta = MetaData(schema=tenant_id)
    await conn.run_sync(meta.reflect)
    return meta

async def create_tenant_schema(conn: AsyncConnection, tenant_id: str) -> None:
    """
    Provisions a new tenant: creates schema, then creates all kernel tables within it.
    Called by the admin router POST /tenants endpoint.
    """
    # Validate tenant_id to prevent schema injection (alphanumeric + hyphen/underscore only).
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,62}", tenant_id):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")

    await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {tenant_id}"))
    # Set search_path and create all tables in the new schema.
    await conn.execute(text(f"SET search_path TO {tenant_id}"))
    await conn.run_sync(KernelBase.metadata.create_all)
    # Enable Row-Level Security as defense-in-depth (spec §3.10).
    for table in KernelBase.metadata.sorted_tables:
        await conn.execute(text(f"ALTER TABLE {tenant_id}.{table.name} ENABLE ROW LEVEL SECURITY"))
```

### Async Session Factory Per Tenant

The session factory is shared (one engine for all tenants); `search_path` makes it tenant-scoped. For deployment tiers where each tenant has a dedicated database instance, swap the engine rather than the session factory.

```python
# adapters/storage/postgres/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

class TenantSessionFactory:
    """
    Single engine, per-request tenant scoping via search_path.
    For sovereign/dedicated tiers: instantiate one TenantSessionFactory per database URL.
    """
    def __init__(self, database_url: str):
        self._engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        self._factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def session_for_tenant(self, tenant_id: str) -> AsyncGenerator[AsyncSession, None]:
        import re
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,62}", tenant_id):
            raise ValueError(f"Invalid tenant_id: {tenant_id!r}")
        async with self._factory() as session:
            await session.execute(f"SET search_path TO {tenant_id}, public")
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.execute("SET search_path TO public")

    async def close(self):
        await self._engine.dispose()
```

### Alembic Multi-Tenant Migration Script

QUAICU owns its own schema and migrations (`migrations/` at the repo root). When a new kernel version adds tables, the migration must run against every existing tenant's schema, then against the template schema used for future tenants.

```python
# migrations/env.py  — multi-tenant Alembic env
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from alembic import context
from adapters.storage.postgres.base import KernelBase

config = context.config
fileConfig(config.config_file_name)

target_metadata = KernelBase.metadata

async def get_tenant_schemas(conn) -> list[str]:
    """Returns all tenant schema names (excludes pg_catalog, information_schema, public)."""
    result = await conn.execute(text(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'public') "
        "AND schema_name NOT LIKE 'pg_toast%'"
    ))
    return [row[0] for row in result.fetchall()]

async def run_migrations_online():
    engine = create_async_engine(config.get_main_option("sqlalchemy.url"))
    async with engine.connect() as conn:
        schemas = await get_tenant_schemas(conn)
        # Always include _template schema (used for new tenant provisioning).
        if "_template" not in schemas:
            schemas.append("_template")

        for schema in schemas:
            print(f"Migrating schema: {schema}")
            await conn.execute(text(f"SET search_path TO {schema}"))
            await conn.run_sync(
                lambda sync_conn: context.configure(
                    connection=sync_conn,
                    target_metadata=target_metadata,
                    # Include schema in version table to track per-schema state.
                    version_table=f"alembic_version",
                    include_schemas=False,  # search_path handles schema routing
                    compare_type=True,
                )
            )
            async with conn.begin_nested():
                await conn.run_sync(lambda sync_conn: context.run_migrations())

        await conn.execute(text("SET search_path TO public"))
        await conn.commit()
    await engine.dispose()

asyncio.run(run_migrations_online())
```

### Event Listeners for Audit Logging

The spec (§3.13) requires that the ledger capture inputs and results — not just outcomes. SQLAlchemy event listeners record every model mutation to a per-tenant `audit_log` table without burdening repository code with explicit audit calls.

```python
# adapters/storage/postgres/audit.py
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from adapters.storage.postgres.models.audit import AuditLogEntry

def register_audit_listeners(session_factory):
    """
    Attaches SQLAlchemy event listeners that write to audit_log on every
    INSERT/UPDATE/DELETE of kernel-owned tables.
    """
    @event.listens_for(session_factory, "after_flush")
    def after_flush(session: Session, flush_context):
        from delivery.api.middleware.tenant import get_current_tenant_id
        try:
            tenant_id = get_current_tenant_id()
        except RuntimeError:
            return  # Background tasks without a request context skip audit

        entries = []
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            mapper = inspect(type(obj))
            if not hasattr(mapper, "persist_selectable"):
                continue
            table_name = mapper.persist_selectable.name
            # Skip the audit_log table itself to prevent infinite recursion.
            if table_name == "audit_log":
                continue
            state = inspect(obj)
            entries.append(AuditLogEntry(
                table_name=table_name,
                operation="INSERT" if obj in session.new else (
                    "DELETE" if obj in session.deleted else "UPDATE"),
                record_id=str(getattr(obj, "id", None)),
                changed_fields={
                    attr.key: {"old": attr.history.deleted[0] if attr.history.deleted else None,
                               "new": attr.history.added[0] if attr.history.added else None}
                    for attr in state.attrs
                    if attr.history.has_changes()
                },
                tenant_id=tenant_id,
            ))
        for entry in entries:
            session.add(entry)
```

### pgvector Integration for Semantic Policy Search

Policy evaluation relies on CEL expressions, but policy *discovery* (finding which policies apply to an action type) can be augmented with semantic search. The `policy` table stores a vector embedding of the policy description for `SELECT ... ORDER BY embedding <=> $1` similarity queries.

```python
# adapters/storage/postgres/models/policy.py
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from adapters.storage.postgres.base import KernelBase

class PolicyModel(KernelBase):
    __tablename__ = "policies"

    id: Mapped[str]          = mapped_column(String(128), primary_key=True)
    version: Mapped[int]     = mapped_column()
    action_type: Mapped[str] = mapped_column(String(256), index=True)
    condition_cel: Mapped[str] = mapped_column(Text)
    decision: Mapped[str]    = mapped_column(String(32))   # allow | deny | require_approval
    lifecycle: Mapped[str]   = mapped_column(String(32), index=True)  # DRAFT|REVIEW|ACTIVATED|DEPRECATED
    # pgvector column — 1536 dims for text-embedding-3-small; adjust for local models.
    description_embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=True)
    regulatory_refs: Mapped[list] = mapped_column(JSON, default=list)

# Migration: CREATE EXTENSION IF NOT EXISTS vector; must run before this table is created.
# Alembic upgrade op: op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

```python
# adapters/storage/postgres/repositories/policy.py
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from adapters.storage.postgres.models.policy import PolicyModel

class PolicyRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_action_type(self, action_type: str) -> list[PolicyModel]:
        """Exact match — primary policy resolution path."""
        result = await self._session.execute(
            select(PolicyModel)
            .where(PolicyModel.action_type == action_type)
            .where(PolicyModel.lifecycle == "ACTIVATED")
            .order_by(PolicyModel.version.desc())
        )
        return list(result.scalars().all())

    async def semantic_search(
        self, query_embedding: list[float], limit: int = 10
    ) -> list[PolicyModel]:
        """
        pgvector cosine similarity search — used by the policy authoring UI to suggest
        related policies when drafting a new one. Never used on the evaluation hot path.
        """
        result = await self._session.execute(
            select(PolicyModel)
            .where(PolicyModel.lifecycle == "ACTIVATED")
            .where(PolicyModel.description_embedding.isnot(None))
            .order_by(PolicyModel.description_embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        return list(result.scalars().all())
```

### Table Reflection for Dynamic Tenant Schema

When provisioning a tenant from an API call (not a migration), reflect the current `_template` schema into the target tenant schema. This is faster than running Alembic for interactive provisioning and ensures new tenants always start at the current schema version.

```python
# adapters/storage/postgres/tenant_schema.py  (continued)
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncConnection

async def provision_tenant_from_template(
    conn: AsyncConnection, tenant_id: str
) -> None:
    """
    Clones the _template schema's table structure into a new tenant schema.
    Faster than running Alembic for interactive provisioning.
    After cloning, insert the alembic_version row so future Alembic runs
    treat this schema as up-to-date.
    """
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,62}", tenant_id):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")

    await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {tenant_id}"))

    # Use pg_dump | pg_restore pattern via server-side SQL for zero-dependency cloning.
    # For a pure-SQLAlchemy approach, reflect _template and recreate in new schema.
    sync_conn = await conn.get_raw_connection()
    template_meta = MetaData(schema="_template")
    await conn.run_sync(template_meta.reflect)

    new_meta = MetaData(schema=tenant_id)
    for table in template_meta.sorted_tables:
        table.tometadata(new_meta, schema=tenant_id)

    await conn.run_sync(new_meta.create_all)

    # Record the current alembic head so this schema is treated as migrated.
    head_rev = await _get_alembic_head()
    await conn.execute(
        text(f"INSERT INTO {tenant_id}.alembic_version (version_num) VALUES (:rev)"),
        {"rev": head_rev},
    )

    # Enable RLS on all new tables.
    for table in new_meta.sorted_tables:
        await conn.execute(text(
            f"ALTER TABLE {tenant_id}.{table.name} ENABLE ROW LEVEL SECURITY"
        ))

async def _get_alembic_head() -> str:
    """Returns the current Alembic head revision from the migration scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config("migrations/alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()
```
