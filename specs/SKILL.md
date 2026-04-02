---
name: alis-os
description: Build, extend, debug, and maintain ALIS OS — the Autonomous Institutional Operating System for universities by QUAICU. Use this skill for every task involving the ALIS codebase: implementing new features, fixing bugs, writing migrations, adding edge case resolvers, building frontend components, wiring domain events, updating the policy engine, writing tests, or making any architectural decision. Also use when the user asks how something should work in ALIS, what the correct implementation pattern is, or how to handle a specific university workflow. This skill is the master orchestrator — it tells you which reference file to read for each task type, what invariants can never be broken, and exactly how to sequence your work. Always read this file first before touching any ALIS code.
---

# ALIS OS — Master Build Skill

ALIS is an Autonomous Institutional Operating System for Indian universities. It is a **platform** — one codebase serving many institutions, each with different rules, workflows, and policies stored as data, not code.

Before writing a single line, read this file completely. Then follow the "What to read next" pointers for your specific task.

---

## Reference files — load these for your task

This skill has four reference files. Only load what your task needs.

```
alis-skill/
├── SKILL.md                          ← you are here — read first, always
└── references/
    ├── architecture.md               ← backend, DB, events, RBAC, AI, policies, go-live blocker specs (§21–§33)
    ├── edge-cases.md                 ← 32 edge case resolvers with SQL + Python
    ├── frontend.md                   ← UI shell, design system, agent-canvas sync
    └── gaps.md                       ← product gap epics: E15–E21, accounting, offline, load testing
```

**When to load each reference:**

| Your task | Read |
|---|---|
| Backend feature, migration, domain event, API route | `references/architecture.md` |
| Edge case resolver, failure mode fix, state machine | `references/edge-cases.md` |
| Frontend component, canvas view, agent rail, mobile | `references/frontend.md` |
| Policy engine, workflow engine, feature flags | `references/architecture.md` §10–12 |
| Policy authoring agent (chat → live rule update) | `references/architecture.md` §10b |
| Go-live blockers (parent portal, MFA, shadow mode, WhatsApp, fee versioning, observability, data migration, DPDP) | `references/architecture.md` §21–§28 |
| Platform gaps (API versioning, multi-campus, webhooks, backup, OBE, e-Invoice) | `references/architecture.md` §29–§33 |
| PhD module (E15), re-admission (E17), convocation (E18), quota matrix (E19) | `references/gaps.md` |
| Duplicate merge, Tally/Busy export, regional language, offline PWA, load testing | `references/gaps.md` |
| New module (E14 or beyond) | `references/architecture.md` §5 + §8, then `references/gaps.md` |
| Cross-cutting: audit, multi-tenancy, idempotency | `references/edge-cases.md` EC-CROSS-* |

Load the relevant reference file, read it fully, then proceed. Never guess at patterns — the reference files contain the exact implementations to follow.

---

## The three invariants — never break these

These apply to every task, every file, every line. They override everything else.

### 1. AI proposes. Rules enforce. Humans approve.

```
LLM produces DRAFT output only
    ↓
PolicyEngine validates against tenant_policies DSL
    ↓
Approval queue (if human gate required)
    ↓
Executed + written to AuditLedger
```

The LLM never writes directly to the database. The rules engine never calls the LLM. Humans always have a structured approve/reject/edit path. If what you're building violates this flow, stop and reconsider the design.

### 2. Configuration is data, not code

Every value that differs between institutions lives in the database, read at runtime.

```python
# WRONG — never write this
if tenant_id == "woxsen":
    threshold = 0.80

# RIGHT — always write this
threshold = await policy_engine.get_value("attendance.minimum_threshold", tenant_id)
```

If you catch yourself writing a tenant-specific condition in application code, that condition belongs in `tenant_policies` JSONB.

### 3. Modules never call each other directly

All cross-module communication goes through the Domain Event Bus. A module publishes an event and handles its own cleanup. Other modules subscribe independently.

```python
# WRONG
await academic_service.initialize_student(student_id)  # from admissions code

# RIGHT
await domain_event_bus.publish(DomainEvent(
    event_type="student.enrolled",
    tenant_id=tenant_id,
    payload={...}
))
```

---

## Before you write any code — the five-question checklist

Run through this mentally before every implementation:

1. **Does this belong in the database or in code?** If it's a rule, threshold, or workflow step → database.
2. **Does this cross a module boundary?** If yes → domain event, not a direct call.
3. **Does this touch money, exam results, or student records?** If yes → dual authorization, audit log, idempotent.
4. **Is there an edge case resolver for this scenario?** Check `references/edge-cases.md` before writing your own logic.
5. **Is this gated by a feature flag?** Every new feature that can be turned on/off per institution must be behind `feature_flags.is_enabled(key, tenant_id)`.

---

## Task playbooks — how to execute common tasks

### Implementing a new backend feature

1. Read `references/architecture.md` — specifically §4 (6-layer model), §6 (DB conventions), §8 (events).
2. Check `references/edge-cases.md` — does your feature touch a known failure mode?
3. Write the Alembic migration first — schema before logic.
4. Implement the service layer using `execute_query` / `execute_transaction` helpers only.
5. If the feature crosses modules — publish a domain event, never import the other module.
6. Write the approval workflow in Temporal if human gates are needed.
7. Gate the feature behind a feature flag.
8. Write unit tests + at least one integration test.
9. Add the audit log call — every state change must be recorded.

### Implementing an edge case resolver

1. Read the specific EC-* entry in `references/edge-cases.md` — the SQL schema and Python implementation are already written. Follow them exactly.
2. Run the Alembic migration for any new tables.
3. Implement idempotency first — the handler must be safe to re-run.
4. Wire the Temporal workflow or Celery task.
5. Add the domain event subscription in the relevant module's handler registry.
6. Test the failure path explicitly — not just the happy path.

**Implementation priority order — do P0 cases before anything else:**

```
P0 — implement these before any new features:
  EC-CROSS-03  Multi-tenant data leakage (asyncpg pool fix)
  EC-CROSS-01  Celery idempotency (all domain event handlers)
  EC-CROSS-02  Audit ledger RLS (PostgreSQL row-level security)
  EC-ADM-05    Razorpay webhook drop (payment dispute portal)
  EC-EXM-01    Question paper dispatch failure (offline vault fallback)
  EC-EXM-05    AI evaluation hallucination (draft score + faculty confirm)

P1 — implement in sprint 2:
  EC-ADM-03    Ghost withdrawal (reporting gate + biometric)
  EC-ADM-01    Identity mismatch (Jaro-Winkler fuzzy match)
  EC-ACA-01    Global recalibration trigger
  EC-ACA-03    Mass bunk anomaly filter
  EC-FIN-01    DBT scholarship exemption ledger
  EC-EXM-03    Revaluation vs supplementary resolver
  EC-SS-01     Weaponized grievance spike detector
  EC-CROSS-04  SLA timer drift (absolute timestamps in Temporal)
```

### Building a frontend component

1. Read `references/frontend.md` — the full design system, layout rules, and component specs.
2. Identify which role this component serves — density and data differ per role.
3. Use Zustand for all canvas state — never local component state for navigation.
4. If the component responds to agent commands — wire it to `useAgentCanvasSync`.
5. Every data table on mobile becomes a card list — never force horizontal scroll.
6. Test in both light and dark mode before considering it done.

### Implementing the Policy Authoring Agent (PAA)

The PAA lets an authorised user type a natural-language policy change into the agent chat and have it route through approval to the live rules engine — with the AI engine context automatically refreshed on approval.

Read `references/architecture.md` §10b before starting. The full implementation — all four layers, all classes, all SQL, the risk tier map, and the exact conversation flow — is specified there. Build it in this exact sequence:

**Sequence:**
1. `PolicyConflictDetector.check()` — pure data queries, no LLM, run first always
2. `PolicyImpactCalculator.calculate()` — counts affected students/staff per change
3. `PolicyAuthoringAgent.translate_intent()` — the single LLM call (`EXTRACTION` task class, small model tier, `PolicyChangeDraft` Pydantic output only)
4. Route via `POLICY_RISK_TIERS` map → E13 Dynamic Workflow (approval card must include impact report + conflict warnings)
5. `broadcast_policy_update` Celery task → invalidates Redis policy cache, regenerates AI system prompt context for the tenant

**Five rules that govern every line of PAA code:**
- `PolicyChangeDraft.status` is always `'DRAFT'` when created — never `'APPROVED'`
- `PolicyEngine.evaluate()` only reads `status='APPROVED'` policies — no bypass path exists
- The DSL YAML is assembled deterministically from the `PolicyChangeDraft` struct — never LLM-generated YAML
- `approver == "QUAICU_ONLY"` policies (`audit_ledger_retention`, `tenant_isolation`, `dpdp_compliance_mode`, `rbac_system_roles`) return an error to the user and create no draft
- `broadcast_policy_update` runs as a Celery task after approval — never inline in the approval handler

**New file to create:** `ALIS/server/core/policy_authoring_agent.py`
Contains: `PolicyAuthoringAgent`, `PolicyConflictDetector`, `PolicyImpactCalculator`, `broadcast_policy_update`, `POLICY_RISK_TIERS`

### Writing a database migration

```python
# Every migration must follow this pattern exactly

def upgrade():
    # 1. Schema change
    op.add_column('table_name', sa.Column(...))

    # 2. Add RLS policy if this is a new tenant-scoped table
    op.execute("""
        ALTER TABLE new_table ENABLE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON new_table
            USING (tenant_id::text = current_setting('alis.current_tenant'));
    """)

    # 3. Add composite index — always (tenant_id, query_field), never query_field alone
    op.create_index('ix_new_table_tenant_field', 'new_table', ['tenant_id', 'field_name'])

def downgrade():
    op.drop_index('ix_new_table_tenant_field')
    op.drop_column('table_name', 'column_name')
```

Never use raw SQL in application code. Migrations only via Alembic.

---

## The things you must never do

Read this list before every task. These are hard stops.

```
NEVER hardcode a tenant-specific value — use PolicyEngine
NEVER call another module's service class directly — use domain events
NEVER use SimpleConnectionPool — it is being migrated to asyncpg
NEVER use Python eval() for policy expressions — use asteval
NEVER let LLM output go directly to the database — always validate with Pydantic first
NEVER use the LLM for eligibility, progression, or penalty decisions — rules engine only
NEVER write migrations in raw SQL — use Alembic
NEVER delete records — use status='ARCHIVED' or status='ANNULLED'
NEVER skip the audit log — every state change must be recorded with policy_version
NEVER let a policy with status='DRAFT' be evaluated — APPROVED only
NEVER store question paper keys in .env — use HashiCorp Vault
NEVER let an approval task run forever — every gate has SLA + escalation
NEVER skip the tenant SET LOCAL on database connections
NEVER trust LLM confidence > 0.8 for high-stakes decisions — always HITL
NEVER send parent/student alerts without checking the mass anomaly filter first
NEVER apply grace marks to students on the top-1% merit list
NEVER process a payment webhook without idempotency check first
```

---

## Current build status — what exists, what doesn't

| Epic | Module | Status |
|---|---|---|
| E01–E13 | Core platform (Auth through Dynamic Process Engine) | ✅ All complete |
| **E14** | **Regulatory & Accreditation** | ✅ Built |
| **E15** | **PhD / Doctoral Research** | ✅ Built |
| **E16** | **Parent / Guardian Portal** | ❌ Not built — go-live blocker |
| **E17** | **Re-admission & Credit Transfer** | ✅ Built |
| **E18** | **Convocation Management** | ✅ Built |
| **E19** | **Quota Seat Matrix Engine** | ✅ Built |
| **E20** | **OBE / CO-PO Mapping** | ✅ Built |
| **E21** | **DPDP Consent Management** | ✅ Built |
| **PAA** | **Policy Authoring Agent** | ✅ Built |
| **FE** | **React Frontend** | In progress (P15) |
| **Go-live blockers** | WhatsApp, E16 (Parent Portal) | ❌ Not built |

**1055 tests passing** (883 data-plane + 172 SaaS). Do not break this. Run the full test suite before every commit.

**Remaining build order for go-live readiness:**
1. Fix P0 bugs (connection pool, Vault, LLM model tier) — see §14
2. Go-live blockers in this order: WhatsApp → E16 (Parent Portal)

---

## Known P0 bugs — fix these before adding features

These are in production-blocking state. Address them in the order listed.

**1. Connection pool — CRITICAL DATA CORRUPTION RISK**
`psycopg2.pool.SimpleConnectionPool` is not async-safe. Under concurrent load, two coroutines can share a connection. File: `ALIS/server/db_service.py`. Migrate to `asyncpg.create_pool()`. The `execute_query` / `execute_transaction` helpers are the correct abstraction — only the driver underneath changes.

**2. LLM model tier — WRONG MODEL FOR DRAFTING**
`qwen2.5:1.5b` is used for all tasks including offer letters and parent alerts. Pull `llama3.1:8b` via Ollama. Route `DRAFTING` and `GENERATION` task classes to 8B. Keep 1.5B for `EXTRACTION` only.

**3. HashiCorp Vault — MISSING FOR QUESTION PAPERS**
Exam question papers require AES-256 encryption with CoE-only decrypt access and a full access audit log. HashiCorp Vault is not yet in the Docker Compose stack. Add it before any exam module goes to a pilot institution.

**4. RBAC scope on role assignments — VERIFY MIGRATION 0001**
Check that `role_assignments` has a `scope_id` column. Without it, HODs get institution-wide access instead of department-scoped. If missing, add it in a new migration before onboarding any multi-department institution.

---

## File locations — where things live

```
ALIS/server/
├── main.py                    # FastAPI app, middleware, routers, health probes
├── worker.py                  # Celery app + Beat schedule
├── db_service.py              # DB pool, execute_query, execute_transaction
├── core/
│   ├── settings.py            # All config (Pydantic Settings)
│   ├── domain_events.py       # Event bus + handler registry
│   ├── ai_gateway.py          # LLM routing, guardrails, HITL
│   ├── security.py            # TenantMiddleware, RBAC, JWT
│   ├── policy_engine.py       # DSL interpreter — rules-as-data
│   ├── feature_flags.py       # Institutional feature flag system
│   ├── llm_router.py          # Task class → model tier → provider
│   ├── audit_ledger.py        # Immutable hash-chain audit log
│   └── plugin_registry.py     # Plugin installation + event wiring
├── modules/
│   ├── admissions/            # E04
│   ├── academics/             # E05
│   ├── examinations/          # E06
│   ├── finance/               # E07
│   ├── hr/                    # E08
│   ├── student_services/      # E09
│   ├── communication/         # E10
│   ├── reporting/             # E11
│   ├── alumni/                # E12
│   ├── workflow_engine/       # E13
│   └── regulatory/            # E14 — CREATE THIS
└── api/
    └── admissions_router.py   # 87-route example

ALIS/migrations/versions/
├── 0001_foundation.py         # auth, users, RBAC
├── 0002–0012_*.py             # core module tables
├── 0013_indexes.py            # performance indexes
└── 0014_admissions.py         # full admissions schema (40+ tables)

web/src/                       # React frontend
├── shell/                     # ALISShell, IconNav, PrimaryCanvas, AgentRail
├── views/                     # one component per module view
├── components/                # Badge, StatCard, SLABar, DataTable, etc.
├── store/alis.store.ts        # Zustand: canvas + agent + chat state
└── hooks/                     # useALISRole, useAgentCanvasSync, useQuickActions
```

---

## How to handle ambiguous tasks

When the user gives you a task that could be implemented multiple ways, always choose the approach that:

1. Puts the most logic in data (policies, workflow DAGs, feature flags) rather than code.
2. Keeps modules decoupled via events.
3. Makes the happy path and the failure path equally explicit.
4. Leaves the audit trail complete.

If genuinely unsure, ask one specific clarifying question before proceeding. Never ask more than one question at a time.

---

## Glossary — terms used throughout the codebase

| Term | Meaning |
|---|---|
| Tenant | One university institution — has its own PostgreSQL schema |
| Principal | A user or service account — always assigned roles, never permissions directly |
| PolicyEngine | The rules-as-data DSL interpreter — reads `tenant_policies` JSONB at runtime |
| Domain Event | The only way modules communicate — published to Kafka/Redpanda, consumed by handlers |
| HITL | Human-in-the-loop — an approval task in the queue requiring human decision |
| SLA | The time window before an approval task auto-approves or escalates |
| Temporal | Durable workflow engine — used for any process that spans more than one request |
| CanvasAction | A structured instruction the agent sends to the frontend dashboard |
| PAA | Policy Authoring Agent — the capability that lets users update live policies via chat |
| CoE | Controller of Examinations — the role with authority over all exam operations |
| SGPA / CGPA | Semester GPA / Cumulative GPA — computed by the Examinations module |
| API Score | Academic Performance Indicator score — UGC framework for faculty CAS promotions |
| CAS | Career Advancement Scheme — UGC-mandated faculty promotion system |
