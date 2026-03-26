from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE readmission_applications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            applicant_name VARCHAR(200) NOT NULL,
            applicant_email VARCHAR(200) NOT NULL,
            applicant_phone VARCHAR(30),
            previous_roll_number VARCHAR(50),
            program_id UUID NOT NULL,
            previous_institution VARCHAR(200),
            gap_reason TEXT NOT NULL,
            gap_from DATE NOT NULL,
            gap_to DATE NOT NULL,
            semesters_completed INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'SUBMITTED',
            new_student_id UUID,
            new_roll_number VARCHAR(50),
            reviewed_by UUID,
            review_notes TEXT,
            approved_at TIMESTAMPTZ,
            rejected_at TIMESTAMPTZ,
            policy_version_id VARCHAR(80),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE credit_transfer_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            student_id UUID NOT NULL,
            readmission_id UUID REFERENCES readmission_applications(id),
            source_institution VARCHAR(200) NOT NULL,
            source_course_code VARCHAR(50) NOT NULL,
            source_course_name VARCHAR(200) NOT NULL,
            source_credits DECIMAL(5,2) NOT NULL,
            target_course_id UUID,
            target_credits DECIMAL(5,2),
            equivalency_method VARCHAR(30) NOT NULL DEFAULT 'AI_DRAFT',
            ai_draft_json JSONB,
            committee_decision VARCHAR(20),
            committee_notes TEXT,
            decided_by UUID,
            decided_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            policy_version_id VARCHAR(80),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE credit_equivalency_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            credit_transfer_id UUID NOT NULL REFERENCES credit_transfer_requests(id),
            student_id UUID NOT NULL,
            source_course_code VARCHAR(50) NOT NULL,
            target_course_id UUID NOT NULL,
            credits_awarded DECIMAL(5,2) NOT NULL,
            grade_equivalency VARCHAR(5),
            locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            locked_by UUID NOT NULL,
            policy_version_id VARCHAR(80) NOT NULL
        )
    """)

    # Indexes for readmission_applications
    op.execute("CREATE INDEX idx_readmission_applications_org_id ON readmission_applications (org_id)")
    op.execute("CREATE INDEX idx_readmission_applications_status ON readmission_applications (status)")
    op.execute("CREATE INDEX idx_readmission_applications_new_student_id ON readmission_applications (new_student_id)")

    # Indexes for credit_transfer_requests
    op.execute("CREATE INDEX idx_credit_transfer_requests_org_student ON credit_transfer_requests (org_id, student_id)")
    op.execute("CREATE INDEX idx_credit_transfer_requests_readmission_id ON credit_transfer_requests (readmission_id)")
    op.execute("CREATE INDEX idx_credit_transfer_requests_status ON credit_transfer_requests (status)")

    # Indexes for credit_equivalency_records
    op.execute("CREATE INDEX idx_credit_equivalency_records_student_id ON credit_equivalency_records (student_id)")
    op.execute("CREATE INDEX idx_credit_equivalency_records_credit_transfer_id ON credit_equivalency_records (credit_transfer_id)")

    # Seed institution policies
    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'admissions.readmission_max_gap_years', '5'::jsonb, 'Maximum gap years allowed for re-admission', 'admissions'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'admissions.credit_transfer_max_pct', '50'::jsonb, 'Max % of program credits that can be transferred from other institutions', 'admissions'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    # Seed feature flags
    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, enabled, config)
        SELECT id, 'admissions.readmission_enabled', true, '{}'::jsonb
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, enabled, config)
        SELECT id, 'admissions.credit_transfer_ai_draft', true, '{}'::jsonb
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS credit_equivalency_records")
    op.execute("DROP TABLE IF EXISTS credit_transfer_requests")
    op.execute("DROP TABLE IF EXISTS readmission_applications")
