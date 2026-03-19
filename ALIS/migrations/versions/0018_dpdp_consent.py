"""E21 DPDP Consent Management — consent_records + erasure_requests

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-15

Changes
───────
1. consent_records — per-user per-purpose consent tracking (DPDP Act 2023)
   One row per (org_id, user_id, purpose) with UPSERT semantics.
   Status lifecycle: PENDING → GIVEN → WITHDRAWN | EXPIRED
   Purposes: ADMISSIONS | ACADEMICS | FINANCE | HR | COMMUNICATIONS | ANALYTICS | ALL

2. erasure_requests — right-to-erasure request lifecycle
   Tracks module-by-module erasure progress.
   Status lifecycle: PENDING → IN_PROGRESS → COMPLETED | REJECTED
   due_by = request_date + 30 days (DPDP Act compliance window)

RLS policies on both tables scoped to org_id = current_setting('alis.current_tenant', true).
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────────
    # 1. consent_records
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS consent_records (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        purpose         TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING',
        given_at        TIMESTAMPTZ,
        withdrawn_at    TIMESTAMPTZ,
        expires_at      TIMESTAMPTZ,
        ip_address      INET,
        user_agent      TEXT,
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_consent UNIQUE (org_id, user_id, purpose)
    )
    """)

    op.execute("""
    ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON consent_records
        USING (org_id = current_setting('alis.current_tenant', true));
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_consent_org_user
        ON consent_records (org_id, user_id);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_consent_org_user_purpose
        ON consent_records (org_id, user_id, purpose);
    """)

    # ─────────────────────────────────────────────────────────────────
    # 2. erasure_requests
    # ─────────────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS erasure_requests (
        id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id           TEXT NOT NULL,
        user_id          UUID NOT NULL,
        requested_by     UUID NOT NULL,
        reason           TEXT,
        status           TEXT NOT NULL DEFAULT 'PENDING',
        modules_queued   TEXT[] NOT NULL DEFAULT '{}',
        modules_done     TEXT[] NOT NULL DEFAULT '{}',
        due_by           TIMESTAMPTZ NOT NULL,
        completed_at     TIMESTAMPTZ,
        rejected_at      TIMESTAMPTZ,
        rejection_reason TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    ALTER TABLE erasure_requests ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON erasure_requests
        USING (org_id = current_setting('alis.current_tenant', true));
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_erasure_org_user
        ON erasure_requests (org_id, user_id);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_erasure_status
        ON erasure_requests (status)
        WHERE status IN ('PENDING', 'IN_PROGRESS');
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS erasure_requests")
    op.execute("DROP TABLE IF EXISTS consent_records")
