"""MFA devices and trusted devices tables

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-15

Adds:
  - mfa_devices        : TOTP secrets (encrypted at rest) + backup codes per user
  - trusted_devices    : 30-day device-trust skip for MFA re-prompt
  - RLS policies on both tables scoped to alis.current_tenant
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # mfa_devices
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS mfa_devices (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_name     TEXT NOT NULL DEFAULT 'Authenticator App',
            totp_secret     TEXT NOT NULL,
            backup_codes    TEXT[] NOT NULL DEFAULT '{}',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at    TIMESTAMPTZ,
            CONSTRAINT uq_mfa_user_device UNIQUE (org_id, user_id, device_name)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mfa_devices_org_user
            ON mfa_devices (org_id, user_id)
    """)

    # Row-Level Security
    op.execute("ALTER TABLE mfa_devices ENABLE ROW LEVEL SECURITY")

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'mfa_devices' AND policyname = 'mfa_devices_tenant_isolation'
            ) THEN
                CREATE POLICY mfa_devices_tenant_isolation ON mfa_devices
                    USING (org_id = current_setting('alis.current_tenant', TRUE));
            END IF;
        END
        $$
    """)

    # ------------------------------------------------------------------
    # trusted_devices
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS trusted_devices (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_hash     TEXT NOT NULL,
            trusted_until   TIMESTAMPTZ NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_trusted_device UNIQUE (org_id, user_id, device_hash)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_trusted_devices_org_user
            ON trusted_devices (org_id, user_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_trusted_devices_expiry
            ON trusted_devices (trusted_until)
    """)

    # Row-Level Security
    op.execute("ALTER TABLE trusted_devices ENABLE ROW LEVEL SECURITY")

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'trusted_devices' AND policyname = 'trusted_devices_tenant_isolation'
            ) THEN
                CREATE POLICY trusted_devices_tenant_isolation ON trusted_devices
                    USING (org_id = current_setting('alis.current_tenant', TRUE));
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trusted_devices CASCADE")
    op.execute("DROP TABLE IF EXISTS mfa_devices CASCADE")
