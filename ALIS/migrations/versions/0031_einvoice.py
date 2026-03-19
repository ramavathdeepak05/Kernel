from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    # 1. ALTER student_invoices — IRN / e-Invoice fields
    op.execute("""
        ALTER TABLE student_invoices ADD COLUMN IF NOT EXISTS irn VARCHAR(64);
    """)
    op.execute("""
        ALTER TABLE student_invoices ADD COLUMN IF NOT EXISTS irn_generated_at TIMESTAMPTZ;
    """)
    op.execute("""
        ALTER TABLE student_invoices ADD COLUMN IF NOT EXISTS irn_ack_no VARCHAR(64);
    """)
    op.execute("""
        ALTER TABLE student_invoices ADD COLUMN IF NOT EXISTS einvoice_payload JSONB;
    """)

    # 2. Index on IRN (partial — only rows where IRN is set)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_student_invoices_irn
            ON student_invoices(irn)
            WHERE irn IS NOT NULL;
    """)

    # 3. Seed feature flag — e-Invoice
    op.execute("""
        INSERT INTO tenant_feature_flags (org_id, flag_key, flag_value, description)
        SELECT id,
               'finance.einvoice_enabled',
               'false',
               'GST e-Invoice IRN generation via NIC API (enable for GST-registered institutions)'
        FROM organizations
        ON CONFLICT (org_id, flag_key) DO NOTHING;
    """)

    # 4. Seed policy — e-invoice threshold
    op.execute("""
        INSERT INTO institution_policies
            (org_id, policy_key, policy_value, policy_type, description, version, created_by)
        SELECT id,
               'finance.einvoice_threshold_inr',
               '500000',
               'DECIMAL',
               'Invoice amount threshold (INR) above which GST e-Invoice / IRN is required',
               1,
               NULL
        FROM organizations
        ON CONFLICT (org_id, policy_key) DO NOTHING;
    """)

    # 5. ALTER users — language_preference
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS language_preference VARCHAR(5) NOT NULL DEFAULT 'en';
    """)

    # Seed policy — supported languages
    op.execute("""
        INSERT INTO institution_policies
            (org_id, policy_key, policy_value, policy_type, description, version, created_by)
        SELECT id,
               'platform.supported_languages',
               '["en","te","kn","ta","mr","hi"]',
               'JSON',
               'Languages supported for student/parent facing UI',
               1,
               NULL
        FROM organizations
        ON CONFLICT (org_id, policy_key) DO NOTHING;
    """)


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS language_preference;")
    op.execute("ALTER TABLE student_invoices DROP COLUMN IF EXISTS einvoice_payload;")
    op.execute("ALTER TABLE student_invoices DROP COLUMN IF EXISTS irn_ack_no;")
    op.execute("ALTER TABLE student_invoices DROP COLUMN IF EXISTS irn_generated_at;")
    op.execute("ALTER TABLE student_invoices DROP COLUMN IF EXISTS irn;")
