"""
Control Plane Database — S2

Manages the control plane's own PostgreSQL database (alis_control).
This DB stores the tenant registry: tenant metadata, DB connection config,
plan info, and lifecycle state.

The control plane DB is separate from all tenant DBs. It does NOT use RLS
or per-tenant pools — it has one small DB for its own records.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_pool = None  # psycopg2 ThreadedConnectionPool


def init_db_pool() -> None:
    """Create the psycopg2 connection pool. Call once at startup."""
    global _pool
    import psycopg2.pool
    from control_plane.settings import settings

    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=settings.cp_db_url,
    )
    logger.info("Control plane DB pool initialised at %s", settings.cp_db_url)


def close_db_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Control plane DB pool closed.")


@contextmanager
def get_conn():
    """Get a psycopg2 connection from the pool."""
    if _pool is None:
        raise RuntimeError("Control plane DB pool not initialised.")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def query(sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """Execute a SELECT and return list of row dicts."""
    import psycopg2.extras
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                return [dict(r) for r in cur.fetchall()]
            return []


def execute(sql: str, params: Optional[Tuple] = None) -> None:
    """Execute an INSERT/UPDATE/DELETE and commit."""
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_schema() -> None:
    """
    Create the control plane schema if it doesn't exist.

    Called once at startup. Idempotent (IF NOT EXISTS everywhere).
    """
    schema_sql = """
    CREATE TABLE IF NOT EXISTS cp_tenants (
        tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        subdomain       VARCHAR(100) UNIQUE NOT NULL,
        display_name    VARCHAR(255) NOT NULL,
        region          VARCHAR(50)  NOT NULL DEFAULT 'in-central',
        db_host         VARCHAR(255) NOT NULL,
        db_port         INTEGER      NOT NULL DEFAULT 5432,
        db_name         VARCHAR(100) NOT NULL,
        db_user         VARCHAR(100) NOT NULL,
        db_password_enc TEXT         NOT NULL,
        plan            VARCHAR(50)  NOT NULL DEFAULT 'starter',
        feature_flags   JSONB        NOT NULL DEFAULT '{}',
        status          VARCHAR(50)  NOT NULL DEFAULT 'active',
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        suspended_at    TIMESTAMPTZ,
        deleted_at      TIMESTAMPTZ,
        bucket_name     VARCHAR(200)                    -- S5: per-tenant S3 bucket
    );

    CREATE INDEX IF NOT EXISTS idx_cp_tenants_subdomain ON cp_tenants (subdomain);
    CREATE INDEX IF NOT EXISTS idx_cp_tenants_status    ON cp_tenants (status);
    CREATE INDEX IF NOT EXISTS idx_cp_tenants_region    ON cp_tenants (region);

    CREATE TABLE IF NOT EXISTS cp_provisioning_log (
        id              BIGSERIAL    PRIMARY KEY,
        tenant_id       UUID         NOT NULL,
        action          VARCHAR(50)  NOT NULL,
        status          VARCHAR(50)  NOT NULL DEFAULT 'started',
        started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        finished_at     TIMESTAMPTZ,
        error           TEXT,
        metadata        JSONB        NOT NULL DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_cp_plog_tenant ON cp_provisioning_log (tenant_id);

    -- S4: Usage events (immutable append-only)
    CREATE TABLE IF NOT EXISTS cp_usage_events (
        id          BIGSERIAL    PRIMARY KEY,
        tenant_id   UUID         NOT NULL,
        event_type  VARCHAR(50)  NOT NULL,
        quantity    NUMERIC(20,6) NOT NULL DEFAULT 0,
        metadata    JSONB        NOT NULL DEFAULT '{}',
        recorded_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_cp_usage_tenant_period
        ON cp_usage_events (tenant_id, recorded_at);
    CREATE INDEX IF NOT EXISTS idx_cp_usage_event_type
        ON cp_usage_events (event_type);

    -- S4: Invoices (one per tenant per calendar month)
    CREATE TABLE IF NOT EXISTS cp_invoices (
        id          BIGSERIAL    PRIMARY KEY,
        tenant_id   UUID         NOT NULL,
        period      VARCHAR(7)   NOT NULL,          -- "YYYY-MM"
        period_start DATE        NOT NULL,
        period_end   DATE        NOT NULL,
        plan        VARCHAR(50)  NOT NULL,
        line_items  JSONB        NOT NULL DEFAULT '[]',
        subtotal    NUMERIC(14,2) NOT NULL DEFAULT 0,
        tax         NUMERIC(14,2) NOT NULL DEFAULT 0,
        total       NUMERIC(14,2) NOT NULL DEFAULT 0,
        currency    VARCHAR(3)   NOT NULL DEFAULT 'USD',
        status      VARCHAR(20)  NOT NULL DEFAULT 'draft',
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        issued_at   TIMESTAMPTZ,
        UNIQUE (tenant_id, period)
    );

    CREATE INDEX IF NOT EXISTS idx_cp_invoices_tenant ON cp_invoices (tenant_id);
    CREATE INDEX IF NOT EXISTS idx_cp_invoices_status  ON cp_invoices (status);

    -- S9: Plan configuration (dynamic billing plans)
    CREATE TABLE IF NOT EXISTS cp_plans (
        name                VARCHAR(50) PRIMARY KEY,
        monthly_price_usd   NUMERIC(10,2) NOT NULL,
        token_quota         INTEGER       NOT NULL,
        storage_gb_quota    INTEGER       NOT NULL,
        api_call_quota      INTEGER       NOT NULL,
        active_user_quota   INTEGER       NOT NULL,
        overage_token_per_1k NUMERIC(8,4) NOT NULL,
        overage_storage_gb   NUMERIC(8,4) NOT NULL,
        overage_api_per_1k   NUMERIC(8,4) NOT NULL,
        overage_user         NUMERIC(8,4) NOT NULL,
        status              VARCHAR(20)   NOT NULL DEFAULT 'active',
        created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    );

    -- S9: Payment records (Stripe/Razorpay webhook outcomes)
    CREATE TABLE IF NOT EXISTS cp_payments (
        id              BIGSERIAL    PRIMARY KEY,
        tenant_id       UUID         NOT NULL,
        invoice_id      BIGINT       REFERENCES cp_invoices(id),
        provider        VARCHAR(50)  NOT NULL,       -- stripe | razorpay
        provider_payment_id VARCHAR(200) NOT NULL,
        amount          NUMERIC(14,2) NOT NULL,
        currency        VARCHAR(3)   NOT NULL DEFAULT 'USD',
        status          VARCHAR(50)  NOT NULL DEFAULT 'pending',  -- pending | succeeded | failed | refunded
        webhook_payload JSONB        NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_cp_payments_tenant ON cp_payments (tenant_id);
    CREATE INDEX IF NOT EXISTS idx_cp_payments_provider_id ON cp_payments (provider_payment_id);
    """
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
            logger.info("Control plane schema ready.")
        except Exception as exc:
            conn.rollback()
            logger.error("Control plane schema init failed: %s", exc)
            raise
