"""017 — extend RLS to every tenant-keyed kernel table (D4-1, F-07 defense in depth).

Revision ID: 017
Revises: 016
Create Date: 2026-07-04

Migrations 004/007 put RLS (with the ``'*'`` read-only hydration sentinel) on only three tables
(quaicu_actions, quaicu_ledger_entries, quaicu_ledger_sth). Every other tenant-keyed table relied
purely on the adapters' ``WHERE tenant_id`` predicates — logical isolation with no database
backstop. This migration applies the same 007-style policy (strict writes, ``'*'`` sentinel reads)
plus ENABLE/FORCE RLS to the remaining six:

  quaicu_customer_plans  (005) — entitlement plans
  quaicu_accounts        (006) — account registry (PII, password hashes)
  quaicu_api_keys        (006) — hashed API keys
  quaicu_members         (011) — team members (PII, password hashes)
  quaicu_shred_keys      (012) — KMS-wrapped DEKs
  quaicu_approvals       (013) — HITL approval queue

Intentionally NOT under RLS (documented, not an oversight):
  quaicu_policies / quaicu_policy_impact_reports — no tenant_id column; kernel-global control plane.
  quaicu_witness_state — witness-service infrastructure state, written by a non-tenant-scoped
  service in its own trust domain (see migration 016).

Deploy order matters on a live database: the adapter build that sets ``app.current_tenant`` per
transaction (same D4-1 change-set) must be RUNNING before this migration is applied — FORCE RLS
turns un-GUC'd adapter reads into empty result sets instantly. Setting the GUC against tables
without RLS is harmless, so the adapter build always ships first.
"""

from __future__ import annotations

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

_TABLES = (
    "quaicu_customer_plans",
    "quaicu_accounts",
    "quaicu_api_keys",
    "quaicu_members",
    "quaicu_shred_keys",
    "quaicu_approvals",
)

# Same shape as migration 007: reads also match the internal '*' sentinel (cross-tenant hydration /
# key-by-id lookups); writes never do — a '*' session can read everything but write nothing foreign.
# Tenant ids are validated ^[a-z0-9][a-z0-9_-]{0,50}$ (adapters/storage/isolation), so no real
# tenant can present '*' through the per-request path.
_READ = (
    "tenant_id = current_setting('app.current_tenant', true) "
    "OR current_setting('app.current_tenant', true) = '*'"
)
_WRITE = "tenant_id = current_setting('app.current_tenant', true)"


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING ({_READ})
                WITH CHECK ({_WRITE})
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
