"""Dynamic Process Engine — process definitions, steps, instances, form submissions

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-06
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # E13-S01 — Process Definitions
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS process_definitions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        description     TEXT,
        trigger_event   TEXT,            -- domain event that auto-launches this process (NULL = manual only)
        trigger_filter  JSONB DEFAULT '{}',  -- filter on event payload to decide if process should launch
        context_schema  JSONB DEFAULT '{}',  -- expected context variables when launched
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        version         INT NOT NULL DEFAULT 1,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_proc_def_org ON process_definitions(org_id, is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_proc_def_event ON process_definitions(trigger_event) WHERE trigger_event IS NOT NULL")

    # -----------------------------------------------------------------------
    # E13-S01 — Process Steps
    # Each step belongs to a process definition and has a type + config.
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS process_steps (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        process_id      UUID NOT NULL REFERENCES process_definitions(id) ON DELETE CASCADE,
        step_order      INT NOT NULL,           -- execution sequence (1, 2, 3 ...)
        name            TEXT NOT NULL,
        step_type       TEXT NOT NULL,          -- FORM | APPROVAL | CONDITION | NOTIFICATION | AI_EVALUATION | AUTO_ACTION
        config          JSONB NOT NULL DEFAULT '{}',
        -- config schema per step_type documented in models.py
        on_pass_step    INT,                    -- step_order to go to on success/true
        on_fail_step    INT,                    -- step_order to go to on failure/false (NULL = terminate)
        is_required     BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_proc_steps_process ON process_steps(process_id, step_order)")

    # -----------------------------------------------------------------------
    # E13-S03 — Process Instances
    # One row per launched process execution.
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS process_instances (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        process_id      UUID NOT NULL REFERENCES process_definitions(id),
        entity_type     TEXT,            -- the domain entity this process is about (e.g. "application")
        entity_id       TEXT,            -- entity UUID
        triggered_by    TEXT,            -- user_id or "system"
        trigger_event   TEXT,            -- domain event name that launched it (if event-triggered)
        context         JSONB NOT NULL DEFAULT '{}',  -- runtime variables accumulated across steps
        status          TEXT NOT NULL DEFAULT 'RUNNING',  -- RUNNING | COMPLETED | FAILED | CANCELLED
        current_step    INT NOT NULL DEFAULT 1,
        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ,
        error_message   TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_proc_inst_org ON process_instances(org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_proc_inst_entity ON process_instances(entity_type, entity_id)")

    # -----------------------------------------------------------------------
    # E13-S03 — Step Execution Log
    # One row per step execution within an instance.
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS process_step_logs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        instance_id     UUID NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
        step_id         UUID NOT NULL REFERENCES process_steps(id),
        step_order      INT NOT NULL,
        step_type       TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | RUNNING | PASSED | FAILED | SKIPPED
        input_data      JSONB DEFAULT '{}',
        output_data     JSONB DEFAULT '{}',
        error_message   TEXT,
        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_step_logs_instance ON process_step_logs(instance_id, step_order)")

    # -----------------------------------------------------------------------
    # E13-S04 — Form Submissions
    # Stores data submitted at FORM steps.
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS process_form_submissions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        instance_id     UUID NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
        step_id         UUID NOT NULL REFERENCES process_steps(id),
        submitted_by    TEXT NOT NULL,
        form_data       JSONB NOT NULL DEFAULT '{}',
        submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # -----------------------------------------------------------------------
    # RLS
    # -----------------------------------------------------------------------
    for table in [
        "process_definitions", "process_steps",
        "process_instances", "process_step_logs", "process_form_submissions",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in [
        "process_form_submissions", "process_step_logs",
        "process_instances", "process_steps", "process_definitions",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
