"""Autonomous admissions — policy store, review queue, org API keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-05
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E04-S10 — Institution Policy Store
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS institution_policies (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       JSONB NOT NULL,
        description TEXT,
        category    TEXT NOT NULL DEFAULT 'general',
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        updated_by  TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ,
        UNIQUE(org_id, key)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_policies_org_cat ON institution_policies(org_id, category)")

    op.execute("ALTER TABLE institution_policies ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DROP POLICY IF EXISTS institution_policies_tenant_isolation ON institution_policies;
            CREATE POLICY institution_policies_tenant_isolation
        ON institution_policies
        USING (org_id::text = current_setting('alis.current_tenant', TRUE))
    """)

    # -------------------------------------------------------------------------
    # E04-S12 — Review Queue
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS review_items (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        entity_type     TEXT NOT NULL,
        entity_id       TEXT NOT NULL,
        reason          TEXT NOT NULL,
        flags           JSONB NOT NULL DEFAULT '[]',
        policy_key      TEXT,
        policy_value    JSONB,
        actual_value    JSONB,
        status          TEXT NOT NULL DEFAULT 'PENDING',
        decision        TEXT,
        decided_by      TEXT,
        decided_at      TIMESTAMPTZ,
        decision_note   TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_review_org_status ON review_items(org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_review_entity ON review_items(entity_type, entity_id)")

    op.execute("ALTER TABLE review_items ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DROP POLICY IF EXISTS review_items_tenant_isolation ON review_items;
            CREATE POLICY review_items_tenant_isolation
        ON review_items
        USING (org_id::text = current_setting('alis.current_tenant', TRUE))
    """)

    # -------------------------------------------------------------------------
    # E04-S14 — Org API Keys (public intake authentication)
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS org_api_keys (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      TEXT NOT NULL,
        key_hash    TEXT NOT NULL UNIQUE,
        label       TEXT NOT NULL,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        created_by  TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_used_at TIMESTAMPTZ
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_org ON org_api_keys(org_id)")


def downgrade() -> None:
    for t in ["org_api_keys", "review_items", "institution_policies"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
