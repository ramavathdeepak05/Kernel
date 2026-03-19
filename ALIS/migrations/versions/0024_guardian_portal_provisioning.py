"""Guardian portal provisioning — parent accounts linked to students

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-16

Changes
───────
1. guardian_student_links — FK table binding a guardian (parent) user to
   a student user within the same org.  A guardian can be linked to multiple
   students; a student can have multiple guardians.

2. guardian_portal_settings — per-guardian opt-in flags:
   - receive_attendance_alerts  (default TRUE)
   - receive_fee_reminders      (default TRUE)
   - receive_result_notifications (default TRUE)
   - preferred_language         (inherits student language, overridable)

These tables are prerequisites for the WhatsApp language-variant work (0023),
which adds preferred_language to users and links guardian messaging to students.
"""

from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS guardian_student_links (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          UUID NOT NULL,
            guardian_id     UUID NOT NULL,
            student_id      UUID NOT NULL,
            relationship    VARCHAR(50) NOT NULL DEFAULT 'PARENT',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_guardian_student UNIQUE (org_id, guardian_id, student_id)
        );
        CREATE INDEX IF NOT EXISTS idx_gsl_guardian ON guardian_student_links(org_id, guardian_id);
        CREATE INDEX IF NOT EXISTS idx_gsl_student  ON guardian_student_links(org_id, student_id);

        CREATE TABLE IF NOT EXISTS guardian_portal_settings (
            id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id                          UUID NOT NULL,
            guardian_id                     UUID NOT NULL,
            receive_attendance_alerts       BOOLEAN NOT NULL DEFAULT TRUE,
            receive_fee_reminders           BOOLEAN NOT NULL DEFAULT TRUE,
            receive_result_notifications    BOOLEAN NOT NULL DEFAULT TRUE,
            preferred_language              VARCHAR(5) NOT NULL DEFAULT 'en',
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_guardian_portal_settings UNIQUE (org_id, guardian_id)
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS guardian_portal_settings;
        DROP TABLE IF EXISTS guardian_student_links;
    """)
