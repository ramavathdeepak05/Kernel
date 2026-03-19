"""0034 — Course and session TA assignments

Revision ID: 0034
Revises: 0033
Create Date: 2026-03-19
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Course-level TA assignments (semester-long, revocable anytime)
    op.execute("""
        CREATE TABLE course_ta_assignments (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            course_id       UUID NOT NULL REFERENCES courses(id),
            faculty_id      UUID NOT NULL,
            student_id      UUID NOT NULL,
            assigned_by     UUID NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            notes           TEXT,
            assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at      TIMESTAMPTZ,
            revoked_by      UUID,
            UNIQUE (course_id, student_id, status)
        )
    """)
    op.execute("CREATE INDEX idx_course_ta_course   ON course_ta_assignments(course_id, status)")
    op.execute("CREATE INDEX idx_course_ta_student  ON course_ta_assignments(student_id, status)")
    op.execute("CREATE INDEX idx_course_ta_faculty  ON course_ta_assignments(faculty_id)")

    # Session-level TA assignments (one specific attendance session only)
    op.execute("""
        CREATE TABLE session_ta_assignments (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            course_id       UUID NOT NULL,
            session_ref     UUID NOT NULL,
            session_type    VARCHAR(20) NOT NULL DEFAULT 'WIFI',
            faculty_id      UUID NOT NULL,
            student_id      UUID NOT NULL,
            assigned_by     UUID NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at      TIMESTAMPTZ,
            revoked_by      UUID,
            UNIQUE (session_ref, student_id)
        )
    """)
    op.execute("CREATE INDEX idx_session_ta_session  ON session_ta_assignments(session_ref, status)")
    op.execute("CREATE INDEX idx_session_ta_student  ON session_ta_assignments(student_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_ta_assignments CASCADE")
    op.execute("DROP TABLE IF EXISTS course_ta_assignments CASCADE")
