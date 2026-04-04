"""
0046 — Table Partitioning for audit_ledger (monthly) and domain_events (weekly)

Converts high-volume tables to PostgreSQL native range partitioning.

audit_ledger: RANGE on timestamp (monthly)
  - Hash chain integrity preserved: (tenant_id, id DESC) index spans all partitions
  - Partitions pre-created 12 months ahead
  - Old partitions (> 2 years) can be detached and exported to cold storage

domain_events: RANGE on published_at (weekly)
  - Events are short-lived (PENDING → DONE in seconds)
  - Partitions pre-created 8 weeks ahead
  - Old partitions (> 30 days) can be dropped (state already materialized)

Strategy:
  1. Rename existing table to {table}_old
  2. Create partitioned table with same schema
  3. Create partitions for current + future periods
  4. Migrate data from old table into partitioned table
  5. Drop old table

NOTE: This migration may take significant time on large datasets.
Run during a maintenance window.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def _month_range(start_year: int, start_month: int, count: int):
    """Generate (year, month) pairs for partition creation."""
    for i in range(count):
        m = start_month + i
        y = start_year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        yield y, m


def _next_month(year: int, month: int):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def upgrade() -> None:
    conn = op.get_bind()

    # =========================================================================
    # 1. AUDIT_LEDGER — Monthly partitioning on timestamp
    # =========================================================================

    # 1a. Rename existing table
    op.execute("ALTER TABLE IF EXISTS audit_ledger RENAME TO audit_ledger_old")

    # 1b. Create partitioned table with identical schema
    op.execute("""
        CREATE TABLE audit_ledger (
            id BIGSERIAL,
            tenant_id TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            actor_role TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            metadata JSONB,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            previous_hash TEXT,
            hash TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp)
    """)

    # 1c. Create indexes that span all partitions
    op.execute("""
        CREATE INDEX idx_audit_ledger_tenant_id_desc
        ON audit_ledger (tenant_id, id DESC)
    """)
    op.execute("""
        CREATE INDEX idx_audit_ledger_tenant_ts_desc
        ON audit_ledger (tenant_id, timestamp DESC)
    """)
    op.execute("""
        CREATE INDEX idx_audit_ledger_tenant_action
        ON audit_ledger (tenant_id, action)
    """)

    # 1d. Create immutability trigger on the partitioned table
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_audit_ledger_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_ledger is immutable: % operations are forbidden', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_ledger_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_ledger
        FOR EACH STATEMENT
        EXECUTE FUNCTION fn_audit_ledger_immutable()
    """)

    # 1e. Create partitions: 6 months back + 12 months forward
    now = datetime.utcnow()
    start_year = now.year
    start_month = now.month - 6
    if start_month < 1:
        start_year -= 1
        start_month += 12

    for y, m in _month_range(start_year, start_month, 18):
        ny, nm = _next_month(y, m)
        part_name = f"audit_ledger_y{y}m{m:02d}"
        from_date = f"{y}-{m:02d}-01"
        to_date = f"{ny}-{nm:02d}-01"
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {part_name}
            PARTITION OF audit_ledger
            FOR VALUES FROM ('{from_date}') TO ('{to_date}')
        """)

    # 1f. Migrate data from old table
    op.execute("""
        INSERT INTO audit_ledger
            (id, tenant_id, actor_id, actor_role, action, entity_type,
             entity_id, metadata, timestamp, previous_hash, hash)
        SELECT id, tenant_id, actor_id, actor_role, action, entity_type,
               entity_id, metadata, timestamp, previous_hash, hash
        FROM audit_ledger_old
        ORDER BY id ASC
    """)

    # 1g. Sync the sequence
    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('audit_ledger', 'id'),
            COALESCE((SELECT MAX(id) FROM audit_ledger), 0) + 1,
            false
        )
    """)

    # 1h. Enable RLS on partitioned table (same policy as original)
    op.execute("ALTER TABLE audit_ledger ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY audit_ledger_tenant_isolation ON audit_ledger
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)
    # Restrict to SELECT + INSERT only (no UPDATE/DELETE even with RLS)
    op.execute("""
        CREATE POLICY audit_ledger_insert_only ON audit_ledger
        FOR INSERT WITH CHECK (TRUE)
    """)

    # 1i. Drop old table
    op.execute("DROP TABLE IF EXISTS audit_ledger_old")

    # =========================================================================
    # 2. DOMAIN_EVENTS — Weekly partitioning on published_at
    # =========================================================================

    # 2a. Rename existing table
    op.execute("ALTER TABLE IF EXISTS domain_events RENAME TO domain_events_old")

    # 2b. Create partitioned table
    op.execute("""
        CREATE TABLE domain_events (
            id UUID NOT NULL,
            org_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            payload JSONB,
            actor_id TEXT NOT NULL DEFAULT 'system',
            correlation_id TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ,
            retry_count INT NOT NULL DEFAULT 0,
            failure_reason TEXT,
            processing_started_at TIMESTAMPTZ,
            PRIMARY KEY (id, published_at)
        ) PARTITION BY RANGE (published_at)
    """)

    # 2c. Indexes
    op.execute("""
        CREATE INDEX idx_domain_events_status_published
        ON domain_events (status, published_at ASC)
    """)
    op.execute("""
        CREATE INDEX idx_domain_events_org_type
        ON domain_events (org_id, event_type)
    """)
    op.execute("""
        CREATE INDEX idx_domain_events_correlation
        ON domain_events (correlation_id)
        WHERE correlation_id IS NOT NULL
    """)

    # 2d. Create partitions: 2 weeks back + 8 weeks forward
    today = datetime.utcnow().date()
    # Find the Monday of 2 weeks ago
    start_monday = today - timedelta(days=today.weekday() + 14)

    for i in range(10):  # 2 back + 8 forward
        week_start = start_monday + timedelta(weeks=i)
        week_end = week_start + timedelta(weeks=1)
        part_name = f"domain_events_w{week_start.isocalendar()[0]}w{week_start.isocalendar()[1]:02d}"
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {part_name}
            PARTITION OF domain_events
            FOR VALUES FROM ('{week_start.isoformat()}') TO ('{week_end.isoformat()}')
        """)

    # 2e. Migrate data
    op.execute("""
        INSERT INTO domain_events
            (id, org_id, event_type, entity_type, entity_id, payload,
             actor_id, correlation_id, status, published_at, processed_at,
             retry_count, failure_reason, processing_started_at)
        SELECT id, org_id, event_type, entity_type, entity_id, payload,
               actor_id, correlation_id, status, published_at, processed_at,
               retry_count, failure_reason, processing_started_at
        FROM domain_events_old
        ORDER BY published_at ASC
    """)

    # 2f. Drop old table
    op.execute("DROP TABLE IF EXISTS domain_events_old")


def downgrade() -> None:
    # Reverse: create non-partitioned tables and migrate data back
    # WARNING: this will lose partition structure but preserve data

    # --- audit_ledger ---
    op.execute("ALTER TABLE audit_ledger RENAME TO audit_ledger_partitioned")
    op.execute("""
        CREATE TABLE audit_ledger (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            actor_role TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            metadata JSONB,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            previous_hash TEXT,
            hash TEXT NOT NULL DEFAULT ''
        )
    """)
    op.execute("""
        INSERT INTO audit_ledger SELECT * FROM audit_ledger_partitioned ORDER BY id ASC
    """)
    op.execute("DROP TABLE audit_ledger_partitioned CASCADE")

    # --- domain_events ---
    op.execute("ALTER TABLE domain_events RENAME TO domain_events_partitioned")
    op.execute("""
        CREATE TABLE domain_events (
            id UUID PRIMARY KEY,
            org_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            payload JSONB,
            actor_id TEXT NOT NULL DEFAULT 'system',
            correlation_id TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ,
            retry_count INT NOT NULL DEFAULT 0,
            failure_reason TEXT,
            processing_started_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        INSERT INTO domain_events SELECT * FROM domain_events_partitioned ORDER BY published_at ASC
    """)
    op.execute("DROP TABLE domain_events_partitioned CASCADE")
