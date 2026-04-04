"""
0042 — AI Provider Configs (per-tenant AI API extensibility)

Enables institutions to bring their own AI API keys and providers.
Each tenant can configure one or more AI providers (OpenAI, Anthropic,
Azure, Google, or any OpenAI-compatible API).

Revision ID: 0042
Revises: 0041
"""
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_provider_configs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       VARCHAR(64) NOT NULL,
            provider_type   VARCHAR(32) NOT NULL,   -- openai, azure_openai, anthropic, google, ollama, openai_compat
            display_name    VARCHAR(128) NOT NULL DEFAULT '',
            api_key_encrypted TEXT NOT NULL DEFAULT '',
            api_base_url    TEXT NOT NULL DEFAULT '',
            model_name      VARCHAR(128) NOT NULL DEFAULT '',
            max_tokens      INTEGER NOT NULL DEFAULT 2048,
            temperature     NUMERIC(3,2) NOT NULL DEFAULT 0.20,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            azure_deployment VARCHAR(128) NOT NULL DEFAULT '',
            azure_api_version VARCHAR(32) NOT NULL DEFAULT '2024-02-01',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_ai_provider_configs_tenant
            ON ai_provider_configs(tenant_id, is_active);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_provider_configs;")
