"""0036 — workflow_tasks: agent-rail columns + indexes

Revision ID: 0036
Revises: 0035
Create Date: 2026-03-20

Adds four columns required by context_advisor_v1 count queries:

    tenant_id          — explicit tenant scoping alias for org_id.
                         RLS already enforces via org_id; this column lets the
                         agent-rail queries use a stable, named filter key.
    urgency            — 'HIGH' | 'NORMAL' | 'LOW'. Used for urgent-item counts.
    assignee_role      — role-wide task assignment (e.g. 'registrar').
    assignee_actor_id  — personally-assigned tasks; higher signal than role-wide.

Backfill:
    tenant_id is set to org_id for all existing rows.
    urgency defaults to 'NORMAL'.
    assignee_role / assignee_actor_id are NULL for existing rows.

Indexes:
    idx_wt_tenant_status           — primary agent-rail query filter
    idx_wt_tenant_status_sla       — SLA breach count (sla_deadline < NOW())
"""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New columns — all IF NOT EXISTS so re-runs and test-fixture
    #    pre-provisioning are both handled safely.
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE workflow_tasks
            ADD COLUMN IF NOT EXISTS tenant_id         TEXT,
            ADD COLUMN IF NOT EXISTS urgency           TEXT NOT NULL DEFAULT 'NORMAL',
            ADD COLUMN IF NOT EXISTS assignee_role     TEXT,
            ADD COLUMN IF NOT EXISTS assignee_actor_id TEXT
    """)

    # ------------------------------------------------------------------
    # 2. Backfill tenant_id from org_id for existing rows
    # ------------------------------------------------------------------
    op.execute("""
        UPDATE workflow_tasks
        SET tenant_id = org_id
        WHERE tenant_id IS NULL
    """)

    # ------------------------------------------------------------------
    # 3. Make tenant_id NOT NULL now that backfill is done
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE workflow_tasks
            ALTER COLUMN tenant_id SET NOT NULL,
            ALTER COLUMN tenant_id SET DEFAULT ''
    """)

    # ------------------------------------------------------------------
    # 4. Indexes for agent-rail count queries
    #    Pattern: WHERE tenant_id = %s AND status = 'PENDING'
    #               AND (assignee_role = %s OR assignee_actor_id = %s)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_wt_tenant_status
            ON workflow_tasks (tenant_id, status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_wt_tenant_status_sla
            ON workflow_tasks (tenant_id, status, sla_deadline)
            WHERE sla_deadline IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wt_tenant_status_sla")
    op.execute("DROP INDEX IF EXISTS idx_wt_tenant_status")

    op.execute("""
        ALTER TABLE workflow_tasks
            DROP COLUMN IF EXISTS assignee_actor_id,
            DROP COLUMN IF EXISTS assignee_role,
            DROP COLUMN IF EXISTS urgency,
            DROP COLUMN IF EXISTS tenant_id
    """)
