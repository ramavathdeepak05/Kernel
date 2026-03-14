"""Initial schema — all E01–E04 + P0 tables

Revision ID: 0001
Revises:
Create Date: 2026-03-05
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # -------------------------------------------------------------------------
    # E01 — Auth, Users, Organisations, Roles
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS organisations (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name        TEXT NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        status      TEXT NOT NULL DEFAULT 'ACTIVE',
        metadata    JSONB NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      UUID NOT NULL REFERENCES organisations(id),
        email       TEXT NOT NULL,
        phone       TEXT,
        name        TEXT NOT NULL,
        role        TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'ACTIVE',
        password_hash TEXT,
        metadata    JSONB NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ,
        UNIQUE(org_id, email)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      UUID NOT NULL REFERENCES organisations(id),
        name        TEXT NOT NULL,
        permissions JSONB NOT NULL DEFAULT '[]',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, name)
    )""")

    # -------------------------------------------------------------------------
    # E02 — Workflow Engine, Approvals
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      UUID NOT NULL,
        name        TEXT NOT NULL,
        definition  JSONB NOT NULL DEFAULT '{}',
        status      TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS approval_requests (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          UUID NOT NULL,
        workflow_id     UUID,
        entity_type     TEXT NOT NULL,
        entity_id       UUID NOT NULL,
        requested_by    UUID NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',
        quorum_required INT NOT NULL DEFAULT 1,
        approvals       JSONB NOT NULL DEFAULT '[]',
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        decided_at      TIMESTAMPTZ
    )""")

    # -------------------------------------------------------------------------
    # E03 — AI Gateway, Audit
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_ledger (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        action          TEXT NOT NULL,
        actor_id        TEXT NOT NULL,
        actor_type      TEXT,
        actor_role      TEXT,
        entity_type     TEXT,
        entity_id       TEXT,
        module          TEXT,
        wizard          TEXT,
        success         BOOLEAN NOT NULL DEFAULT TRUE,
        failure_reason  TEXT,
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_org_action ON audit_ledger(org_id, action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_ledger(entity_type, entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_ledger(created_at)")

    # PGVector — counsellor embeddings (E04-S05)
    op.execute("""
    CREATE TABLE IF NOT EXISTS counsellor_embeddings (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        counsellor_id   TEXT NOT NULL,
        profile_text    TEXT NOT NULL,
        embedding       vector(768),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, counsellor_id)
    )""")

    # -------------------------------------------------------------------------
    # E04 — Admissions (M1)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS applicants (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        name                TEXT NOT NULL,
        email               TEXT NOT NULL,
        phone               TEXT,
        intended_program    TEXT,
        source_channel      TEXT,
        status              TEXT NOT NULL DEFAULT 'APPLIED',
        metadata            JSONB NOT NULL DEFAULT '{}',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_applicants_org_status ON applicants(org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_applicants_email ON applicants(org_id, email)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS lead_merge_log (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        primary_id          UUID NOT NULL,
        merged_id           UUID NOT NULL,
        similarity_score    DECIMAL(5,4),
        method              TEXT NOT NULL,
        justification       TEXT,
        merged_by           TEXT NOT NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS application_documents (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        applicant_id        UUID NOT NULL,
        doc_type            TEXT NOT NULL,
        file_path           TEXT NOT NULL,
        is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
        verification_method TEXT,
        verification_detail TEXT,
        verified_by         TEXT,
        verified_at         TIMESTAMPTZ,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS counsellor_assignments (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        applicant_id        UUID NOT NULL,
        counsellor_id       UUID NOT NULL,
        method              TEXT NOT NULL,
        similarity_score    DECIMAL(5,4),
        assigned_by         TEXT NOT NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS offer_letters (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        applicant_id        UUID NOT NULL,
        program_name        TEXT NOT NULL,
        academic_year       TEXT NOT NULL,
        template_version    INT NOT NULL DEFAULT 1,
        content_hash        TEXT NOT NULL,
        pdf_path            TEXT NOT NULL,
        issued_at           TIMESTAMPTZ NOT NULL,
        is_valid            BOOLEAN NOT NULL DEFAULT TRUE
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS admission_records (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        applicant_id        UUID NOT NULL,
        registration_number TEXT NOT NULL UNIQUE,
        payment_reference   TEXT NOT NULL,
        fee_amount          DECIMAL(12,2),
        currency            CHAR(3) NOT NULL DEFAULT 'INR',
        admitted_at         TIMESTAMPTZ NOT NULL,
        admitted_by         TEXT NOT NULL
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS intake_quality_scores (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        batch_id        TEXT NOT NULL,
        program         TEXT,
        quality_score   DECIMAL(5,4) NOT NULL,
        factors         JSONB NOT NULL DEFAULT '{}',
        alert_triggered BOOLEAN NOT NULL DEFAULT FALSE,
        scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        applicant_id    UUID NOT NULL UNIQUE,
        roll_number     TEXT NOT NULL UNIQUE,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL,
        phone           TEXT,
        program         TEXT NOT NULL,
        enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_students_org ON students(org_id)")

    # -------------------------------------------------------------------------
    # P0-S17 — Domain Events
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS domain_events (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        event_type      TEXT NOT NULL,
        entity_type     TEXT NOT NULL,
        entity_id       TEXT NOT NULL,
        payload         JSONB NOT NULL DEFAULT '{}',
        actor_id        TEXT NOT NULL DEFAULT 'system',
        correlation_id  TEXT,
        status          TEXT NOT NULL DEFAULT 'PENDING',
        published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        processed_at    TIMESTAMPTZ,
        retry_count     INT NOT NULL DEFAULT 0,
        failure_reason  TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON domain_events(status, published_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON domain_events(event_type, org_id)")

    # -------------------------------------------------------------------------
    # P0-S19 — Academic Calendar
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS academic_calendars (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        academic_year   TEXT NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS calendar_phases (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        calendar_id     UUID NOT NULL REFERENCES academic_calendars(id),
        phase_name      TEXT NOT NULL,
        start_date      DATE NOT NULL,
        end_date        DATE NOT NULL,
        CHECK (phase_name IN (
            'ENROLLMENT_OPEN','CLASSES','ATTENDANCE_LOCK',
            'EXAM_REGISTRATION','EXAM_PERIOD','RESULTS','SEMESTER_BREAK'
        ))
    )""")

    # -------------------------------------------------------------------------
    # Row-Level Security (tenant isolation)
    # -------------------------------------------------------------------------
    for table in [
        "applicants", "lead_merge_log", "application_documents",
        "counsellor_assignments", "offer_letters", "admission_records",
        "intake_quality_scores", "students", "domain_events",
        "academic_calendars",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    tables = [
        "calendar_phases", "academic_calendars",
        "domain_events", "students", "intake_quality_scores",
        "admission_records", "offer_letters", "counsellor_assignments",
        "application_documents", "lead_merge_log", "applicants",
        "counsellor_embeddings", "audit_ledger",
        "approval_requests", "workflows",
        "roles", "users", "organisations",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
