"""Finance module (M4)

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-05
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E07-S01 — Fee Structures
    # org_id + program_id + academic_year + semester = one canonical fee structure
    # fee_items is a JSONB array: [{label, amount, fee_type, is_optional}]
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS fee_structures (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        program_id      UUID REFERENCES programs(id),
        academic_year   TEXT NOT NULL,
        semester        INT,                         -- NULL = annual (all semesters)
        fee_items       JSONB NOT NULL DEFAULT '[]',
        total_amount    DECIMAL(12,2) NOT NULL DEFAULT 0,
        currency        TEXT NOT NULL DEFAULT 'INR',
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(org_id, program_id, academic_year, semester)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_fee_structure_org ON fee_structures(org_id, academic_year)")

    # -------------------------------------------------------------------------
    # E07-S02 — Student Invoices
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS student_invoices (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        fee_structure_id UUID REFERENCES fee_structures(id),
        academic_year   TEXT NOT NULL,
        semester        INT,
        invoice_number  TEXT NOT NULL UNIQUE,
        amount_due      DECIMAL(12,2) NOT NULL,
        amount_paid     DECIMAL(12,2) NOT NULL DEFAULT 0,
        discount        DECIMAL(12,2) NOT NULL DEFAULT 0,  -- scholarships + waivers
        balance         DECIMAL(12,2) GENERATED ALWAYS AS (amount_due - amount_paid - discount) STORED,
        currency        TEXT NOT NULL DEFAULT 'INR',
        due_date        DATE NOT NULL,
        status          TEXT NOT NULL DEFAULT 'UNPAID',  -- UNPAID | PARTIAL | PAID | OVERDUE | WAIVED
        generated_by    TEXT NOT NULL,
        generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        paid_at         TIMESTAMPTZ,
        notes           TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_invoice_student ON student_invoices(student_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_invoice_status ON student_invoices(org_id, status)")

    # -------------------------------------------------------------------------
    # E07-S03/S04 — Payments (Razorpay + Manual)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id              TEXT NOT NULL,
        student_id          UUID NOT NULL REFERENCES students(id),
        invoice_id          UUID NOT NULL REFERENCES student_invoices(id),
        amount              DECIMAL(12,2) NOT NULL,
        currency            TEXT NOT NULL DEFAULT 'INR',
        method              TEXT NOT NULL,  -- RAZORPAY | CASH | CHEQUE | DD | NEFT | UPI
        status              TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | CAPTURED | FAILED | REFUNDED
        -- Razorpay fields
        razorpay_order_id   TEXT,
        razorpay_payment_id TEXT,
        razorpay_signature  TEXT,
        -- Manual payment fields
        reference_number    TEXT,
        bank_name           TEXT,
        cheque_date         DATE,
        -- Metadata
        recorded_by         TEXT,
        recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        notes               TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id, org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payments_razorpay ON payments(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL")

    # -------------------------------------------------------------------------
    # E07-S05 — Scholarships
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS scholarships (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        name            TEXT NOT NULL,
        description     TEXT,
        type            TEXT NOT NULL DEFAULT 'MERIT',  -- MERIT | NEED | SPORTS | GOVT | INSTITUTIONAL
        discount_type   TEXT NOT NULL DEFAULT 'PERCENTAGE',  -- PERCENTAGE | FIXED
        discount_value  DECIMAL(10,2) NOT NULL,
        academic_year   TEXT NOT NULL,
        max_recipients  INT,
        criteria        JSONB,  -- {min_cgpa, income_limit, category, etc.}
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS scholarship_assignments (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        scholarship_id  UUID NOT NULL REFERENCES scholarships(id),
        student_id      UUID NOT NULL REFERENCES students(id),
        academic_year   TEXT NOT NULL,
        amount_applied  DECIMAL(12,2) NOT NULL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | SUSPENDED | EXPIRED
        assigned_by     TEXT NOT NULL,
        assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(scholarship_id, student_id, academic_year)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_student ON scholarship_assignments(student_id, academic_year)")

    # -------------------------------------------------------------------------
    # E07-S06 — Fee Waivers
    # Routes through E02 approval engine
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS fee_waivers (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        invoice_id      UUID NOT NULL REFERENCES student_invoices(id),
        waiver_type     TEXT NOT NULL DEFAULT 'PARTIAL',  -- PARTIAL | FULL
        waiver_amount   DECIMAL(12,2) NOT NULL,
        reason          TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | APPROVED | REJECTED
        requested_by    TEXT NOT NULL,
        requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        approved_by     TEXT,
        approved_at     TIMESTAMPTZ,
        rejection_note  TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_waivers_student ON fee_waivers(student_id, org_id)")

    # -------------------------------------------------------------------------
    # RLS
    # -------------------------------------------------------------------------
    for table in ["fee_structures", "student_invoices", "payments",
                  "scholarships", "scholarship_assignments", "fee_waivers"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in ["fee_waivers", "scholarship_assignments", "scholarships",
              "payments", "student_invoices", "fee_structures"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
