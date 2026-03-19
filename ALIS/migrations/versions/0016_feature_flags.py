"""Feature flags — institutional per-tenant feature flag system

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-15

Changes
───────
1. tenant_feature_flags table
   Stores per-tenant feature flag state (enabled/disabled) plus an
   optional JSONB config bag (e.g. {"tier": "medium"} for AI model
   tier flags).

   Flags are cached in Redis (key: alis:ff:{org_id}:{flag_key}, TTL 300s)
   and read from DB on cache miss.  Every feature that differs per
   institution MUST be gated behind a flag — no tenant-specific
   conditionals in application code.

   Flag key convention (dot-notation):
     module.feature_name        →  "academics.ai_ppt_generation"
     ai.capability.dimension    →  "ai.model_tier.drafting"
     compliance.requirement     →  "compliance.dpdp_strict_mode"

   Default flags are seeded by FeatureFlags.seed_defaults(org_id) on
   institution onboarding.
"""

from alembic import op

# revision identifiers
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS tenant_feature_flags (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,

        -- dot-notation key, e.g. "academics.ai_ppt_generation"
        flag_key    TEXT NOT NULL,

        -- master switch
        enabled     BOOLEAN NOT NULL DEFAULT false,

        -- optional parameters carried by this flag
        -- e.g. {"tier": "medium"} for AI model-tier flags
        config      JSONB NOT NULL DEFAULT '{}',

        -- actor who last modified
        updated_by  UUID,

        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ,

        CONSTRAINT uq_tenant_flag UNIQUE (org_id, flag_key)
    )
    """)

    # RLS — each tenant reads only its own flags
    op.execute("""
    ALTER TABLE tenant_feature_flags ENABLE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON tenant_feature_flags
        USING (org_id::text = current_setting('alis.current_tenant', true));
    """)

    # Composite index for the most common query: org_id + flag_key lookup
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_tff_org_flag
        ON tenant_feature_flags (org_id, flag_key);
    """)

    # Partial index — find all enabled flags per tenant quickly
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_tff_org_enabled
        ON tenant_feature_flags (org_id)
        WHERE enabled = true;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tff_org_enabled")
    op.execute("DROP INDEX IF EXISTS ix_tff_org_flag")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_feature_flags")
    op.execute("DROP TABLE IF EXISTS tenant_feature_flags")
