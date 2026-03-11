"""Academics module — programs, courses, enrollment, attendance

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-05
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E05-S01 — Programs
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS programs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        code            TEXT NOT NULL,
        degree_type     TEXT NOT NULL,           -- UG | PG | DIPLOMA | CERTIFICATE
        duration_years  DECIMAL(3,1) NOT NULL,
        total_credits   INT,
        status          TEXT NOT NULL DEFAULT 'ACTIVE',
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ,
        UNIQUE(org_id, code)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_programs_org ON programs(org_id, status)")

    # -------------------------------------------------------------------------
    # E05-S02 — Courses
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        program_id      UUID NOT NULL REFERENCES programs(id),
        name            TEXT NOT NULL,
        code            TEXT NOT NULL,
        semester        INT NOT NULL,            -- 1..8
        credits         INT NOT NULL DEFAULT 3,
        course_type     TEXT NOT NULL DEFAULT 'THEORY',  -- THEORY | LAB | PROJECT | ELECTIVE
        status          TEXT NOT NULL DEFAULT 'ACTIVE',
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, code)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_courses_program ON courses(program_id, semester)")

    # -------------------------------------------------------------------------
    # E05-S03 — Student-Course Enrollments
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS course_enrollments (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        course_id       UUID NOT NULL REFERENCES courses(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'ENROLLED',  -- ENROLLED | DROPPED | COMPLETED
        enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(student_id, course_id, academic_year)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_student ON course_enrollments(student_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_course ON course_enrollments(course_id, academic_year)")

    # -------------------------------------------------------------------------
    # E05-S04 — Faculty Assignments
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS faculty_assignments (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        faculty_id      UUID NOT NULL,           -- references users(id) with role=FACULTY
        course_id       UUID NOT NULL REFERENCES courses(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        assigned_by     TEXT NOT NULL,
        assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(faculty_id, course_id, academic_year)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_faculty_assign_course ON faculty_assignments(course_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_faculty_assign_faculty ON faculty_assignments(faculty_id, academic_year)")

    # -------------------------------------------------------------------------
    # E05-S05 — Timetable
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS timetable_slots (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        course_id       UUID NOT NULL REFERENCES courses(id),
        faculty_id      UUID,
        academic_year   TEXT NOT NULL,
        day_of_week     INT NOT NULL,            -- 1=Mon .. 7=Sun
        start_time      TIME NOT NULL,
        end_time        TIME NOT NULL,
        room            TEXT,
        slot_type       TEXT NOT NULL DEFAULT 'LECTURE',  -- LECTURE | LAB | TUTORIAL
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_timetable_course ON timetable_slots(course_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_timetable_faculty ON timetable_slots(faculty_id, academic_year)")

    # -------------------------------------------------------------------------
    # E05-S06 — Attendance Records
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS attendance_sessions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        course_id       UUID NOT NULL REFERENCES courses(id),
        faculty_id      UUID NOT NULL,
        academic_year   TEXT NOT NULL,
        session_date    DATE NOT NULL,
        slot_type       TEXT NOT NULL DEFAULT 'LECTURE',
        is_finalized    BOOLEAN NOT NULL DEFAULT FALSE,
        finalized_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(course_id, session_date, slot_type)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS attendance_records (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        session_id      UUID NOT NULL REFERENCES attendance_sessions(id),
        student_id      UUID NOT NULL REFERENCES students(id),
        status          TEXT NOT NULL DEFAULT 'ABSENT',  -- PRESENT | ABSENT | LATE | EXCUSED
        marked_by       TEXT NOT NULL,
        marked_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(session_id, student_id)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance_records(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance_records(student_id)")

    # -------------------------------------------------------------------------
    # RLS on all academics tables
    # -------------------------------------------------------------------------
    for table in ["programs", "courses", "course_enrollments", "faculty_assignments",
                  "timetable_slots", "attendance_sessions", "attendance_records"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in ["attendance_records", "attendance_sessions", "timetable_slots",
              "faculty_assignments", "course_enrollments", "courses", "programs"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
