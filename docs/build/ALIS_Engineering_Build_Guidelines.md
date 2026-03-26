# ALIS OS — Engineering Build Guidelines
### The Constitution for Building ALIS
**QUAICU Solutions Private Limited | Hyderabad, India | Version 1.0 | March 2026 | Confidential**

---

## Purpose of This Document

This document is the engineering constitution for building ALIS OS. Every developer, every pull request, every architectural decision must be measured against these rules. These are not suggestions. They are the load-bearing walls of the system.

ALIS is an Institutional Operating System. It runs regulated institutions. Wrong decisions have legal, financial, and academic consequences for real people. The rules here exist because of that reality — not despite it.

| | |
|---|---|
| **Scope** | All backend services, API routes, database migrations, Temporal workflows, Celery tasks, AI gateway integrations, and frontend API calls across all ALIS modules. |
| **Audience** | All engineers, technical partners, contractors, and reviewers working on the ALIS codebase. |
| **Authority** | The Tech Lead and QUAICU Co-Founders. Any deviation requires written approval before implementation. |

---

## Section 1 — Core Philosophy

Before writing a single line of code, every engineer must internalise three principles. These govern every decision at every layer of the stack.

### 1.1 The Three Immovable Principles

---

#### Principle I — AI Proposes. Rules Enforce. Humans Approve.

The LLM is a co-processor, not a decision-maker. It produces typed draft objects. The policy engine validates the draft against institutional rules. The workflow engine routes it to a human if approval is required. The state machine executes the transition. The audit ledger records everything. The LLM never writes to the database — directly or indirectly.

If you are writing code where an LLM output directly causes a database write without passing through the policy engine and workflow engine, you are violating this principle.

---

#### Principle II — Configuration is Data, Not Code.

Every institutional rule, every approval chain, every SLA, every threshold, every role, every fee, every notification template must live in the database and be read at runtime. Application code must never know the value of a threshold, the name of an approver, or the structure of an approval chain.

**The test:** if changing a policy, workflow, or threshold requires a code change or deployment, the implementation is wrong.

---

#### Principle III — Every Action is Observable, Auditable, and Reversible.

Every state change, AI invocation, policy evaluation, workflow transition, and human decision is written to the immutable audit ledger with a hash chain. No operation happens silently. No operation can be undone by modifying records — only by creating reversal entries. The audit ledger is append-only at the database layer.

---

## Section 2 — Architecture Rules

### 2.1 Module Boundaries

ALIS has seven core modules. Each is a bounded context. The rules for module interaction are absolute:

- Modules never import from each other. Zero cross-module imports in business logic.
- All cross-module communication goes through the Domain Event Bus. No exceptions.
- A module may read from a shared read model (e.g. `student_dues_status`) but may never write to another module's primary tables.
- If you find yourself importing a service class from another module, you are violating this rule. Publish an event instead.

### 2.2 The Six-Layer Stack

Every module must be built with exactly six layers, in this order:

| Layer | Responsibility |
|---|---|
| 1 — Module Purpose | Domain business logic specific to this module. Bounded context. |
| 2 — Agentic Decisions | LLM proposals only. Always DRAFT. Never writes to DB. |
| 3 — State Machines | Only legal path to change entity status. All transitions logged. |
| 4 — Global Locks | Redis distributed locks for race-condition-prone operations. |
| 5 — Roles / Quorum | RBAC checks and quorum enforcement on every operation. |
| 6 — Resilience | SLA timers, escalation chains, auto-approve for low-stakes. |

The AuditLedger cuts across all six layers. Every layer writes to it. No layer is exempt.

### 2.3 The Request Pipeline

Every inbound API request must pass through this pipeline in order. No step may be skipped:

| Step | Component |
|---|---|
| 1 | Nginx — rate limiting, SSL termination |
| 2 | TenantMiddleware — JWT decode, `SET LOCAL tenant` on DB connection |
| 3 | RBAC check — `req.can(resource, action, scope_ref, tenant_id)` |
| 4 | Route handler — calls service layer only |
| 5 | State machine — validates transition is legal |
| 6 | Policy engine — evaluates applicable rules |
| 7 | AI Gateway (if AI involved) — guardrails, logging, HITL gate |
| 8 | Workflow engine — creates approval task if required |
| 9 | AuditLedger — immutable record written |
| 10 | Domain Event Bus — publishes event for downstream consumers |

---

## Section 3 — Database Rules

### 3.1 Multi-Tenancy

- Every table that holds institutional data must have a `tenant_id` column.
- Row-Level Security (RLS) must be enabled on every such table.
- The RLS policy must enforce `WHERE tenant_id = current_setting('alis.current_tenant')`.
- TenantMiddleware must execute `SET LOCAL alis.current_tenant` on every connection before any query.
- No query may use a raw `WHERE tenant_id = $1` clause as the only isolation mechanism. RLS is mandatory at the database layer as the last line of defence.

### 3.2 The Audit Ledger

- The `audit_ledger` table has no UPDATE or DELETE RLS policy. Append-only.
- A PostgreSQL trigger fires on any UPDATE or DELETE attempt and raises an exception.
- Every entry carries: `actor_id`, `role`, `entity_type`, `entity_id`, `old_state`, `new_state`, `policy_id`, `policy_version`, AI model used (if applicable), prompt hash, output hash, human decision.
- Hash chain: `entry.hash = SHA256(previous_entry.hash + json.dumps(event_payload))`
- No code path may write to a module's primary tables without also writing to the audit ledger in the same transaction.

### 3.3 Migrations

- All schema changes go through Alembic. No ad-hoc SQL on production databases.
- Every migration is reviewed before merge. Destructive operations (DROP, truncation) require Tech Lead sign-off.
- Migrations must be backward compatible wherever possible. If a breaking change is required, a two-phase migration is mandatory: add new column → migrate data → remove old column, across separate deployments.
- Never use a migration to update data that should be driven by a policy or workflow change.

### 3.4 The Immutable Ledger Rule for Financial Data

- Posted ledger entries are never modified. Ever.
- Corrections use reversal entries with explicit types: `SCHOLARSHIP_REVERSAL`, `PAYMENT_REVERSAL`, `WAIVER_REVERSAL`, etc.
- No UPDATE or DELETE on the ledger table is permitted from application code.
- This applies to: fee ledger, payroll records, scholarship disbursements, and vendor payments.

---

## Section 4 — Policy Engine Rules

### 4.1 No Threshold Lives in Code

Any value that could differ between institutions or change over time must live in `tenant_policies`. This is non-negotiable.

```python
# ✗ ILLEGAL — hardcoded threshold
if student.attendance_pct >= 75:
    return "ELIGIBLE"

# ✓ LEGAL — runtime policy read
threshold = await policy_engine.get_value(
    "attendance.minimum_threshold", tenant_id
)
if student.attendance_pct >= threshold:
    return "ELIGIBLE"
```

### 4.2 Policy Versioning

- When a policy is updated, the existing record is never modified.
- A new version record is inserted with an incremented version number and new `effective_from` date.
- Old versions are retained permanently — required for audit replay.
- `PolicyEngine.evaluate()` must store the `policy_version` used on every decision record.
- `PolicyEngine.evaluate()` only reads policies with `status='APPROVED'`. Draft policies have no effect on runtime.

### 4.3 The Policy DSL

- The DSL uses `asteval` for safe expression evaluation. `eval()` is permanently banned everywhere in the codebase.
- Policies are cached in Redis with a 5-minute TTL.
- Redis is a performance cache, not a source of truth. The database is always authoritative.
- If Redis is unavailable, PolicyEngine falls back to direct database reads. No degraded behaviour.

### 4.4 The QUAICU_ONLY Tier

Three policy categories cannot be changed by any institution through any interface. They require QUAICU engineering intervention:

- `audit_ledger_retention` — governs how long audit data is kept
- `tenant_isolation` — governs cross-tenant data separation
- `dpdp_compliance_mode` — governs DPDP Act enforcement behaviour

The Policy Authoring Agent must reject any request to modify these with: *"This policy is governed at the platform level and cannot be changed through ALIS. Please contact QUAICU support."*

---

## Section 5 — Workflow Engine Rules

### 5.1 No Approval Chain in Code

Every approval sequence must be a JSON DAG record in `workflow_definitions`. The Temporal runtime walks the graph generically. It does not know what a "grade submission" or "scholarship approval" is.

```python
# ✗ ILLEGAL — approval chain in code
async def submit_grades(grade_data, tenant_id):
    await notify_hod_for_approval(grade_data)
    if hod_approved:
        await notify_exam_controller(grade_data)

# ✓ LEGAL — workflow definition drives everything
workflow_def = await get_workflow_definition("grade_submission", tenant_id)
await workflow_engine.trigger(workflow_def, payload=grade_data)
```

Adding a new approval step at any institution requires one database record. Zero code changes. Zero deployments.

### 5.2 SLA Timers

- Every SLA value lives in the workflow step definition in `workflow_definitions`, not in application code.
- SLA timers must always use absolute `TIMESTAMPTZ` deadlines stored at task creation time.

```python
# ✗ ILLEGAL — relative sleep drifts and cannot be inspected
await workflow.sleep(timedelta(hours=24))

# ✓ LEGAL — absolute deadline stored at task creation
deadline = task.created_at + timedelta(hours=step.sla_hours)
timeout = deadline - workflow.now()  # computed at resume time
```

### 5.3 Temporal Activity Rules

- Every workflow step is a registered Temporal activity with its own retry policy.
- Activities must be idempotent. Re-executing an activity that already succeeded must produce the same result without side effects.
- Side effects that cannot be undone (sending an email, issuing a payment) must use idempotency keys.
- Sagas that wait for multiple signals must have explicit timeout handling. Nothing waits indefinitely.

---

## Section 6 — AI Gateway Rules

### 6.1 All LLM Calls Go Through the Gateway

No LLM call may be made directly from a route handler, service class, or Celery task. Every LLM invocation must go through the AI Gateway.

```python
# ✗ ILLEGAL — direct call
result = await ollama.generate(model='llama3', prompt=prompt)

# ✓ LEGAL — through gateway
draft = await ai_gateway.invoke(
    task_class='DRAFTING',
    prompt=prompt,
    tenant_id=tenant_id
)
```

### 6.2 Task Class Routing

The AI Gateway routes by task class. Never call a 14B model for extraction. Never use the rules engine for reasoning tasks that are LLM-appropriate.

| Task Class | Model Tier & Use Case |
|---|---|
| `EXTRACTION` | Small (1.5B) — slot filling, data parsing, eligibility inputs |
| `DRAFTING` | Medium (7B+) — offer letters, appointment letters, parent alerts |
| `GENERATION` | Medium (7B+) — lecture PPTs, course outlines, CO suggestions |
| `NARRATIVE` | Large (70B / API) — NAAC SSR narratives, IQAC reports |
| `EMBEDDING` | nomic-embed-text — RAG, semantic search, counsellor matching |
| `REASONING` | **Rules Engine ONLY** — never an LLM for policy decisions |

### 6.3 All LLM Output is Typed

- Every AI response must be a validated Pydantic model. No free text stored in the database.
- If Pydantic validation fails, the failure is logged and the task is re-queued for human handling.
- The AI Gateway logs every invocation: model used, tokens consumed, latency, guardrail flags, output hash, outcome.
- `ai_draft_score` and similar draft fields are **never** promoted to final status without explicit human confirmation. Enforce this at the database layer with CHECK constraints.

### 6.4 HITL Gate

- If AI confidence is below the configured threshold, the task routes to the human review queue.
- The confidence threshold is configurable per task class in `tenant_policies`. It is not hardcoded.
- When `confidence < threshold` for descriptive evaluation, the AI score is hidden from the human reviewer to prevent anchoring bias.

---

## Section 7 — State Machine Rules

### 7.1 The Only Legal Path to Change Status

Raw SQL UPDATE statements that change an entity's status field are permanently banned. The state machine class is the only permitted path.

```python
# ✗ ILLEGAL — raw SQL status update
await execute_transaction([
    ("UPDATE applications SET status='ENROLLED' WHERE id=$1", [app_id])
])

# ✗ ILLEGAL — also banned, even in Python
application.status = 'ENROLLED'

# ✓ LEGAL — only path
await application_state_machine.transition(
    entity_id=app_id,
    target_state="ENROLLED",
    actor_id=registrar_id,
    tenant_id=tenant_id
)
```

This ban applies to: application code, migrations, test fixtures, data repair scripts, and seed files. No exceptions.

### 7.2 Transition Validation

- Every state machine class defines its valid transitions explicitly.
- Any attempt to make an invalid transition raises a `StateTransitionError` before touching the database.
- Every valid transition writes to the audit ledger within the same database transaction.
- No transition may be bypassed — including in migrations, test fixtures, or data repair scripts.

### 7.3 Transition Hooks

- State machines may define hooks that run on specific transitions.
- Hooks may publish domain events. They may not call external services directly.
- If a hook fails, the transition must roll back. Partial transitions are not permitted.

---

## Section 8 — RBAC Rules

### 8.1 No Role Name in Business Logic

Role names, permission scopes, and role hierarchy must be read from RBAC tables at runtime. No string literals representing role names in business logic.

```python
# ✗ ILLEGAL — hardcoded role name
if user.role == "registrar":
    allow_enrollment()

# ✓ LEGAL — runtime RBAC check
if await rbac.can(
    user_id, "enrollment", "execute",
    scope_ref=department_id,
    tenant_id=tenant_id
):
    allow_enrollment()
```

### 8.2 Three-Dimensional Role Assignment

Every role assignment has three mandatory dimensions. A role without all three is incomplete:

- **Role** — what the user is (`FACULTY`, `HOD`, `REGISTRAR`, etc.)
- **Scope** — what they can see (department, batch, course, global)
- **Validity window** — when the assignment is active (`valid_from`, `valid_until`)

A `FACULTY` role scoped to `department=CS` cannot see timetables from `department=MBA`. Scope is enforced at every permission check, not just at login.

### 8.3 Quorum Enforcement

- High-stakes operations requiring quorum must enforce it at the Workflow Engine level, not the application layer.
- No role may approve their own quorum. The system must reject self-approval.
- Quorum state is tracked by the Workflow Engine. Each approver acts independently and cannot see the other's decision until both have submitted.

---

## Section 9 — Domain Event Rules

### 9.1 Events Before Dispatch

- Domain events must be persisted to the database before dispatch. Never dispatch an event that is not in the database.
- If a Celery worker crashes mid-processing, Celery Beat retries from the persisted event.
- The `domain_event_handler_log` table tracks which handlers have successfully processed each event. Retries never duplicate work.

### 9.2 Event Naming Convention

Events follow the pattern: `entity.action` in past tense.

- `student.enrolled` — not `student.enroll` or `enrollment.created`
- `grades.submitted` — not `grade.submit`
- `scholarship.awarded` — not `scholarship.award`

Event names are permanent contracts. Once published, they cannot be renamed without a versioning strategy.

### 9.3 Event Payload Rules

- Event payloads must be self-contained. Consumers must not need to re-query the source module to get the data they need.
- Payloads must be versioned. Include a `schema_version` field on every event.
- Sensitive data (bank account numbers, Aadhaar) must never appear in event payloads. Use references (`student_id`), not values.

---

## Section 10 — Idempotency Rules

Idempotency is not optional. Every operation that can be retried must be safe to execute multiple times with the same result.

### 10.1 Payment Webhooks

- Every webhook processor checks `payment_webhook_log` before processing. If the `payment_id` already exists, skip and return 200.
- On startup, ALIS replays any payments in the last 24 hours not in `payment_webhook_log` by polling the Razorpay API.

### 10.2 Domain Event Handlers

- Every domain event handler checks `domain_event_handler_log` before processing.
- Handlers insert their completion record after successful processing.
- If a handler fails, it does not insert a completion record — allowing safe retry.

### 10.3 Temporal Activities

- All Temporal activities must be idempotent by design.
- Use the Temporal workflow ID + activity ID as the natural idempotency key for external calls.
- Never rely on Temporal's at-most-once execution guarantee. Design for at-least-once.

---

## Section 11 — Security and DPDP Rules

### 11.1 Data Classification

All data in ALIS is classified into three tiers. Every engineer must know which tier they are handling:

| Tier | Data & Handling |
|---|---|
| **CRITICAL** | Bank accounts, Aadhaar, salary data, counseling notes. Encrypted at rest. Masked in all UI except authorised roles. MFA required for access. |
| **SENSITIVE** | Student grades, health records, disciplinary records, placement CTC. Role-scoped. Access logged. Never in event payloads. |
| **STANDARD** | Timetables, attendance records, course content. Normal RLS. Standard audit logging. |

### 11.2 DPDP Act Compliance

- Consent must be logged in `consent_records` before writing personal data at any new data collection point.
- `ConsentMiddleware` enforces this for all enrollment, hostel, placement, scholarship, and alumni onboarding endpoints.
- Erasure requests must anonymise PII while preserving aggregate statistical records for NAAC/NIRF.
- Legal holds (active disputes, pending refunds) block erasure until resolved.

### 11.3 Secret Management

- All secrets, API keys, and credentials live in HashiCorp Vault. Never in environment variables, config files, or the codebase.
- Exam question papers are encrypted with AES-256 using paper-specific keys stored in Vault.
- Vault access is logged per operation. Unauthorised access triggers an immediate SMS alert to CoE and Registrar.
- Vault must be in HA mode (3-node Raft) in production. Single-node Vault is not permitted for live exam operations.

### 11.4 MFA Requirements

The following roles must have MFA (TOTP) enforced at login. This is not optional and cannot be toggled off per user:

- Finance Officer
- HR Officer
- Accounts Staff (for payment batch release)
- Controller of Examinations
- Any role with access to salary or bank account data

---

## Section 12 — Code Quality Rules

### 12.1 Test Coverage Requirements

| Layer | Minimum Coverage |
|---|---|
| State machines | 100% — every valid and invalid transition must be tested |
| Policy engine evaluations | 100% — every rule must have a passing and failing test case |
| RBAC permission checks | 95% — every resource/action/scope combination |
| Payment and webhook flows | 100% — including idempotency and failure scenarios |
| Domain event handlers | 95% — including retry and duplicate scenarios |
| AI Gateway guardrails | 100% — including PII leak, prompt injection, low confidence |
| API routes | 90% — all happy paths and primary error cases |

### 12.2 The Policy Change Test

Every policy-driven behaviour must have an integration test that:

1. Sets a policy value in the database
2. Calls the business logic function
3. Verifies the system behaviour changes accordingly
4. Without touching any application code

**If you cannot write this test, the feature is hardcoded. Do not merge.**

### 12.3 Pull Request Requirements

No PR may be merged without:

- All tests passing including the policy change test for any policy-driven feature
- No new hardcoded thresholds, role names, approval chains, or SLA values
- No raw `UPDATE status=` SQL in non-migration files
- Audit ledger write included in the same transaction as any state change
- Tech Lead review if the PR touches: state machines, payment flows, AI gateway, RBAC, or any database migration

### 12.4 What the Linter Must Catch

A custom linter rule must flag and block merges containing:

- String literals matching known role names (`registrar`, `hod`, `faculty`, `finance_officer`) in business logic files
- Numeric literals in eligibility or threshold functions outside of test files
- Raw `UPDATE ... SET status=` in non-migration Python files
- Direct `ollama`, `openai`, or `anthropic` client calls outside of the AI Gateway module
- `import` from another module's service layer in business logic files

---

## Section 13 — Operational Rules

### 13.1 Feature Flags

- All feature flags live in the `feature_flags` table, keyed by feature name and `tenant_id`.
- No `if settings.FEATURE_X_ENABLED` conditionals in application code.
- No `if tenant_id == SPECIFIC_TENANT_ID` conditionals anywhere. Ever.
- Feature flags are read at runtime on every request. Never cached in application memory beyond the configured TTL.

### 13.2 Shadow Mode

- Shadow mode must be completed before any institution goes live.
- In shadow mode, all outbound communications are suppressed. Workflows run in full. No emails, SMS, or WhatsApp are sent.
- Staff compare what ALIS would have done vs. what was done manually and flag divergences.
- Go-live is blocked until divergence on key metrics is below threshold for 5 consecutive days.

### 13.3 Data Migration

- All data migrations use the three-phase pipeline: validate → dry-run → commit.
- Dry-run mode shows what will be created without writing to the database.
- All migrated records are tagged `data_source='migration_pipeline'` in the audit ledger.
- Validation runs every row through the same rules engine before committing.
- Duplicate detection uses Jaro-Winkler similarity before inserting any record.

### 13.4 No Hard Cloud Dependencies

- ALIS must be deployable entirely on-premises on Docker Compose (development/pilot) or K3s (production).
- No feature may require an external cloud API to function. Every external integration (Razorpay, DigiLocker, MSG91) must have a graceful fallback or manual override path.
- The LLM stack (Ollama + local models) is the primary inference path. External APIs (NVIDIA NIM, OpenAI) are fallbacks only.

### 13.5 Observability

- Every API endpoint must emit latency, error rate, and request count metrics.
- Every AI Gateway invocation must emit: model, task class, token count, latency, guardrail result.
- Every SLA breach must emit an observable event, not just an audit log entry.
- The governance agent runs every 6 hours and must have its own observable health check.

---

## Section 14 — The Single Deciding Question

> Before writing any value, condition, sequence, or rule into code — ask:
>
> **"Could a VC, Registrar, or Finance Officer ever need to change this without calling QUAICU?"**
>
> **If yes — it goes in the database. Always.**

---

This is the constitution. It is not a checklist to be completed once. It is the standard against which every line of code in ALIS is measured, every day, by every engineer on the team.

ALIS runs regulated institutions. The rules here protect students whose hall tickets could be wrongly blocked. Faculty whose salaries could be incorrectly computed. Institutions whose NAAC submissions could be rejected. These are not abstract engineering concerns. They are real consequences for real people.

Build accordingly.

---

*QUAICU Solutions Private Limited | Hyderabad, India | Version 1.0 | March 2026 | Confidential*

*Connected to: ALIS_BUILD_PLAN.md | references/architecture.md | references/edge-cases.md*
