"""
ALIS Database Service - Safe DB Tools (E00-S03 Tenant Isolation)

MODULE: Shared Infrastructure
LAYER: Infrastructure (below Layer 1) + Layer 4 (Tenant Isolation)
ENTITY: Database Connection

This module provides a safe, centralized way to execute database queries.
It prevents raw SQL injection, ensures connection pooling, and enforces
tenant isolation as a Layer 4 invariant.

TENANT ISOLATION ENFORCEMENT:
- All queries are automatically scoped by tenant_id via PostgreSQL
  session variable `alis.current_tenant`.
- The tenant_id is read from the request-scoped ContextVar set by
  TenantMiddleware in security.py.
- System-level queries (migrations, health checks) use
  `execute_system_query` which bypasses tenant scoping.

Must Align With:
- "Safe DB Tools" requirement in Project Structure.
- "No Cloud" rule (local PostgreSQL).
- E00-S03: Tenant Isolation Enforcement (Layer 4).

Usage:
    # Tenant-scoped (default - reads tenant from ContextVar):
    result = execute_query("SELECT * FROM users WHERE id = %s", (user_id,))

    # System-level (bypasses tenant scoping - use sparingly):
    result = execute_system_query("SELECT count(*) FROM pg_stat_activity")
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager, contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool as pg_pool_module
except ImportError:
    logging.warning("psycopg2 not found. Database functionality will be mocked or fail.")
    psycopg2 = None
    pg_pool_module = None

try:
    import asyncpg
except ImportError:
    logging.warning("asyncpg not found. Async database functionality unavailable.")
    asyncpg = None

# Configure Logging
logger = logging.getLogger(__name__)

# System pools — used by execute_system_query* (no tenant scoping)
_pg_pool = None           # psycopg2 — Celery sync workers, system queries
_asyncpg_pool = None      # asyncpg  — FastAPI async handlers, system queries


# ---------------------------------------------------------------------------
# S1: DBRouter — per-tenant connection pool manager
# ---------------------------------------------------------------------------

@dataclass
class _TenantDBConfig:
    """Resolved DB connection info for a single tenant."""
    tenant_id: str
    db_url: str       # asyncpg DSN  (postgresql://...)
    db_url_sync: str  # psycopg2 DSN (postgresql://...)


class DBRouter:
    """
    Per-tenant connection pool manager (S1 — SaaS multi-tenant foundation).

    Maintains a map of asyncpg + psycopg2 pools, one per tenant.
    Pools are created lazily on first request and reused thereafter.

    Backward compat:
    - When CONTROL_PLANE_URL is not set, TenantRegistry returns a fallback
      TenantRecord that points at settings.db_url — identical to the old
      single-pool behavior.
    - All execute_query* / execute_transaction* functions transparently route
      through this class; callers require zero changes.

    Thread safety:
    - asyncpg pools: protected by asyncio.Lock (lazy-created per event loop).
    - psycopg2 pools: protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._async_pools: dict[str, Any] = {}      # tenant_id → asyncpg.Pool
        self._sync_pools: dict[str, Any] = {}        # tenant_id → psycopg2.ThreadedConnectionPool
        self._async_lock: Optional[asyncio.Lock] = None
        self._sync_lock = threading.Lock()

    @property
    def _alock(self) -> asyncio.Lock:
        """Lazy asyncio.Lock — avoids binding to event loop at import time."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    async def _resolve_config(self, tenant_id: str) -> _TenantDBConfig:
        from server.core.tenant_registry import TenantRegistry
        record = await TenantRegistry.get_by_id(tenant_id)
        return _TenantDBConfig(
            tenant_id=record.tenant_id,
            db_url=record.db_url,
            db_url_sync=record.db_url_sync,
        )

    def _resolve_config_sync(self, tenant_id: str) -> _TenantDBConfig:
        from server.core.tenant_registry import TenantRegistry
        record = TenantRegistry.get_by_id_sync(tenant_id)
        return _TenantDBConfig(
            tenant_id=record.tenant_id,
            db_url=record.db_url,
            db_url_sync=record.db_url_sync,
        )

    # ------------------------------------------------------------------
    # Async (asyncpg) pool
    # ------------------------------------------------------------------

    async def get_async_pool(self, tenant_id: str):
        """Return the asyncpg pool for tenant_id, creating it if needed."""
        if asyncpg is None:
            return None
        if tenant_id in self._async_pools:
            return self._async_pools[tenant_id]

        async with self._alock:
            # Double-checked locking — another coroutine may have created it.
            if tenant_id in self._async_pools:
                return self._async_pools[tenant_id]

            config = await self._resolve_config(tenant_id)
            from server.core.settings import settings
            pool = await asyncpg.create_pool(
                dsn=config.db_url,
                min_size=settings.tenant_pool_min,
                max_size=settings.tenant_pool_max,
                statement_cache_size=0,   # required for SET LOCAL + pgbouncer
                init=_init_connection,
                command_timeout=30,
            )
            self._async_pools[tenant_id] = pool
            logger.info(
                "DBRouter: asyncpg pool created for tenant=%s (min=%s max=%s)",
                tenant_id, settings.tenant_pool_min, settings.tenant_pool_max,
            )
            return pool

    async def close_all_async_pools(self) -> None:
        """Gracefully close all asyncpg pools. Called from FastAPI lifespan shutdown."""
        for tenant_id, pool in list(self._async_pools.items()):
            try:
                await pool.close()
                logger.info("DBRouter: asyncpg pool closed for tenant=%s", tenant_id)
            except Exception as exc:
                logger.warning("DBRouter: error closing pool for tenant=%s: %s", tenant_id, exc)
        self._async_pools.clear()

    # ------------------------------------------------------------------
    # Sync (psycopg2) pool
    # ------------------------------------------------------------------

    def get_sync_pool(self, tenant_id: str):
        """Return the psycopg2 pool for tenant_id, creating it if needed."""
        if psycopg2 is None:
            return None
        if tenant_id in self._sync_pools:
            return self._sync_pools[tenant_id]

        with self._sync_lock:
            if tenant_id in self._sync_pools:
                return self._sync_pools[tenant_id]

            config = self._resolve_config_sync(tenant_id)
            from server.core.settings import settings
            pool = psycopg2.pool.ThreadedConnectionPool(
                settings.tenant_pool_min,
                settings.tenant_pool_max,
                config.db_url_sync,   # psycopg2 accepts postgresql:// DSN as positional arg
            )
            self._sync_pools[tenant_id] = pool
            logger.info(
                "DBRouter: psycopg2 pool created for tenant=%s (min=%s max=%s)",
                tenant_id, settings.tenant_pool_min, settings.tenant_pool_max,
            )
            return pool

    def close_all_sync_pools(self) -> None:
        """Close all psycopg2 pools."""
        with self._sync_lock:
            for tenant_id, pool in list(self._sync_pools.items()):
                try:
                    pool.closeall()
                    logger.info("DBRouter: psycopg2 pool closed for tenant=%s", tenant_id)
                except Exception as exc:
                    logger.warning("DBRouter: error closing sync pool for tenant=%s: %s", tenant_id, exc)
            self._sync_pools.clear()


# Module-level DBRouter singleton — pools created lazily on first request.
_db_router = DBRouter()


# ---------------------------------------------------------------------------
# P0-1: asyncpg pool lifecycle (call from FastAPI lifespan)
# ---------------------------------------------------------------------------

def _convert_params(query: str) -> str:
    """Replace %s placeholders with asyncpg-style $N positional params."""
    counter = 0

    def _replace(_m: re.Match) -> str:
        nonlocal counter
        counter += 1
        return f"${counter}"

    return re.sub(r"%s", _replace, query)


async def _init_connection(conn) -> None:
    """Per-connection init: disable statement cache (required for SET LOCAL + pgbouncer)."""
    await conn.set_type_codec("jsonb", encoder=str, decoder=str, schema="pg_catalog")


async def init_pool() -> None:
    """Call from FastAPI lifespan startup to create the asyncpg pool."""
    global _asyncpg_pool
    if asyncpg is None:
        logger.warning("asyncpg not installed — skipping async pool init.")
        return
    from server.core.settings import settings
    # Route through PgBouncer when enabled (session mode, no connection limit worries)
    db_host = settings.pgbouncer_host if settings.pgbouncer_enabled else settings.db_host
    db_port = settings.pgbouncer_port if settings.pgbouncer_enabled else settings.db_port
    _asyncpg_pool = await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_password,
        host=db_host,
        port=db_port,
        database=settings.db_name,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        statement_cache_size=0,   # required: SET LOCAL + pgbouncer compat
        init=_init_connection,
        command_timeout=30,
    )
    via = f"pgbouncer ({db_host}:{db_port})" if settings.pgbouncer_enabled else f"postgres ({db_host}:{db_port})"
    logger.info("asyncpg pool initialised via %s (min=%s max=%s).", via, settings.db_pool_min, settings.db_pool_max)


async def close_pool() -> None:
    """Call from FastAPI lifespan shutdown."""
    global _asyncpg_pool
    if _asyncpg_pool is not None:
        await _asyncpg_pool.close()
        _asyncpg_pool = None
        logger.info("asyncpg system pool closed.")

    # Close all per-tenant asyncpg pools managed by DBRouter.
    await _db_router.close_all_async_pools()
    _db_router.close_all_sync_pools()


def _get_async_pool():
    if _asyncpg_pool is None:
        raise RuntimeError("asyncpg pool not initialised. Call init_pool() at startup.")
    return _asyncpg_pool


def get_db_pool():
    """Initialize and return the connection pool."""
    global _pg_pool
    if _pg_pool is None and psycopg2:
        try:
            from server.core.settings import settings
            db_host = settings.pgbouncer_host if settings.pgbouncer_enabled else settings.db_host
            db_port = settings.pgbouncer_port if settings.pgbouncer_enabled else settings.db_port
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=settings.db_pool_min,
                maxconn=settings.db_pool_max,
                user=settings.db_user,
                password=settings.db_password,
                host=db_host,
                port=db_port,
                database=settings.db_name,
            )
            via = f"pgbouncer ({db_host}:{db_port})" if settings.pgbouncer_enabled else f"postgres ({db_host}:{db_port})"
            logger.info("psycopg2 pool initialised via %s (max=%s).", via, settings.db_pool_max)
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    return _pg_pool


@contextmanager
def get_db_connection():
    """
    System-level context manager (psycopg2) — uses the global system pool.
    Reserved for execute_system_query* (health checks, migrations, init_db).
    Tenant-scoped code should use get_tenant_db_connection() instead.
    """
    pool = get_db_pool()
    if not pool:
        raise RuntimeError("Database connection pool is not available.")

    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def get_tenant_db_connection(tenant_id: str):
    """
    Tenant-scoped context manager (psycopg2) — routes to per-tenant DBRouter pool.

    Used by execute_query and execute_transaction to obtain a connection
    from the correct per-tenant database.
    """
    if not psycopg2:
        raise RuntimeError("psycopg2 not available.")
    pool = _db_router.get_sync_pool(tenant_id)
    if not pool:
        raise RuntimeError(f"Could not obtain sync pool for tenant={tenant_id}")

    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# ============================================================================
# E00-S03: TENANT-SCOPED DATABASE ACCESS
# ============================================================================

def _set_tenant_on_connection(cursor, tenant_id: str) -> None:
    """
    Set the current tenant on the PostgreSQL connection session.

    This uses PostgreSQL's `SET LOCAL` to set a session variable that
    Row-Level Security (RLS) policies can reference via
    `current_setting('alis.current_tenant')`.

    SET LOCAL ensures the variable is scoped to the current transaction only.
    """
    cursor.execute("SET LOCAL alis.current_tenant = %s", (tenant_id,))


def _get_tenant_id_from_context() -> str:
    """
    Get tenant_id from the request-scoped ContextVar.

    Raises TenantIsolationError if not set.
    """
    from server.core.security import get_current_tenant_id
    return get_current_tenant_id()


async def execute_query_async(
    query: str,
    params: Optional[Tuple] = None,
    tenant_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Async execute_query using asyncpg — use in async FastAPI route handlers.

    EC-CROSS-03: SET LOCAL alis.current_tenant inside every transaction so
    tenant context is never inherited from a previous connection in the pool.

    The tenant_id is resolved in this priority:
    1. Explicit `tenant_id` parameter (for internal service calls)
    2. Request-scoped ContextVar (set by TenantMiddleware)
    """
    if asyncpg is None:
        logger.warning("Mocking execute_query_async (asyncpg unavailable).")
        return []

    resolved_tenant = tenant_id or _get_tenant_id_from_context()
    q = _convert_params(query)
    p = list(params) if params else []

    # S1: route to per-tenant pool via DBRouter
    pool = await _db_router.get_async_pool(resolved_tenant)
    async with pool.acquire() as conn:
        async with conn.transaction():
            # EC-CROSS-03: isolate tenant per transaction (defense-in-depth RLS)
            await conn.execute("SET LOCAL alis.current_tenant = $1", resolved_tenant)
            rows = await conn.fetch(q, *p)
    return [dict(r) for r in rows]


def execute_query(
    query: str,
    params: Optional[Tuple] = None,
    tenant_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Synchronous execute_query (psycopg2) — for Celery workers only.

    ** DO NOT CALL FROM FastAPI ASYNC HANDLERS. **
    Use execute_query_async() instead. Calling this from an async context
    blocks the event loop and degrades throughput under concurrency.
    This function raises RuntimeError if an event loop is running.
    """
    try:
        import asyncio
        asyncio.get_running_loop()
        # If we reach here, a loop IS running — this is a misuse from async context.
        raise RuntimeError(
            "execute_query (psycopg2 sync) called inside a running asyncio event loop. "
            "Use execute_query_async() in FastAPI route handlers to avoid event loop blocking. "
            "Only Celery workers should use the sync variant."
        )
    except RuntimeError as re:
        if "execute_query" in str(re):
            raise
        # No event loop running — safe to proceed (Celery context)
        pass
    if not psycopg2:
        logger.warning("Mocking execute_query due to missing driver.")
        return []

    resolved_tenant = tenant_id or _get_tenant_id_from_context()

    # S1: route to per-tenant pool via DBRouter
    with get_tenant_db_connection(resolved_tenant) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                _set_tenant_on_connection(cursor, resolved_tenant)
                cursor.execute(query, params)
                if cursor.description:
                    return cursor.fetchall()
                return []
            except Exception as e:
                # Log the query template (not params) to avoid leaking PII in logs
                logger.error("Query execution failed: %s | query_template=%s", e, query[:200])
                raise


# Alias for Celery workers — same as execute_query (both are sync psycopg2)
execute_query_sync = execute_query


async def execute_transaction_async(
    queries: List[Tuple[str, Optional[Tuple]]],
    tenant_id: Optional[str] = None
) -> None:
    """
    Async execute_transaction (asyncpg) — use in async FastAPI route handlers.
    EC-CROSS-03: SET LOCAL inside the transaction block ensures per-transaction tenant isolation.
    """
    if asyncpg is None:
        logger.warning("Mocking execute_transaction_async (asyncpg unavailable).")
        return

    from server.core.lockdown import LockdownManager
    LockdownManager.assert_write_allowed()

    resolved_tenant = tenant_id or _get_tenant_id_from_context()

    # S1: route to per-tenant pool via DBRouter
    pool = await _db_router.get_async_pool(resolved_tenant)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL alis.current_tenant = $1", resolved_tenant)
            for query, params in queries:
                q = _convert_params(query)
                p = list(params) if params else []
                await conn.execute(q, *p)


def execute_transaction(
    queries: List[Tuple[str, Optional[Tuple]]],
    tenant_id: Optional[str] = None
) -> None:
    """
    Synchronous execute_transaction (psycopg2) — for Celery workers only.

    ** DO NOT CALL FROM FastAPI ASYNC HANDLERS. **
    Use execute_transaction_async() instead. Calling this from an async context
    blocks the event loop and degrades concurrency.
    This function raises RuntimeError if an event loop is running.
    """
    try:
        import asyncio
        asyncio.get_running_loop()
        raise RuntimeError(
            "execute_transaction (psycopg2 sync) called inside a running asyncio event loop. "
            "Use execute_transaction_async() in FastAPI route handlers. "
            "Only Celery workers should use the sync variant."
        )
    except RuntimeError as re:
        if "execute_transaction" in str(re):
            raise
        pass
    if not psycopg2:
        logger.warning("Mocking execute_transaction.")
        return

    # --- E00-S05: Lockdown Write Gate (Layer 4) ---
    from server.core.lockdown import LockdownManager
    LockdownManager.assert_write_allowed()

    resolved_tenant = tenant_id or _get_tenant_id_from_context()

    # S1: route to per-tenant pool via DBRouter
    with get_tenant_db_connection(resolved_tenant) as conn:
        try:
            with conn.cursor() as cursor:
                _set_tenant_on_connection(cursor, resolved_tenant)
                for query, params in queries:
                    cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise


# Alias for Celery workers
execute_transaction_sync = execute_transaction


async def execute_system_query_async(
    query: str,
    params: Optional[Tuple] = None
) -> List[Dict[str, Any]]:
    """
    Async system-level query (asyncpg) — use in async FastAPI handlers.
    USE SPARINGLY. For health checks and SUPER_ADMIN analytics.
    """
    if asyncpg is None:
        logger.warning("Mocking execute_system_query_async (asyncpg unavailable).")
        return []

    q = _convert_params(query)
    p = list(params) if params else []
    async with _get_async_pool().acquire() as conn:
        rows = await conn.fetch(q, *p)
    return [dict(r) for r in rows]


def execute_system_query(
    query: str,
    params: Optional[Tuple] = None
) -> List[Dict[str, Any]]:
    """
    Synchronous system-level query (psycopg2) — backward-compatible default.
    USE SPARINGLY. For Celery workers, init_db, health checks (sync context).
    """
    if not psycopg2:
        logger.warning("Mocking execute_system_query due to missing driver.")
        return []

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                cursor.execute(query, params)
                if cursor.description:
                    return cursor.fetchall()
                return []
            except Exception as e:
                logger.error(f"System query execution failed: {e}\nQuery: {query}")
                raise


async def execute_system_transaction_async(
    queries: List[Tuple[str, Optional[Tuple]]]
) -> None:
    """
    Async system-level transaction (asyncpg) — use in async FastAPI handlers.
    USE SPARINGLY. Same restrictions as execute_system_query_async.
    """
    if asyncpg is None:
        logger.warning("Mocking execute_system_transaction_async (asyncpg unavailable).")
        return

    async with _get_async_pool().acquire() as conn:
        async with conn.transaction():
            for query, params in queries:
                q = _convert_params(query)
                p = list(params) if params else []
                await conn.execute(q, *p)


def execute_system_transaction(
    queries: List[Tuple[str, Optional[Tuple]]]
) -> None:
    """
    Synchronous system-level transaction (psycopg2) — backward-compatible default.
    Used by init_db and Celery workers.
    """
    if not psycopg2:
        logger.warning("Mocking execute_system_transaction.")
        return

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"System transaction failed: {e}")
            raise


# Aliases used by Celery task files (both resolve to sync psycopg2 versions)
execute_system_query_sync = execute_system_query
execute_system_transaction_sync = execute_system_transaction


# ============================================================================
# DATABASE INITIALIZATION (System-Level)
# ============================================================================

def init_db():
    """
    Initialize database schema if needed.
    Uses execute_system_transaction (no tenant scoping needed for DDL).

    E00-S03: All tables now include tenant_id for row-level isolation.
    """
    # --- PostgreSQL Session Variable for Tenant Context ---
    tenant_session_var_sql = """
    DO $$
    BEGIN
        -- Create the custom GUC variable for tenant context
        -- This allows SET LOCAL alis.current_tenant = 'xxx'
        PERFORM set_config('alis.current_tenant', '', true);
    EXCEPTION WHEN OTHERS THEN
        -- Variable may already exist, which is fine
        NULL;
    END
    $$;
    """

    search_table_sql = """
    CREATE TABLE IF NOT EXISTS search_index (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        entity_type VARCHAR(50) NOT NULL,
        entity_id VARCHAR(100) NOT NULL,
        content TEXT,
        metadata JSONB,
        search_vector TSVECTOR,
        roles_allowed TEXT[],
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_search_vector ON search_index USING GIN(search_vector);
    CREATE INDEX IF NOT EXISTS idx_search_entity_type ON search_index(entity_type);
    CREATE INDEX IF NOT EXISTS idx_search_tenant ON search_index(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_search_tenant_entity ON search_index(tenant_id, entity_type);
    """

    activity_table_sql = """
    CREATE TABLE IF NOT EXISTS activity_feed (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        entity_type VARCHAR(50) NOT NULL,
        entity_id VARCHAR(100) NOT NULL,
        activity_type VARCHAR(50) NOT NULL,
        description TEXT NOT NULL,
        metadata JSONB,
        actor_id VARCHAR(100) NOT NULL,
        actor_role VARCHAR(50) NOT NULL,
        visible_to_roles TEXT[],
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_activity_entity ON activity_feed(entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_activity_tenant ON activity_feed(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_activity_tenant_entity ON activity_feed(tenant_id, entity_type);
    """

    comments_table_sql = """
    CREATE TABLE IF NOT EXISTS comments (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        entity_type VARCHAR(50) NOT NULL,
        entity_id VARCHAR(100) NOT NULL,
        content TEXT NOT NULL,
        parent_id INTEGER REFERENCES comments(id),
        actor_id VARCHAR(100) NOT NULL,
        actor_role VARCHAR(50) NOT NULL,
        visible_to_roles TEXT[],
        is_hidden BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_comments_entity ON comments(entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_comments_tenant ON comments(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_comments_tenant_entity ON comments(tenant_id, entity_type);
    """

    # --- E00-S02: Immutable Audit Ledger Table ---
    audit_ledger_table_sql = """
    CREATE TABLE IF NOT EXISTS audit_ledger (
        id BIGSERIAL PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        actor_id VARCHAR(100) NOT NULL,
        actor_role VARCHAR(50) NOT NULL,
        action VARCHAR(100) NOT NULL,
        entity_type VARCHAR(100) NOT NULL,
        entity_id VARCHAR(200) NOT NULL,
        metadata JSONB,
        timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        previous_hash VARCHAR(64),
        hash VARCHAR(64) NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_audit_ledger_tenant
        ON audit_ledger(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_audit_ledger_tenant_ts
        ON audit_ledger(tenant_id, timestamp);
    CREATE INDEX IF NOT EXISTS idx_audit_ledger_entity
        ON audit_ledger(entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_audit_ledger_actor
        ON audit_ledger(tenant_id, actor_id);
    """

    # --- E00-S02: Immutability Enforcement (Layer 4 — Lock After Commit) ---
    audit_ledger_immutability_sql = """
    -- Trigger function: block UPDATE and DELETE on audit_ledger
    CREATE OR REPLACE FUNCTION audit_ledger_immutable_guard()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION
            'E00-S02 VIOLATION: audit_ledger is append-only. '
            '% operations are prohibited.',
            TG_OP;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    -- Attach trigger for UPDATE
    DROP TRIGGER IF EXISTS trg_audit_ledger_no_update ON audit_ledger;
    CREATE TRIGGER trg_audit_ledger_no_update
        BEFORE UPDATE ON audit_ledger
        FOR EACH ROW
        EXECUTE FUNCTION audit_ledger_immutable_guard();

    -- Attach trigger for DELETE
    DROP TRIGGER IF EXISTS trg_audit_ledger_no_delete ON audit_ledger;
    CREATE TRIGGER trg_audit_ledger_no_delete
        BEFORE DELETE ON audit_ledger
        FOR EACH ROW
        EXECUTE FUNCTION audit_ledger_immutable_guard();

    -- Block TRUNCATE via a statement-level trigger
    DROP TRIGGER IF EXISTS trg_audit_ledger_no_truncate ON audit_ledger;
    CREATE TRIGGER trg_audit_ledger_no_truncate
        BEFORE TRUNCATE ON audit_ledger
        FOR EACH STATEMENT
        EXECUTE FUNCTION audit_ledger_immutable_guard();
    """

    # --- E00-S03: Row-Level Security Policies ---
    rls_policies_sql = """
    -- Enable RLS on tenant-scoped tables
    ALTER TABLE search_index ENABLE ROW LEVEL SECURITY;
    ALTER TABLE activity_feed ENABLE ROW LEVEL SECURITY;
    ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_ledger ENABLE ROW LEVEL SECURITY;

    -- Create RLS policies (idempotent via DROP IF EXISTS + CREATE)
    DROP POLICY IF EXISTS tenant_isolation_search ON search_index;
    CREATE POLICY tenant_isolation_search ON search_index
        USING (tenant_id = current_setting('alis.current_tenant', true));

    DROP POLICY IF EXISTS tenant_isolation_activity ON activity_feed;
    CREATE POLICY tenant_isolation_activity ON activity_feed
        USING (tenant_id = current_setting('alis.current_tenant', true));

    DROP POLICY IF EXISTS tenant_isolation_comments ON comments;
    CREATE POLICY tenant_isolation_comments ON comments
        USING (tenant_id = current_setting('alis.current_tenant', true));

    -- EC-CROSS-02: Audit ledger RLS — SELECT + INSERT only (immutable ledger)
    -- No UPDATE or DELETE policies exist intentionally; triggers handle the block.
    DROP POLICY IF EXISTS tenant_isolation_audit_ledger ON audit_ledger;
    DROP POLICY IF EXISTS tenant_audit_ledger_select ON audit_ledger;
    DROP POLICY IF EXISTS tenant_audit_ledger_insert ON audit_ledger;

    CREATE POLICY tenant_audit_ledger_select ON audit_ledger
        FOR SELECT
        USING (tenant_id = current_setting('alis.current_tenant', true));

    CREATE POLICY tenant_audit_ledger_insert ON audit_ledger
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E00-S09: Policy Registry Table ---
    policy_registry_table_sql = """
    CREATE TABLE IF NOT EXISTS policy_registry (
        id VARCHAR(100) PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        policy_type VARCHAR(100) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        parameters JSONB NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
        effective_to TIMESTAMP WITH TIME ZONE,
        content_hash VARCHAR(64) NOT NULL,
        module VARCHAR(50),
        created_by VARCHAR(100) NOT NULL,
        submitted_by VARCHAR(100),
        approved_by VARCHAR(100),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        submitted_at TIMESTAMP WITH TIME ZONE,
        approved_at TIMESTAMP WITH TIME ZONE,
        activated_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_policy_type_version_tenant
            UNIQUE (tenant_id, policy_type, version)
    );

    CREATE INDEX IF NOT EXISTS idx_policy_tenant
        ON policy_registry(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_policy_type_status
        ON policy_registry(tenant_id, policy_type, status);
    CREATE INDEX IF NOT EXISTS idx_policy_effective
        ON policy_registry(tenant_id, policy_type, effective_from, effective_to);
    """

    # --- E00-S09: Policy Immutability Guard (Layer 4) ---
    # Prevents mutation of ACTIVATED or SUPERSEDED policies.
    # Only status transitions FROM ACTIVATED → SUPERSEDED are allowed.
    policy_immutability_sql = """
    CREATE OR REPLACE FUNCTION policy_activated_guard()
    RETURNS TRIGGER AS $$
    BEGIN
        -- Allow status change ACTIVATED → SUPERSEDED (by system)
        IF OLD.status = 'ACTIVATED' AND NEW.status = 'SUPERSEDED'
           AND OLD.parameters::text = NEW.parameters::text
           AND OLD.effective_from = NEW.effective_from
           AND OLD.content_hash = NEW.content_hash
        THEN
            RETURN NEW;
        END IF;

        -- Block all other mutations on ACTIVATED or SUPERSEDED records
        IF OLD.status IN ('ACTIVATED', 'SUPERSEDED') THEN
            RAISE EXCEPTION
                'E00-S09 VIOLATION: Cannot mutate policy in % status. '
                'Retroactive policy modification is prohibited.',
                OLD.status;
            RETURN NULL;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_policy_immutability ON policy_registry;
    CREATE TRIGGER trg_policy_immutability
        BEFORE UPDATE ON policy_registry
        FOR EACH ROW
        EXECUTE FUNCTION policy_activated_guard();

    -- Block DELETE on policy_registry entirely (soft-delete only via SUPERSEDED)
    CREATE OR REPLACE FUNCTION policy_no_delete_guard()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION
            'E00-S09 VIOLATION: Hard deletion of policies is prohibited.';
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_policy_no_delete ON policy_registry;
    CREATE TRIGGER trg_policy_no_delete
        BEFORE DELETE ON policy_registry
        FOR EACH ROW
        EXECUTE FUNCTION policy_no_delete_guard();
    """

    # --- E00-S09: Policy RLS ---
    policy_rls_sql = """
    ALTER TABLE policy_registry ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_policy ON policy_registry;
    CREATE POLICY tenant_isolation_policy ON policy_registry
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E03-S02: LLM Model Registry Table ---
    llm_model_registry_table_sql = """
    CREATE TABLE IF NOT EXISTS llm_model_registry (
        id VARCHAR(100) PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        name VARCHAR(100) NOT NULL,
        version VARCHAR(50) NOT NULL,
        capability VARCHAR(50) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT FALSE,
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_llm_model_tenant
        ON llm_model_registry(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_llm_model_capability
        ON llm_model_registry(tenant_id, capability, is_active);

    -- Partial unique index: only one active model per capability per tenant
    CREATE UNIQUE INDEX IF NOT EXISTS uq_llm_model_active_capability
        ON llm_model_registry(tenant_id, capability)
        WHERE is_active = TRUE;
    """

    # --- E03-S02: LLM Model Registry RLS ---
    llm_model_rls_sql = """
    ALTER TABLE llm_model_registry ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_llm_models ON llm_model_registry;
    CREATE POLICY tenant_isolation_llm_models ON llm_model_registry
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E03-S02: Seed initial model (qwen 1.5 Q8) ---
    llm_model_seed_sql = """
    INSERT INTO llm_model_registry (id, tenant_id, name, version, capability, is_active, config)
    VALUES
        ('seed-qwen-infer', 'default', 'qwen', '1.5-q8', 'Infer', TRUE, '{"temperature": 0.0, "num_ctx": 4096, "num_gpu": 35, "num_thread": 8, "keep_alive": "5m"}'::jsonb),
        ('seed-qwen-score', 'default', 'qwen', '1.5-q8', 'Score', TRUE, '{"temperature": 0.0, "num_ctx": 4096, "num_gpu": 35, "num_thread": 8, "keep_alive": "5m"}'::jsonb),
        ('seed-qwen-plan',  'default', 'qwen', '1.5-q8', 'Plan',  TRUE, '{"temperature": 0.0, "num_ctx": 4096, "num_gpu": 35, "num_thread": 8, "keep_alive": "5m"}'::jsonb)
    ON CONFLICT (id) DO NOTHING;
    """

    # --- E03-S03: Prompt Registry Table ---
    prompt_registry_table_sql = """
    CREATE TABLE IF NOT EXISTS prompt_registry (
        id VARCHAR(100) PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        content TEXT NOT NULL,
        format VARCHAR(20) NOT NULL DEFAULT 'jinja2',
        description TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        content_hash VARCHAR(64) NOT NULL,
        created_by VARCHAR(100) NOT NULL,
        created_by_role VARCHAR(50) NOT NULL,
        activated_by VARCHAR(100),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        activated_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_prompt_name_version_tenant
            UNIQUE (tenant_id, name, version)
    );

    CREATE INDEX IF NOT EXISTS idx_prompt_tenant
        ON prompt_registry(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_prompt_name_status
        ON prompt_registry(tenant_id, name, status);
    CREATE INDEX IF NOT EXISTS idx_prompt_name_version
        ON prompt_registry(tenant_id, name, version);
    """

    # --- E03-S03: Prompt Immutability Guard (Layer 4) ---
    # Prevents mutation of ACTIVATED or SUPERSEDED prompts.
    # Only status transition ACTIVATED → SUPERSEDED is allowed.
    prompt_immutability_sql = """
    CREATE OR REPLACE FUNCTION prompt_activated_guard()
    RETURNS TRIGGER AS $$
    BEGIN
        -- Allow status change ACTIVATED → SUPERSEDED (by system)
        IF OLD.status = 'ACTIVATED' AND NEW.status = 'SUPERSEDED'
           AND OLD.content = NEW.content
           AND OLD.content_hash = NEW.content_hash
        THEN
            RETURN NEW;
        END IF;

        -- Block all other mutations on ACTIVATED or SUPERSEDED records
        IF OLD.status IN ('ACTIVATED', 'SUPERSEDED') THEN
            RAISE EXCEPTION
                'E03-S03 VIOLATION: Cannot mutate prompt in % status. '
                'Retroactive prompt modification is prohibited.',
                OLD.status;
            RETURN NULL;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_prompt_immutability ON prompt_registry;
    CREATE TRIGGER trg_prompt_immutability
        BEFORE UPDATE ON prompt_registry
        FOR EACH ROW
        EXECUTE FUNCTION prompt_activated_guard();

    -- Block DELETE on prompt_registry entirely
    CREATE OR REPLACE FUNCTION prompt_no_delete_guard()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION
            'E03-S03 VIOLATION: Hard deletion of prompts is prohibited.';
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_prompt_no_delete ON prompt_registry;
    CREATE TRIGGER trg_prompt_no_delete
        BEFORE DELETE ON prompt_registry
        FOR EACH ROW
        EXECUTE FUNCTION prompt_no_delete_guard();
    """

    # --- E03-S03: Prompt Registry RLS ---
    prompt_rls_sql = """
    ALTER TABLE prompt_registry ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_prompts ON prompt_registry;
    CREATE POLICY tenant_isolation_prompts ON prompt_registry
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E02-S02: Approval Requests & Actions Tables ---
    approval_requests_table_sql = """
    CREATE TABLE IF NOT EXISTS approval_requests (
        id               VARCHAR(100) PRIMARY KEY,
        tenant_id        VARCHAR(50)  NOT NULL,
        entity_type      VARCHAR(100) NOT NULL,
        entity_id        VARCHAR(100) NOT NULL,
        action_type      VARCHAR(100) NOT NULL,
        config_id        VARCHAR(100) NOT NULL,
        status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
        requested_by     VARCHAR(100) NOT NULL,
        required_roles   JSONB        NOT NULL DEFAULT '[]'::jsonb,
        mode             VARCHAR(20)  NOT NULL DEFAULT 'single',
        required_count   INTEGER      NOT NULL DEFAULT 1,
        resolved_at      TIMESTAMP WITH TIME ZONE,
        resolution_reason TEXT,
        context          JSONB        NOT NULL DEFAULT '{}'::jsonb,
        created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_ar_tenant_status
        ON approval_requests(tenant_id, status);
    CREATE INDEX IF NOT EXISTS idx_ar_entity
        ON approval_requests(tenant_id, entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_ar_requested_by
        ON approval_requests(tenant_id, requested_by);
    """

    approval_actions_table_sql = """
    CREATE TABLE IF NOT EXISTS approval_actions (
        id          VARCHAR(100) PRIMARY KEY,
        tenant_id   VARCHAR(50)  NOT NULL,
        request_id  VARCHAR(100) NOT NULL REFERENCES approval_requests(id),
        actor_id    VARCHAR(100) NOT NULL,
        actor_role  VARCHAR(50)  NOT NULL,
        action      VARCHAR(20)  NOT NULL,
        comment     TEXT,
        acted_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_approval_actor UNIQUE (request_id, actor_id)
    );

    CREATE INDEX IF NOT EXISTS idx_aa_request_id
        ON approval_actions(request_id);
    CREATE INDEX IF NOT EXISTS idx_aa_tenant_actor
        ON approval_actions(tenant_id, actor_id);
    """

    approval_rls_sql = """
    ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_approval_requests ON approval_requests;
    CREATE POLICY tenant_isolation_approval_requests ON approval_requests
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));

    ALTER TABLE approval_actions ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_approval_actions ON approval_actions;
    CREATE POLICY tenant_isolation_approval_actions ON approval_actions
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E01-S05: Organizations Table ---
    organizations_table_sql = """
    CREATE TABLE IF NOT EXISTS organizations (
        id          VARCHAR(100) PRIMARY KEY,
        tenant_id   VARCHAR(50)  NOT NULL,
        name        VARCHAR(256) NOT NULL,
        code        VARCHAR(32)  NOT NULL,
        parent_id   VARCHAR(100) REFERENCES organizations(id),
        status      VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
        is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
        deleted_at  TIMESTAMP WITH TIME ZONE,
        created_by  VARCHAR(100) NOT NULL,
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_org_code_tenant UNIQUE (tenant_id, code)
    );

    CREATE INDEX IF NOT EXISTS idx_org_tenant
        ON organizations(tenant_id)
        WHERE is_deleted = FALSE;
    CREATE INDEX IF NOT EXISTS idx_org_parent
        ON organizations(tenant_id, parent_id)
        WHERE is_deleted = FALSE;
    """

    organizations_rls_sql = """
    ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_organizations ON organizations;
    CREATE POLICY tenant_isolation_organizations ON organizations
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E01-S01: Users Table ---
    users_table_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id          VARCHAR(100) PRIMARY KEY,
        tenant_id   VARCHAR(50)  NOT NULL,
        username    VARCHAR(64)  NOT NULL,
        email       VARCHAR(255),
        display_name VARCHAR(256),
        password_hash VARCHAR(200) NOT NULL,
        role        VARCHAR(50)  NOT NULL DEFAULT 'student',
        actor_type  VARCHAR(20)  NOT NULL DEFAULT 'human',
        status      VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
        is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
        deleted_at  TIMESTAMP WITH TIME ZONE,
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMP WITH TIME ZONE,
        CONSTRAINT uq_users_username_tenant UNIQUE (tenant_id, username)
    );

    CREATE INDEX IF NOT EXISTS idx_users_tenant
        ON users(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_users_tenant_username
        ON users(tenant_id, username)
        WHERE is_deleted = FALSE;
    CREATE INDEX IF NOT EXISTS idx_users_tenant_role
        ON users(tenant_id, role)
        WHERE is_deleted = FALSE;
    """

    # --- E01-S01: Users RLS ---
    users_rls_sql = """
    ALTER TABLE users ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS tenant_isolation_users ON users;
    CREATE POLICY tenant_isolation_users ON users
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # --- E03-S03: Seed Admissions Prompts ---
    prompt_seed_sql = """
    INSERT INTO prompt_registry (
        id, tenant_id, name, version, content, format, description,
        status, content_hash, created_by, created_by_role,
        activated_by, activated_at
    ) VALUES
    (
        'seed-eligibility-extract-grades-v1',
        'default',
        'eligibility.extract_grades',
        1,
        'You are an academic document analyzer for an admissions system.\nExtract all subjects and their marks/grades from the following marksheet text.\n\nReturn ONLY a JSON object with this structure:\n{"subjects": [{"name": "...", "marks": ..., "max_marks": ...}], "aggregate_percentage": ...}\n\nMarksheet Text:\n{{ marksheet_text }}',
        'jinja2',
        'Extracts structured grade data from OCR marksheet text for the Eligibility Eval wizard (M1-W3).',
        'ACTIVATED',
        '',
        'system_seed',
        'SYSTEM',
        'system_seed',
        NOW()
    ),
    (
        'seed-eligibility-evaluate-v1',
        'default',
        'eligibility.evaluate',
        1,
        'You are an admissions eligibility evaluator.\nCompare the extracted grades against the admission criteria.\n\nYou MUST respond with ONLY a JSON object matching this schema:\n{\n  "decision": "<ELIGIBLE | PROVISIONALLY_ELIGIBLE | NOT_ELIGIBLE>",\n  "confidence_score": <0.0 to 1.0>,\n  "confidence_tier": "<HIGH | MEDIUM | LOW>",\n  "state_impact": "Draft",\n  "reasoning": "<explanation>"\n}\n\nRules:\n- confidence_score >= 0.8 → decision = ELIGIBLE\n- 0.5 <= confidence_score < 0.8 → decision = PROVISIONALLY_ELIGIBLE\n- confidence_score < 0.5 → decision = NOT_ELIGIBLE\n- state_impact MUST be ''Draft'' (AI cannot finalize decisions)\n\nExtracted Grades:\n{{ extracted_grades }}\n\nAdmission Criteria:\n{{ admission_criteria }}',
        'jinja2',
        'Evaluates applicant eligibility by comparing grades against criteria for the Eligibility Eval wizard (M1-W3).',
        'ACTIVATED',
        '',
        'system_seed',
        'SYSTEM',
        'system_seed',
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;
    """

    # --- E01-S03: Dynamic Role Management Tables ---

    custom_roles_table_sql = """
    CREATE TABLE IF NOT EXISTS custom_roles (
        id          VARCHAR(100) PRIMARY KEY,
        tenant_id   VARCHAR(50)  NOT NULL,
        module      VARCHAR(20)  NOT NULL,
        role_name   VARCHAR(100) NOT NULL,
        description TEXT,
        status      VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
        created_by  VARCHAR(100) NOT NULL,
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_custom_role_name_tenant UNIQUE (tenant_id, role_name)
    );

    CREATE INDEX IF NOT EXISTS idx_custom_roles_tenant
        ON custom_roles(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_custom_roles_tenant_module
        ON custom_roles(tenant_id, module);
    CREATE INDEX IF NOT EXISTS idx_custom_roles_tenant_status
        ON custom_roles(tenant_id, status);
    """

    custom_role_permissions_table_sql = """
    CREATE TABLE IF NOT EXISTS custom_role_permissions (
        id           VARCHAR(100) PRIMARY KEY,
        tenant_id    VARCHAR(50)  NOT NULL,
        role_id      VARCHAR(100) NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
        permission   VARCHAR(100) NOT NULL,
        status       VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
        requested_by VARCHAR(100) NOT NULL,
        requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        reviewed_by  VARCHAR(100),
        reviewed_at  TIMESTAMP WITH TIME ZONE,
        review_note  TEXT,
        CONSTRAINT uq_custom_role_permission UNIQUE (role_id, permission)
    );

    CREATE INDEX IF NOT EXISTS idx_crp_role_id
        ON custom_role_permissions(role_id);
    CREATE INDEX IF NOT EXISTS idx_crp_tenant_status
        ON custom_role_permissions(tenant_id, status);
    CREATE INDEX IF NOT EXISTS idx_crp_permission_status
        ON custom_role_permissions(permission, status);
    """

    user_custom_roles_table_sql = """
    CREATE TABLE IF NOT EXISTS user_custom_roles (
        id          VARCHAR(100) PRIMARY KEY,
        tenant_id   VARCHAR(50)  NOT NULL,
        user_id     VARCHAR(100) NOT NULL,
        role_id     VARCHAR(100) NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
        assigned_by VARCHAR(100) NOT NULL,
        assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_user_custom_role UNIQUE (user_id, role_id)
    );

    CREATE INDEX IF NOT EXISTS idx_ucr_user_id
        ON user_custom_roles(user_id);
    CREATE INDEX IF NOT EXISTS idx_ucr_tenant
        ON user_custom_roles(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_ucr_role_id
        ON user_custom_roles(role_id);
    """

    custom_roles_rls_sql = """
    ALTER TABLE custom_roles ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_custom_roles ON custom_roles;
    CREATE POLICY tenant_isolation_custom_roles ON custom_roles
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));

    ALTER TABLE custom_role_permissions ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_custom_role_perms ON custom_role_permissions;
    CREATE POLICY tenant_isolation_custom_role_perms ON custom_role_permissions
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));

    ALTER TABLE user_custom_roles ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_user_custom_roles ON user_custom_roles;
    CREATE POLICY tenant_isolation_user_custom_roles ON user_custom_roles
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    workflows_table_sql = """
    CREATE TABLE IF NOT EXISTS workflow_instances (
        id VARCHAR(100) PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        workflow_type VARCHAR(100) NOT NULL,
        current_state VARCHAR(50) NOT NULL,
        context JSONB,
        decision JSONB,
        approver_roles JSONB,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMP WITH TIME ZONE
    );
    CREATE INDEX IF NOT EXISTS idx_workflow_tenant ON workflow_instances(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_workflow_type ON workflow_instances(tenant_id, workflow_type);
    """

    workflow_steps_table_sql = """
    CREATE TABLE IF NOT EXISTS workflow_steps (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(50) NOT NULL,
        workflow_id VARCHAR(100) NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
        step_name VARCHAR(100) NOT NULL,
        outcome VARCHAR(50) NOT NULL,
        message TEXT,
        data JSONB,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id);
    """

    workflows_rls_sql = """
    ALTER TABLE workflow_instances ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_workflows ON workflow_instances;
    CREATE POLICY tenant_isolation_workflows ON workflow_instances
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));

    ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_workflow_steps ON workflow_steps;
    CREATE POLICY tenant_isolation_workflow_steps ON workflow_steps
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """

    # =========================================================================
    # E04: Admissions Tables
    # =========================================================================

    admissions_tables_sql = """
    CREATE TABLE IF NOT EXISTS applicants (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        name                VARCHAR(200) NOT NULL,
        email               VARCHAR(255) NOT NULL,
        phone               VARCHAR(30)  NOT NULL,
        intended_program    VARCHAR(200) NOT NULL,
        source_channel      VARCHAR(50)  NOT NULL DEFAULT 'website',
        status              VARCHAR(50)  NOT NULL DEFAULT 'APPLIED',
        metadata            JSONB        NOT NULL DEFAULT '{}',
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
        UNIQUE (org_id, email),
        UNIQUE (org_id, phone)
    );

    CREATE TABLE IF NOT EXISTS lead_merge_log (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        primary_id          VARCHAR(100) NOT NULL REFERENCES applicants(id),
        merged_id           VARCHAR(100) NOT NULL REFERENCES applicants(id),
        similarity_score    NUMERIC(6,4) NOT NULL,
        method              VARCHAR(30)  NOT NULL,
        justification       TEXT,
        merged_by           VARCHAR(100) NOT NULL,
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS application_documents (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        applicant_id        VARCHAR(100) NOT NULL REFERENCES applicants(id),
        doc_type            VARCHAR(50)  NOT NULL,
        file_path           TEXT         NOT NULL,
        is_verified         BOOLEAN      NOT NULL DEFAULT FALSE,
        verification_method VARCHAR(50),
        verification_detail TEXT,
        verified_by         VARCHAR(100),
        verified_at         TIMESTAMPTZ,
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS counsellor_assignments (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        applicant_id        VARCHAR(100) NOT NULL REFERENCES applicants(id),
        counsellor_id       VARCHAR(100) NOT NULL,
        method              VARCHAR(30)  NOT NULL,
        similarity_score    NUMERIC(6,4),
        assigned_by         VARCHAR(100) NOT NULL,
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
        UNIQUE (org_id, applicant_id)
    );

    CREATE TABLE IF NOT EXISTS offer_letters (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        applicant_id        VARCHAR(100) NOT NULL REFERENCES applicants(id),
        program_name        VARCHAR(200) NOT NULL,
        academic_year       VARCHAR(10)  NOT NULL,
        template_version    INTEGER      NOT NULL DEFAULT 1,
        content_hash        VARCHAR(64)  NOT NULL,
        pdf_path            TEXT         NOT NULL,
        issued_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
        is_valid            BOOLEAN      NOT NULL DEFAULT TRUE
    );

    CREATE TABLE IF NOT EXISTS admission_records (
        id                  VARCHAR(100) PRIMARY KEY,
        org_id              VARCHAR(50)  NOT NULL,
        applicant_id        VARCHAR(100) NOT NULL REFERENCES applicants(id),
        registration_number VARCHAR(50)  NOT NULL UNIQUE,
        payment_reference   VARCHAR(100) NOT NULL,
        fee_amount          NUMERIC(12,2) NOT NULL,
        admitted_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
        admitted_by         VARCHAR(100) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS intake_quality_scores (
        id              VARCHAR(100) PRIMARY KEY,
        org_id          VARCHAR(50)  NOT NULL,
        batch_id        VARCHAR(100) NOT NULL,
        program         VARCHAR(200),
        quality_score   NUMERIC(6,4) NOT NULL,
        factors         JSONB        NOT NULL DEFAULT '{}',
        alert_triggered BOOLEAN      NOT NULL DEFAULT FALSE,
        scored_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS students (
        id              VARCHAR(100) PRIMARY KEY,
        org_id          VARCHAR(50)  NOT NULL,
        applicant_id    VARCHAR(100) NOT NULL REFERENCES applicants(id),
        roll_number     VARCHAR(50)  NOT NULL UNIQUE,
        name            VARCHAR(200) NOT NULL,
        email           VARCHAR(255) NOT NULL,
        phone           VARCHAR(30)  NOT NULL,
        program         VARCHAR(200) NOT NULL,
        enrolled_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """

    admissions_rls_sql = """
    ALTER TABLE applicants ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_applicants ON applicants;
    CREATE POLICY tenant_isolation_applicants ON applicants
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE lead_merge_log ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_lead_merge ON lead_merge_log;
    CREATE POLICY tenant_isolation_lead_merge ON lead_merge_log
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE application_documents ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_app_docs ON application_documents;
    CREATE POLICY tenant_isolation_app_docs ON application_documents
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE counsellor_assignments ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_counsellor ON counsellor_assignments;
    CREATE POLICY tenant_isolation_counsellor ON counsellor_assignments
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE offer_letters ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_offer_letters ON offer_letters;
    CREATE POLICY tenant_isolation_offer_letters ON offer_letters
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE admission_records ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_admission_records ON admission_records;
    CREATE POLICY tenant_isolation_admission_records ON admission_records
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE intake_quality_scores ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_intake_scores ON intake_quality_scores;
    CREATE POLICY tenant_isolation_intake_scores ON intake_quality_scores
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));

    ALTER TABLE students ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation_students ON students;
    CREATE POLICY tenant_isolation_students ON students
        FOR ALL
        USING (org_id = current_setting('alis.current_tenant', true))
        WITH CHECK (org_id = current_setting('alis.current_tenant', true));
    """

    # --- EC-CROSS-01: Domain Event Idempotency Log ---
    # Prevents Celery from executing the same domain event handler twice on retry.
    # UNIQUE(event_id, handler_name) makes every handler invocation idempotent.
    domain_event_handler_log_sql = """
    CREATE TABLE IF NOT EXISTS domain_event_handler_log (
        id              BIGSERIAL    PRIMARY KEY,
        event_id        VARCHAR(100) NOT NULL,
        handler_name    VARCHAR(200) NOT NULL,
        status          VARCHAR(20)  NOT NULL DEFAULT 'SUCCESS',
        error_detail    TEXT,
        processed_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_event_handler UNIQUE (event_id, handler_name)
    );

    CREATE INDEX IF NOT EXISTS idx_dehl_event_id
        ON domain_event_handler_log(event_id);
    CREATE INDEX IF NOT EXISTS idx_dehl_handler_status
        ON domain_event_handler_log(handler_name, status);
    """

    # --- EC-CROSS-01: idempotency_store (Celery task-level dedup) ---
    idempotency_store_sql = """
    CREATE TABLE IF NOT EXISTS idempotency_store (
        idempotency_key VARCHAR(200) PRIMARY KEY,
        task_name       VARCHAR(200) NOT NULL,
        result          JSONB,
        created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        expires_at      TIMESTAMP WITH TIME ZONE NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_idem_expires
        ON idempotency_store(expires_at);
    """

    try:
        execute_system_transaction_sync([
            (tenant_session_var_sql, None),
            (approval_requests_table_sql, None),
            (approval_actions_table_sql, None),
            (approval_rls_sql, None),
            (organizations_table_sql, None),
            (organizations_rls_sql, None),
            (users_table_sql, None),
            (users_rls_sql, None),
            (search_table_sql, None),
            (activity_table_sql, None),
            (comments_table_sql, None),
            (audit_ledger_table_sql, None),
            (audit_ledger_immutability_sql, None),
            (rls_policies_sql, None),
            (policy_registry_table_sql, None),
            (policy_immutability_sql, None),
            (policy_rls_sql, None),
            (llm_model_registry_table_sql, None),
            (llm_model_rls_sql, None),
            (llm_model_seed_sql, None),
            (prompt_registry_table_sql, None),
            (prompt_immutability_sql, None),
            (prompt_rls_sql, None),
            (prompt_seed_sql, None),
            (custom_roles_table_sql, None),
            (custom_role_permissions_table_sql, None),
            (user_custom_roles_table_sql, None),
            (custom_roles_rls_sql, None),
            (workflows_table_sql, None),
            (workflow_steps_table_sql, None),
            (workflows_rls_sql, None),
            # E04: Admissions
            (admissions_tables_sql, None),
            (admissions_rls_sql, None),
            # EC-CROSS-01: Celery idempotency
            (domain_event_handler_log_sql, None),
            (idempotency_store_sql, None),
        ])
        logger.info(
            "Database tables initialized with tenant isolation "
            "(users, search, activity, comments, audit_ledger, policy_registry, "
            "llm_model_registry, prompt_registry, approval_requests, approval_actions, "
            "organizations, custom_roles, "
            "custom_role_permissions, user_custom_roles, workflows, "
            "applicants, lead_merge_log, application_documents, "
            "counsellor_assignments, offer_letters, admission_records, "
            "intake_quality_scores, students, "
            "domain_event_handler_log, idempotency_store "
            "+ RLS policies + immutability triggers)."
        )
    except Exception as e:
        logger.error(f"Failed to init DB: {e}")

