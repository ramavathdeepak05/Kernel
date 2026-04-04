"""
0045 — Final compliance tables: remaining gaps for 100% coverage

New tables:
- adjunct_availability (EC-ACA-04)
- document_verifications (QR code verification)
- medical_emergency_alerts, health_clearances (SS-7)
- naac_evidence, dvv_queries (RA-1 SSR/DVV)
- student_satisfaction_surveys, sss_responses (RA-1 SSS)

Columns added:
- attendance_sessions: mass_bunk_flagged, mass_bunk_rate, mass_bunk_resolved
- grievances: category, severity, assigned_committee, confidential, hearing_date, etc.

Revision ID: 0045
Revises: 0044
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""

    -- ===========================================================
    -- EC-ACA-04: Adjunct Faculty Scheduling
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS adjunct_availability (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        faculty_id      UUID NOT NULL,
        week_start      DATE NOT NULL,
        slots           JSONB NOT NULL DEFAULT '[]',
        status          VARCHAR(32) NOT NULL DEFAULT 'SUBMITTED',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, faculty_id, week_start)
    );

    -- ===========================================================
    -- Attendance session mass bunk columns
    -- ===========================================================
    DO $$ BEGIN
        ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS mass_bunk_flagged BOOLEAN DEFAULT FALSE;
        ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS mass_bunk_rate DECIMAL(5,4);
        ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS mass_bunk_resolved VARCHAR(32);
        ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS mass_bunk_resolved_by VARCHAR(64);
    EXCEPTION WHEN undefined_table THEN NULL;
    END $$;

    -- ===========================================================
    -- QR Code Document Verification
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS document_verifications (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        document_type   VARCHAR(32) NOT NULL,
        document_id     UUID NOT NULL,
        student_id      UUID NOT NULL,
        content_hash    VARCHAR(64) NOT NULL,
        verification_url TEXT NOT NULL,
        issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_doc_verify ON document_verifications(id);

    -- ===========================================================
    -- SS-7: Medical Emergency + Health Clearance
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS medical_emergency_alerts (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        details         TEXT NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        triggered_by    VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS health_clearances (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        status          VARCHAR(32) NOT NULL DEFAULT 'CLEARED',
        issued_by       VARCHAR(64) NOT NULL,
        issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- Grievance workflow columns
    -- ===========================================================
    DO $$ BEGIN
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS category VARCHAR(64);
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS severity VARCHAR(32);
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS assigned_committee VARCHAR(64);
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS confidential BOOLEAN DEFAULT FALSE;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS classified_at TIMESTAMPTZ;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS hearing_date DATE;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS hearing_notes TEXT;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS resolution TEXT;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS resolution_action TEXT;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(64);
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
        ALTER TABLE grievances ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ;
    EXCEPTION WHEN undefined_table THEN NULL;
    END $$;

    -- ===========================================================
    -- RA-1: NAAC Evidence + DVV + SSS
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS naac_evidence (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        criterion       VARCHAR(8) NOT NULL,
        title           VARCHAR(256) NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        document_url    TEXT NOT NULL DEFAULT '',
        evidence_type   VARCHAR(32) NOT NULL DEFAULT 'DOCUMENT',
        uploaded_by     VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_naac_evidence_org ON naac_evidence(org_id, criterion);

    CREATE TABLE IF NOT EXISTS dvv_queries (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        query_text      TEXT NOT NULL DEFAULT '',
        criterion       VARCHAR(8) NOT NULL DEFAULT '',
        response        TEXT,
        evidence_ids    TEXT[],
        sla_deadline    TIMESTAMPTZ,
        responded_by    VARCHAR(64),
        responded_at    TIMESTAMPTZ,
        status          VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS student_satisfaction_surveys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        academic_year   VARCHAR(16) NOT NULL,
        status          VARCHAR(32) NOT NULL DEFAULT 'OPEN',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS sss_responses (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        survey_id       UUID NOT NULL REFERENCES student_satisfaction_surveys(id),
        student_id      UUID NOT NULL,
        responses       JSONB NOT NULL DEFAULT '{}',
        submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, survey_id, student_id)
    );

    """)


def downgrade() -> None:
    tables = [
        "sss_responses", "student_satisfaction_surveys", "dvv_queries",
        "naac_evidence", "health_clearances", "medical_emergency_alerts",
        "document_verifications", "adjunct_availability",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
