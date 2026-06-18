"""010 — add paid_until to accounts (₹2/yr signup fee, ADR-0011).

Revision ID: 010
Revises: 009
Create Date: 2026-06-19

The signup fee (₹2) is collected via Razorpay at signup; the account is "paid through" one year from
payment. ``paid_until`` records that date. Nullable — accounts created before the fee, or on deploys
with the fee disabled, simply have NULL.
"""

from __future__ import annotations

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts ADD COLUMN IF NOT EXISTS paid_until TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE quaicu_accounts DROP COLUMN IF EXISTS paid_until")
