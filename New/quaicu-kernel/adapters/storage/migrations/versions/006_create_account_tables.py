"""006 — create account + API-key tables (durable self-serve accounts, ADR-0010).

Revision ID: 006
Revises: 005
Create Date: 2026-06-17

Persists accounts and hashed API keys so self-serve signups survive a restart / scale-out (the
in-memory `AccountStore` is a cache hydrated from here at startup). Backs `PostgresAccountRepository`.

Like quaicu_customer_plans (migration 005), these are *control-plane* registries the app reads across
all tenants (auth resolves any key/tenant), so they are intentionally NOT under row-level security —
`load_all()` must see every tenant's records. Only HMAC-SHA256 hashes of key secrets are stored.
"""

from __future__ import annotations

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS quaicu_accounts (
            account_id   TEXT        NOT NULL,
            tenant_id    TEXT        NOT NULL,
            email        TEXT        NOT NULL,
            name         TEXT        NOT NULL,
            status       TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL,
            CONSTRAINT quaicu_accounts_pkey PRIMARY KEY (account_id),
            CONSTRAINT quaicu_accounts_email_key UNIQUE (email),
            CONSTRAINT quaicu_accounts_tenant_key UNIQUE (tenant_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS quaicu_api_keys (
            key_id         TEXT        NOT NULL,
            tenant_id      TEXT        NOT NULL,
            hashed_secret  TEXT        NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL,
            revoked        BOOLEAN     NOT NULL DEFAULT FALSE,
            scopes         JSONB       NOT NULL DEFAULT '[]',
            CONSTRAINT quaicu_api_keys_pkey PRIMARY KEY (key_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS quaicu_api_keys_tenant ON quaicu_api_keys (tenant_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quaicu_api_keys")
    op.execute("DROP TABLE IF EXISTS quaicu_accounts")
