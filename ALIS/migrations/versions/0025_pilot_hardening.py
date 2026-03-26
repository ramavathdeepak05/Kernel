"""P21 — Pilot Hardening: Shadow Mode, Data Migration, Webhooks, E19, Edge Cases

Revision ID: 0025
Revises: 0024
Create Date: 2026-03-19

Changes
───────
1.  shadow_mode_divergence_log   — nightly metric comparison log
2.  shadow_mode_go_live_log      — consecutive-days gate tracking
3.  data_migration_jobs          — 3-phase CSV import job tracking
4.  data_migration_errors        — per-row import error log
5.  outbound_webhook_subscriptions — event endpoint registry
6.  outbound_webhook_deliveries  — delivery + retry log
7.  reporting_gate_log           — EC-ADM-03 physical reporting gate
8.  grievance_anomaly_log        — EC-SS-01 spike detection log
9.  course_recalibration_log     — EC-ACA-01 disruption log
10. hostel_swap_requests         — EC-SS-04 swap exchange
11. answer_evaluation_records    — EC-EXM-05 AI draft + faculty confirm
12. seat_matrix ALTER            — category/quota columns + trigger
13. enrollment_type column       — enrollment_provisioning (EC-ADM-02)
14. New feature flags            — biometric_reporting_gate, ai_evaluation,
                                   shadow_mode seeding
"""

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. shadow_mode_divergence_log
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS shadow_mode_divergence_log (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        metric          VARCHAR(100) NOT NULL,
        alis_value      DECIMAL(15, 4),
        actual_value    DECIMAL(15, 4),
        divergence_pct  DECIMAL(10, 4),
        measured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_shadow_div_org_metric
        ON shadow_mode_divergence_log(org_id, metric, measured_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 2. shadow_mode_go_live_log
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS shadow_mode_go_live_log (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        consecutive_days    INTEGER NOT NULL DEFAULT 0,
        metrics_passing     JSONB NOT NULL DEFAULT '{}',
        can_go_live         BOOLEAN NOT NULL DEFAULT FALSE,
        checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_shadow_golive_org
        ON shadow_mode_go_live_log(org_id, checked_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 3. data_migration_jobs
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS data_migration_jobs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        entity_type     VARCHAR(50) NOT NULL,
        mode            VARCHAR(20) NOT NULL,
        status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        total_rows      INTEGER,
        processed_rows  INTEGER NOT NULL DEFAULT 0,
        inserted_rows   INTEGER NOT NULL DEFAULT 0,
        skipped_rows    INTEGER NOT NULL DEFAULT 0,
        error_count     INTEGER NOT NULL DEFAULT 0,
        file_name       TEXT,
        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ,
        actor_id        UUID,
        CONSTRAINT chk_migration_mode
            CHECK (mode IN ('validate', 'dry_run', 'commit')),
        CONSTRAINT chk_migration_status
            CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_migration_jobs_org
        ON data_migration_jobs(org_id, started_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 4. data_migration_errors
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS data_migration_errors (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        job_id          UUID NOT NULL REFERENCES data_migration_jobs(id) ON DELETE CASCADE,
        row_number      INTEGER NOT NULL,
        raw_data        JSONB,
        error_type      VARCHAR(50) NOT NULL DEFAULT 'VALIDATION',
        error_message   TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_error_type
            CHECK (error_type IN ('VALIDATION', 'DUPLICATE', 'CONSTRAINT', 'TRANSFORM'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_migration_errors_job
        ON data_migration_errors(job_id)
    """)

    # -------------------------------------------------------------------------
    # 5. outbound_webhook_subscriptions
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS outbound_webhook_subscriptions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        event_type      VARCHAR(100) NOT NULL,
        url             TEXT NOT NULL,
        secret_hash     TEXT NOT NULL,
        active          BOOLEAN NOT NULL DEFAULT TRUE,
        description     TEXT,
        created_by      UUID,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_webhook_subs_org_event
        ON outbound_webhook_subscriptions(org_id, event_type, active)
    """)

    # -------------------------------------------------------------------------
    # 6. outbound_webhook_deliveries
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS outbound_webhook_deliveries (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        subscription_id     UUID NOT NULL REFERENCES outbound_webhook_subscriptions(id),
        org_id              UUID NOT NULL,
        event_type          VARCHAR(100) NOT NULL,
        payload             JSONB NOT NULL DEFAULT '{}',
        status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        attempt_count       INTEGER NOT NULL DEFAULT 0,
        next_retry_at       TIMESTAMPTZ,
        last_http_status    INTEGER,
        last_error          TEXT,
        delivered_at        TIMESTAMPTZ,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_delivery_status
            CHECK (status IN ('PENDING', 'DELIVERED', 'FAILED', 'DEAD', 'REPLAYING'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_webhook_del_pending
        ON outbound_webhook_deliveries(status, next_retry_at)
        WHERE status = 'PENDING'
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_webhook_del_org
        ON outbound_webhook_deliveries(org_id, created_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 7. reporting_gate_log — EC-ADM-03
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS reporting_gate_log (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        application_id  UUID NOT NULL,
        student_id      UUID,
        reported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        method          VARCHAR(30) NOT NULL DEFAULT 'IN_PERSON',
        biometric_ref   TEXT,
        actor_id        UUID,
        notes           TEXT,
        CONSTRAINT chk_report_method
            CHECK (method IN ('IN_PERSON', 'BIOMETRIC', 'QR_SCAN', 'DIGILOCKER', 'REMOTE'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_reporting_gate_app
        ON reporting_gate_log(application_id)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_reporting_gate_org
        ON reporting_gate_log(org_id, reported_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 8. grievance_anomaly_log — EC-SS-01
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS grievance_anomaly_log (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        respondent_id       UUID,
        window_start        TIMESTAMPTZ NOT NULL,
        window_end          TIMESTAMPTZ NOT NULL,
        complaint_count     INTEGER NOT NULL,
        rolling_avg         DECIMAL(10, 2),
        spike_multiplier    DECIMAL(10, 2),
        outcome             VARCHAR(30) NOT NULL DEFAULT 'PENDING_REVIEW',
        resolved_by         UUID,
        resolved_at         TIMESTAMPTZ,
        reviewer_notes      TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_anomaly_outcome
            CHECK (outcome IN ('PENDING_REVIEW', 'CONFIRMED_SPIKE', 'FALSE_POSITIVE', 'ESCALATED'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_grievance_anomaly_org
        ON grievance_anomaly_log(org_id, created_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 9. course_recalibration_log — EC-ACA-01
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS course_recalibration_log (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        scope               VARCHAR(30) NOT NULL,
        scope_ref_id        UUID,
        reason              TEXT NOT NULL,
        disruption_days     INTEGER NOT NULL DEFAULT 1,
        affected_sessions   INTEGER NOT NULL DEFAULT 0,
        affected_deadlines  INTEGER NOT NULL DEFAULT 0,
        locked_exam_dates   INTEGER NOT NULL DEFAULT 0,
        actor_id            UUID,
        triggered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_recal_scope
            CHECK (scope IN ('INSTITUTION_WIDE', 'DEPARTMENT', 'PROGRAM', 'SECTION'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_recal_log_org
        ON course_recalibration_log(org_id, triggered_at DESC)
    """)

    # -------------------------------------------------------------------------
    # 10. hostel_swap_requests — EC-SS-04
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS hostel_swap_requests (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              UUID NOT NULL,
        requester_id        UUID NOT NULL REFERENCES students(id),
        requester_room_id   UUID,
        matched_student_id  UUID REFERENCES students(id),
        matched_room_id     UUID,
        severity            VARCHAR(20) NOT NULL DEFAULT 'ROUTINE',
        reason              TEXT NOT NULL,
        status              VARCHAR(30) NOT NULL DEFAULT 'OPEN',
        overflow_room_id    UUID,
        overflow_placed_at  TIMESTAMPTZ,
        overflow_deadline   TIMESTAMPTZ,
        approved_by         UUID REFERENCES users(id),
        approved_at         TIMESTAMPTZ,
        resolved_at         TIMESTAMPTZ,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_swap_severity
            CHECK (severity IN ('ROUTINE', 'URGENT', 'SAFETY')),
        CONSTRAINT chk_swap_status
            CHECK (status IN ('OPEN', 'MATCHED', 'PENDING_APPROVAL', 'APPROVED',
                              'OVERFLOW_PLACED', 'RESOLVED', 'CANCELLED'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_hostel_swap_org
        ON hostel_swap_requests(org_id, status, created_at DESC)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_hostel_swap_requester
        ON hostel_swap_requests(requester_id)
    """)

    # -------------------------------------------------------------------------
    # 11. answer_evaluation_records — EC-EXM-05
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS answer_evaluation_records (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id                  UUID NOT NULL,
        answer_script_id        UUID NOT NULL,
        student_id              UUID NOT NULL REFERENCES students(id),
        course_id               UUID NOT NULL,
        question_id             UUID,
        max_marks               DECIMAL(6, 2) NOT NULL,
        ai_draft_score          DECIMAL(6, 2),
        ai_confidence           DECIMAL(5, 4),
        faculty_final_score     DECIMAL(6, 2),
        override_reason         TEXT,
        rubber_stamp_flagged    BOOLEAN NOT NULL DEFAULT FALSE,
        policy_version_id       UUID,
        ai_evaluated_at         TIMESTAMPTZ,
        faculty_confirmed_at    TIMESTAMPTZ,
        confirmed_by            UUID REFERENCES users(id),
        status                  VARCHAR(30) NOT NULL DEFAULT 'AI_DRAFT',
        CONSTRAINT chk_eval_status
            CHECK (status IN ('AI_DRAFT', 'PENDING_FACULTY', 'FACULTY_CONFIRMED',
                              'OVERRIDE_PENDING', 'FINALIZED'))
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_answer_eval_script
        ON answer_evaluation_records(answer_script_id)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_answer_eval_pending
        ON answer_evaluation_records(org_id, status)
        WHERE status IN ('AI_DRAFT', 'PENDING_FACULTY', 'OVERRIDE_PENDING')
    """)

    # -------------------------------------------------------------------------
    # 12. seat_matrix — add category/quota columns + filled counters
    # -------------------------------------------------------------------------
    # Add category seat allocation columns (must sum to total_intake)
    for col in [
        "general_seats   INTEGER NOT NULL DEFAULT 0",
        "sc_seats        INTEGER NOT NULL DEFAULT 0",
        "st_seats        INTEGER NOT NULL DEFAULT 0",
        "obc_ncl_seats   INTEGER NOT NULL DEFAULT 0",
        "ews_seats       INTEGER NOT NULL DEFAULT 0",
        "pwd_seats       INTEGER NOT NULL DEFAULT 0",   # supernumerary
        "management_quota INTEGER NOT NULL DEFAULT 0",
        "nri_quota       INTEGER NOT NULL DEFAULT 0",
        "sports_quota    INTEGER NOT NULL DEFAULT 0",
        # Filled counters (maintained by trigger)
        "filled_general  INTEGER NOT NULL DEFAULT 0",
        "filled_sc       INTEGER NOT NULL DEFAULT 0",
        "filled_st       INTEGER NOT NULL DEFAULT 0",
        "filled_obc      INTEGER NOT NULL DEFAULT 0",
        "filled_ews      INTEGER NOT NULL DEFAULT 0",
        "filled_pwd      INTEGER NOT NULL DEFAULT 0",
        "filled_management INTEGER NOT NULL DEFAULT 0",
        "filled_nri      INTEGER NOT NULL DEFAULT 0",
        "filled_sports   INTEGER NOT NULL DEFAULT 0",
        "last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    ]:
        col_name = col.split()[0]
        op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='seat_matrix' AND column_name='{col_name}'
            ) THEN
                ALTER TABLE seat_matrix ADD COLUMN {col};
            END IF;
        END$$
        """)

    # Add category sum constraint (skip if exists)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'seat_matrix'
              AND constraint_name = 'chk_seat_matrix_category_sum'
        ) THEN
            ALTER TABLE seat_matrix ADD CONSTRAINT chk_seat_matrix_category_sum
            CHECK (
                general_seats + sc_seats + st_seats + obc_ncl_seats + ews_seats
                + management_quota + nri_quota + sports_quota <= total_seats + pwd_seats
            );
        END IF;
    END$$
    """)

    # Trigger function: decrement the correct filled counter on seat confirmation
    op.execute("""
    CREATE OR REPLACE FUNCTION decrement_seat_counter()
    RETURNS TRIGGER AS $$
    DECLARE
        v_category  TEXT;
        v_quota     TEXT;
    BEGIN
        -- Read category and quota from the enrollment record payload
        v_category := UPPER(COALESCE(NEW.category, 'GENERAL'));
        v_quota    := UPPER(COALESCE(NEW.quota, 'GENERAL'));

        UPDATE seat_matrix
        SET
            filled_general    = filled_general    + CASE WHEN v_category = 'GENERAL'    AND v_quota = 'GENERAL'    THEN 1 ELSE 0 END,
            filled_sc         = filled_sc         + CASE WHEN v_category = 'SC'         THEN 1 ELSE 0 END,
            filled_st         = filled_st         + CASE WHEN v_category = 'ST'         THEN 1 ELSE 0 END,
            filled_obc        = filled_obc        + CASE WHEN v_category = 'OBC_NCL'    THEN 1 ELSE 0 END,
            filled_ews        = filled_ews        + CASE WHEN v_category = 'EWS'        THEN 1 ELSE 0 END,
            filled_pwd        = filled_pwd        + CASE WHEN v_category = 'PWD'        THEN 1 ELSE 0 END,
            filled_management = filled_management + CASE WHEN v_quota    = 'MANAGEMENT' THEN 1 ELSE 0 END,
            filled_nri        = filled_nri        + CASE WHEN v_quota    = 'NRI'        THEN 1 ELSE 0 END,
            filled_sports     = filled_sports     + CASE WHEN v_quota    = 'SPORTS'     THEN 1 ELSE 0 END,
            filled_seats      = filled_seats + 1,
            last_updated_at   = NOW()
        WHERE tenant_id = NEW.org_id
          AND program_id = NEW.program_id
          AND intake_year = NEW.intake_year;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # NOTE: trigger skipped — enrollment_provisioning has no status/program_id/intake_year.
    # The decrement_seat_counter() function is registered; seat_matrix updates must be
    # wired via applicants.status transition (not enrollment_provisioning INSERT).
    op.execute("DROP TRIGGER IF EXISTS trg_decrement_seat_counter ON enrollment_provisioning")

    # -------------------------------------------------------------------------
    # 13. enrollment_type column on enrollment_provisioning — EC-ADM-02
    # -------------------------------------------------------------------------
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='enrollment_provisioning' AND column_name='enrollment_type'
        ) THEN
            ALTER TABLE enrollment_provisioning
                ADD COLUMN enrollment_type VARCHAR(20) NOT NULL DEFAULT 'STANDARD';
        END IF;
    END$$
    """)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='enrollment_provisioning' AND column_name='joining_date'
        ) THEN
            ALTER TABLE enrollment_provisioning ADD COLUMN joining_date DATE;
        END IF;
    END$$
    """)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='enrollment_provisioning' AND column_name='category'
        ) THEN
            ALTER TABLE enrollment_provisioning
                ADD COLUMN category VARCHAR(20) NOT NULL DEFAULT 'GENERAL';
        END IF;
    END$$
    """)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='enrollment_provisioning' AND column_name='quota'
        ) THEN
            ALTER TABLE enrollment_provisioning
                ADD COLUMN quota VARCHAR(20) NOT NULL DEFAULT 'GENERAL';
        END IF;
    END$$
    """)

    # -------------------------------------------------------------------------
    # 14. RLS on all new tables
    # -------------------------------------------------------------------------
    rls_tables = [
        "shadow_mode_divergence_log",
        "shadow_mode_go_live_log",
        "data_migration_jobs",
        # data_migration_errors excluded — no org_id column, inherits isolation via job_id FK
        "outbound_webhook_subscriptions",
        "outbound_webhook_deliveries",
        "reporting_gate_log",
        "grievance_anomaly_log",
        "course_recalibration_log",
        "hostel_swap_requests",
        "answer_evaluation_records",
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # PostgreSQL has no CREATE POLICY IF NOT EXISTS — drop first, then create
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)

    # -------------------------------------------------------------------------
    # 15. New feature flags in DEFAULT_FLAGS (seeded via migration for all orgs)
    # -------------------------------------------------------------------------
    op.execute("""
    INSERT INTO tenant_feature_flags (id, org_id, flag_key, enabled, config, updated_by)
    SELECT
        gen_random_uuid(),
        org.id,
        f.flag_key,
        f.enabled,
        f.config::jsonb,
        NULL::uuid
    FROM organizations org
    CROSS JOIN (VALUES
        ('admissions.biometric_reporting_gate',    false, '{}'),
        ('examinations.ai_evaluation',             true,  '{}'),
        ('shadow_mode.enabled',                    false, '{}'),
        ('comms.suppress_in_shadow_mode',          true,  '{}')
    ) AS f(flag_key, enabled, config)
    WHERE NOT EXISTS (
        SELECT 1 FROM tenant_feature_flags ff
        WHERE ff.org_id = org.id AND ff.flag_key = f.flag_key
    )
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_decrement_seat_counter ON enrollment_provisioning")
    op.execute("DROP FUNCTION IF EXISTS decrement_seat_counter()")
    op.execute("DROP TABLE IF EXISTS answer_evaluation_records CASCADE")
    op.execute("DROP TABLE IF EXISTS hostel_swap_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS course_recalibration_log CASCADE")
    op.execute("DROP TABLE IF EXISTS grievance_anomaly_log CASCADE")
    op.execute("DROP TABLE IF EXISTS reporting_gate_log CASCADE")
    op.execute("DROP TABLE IF EXISTS outbound_webhook_deliveries CASCADE")
    op.execute("DROP TABLE IF EXISTS outbound_webhook_subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS data_migration_errors CASCADE")
    op.execute("DROP TABLE IF EXISTS data_migration_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS shadow_mode_go_live_log CASCADE")
    op.execute("DROP TABLE IF EXISTS shadow_mode_divergence_log CASCADE")
