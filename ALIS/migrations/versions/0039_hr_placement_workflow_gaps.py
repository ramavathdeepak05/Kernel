"""Workflow compliance — HR-01, HR-03, SS-3, SS-02, SS-03 gaps

Revision ID: 0039
Revises: 0038
Create Date: 2026-03-26

Changes
───────
1. visiting_faculty_session_log (EC-HR-01)
   OTP-confirmed session log for visiting/contract faculty.
   Only payable=TRUE sessions are used in FM-5 payroll computation.
   Prevents over/under-payment when sessions are cancelled or added ad-hoc.

2. employee_department_assignments (EC-HR-03)
   Enables shared faculty who teach across departments.
   weight_pct per department must sum to 100 for each employee.
   Consumed by Regulatory E14 for faculty-to-student ratio per department.

3. placement_drives + placement_registrations (SS-3)
   Full placement drive management tables.
   Enforces one-offer policy via student_offer_locked flag.

4. placement_offer_locks (EC-SS-03)
   Verbal lock pattern: TPO-initiated lock with auto-expiry if
   formal offer PDF is not received by formal_offer_due_by date.

5. placement_offer_revocations (EC-SS-02)
   Tracks employer-side offer revocations with TPO verification.
   REVOKED_BY_EMPLOYER status excluded from NIRF placement % computation.
"""

from alembic import op


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. visiting_faculty_session_log (EC-HR-01)
    #    Visiting faculty confirm each delivered session via OTP.
    #    payable = faculty_confirmed AND status = 'DELIVERED' (computed column).
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS visiting_faculty_session_log (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        faculty_id          UUID NOT NULL REFERENCES staff_profiles(id),
        timetable_slot_id   UUID,                          -- NULL for unscheduled sessions
        session_date        DATE NOT NULL,
        start_time          TIME NOT NULL,
        end_time            TIME NOT NULL,
        session_type        VARCHAR(20) NOT NULL DEFAULT 'lecture'
            CHECK (session_type IN ('lecture', 'tutorial', 'lab', 'other')),
        status              VARCHAR(30) NOT NULL DEFAULT 'SCHEDULED'
            CHECK (status IN (
                'SCHEDULED',
                'DELIVERED',
                'CANCELLED',
                'UNSCHEDULED_ADDED'
            )),
        faculty_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
        faculty_otp_hash    VARCHAR(64),                   -- bcrypt hash of OTP used
        confirmed_at        TIMESTAMPTZ,
        hod_verified        BOOLEAN NOT NULL DEFAULT FALSE, -- required for UNSCHEDULED_ADDED
        hod_verified_at     TIMESTAMPTZ,
        hod_verified_by     UUID,
        rate_per_session    DECIMAL(10,2) NOT NULL DEFAULT 0,
        payroll_month       DATE,                          -- first day of payment month
        included_in_payroll BOOLEAN NOT NULL DEFAULT FALSE,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # Computed-column equivalent: payable index
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_vf_session_payable
        ON visiting_faculty_session_log(org_id, faculty_id, payroll_month)
        WHERE faculty_confirmed = TRUE AND status = 'DELIVERED'
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_vf_session_faculty
        ON visiting_faculty_session_log(faculty_id, session_date)
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_vf_session_pending_otp
        ON visiting_faculty_session_log(org_id, session_date)
        WHERE faculty_confirmed = FALSE AND status = 'SCHEDULED'
    """)

    # -------------------------------------------------------------------------
    # 2. employee_department_assignments (EC-HR-03)
    #    Shared faculty teaching across departments.
    #    weight_pct per employee must sum to 100 (enforced in service layer).
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS employee_department_assignments (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        staff_id        UUID NOT NULL REFERENCES staff_profiles(id),
        department_id   VARCHAR(100) NOT NULL,
        department_name VARCHAR(200) NOT NULL,
        weight_pct      DECIMAL(5,2) NOT NULL
            CHECK (weight_pct > 0 AND weight_pct <= 100),
        is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
        effective_from  DATE NOT NULL,
        effective_to    DATE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, staff_id, department_id)
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_emp_dept_staff
        ON employee_department_assignments(staff_id, is_primary)
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_emp_dept_org_dept
        ON employee_department_assignments(org_id, department_id)
    """)

    # -------------------------------------------------------------------------
    # 3a. placement_drives (SS-3)
    #     One row per campus placement drive / company visit.
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS placement_drives (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        company_name        VARCHAR(300) NOT NULL,
        company_website     TEXT,
        jd_title            VARCHAR(300) NOT NULL,
        jd_description      TEXT,
        jd_skills           TEXT[],
        ctc_min_lpa         DECIMAL(8,2),
        ctc_max_lpa         DECIMAL(8,2),
        drive_type          VARCHAR(30) NOT NULL DEFAULT 'CAMPUS'
            CHECK (drive_type IN ('CAMPUS', 'VIRTUAL', 'OFFCAMPUS', 'PPO', 'INTERNSHIP')),
        eligibility_min_cgpa DECIMAL(4,2),
        eligibility_max_backlogs INTEGER NOT NULL DEFAULT 0,
        eligible_programs   TEXT[],
        eligible_batches    INTEGER[],
        registration_open_at  TIMESTAMPTZ,
        registration_close_at TIMESTAMPTZ,
        drive_date          DATE,
        result_date         DATE,
        venue               VARCHAR(500),
        status              VARCHAR(30) NOT NULL DEFAULT 'DRAFT'
            CHECK (status IN (
                'DRAFT', 'OPEN', 'REGISTRATION_CLOSED',
                'IN_PROGRESS', 'COMPLETED', 'CANCELLED'
            )),
        apply_one_offer_policy BOOLEAN NOT NULL DEFAULT TRUE,
        created_by          UUID,
        approved_by         UUID,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_placement_drives_org_status
        ON placement_drives(org_id, status, drive_date DESC)
    """)

    # -------------------------------------------------------------------------
    # 3b. placement_registrations (SS-3)
    #     Student ↔ drive many-to-many with round-wise status tracking.
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS placement_registrations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        drive_id        UUID NOT NULL REFERENCES placement_drives(id),
        student_id      UUID NOT NULL REFERENCES students(id),
        registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        current_round   VARCHAR(50) NOT NULL DEFAULT 'REGISTERED',
        status          VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'
            CHECK (status IN (
                'ACTIVE',
                'SHORTLISTED',
                'SELECTED',
                'REJECTED',
                'WITHDRAWN',
                'BLOCKED_ONE_OFFER'
            )),
        offer_received  BOOLEAN NOT NULL DEFAULT FALSE,
        offer_accepted  BOOLEAN NOT NULL DEFAULT FALSE,
        ctc_lpa         DECIMAL(8,2),
        offer_letter_url TEXT,
        notes           TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(drive_id, student_id)
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_place_reg_drive
        ON placement_registrations(drive_id, status)
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_place_reg_student
        ON placement_registrations(student_id, status)
    """)

    # -------------------------------------------------------------------------
    # 3c. student_placement_status (SS-3)
    #     One row per student — tracks one-offer-policy lock.
    #     student_offer_locked = TRUE blocks further drive registrations.
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS student_placement_status (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id                UUID NOT NULL,
        student_id            UUID NOT NULL REFERENCES students(id),
        profile_active        BOOLEAN NOT NULL DEFAULT FALSE,
        student_offer_locked  BOOLEAN NOT NULL DEFAULT FALSE,
        locked_by_drive_id    UUID REFERENCES placement_drives(id),
        locked_at             TIMESTAMPTZ,
        lock_type             VARCHAR(20) DEFAULT 'FORMAL_OFFER'
            CHECK (lock_type IN ('FORMAL_OFFER', 'VERBAL_LOCK')),
        unlock_reason         TEXT,
        unlocked_at           TIMESTAMPTZ,
        unlocked_by           UUID,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, student_id)
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_student_place_status
        ON student_placement_status(org_id, student_offer_locked)
    """)

    # -------------------------------------------------------------------------
    # 4. placement_offer_locks (EC-SS-03)
    #    Verbal lock: TPO-initiated, auto-expiry if formal offer not received.
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS placement_offer_locks (
        id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id                    UUID NOT NULL,
        student_id                UUID NOT NULL REFERENCES students(id),
        drive_id                  UUID REFERENCES placement_drives(id),
        company_name              VARCHAR(300) NOT NULL,
        lock_type                 VARCHAR(20) NOT NULL DEFAULT 'VERBAL_LOCK'
            CHECK (lock_type IN ('FORMAL_OFFER', 'VERBAL_LOCK')),
        initiated_by              UUID NOT NULL,   -- TPO only
        company_contact_name      VARCHAR(200),
        company_contact_email     VARCHAR(254),
        formal_offer_due_by       DATE,            -- deadline for formal PDF
        formal_offer_received_at  TIMESTAMPTZ,
        auto_unlock_if_no_formal  BOOLEAN NOT NULL DEFAULT TRUE,
        status                    VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'
            CHECK (status IN ('ACTIVE', 'CONVERTED_TO_FORMAL', 'AUTO_EXPIRED', 'MANUALLY_UNLOCKED')),
        unlocked_at               TIMESTAMPTZ,
        created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_place_offer_lock_student
        ON placement_offer_locks(student_id, status)
    """)

    # -------------------------------------------------------------------------
    # 5. placement_offer_revocations (EC-SS-02)
    #    Employer-side revocation — must be TPO-verified.
    #    REVOKED_BY_EMPLOYER status excluded from NIRF placement %.
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS placement_offer_revocations (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        student_id          UUID NOT NULL REFERENCES students(id),
        drive_id            UUID REFERENCES placement_drives(id),
        company_name        VARCHAR(300) NOT NULL,
        revocation_reason   TEXT NOT NULL,
        revocation_date     DATE NOT NULL,
        evidence_url        TEXT,               -- email screenshot / formal letter URL
        reported_by         UUID NOT NULL,      -- who reported (student or TPO)
        tpo_verified        BOOLEAN NOT NULL DEFAULT FALSE,
        tpo_verified_by     UUID,
        tpo_verified_at     TIMESTAMPTZ,
        student_reactivated BOOLEAN NOT NULL DEFAULT FALSE,
        student_reactivated_at TIMESTAMPTZ,
        status              VARCHAR(30) NOT NULL DEFAULT 'PENDING_VERIFICATION'
            CHECK (status IN (
                'PENDING_VERIFICATION',
                'VERIFIED_REACTIVATED',
                'REJECTED_BY_TPO',
                'ESCALATED_TO_DEAN'
            )),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_place_revoc_student
        ON placement_offer_revocations(student_id, status)
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_place_revoc_pending
        ON placement_offer_revocations(org_id, tpo_verified, created_at)
        WHERE tpo_verified = FALSE
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS placement_offer_revocations")
    op.execute("DROP TABLE IF EXISTS placement_offer_locks")
    op.execute("DROP TABLE IF EXISTS student_placement_status")
    op.execute("DROP TABLE IF EXISTS placement_registrations")
    op.execute("DROP TABLE IF EXISTS placement_drives")
    op.execute("DROP TABLE IF EXISTS employee_department_assignments")
    op.execute("DROP TABLE IF EXISTS visiting_faculty_session_log")
