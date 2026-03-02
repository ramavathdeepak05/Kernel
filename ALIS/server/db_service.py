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

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool as pg_pool_module
except ImportError:
    logging.warning("psycopg2 not found. Database functionality will be mocked or fail.")
    psycopg2 = None
    pg_pool_module = None

# Configure Logging
logger = logging.getLogger(__name__)

# Connection Pool (Global)
_pg_pool = None


def get_db_pool():
    """Initialize and return the connection pool."""
    global _pg_pool
    if _pg_pool is None and psycopg2:
        try:
            _pg_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "alis_db")
            )
            logger.info("Database connection pool initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    return _pg_pool


@contextmanager
def get_db_connection():
    """
    Context manager to get a connection from the pool.
    Ensures connection is returned to the pool even on error.
    """
    pool = get_db_pool()
    if not pool:
        raise RuntimeError("Database connection pool is not available.")

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


def execute_query(
    query: str,
    params: Optional[Tuple] = None,
    tenant_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Execute a read-only query with MANDATORY tenant scoping.

    The tenant_id is resolved in this priority:
    1. Explicit `tenant_id` parameter (for internal service calls)
    2. Request-scoped ContextVar (set by TenantMiddleware)

    If neither is available, the query is REJECTED (Layer 4 Invariant).

    Args:
        query: SQL query string
        params: Tuple of parameters for variable substitution
        tenant_id: Optional explicit tenant override

    Returns:
        List of dicts representing rows.

    Raises:
        TenantIsolationError: If tenant context cannot be resolved.
    """
    if not psycopg2:
        logger.warning("Mocking execute_query due to missing driver.")
        return []

    # Resolve tenant_id
    resolved_tenant = tenant_id or _get_tenant_id_from_context()

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Set tenant context on connection (for RLS policies)
                _set_tenant_on_connection(cursor, resolved_tenant)

                cursor.execute(query, params)
                if cursor.description:
                    return cursor.fetchall()
                return []
            except Exception as e:
                logger.error(f"Query execution failed: {e}\nQuery: {query}")
                raise


def execute_transaction(
    queries: List[Tuple[str, Optional[Tuple]]],
    tenant_id: Optional[str] = None
) -> None:
    """
    Execute a list of queries as a single atomic transaction
    with MANDATORY tenant scoping.

    Args:
        queries: List of (query_string, params_tuple)
        tenant_id: Optional explicit tenant override

    Raises:
        TenantIsolationError: If tenant context cannot be resolved.
    """
    if not psycopg2:
        logger.warning("Mocking execute_transaction.")
        return

    # --- E00-S05: Lockdown Write Gate (Layer 4) ---
    # Block all state mutations when system is in lockdown mode.
    # Admin/SuperAdmin bypass is handled inside assert_write_allowed.
    from server.core.lockdown import LockdownManager
    LockdownManager.assert_write_allowed()

    # Resolve tenant_id
    resolved_tenant = tenant_id or _get_tenant_id_from_context()

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                # Set tenant context for the entire transaction
                _set_tenant_on_connection(cursor, resolved_tenant)

                for query, params in queries:
                    cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise


def execute_system_query(
    query: str,
    params: Optional[Tuple] = None
) -> List[Dict[str, Any]]:
    """
    Execute a system-level query WITHOUT tenant scoping.

    USE SPARINGLY. This is for:
    - Schema migrations
    - Health checks
    - System-wide analytics (by SUPER_ADMIN only)
    - Database initialization

    This function does NOT set alis.current_tenant, so RLS policies
    will block access to tenant-scoped tables unless the connection
    role has the BYPASSRLS attribute.

    Args:
        query: SQL query string
        params: Tuple of parameters for variable substitution

    Returns:
        List of dicts representing rows.
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


def execute_system_transaction(
    queries: List[Tuple[str, Optional[Tuple]]]
) -> None:
    """
    Execute a system-level transaction WITHOUT tenant scoping.

    USE SPARINGLY. Same restrictions as execute_system_query.
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

    -- E00-S02: Audit ledger RLS — tenant-scoped SELECT + INSERT only
    DROP POLICY IF EXISTS tenant_isolation_audit_ledger ON audit_ledger;
    CREATE POLICY tenant_isolation_audit_ledger ON audit_ledger
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
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

    try:
        execute_system_transaction([
            (tenant_session_var_sql, None),
            (search_table_sql, None),
            (activity_table_sql, None),
            (comments_table_sql, None),
            (audit_ledger_table_sql, None),
            (audit_ledger_immutability_sql, None),
            (rls_policies_sql, None),
            (policy_registry_table_sql, None),
            (policy_immutability_sql, None),
            (policy_rls_sql, None),
        ])
        logger.info(
            "Database tables initialized with tenant isolation "
            "(search, activity, comments, audit_ledger, policy_registry "
            "+ RLS policies + immutability triggers)."
        )
    except Exception as e:
        logger.error(f"Failed to init DB: {e}")

