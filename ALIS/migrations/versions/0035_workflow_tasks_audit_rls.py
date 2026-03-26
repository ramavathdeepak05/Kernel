"""0035 — workflow_tasks table + audit ledger immutability trigger + RLS hardening

Revision ID: 0035
Revises: 0034
Create Date: 2026-03-20

Fixes three confirmed production blockers:
  1. workflow_tasks table missing — referenced by course_handover_workflow,
     deduplication_service, and forgery_detection but never created.
  2. audit_ledger has no immutability trigger — anyone with DB access could
     UPDATE or DELETE audit entries.
  3. RLS disabled on audit_ledger and leads — cross-tenant reads possible.
"""
from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. workflow_tasks — union of all columns used across 3 service files
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_tasks (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id              TEXT NOT NULL,
            workflow_type       TEXT NOT NULL,
            task_type           TEXT NOT NULL DEFAULT '',
            resource_id         UUID,
            status              TEXT NOT NULL DEFAULT 'PENDING',
            payload             JSONB NOT NULL DEFAULT '{}',
            requires_roles      TEXT[] NOT NULL DEFAULT '{}',
            created_by          UUID,
            resolved_by         UUID,
            resolved_at         TIMESTAMPTZ,
            resolution_notes    TEXT,
            sla_deadline        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_workflow_tasks_org_status
            ON workflow_tasks (org_id, status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_workflow_tasks_resource
            ON workflow_tasks (resource_id)
    """)

    op.execute("""
        CREATE POLICY workflow_tasks_tenant_isolation
            ON workflow_tasks
            USING (org_id = current_setting('app.tenant_id', true))
    """)

    op.execute("ALTER TABLE workflow_tasks ENABLE ROW LEVEL SECURITY")

    # ------------------------------------------------------------------
    # 2. audit_ledger immutability trigger
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_audit_ledger_immutable()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_ledger is immutable: UPDATE and DELETE are forbidden. '
                'Operation: %, Row ID: %', TG_OP, OLD.id;
        END;
        $$
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_ledger_immutable
        BEFORE UPDATE OR DELETE ON audit_ledger
        FOR EACH ROW EXECUTE FUNCTION fn_audit_ledger_immutable()
    """)

    op.execute("ALTER TABLE audit_ledger ENABLE ROW LEVEL SECURITY")

    # ------------------------------------------------------------------
    # 3. leads — enable RLS (policy already defined in earlier migration;
    #    if not, create it now)
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'leads'
                  AND policyname = 'leads_tenant_isolation'
            ) THEN
                EXECUTE '
                    CREATE POLICY leads_tenant_isolation
                        ON leads
                        USING (org_id = current_setting(''app.tenant_id'', true))
                ';
            END IF;
        END;
        $$
    """)

    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # RLS
    op.execute("ALTER TABLE leads DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS leads_tenant_isolation ON leads")
    op.execute("ALTER TABLE audit_ledger DISABLE ROW LEVEL SECURITY")

    # Immutability trigger
    op.execute("DROP TRIGGER IF EXISTS trg_audit_ledger_immutable ON audit_ledger")
    op.execute("DROP FUNCTION IF EXISTS fn_audit_ledger_immutable()")

    # workflow_tasks
    op.execute("DROP TABLE IF EXISTS workflow_tasks")
