"""008 — add professional contact fields to accounts (verified signup, ADR-0010).

Revision ID: 008
Revises: 007
Create Date: 2026-06-18

The verified-signup form collects the person's name, job title, and phone alongside the company name
(stored in ``name``) and company email. Nullable so existing rows are unaffected; the repository
COALESCEs NULL → '' on read.
"""

from __future__ import annotations

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS full_name TEXT")
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS job_title TEXT")
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS phone TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS job_title")
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS full_name")
