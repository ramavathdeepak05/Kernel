"""E14 Regulatory & Accreditation — schema

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-15

Changes
───────
1. regulatory_metrics — one row per metric per tenant per date
   E14 is a pure event consumer. Every domain event from every module
   increments exactly one counter (or overwrites one latest-value) in
   this table. The NAAC/NIRF/AISHE dashboards read only from here —
   never from source module tables. This keeps regulatory reporting
   isolated and ensures zero performance impact on live modules.

   Metric keys follow the convention:
     <framework>.<criterion>.<indicator>
   e.g.
     naac.criterion_1.student_faculty_ratio
     naac.criterion_5.grievance_resolution_rate
     nirf.teaching_learning.pass_percentage
     aishe.enrollment.total_students

2. naac_evidence — structured evidence items for NAAC SSR criteria
   Each row stores one piece of documentary evidence (uploaded file,
   data snapshot, or API response) linked to a specific NAAC criterion
   and indicator.  Used to auto-draft SSR criterion narratives via the
   NARRATIVE LLM task class.

3. nirf_data — annual NIRF submission data
   One row per institution per year per NIRF parameter group.
   Computed by aggregating regulatory_metrics rows for the reporting
   academic year.

4. aishe_data — annual AISHE return data
   One row per institution per year per AISHE data table.
   Same aggregation pattern as NIRF.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────────
    # 1. regulatory_metrics
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS regulatory_metrics (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,

        -- dot-notation: "naac.criterion_1.student_faculty_ratio"
        metric_key      TEXT NOT NULL,

        -- NAAC | NIRF | AISHE | UGC | NBA | INTERNAL
        framework       TEXT NOT NULL DEFAULT 'NAAC',

        -- The computed metric value.
        -- Numeric metrics (counts, percentages, ratios) stored as DECIMAL.
        -- Categorical metrics stored as 0/1 or mapped values.
        metric_value    DECIMAL(18, 4),

        -- Supplementary breakdown as JSONB.
        -- e.g. {"by_program": {"B.Tech": 1250, "M.Tech": 180}, "male": 830, "female": 600}
        breakdown       JSONB NOT NULL DEFAULT '{}',

        -- The date this metric snapshot was valid for.
        -- For real-time counters: today's date.
        -- For annual snapshots: last day of the academic year.
        metric_date     DATE NOT NULL DEFAULT CURRENT_DATE,

        -- Source event that last updated this row
        source_event    TEXT,
        source_event_id UUID,

        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        -- One metric value per org per key per date
        CONSTRAINT uq_regulatory_metric UNIQUE (org_id, metric_key, metric_date)
    )
    """)

    op.execute("""
    ALTER TABLE regulatory_metrics ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON regulatory_metrics
        USING (org_id::text = current_setting('alis.current_tenant', true));
    """)

    # Composite index for dashboard queries: org + framework + date range
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_reg_metrics_org_framework_date
        ON regulatory_metrics (org_id, framework, metric_date DESC);
    """)

    # Index for event-driven upserts: org + metric_key lookup
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_reg_metrics_org_key
        ON regulatory_metrics (org_id, metric_key);
    """)

    # ─────────────────────────────────────────────────────────────────
    # 2. naac_evidence
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS naac_evidence (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,

        -- NAAC SSR criterion (1–7) and sub-metric key
        criterion       INTEGER NOT NULL,           -- 1–7
        indicator_key   TEXT NOT NULL,              -- e.g. "1.1.3" or "student_faculty_ratio"

        -- DOCUMENT | DATA_SNAPSHOT | API_RESPONSE | NARRATIVE_DRAFT
        evidence_type   TEXT NOT NULL DEFAULT 'DOCUMENT',

        -- Human-readable title for NAAC peer review
        title           TEXT NOT NULL,

        -- For DOCUMENT: MinIO object key
        -- For DATA_SNAPSHOT: embedded JSONB in evidence_data
        -- For NARRATIVE_DRAFT: text in narrative_draft
        file_key        TEXT,

        -- Structured data (for DATA_SNAPSHOT evidence)
        evidence_data   JSONB NOT NULL DEFAULT '{}',

        -- LLM-generated SSR narrative (NARRATIVE task class — 70B model)
        -- NULL until ai_narrative_task runs
        narrative_draft TEXT,

        -- COLLECTED | DRAFT | REVIEWED | SUBMITTED
        status          TEXT NOT NULL DEFAULT 'COLLECTED',

        -- Academic year this evidence pertains to, e.g. "2025-26"
        academic_year   TEXT NOT NULL,

        collected_by    UUID,
        reviewed_by     UUID,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ
    )
    """)

    op.execute("""
    ALTER TABLE naac_evidence ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON naac_evidence
        USING (org_id::text = current_setting('alis.current_tenant', true));
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_naac_evidence_org_criterion
        ON naac_evidence (org_id, criterion, academic_year);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_naac_evidence_status
        ON naac_evidence (org_id, status)
        WHERE status != 'SUBMITTED';
    """)

    # ─────────────────────────────────────────────────────────────────
    # 3. nirf_data
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS nirf_data (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,

        -- NIRF submission year (calendar year of submission)
        submission_year INTEGER NOT NULL,

        -- NIRF parameter group:
        -- TLR | RPC | GO | OI | PERCEPTION
        parameter_group TEXT NOT NULL,

        -- Computed values for this parameter group
        -- Matches NIRF submission template field names exactly
        data            JSONB NOT NULL DEFAULT '{}',

        -- DRAFT | FINALISED | SUBMITTED
        status          TEXT NOT NULL DEFAULT 'DRAFT',

        computed_at     TIMESTAMPTZ,
        submitted_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ,

        CONSTRAINT uq_nirf_data UNIQUE (org_id, submission_year, parameter_group)
    )
    """)

    op.execute("""
    ALTER TABLE nirf_data ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON nirf_data
        USING (org_id::text = current_setting('alis.current_tenant', true));
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_nirf_data_org_year
        ON nirf_data (org_id, submission_year DESC);
    """)

    # ─────────────────────────────────────────────────────────────────
    # 4. aishe_data
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS aishe_data (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,

        -- Academic year: "2025-26"
        academic_year   TEXT NOT NULL,

        -- AISHE data table identifier (matches AISHE portal table codes)
        -- e.g. "Table_1A" (Enrolment), "Table_9" (Faculty Qualifications)
        table_code      TEXT NOT NULL,

        -- Populated data matching AISHE portal field names
        data            JSONB NOT NULL DEFAULT '{}',

        -- DRAFT | VALIDATED | SUBMITTED
        status          TEXT NOT NULL DEFAULT 'DRAFT',

        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ,

        CONSTRAINT uq_aishe_data UNIQUE (org_id, academic_year, table_code)
    )
    """)

    op.execute("""
    ALTER TABLE aishe_data ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON aishe_data
        USING (org_id::text = current_setting('alis.current_tenant', true));
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_aishe_data_org_year
        ON aishe_data (org_id, academic_year DESC);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_aishe_data_org_year")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON aishe_data")
    op.execute("DROP TABLE IF EXISTS aishe_data")

    op.execute("DROP INDEX IF EXISTS ix_nirf_data_org_year")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON nirf_data")
    op.execute("DROP TABLE IF EXISTS nirf_data")

    op.execute("DROP INDEX IF EXISTS ix_naac_evidence_status")
    op.execute("DROP INDEX IF EXISTS ix_naac_evidence_org_criterion")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON naac_evidence")
    op.execute("DROP TABLE IF EXISTS naac_evidence")

    op.execute("DROP INDEX IF EXISTS ix_reg_metrics_org_key")
    op.execute("DROP INDEX IF EXISTS ix_reg_metrics_org_framework_date")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON regulatory_metrics")
    op.execute("DROP TABLE IF EXISTS regulatory_metrics")
