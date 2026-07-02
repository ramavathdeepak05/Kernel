"""015 — member password hash (in-browser console login for members, D1-5).

Adds `password_hash` to `quaicu_members` so an invited member (e.g. a COMPLIANCE checker) can set a
password via the emailed set-password link and log into the console to approve — not only via API key.
Additive + nullable (IdP/SCIM members leave it NULL and authenticate via their IdP token).

Revision ID: 015
Revises: 014
Create Date: 2026-07-02
"""

from __future__ import annotations

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE quaicu_members ADD COLUMN IF NOT EXISTS password_hash TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE quaicu_members DROP COLUMN IF EXISTS password_hash")
