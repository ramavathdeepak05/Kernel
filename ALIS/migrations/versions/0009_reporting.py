"""Reporting & Analytics — saved_reports, report_schedules, kpi_snapshots

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-06
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # E11-S05 — Saved / Custom Reports
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS saved_reports (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        description     TEXT,
        module          TEXT NOT NULL,   -- admissions | academics | examinations | finance | hr | services
        filters         JSONB NOT NULL DEFAULT '{}',
        columns         JSONB NOT NULL DEFAULT '[]',
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_run_at     TIMESTAMPTZ
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_saved_reports_org ON saved_reports(org_id, module)")

    # -----------------------------------------------------------------------
    # E11-S06 — Export Jobs
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS export_jobs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        report_type     TEXT NOT NULL,
        format          TEXT NOT NULL DEFAULT 'CSV',  -- CSV | XLSX | PDF
        filters         JSONB NOT NULL DEFAULT '{}',
        status          TEXT NOT NULL DEFAULT 'QUEUED',  -- QUEUED | RUNNING | DONE | FAILED
        file_path       TEXT,
        error_message   TEXT,
        requested_by    TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_export_jobs_org ON export_jobs(org_id, created_at DESC)")

    # -----------------------------------------------------------------------
    # E11-S01 — KPI Snapshots (hourly/daily cache of expensive aggregates)
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS kpi_snapshots (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
        kpi_key         TEXT NOT NULL,
        value           JSONB NOT NULL,
        computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, snapshot_date, kpi_key)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_org ON kpi_snapshots(org_id, snapshot_date DESC)")

    # -----------------------------------------------------------------------
    # RLS
    # -----------------------------------------------------------------------
    for table in ["saved_reports", "export_jobs", "kpi_snapshots"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in ["kpi_snapshots", "export_jobs", "saved_reports"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
