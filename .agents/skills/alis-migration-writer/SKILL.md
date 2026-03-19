---
name: alis-migration-writer
description: |
  ALIS Alembic migration writing patterns. Use when creating, reviewing, or debugging database migrations
  for ALIS. Covers correct table conventions (UUID PKs, TIMESTAMPTZ, DECIMAL(12,2) for money, JSONB,
  soft delete status columns, pgvector, pg_trgm, uuid-ossp extensions), index patterns, FK constraints,
  immutable audit_ledger triggers, and Alembic revision chaining. Trigger keywords: migration, alembic,
  schema, CREATE TABLE, op.execute, revision, upgrade, downgrade, table, column, index, FK, foreign key,
  TIMESTAMPTZ, UUID, DECIMAL, JSONB, pgvector, vector, soft delete, status column, migrate, database schema.
---

# ALIS Migration Writer

You are the ALIS Database Schema Expert. All migrations live in `ALIS/migrations/versions/` and follow
Alembic conventions with ALIS-specific table design rules.

## Migration File Header

```python
"""<description — one line>

Revision ID: NNNN
Revises: MMMM
Create Date: YYYY-MM-DD
"""

from alembic import op

revision = "NNNN"
down_revision = "MMMM"   # Previous migration ID (None for first)
branch_labels = None
depends_on = None


def upgrade() -> None:
    ...


def downgrade() -> None:
    ...
```

Revision IDs are zero-padded 4-digit strings: `"0001"`, `"0012"`. Never use Alembic's auto-generated hex IDs.

## Existing Migrations

| File | Covers |
|---|---|
| `0001_initial_schema.py` | E01 Auth + Users + E02 Workflow + E03 AI + E04 Admissions |
| `0002_autonomous_admissions.py` | Additional admissions tables |
| `0003_academics.py` | E05 Academics |
| `0004_examinations.py` | E06 Examinations |
| `0005_finance.py` | E07 Finance |
| `0006_hr_staff.py` | E08 HR & Payroll |
| `0007_student_services.py` | E09 Student Services |
| `0008_communication_hub.py` | E10 Communication Hub |
| `0009_reporting.py` | E11 Reporting & Analytics |
| `0010_alumni_placement.py` | E12 Alumni & Placement |
| `0011_process_engine.py` | E13 Dynamic Process Engine |
| `0012_schema_corrections.py` | Schema fixes across epics |
| `0013_missing_indexes.py` | Performance indexes |
| `0014_admissions_full_workflow.py` | Full 10-stage admissions pipeline (40+ tables) |
| `0015_rbac_scope_and_event_hardening.py` | `role_assignments` with scope + `domain_events.processing_started_at` |

Next revision: `0016`.

## Required Extensions (already in 0001 — do NOT re-create)

```python
op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
```

## Table Design Rules

### Primary Keys — always UUID

```sql
id  UUID PRIMARY KEY DEFAULT uuid_generate_v4()
```

Never use SERIAL or BIGSERIAL. Never use integer PKs.

### Tenant Column — mandatory on all business tables

```sql
org_id  UUID NOT NULL REFERENCES organisations(id)
```

### Timestamps

```sql
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at  TIMESTAMPTZ          -- nullable, set on mutation
```

Always `TIMESTAMPTZ` (with timezone). Never `TIMESTAMP` (without timezone).

### Status / Soft Delete

```sql
status  TEXT NOT NULL DEFAULT 'ACTIVE'
-- Values: 'ACTIVE', 'ARCHIVED' (lifecycle) or 'DRAFT', 'PENDING', 'APPROVED', 'ANNULLED' (state machine)
```

Never add a `deleted_at` column — soft delete via `status='ARCHIVED'`.

### Money Columns

```sql
amount      DECIMAL(12,2) NOT NULL DEFAULT 0.00
fee_total   DECIMAL(12,2)
```

Always `DECIMAL(12,2)`. Never `FLOAT` or `NUMERIC` without precision.

### Free-Form Metadata

```sql
metadata    JSONB NOT NULL DEFAULT '{}'
```

Use JSONB (binary) not JSON. Include a GIN index if queried:
```python
op.execute("CREATE INDEX IF NOT EXISTS idx_table_metadata ON table USING GIN (metadata)")
```

### Vector Embeddings (pgvector)

```sql
embedding   vector(768)   -- nomic-embed-text dimension
```

```python
op.execute("""
CREATE TABLE IF NOT EXISTS counsellor_profiles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id      UUID NOT NULL REFERENCES organisations(id),
    embedding   vector(768),
    ...
)""")
op.execute("""
CREATE INDEX IF NOT EXISTS idx_counsellor_embedding
ON counsellor_profiles USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100)
""")
```

## Full Table Example

```python
op.execute("""
CREATE TABLE IF NOT EXISTS scholarship_awards (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    student_id      UUID NOT NULL REFERENCES students(id),
    scholarship_id  UUID NOT NULL REFERENCES scholarships(id),
    amount          DECIMAL(12,2) NOT NULL,
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    awarded_by      UUID,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
)""")
```

## Index Patterns

```python
# FK index (always index FK columns)
op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_awards_org ON scholarship_awards(org_id)")
op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_awards_student ON scholarship_awards(student_id)")

# Status filter (common query pattern)
op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_awards_status ON scholarship_awards(status)")

# Composite (tenant + status — most list queries filter both)
op.execute("""
CREATE INDEX IF NOT EXISTS idx_scholarship_awards_org_status
ON scholarship_awards(org_id, status)
""")

# Text search with pg_trgm
op.execute("""
CREATE INDEX IF NOT EXISTS idx_students_name_trgm
ON students USING GIN (name gin_trgm_ops)
""")

# Unique constraint
op.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_scholarship_awards_unique
ON scholarship_awards(org_id, student_id, scholarship_id)
WHERE status != 'ANNULLED'
""")
```

## Immutable Audit Ledger Triggers (already in 0001 — reference only)

The `audit_ledger` table has DB-level triggers preventing UPDATE/DELETE/TRUNCATE.
Never alter, drop, or recreate these triggers.

## Downgrade Pattern

Always implement a safe downgrade:

```python
def downgrade() -> None:
    # Drop indexes first, then tables (reverse of upgrade)
    op.execute("DROP INDEX IF EXISTS idx_scholarship_awards_org_status")
    op.execute("DROP INDEX IF EXISTS idx_scholarship_awards_status")
    op.execute("DROP INDEX IF EXISTS idx_scholarship_awards_student")
    op.execute("DROP INDEX IF EXISTS idx_scholarship_awards_org")
    op.execute("DROP TABLE IF EXISTS scholarship_awards")
```

Drop indexes before tables. Use `IF EXISTS` everywhere.

## Alembic Commands

```bash
# Run all pending migrations
alembic -c ALIS/alembic.ini upgrade head

# Run to specific revision
alembic -c ALIS/alembic.ini upgrade 0005

# Roll back one step
alembic -c ALIS/alembic.ini downgrade -1

# Check current revision
alembic -c ALIS/alembic.ini current

# Show history
alembic -c ALIS/alembic.ini history
```

## Adding a Column to an Existing Table

Use `ADD COLUMN IF NOT EXISTS` — always idempotent:

```python
op.execute("""
    ALTER TABLE domain_events
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ
""")

# Partial index on the new column (only indexes rows in relevant states)
op.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_stuck
    ON domain_events(status, processing_started_at)
    WHERE status = 'PROCESSING'
""")
```

## Scoped RBAC Table Pattern (role_assignments)

When a role grant needs to be bounded to a sub-resource (department, program, course):

```python
op.execute("""
CREATE TABLE IF NOT EXISTS role_assignments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id      TEXT NOT NULL,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    scope_type  TEXT,    -- NULL = org-wide | DEPARTMENT | PROGRAM | COURSE | HOSTEL_BLOCK
    scope_ref   TEXT,    -- the id of the scoped resource (e.g. dept_id)
    granted_by  UUID NOT NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    CONSTRAINT uq_role_assignment
        UNIQUE (org_id, user_id, role_id,
                COALESCE(scope_type, ''), COALESCE(scope_ref, ''))
)""")
op.execute("ALTER TABLE role_assignments ENABLE ROW LEVEL SECURITY")
op.execute("""
    CREATE POLICY role_assignments_tenant_isolation ON role_assignments
    USING (org_id::text = current_setting('alis.current_tenant', TRUE))
""")
```

Key pattern: `COALESCE(scope_type, '')` in the unique constraint — allows `NULL` scope (org-wide) to be
distinct from scoped grants without a unique-index NULL comparison problem.

## Common Mistakes to Avoid

- Using `TIMESTAMP` instead of `TIMESTAMPTZ` — always include timezone
- Using `FLOAT` for money — always `DECIMAL(12,2)`
- Forgetting `org_id` on business tables — every entity is tenant-scoped
- Using integer IDs — always UUID with `uuid_generate_v4()`
- Missing FK index — every FK column needs a btree index
- Not using `IF NOT EXISTS` — migrations must be idempotent
- Altering `audit_ledger` — immutable by design, never change it
- Skipping downgrade — always implement a clean rollback
