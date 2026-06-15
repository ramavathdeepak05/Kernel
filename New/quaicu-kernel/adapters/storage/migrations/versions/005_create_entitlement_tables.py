"""005 — create customer-plan table (durable entitlement store, ADR-0009 / WS-C).

Revision ID: 005
Revises: 004
Create Date: 2026-06-16

Persists one `CustomerPlan` per tenant so a restarted kernel resolves the same tiers and a
billing-driven tier flip survives a redeploy. Backs `PostgresEntitlementRepository`.

Note: this is a *control-plane* registry the app reads across all tenants (it resolves any tenant's
plan to route/gate requests), so — unlike the tenant-scoped data tables hardened in migration 004 —
it is intentionally NOT under row-level security; `load_all()` must see every tenant's plan.
"""

from __future__ import annotations

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS quaicu_customer_plans (
            tenant_id         TEXT        NOT NULL,
            tier              TEXT        NOT NULL,
            status            TEXT        NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL,
            updated_at        TIMESTAMPTZ NOT NULL,
            billing_provider  TEXT,
            billing_ref       TEXT,
            quota_overrides   JSONB       NOT NULL DEFAULT '{}',
            CONSTRAINT quaicu_customer_plans_pkey PRIMARY KEY (tenant_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS quaicu_customer_plans_status
            ON quaicu_customer_plans (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quaicu_customer_plans")
