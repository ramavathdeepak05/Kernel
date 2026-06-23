"""011 — create members table + api_keys.member_id (enterprise RBAC / SCIM, W6-1).

Revision ID: 011
Revises: 010
Create Date: 2026-06-23

Adds multi-user support to a tenant. `quaicu_members` holds the users an admin invites or an enterprise
IdP provisions over SCIM 2.0; each carries a `role` (see core/account/roles.py). Like the other
control-plane registries (accounts/api_keys), it is intentionally NOT under RLS — `load_members()`
hydrates the cache across all tenants and auth resolves any member/tenant.

`quaicu_api_keys.member_id` binds a key to a member so deactivating that member (SCIM `active=false` /
console deactivate) revokes their keys — the deprovisioning guarantee. Nullable/empty for the legacy
bootstrap/tenant key, which is unaffected.
"""

from __future__ import annotations

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS quaicu_members (
            member_id    TEXT        NOT NULL,
            tenant_id    TEXT        NOT NULL,
            email        TEXT        NOT NULL,
            display_name TEXT        NOT NULL DEFAULT '',
            role         TEXT        NOT NULL,
            status       TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL,
            external_id  TEXT        NOT NULL DEFAULT '',
            CONSTRAINT quaicu_members_pkey PRIMARY KEY (member_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS quaicu_members_tenant ON quaicu_members (tenant_id)")
    # Unique per tenant: at most one member per email, and one per SCIM external_id (when present).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS quaicu_members_tenant_email "
        "ON quaicu_members (tenant_id, lower(email))"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS quaicu_members_tenant_extid "
        "ON quaicu_members (tenant_id, external_id) WHERE external_id <> ''"
    )
    op.execute("ALTER TABLE quaicu_api_keys ADD COLUMN IF NOT EXISTS member_id TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE quaicu_api_keys DROP COLUMN IF EXISTS member_id")
    op.execute("DROP TABLE IF EXISTS quaicu_members")
