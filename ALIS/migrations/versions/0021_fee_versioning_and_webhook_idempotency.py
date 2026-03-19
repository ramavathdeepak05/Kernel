"""Fee structure versioning + payment webhook idempotency

Revision ID: 0021
Revises: 0020
Create Date: 2026-03-15

Changes
───────
1. EC-FIN: fee_structures — intake_year lock
   Add intake_year (SMALLINT), is_locked (BOOLEAN), locked_at (TIMESTAMPTZ).
   A trigger locks the row permanently when the first invoice is issued against it,
   preventing retroactive edits that would corrupt enrolled students' fee records.

2. EC-ADM-05: payment_webhook_log
   Idempotency store for Razorpay (and future gateway) webhooks.
   UNIQUE(gateway, event_id) ensures each webhook fires exactly once even when
   the gateway retries after a timeout.

3. EC-ADM-05: payment_utr_disputes
   Lifecycle table for UTR-level payment disputes (wrong amount, failed bank
   transfer, duplicate debit).  Raised by Finance Officer, resolved with note.
"""

from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. fee_structures — intake_year lock columns
    # -------------------------------------------------------------------------
    op.execute("""
    ALTER TABLE fee_structures
        ADD COLUMN IF NOT EXISTS intake_year  SMALLINT,
        ADD COLUMN IF NOT EXISTS is_locked    BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS locked_at    TIMESTAMPTZ;

    -- Back-fill intake_year from academic_year string (e.g. "2025-26" → 2025)
    UPDATE fee_structures
       SET intake_year = CAST(SPLIT_PART(academic_year, '-', 1) AS SMALLINT)
     WHERE intake_year IS NULL
       AND academic_year ~ '^[0-9]{4}';

    CREATE INDEX IF NOT EXISTS idx_fee_structures_intake_year
        ON fee_structures(intake_year);
    """)

    # Trigger: lock the fee structure when the first invoice is generated against it
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_lock_fee_structure_on_invoice()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.fee_structure_id IS NOT NULL THEN
            UPDATE fee_structures
               SET is_locked = TRUE,
                   locked_at = NOW()
             WHERE id = NEW.fee_structure_id
               AND is_locked = FALSE;
        END IF;
        RETURN NEW;
    END;
    $$;

    DROP TRIGGER IF EXISTS trg_lock_fee_structure ON student_invoices;
    CREATE TRIGGER trg_lock_fee_structure
        AFTER INSERT ON student_invoices
        FOR EACH ROW EXECUTE FUNCTION fn_lock_fee_structure_on_invoice();
    """)

    # -------------------------------------------------------------------------
    # 2. payment_webhook_log — idempotency store (EC-ADM-05)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS payment_webhook_log (
        id              BIGSERIAL    PRIMARY KEY,
        gateway         VARCHAR(50)  NOT NULL,
        event_id        VARCHAR(200) NOT NULL,
        event_type      VARCHAR(100) NOT NULL,
        payload         JSONB        NOT NULL,
        status          VARCHAR(20)  NOT NULL DEFAULT 'RECEIVED',
        processed_at    TIMESTAMPTZ,
        error_detail    TEXT,
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_payment_webhook UNIQUE (gateway, event_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pwl_gateway_event
        ON payment_webhook_log(gateway, event_id);
    CREATE INDEX IF NOT EXISTS idx_pwl_status
        ON payment_webhook_log(status, created_at);
    """)

    # -------------------------------------------------------------------------
    # 3. payment_utr_disputes — UTR dispute lifecycle
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS payment_utr_disputes (
        id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID         NOT NULL REFERENCES organisations(id),
        payment_id      UUID         NOT NULL,
        utr_number      VARCHAR(100),
        disputed_amount DECIMAL(12,2) NOT NULL,
        reason          TEXT         NOT NULL,
        status          VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
        raised_by       UUID         REFERENCES users(id),
        resolved_by     UUID         REFERENCES users(id),
        raised_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        resolved_at     TIMESTAMPTZ,
        resolution_note TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_utr_disputes_org
        ON payment_utr_disputes(org_id, status);
    CREATE INDEX IF NOT EXISTS idx_utr_disputes_payment
        ON payment_utr_disputes(payment_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payment_utr_disputes;")
    op.execute("DROP TABLE IF EXISTS payment_webhook_log;")
    op.execute("DROP TRIGGER IF EXISTS trg_lock_fee_structure ON student_invoices;")
    op.execute("DROP FUNCTION IF EXISTS fn_lock_fee_structure_on_invoice();")
    op.execute("""
    ALTER TABLE fee_structures
        DROP COLUMN IF EXISTS locked_at,
        DROP COLUMN IF EXISTS is_locked,
        DROP COLUMN IF EXISTS intake_year;
    """)
