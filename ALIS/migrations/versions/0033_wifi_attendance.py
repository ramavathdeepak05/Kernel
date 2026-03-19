"""0033 — WiFi proximity attendance sessions

Revision ID: 0033
Revises: 0032
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE attendance_wifi_sessions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL,
            course_id           UUID NOT NULL REFERENCES courses(id),
            faculty_id          UUID NOT NULL,
            session_token       VARCHAR(64) UNIQUE NOT NULL,
            ssid                VARCHAR(32) NOT NULL,
            wifi_password       VARCHAR(16) NOT NULL,
            faculty_public_ip   INET NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            duration_minutes    INTEGER NOT NULL DEFAULT 15,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at            TIMESTAMPTZ,
            student_count       INTEGER NOT NULL DEFAULT 0,
            present_count       INTEGER NOT NULL DEFAULT 0,
            absent_count        INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX idx_wifi_sessions_tenant ON attendance_wifi_sessions(tenant_id);
        CREATE INDEX idx_wifi_sessions_course ON attendance_wifi_sessions(course_id);
        CREATE INDEX idx_wifi_sessions_token  ON attendance_wifi_sessions(session_token);
    """)

    op.execute("""
        CREATE TABLE attendance_wifi_verifications (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id          UUID NOT NULL REFERENCES attendance_wifi_sessions(id),
            student_id          UUID NOT NULL,
            tenant_id           UUID NOT NULL,
            student_public_ip   INET,
            ip_matched          BOOLEAN,
            status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            verified_at         TIMESTAMPTZ,
            attendance_record_id UUID,
            UNIQUE(session_id, student_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_wifi_verif_session   ON attendance_wifi_verifications(session_id);
        CREATE INDEX idx_wifi_verif_student   ON attendance_wifi_verifications(student_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attendance_wifi_verifications CASCADE")
    op.execute("DROP TABLE IF EXISTS attendance_wifi_sessions CASCADE")
