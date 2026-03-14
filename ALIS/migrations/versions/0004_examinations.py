"""Examinations & Grades module

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-05
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E06-S01 — Exam Schedules
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS exam_schedules (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        course_id       UUID NOT NULL REFERENCES courses(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        exam_type       TEXT NOT NULL DEFAULT 'SEMESTER_END',  -- SEMESTER_END | MID_TERM | INTERNAL
        exam_date       DATE NOT NULL,
        start_time      TIME NOT NULL,
        end_time        TIME NOT NULL,
        venue           TEXT,
        max_marks       INT NOT NULL DEFAULT 100,
        pass_marks      INT NOT NULL DEFAULT 40,
        status          TEXT NOT NULL DEFAULT 'SCHEDULED',  -- SCHEDULED | ONGOING | COMPLETED | CANCELLED
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(course_id, academic_year, exam_type)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_exam_schedule_org ON exam_schedules(org_id, academic_year)")

    # -------------------------------------------------------------------------
    # E06-S02 — Hall Tickets
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS hall_tickets (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        exam_type       TEXT NOT NULL DEFAULT 'SEMESTER_END',
        ticket_number   TEXT NOT NULL UNIQUE,
        pdf_path        TEXT,
        is_valid        BOOLEAN NOT NULL DEFAULT TRUE,
        issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        issued_by       TEXT NOT NULL
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_hall_tickets_student ON hall_tickets(student_id, academic_year)")

    # -------------------------------------------------------------------------
    # E06-S03 — Grades
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS grades (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        course_id       UUID NOT NULL REFERENCES courses(id),
        exam_schedule_id UUID REFERENCES exam_schedules(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        marks_obtained  DECIMAL(6,2),
        max_marks       INT NOT NULL DEFAULT 100,
        grade           TEXT,            -- A+, A, B+, B, C, D, F (configurable)
        grade_points    DECIMAL(4,2),    -- 4.0 or 10.0 scale (configurable)
        is_absent       BOOLEAN NOT NULL DEFAULT FALSE,
        is_pass         BOOLEAN,
        entered_by      TEXT NOT NULL,
        entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_published    BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE(student_id, course_id, academic_year, semester)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_grades_course ON grades(course_id, academic_year)")

    # -------------------------------------------------------------------------
    # E06-S04 — Semester Results (computed GPA/CGPA per student)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS semester_results (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        academic_year   TEXT NOT NULL,
        semester        INT NOT NULL,
        sgpa            DECIMAL(4,2),     -- Semester GPA
        cgpa            DECIMAL(4,2),     -- Cumulative GPA (all semesters to date)
        total_credits   INT,
        credits_earned  INT,
        status          TEXT NOT NULL DEFAULT 'PASS',  -- PASS | FAIL | WITHHELD
        declared_at     TIMESTAMPTZ,
        is_published    BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE(student_id, academic_year, semester)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_results_student ON semester_results(student_id)")

    # -------------------------------------------------------------------------
    # E06-S06 — Transcripts
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS transcripts (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        pdf_path        TEXT NOT NULL,
        content_hash    TEXT NOT NULL,
        generated_by    TEXT NOT NULL,
        is_official     BOOLEAN NOT NULL DEFAULT FALSE
    )""")

    # -------------------------------------------------------------------------
    # E06-S07 — Re-evaluation Requests
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS reeval_requests (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        grade_id        UUID NOT NULL REFERENCES grades(id),
        reason          TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | UNDER_REVIEW | REVISED | REJECTED
        original_marks  DECIMAL(6,2),
        revised_marks   DECIMAL(6,2),
        reviewed_by     TEXT,
        reviewed_at     TIMESTAMPTZ,
        review_note     TEXT,
        fee_paid        BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # -------------------------------------------------------------------------
    # RLS
    # -------------------------------------------------------------------------
    for table in ["exam_schedules", "hall_tickets", "grades",
                  "semester_results", "transcripts", "reeval_requests"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in ["reeval_requests", "transcripts", "semester_results",
              "grades", "hall_tickets", "exam_schedules"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
