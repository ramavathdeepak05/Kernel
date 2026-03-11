"""Alumni & Placement module

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-06
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # E12-S01 — Alumni Profiles
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS alumni_profiles (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID REFERENCES students(id),        -- linked to original student record
        name            TEXT NOT NULL,
        email           TEXT NOT NULL,
        phone           TEXT,
        program         TEXT NOT NULL,
        graduation_year INT NOT NULL,
        roll_number     TEXT,
        cgpa            DECIMAL(4,2),
        current_employer TEXT,
        current_designation TEXT,
        current_location TEXT,
        linkedin_url    TEXT,
        bio             TEXT,
        is_verified     BOOLEAN NOT NULL DEFAULT FALSE,      -- verified by institution
        is_mentor       BOOLEAN NOT NULL DEFAULT FALSE,      -- available for mentoring
        status          TEXT NOT NULL DEFAULT 'ACTIVE',      -- ACTIVE | INACTIVE
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, email)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_org ON alumni_profiles(org_id, graduation_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_program ON alumni_profiles(org_id, program)")

    # -----------------------------------------------------------------------
    # E12-S02 — Placement Records
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS placement_records (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        academic_year   TEXT NOT NULL,
        company_name    TEXT NOT NULL,
        role            TEXT NOT NULL,
        package_lpa     DECIMAL(8,2),        -- annual package in LPA (lakhs per annum)
        placement_type  TEXT NOT NULL DEFAULT 'CAMPUS',  -- CAMPUS | OFF_CAMPUS | INTERNSHIP
        offer_date      DATE,
        joining_date    DATE,
        location        TEXT,
        is_ppo          BOOLEAN NOT NULL DEFAULT FALSE,   -- Pre-Placement Offer
        recorded_by     TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_placement_org ON placement_records(org_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_placement_student ON placement_records(student_id)")

    # -----------------------------------------------------------------------
    # E12-S03 — Job Board
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS job_postings (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        title           TEXT NOT NULL,
        company_name    TEXT NOT NULL,
        description     TEXT NOT NULL,
        location        TEXT,
        job_type        TEXT NOT NULL DEFAULT 'FULL_TIME',  -- FULL_TIME | PART_TIME | INTERNSHIP | CONTRACT
        experience_min  INT DEFAULT 0,                       -- years
        experience_max  INT,
        salary_range    TEXT,
        skills_required JSONB NOT NULL DEFAULT '[]',
        apply_url       TEXT,
        apply_email     TEXT,
        posted_by       TEXT NOT NULL,                       -- alumni_id or staff user_id
        source          TEXT NOT NULL DEFAULT 'ALUMNI',     -- ALUMNI | COMPANY | STAFF
        status          TEXT NOT NULL DEFAULT 'ACTIVE',     -- ACTIVE | CLOSED | EXPIRED
        expires_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_org ON job_postings(org_id, status, created_at DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS job_applications (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        job_id          UUID NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
        applicant_id    TEXT NOT NULL,       -- student_id or alumni_id
        applicant_type  TEXT NOT NULL DEFAULT 'STUDENT',  -- STUDENT | ALUMNI
        resume_path     TEXT,
        cover_note      TEXT,
        status          TEXT NOT NULL DEFAULT 'APPLIED',  -- APPLIED | SHORTLISTED | REJECTED | HIRED
        applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(job_id, applicant_id)
    )""")

    # -----------------------------------------------------------------------
    # E12-S04 — Recruitment Drives
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS recruitment_drives (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        company_name    TEXT NOT NULL,
        drive_date      DATE NOT NULL,
        venue           TEXT,
        roles_offered   JSONB NOT NULL DEFAULT '[]',      -- [{title, package_lpa, count}]
        eligibility     JSONB NOT NULL DEFAULT '{}',      -- {min_cgpa, programs, graduation_years}
        description     TEXT,
        status          TEXT NOT NULL DEFAULT 'SCHEDULED', -- SCHEDULED | ONGOING | COMPLETED | CANCELLED
        registered_count INT NOT NULL DEFAULT 0,
        selected_count   INT NOT NULL DEFAULT 0,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_drives_org ON recruitment_drives(org_id, drive_date DESC)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS drive_registrations (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        drive_id        UUID NOT NULL REFERENCES recruitment_drives(id) ON DELETE CASCADE,
        student_id      UUID NOT NULL REFERENCES students(id),
        status          TEXT NOT NULL DEFAULT 'REGISTERED',  -- REGISTERED | APPEARED | SELECTED | REJECTED
        registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(drive_id, student_id)
    )""")

    # -----------------------------------------------------------------------
    # E12-S05 — Alumni Network (connections + mentorship)
    # -----------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS alumni_connections (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        requester_id    UUID NOT NULL REFERENCES alumni_profiles(id),
        target_id       UUID NOT NULL REFERENCES alumni_profiles(id),
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | ACCEPTED | REJECTED
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(requester_id, target_id)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS mentorship_requests (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        mentor_id       UUID NOT NULL REFERENCES alumni_profiles(id),
        mentee_id       TEXT NOT NULL,       -- student_id
        topic           TEXT NOT NULL,
        message         TEXT,
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | ACCEPTED | COMPLETED | DECLINED
        session_date    DATE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # -----------------------------------------------------------------------
    # RLS
    # -----------------------------------------------------------------------
    for table in [
        "alumni_profiles", "placement_records", "job_postings", "job_applications",
        "recruitment_drives", "drive_registrations",
        "alumni_connections", "mentorship_requests",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in [
        "mentorship_requests", "alumni_connections",
        "drive_registrations", "recruitment_drives",
        "job_applications", "job_postings",
        "placement_records", "alumni_profiles",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
