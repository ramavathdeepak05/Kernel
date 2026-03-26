from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE convocation_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            title VARCHAR(200) NOT NULL,
            ceremony_date DATE NOT NULL,
            venue VARCHAR(300),
            academic_year VARCHAR(20) NOT NULL,
            batch_year INTEGER NOT NULL,
            chief_guest VARCHAR(200),
            status VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE convocation_degree_audits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            convocation_id UUID NOT NULL REFERENCES convocation_events(id),
            student_id UUID NOT NULL,
            program_id UUID NOT NULL,
            total_credits_required DECIMAL(6,2),
            total_credits_earned DECIMAL(6,2),
            cgpa DECIMAL(4,2),
            cgpa_without_grace DECIMAL(4,2),
            backlogs_pending INTEGER NOT NULL DEFAULT 0,
            dues_cleared BOOLEAN NOT NULL DEFAULT FALSE,
            eligible_for_degree BOOLEAN NOT NULL DEFAULT FALSE,
            eligible_for_distinction BOOLEAN NOT NULL DEFAULT FALSE,
            eligible_for_gold_medal BOOLEAN NOT NULL DEFAULT FALSE,
            audit_notes TEXT,
            audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            audited_by UUID,
            policy_version_id VARCHAR(80)
        )
    """)

    op.execute("""
        CREATE TABLE convocation_seating (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            convocation_id UUID NOT NULL REFERENCES convocation_events(id),
            student_id UUID NOT NULL,
            seat_number VARCHAR(20) NOT NULL,
            row_label VARCHAR(10),
            section VARCHAR(50),
            program_id UUID NOT NULL,
            certificate_printed BOOLEAN NOT NULL DEFAULT FALSE,
            certificate_url TEXT,
            attended BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE gold_medal_computations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            convocation_id UUID NOT NULL REFERENCES convocation_events(id),
            program_id UUID NOT NULL,
            winner_student_id UUID NOT NULL,
            cgpa_without_grace DECIMAL(4,2) NOT NULL,
            computation_notes TEXT,
            policy_version_id VARCHAR(80) NOT NULL,
            approved_by UUID,
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Indexes for convocation_events
    op.execute("CREATE INDEX ix_convocation_events_org_id ON convocation_events (org_id)")
    op.execute("CREATE INDEX ix_convocation_events_status ON convocation_events (status)")
    op.execute("CREATE INDEX ix_convocation_events_ceremony_date ON convocation_events (ceremony_date)")

    # Indexes for convocation_degree_audits
    op.execute("CREATE INDEX ix_convocation_degree_audits_convocation_id ON convocation_degree_audits (convocation_id)")
    op.execute("CREATE INDEX ix_convocation_degree_audits_student_id ON convocation_degree_audits (student_id)")
    op.execute("CREATE INDEX ix_convocation_degree_audits_eligible_for_degree ON convocation_degree_audits (eligible_for_degree)")

    # Indexes for convocation_seating
    op.execute("CREATE INDEX ix_convocation_seating_convocation_student ON convocation_seating (convocation_id, student_id)")
    op.execute("CREATE INDEX ix_convocation_seating_seat_number ON convocation_seating (seat_number)")

    # Indexes for gold_medal_computations
    op.execute("CREATE INDEX ix_gold_medal_computations_convocation_program ON gold_medal_computations (convocation_id, program_id)")

    # Seed policies
    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'convocation.distinction_cgpa_threshold', '8.5'::jsonb, 'Minimum CGPA for distinction at convocation', 'academics'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'convocation.gold_medal_exclude_grace', 'true'::jsonb, 'Exclude grace marks from gold medal CGPA computation', 'academics'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS gold_medal_computations")
    op.execute("DROP TABLE IF EXISTS convocation_seating")
    op.execute("DROP TABLE IF EXISTS convocation_degree_audits")
    op.execute("DROP TABLE IF EXISTS convocation_events")
