from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    # 1. ALTER organizations — group entity model
    op.execute("""
        ALTER TABLE organizations ADD COLUMN IF NOT EXISTS parent_org_id UUID REFERENCES organizations(id);
    """)
    op.execute("""
        ALTER TABLE organizations ADD COLUMN IF NOT EXISTS entity_type VARCHAR(20) NOT NULL DEFAULT 'STANDALONE';
    """)
    op.execute("""
        ALTER TABLE organizations ADD CONSTRAINT organizations_entity_type_check
            CHECK (entity_type IN ('STANDALONE', 'CAMPUS', 'GROUP'));
    """)

    # 2. New table: campus_entities
    op.execute("""
        CREATE TABLE IF NOT EXISTS campus_entities (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id            UUID        NOT NULL UNIQUE REFERENCES organizations(id),
            campus_code       VARCHAR(20) NOT NULL,
            campus_name       VARCHAR(200) NOT NULL,
            address           TEXT,
            city              VARCHAR(100),
            state             VARCHAR(100),
            pincode           VARCHAR(10),
            phone             VARCHAR(30),
            principal_user_id UUID,
            is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 3. New table: campus_user_assignments
    op.execute("""
        CREATE TABLE IF NOT EXISTS campus_user_assignments (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        UUID        NOT NULL,
            campus_org_id  UUID        NOT NULL REFERENCES organizations(id),
            role_scope     VARCHAR(30) NOT NULL DEFAULT 'CAMPUS_ONLY',
            assigned_by    UUID,
            assigned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, campus_org_id)
        );
    """)

    # Indexes — organizations
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_organizations_parent_org_id
            ON organizations(parent_org_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_organizations_entity_type
            ON organizations(entity_type);
    """)

    # Indexes — campus_entities
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_campus_entities_org_id
            ON campus_entities(org_id);
    """)

    # Indexes — campus_user_assignments
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_campus_user_assignments_user_id
            ON campus_user_assignments(user_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_campus_user_assignments_campus_org_id
            ON campus_user_assignments(campus_org_id);
    """)

    # Seed feature flag
    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, enabled, config)
        SELECT id,
               'platform.multi_campus_enabled',
               false,
               '{}'::jsonb
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS campus_user_assignments;")
    op.execute("DROP TABLE IF EXISTS campus_entities;")
    op.execute("""
        ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_entity_type_check;
    """)
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS entity_type;")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS parent_org_id;")
