"""HR & Staff module (M5)

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-05
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E08-S01 — Staff Profiles
    # Extends the users table; one row per staff member
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS staff_profiles (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        user_id             UUID NOT NULL REFERENCES users(id),
        employee_code       TEXT NOT NULL,
        department          TEXT NOT NULL,
        designation         TEXT NOT NULL,
        employment_type     TEXT NOT NULL DEFAULT 'FULL_TIME',  -- FULL_TIME | PART_TIME | CONTRACT | VISITING
        date_of_joining     DATE NOT NULL,
        date_of_leaving     DATE,
        salary_grade        TEXT,
        reporting_to        UUID REFERENCES users(id),
        specializations     TEXT[],
        qualifications      JSONB,   -- [{degree, institution, year}]
        experience_years    INT,
        is_active           BOOLEAN NOT NULL DEFAULT TRUE,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, user_id),
        UNIQUE(org_id, employee_code)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_org ON staff_profiles(org_id, department)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_user ON staff_profiles(user_id)")

    # -------------------------------------------------------------------------
    # E08-S03 — Leave Types (configured per org)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS leave_types (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        code            TEXT NOT NULL,
        annual_quota    DECIMAL(5,1) NOT NULL DEFAULT 0,
        carry_forward   BOOLEAN NOT NULL DEFAULT FALSE,
        max_carry_forward DECIMAL(5,1) DEFAULT 0,
        is_paid         BOOLEAN NOT NULL DEFAULT TRUE,
        applicable_to   TEXT NOT NULL DEFAULT 'ALL',  -- ALL | FACULTY | ADMIN | CONTRACT
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, code)
    )""")

    # -------------------------------------------------------------------------
    # E08-S03 — Leave Requests
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS leave_requests (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        leave_type_id   UUID NOT NULL REFERENCES leave_types(id),
        from_date       DATE NOT NULL,
        to_date         DATE NOT NULL,
        days            DECIMAL(5,1) NOT NULL,
        reason          TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | APPROVED | REJECTED | CANCELLED
        applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        approved_by     UUID REFERENCES users(id),
        approved_at     TIMESTAMPTZ,
        rejection_note  TEXT,
        attachment_path TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_leave_staff ON leave_requests(staff_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leave_dates ON leave_requests(org_id, from_date, to_date)")

    # -------------------------------------------------------------------------
    # E08-S04 — Payroll
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_components (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        code            TEXT NOT NULL,
        component_type  TEXT NOT NULL DEFAULT 'EARNING',  -- EARNING | DEDUCTION | STATUTORY
        calc_type       TEXT NOT NULL DEFAULT 'FIXED',    -- FIXED | PERCENTAGE_OF_BASIC | PERCENTAGE_OF_GROSS
        value           DECIMAL(12,2) NOT NULL DEFAULT 0,
        is_taxable      BOOLEAN NOT NULL DEFAULT TRUE,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, code)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS staff_salary_structures (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        basic_salary    DECIMAL(12,2) NOT NULL,
        components      JSONB NOT NULL DEFAULT '[]',  -- [{component_id, override_value}]
        effective_from  DATE NOT NULL,
        effective_to    DATE,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, staff_id, effective_from)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payslips (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        month           INT NOT NULL,         -- 1-12
        year            INT NOT NULL,
        working_days    INT NOT NULL DEFAULT 0,
        present_days    INT NOT NULL DEFAULT 0,
        leave_days      DECIMAL(5,1) NOT NULL DEFAULT 0,
        lop_days        DECIMAL(5,1) NOT NULL DEFAULT 0,  -- Loss of Pay
        gross_salary    DECIMAL(12,2) NOT NULL DEFAULT 0,
        total_deductions DECIMAL(12,2) NOT NULL DEFAULT 0,
        net_salary      DECIMAL(12,2) NOT NULL DEFAULT 0,
        earnings_detail JSONB NOT NULL DEFAULT '{}',
        deductions_detail JSONB NOT NULL DEFAULT '{}',
        pdf_path        TEXT,
        status          TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT | PROCESSED | PAID | CANCELLED
        processed_by    TEXT,
        processed_at    TIMESTAMPTZ,
        paid_at         TIMESTAMPTZ,
        UNIQUE(org_id, staff_id, month, year)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_payslip_staff ON payslips(staff_id, year, month)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payslip_org ON payslips(org_id, year, month)")

    # -------------------------------------------------------------------------
    # E08-S05 — Performance Reviews
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS performance_reviews (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        reviewer_id     UUID NOT NULL REFERENCES users(id),
        review_period   TEXT NOT NULL,    -- e.g. "2025-26-H1", "2025-26-ANNUAL"
        review_type     TEXT NOT NULL DEFAULT 'ANNUAL',  -- ANNUAL | HALF_YEARLY | PROBATION
        ratings         JSONB NOT NULL DEFAULT '{}',  -- {teaching_quality: 4, research: 3, ...}
        overall_rating  DECIMAL(3,1),
        strengths       TEXT,
        improvements    TEXT,
        goals_next      TEXT,
        status          TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT | SUBMITTED | ACKNOWLEDGED | FINALIZED
        submitted_at    TIMESTAMPTZ,
        acknowledged_at TIMESTAMPTZ,
        staff_comments  TEXT,
        UNIQUE(org_id, staff_id, review_period)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_review_staff ON performance_reviews(staff_id, review_period)")

    # -------------------------------------------------------------------------
    # E08-S06 — Staff Attendance
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS staff_attendance (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        date            DATE NOT NULL,
        check_in        TIMESTAMPTZ,
        check_out       TIMESTAMPTZ,
        status          TEXT NOT NULL DEFAULT 'PRESENT',  -- PRESENT | ABSENT | HALF_DAY | LEAVE | HOLIDAY | WFH
        source          TEXT NOT NULL DEFAULT 'MANUAL',   -- MANUAL | BIOMETRIC | SYSTEM
        remarks         TEXT,
        marked_by       TEXT,
        UNIQUE(org_id, staff_id, date)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_attendance_date ON staff_attendance(org_id, date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_attendance_staff ON staff_attendance(staff_id, date)")

    # -------------------------------------------------------------------------
    # RLS
    # -------------------------------------------------------------------------
    for table in ["staff_profiles", "leave_types", "leave_requests",
                  "payroll_components", "staff_salary_structures", "payslips",
                  "performance_reviews", "staff_attendance"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in ["staff_attendance", "performance_reviews", "payslips",
              "staff_salary_structures", "payroll_components",
              "leave_requests", "leave_types", "staff_profiles"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
