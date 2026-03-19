---
name: alis-dynamic-rbac
description: |
  ALIS Dynamic RBAC+ system — static roles, custom role creation, cross-module permission approval,
  policy governance, and policy resolver middleware. Use when implementing role checks, creating custom
  roles, requesting cross-module permissions, building policy-gated endpoints, managing policy
  lifecycle (DRAFT→ACTIVATED), or resolving active policies in rule engine and Celery tasks.
  Covers Role enum, Permission enum, ROLE_PERMISSIONS, MODULE_PERMISSIONS, PERMISSION_TO_MODULE,
  verify_access (ABAC), require_permission decorator, custom_roles table, custom_role_permissions
  approval flow, PolicyService (create_draft/submit/approve), PolicyResolver (RequirePolicy dependency,
  resolve_policy_for_rule, cache invalidation), PolicyResolverCache. Trigger keywords: RBAC, role,
  permission, custom role, dynamic role, module manager, cross-module, permission approval, policy,
  policy lifecycle, policy draft, policy approval, policy resolver, RequirePolicy, verify_access,
  require_permission, ROLE_PERMISSIONS, Permission enum, Role enum, access control, authority matrix,
  SUPER_ADMIN, M1_MANAGER, policy_type, policy version, attendance_threshold, grading_cutoff.
---

# ALIS Dynamic RBAC+

You are the ALIS Access Control Expert. ALIS uses a two-layer RBAC+ system:
1. **Static RBAC** — hardcoded role-permission maps (`rbac.py`)
2. **Dynamic RBAC** — runtime custom roles created by module managers (`roles_router.py`)

Both layers are governed by an immutable **Policy Governance** system that feeds the **Rule Engine**.

---

## Layer 1 — Static RBAC (Foundation)

### Role Hierarchy

```python
from server.core.rbac import Role

# Human roles
Role.STUDENT | Role.FACULTY | Role.HOD | Role.DEAN
Role.REGISTRAR | Role.FINANCE_OFFICER | Role.HR_ADMIN
Role.ADMIN | Role.SUPER_ADMIN | Role.DEAN_ELEVATED

# Module Manager roles (one per module, created by SUPER_ADMIN)
Role.M1_MANAGER  # Admissions & Marketing
Role.M2_MANAGER  # Academics
Role.M3_MANAGER  # Examinations
Role.M4_MANAGER  # Finance
Role.M5_MANAGER  # HR & Payroll
Role.M6_MANAGER  # Student Services
Role.M7_MANAGER  # Communication Hub
Role.M8_MANAGER  # Reporting & Analytics
Role.M9_MANAGER  # Alumni & Placement

# System roles
Role.AI_AGENT    # Read-only, advisory only
Role.SYSTEM      # Internal ops, bypasses tenant checks
```

### Permission Check (Basic RBAC)

```python
from server.core.rbac import check_role_permission, Role, Permission

# Simple check — does this role have this permission?
allowed = check_role_permission(Role.REGISTRAR, Permission.RESULT_PUBLISH)  # True
allowed = check_role_permission(Role.STUDENT, Permission.RESULT_PUBLISH)    # False
```

### RBAC+ Access Verification (ABAC Extension)

Always use `verify_access` in service layer for context-aware decisions:

```python
from server.core.rbac import verify_access, Role, Permission

result = verify_access(
    actor_role=Role.FACULTY,
    permission=Permission.MARKS_ENTRY,
    context={
        "tenant_id": org_id,
        "exam_status": "EVALUATION_OPEN",  # Context-aware: only during eval window
        "is_owner": True,
    },
)

if not result.allowed:
    raise PermissionDeniedError(
        message=result.reason,
        details={"violations": result.context_violations},
    )
```

Context keys:
- `tenant_id` — mandatory for all non-system operations (Layer 4)
- `exam_status` — gates `MARKS_ENTRY` to `"EVALUATION_OPEN"` window
- `is_owner` — gates `COURSE_UPDATE` to course owners
- `action` — `"read"` or `"write"` — AI_AGENT blocked from `"write"`
- `override_tenant` — AI_AGENT cannot set this

### Route Decorator

```python
from server.core.rbac import require_permission, Permission

@router.post("/results/publish")
@require_permission(Permission.RESULT_PUBLISH)
async def publish_results(request: Request):
    ...
```

### Permission Reference (Key Ones)

```python
from server.core.rbac import Permission

# Student data
Permission.STUDENT_READ | STUDENT_CREATE | STUDENT_UPDATE | STUDENT_READ_PII

# Academics
Permission.COURSE_READ | COURSE_CREATE | COURSE_UPDATE
Permission.MARKS_READ | MARKS_ENTRY | MARKS_FINALIZE

# Finance
Permission.FEE_READ | FEE_CREATE | PAYMENT_PROCESS | LEDGER_READ

# Overrides & AI
Permission.OVERRIDE_REQUEST | OVERRIDE_APPROVE | AI_INVOKE

# Dynamic roles
Permission.ROLE_CREATE | ROLE_MANAGE | ROLE_APPROVE

# Policy governance
Permission.POLICY_DRAFT | POLICY_SUBMIT | POLICY_APPROVE | POLICY_READ

# Process engine
Permission.PROCESS_READ | PROCESS_MANAGE
```

### Module-Permission Ownership Maps

```python
from server.core.rbac import (
    MANAGER_MODULE,        # Role.M1_MANAGER → "M1"
    MODULE_MANAGER_ROLE,   # "M1" → Role.M1_MANAGER
    MODULE_PERMISSIONS,    # "M1" → [STUDENT_READ, STUDENT_CREATE, ...]
    PERMISSION_TO_MODULE,  # Permission.STUDENT_READ → "M1"
    ALL_MANAGER_ROLES,     # frozenset of all Mx_MANAGER roles
    is_manager_role,       # Role → bool
    get_manager_module,    # Role → Optional[str]
    get_module_for_permission,  # Permission → Optional[str]
)

# What module does M3_MANAGER own?
module = get_manager_module(Role.M3_MANAGER)  # "M3"

# Which module owns RESULT_PUBLISH?
owning = get_module_for_permission(Permission.RESULT_PUBLISH)  # "M3"

# Is this role a module manager?
is_manager_role(Role.M2_MANAGER)  # True
is_manager_role(Role.FACULTY)     # False
```

---

## Layer 2 — Dynamic RBAC (Custom Roles)

Module managers create custom roles within their module scope. Custom role permissions
are **additive** on top of a user's base static role.

### Authority Matrix

| Action | SUPER_ADMIN | Mx_MANAGER | Others |
|---|---|---|---|
| Create custom role | ✓ | ✓ (own module) | ✗ |
| Request permissions | ✓ | ✓ (own role only) | ✗ |
| Approve cross-module perm | ✓ | ✓ (own module perms) | ✗ |
| Archive role | ✓ | ✓ (own role only) | ✗ |

### Permission Routing Logic

```
SUPER_ADMIN requests any permission       → APPROVED immediately
Same-module permission                    → APPROVED immediately
Platform-level permission (no module)     → APPROVED immediately
Cross-module permission                   → PENDING (owning module manager approves)
```

### DB Schema (custom roles)

```sql
-- custom_roles
id UUID, tenant_id UUID, module TEXT, role_name TEXT,
description TEXT, status TEXT DEFAULT 'ACTIVE',
created_by UUID, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
-- Unique: (tenant_id, role_name)  [uq_custom_role_name_tenant]

-- custom_role_permissions
id UUID, tenant_id UUID, role_id UUID → custom_roles(id),
permission TEXT, status TEXT,  -- PENDING | APPROVED | DENIED
requested_by UUID, requested_at TIMESTAMPTZ,
reviewed_by UUID, reviewed_at TIMESTAMPTZ, review_note TEXT

-- user_custom_roles
user_id UUID, role_id UUID, assigned_by UUID, assigned_at TIMESTAMPTZ
```

### Scoped Role Assignments (role_assignments — migration 0015)

The flat `users.role` column gives org-wide access. For boundary enforcement (HOD sees only their
department, warden sees only their block), use `role_assignments` with a scope:

```sql
-- role_assignments (added in 0015_rbac_scope_and_event_hardening.py)
id UUID, org_id TEXT,
user_id UUID → users(id),
role_id UUID → roles(id),
scope_type TEXT,    -- NULL = org-wide | DEPARTMENT | PROGRAM | COURSE | HOSTEL_BLOCK | EXAM_BATCH
scope_ref  TEXT,    -- the id value of the scoped resource
granted_by UUID, granted_at TIMESTAMPTZ, expires_at TIMESTAMPTZ
-- Unique: (org_id, user_id, role_id, COALESCE(scope_type,''), COALESCE(scope_ref,''))
```

```python
from server.db_service import execute_transaction
from uuid import uuid4

# Grant HOD access scoped to CSE department only
execute_transaction([
    ("""
    INSERT INTO role_assignments (id, org_id, user_id, role_id, scope_type, scope_ref, granted_by)
    VALUES (%s, %s, %s, %s, 'DEPARTMENT', %s, %s)
    ON CONFLICT ON CONSTRAINT uq_role_assignment DO NOTHING
    """, (str(uuid4()), org_id, hod_user_id, hod_role_id, "dept-cse-uuid", actor_id)),
])

# Query: what scoped roles does this user hold?
from server.db_service import execute_query
scoped = execute_query(
    """
    SELECT ra.scope_type, ra.scope_ref, r.name AS role_name, r.permissions
    FROM role_assignments ra
    JOIN roles r ON r.id = ra.role_id
    WHERE ra.org_id = %s AND ra.user_id = %s
      AND (ra.expires_at IS NULL OR ra.expires_at > NOW())
    """,
    (org_id, user_id),
)
```

Use scoped grants for: HOD (DEPARTMENT), faculty (COURSE), hostel warden (HOSTEL_BLOCK),
exam invigilators (EXAM_BATCH). `scope_type = NULL` means org-wide (equivalent to the flat role).

### API Endpoints

```
POST   /api/roles                               — Create custom role
GET    /api/roles?module=M1&status=ACTIVE       — List custom roles
GET    /api/roles/approvals/pending             — View cross-module pending approvals
POST   /api/roles/approvals/{req_id}/approve    — Approve permission
POST   /api/roles/approvals/{req_id}/deny       — Deny permission (+ review_note)
GET    /api/roles/{id}                          — Get role + all permissions + statuses
POST   /api/roles/{id}/permissions              — Request permissions for a role
DELETE /api/roles/{id}/permissions/{perm}       — Remove a permission
DELETE /api/roles/{id}                          — Archive role (cascades: revokes from all users)
```

### Querying Custom Role Permissions in Service Layer

```python
from server.db_service import execute_query

# Get all APPROVED permissions for a user (base role + custom roles combined)
def get_effective_permissions(user_id: str, org_id: str, base_role: str) -> set:
    # 1. Start with static role permissions
    from server.core.rbac import ROLE_PERMISSIONS, Role
    try:
        static_perms = {p.value for p in ROLE_PERMISSIONS.get(Role(base_role), [])}
    except ValueError:
        static_perms = set()

    # 2. Add approved custom role permissions
    custom_rows = execute_query(
        """
        SELECT crp.permission
        FROM user_custom_roles ucr
        JOIN custom_role_permissions crp ON crp.role_id = ucr.role_id
        WHERE ucr.user_id = %s
          AND crp.status = 'APPROVED'
          AND crp.tenant_id = %s
        """,
        (user_id, org_id),
    )
    custom_perms = {row["permission"] for row in custom_rows}

    return static_perms | custom_perms
```

### Archiving Custom Roles

Archiving is terminal and cascades automatically:
- `custom_roles.status → 'ARCHIVED'`
- `DELETE FROM user_custom_roles WHERE role_id = ...` (all assignments revoked)
- Audit logged: `AuditAction.STATE_TRANSITION` (ACTIVE → ARCHIVED)

---

## Layer 3 — Policy Governance (Rule Engine Feed)

Policies are structured, versioned, time-bound, approval-controlled rules that drive
all institutional decisions. **No module may access `policy_registry` directly — always go through PolicyService or PolicyResolver.**

### Policy Lifecycle

```
DRAFT → SUBMITTED → APPROVED → ACTIVATED → SUPERSEDED
```

- `DRAFT`: editable, author composing
- `SUBMITTED`: locked, awaiting approval
- `APPROVED`: approval granted, pending `effective_from` date
- `ACTIVATED`: live, consumed by rule engine, **IMMUTABLE**
- `SUPERSEDED`: replaced by newer version, **IMMUTABLE**, retained for appeal replay

### Creating a Policy (DRAFT → SUBMITTED → APPROVED)

```python
from server.core.policy_service import PolicyService
from datetime import datetime, timezone

# 1. Create draft
draft = PolicyService.create_draft(
    policy_type="attendance_threshold",     # Canonical type key
    name="AY 2026-27 Attendance Policy",
    description="Minimum attendance for exam eligibility",
    parameters={
        "minimum_percentage": 75,
        "grace_period_days": 5,
        "applies_to": ["UG", "PG"],
    },
    effective_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
    effective_to=datetime(2027, 6, 30, tzinfo=timezone.utc),  # or None = indefinite
    created_by=actor_id,
    actor_role="admin",
    tenant_id=org_id,
    module="M2",  # Optional: owning module
)
# draft["content_hash"] — SHA-256 of payload (immutability fingerprint)

# 2. Submit for approval (locks from further edits)
PolicyService.submit_for_approval(
    policy_id=draft["id"],
    submitted_by=actor_id,
    actor_role="admin",
    tenant_id=org_id,
)

# 3. Approve (requires Permission.POLICY_APPROVE — ADMIN or SUPER_ADMIN)
result = PolicyService.approve_policy(
    policy_id=draft["id"],
    approved_by=super_admin_id,
    actor_role="super_admin",
    tenant_id=org_id,
)
# If effective_from <= now: auto-activates + supersedes previous version
# If effective_from > now: stays APPROVED until effective_from date
```

### Retrieving Active Policies (Rule Engine)

```python
from server.core.policy_service import PolicyService

# Get currently active policy (consumed by rule engine)
policy = PolicyService.get_active_policy_by_type(
    policy_type="attendance_threshold",
    tenant_id=org_id,
    as_of_date=None,  # None = now
)
# policy["parameters"]["minimum_percentage"] → 75
# policy["version"] → 3
# policy["content_hash"] → "sha256..."

# Historical lookup (appeal replay — §20)
historical = PolicyService.get_active_policy_by_type(
    policy_type="grading_cutoff",
    tenant_id=org_id,
    as_of_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
)

# Version history (diff viewer)
history = PolicyService.get_version_history("attendance_threshold", org_id)
```

### Policy Resolver — Endpoints (FastAPI Dependency)

Every endpoint that makes institutional decisions must inject the policy via `RequirePolicy`:

```python
from fastapi import Depends
from server.core.policy_resolver import RequirePolicy, build_policy_context

@router.post("/attendance/finalize")
@require_permission(Permission.MARKS_FINALIZE)
async def finalize_attendance(
    body: AttendanceFinalizeRequest,
    request: Request,
    policy: dict = Depends(RequirePolicy("attendance_threshold")),
):
    # `policy` is guaranteed to be ACTIVATED — HTTP 428 if none exists
    ctx = build_policy_context(policy)
    min_pct = ctx["parameters"]["minimum_percentage"]

    # Log policy_version_used (already attached to request.state by RequirePolicy)
    # request.state.policy_version_used = {policy_id, policy_type, version, content_hash}

    # Make deterministic decision
    eligible = attendance_pct >= min_pct
    ...
```

### Policy Resolver — Rule Engine / Celery (Non-HTTP)

```python
from server.core.policy_resolver import resolve_policy_for_rule, build_policy_context

# In Celery task or event handler
policy = resolve_policy_for_rule(
    policy_type="fee_waiver_limit",
    tenant_id=org_id,
    decision_date=None,          # None = now
    actor_id="system",
    actor_role="system",
)
# Raises PolicyResolutionError if no active policy — blocks execution (Layer 4)

ctx = build_policy_context(policy)
max_waiver = ctx["parameters"]["max_waiver_percentage"]
```

### Policy Cache Invalidation

The resolver caches policies for 5 minutes (TTL). Invalidate when a policy activates:

```python
from server.core.policy_resolver import get_resolver_cache

# Invalidate specific policy type for a tenant (called on PolicyActivated event)
cache = get_resolver_cache()
cache.invalidate(tenant_id=org_id, policy_type="attendance_threshold")

# Invalidate ALL policies for a tenant (e.g., on tenant reset)
cache.invalidate(tenant_id=org_id)
```

The `PolicyActivated` domain event automatically triggers cache invalidation in the
event handler. Subscribe to `"e00.policy.activated"` in any module that caches policy values.

### Standard Policy Types

| Policy Type Key | Module | Parameters |
|---|---|---|
| `attendance_threshold` | M2 | `minimum_percentage`, `grace_period_days` |
| `grading_cutoff` | M3 | `pass_mark`, `distinction_mark`, `fail_mark` |
| `fee_waiver_limit` | M4 | `max_waiver_percentage`, `requires_dual_control` |
| `seat_capacity` | M1 | `max_seats`, `waitlist_size` |
| `late_fee_penalty` | M4 | `penalty_percentage`, `grace_days` |
| `exam_eligibility` | M3 | `min_attendance_pct`, `min_assignment_score` |
| `leave_approval_limit` | M5 | `max_days_self_approve`, `requires_hod_above` |

---

## RBAC Anti-Patterns — Never Do These

- Hardcoding permission strings — always use `Permission.PERMISSION_NAME`
- Calling `policy_registry` table directly — always use `PolicyService` or `PolicyResolver`
- Skipping `verify_access()` in service methods — every mutation needs an access check
- Using `Role.SUPER_ADMIN` to bypass tenant checks — `tenant_id` still required
- Letting `APPROVED` status skip module ownership check in approval flow
- Archiving a role without cascading user assignment revocation
- Activating a policy without superseding the previous active version
- Storing policy parameters as free text or embedding in AI weights

## Dynamic RBAC Checklist — New Permission/Role Feature

- [ ] Permission added to `Permission` enum in `rbac.py`
- [ ] Permission added to relevant `ROLE_PERMISSIONS` entries
- [ ] Permission added to `MODULE_PERMISSIONS[module]` (for cross-module routing)
- [ ] Route decorated with `@require_permission(Permission.NEW_PERMISSION)`
- [ ] Service layer calls `verify_access()` with context dict
- [ ] Policy-gated endpoint uses `Depends(RequirePolicy("policy_type"))`
- [ ] `AuditLedger.log()` called on every permission grant/revoke/approval
- [ ] Custom role archive cascades: user assignments deleted atomically
- [ ] Policy activation triggers cache invalidation (`cache.invalidate(...)`)
- [ ] New policy type documented in standard policy types table above
