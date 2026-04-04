"""
0044 — Student Services + Regulatory compliance tables

Tables:
- student_clubs, club_members, club_events, event_participants (SS-6)
- external_competition_nocs (SS-6 NOC)
- guardian_accounts, guardian_student_links (E16)
- library_memberships (SS-2 auto-provision)
- graduation_saga_signals, graduation_saga_completions (SS-8 saga)
- graduation_employment_declarations (NIRF GO)
- iqac_meetings, iqac_action_items, iqac_best_practices (RA-8)

Revision ID: 0044
Revises: 0043
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""

    -- ===========================================================
    -- SS-6: Student Clubs & Events
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS student_clubs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        name            VARCHAR(256) NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        category        VARCHAR(64) NOT NULL DEFAULT 'GENERAL',
        proposed_by     VARCHAR(64) NOT NULL,
        faculty_advisor_id UUID,
        approved_by     VARCHAR(64),
        approved_at     TIMESTAMPTZ,
        status          VARCHAR(32) NOT NULL DEFAULT 'PROPOSED',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_clubs_org ON student_clubs(org_id, status);

    CREATE TABLE IF NOT EXISTS club_members (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        club_id         UUID NOT NULL REFERENCES student_clubs(id),
        student_id      UUID NOT NULL,
        role            VARCHAR(32) NOT NULL DEFAULT 'MEMBER',
        joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, club_id, student_id)
    );

    CREATE TABLE IF NOT EXISTS club_events (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        club_id         UUID REFERENCES student_clubs(id),
        title           VARCHAR(256) NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        event_date      DATE,
        venue_requested VARCHAR(256) NOT NULL DEFAULT '',
        venue_allotted  VARCHAR(256),
        expected_participants INT NOT NULL DEFAULT 0,
        actual_participants INT,
        budget_requested DECIMAL(12,2) NOT NULL DEFAULT 0,
        budget_sanctioned DECIMAL(12,2),
        status          VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        proposed_by     VARCHAR(64),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_events_org ON club_events(org_id, status);

    CREATE TABLE IF NOT EXISTS event_participants (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        event_id        UUID NOT NULL REFERENCES club_events(id),
        student_id      UUID NOT NULL,
        certificate_issued BOOLEAN NOT NULL DEFAULT FALSE,
        attended_at     TIMESTAMPTZ,
        UNIQUE(org_id, event_id, student_id)
    );

    CREATE TABLE IF NOT EXISTS external_competition_nocs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        competition_name VARCHAR(256) NOT NULL,
        dates           VARCHAR(64) NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'ISSUED',
        issued_by       VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- E16: Guardian Portal
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS guardian_accounts (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        phone           VARCHAR(20) NOT NULL,
        name            VARCHAR(256) NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_guardian_phone ON guardian_accounts(org_id, phone);

    CREATE TABLE IF NOT EXISTS guardian_student_links (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        guardian_id     UUID NOT NULL REFERENCES guardian_accounts(id),
        student_id      UUID NOT NULL,
        relationship    VARCHAR(32) NOT NULL DEFAULT 'PARENT',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, guardian_id, student_id)
    );

    -- ===========================================================
    -- SS-2: Library auto-membership
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS library_memberships (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        status          VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, student_id)
    );

    -- ===========================================================
    -- SS-8: Alumni Transition Saga
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS graduation_saga_signals (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        signal_type     VARCHAR(64) NOT NULL,
        received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, student_id, signal_type)
    );

    CREATE TABLE IF NOT EXISTS graduation_saga_completions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL UNIQUE,
        alumni_id       UUID NOT NULL,
        completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS graduation_employment_declarations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        category        VARCHAR(64) NOT NULL,
        employer_name   VARCHAR(256) NOT NULL DEFAULT '',
        employer_cin    VARCHAR(32) NOT NULL DEFAULT '',
        institution     VARCHAR(256) NOT NULL DEFAULT '',
        program         VARCHAR(256) NOT NULL DEFAULT '',
        startup_name    VARCHAR(256) NOT NULL DEFAULT '',
        gstin           VARCHAR(15) NOT NULL DEFAULT '',
        business_name   VARCHAR(256) NOT NULL DEFAULT '',
        submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, student_id)
    );

    -- ===========================================================
    -- RA-8: IQAC
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS iqac_meetings (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        meeting_date    DATE NOT NULL,
        agenda          TEXT NOT NULL DEFAULT '',
        attendees       JSONB NOT NULL DEFAULT '[]',
        minutes         TEXT,
        action_items    JSONB,
        status          VARCHAR(32) NOT NULL DEFAULT 'SCHEDULED',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS iqac_action_items (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        meeting_id      UUID NOT NULL REFERENCES iqac_meetings(id),
        description     TEXT NOT NULL DEFAULT '',
        responsible     VARCHAR(128) NOT NULL DEFAULT '',
        deadline        DATE,
        status          VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS iqac_best_practices (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        title           VARCHAR(256) NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        category        VARCHAR(64) NOT NULL DEFAULT 'ACADEMIC',
        impact_metrics  TEXT NOT NULL DEFAULT '',
        academic_year   VARCHAR(16) NOT NULL DEFAULT '',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    """)


def downgrade() -> None:
    tables = [
        "iqac_best_practices", "iqac_action_items", "iqac_meetings",
        "graduation_employment_declarations", "graduation_saga_completions",
        "graduation_saga_signals", "library_memberships",
        "guardian_student_links", "guardian_accounts",
        "external_competition_nocs", "event_participants",
        "club_events", "club_members", "student_clubs",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
