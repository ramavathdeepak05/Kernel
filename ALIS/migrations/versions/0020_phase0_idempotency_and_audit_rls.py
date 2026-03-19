"""Phase 0 hardening: Celery idempotency + audit ledger RLS

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-15

Changes
───────
1. EC-CROSS-01: domain_event_handler_log
   Prevents Celery from executing the same domain event handler twice
   when a task is retried after a worker crash.  UNIQUE(event_id, handler_name)
   makes every handler invocation idempotent — if the handler already completed
   successfully, it is skipped on retry.

2. EC-CROSS-01: idempotency_store
   General-purpose Celery task deduplication store.  Keyed by a
   caller-provided idempotency_key.  Rows expire after the TTL so the
   table doesn't grow unbounded.

3. EC-CROSS-02: audit_ledger RLS — split FOR ALL → SELECT + INSERT
   The previous policy used FOR ALL which inadvertently granted UPDATE
   and DELETE access at the policy level (blocked only by trigger).
   Splitting into explicit SELECT and INSERT policies removes the
   policy-level permission for UPDATE/DELETE, layering defence-in-depth
   with the existing immutability trigger.
"""

from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # EC-CROSS-01: domain_event_handler_log
    # -------------------------------------------------------------------------
    op.execute("""
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
    """)

    # -------------------------------------------------------------------------
    # EC-CROSS-01: idempotency_store
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS idempotency_store (
        idempotency_key VARCHAR(200) PRIMARY KEY,
        task_name       VARCHAR(200) NOT NULL,
        result          JSONB,
        created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        expires_at      TIMESTAMP WITH TIME ZONE NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_idem_expires
        ON idempotency_store(expires_at);
    """)

    # -------------------------------------------------------------------------
    # EC-CROSS-02: audit_ledger RLS — replace FOR ALL with SELECT + INSERT
    # -------------------------------------------------------------------------
    op.execute("""
    -- Drop the over-permissive FOR ALL policy
    DROP POLICY IF EXISTS tenant_isolation_audit_ledger ON audit_ledger;

    -- SELECT: tenant can only see their own rows
    DROP POLICY IF EXISTS tenant_audit_ledger_select ON audit_ledger;
    CREATE POLICY tenant_audit_ledger_select ON audit_ledger
        FOR SELECT
        USING (tenant_id = current_setting('alis.current_tenant', true));

    -- INSERT: tenant can only append their own rows
    DROP POLICY IF EXISTS tenant_audit_ledger_insert ON audit_ledger;
    CREATE POLICY tenant_audit_ledger_insert ON audit_ledger
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));

    -- No UPDATE or DELETE policy exists — immutability trigger handles the block.
    """)


def downgrade() -> None:
    # Restore old FOR ALL policy
    op.execute("""
    DROP POLICY IF EXISTS tenant_audit_ledger_select ON audit_ledger;
    DROP POLICY IF EXISTS tenant_audit_ledger_insert ON audit_ledger;

    CREATE POLICY tenant_isolation_audit_ledger ON audit_ledger
        FOR ALL
        USING (tenant_id = current_setting('alis.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('alis.current_tenant', true));
    """)

    op.execute("DROP TABLE IF EXISTS idempotency_store;")
    op.execute("DROP TABLE IF EXISTS domain_event_handler_log;")
