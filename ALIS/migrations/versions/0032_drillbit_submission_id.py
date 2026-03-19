from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    # Add Drillbit submission tracking columns to phd_plagiarism_reports
    op.execute("""
        ALTER TABLE phd_plagiarism_reports
        ADD COLUMN IF NOT EXISTS drillbit_submission_id VARCHAR(120),
        ADD COLUMN IF NOT EXISTS submitted_by UUID,
        ADD COLUMN IF NOT EXISTS checked_by UUID,
        ADD COLUMN IF NOT EXISTS report_url TEXT,
        ADD COLUMN IF NOT EXISTS similarity_details JSONB
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_phd_plagiarism_reports_drillbit_submission_id
        ON phd_plagiarism_reports (drillbit_submission_id)
        WHERE drillbit_submission_id IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_phd_plagiarism_reports_status_pending
        ON phd_plagiarism_reports (org_id, status)
        WHERE status = 'PENDING'
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_phd_plagiarism_reports_drillbit_submission_id")
    op.execute("DROP INDEX IF EXISTS idx_phd_plagiarism_reports_status_pending")
    op.execute("""
        ALTER TABLE phd_plagiarism_reports
        DROP COLUMN IF EXISTS drillbit_submission_id,
        DROP COLUMN IF EXISTS submitted_by,
        DROP COLUMN IF EXISTS checked_by,
        DROP COLUMN IF EXISTS report_url,
        DROP COLUMN IF EXISTS similarity_details
    """)
