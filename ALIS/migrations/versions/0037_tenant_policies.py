"""0037 — tenant_policies table

Revision ID: 0037
Revises: 0036
Create Date: 2026-03-20

Creates the tenant_policies table consumed by policy_engine.evaluate().

The policy engine reads rules from this table and evaluates them with
the asteval-safe DSL. Policies are versioned, scoped to a tenant, and
time-bounded (effective_from / effective_until).

First policy seeded via scripts/seed.py: agent_rail_silence —
    three rules governing when the agent rail proactively surfaces
    information vs. stays silent.

RLS:
    tenant_id = current_setting('app.tenant_id', true)
    Same pattern as all other tenant-scoped tables.
"""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_policies (
            id              TEXT         PRIMARY KEY,
            tenant_id       TEXT         NOT NULL,
            policy_id       TEXT         NOT NULL,
            version         INTEGER      NOT NULL DEFAULT 1,
            scope           TEXT         NOT NULL DEFAULT 'tenant',
            rules           JSONB        NOT NULL DEFAULT '[]',
            status          TEXT         NOT NULL DEFAULT 'DRAFT',
            effective_from  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            effective_until TIMESTAMPTZ,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_tenant_policy_version
                UNIQUE (tenant_id, policy_id, version),

            CONSTRAINT ck_tenant_policies_status
                CHECK (status IN ('DRAFT', 'APPROVED', 'ARCHIVED'))
        )
    """)

    # ------------------------------------------------------------------
    # 2. Indexes
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tenant_policies_lookup
            ON tenant_policies (tenant_id, policy_id, status, effective_from)
    """)

    # ------------------------------------------------------------------
    # 3. RLS — same pattern as workflow_tasks, leads, audit_ledger
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'tenant_policies'
                  AND policyname = 'tenant_policies_isolation'
            ) THEN
                EXECUTE '
                    CREATE POLICY tenant_policies_isolation
                        ON tenant_policies
                        USING (tenant_id = current_setting(''app.tenant_id'', true))
                ';
            END IF;
        END;
        $$
    """)

    op.execute("ALTER TABLE tenant_policies ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_policies DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_policies_isolation ON tenant_policies")
    op.execute("DROP INDEX IF EXISTS idx_tenant_policies_lookup")
    op.execute("DROP TABLE IF EXISTS tenant_policies")
