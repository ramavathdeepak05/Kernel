"""EC-FIN-01 — DBT Exemption + EC-FIN-02 — Promissory Note Ledger

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-16

Changes
───────
1. EC-FIN-01: student_fee_exemptions
   Government DBT exemptions (NSP, state portals) and management waivers.
   Active exemption pauses escalation — does NOT waive the fee itself.
   Default validity: 180 days (configurable via institution_policies).
   Dual-approval (second_approver) required for MANAGEMENT_WAIVER > ₹50,000.

2. EC-FIN-02: fee_payment_components
   Multi-source payment component ledger — direct payments, DDs, loan tranches,
   scholarship credits, and promissory notes.  Sum of all non-MISSED components
   must >= invoice amount for student to be considered NOT a defaulter.

3. student_dues_status (view)
   Read model consumed by examination hall-ticket block and defaulter reports.
   Carries exemption_active, promissory_cover_active, and total_covered.
"""

from alembic import op


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. EC-FIN-01 — student_fee_exemptions
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS student_fee_exemptions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        invoice_id      UUID REFERENCES student_invoices(id),
        exemption_type  VARCHAR(50) NOT NULL,
        reason          TEXT NOT NULL,
        valid_from      DATE NOT NULL DEFAULT CURRENT_DATE,
        valid_until     DATE NOT NULL,
        status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        approved_by     UUID REFERENCES users(id),
        second_approver UUID REFERENCES users(id),
        revoked_by      UUID REFERENCES users(id),
        revoked_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_exemption_student_invoice
            UNIQUE (org_id, student_id, invoice_id, exemption_type)
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_fee_exempt_student
        ON student_fee_exemptions(student_id, status, valid_until)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_fee_exempt_org_active
        ON student_fee_exemptions(org_id, status, valid_until)
    """)

    # -------------------------------------------------------------------------
    # 2. EC-FIN-02 — fee_payment_components
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS fee_payment_components (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id          UUID NOT NULL,
        invoice_id      UUID NOT NULL REFERENCES student_invoices(id),
        student_id      UUID NOT NULL REFERENCES students(id),
        component_type  VARCHAR(30) NOT NULL,
        amount          DECIMAL(12,2) NOT NULL,
        expected_date   DATE,
        received_date   DATE,
        reference_no    VARCHAR(200),
        status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        created_by      UUID REFERENCES users(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_fee_components_invoice
        ON fee_payment_components(invoice_id)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_fee_components_student
        ON fee_payment_components(student_id, component_type)
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_fee_components_expected
        ON fee_payment_components(expected_date, status)
    """)

    # -------------------------------------------------------------------------
    # 3. student_dues_status — read model view
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE OR REPLACE VIEW student_dues_status AS
    SELECT
        si.student_id,
        si.org_id,
        si.id AS invoice_id,
        si.academic_year,
        si.amount_due,
        si.amount_paid,
        si.balance,
        si.status AS invoice_status,
        si.due_date,
        -- Exemption active?
        EXISTS (
            SELECT 1 FROM student_fee_exemptions e
            WHERE e.student_id::text = si.student_id::text
              AND e.org_id::text = si.org_id::text
              AND e.status = 'ACTIVE'
              AND e.valid_until >= CURRENT_DATE
              AND (e.invoice_id IS NULL OR e.invoice_id::text = si.id::text)
        ) AS exemption_active,
        -- Promissory cover sufficient?
        (
            COALESCE((
                SELECT SUM(fc.amount)
                FROM fee_payment_components fc
                WHERE fc.invoice_id = si.id
                  AND fc.component_type = 'PROMISSORY'
                  AND fc.status IN ('PENDING', 'CONFIRMED')
                  AND (fc.expected_date IS NULL OR fc.expected_date >= CURRENT_DATE)
            ), 0) + si.amount_paid >= si.amount_due
        ) AS promissory_cover_active,
        -- Total component coverage (all non-MISSED components + direct payments)
        COALESCE((
            SELECT SUM(fc.amount)
            FROM fee_payment_components fc
            WHERE fc.invoice_id = si.id
              AND fc.status != 'MISSED'
        ), 0) + si.amount_paid AS total_covered
    FROM student_invoices si
    """)

    # -------------------------------------------------------------------------
    # 4. RLS on new tables
    # -------------------------------------------------------------------------
    for table in ["student_fee_exemptions", "fee_payment_components"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS student_dues_status")
    op.execute("DROP TABLE IF EXISTS fee_payment_components CASCADE")
    op.execute("DROP TABLE IF EXISTS student_fee_exemptions CASCADE")
