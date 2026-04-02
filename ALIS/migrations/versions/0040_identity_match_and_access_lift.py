"""EC-ADM-01 + EC-ADM-05 compliance gaps

Revision ID: 0040
Revises: 0039
Create Date: 2026-03-27

Changes
───────
1. EC-ADM-01 — Identity mismatch columns on `applications`
   Add aadhaar_name, jee_name, name_variants (JSONB), kyc_status.
   The IdentityMatchService compares these names with Jaro-Winkler (≥0.85)
   and routes to KYC_RECONCILIATION when any pair falls below threshold.

2. EC-ADM-05 — access_lifted_until on `payment_utr_disputes`
   When a UTR dispute is raised the system temporarily lifts access
   restrictions for 48 hours while the payment is being verified.
   access_lifted_until = NOW() + '48 hours'. A Celery task expires these.
"""

from alembic import op


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. EC-ADM-01 — identity match columns on applications
    # -------------------------------------------------------------------------
    op.execute("""
    ALTER TABLE applicants
        ADD COLUMN IF NOT EXISTS aadhaar_name       VARCHAR(300),
        ADD COLUMN IF NOT EXISTS jee_name           VARCHAR(300),
        ADD COLUMN IF NOT EXISTS name_variants      JSONB,
        ADD COLUMN IF NOT EXISTS kyc_status         VARCHAR(30)
            CHECK (kyc_status IN (
                'NOT_CHECKED', 'MATCHED', 'KYC_RECONCILIATION', 'CLEARED'
            )) DEFAULT 'NOT_CHECKED';

    -- Index for the KYC reconciliation queue (officers pull this view)
    CREATE INDEX IF NOT EXISTS idx_applications_kyc_status
        ON applicants(org_id, kyc_status)
        WHERE kyc_status = 'KYC_RECONCILIATION';
    """)

    # -------------------------------------------------------------------------
    # 2. EC-ADM-05 — access_lifted_until on payment_utr_disputes
    # -------------------------------------------------------------------------
    op.execute("""
    ALTER TABLE payment_utr_disputes
        ADD COLUMN IF NOT EXISTS access_lifted_until TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS access_expired      BOOLEAN NOT NULL DEFAULT FALSE;

    -- Index for the Celery expiry task (runs every 30 minutes)
    CREATE INDEX IF NOT EXISTS idx_utr_disputes_access_lift
        ON payment_utr_disputes(access_lifted_until)
        WHERE access_lifted_until IS NOT NULL AND access_expired = FALSE;
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS idx_utr_disputes_access_lift;
    ALTER TABLE payment_utr_disputes
        DROP COLUMN IF EXISTS access_expired,
        DROP COLUMN IF EXISTS access_lifted_until;
    """)

    op.execute("""
    DROP INDEX IF EXISTS idx_applications_kyc_status;
    ALTER TABLE applicants
        DROP COLUMN IF EXISTS kyc_status,
        DROP COLUMN IF EXISTS name_variants,
        DROP COLUMN IF EXISTS jee_name,
        DROP COLUMN IF EXISTS aadhaar_name;
    """)
