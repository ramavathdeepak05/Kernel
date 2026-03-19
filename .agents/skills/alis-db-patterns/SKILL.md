---
name: alis-db-patterns
description: |
  ALIS database access guardrail. Enforces correct use of execute_query (SELECT only) vs
  execute_transaction (all writes). Catches direct DB writes, raw psycopg2 usage, missing tenant
  scoping, and missing audit logs after mutations. Use when reviewing or writing any code that touches
  the database in ALIS. Trigger keywords: execute_query, execute_transaction, INSERT, UPDATE, DELETE,
  database write, db_service, psycopg2, connection, cursor, SQL, query, transaction, tenant_id, org_id
  missing, audit missing after write, no AuditLedger, raw SQL write.
---

# ALIS DB Patterns Guardrail

You are the ALIS Database Safety Auditor. Before writing or approving any code that touches the database,
verify all rules below. Violating these rules causes data corruption, tenant leaks, or audit gaps.

## The Two DB Functions (Absolute Rules)

### execute_query — SELECT only, never commits

```python
from server.db_service import execute_query

# CORRECT
rows = execute_query(
    "SELECT * FROM applicants WHERE org_id = %s AND status = %s",
    (org_id, "ACTIVE")
)

# WRONG — execute_query does NOT commit, writes are silently lost
execute_query("INSERT INTO applicants ...", ...)  # BUG
```

### execute_transaction — ALL writes, always commits atomically

```python
from server.db_service import execute_transaction

# CORRECT — single statement
execute_transaction([
    ("INSERT INTO applicants (id, org_id, name, status) VALUES (%s, %s, %s, %s)",
     (str(uuid4()), org_id, name, "DRAFT")),
])

# CORRECT — atomic multi-statement (all succeed or all roll back)
execute_transaction([
    ("UPDATE applicants SET status = %s WHERE id = %s", ("APPROVED", app_id)),
    ("INSERT INTO audit_events (entity_id, event) VALUES (%s, %s)", (app_id, "approved")),
])

# WRONG — raw connection usage in business logic
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("INSERT ...")
conn.commit()  # BUG — bypasses tenant isolation + pooling
```

### execute_system_query / execute_system_transaction — bypasses RLS, restricted use only

```python
from server.db_service import execute_system_query, execute_system_transaction

# ONLY for: Celery Beat tasks, migrations, health checks, audit chain verification
# NEVER in HTTP request-handling code paths

# Celery Beat has no HTTP context — ContextVar is not set — execute_query raises TenantIsolationError
rows = execute_system_query(
    "SELECT id FROM domain_events WHERE status = 'PENDING' LIMIT 50", ()
)

# System-level write (e.g., resetting stuck events across all tenants)
execute_system_transaction([
    ("UPDATE domain_events SET status = 'PENDING' WHERE id = ANY(%s)", (stuck_ids,)),
])
```

**In Celery tasks that DO know their tenant**, pass it explicitly instead:
```python
execute_query("SELECT ...", (params,), tenant_id=org_id)
execute_transaction([("UPDATE ...", (params,))], tenant_id=org_id)
```

## Tenant Isolation (Layer 4 Invariant)

Every business table has `org_id`. Every query MUST scope by `org_id`.

```python
# CORRECT
rows = execute_query(
    "SELECT * FROM students WHERE org_id = %s AND id = %s",
    (org_id, student_id)
)

# WRONG — cross-tenant data leak
rows = execute_query("SELECT * FROM students WHERE id = %s", (student_id,))
```

Extract `org_id` from request state, never from the request body:

```python
org_id = getattr(request.state, "tenant_id", None)
if not org_id:
    raise PermissionDeniedError("No tenant context")
```

## Parameterized Queries (SQL Injection Prevention)

```python
# CORRECT — always use %s placeholders
execute_query("SELECT * FROM users WHERE email = %s", (email,))

# WRONG — string interpolation = SQL injection vulnerability
execute_query(f"SELECT * FROM users WHERE email = '{email}'")  # NEVER
execute_query("SELECT * FROM users WHERE email = '" + email + "'")  # NEVER
```

## Audit Log After Every Mutation

Every `execute_transaction` that changes business state MUST be followed by `AuditLedger.log()`:

```python
from server.core.audit import AuditLedger, AuditAction

execute_transaction([
    ("UPDATE students SET status = %s WHERE id = %s AND org_id = %s",
     ("ARCHIVED", student_id, org_id)),
])

# MANDATORY — audit the mutation
AuditLedger.log(
    action=AuditAction.UPDATE,
    actor_id=actor_id,
    actor_role=actor_role,
    entity_type="Student",
    entity_id=student_id,
    tenant_id=org_id,
    metadata={"status": "ARCHIVED"},
)
```

Exceptions: internal Celery tasks logging their own events, and the audit ledger itself.

## ID Generation

```python
from uuid import uuid4

# CORRECT
new_id = str(uuid4())

# WRONG — integer IDs, sequential IDs, non-UUID strings
new_id = 1          # NEVER
new_id = "student_001"  # NEVER
```

## Money Handling

```python
# In DB: DECIMAL(12,2) column
# In Python: use Decimal, never float
from decimal import Decimal

amount = Decimal("12500.00")

# In JSON response: send as string to preserve precision
{"amount": str(amount)}  # "12500.00"

# WRONG
amount = 12500.0  # float — precision loss
{"amount": 12500.0}  # float in JSON — precision loss
```

## Timestamp Handling

```python
from datetime import datetime, timezone

# CORRECT — always UTC-aware
now = datetime.now(timezone.utc)

# WRONG — naive datetime loses timezone info
now = datetime.now()  # NEVER in ALIS
now = datetime.utcnow()  # NEVER — deprecated, returns naive
```

## Checklist Before Any DB Write

- [ ] Using `execute_transaction`, not `execute_query`
- [ ] Query includes `org_id = %s` parameter
- [ ] All parameters use `%s` placeholders (no f-strings in SQL)
- [ ] IDs are `str(uuid4())`
- [ ] Money values are `Decimal`, not `float`
- [ ] `AuditLedger.log()` called after the mutation
- [ ] No raw psycopg2 cursor usage in business logic
- [ ] Timestamps use `datetime.now(timezone.utc)`

## Checklist Before Any DB Read

- [ ] Using `execute_query`, not `execute_transaction`
- [ ] Query scoped by `org_id`
- [ ] Parameterized with `%s` — no string interpolation
- [ ] `LIMIT` clause present on list queries (default 50, max 200)
