"""RBAC scope model + domain_events hardening

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-14

Changes
───────
1. role_assignments table
   The existing RBAC model stores a flat `role TEXT` on the users row.
   That gives every HOD STUDENT_READ across the entire institution —
   which is not what the product intends.

   This migration adds a proper `role_assignments` table with an
   optional scope, so role grants can be narrowed to a specific
   department, program, course, hostel block, etc.

   scope_type  │ scope_ref example
   ────────────┼──────────────────────────────────────────
   NULL        │ org-wide (backwards-compatible default)
   DEPARTMENT  │ dept_id (e.g. "CSE", "MECH")
   PROGRAM     │ program_id (e.g. "B.Tech-CSE-2024")
   COURSE      │ course_id
   HOSTEL_BLOCK│ block_id
   EXAM_BATCH  │ batch_id

   The flat users.role column is NOT removed — it continues to serve
   as the primary role for simple permission checks.  role_assignments
   provides the additional scoped grants that the policy engine evaluates
   for RBAC boundary enforcement.

2. domain_events.processing_started_at column
   Without this, there is no way to distinguish between an event that
   was never dispatched (PENDING) and one that started processing but
   whose worker crashed mid-flight (stuck PROCESSING).

   The retry Beat task can now query:
       WHERE status = 'PROCESSING'
         AND processing_started_at < NOW() - INTERVAL '2 minutes'
   to find stuck events and requeue them — separately from the
   PENDING event retry path.
"""

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. role_assignments — scoped RBAC grants
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS role_assignments (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      TEXT NOT NULL,
        user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,

        -- scope_type = NULL means org-wide (equivalent to the existing flat model).
        -- When set, the grant applies only to the specified resource.
        scope_type  TEXT,    -- DEPARTMENT | PROGRAM | COURSE | HOSTEL_BLOCK | EXAM_BATCH
        scope_ref   TEXT,    -- the id of the scoped resource

        granted_by  UUID NOT NULL,
        granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        -- Optional expiry -- for temporary elevated roles (e.g. exam duty)
        expires_at  TIMESTAMPTZ
    )""")

    # PostgreSQL UNIQUE constraints don't support expressions; use a unique index
    # COALESCE normalises NULL scope values so a user can't hold the same role
    # org-wide twice, but CAN hold it org-wide AND scoped.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_role_assignment
        ON role_assignments (org_id, user_id, role_id,
                             COALESCE(scope_type, ''), COALESCE(scope_ref, ''))
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_role_asgn_org_user  ON role_assignments(org_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_asgn_org_role  ON role_assignments(org_id, role_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_asgn_scope     ON role_assignments(org_id, scope_type, scope_ref)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_asgn_expires   ON role_assignments(expires_at) WHERE expires_at IS NOT NULL")

    # RLS — tenant isolation
    op.execute("ALTER TABLE role_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY role_assignments_tenant_isolation
        ON role_assignments
        USING (org_id::text = current_setting('alis.current_tenant', TRUE))
    """)

    # -------------------------------------------------------------------------
    # 2. domain_events — add processing_started_at for stuck-event detection
    # -------------------------------------------------------------------------
    op.execute("""
        ALTER TABLE domain_events
        ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ
    """)

    # Index so the stuck-event query (status=PROCESSING + old processing_started_at)
    # doesn't do a sequential scan on a potentially large events table.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_stuck
        ON domain_events(status, processing_started_at)
        WHERE status = 'PROCESSING'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_stuck")
    op.execute("ALTER TABLE domain_events DROP COLUMN IF EXISTS processing_started_at")

    op.execute("DROP POLICY IF EXISTS role_assignments_tenant_isolation ON role_assignments")
    op.execute("DROP TABLE IF EXISTS role_assignments CASCADE")
