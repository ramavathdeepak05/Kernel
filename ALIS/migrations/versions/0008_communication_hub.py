"""Communication Hub — notification_templates, notification_logs, in_app_notifications,
announcements, announcement_reads

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-06
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # E10-S01 — DB-backed notification templates
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS notification_templates (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        key             TEXT NOT NULL,           -- slug: "results_declared", "welcome", etc.
        name            TEXT NOT NULL,
        subject         TEXT,                    -- NULL for SMS/in-app
        body            TEXT NOT NULL,
        channel         TEXT NOT NULL DEFAULT 'EMAIL',  -- EMAIL | SMS | IN_APP | ALL
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, key, channel)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_notif_templates_org ON notification_templates(org_id, key)")

    # -----------------------------------------------------------------------
    # E10-S02/S03 — DB-backed notification delivery log
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS notification_logs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT,
        recipient_id    TEXT NOT NULL,
        recipient_addr  TEXT NOT NULL,           -- email or phone
        template_key    TEXT NOT NULL,
        channel         TEXT NOT NULL,           -- EMAIL | SMS | IN_APP
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | SENT | FAILED
        error_message   TEXT,
        sent_at         TIMESTAMPTZ,
        retry_count     INT NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_notif_logs_recipient ON notification_logs(recipient_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notif_logs_status ON notification_logs(status) WHERE status != 'SENT'")

    # -----------------------------------------------------------------------
    # E10-S04 — In-App Notifications
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS in_app_notifications (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        recipient_id    TEXT NOT NULL,           -- user_id
        title           TEXT NOT NULL,
        body            TEXT NOT NULL,
        link            TEXT,                    -- optional deep link
        is_read         BOOLEAN NOT NULL DEFAULT FALSE,
        read_at         TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_in_app_recipient ON in_app_notifications(recipient_id, is_read, created_at DESC)")

    # -----------------------------------------------------------------------
    # E10-S05 — Announcements
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        title           TEXT NOT NULL,
        body            TEXT NOT NULL,
        target_audience TEXT NOT NULL DEFAULT 'ALL',  -- ALL | STUDENTS | STAFF | FACULTY | PARENTS
        priority        TEXT NOT NULL DEFAULT 'NORMAL',  -- LOW | NORMAL | HIGH | URGENT
        published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at      TIMESTAMPTZ,
        created_by      TEXT NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_announcements_org ON announcements(org_id, published_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS announcement_reads (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        announcement_id UUID NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
        user_id         TEXT NOT NULL,
        read_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(announcement_id, user_id)
    )""")

    # -----------------------------------------------------------------------
    # E10-S07 — Bulk message jobs
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS bulk_message_jobs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        title           TEXT NOT NULL,
        message         TEXT NOT NULL,
        channel         TEXT NOT NULL DEFAULT 'EMAIL',
        target_filter   JSONB NOT NULL DEFAULT '{}',  -- {role, program_id, academic_year, ...}
        recipient_count INT,
        sent_count      INT NOT NULL DEFAULT 0,
        failed_count    INT NOT NULL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'QUEUED',  -- QUEUED | RUNNING | DONE | FAILED
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ
    )""")

    # -----------------------------------------------------------------------
    # RLS
    # -----------------------------------------------------------------------
    for table in [
        "notification_templates", "notification_logs", "in_app_notifications",
        "announcements", "bulk_message_jobs",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in [
        "bulk_message_jobs", "announcement_reads", "announcements",
        "in_app_notifications", "notification_logs", "notification_templates",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
