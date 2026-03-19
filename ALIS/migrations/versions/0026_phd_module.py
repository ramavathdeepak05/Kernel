from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phd_registrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            student_id UUID NOT NULL,
            supervisor_id UUID NOT NULL,
            co_supervisor_id UUID,
            program_id UUID NOT NULL,
            research_area TEXT NOT NULL,
            registration_date DATE NOT NULL,
            expected_completion DATE,
            status VARCHAR(40) NOT NULL DEFAULT 'REGISTERED',
            policy_version_id VARCHAR(80),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE phd_milestones (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            phd_id UUID NOT NULL REFERENCES phd_registrations(id),
            milestone_type VARCHAR(60) NOT NULL,
            due_date TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            completed_by UUID,
            notes TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE phd_dc_meetings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            phd_id UUID NOT NULL REFERENCES phd_registrations(id),
            scheduled_at TIMESTAMPTZ NOT NULL,
            held_at TIMESTAMPTZ,
            committee_members JSONB NOT NULL DEFAULT '[]',
            agenda TEXT,
            minutes TEXT,
            outcome VARCHAR(30),
            next_meeting_due TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE phd_plagiarism_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            phd_id UUID NOT NULL REFERENCES phd_registrations(id),
            document_url TEXT NOT NULL,
            similarity_pct DECIMAL(5,2),
            provider VARCHAR(40) DEFAULT 'DRILLBIT',
            threshold_pct DECIMAL(5,2),
            policy_version_id VARCHAR(80),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE phd_thesis_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            phd_id UUID NOT NULL REFERENCES phd_registrations(id),
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            thesis_document_url TEXT NOT NULL,
            examiner_1_id UUID,
            examiner_2_id UUID,
            external_examiner_id UUID,
            viva_scheduled_at TIMESTAMPTZ,
            viva_outcome VARCHAR(30),
            final_approval_at TIMESTAMPTZ,
            approved_by UUID,
            status VARCHAR(30) NOT NULL DEFAULT 'SUBMITTED',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Indexes — phd_registrations
    op.execute("CREATE INDEX idx_phd_registrations_org_id ON phd_registrations (org_id)")
    op.execute("CREATE INDEX idx_phd_registrations_student_id ON phd_registrations (student_id)")
    op.execute("CREATE INDEX idx_phd_registrations_supervisor_id ON phd_registrations (supervisor_id)")
    op.execute("CREATE INDEX idx_phd_registrations_status ON phd_registrations (status)")

    # Indexes — phd_milestones
    op.execute("CREATE INDEX idx_phd_milestones_phd_id ON phd_milestones (phd_id)")
    op.execute("CREATE INDEX idx_phd_milestones_status ON phd_milestones (status)")

    # Indexes — phd_dc_meetings
    op.execute("CREATE INDEX idx_phd_dc_meetings_phd_id ON phd_dc_meetings (phd_id)")
    op.execute("CREATE INDEX idx_phd_dc_meetings_scheduled_at ON phd_dc_meetings (scheduled_at)")

    # Indexes — phd_plagiarism_reports
    op.execute("CREATE INDEX idx_phd_plagiarism_reports_phd_id ON phd_plagiarism_reports (phd_id)")

    # Indexes — phd_thesis_submissions
    op.execute("CREATE INDEX idx_phd_thesis_submissions_phd_id ON phd_thesis_submissions (phd_id)")

    # Feature flag seeds
    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, flag_value, description)
        SELECT id, 'phd.enabled', 'true', 'E15 PhD/Doctoral module'
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, flag_value, description)
        SELECT id, 'phd.plagiarism_check_required', 'true', 'Require Drillbit plagiarism check before thesis submission'
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING
    """)

    # Default policy seeds
    op.execute("""
        INSERT INTO institution_policies (org_id, policy_key, policy_value, policy_type, description, version, created_by)
        SELECT id, 'phd.plagiarism_max_pct', '25', 'DECIMAL', 'Maximum allowed similarity percentage for PhD thesis (Drillbit)', 1, NULL
        FROM organizations
        ON CONFLICT (org_id, policy_key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies (org_id, policy_key, policy_value, policy_type, description, version, created_by)
        SELECT id, 'phd.supervisor_max_scholars', '8', 'INTEGER', 'Maximum PhD scholars per supervisor', 1, NULL
        FROM organizations
        ON CONFLICT (org_id, policy_key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies (org_id, policy_key, policy_value, policy_type, description, version, created_by)
        SELECT id, 'phd.dc_meeting_interval_months', '6', 'INTEGER', 'Months between mandatory DC committee meetings', 1, NULL
        FROM organizations
        ON CONFLICT (org_id, policy_key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS phd_thesis_submissions")
    op.execute("DROP TABLE IF EXISTS phd_plagiarism_reports")
    op.execute("DROP TABLE IF EXISTS phd_dc_meetings")
    op.execute("DROP TABLE IF EXISTS phd_milestones")
    op.execute("DROP TABLE IF EXISTS phd_registrations")
