"""0038 — failed_task_log table

Revision ID: 0038
Revises: 0037
Create Date: 2026-03-26

Dead-letter storage for Celery tasks that exhaust all retries.
Written by the @task_failure.connect signal handler in server/worker.py.
Surfaced via GET /api/v1/admin/failed-tasks for ops team inspection.

No RLS — ops-only table, SUPER_ADMIN access only via admin_router.
"""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS failed_task_log (
            id          BIGSERIAL    PRIMARY KEY,
            task_id     TEXT         NOT NULL,
            task_name   TEXT         NOT NULL,
            args        JSONB        NOT NULL DEFAULT '[]',
            kwargs      JSONB        NOT NULL DEFAULT '{}',
            error       TEXT,
            traceback   TEXT,
            failed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            tenant_id   TEXT,
            retried     BOOLEAN      NOT NULL DEFAULT FALSE,
            retried_at  TIMESTAMPTZ
        )
    """)

    # ------------------------------------------------------------------
    # 2. Indexes
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_failed_task_log_failed_at
            ON failed_task_log (failed_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_failed_task_log_task_name
            ON failed_task_log (task_name)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_failed_task_log_tenant_id
            ON failed_task_log (tenant_id)
            WHERE tenant_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_failed_task_log_retried
            ON failed_task_log (retried)
            WHERE retried = FALSE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_failed_task_log_retried")
    op.execute("DROP INDEX IF EXISTS idx_failed_task_log_tenant_id")
    op.execute("DROP INDEX IF EXISTS idx_failed_task_log_task_name")
    op.execute("DROP INDEX IF EXISTS idx_failed_task_log_failed_at")
    op.execute("DROP TABLE IF EXISTS failed_task_log")
