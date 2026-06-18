"""009 — add password hash + onboarding profile to accounts (console login, ADR-0011).

Revision ID: 009
Revises: 008
Create Date: 2026-06-18

``password_hash`` backs email+password console login (scrypt; see core/account/passwords). ``profile``
is the onboarding survey (use_case, industry, company_size, regulations) as JSON. Both nullable/default
so existing rows are unaffected.
"""

from __future__ import annotations

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS password_hash TEXT")
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS profile JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS profile")
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS password_hash")
