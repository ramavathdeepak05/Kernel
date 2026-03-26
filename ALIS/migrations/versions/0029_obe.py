from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE program_outcomes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            program_id UUID NOT NULL,
            code VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,
            domain VARCHAR(30),
            nba_mapping VARCHAR(10),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, program_id, code)
        )
    """)

    op.execute("""
        CREATE TABLE course_outcomes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            course_id UUID NOT NULL,
            code VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,
            bloom_level VARCHAR(30),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, course_id, code)
        )
    """)

    op.execute("""
        CREATE TABLE co_po_mapping (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            course_id UUID NOT NULL,
            co_id UUID NOT NULL REFERENCES course_outcomes(id),
            po_id UUID NOT NULL REFERENCES program_outcomes(id),
            strength VARCHAR(5) NOT NULL DEFAULT 'M',
            justification TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(co_id, po_id),
            CHECK (strength IN ('H', 'M', 'L'))
        )
    """)

    op.execute("""
        CREATE TABLE assessment_rubrics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            course_id UUID NOT NULL,
            assessment_type VARCHAR(50) NOT NULL,
            co_id UUID NOT NULL REFERENCES course_outcomes(id),
            max_marks DECIMAL(6,2) NOT NULL,
            co_weight_pct DECIMAL(5,2) NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE attainment_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            program_id UUID NOT NULL,
            course_id UUID NOT NULL,
            semester_id UUID NOT NULL,
            co_id UUID NOT NULL REFERENCES course_outcomes(id),
            po_id UUID NOT NULL REFERENCES program_outcomes(id),
            students_assessed INTEGER NOT NULL DEFAULT 0,
            students_attained INTEGER NOT NULL DEFAULT 0,
            attainment_threshold_pct DECIMAL(5,2),
            attainment_pct DECIMAL(5,2),
            co_po_strength_weight DECIMAL(3,1),
            weighted_attainment DECIMAL(5,2),
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            policy_version_id VARCHAR(80)
        )
    """)

    # Indexes for program_outcomes
    op.execute("CREATE INDEX ix_program_outcomes_org_program ON program_outcomes (org_id, program_id)")

    # Indexes for course_outcomes
    op.execute("CREATE INDEX ix_course_outcomes_org_course ON course_outcomes (org_id, course_id)")

    # Indexes for co_po_mapping
    op.execute("CREATE INDEX ix_co_po_mapping_course_id ON co_po_mapping (course_id)")
    op.execute("CREATE INDEX ix_co_po_mapping_co_id ON co_po_mapping (co_id)")
    op.execute("CREATE INDEX ix_co_po_mapping_po_id ON co_po_mapping (po_id)")

    # Indexes for assessment_rubrics
    op.execute("CREATE INDEX ix_assessment_rubrics_course_co ON assessment_rubrics (course_id, co_id)")

    # Indexes for attainment_records
    op.execute("CREATE INDEX ix_attainment_records_org_program_semester ON attainment_records (org_id, program_id, semester_id)")
    op.execute("CREATE INDEX ix_attainment_records_co_po ON attainment_records (co_id, po_id)")

    # Seed policies
    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'obe.attainment_threshold_pct', '60'::jsonb, 'Minimum % of students required to attain CO for it to be considered achieved', 'academics'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies (org_id, key, value, description, category)
        SELECT id, 'obe.po_attainment_target', '70'::jsonb, 'Target PO attainment % for NBA accreditation', 'academics'
        FROM organizations
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    # Seed feature flag
    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, enabled, config)
        SELECT id, 'obe.enabled', true, '{}'::jsonb
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS attainment_records")
    op.execute("DROP TABLE IF EXISTS assessment_rubrics")
    op.execute("DROP TABLE IF EXISTS co_po_mapping")
    op.execute("DROP TABLE IF EXISTS course_outcomes")
    op.execute("DROP TABLE IF EXISTS program_outcomes")
