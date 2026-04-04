"""
0043 — Workflow Compliance: All missing tables for P0/P1/P2 gaps

Tables created:
- question_papers, offline_exam_bundles (P0-2: Exam Vault encryption)
- exam_condonations (P0-4: Attendance condonation)
- reval_supplementary_escrows (P0-5: EC-EXM-03 revaluation escrow)
- vendors, purchase_orders, purchase_invoices, tds_deductions (P1-1: FM-4)
- budgets, budget_transactions (P1-2: FM-6)
- refund_requests, student_fee_assignments (P1-4/5: FM-3 + FM-1)
- salary_tds_records (P1-3: TDS 24Q)
- training_programs, training_enrollments, training_assessments (P1-6: HR-5)
- vacancies, recruitment_applications (P1-7: HR-1)
- appraisals (P1-8: HR-4)
- separations, no_dues_clearances (P1-9: HR-6)
- faculty_publications (P2-1: EC-HR-02)

CHECK constraints:
- answer_evaluation_records: status = 'CONFIRMED' implies faculty_final_score IS NOT NULL (P0-3)

Revision ID: 0043
Revises: 0042
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""

    -- ===========================================================
    -- P0-2: Question Paper Vault Encryption
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS question_papers (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        exam_id         UUID NOT NULL,
        course_code     VARCHAR(32) NOT NULL,
        paper_set       VARCHAR(4)  NOT NULL DEFAULT 'A',
        status          VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        content_hash    VARCHAR(64) NOT NULL DEFAULT '',
        storage_path    TEXT NOT NULL DEFAULT '',
        encrypted_at    TIMESTAMPTZ,
        approved_by     VARCHAR(64),
        approved_at     TIMESTAMPTZ,
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_qp_org_exam ON question_papers(org_id, exam_id);

    CREATE TABLE IF NOT EXISTS offline_exam_bundles (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        exam_id         UUID NOT NULL,
        paper_count     INT NOT NULL DEFAULT 0,
        envelope_key_hash VARCHAR(64) NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'SEALED',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P0-3: AI Evaluation CHECK Constraint
    -- ===========================================================
    DO $$ BEGIN
        ALTER TABLE answer_evaluation_records
            ADD CONSTRAINT chk_faculty_confirmation
            CHECK (
                status NOT IN ('CONFIRMED', 'OVERRIDE_CONFIRMED')
                OR faculty_final_score IS NOT NULL
            );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- ===========================================================
    -- P0-4: Exam Condonation
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS exam_condonations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        exam_id         UUID NOT NULL,
        course_id       UUID NOT NULL,
        reason          TEXT NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        requested_by    VARCHAR(64) NOT NULL,
        decided_by      VARCHAR(64),
        decided_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_condonation_student ON exam_condonations(org_id, student_id, exam_id);

    -- ===========================================================
    -- P0-5: Revaluation-Supplementary Escrow (EC-EXM-03)
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS reval_supplementary_escrows (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id                  VARCHAR(64) NOT NULL,
        student_id              UUID NOT NULL,
        course_id               UUID NOT NULL,
        supplementary_exam_id   UUID NOT NULL,
        reeval_request_id       UUID NOT NULL,
        escrow_amount           DECIMAL(12,2) NOT NULL DEFAULT 0,
        status                  VARCHAR(32) NOT NULL DEFAULT 'CONDITIONAL',
        resolved_at             TIMESTAMPTZ,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P1-1: FM-4 Vendor & Purchase
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS vendors (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        name            VARCHAR(256) NOT NULL,
        gstin           VARCHAR(15) NOT NULL DEFAULT '',
        pan             VARCHAR(10) NOT NULL DEFAULT '',
        address         TEXT NOT NULL DEFAULT '',
        contact_email   VARCHAR(256) NOT NULL DEFAULT '',
        contact_phone   VARCHAR(20) NOT NULL DEFAULT '',
        bank_account    VARCHAR(32) NOT NULL DEFAULT '',
        bank_ifsc       VARCHAR(16) NOT NULL DEFAULT '',
        tds_section     VARCHAR(32) NOT NULL DEFAULT '194C_OTHERS',
        status          VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        approved_by     VARCHAR(64),
        approved_at     TIMESTAMPTZ,
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_vendor_org ON vendors(org_id, status);

    CREATE TABLE IF NOT EXISTS purchase_orders (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        po_number       VARCHAR(32) NOT NULL,
        vendor_id       UUID NOT NULL REFERENCES vendors(id),
        department      VARCHAR(128) NOT NULL DEFAULT '',
        description     TEXT NOT NULL DEFAULT '',
        line_items      JSONB NOT NULL DEFAULT '[]',
        subtotal        DECIMAL(12,2) NOT NULL DEFAULT 0,
        gst_amount      DECIMAL(12,2) NOT NULL DEFAULT 0,
        total_amount    DECIMAL(12,2) NOT NULL DEFAULT 0,
        budget_head     VARCHAR(128) NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        requested_by    VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_po_org ON purchase_orders(org_id, status);

    CREATE TABLE IF NOT EXISTS purchase_invoices (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        po_id           UUID REFERENCES purchase_orders(id),
        vendor_id       UUID NOT NULL REFERENCES vendors(id),
        invoice_number  VARCHAR(64) NOT NULL,
        invoice_date    DATE NOT NULL,
        taxable_amount  DECIMAL(12,2) NOT NULL DEFAULT 0,
        cgst            DECIMAL(12,2) NOT NULL DEFAULT 0,
        sgst            DECIMAL(12,2) NOT NULL DEFAULT 0,
        igst            DECIMAL(12,2) NOT NULL DEFAULT 0,
        total_amount    DECIMAL(12,2) NOT NULL DEFAULT 0,
        itc_eligible    BOOLEAN NOT NULL DEFAULT TRUE,
        status          VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS tds_deductions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        vendor_id       UUID NOT NULL REFERENCES vendors(id),
        po_id           UUID REFERENCES purchase_orders(id),
        deduction_type  VARCHAR(32) NOT NULL DEFAULT 'NON_SALARY',
        tds_section     VARCHAR(32) NOT NULL,
        gross_amount    DECIMAL(12,2) NOT NULL,
        tds_rate        DECIMAL(5,4) NOT NULL,
        tds_amount      DECIMAL(12,2) NOT NULL,
        payment_date    DATE NOT NULL,
        challan_number  VARCHAR(32) NOT NULL DEFAULT '',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P1-2: FM-6 Budget Planning
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS budgets (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        financial_year  VARCHAR(16) NOT NULL,
        department      VARCHAR(128) NOT NULL,
        cost_center     VARCHAR(128) NOT NULL DEFAULT '',
        allocated_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
        committed_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
        spent_amount    DECIMAL(14,2) NOT NULL DEFAULT 0,
        status          VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_budget_org_fy ON budgets(org_id, financial_year);

    CREATE TABLE IF NOT EXISTS budget_transactions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        budget_id       UUID NOT NULL REFERENCES budgets(id),
        transaction_type VARCHAR(32) NOT NULL,
        amount          DECIMAL(14,2) NOT NULL,
        reference       TEXT NOT NULL DEFAULT '',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P1-4/5: FM-3 Refunds + FM-1 Fee Version Locking
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS refund_requests (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        total_fee_paid  DECIMAL(12,2) NOT NULL,
        refund_amount   DECIMAL(12,2) NOT NULL,
        processing_fee  DECIMAL(12,2) NOT NULL DEFAULT 1000,
        deduction_pct   DECIMAL(5,1) NOT NULL DEFAULT 0,
        policy_applied  TEXT NOT NULL DEFAULT '',
        reason          VARCHAR(64) NOT NULL DEFAULT 'voluntary',
        status          VARCHAR(32) NOT NULL DEFAULT 'REQUESTED',
        requested_by    VARCHAR(64) NOT NULL,
        approved_by     VARCHAR(64),
        approved_at     TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS student_fee_assignments (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        student_id      UUID NOT NULL,
        fee_structure_id UUID NOT NULL,
        academic_year   VARCHAR(16) NOT NULL,
        locked_at       TIMESTAMPTZ NOT NULL,
        is_locked       BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, student_id, fee_structure_id)
    );

    CREATE TABLE IF NOT EXISTS salary_tds_records (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        employee_name   VARCHAR(256) NOT NULL,
        pan             VARCHAR(10) NOT NULL DEFAULT '',
        gross_salary    DECIMAL(12,2) NOT NULL,
        tds_deducted    DECIMAL(12,2) NOT NULL,
        pay_period      DATE NOT NULL,
        challan_number  VARCHAR(32) NOT NULL DEFAULT '',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P1-6: HR-5 Training & Development
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS training_programs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        title           VARCHAR(256) NOT NULL,
        training_type   VARCHAR(32) NOT NULL DEFAULT 'FDP',
        description     TEXT NOT NULL DEFAULT '',
        start_date      DATE,
        end_date        DATE,
        duration_days   INT NOT NULL DEFAULT 1,
        max_participants INT NOT NULL DEFAULT 50,
        venue           VARCHAR(256) NOT NULL DEFAULT '',
        organizer       VARCHAR(256) NOT NULL DEFAULT '',
        status          VARCHAR(32) NOT NULL DEFAULT 'PLANNED',
        created_by      VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_training_org ON training_programs(org_id, status);

    CREATE TABLE IF NOT EXISTS training_enrollments (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        program_id      UUID NOT NULL REFERENCES training_programs(id),
        staff_id        UUID NOT NULL,
        status          VARCHAR(32) NOT NULL DEFAULT 'REGISTERED',
        enrolled_at     TIMESTAMPTZ NOT NULL,
        completed_at    TIMESTAMPTZ,
        certificate_url TEXT
    );

    CREATE TABLE IF NOT EXISTS training_assessments (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        program_id      UUID NOT NULL REFERENCES training_programs(id),
        assessment_type VARCHAR(32) NOT NULL DEFAULT 'EFFECTIVENESS',
        scheduled_date  DATE,
        status          VARCHAR(32) NOT NULL DEFAULT 'SCHEDULED',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, program_id, assessment_type)
    );

    -- ===========================================================
    -- P1-7: HR-1 Recruitment
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS vacancies (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              VARCHAR(64) NOT NULL,
        department          VARCHAR(128) NOT NULL,
        designation         VARCHAR(128) NOT NULL,
        positions_count     INT NOT NULL DEFAULT 1,
        qualification_requirements TEXT NOT NULL DEFAULT '',
        ugc_designation     VARCHAR(64) NOT NULL DEFAULT '',
        budget_id           UUID REFERENCES budgets(id),
        status              VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        sanctioned_by       VARCHAR(64),
        sanctioned_at       TIMESTAMPTZ,
        created_by          VARCHAR(64) NOT NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS recruitment_applications (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        vacancy_id      UUID NOT NULL REFERENCES vacancies(id),
        applicant_name  VARCHAR(256) NOT NULL,
        email           VARCHAR(256) NOT NULL DEFAULT '',
        phone           VARCHAR(20) NOT NULL DEFAULT '',
        has_phd         BOOLEAN NOT NULL DEFAULT FALSE,
        has_net_slet    BOOLEAN NOT NULL DEFAULT FALSE,
        teaching_years  INT NOT NULL DEFAULT 0,
        publication_count INT NOT NULL DEFAULT 0,
        resume_url      TEXT NOT NULL DEFAULT '',
        screening_result JSONB,
        status          VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
        screened_at     TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P1-8: HR-4 Performance Appraisal (4-stage)
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS appraisals (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id              VARCHAR(64) NOT NULL,
        staff_id            UUID NOT NULL,
        appraisal_period    VARCHAR(32) NOT NULL DEFAULT '',
        designation         VARCHAR(128) NOT NULL DEFAULT '',
        self_assessment     JSONB NOT NULL DEFAULT '{}',
        api_score           INT NOT NULL DEFAULT 0,
        publications_count  INT NOT NULL DEFAULT 0,
        service_years       DECIMAL(5,1) NOT NULL DEFAULT 0,
        status              VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
        hod_comments        TEXT,
        hod_reviewed_by     VARCHAR(64),
        dean_comments       TEXT,
        dean_reviewed_by    VARCHAR(64),
        committee_decision  VARCHAR(32),
        committee_comments  TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_appraisal_org_staff ON appraisals(org_id, staff_id);

    -- ===========================================================
    -- P1-9: HR-6 Separation
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS separations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        staff_id        UUID NOT NULL,
        separation_type VARCHAR(32) NOT NULL DEFAULT 'RESIGNATION',
        reason          TEXT NOT NULL DEFAULT '',
        last_working_date DATE,
        status          VARCHAR(32) NOT NULL DEFAULT 'INITIATED',
        initiated_by    VARCHAR(64) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS no_dues_clearances (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        separation_id   UUID NOT NULL REFERENCES separations(id),
        staff_id        UUID NOT NULL,
        department      VARCHAR(32) NOT NULL,
        status          VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        cleared_by      VARCHAR(64),
        cleared_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ===========================================================
    -- P2-1: EC-HR-02 Faculty Publications
    -- ===========================================================
    CREATE TABLE IF NOT EXISTS faculty_publications (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          VARCHAR(64) NOT NULL,
        staff_id        UUID NOT NULL,
        title           TEXT NOT NULL,
        journal         VARCHAR(512) NOT NULL DEFAULT '',
        year            VARCHAR(4) NOT NULL DEFAULT '',
        doi             VARCHAR(256) NOT NULL DEFAULT '',
        citation_count  INT NOT NULL DEFAULT 0,
        source          VARCHAR(32) NOT NULL DEFAULT 'MANUAL',
        status          VARCHAR(32) NOT NULL DEFAULT 'UNVERIFIED',
        verified_by     VARCHAR(64),
        verified_at     TIMESTAMPTZ,
        discovered_at   TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_faculty_pub_staff ON faculty_publications(org_id, staff_id);

    """)


def downgrade() -> None:
    tables = [
        "faculty_publications", "no_dues_clearances", "separations",
        "appraisals", "recruitment_applications", "vacancies",
        "training_assessments", "training_enrollments", "training_programs",
        "salary_tds_records", "student_fee_assignments", "refund_requests",
        "budget_transactions", "budgets", "tds_deductions",
        "purchase_invoices", "purchase_orders", "vendors",
        "reval_supplementary_escrows", "exam_condonations",
        "offline_exam_bundles", "question_papers",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
