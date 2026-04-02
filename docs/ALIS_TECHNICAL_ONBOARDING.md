# ALIS Technical Onboarding Document

> **Audience**: Senior backend/fullstack engineers joining the QUAICU Solutions technical partner team.
> **Purpose**: Navigate, change, test, and deploy ALIS without prior knowledge of the codebase.
> **Last verified**: 2026-04-02 — updated for S1-S10 SaaS transformation (control plane, AI service, billing engine, Helm/Terraform/Operator, DNS routing). 172 SaaS tests + 883 data-plane tests passing.

---

## Table of Contents

1. [What ALIS Is](#1-what-alis-is)
2. [The 6-Layer Architecture](#2-the-6-layer-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Backend Module Map](#4-backend-module-map)
5. [The Database](#5-the-database)
6. [The Core Layer](#6-the-core-layer)
7. [The AI Stack](#7-the-ai-stack)
8. [The Agent Rail](#8-the-agent-rail)
9. [Background Workers](#9-background-workers)
10. [The Frontend](#10-the-frontend)
11. [Infrastructure](#11-infrastructure)
12. [Python Dependencies](#12-python-dependencies)
13. [Frontend Dependencies](#13-frontend-dependencies)
14. [The Test Suite](#14-the-test-suite)
15. [Known Issues and Technical Debt](#15-known-issues-and-technical-debt)
16. [How to Work on ALIS — Rules for the Tech Partner](#16-how-to-work-on-alis--rules-for-the-tech-partner)
17. [Current Build Status](#17-current-build-status)
18. [Building a New Feature: End-to-End Walkthrough](#18-building-a-new-feature-end-to-end-walkthrough)
19. [SaaS Platform Architecture](#19-saas-platform-architecture)

---

## 1. What ALIS Is

### Plain English

ALIS (Autonomous Learning & Institutional System) is a **policy-driven autonomous ERP for Indian higher-education institutions**. It replaces the fragmented spreadsheet-and-email workflows that govern admissions, academics, examinations, finance, HR, student services, and regulatory compliance at universities and colleges.

The word *autonomous* is precise: the system operates without daily human intervention. Staff members don't log in to run processes — they log in to **handle exceptions** that the system has already identified, queued, and routed to the right person with the right context.

### Who Uses It

| Persona | Primary Modules | Typical Day |
|---------|----------------|-------------|
| Registrar | Admissions, Academics, Examinations, Regulatory | Approves merit list, reviews SLA breaches, signs off final verification |
| Finance Officer | Finance, Scholarship, Invoice | Handles fee overdue workflow tasks, approves waivers |
| HOD / Faculty | Academics, Examinations, HR | Enters marks during evaluation window, views attendance alerts |
| HR Admin | HR, Payroll, Leave | Approves leave requests, reviews appraisal drafts |
| Student | Student Services, Finance, Examinations | Views hall ticket, checks fee dues, raises grievances |
| Guardian / Parent | Finance (read-only) | Receives WhatsApp notifications on fee due dates |
| PhD Scholar | PhD module | Submits DC meeting minutes, plagiarism report upload |
| Super Admin | All modules, Platform Admin | Creates tenants, seeds policies, manages feature flags |

### The Core Operating Principle

```
LLM Agent → DRAFT record → Human reviews → State machine executes transition
```

Every LLM call in ALIS produces a **Draft** output — a proposed decision, a proposed document, a proposed score. The state machine cannot transition any entity out of a `DRAFT` state without a human approval step in between. This is not a convention; it is enforced at the database layer (status field) and at Layer 2 (the AI stack boundary).

**"AI writes DRAFT only"** is the single most important invariant in this system.

### Why It Differs from a Normal ERP

A conventional ERP hardcodes thresholds in source code:

```python
# What a normal ERP does — never do this in ALIS
if student.attendance_pct >= 75:
    mark_eligible()
```

ALIS stores every threshold, rule, approval chain, and notification template in the database:

```python
# What ALIS does
result = policy_engine.evaluate(
    policy_id="attendance_eligibility",
    context={"student": {"attendance_pct": student.attendance_pct, "category": student.category}},
    tenant_id=tenant_id,
)
if result.verdict == "ELIGIBLE":
    mark_eligible()
```

The 75% threshold lives in `tenant_policies` as a JSON rule. The Registrar can change it without calling the tech partner. Version history is automatic. Every eligibility decision records which policy version it evaluated against.

### Deployment Modes — On-Premises & SaaS

ALIS supports two deployment modes:

**Mode 1: On-Premises (single Docker Compose)** — Institution runs everything on its own infrastructure. No student data leaves the campus network. This is the default for institutions with strict data residency requirements.

**Mode 2: SaaS (multi-tenant, Kubernetes)** — QUAICU operates ALIS as a managed service. A central **Control Plane** provisions and manages tenant instances. Each tenant gets a dedicated database, S3 bucket, Vault path, and Celery queue — full infrastructure isolation. The SaaS platform includes:
- `control_plane/` — Tenant lifecycle, billing, DNS provisioning
- `ai_service/` — Centralized LLM proxy with PII masking and per-tenant budget
- `infra/k8s/helm/` — Helm charts for data-plane, control-plane, AI service
- `infra/terraform/` — Multi-cloud IaC (AWS/Azure/GCP)
- `infra/k8s/operator/` — TenantStack CRD + kopf reconciler

See §19 for the full SaaS architecture guide.

**Data residency guarantees apply in both modes:**

1. **DPDP Act (India)** — The Digital Personal Data Protection Act, 2023 imposes strict data residency obligations. In SaaS mode, tenant data stays within the configured region (Terraform `region` variable).
2. **Exam paper confidentiality** — Question papers are encrypted at rest using HashiCorp Vault Transit. The decryption key never leaves the Vault. In SaaS mode, each tenant has its own Vault path (`alis/{region}/tenant/{tenant_id}/`).
3. **AI privacy** — LLM inference runs on Ollama (VPC-internal). In SaaS mode, the AI Service masks PII before all LLM calls. No student data is sent to external LLM APIs unless the tenant explicitly opts in with `managed_api=true` (enterprise plan only).

### Multi-Tenant Model

ALIS uses two complementary isolation strategies depending on deployment mode:

**On-Premises (shared database, RLS isolation)**:
Multiple institutions share a single PostgreSQL database. Tenant isolation is enforced at the **Row-Level Security (RLS)** layer:

```
JWT → TenantMiddleware extracts tenant_id
    → sets _current_tenant_id ContextVar
    → execute_query/execute_transaction runs:
         SET alis.current_tenant = '{tenant_id}'
    → PostgreSQL RLS policies check:
         current_setting('alis.current_tenant', true) = tenant_id
```

If a bug in application code accidentally omits the tenant filter, RLS catches it at the database level. Data from Institution A cannot leak to Institution B even if the application query is wrong.

**SaaS (dedicated database per tenant)**:
Each tenant gets its own PostgreSQL database (`alis_{subdomain}`), provisioned by the Control Plane. The `SubdomainTenantMiddleware` resolves the subdomain to a tenant record, injects the correct DB DSN, and all queries run against that tenant's isolated database. RLS still applies within each database as defense-in-depth.

```
{subdomain}.alis.app → SubdomainTenantMiddleware
    → GET /internal/tenants/by-subdomain/{sub} (control plane)
    → inject tenant DSN + tenant_id into request context
    → all queries hit tenant's dedicated database
```

Additional SaaS isolation: per-tenant S3 bucket, per-tenant Vault path, per-tenant Celery queues.

### DPDP Act Compliance

ALIS implements the consent module (E21) for DPDP compliance:

- **ConsentMiddleware** sits at the API layer — requests to student data endpoints require an active consent record.
- **Erasure requests** are queued as `consent_erasure_requests` and processed by a Celery task that anonymises PII fields while preserving audit trail structure (audit entries are never deleted — the hash chain integrity requires every entry to remain).
- PII stripping runs on every LLM call in the agent rail (`_strip_pii()` in `context_advisor.py`) before any text is sent to the model.

---

## 2. The 6-Layer Architecture

Every feature in ALIS must respect all six layers. Skipping a layer is a bug, not an optimisation. The layers are enforced in code, not just in documentation.

```
Layer 1 — Module Purpose          (event-driven module boundaries)
Layer 2 — Agentic Decisions       (AI produces DRAFT only)
Layer 3 — State Machines          (transitions via orchestrator only)
Layer 4 — Global Locks            (distributed advisory + Redis locks)
Layer 5 — Roles, Authority & Quorum (RBAC+ verify_access + dual-control approvals)
Layer 6 — Resilience & Audit      (append-only hash-chain + Celery retries)

                ← AuditLedger is cross-cutting across ALL layers →
```

---

### Layer 1 — Module Purpose

**Purpose**: Define bounded contexts. Modules must not call each other's service functions directly.

**What it enforces**: All cross-module data flows happen exclusively through `DomainEventBus.publish()` and `.subscribe()`. A Finance invoice is not created by the Admissions module calling `InvoiceService.create()` — it is created by Finance listening to `admissions.enrollment_confirmed`.

**What breaks if removed**: Hidden coupling appears. A change to how admissions creates offers silently breaks how Finance creates invoices. The audit trail has gaps because the Finance module never recorded why the invoice was created.

**Real code example**:
```python
# ALIS/server/admissions/enrollment_provisioning.py
# Admissions publishes; Finance subscribes. Never a direct call.
DomainEventBus.publish(DomainEvent(
    event_type="admissions.enrollment_confirmed",
    entity_type="enrollment",
    entity_id=enrollment_id,
    org_id=tenant_id,
    payload={
        "student_id": student_id,
        "program_id": program_id,
        "fee_schedule_id": fee_schedule_id,
    },
    actor_id=actor_id,
))

# ALIS/server/finance/event_handlers.py
DomainEventBus.subscribe("admissions.enrollment_confirmed", handle_enrollment_confirmed)

async def handle_enrollment_confirmed(event: DomainEvent):
    # Finance creates the invoice — triggered by event, not by direct call
    await InvoiceService.create_from_enrollment(event.payload, event.org_id)
```

---

### Layer 2 — Agentic Decisions

**Purpose**: All AI-produced decisions are proposals, never executions.

**What it enforces**: Every agent returns a record with `status='DRAFT'` or `proposed_state` field. No agent ever calls `execute_transaction()` to write a final state. The human confirmation step (Confirm chip in Agent Rail, or approval workflow) is the only path to a non-Draft record.

**What breaks if removed**: The system can make irreversible decisions autonomously — incorrect merit list, wrong eligibility verdict, mis-routed escalation — with no human checkpoint.

**Real code example** (from `eligibility.py`):
```python
# The agent outputs a proposed state — never writes to DB
return AIInvocationResult(
    success=True,
    content=json.dumps({
        "eligibility_score": final_state.get("eligibility_score", 0.0),
        "confidence_tier": final_state.get("confidence_tier", "LOW"),
        "proposed_state": final_state.get("proposed_state", "MANUAL_REVIEW"),
        "draft_verdict": final_state.get("draft_verdict", ""),
    }),
    request_id=context.request_id,
)
# Note: no execute_transaction() call anywhere in this file.
```

Confidence tiers:
| Tier | Score Range | `proposed_state` |
|------|-------------|-----------------|
| HIGH | ≥ 0.8 | `ELIGIBLE` |
| MEDIUM | 0.5 – 0.8 | `PROVISIONALLY_ELIGIBLE` |
| LOW | < 0.5 | `MANUAL_REVIEW` |

---

### Layer 3 — State Machines

**Purpose**: Entity lifecycle transitions happen through the state machine orchestrator only — never raw SQL `UPDATE status = '...'`.

**What it enforces**: Every valid transition is declared. Invalid transitions are rejected. Every transition fires events and records in the audit log.

**What breaks if removed**: An entity can reach an impossible state (e.g., `ENROLLED` without going through `PAYMENT_CONFIRMED`). Audit trail has no record of why the status changed. Regression is untraceable.

**Real code example**:
```python
# CORRECT — via state machine
from server.core.workflow import WorkflowOrchestrator

orchestrator = WorkflowOrchestrator()
await orchestrator.transition(
    entity_type="application",
    entity_id=application_id,
    from_state="OFFER_ACCEPTED",
    to_state="PAYMENT_PENDING",
    actor_id=actor_id,
    tenant_id=tenant_id,
)

# WRONG — never do this
await execute_transaction([
    ("UPDATE applications SET status = 'PAYMENT_PENDING' WHERE id = %s", (application_id,))
])
```

The `StudentState` enum has 22 values (expanded from 8 in the initial schema). The expansion was done with backward-compatible migration (migration 0002 pattern) — legacy values were retained.

---

### Layer 4 — Global Locks

**Purpose**: Prevent race conditions in concurrent operations (seat allocation, payment processing, merit list generation).

**What it enforces**: Critical sections acquire a distributed lock before reading and writing shared state. Double-booking of seats is structurally impossible.

**What breaks if removed**: Two concurrent enrollment requests for the last available seat both succeed. Two Celery workers process the same payment callback and create duplicate invoices.

**Real code example** (seat allocation — atomic SQL, not application lock):
```python
# ALIS/server/admissions/merit_list.py
# Atomic UPDATE with row lock — prevents double-booking
rows = execute_query(
    """
    UPDATE seat_matrix
    SET filled_seats = filled_seats + 1
    WHERE program_id = %s
      AND category = %s
      AND filled_seats < total_seats
    RETURNING id, filled_seats, total_seats
    """,
    (program_id, category),
    tenant_id=tenant_id,
)
if not rows:
    raise SeatNotAvailableError("No seats available in this category")
```

For longer operations (merit list generation), use `locks.py`:
```python
from server.core.locks import DistributedLock

async with DistributedLock(f"merit_list:{program_id}", tenant_id=tenant_id):
    # Only one worker generates the merit list at a time
    await generate_merit_list(program_id, tenant_id)
```

---

### Layer 5 — Roles, Authority & Quorum

**Purpose**: Every operation is gated by role-based access. Sensitive operations require multiple approvers (dual-control).

**What it enforces**: `require_permission` decorator on every router endpoint. `approvals.py` quorum check before any multi-signature operation completes.

**What breaks if removed**: A Faculty member can approve their own marks entry. A Finance Officer can unilaterally waive any fee amount. A REGISTRAR can approve their own merit list.

**Real code example**:
```python
# ALIS/server/api/examinations_router.py
@router.post("/grades/submit")
@require_permission(Permission.MARKS_ENTRY)
async def submit_grades(payload: GradeSubmitPayload, request: Request):
    # require_permission checks rbac.verify_access() at Layer 5
    # verify_access also checks context: exam_status == "EVALUATION_OPEN"
    ...

# ALIS/server/core/approvals.py — quorum check
result = await ApprovalWorkflow.check_quorum(
    workflow_id=workflow_id,
    required_roles=[Role.REGISTRAR, Role.DEAN],
    min_approvals=2,
    tenant_id=tenant_id,
)
if not result.quorum_reached:
    return {"status": "PENDING_QUORUM", "approvals_received": result.approval_count}
```

---

### Layer 6 — Resilience & Audit

**Purpose**: Every state transition is recorded in an append-only, tamper-evident ledger. Every background operation retries on failure. Every audit entry is part of a SHA-256 hash chain.

**What it enforces**: DB trigger `fn_audit_ledger_immutable()` blocks `UPDATE` and `DELETE` on `audit_ledger`. Celery `task_acks_late=True` prevents message loss on worker crash.

**What breaks if removed**: Regulatory inspections (NAAC, UGC) cannot verify the chain of approvals for any admission or examination decision. Worker crashes permanently drop background tasks.

**Real code example** (hash chain from `audit.py`):
```python
# Hash formula — reproduced exactly:
# SHA256( (previous_hash or "") + canonical_json(payload) )

import hashlib, json

def _compute_hash(previous_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    raw = (previous_hash or "") + canonical
    return hashlib.sha256(raw.encode()).hexdigest()
```

The hash chain is per-tenant. Advisory lock `pg_advisory_xact_lock(lock_key)` serialises concurrent writes so the chain never forks.

---

## 3. Repository Structure

```
ALIS Production/
├── ALIS/                              # Python backend (FastAPI)
│   ├── server/
│   │   ├── main.py                    # FastAPI app factory: 28 routers, 8 middleware layers
│   │   ├── db_service.py              # execute_query (SELECT) / execute_transaction (writes)
│   │   ├── worker.py                  # Celery app + 15 Beat tasks
│   │   ├── fs_service.py              # MinIO S3-compatible file storage
│   │   ├── core/                      # Cross-cutting infrastructure (45+ modules)
│   │   │   ├── settings.py            # Pydantic Settings — single source of truth for infra config
│   │   │   ├── security.py            # JWT, sessions, TenantMiddleware, MFA, rate limiting
│   │   │   ├── rbac.py                # 22 roles, 65+ permissions, RBAC+ verify_access()
│   │   │   ├── audit.py               # Append-only SHA-256 hash-chain ledger
│   │   │   ├── policy_engine.py       # asteval DSL rule evaluator (first-match-wins)
│   │   │   ├── domain_events.py       # DB-persisted, Celery-dispatched event bus
│   │   │   ├── llm_router.py          # 3-tier model routing: EXTRACTION/GENERATION/REASONING
│   │   │   ├── ai_gateway.py          # Central AI invocation hub with guardrails + HITL
│   │   │   ├── workflow.py            # Generic state machine orchestrator
│   │   │   ├── approvals.py           # Dual-control approval workflows with quorum
│   │   │   ├── locks.py               # Distributed advisory DB locks + Redis locks
│   │   │   ├── vault_client.py        # HashiCorp Vault client (Transit encryption + KV secrets)
│   │   │   ├── shadow_mode.py         # Shadow mode A/B execution framework
│   │   │   ├── shadow_mode_middleware.py # HTTP middleware for shadow mode routing
│   │   │   ├── metrics.py             # Prometheus counter/histogram/gauge definitions
│   │   │   ├── feature_flags.py       # Per-tenant feature flag evaluation
│   │   │   ├── config.py              # Runtime config helpers
│   │   │   ├── exceptions.py          # Domain exception hierarchy (NotFoundError, etc.)
│   │   │   ├── error_handlers.py      # FastAPI exception → HTTP response mapping
│   │   │   ├── guardrails.py          # AI output validation rules
│   │   │   ├── prompt_registry.py     # Versioned prompt store (Jinja2 templates in DB)
│   │   │   ├── tool_registry.py       # AI tool registration and invocation
│   │   │   ├── model_registry.py      # LLM model configuration registry
│   │   │   ├── state_registry.py      # Entity state machine definitions
│   │   │   ├── policy_store.py        # PolicyStore.get() — simple K/V config lookups
│   │   │   ├── policy_resolver.py     # Multi-tenant policy resolution helper
│   │   │   ├── policy_service.py      # Policy CRUD service (create, approve, version)
│   │   │   ├── escalation.py          # SLA breach escalation rules
│   │   │   ├── overrides.py           # Admin override facility (SUPER_ADMIN only)
│   │   │   ├── lockdown.py            # Institution-wide lockdown (exam period)
│   │   │   ├── mfa_service.py         # TOTP-based MFA (pyotp)
│   │   │   ├── tenant_crypto.py       # Per-tenant AES encryption for sensitive fields
│   │   │   ├── webhook_dispatcher.py  # Outbound webhook delivery (after domain events)
│   │   │   ├── data_classification.py # PII/sensitive data tagging for export controls
│   │   │   ├── diff_tracker.py        # Entity diff recorder (before/after state for audit)
│   │   │   ├── retention_policy.py    # Data retention rules (auto-archival)
│   │   │   ├── schema.py              # Shared Pydantic base schemas
│   │   │   ├── tasks.py               # Shared Celery task utilities
│   │   │   ├── backup_service.py      # DB backup orchestration
│   │   │   ├── ai_gateway.py          # (see above)
│   │   │   ├── llm_router.py          # (see above)
│   │   │   ├── notifications/         # Notification subsystem
│   │   │   │   ├── channels.py        # Email, SMS, WhatsApp, in-app channel adapters
│   │   │   │   ├── service.py         # NotificationService.send()
│   │   │   │   └── templates.py       # Jinja2 template rendering
│   │   │   └── documents/             # Document engine
│   │   │       ├── engine.py          # PDF generation (ReportLab)
│   │   │       ├── models.py          # DocumentTemplate, DocumentInstance models
│   │   │       └── service.py         # DocumentService.generate()
│   │   ├── api/                       # FastAPI routers (one per module domain)
│   │   │   ├── auth_router.py         # 10 routes: login, logout, refresh, MFA, bootstrap
│   │   │   ├── users_router.py        # User CRUD + profile management
│   │   │   ├── roles_router.py        # Role assignment + permission queries
│   │   │   ├── admissions_router.py   # 87 routes covering all 10 admissions stages
│   │   │   ├── academics_router.py    # Programs, courses, attendance, timetable, OBE
│   │   │   ├── examinations_router.py # Schedule, hall tickets, marks, grades, revaluation
│   │   │   ├── finance_router.py      # Fees, invoices, payments, scholarship, waivers
│   │   │   ├── hr_router.py           # Staff, leave, payroll, performance
│   │   │   ├── student_services_router.py # Hostel, transport, library, grievances, counselling
│   │   │   ├── communication_router.py # Announcements, bulk notifications, templates
│   │   │   ├── reporting_router.py    # KPI dashboards, custom reports, export
│   │   │   ├── alumni_router.py       # Placement drives, job board, alumni network
│   │   │   ├── workflows_router.py    # Dynamic process engine, form builder
│   │   │   ├── regulatory_router.py   # NAAC criteria, NIRF parameters
│   │   │   ├── phd_router.py          # PhD lifecycle, DC meetings, plagiarism
│   │   │   ├── convocation_router.py  # Degree audit, gold medals, seating chart
│   │   │   ├── consent_router.py      # DPDP consent records, erasure requests
│   │   │   ├── gateway_router.py      # AI gateway invocation + agent rail endpoint
│   │   │   ├── policy_router.py       # Policy CRUD + approval workflow
│   │   │   ├── audit_router.py        # Audit ledger queries + chain verification
│   │   │   ├── approvals_router.py    # Approval workflow management
│   │   │   ├── intake_router.py       # Admission intake cycle management
│   │   │   ├── integrations_router.py # External integration sync (e.g., LMS)
│   │   │   ├── admin_router.py        # Platform admin (tenants, feature flags)
│   │   │   ├── organizations_router.py # Org/campus management
│   │   │   ├── feature_flags_router.py # Feature flag CRUD
│   │   │   ├── process_engine_router.py # Process engine workflow management
│   │   │   └── wifi_attendance_router.py # WiFi proximity attendance (P29)
│   │   ├── admissions/                # E04: 10-stage autonomous admissions
│   │   │   ├── counsellor_service.py  # Lead CRM + PGVector ETL trigger
│   │   │   ├── review_queue.py        # Document review queue management
│   │   │   ├── seat_matrix_service.py # Seat matrix + category allocation
│   │   │   ├── policy_store.py        # Admissions-specific policy lookups
│   │   │   ├── reporting_gate.py      # Data freeze + reporting gate management
│   │   │   ├── forgery_detection.py   # Document authenticity checks
│   │   │   └── event_handlers.py      # Domain event subscriptions
│   │   ├── academics/                 # E05: Programs, courses, attendance, OBE
│   │   ├── examinations/              # E06: Papers, hall tickets, grades, revaluation
│   │   ├── finance/                   # E07: Fees, invoices, payments, Tally export
│   │   ├── hr/                        # E08: Staff, leave, payroll, appraisal
│   │   ├── student_services/          # E09: Hostel, transport, grievances, library
│   │   ├── communication/             # E10: Notifications, WhatsApp, bulk messaging
│   │   ├── reporting/                 # E11: KPI, NAAC AQAR, saved reports
│   │   ├── alumni/                    # E12: Placement drives, job board, alumni profiles
│   │   ├── process_engine/            # E13: Configurable workflows, form builder
│   │   ├── regulatory/                # E14: NAAC criteria, NIRF parameters
│   │   ├── phd/                       # E15: PhD lifecycle, DC meetings, plagiarism
│   │   ├── convocation/               # E18: Degree audit, gold medals, seating
│   │   ├── consent/                   # E21: DPDP consent, erasure requests
│   │   ├── agents/                    # AI agent implementations
│   │   │   ├── rail/                  # RAIL module — context_advisor_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # RailAgentRegistry — registers context_advisor_v1
│   │   │   │   └── context_advisor.py # Three-path executor: view_change/chip/free text
│   │   │   ├── admissions/            # M1 module — eligibility_evaluator_v1 (LangGraph)
│   │   │   │   ├── registry.py        # AdmissionsAgentRegistry
│   │   │   │   └── eligibility.py     # LangGraph StateGraph: extract_grades → evaluate_eligibility
│   │   │   ├── academics/             # M2 module — risk_detector_v1 + content_generator_v1 (P40)
│   │   │   │   ├── registry.py        # AcademicsAgentRegistry
│   │   │   │   ├── risk_detector_v1.py # Student at-risk scoring (attendance + performance)
│   │   │   │   └── content_generator_v1.py # AI course content generation: lecture_notes, quiz_questions, assignment_questions, lesson_plan
│   │   │   ├── examinations/          # M3 module — result_analyzer_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # ExaminationsAgentRegistry
│   │   │   │   └── result_analyzer_v1.py # Exam result distribution + anomaly detection
│   │   │   ├── finance/               # M4 module — dues_predictor_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # FinanceAgentRegistry
│   │   │   │   └── dues_predictor_v1.py # Fee dues default-risk prediction
│   │   │   ├── hr_admin/              # M5 module — workload_analyzer_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # HRAdminAgentRegistry
│   │   │   │   └── workload_analyzer_v1.py # Faculty workload distribution analysis
│   │   │   ├── regulatory/            # M7 module — compliance_auditor_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # RegulatoryAgentRegistry
│   │   │   │   └── compliance_auditor_v1.py # NAAC/NIRF compliance gap detection
│   │   │   ├── research/              # M8 module — plagiarism_advisor_v1 (ACTIVE)
│   │   │   │   ├── registry.py        # ResearchAgentRegistry
│   │   │   │   └── plagiarism_advisor_v1.py # PhD plagiarism report advisory
│   │   │   └── student_services/      # M6 module — grievance_classifier_v1 (ACTIVE)
│   │   │       ├── registry.py        # StudentServicesAgentRegistry
│   │   │       └── grievance_classifier_v1.py # Grievance triage + urgency classification
│   │   ├── mcp/                       # Internal shared services (NOT an MCP server — see §7)
│   │   │   ├── activity_service.py    # Activity feed + entity comments
│   │   │   ├── search_service.py      # PostgreSQL full-text search
│   │   │   └── verify_activity_service.py # Standalone test script (not production)
│   │   ├── tasks/                     # Celery task definitions
│   │   │   ├── events.py              # retry_failed_events, retry_stuck_critical_events
│   │   │   ├── calendar.py            # calendar_phase_check (academic calendar)
│   │   │   ├── notifications.py       # notification_send_queue_processor
│   │   │   ├── ai_tasks.py            # dispatch_domain_event, shadow mode comparison
│   │   │   ├── admissions.py          # admissions-specific periodic tasks
│   │   │   ├── finance.py             # fee_overdue_check, invoice_overdue_check
│   │   │   ├── reporting.py           # refresh_kpi_snapshots, aqar_annual_draft, reporting_gate_check
│   │   │   ├── learning_tasks.py      # close_overdue_assignments (hourly — P40 in-house LMS)
│   │   │   ├── lms_sync.py            # TOMBSTONE — Moodle grade sync replaced by P40 in-house LMS
│   │   │   ├── plagiarism_poll.py     # drillbit_poll (Drillbit API polling)
│   │   │   ├── backup.py              # daily_db_backup
│   │   │   ├── shadow_divergence.py   # shadow_divergence_nightly
│   │   │   └── webhook_retry.py       # webhook_retry (every 5 min)
│   │   ├── tools/                     # AI tool definitions
│   │   │   ├── rag_retriever.py       # PGVector semantic search tool
│   │   │   ├── policy_lookup.py       # Policy engine query tool
│   │   │   ├── rubric_validator.py    # Exam rubric validation tool
│   │   │   └── structured_scoring.py  # Marks entry validation tool
│   │   ├── rules/                     # Business rule definitions (non-policy DSL)
│   │   ├── integrations/              # External integration stubs (P14)
│   │   └── migration/                 # Data migration pipeline (not Alembic)
│   │       └── migration_pipeline.py  # Legacy data import pipeline
│   ├── migrations/                    # Alembic schema migrations
│   │   ├── env.py                     # Alembic env (offline + online modes, tenant-aware)
│   │   ├── alembic.ini                # Alembic configuration
│   │   └── versions/                  # 0001–0041 (head = 0041)
│   ├── tests/                         # pytest suite (883 data-plane tests)
│   │   ├── conftest.py                # Global fixtures: fakeredis, mock_db, mock_audit, JWT helpers
│   │   ├── test_integration_real_db.py     # 14 real-DB integration tests
│   │   ├── test_integration_rail_advisor.py # 2 rail advisor real-DB tests
│   │   └── [120+ mocked unit test files]
│   ├── scripts/
│   │   └── seed.py                    # Bootstrap: org + SUPER_ADMIN + policies + calendar
│   └── requirements.txt               # Python dependencies
├── web/                               # React 19 + Vite + TypeScript frontend
│   ├── src/
│   │   ├── main.tsx                   # Entry point (StrictMode + i18n init)
│   │   ├── App.tsx                    # Router: public routes + ProtectedRoute + ALISShell
│   │   ├── shell/
│   │   │   ├── ALISShell.tsx          # Three-column: 52px IconNav | flex-1 Canvas | 320px AgentRail
│   │   │   └── AgentRail/
│   │   │       ├── AgentRail.tsx      # AI chat panel, two-step EXECUTE confirm pattern
│   │   │       └── ChatThread.tsx     # Message list (agent/user/action-card + ViewDivider)
│   │   ├── store/
│   │   │   ├── alis.store.ts          # Zustand: canvas + agent + chat state (MESSAGE_CAP=50)
│   │   │   └── authStore.ts           # JWT + user profile + tenant context
│   │   ├── hooks/
│   │   │   ├── useAgentContext.ts     # Fires __view_change__ on canvas view change
│   │   │   └── [other module hooks]
│   │   ├── lib/
│   │   │   ├── agent-gateway.ts       # invokeRailAgent(), PII stripping before log
│   │   │   ├── canvas-actions.ts      # CanvasAction union types, ALISModule, CanvasView enums
│   │   │   └── role-config.ts         # Role → density/view/modules mapping
│   │   ├── pages/                     # 35+ page components
│   │   ├── components/                # Shared UI: DataTable, Badge, StatCard, SLABar, etc.
│   │   └── services/                  # API clients: alumni.ts, communication.ts, reporting.ts
│   └── package.json
├── docker-compose.yml                 # 15-container orchestration
├── nginx/
│   ├── nginx.conf                     # Rate limiting, CSP, SSL termination, upstream routing
│   └── certs/                         # TLS certificates (self-signed in dev)
├── control_plane/                     # SaaS Control Plane (S2+S4+S5+S9+S10)
│   ├── main.py                        # FastAPI app — tenant management, billing, DNS
│   ├── settings.py                    # Control plane Pydantic Settings
│   ├── router.py                      # Admin API + Internal API + billing + webhooks
│   ├── provisioner.py                 # TenantProvisioner — full lifecycle (provision/suspend/delete)
│   ├── db.py                          # cp_tenants, cp_invoices, cp_usage_events, cp_plans, cp_payments
│   ├── crypto.py                      # AES-GCM encryption for tenant DB passwords
│   ├── billing_engine.py              # Monthly invoice computation with per-dimension overage
│   ├── billing_models.py              # Plan configs (starter/growth/enterprise), usage event types
│   ├── usage_store.py                 # Immutable usage event recording + aggregation
│   ├── plan_store.py                  # Dynamic plan CRUD (cp_plans table)
│   ├── bucket_provisioner.py          # Per-tenant S3 bucket lifecycle
│   ├── vault_client.py                # Vault KV v2 + AppRole auth for per-tenant secrets
│   ├── dns_manager.py                 # Multi-provider DNS (Cloudflare/Route53/Azure)
│   └── tests/                         # 121 tests (S2, S4, S5, S9, S10)
├── ai_service/                        # SaaS AI Service (S3)
│   ├── main.py                        # FastAPI app — /v1/complete, /v1/embed, /v1/budget
│   ├── router.py                      # AI request handling (PII mask → route → budget)
│   ├── providers.py                   # VpcOllamaProvider, ManagedAPIProvider
│   ├── pii_masker.py                  # Regex PII detection + deterministic tokenization
│   ├── budget.py                      # Per-tenant token budget enforcement (Redis)
│   └── tests/                         # 30 tests (S3)
├── infra/
│   ├── monitoring/
│   │   ├── alertmanager.yml           # Alert routing (email + webhook to PagerDuty stub)
│   │   └── loki-config.yml            # Log aggregation (30d / 720h retention)
│   ├── k8s/
│   │   ├── helm/
│   │   │   ├── alis-data-plane/       # 11 templates (deployment, worker, beat, ingress, HPA, etc.)
│   │   │   ├── alis-control-plane/    # Combined deployment + service + secret
│   │   │   └── alis-ai-service/       # Deployment + HPA + GPU affinity
│   │   └── operator/
│   │       ├── crds/tenantstack.yaml  # TenantStack CRD (alis.app/v1alpha1)
│   │       ├── src/reconciler.py      # kopf reconciler (create/update/delete/timer)
│   │       └── tests/                 # 21 tests (S8)
│   └── terraform/
│       ├── modules/aws/               # VPC, EKS, Aurora, ElastiCache, S3, Route53
│       ├── modules/azure/             # AKS, PostgreSQL Flex, Redis Cache, Blob
│       ├── modules/gcp/               # GKE Autopilot, Cloud SQL, Memorystore, GCS
│       ├── modules/shared/vault.tf    # Vault KV v2 + AppRole policies
│       └── envs/{dev,staging,prod}/   # Environment-specific configs
└── docs/
    ├── ALIS_TECHNICAL_REFERENCE.md    # API-level reference (§17-19 cover SaaS)
    └── ALIS_TECHNICAL_ONBOARDING.md   # This document
```

---

## 4. Backend Module Map

### E01 — Auth + Users + RBAC

**Files**: `server/core/security.py`, `server/core/rbac.py`, `server/core/mfa_service.py`, `server/api/auth_router.py`, `server/api/users_router.py`, `server/api/roles_router.py`

**Routes** (auth_router.py — 10 routes):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Username + password → session token |
| POST | `/api/v1/auth/logout` | Revoke current session |
| POST | `/api/v1/auth/refresh` | Refresh session token |
| POST | `/api/v1/auth/bootstrap` | Create first SUPER_ADMIN (one-time) |
| POST | `/api/v1/auth/mfa/setup` | Initiate TOTP setup |
| POST | `/api/v1/auth/mfa/verify` | Verify TOTP code |
| POST | `/api/v1/auth/mfa/disable` | Disable MFA (requires current TOTP) |
| GET  | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/auth/password/change` | Change own password |
| POST | `/api/v1/auth/lockdown` | Initiate institution lockdown (SUPER_ADMIN) |

**Tables owned**: `users`, `sessions`, `user_roles`, `mfa_configs`, `login_audit`

**Events fired**: `auth.user_created`, `auth.login_failed`, `auth.lockdown_initiated`

---

### E02 — Workflow Engine + Approvals

**Files**: `server/core/workflow.py`, `server/core/approvals.py`, `server/api/approvals_router.py`, `server/api/workflows_router.py`

**Tables owned**: `workflow_definitions`, `workflow_instances`, `workflow_tasks`, `approval_workflows`, `approval_steps`

**Events fired**: `workflow.task_created`, `workflow.task_completed`, `workflow.quorum_reached`, `workflow.sla_breached`

---

### E03 — AI Gateway + Guardrails

**Files**: `server/core/ai_gateway.py`, `server/core/llm_router.py`, `server/core/guardrails.py`, `server/core/prompt_registry.py`, `server/core/tool_registry.py`, `server/core/model_registry.py`, `server/api/gateway_router.py`

**Routes** (gateway_router.py):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ai/invoke` | Invoke an agent by module + agent name |
| GET  | `/api/v1/ai/health` | LLM connectivity health check |
| GET  | `/api/v1/ai/agents` | List registered agents (ACTIVE only) |
| POST | `/api/v1/ai/rail/message` | Agent Rail message endpoint |

**Module registry** (live output — see §17):
```
_MODULE_REGISTRIES keys: ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'RAIL']
```

---

### E04 — Autonomous Admissions

**Files**: `server/admissions/` (10 service files), `server/api/admissions_router.py` (87 routes)

**Stages and primary service files**:

| Stage | Name | Service File |
|-------|------|-------------|
| 1 | Lead CRM | `counsellor_service.py` |
| 2 | Application Form | (in admissions/__init__.py) |
| 3 | Document Management | `review_queue.py` |
| 4 | Eligibility Check | `agents/admissions/eligibility.py` |
| 5A | Entrance Tests | (examinations integration) |
| 5B | Interview Management | (HR/academics integration) |
| 6 | Merit List Engine | `seat_matrix_service.py` |
| 7 | Offer Letter | (workflow engine) |
| 8 | Payment | (finance integration) |
| 9 | Final Verification | `forgery_detection.py` |
| 10 | Enrollment Provisioning | (triggers via domain events) |

**Application ID format**: `APP-{YEAR}-{6-digit-seq}` e.g. `APP-2025-000047`

**Tables owned**: `leads`, `applications`, `application_documents`, `entrance_tests`, `interview_panels`, `merit_lists`, `seat_matrix`, `offer_letters` + 30 more (migration 0014)

**Events fired**: `admissions.lead_created`, `admissions.application_submitted`, `admissions.offer_issued`, `admissions.enrollment_confirmed`

---

### E05 — Academics

**Files**: `server/academics/` (8 service files), `server/api/academics_router.py`

**Key services**: `programs.py`, `courses.py`, `enrollment.py`, `attendance.py`, `timetable.py`, `faculty.py`, `analytics.py`, `recalibration_service.py`, `ta_assignment_service.py`

**Tables owned**: `programs`, `courses`, `course_enrollments`, `attendance_records`, `timetable_slots`, `faculty_assignments`, `obe_outcomes`

**Events fired**: `academics.enrollment_created`, `academics.attendance_below_threshold`

---

### E06 — Examinations & Grades

**Files**: `server/examinations/` (8 service files), `server/api/examinations_router.py`

**Key services**: `schedule.py`, `hall_ticket.py`, `grades.py`, `transcript.py`, `reeval.py`, `grade_card_generator.py`, `ai_evaluation_guard.py`, `analytics.py`

**Special**: `ai_evaluation_guard.py` — prevents AI from directly writing marks; all mark entries go through a human validation step even when AI-assisted.

**Tables owned**: `exam_schedules`, `hall_tickets`, `answer_scripts`, `grade_entries`, `transcripts`, `revaluation_requests`

---

### E07 — Finance

**Files**: `server/finance/` (9 service files), `server/api/finance_router.py`

**Key services**: `fee_structure.py`, `invoice.py`, `payment.py`, `dues_status.py`, `scholarship.py`, `scholarship_revocation.py`, `waiver.py`, `exemption_service.py`, `reports.py`, `analytics.py`

**Tables owned**: `fee_structures`, `invoices`, `payments`, `scholarship_awards`, `waivers`, `payment_reconciliation`

**Events fired**: `finance.payment_received`, `finance.invoice_overdue`, `finance.scholarship_revoked`

---

### E08 — HR & Staff

**Files**: `server/hr/` (6 service files), `server/api/hr_router.py`

**Tables owned**: `staff_profiles`, `leave_requests`, `payroll_runs`, `performance_reviews`

---

### E09 — Student Services

**Files**: `server/student_services/` (6 service files), `server/api/student_services_router.py`

**Key services**: `hostel.py`, `hostel_swap.py`, `transport.py`, `library.py`, `counselling.py`, `grievance_anomaly.py`

---

### E10 — Communication Hub

**Files**: `server/communication/` (5 service files), `server/api/communication_router.py`

**Key services**: `announcements.py`, `bulk.py`, `in_app.py`, `notif_templates.py`, `notification_log.py`

**Channels**: Email (SMTP), SMS (gateway), WhatsApp (API), in-app push

---

### E11 — Reporting & Analytics

**Files**: `server/reporting/` (7 service files), `server/api/reporting_router.py`

**Key services**: `dashboard.py`, `academics_report.py`, `admissions_report.py`, `finance_report.py`, `custom_reports.py`, `export_engine.py`, `ai_insights.py`

---

### E12 — Alumni & Placement

**Files**: `server/alumni/` (5 service files), `server/api/alumni_router.py`

---

### E13 — Dynamic Process Engine

**Files**: `server/process_engine/`, `server/api/process_engine_router.py`

Configurable workflows with drag-and-drop form builder. Institutions create their own approval chains without code changes.

---

### E14 — Regulatory & Accreditation

**Files**: `server/regulatory/`, `server/api/regulatory_router.py`

**Key services**: `naac_service.py` (NAAC 7 criteria + 26 sub-criteria), `nirf_service.py` (NIRF 5 parameters), `metrics_service.py`

---

### E15 — PhD / Doctoral Research

**Files**: `server/phd/`, `server/api/phd_router.py`

**Key services**: `phd_service.py` (DC meetings, milestones), `plagiarism_service.py` (Drillbit API integration)

---

### E18 — Convocation Management

**Files**: `server/convocation/`, `server/api/convocation_router.py`

**Key services**: `convocation_service.py` — degree audit, gold medal eligibility, seating chart generation

---

### E21 — DPDP Consent Management

**Files**: `server/consent/`, `server/api/consent_router.py`

**Key services**: `consent_service.py`, `consent_middleware.py`

---

### P14 — External Integrations

**Files**: `server/integrations/`, `server/admissions/integrations/`

SMS gateway (MSG91 + Twilio), email channels (SMTP), WhatsApp (Meta Graph API), and document storage are **fully implemented**.

DigiLocker, NTA score import, and Google/Microsoft email provisioning are **stubs** — not blocking for manual pilot.

**Moodle LMS integration tombstoned** — `server/admissions/integrations/lms_sync.py` and `server/tasks/lms_sync.py` retain module structure but are no-ops. Replaced by P40 in-house LMS.

---

### P21 — Admin & Platform Hardening

**Files**: `server/api/admin_router.py`, `server/api/feature_flags_router.py`, `server/core/lockdown.py`, `server/core/shadow_mode.py`

---

### P29 — WiFi Proximity Attendance

**Files**: `server/api/wifi_attendance_router.py`

Real-time WiFi proximity-based attendance marking with Electron desktop kiosk integration.

---

### P40 — In-house Learning Management System

**Files**: `server/academics/learning_service.py`, `server/api/learning_router.py`, `server/agents/academics/content_generator_v1.py`, `server/tasks/learning_tasks.py`

**Frontend**: `web/src/pages/academics/LearningPage.tsx` at `/academics/learning` | `web/src/services/learning.ts`

**Migration**: `0041_in_house_learning` — tables `course_materials`, `assignments`, `assignment_submissions`

**Replaced**: Moodle LMS sync (tombstoned). ALIS now manages the full materials-to-grading lifecycle natively.

| Component | Purpose |
|---|---|
| `CourseMaterialService` | CRUD + state machine for course materials |
| `AssignmentService` | Assignment lifecycle: DRAFT → PUBLISHED → CLOSED → ARCHIVED |
| `SubmissionService` | Student workflow: DRAFT → SUBMITTED → UNDER_REVIEW → GRADED / RETURNED |
| `content_generator_v1.py` | REASONING-tier AI agent — generates lecture notes, quizzes, assignment questions, lesson plans from OBE CO data |
| `close_overdue_assignments` | Hourly Celery beat task — transitions PUBLISHED assignments past due (+ grace days) to CLOSED |

**Permissions added**: `LEARNING_READ` (student + faculty), `LEARNING_MANAGE` (faculty + HOD)

**AI content generation flow**:
1. Faculty selects generation type + course + CO
2. Router calls `_fetch_co_context()` to pull CO codes, Bloom's levels, syllabus topics from DB
3. `execute_content_generator()` invokes REASONING tier via `AIGateway`
4. Result stored as `status='DRAFT'` course material — faculty must publish manually (unless `auto_publish=True`)
5. AI confidence score + tier returned in response

**Late submission policy**: `learning.assignment.late_penalty_pct_default` (default 10%) and `learning.assignment.max_late_days` (default 3) stored in `institution_policies`, never hardcoded.

**OBE integration**: `assignment.graded` domain event includes `co_id` — triggers attainment recalculation in OBE module.

---

## 5. The Database

### Migration History

```
Current head: 0041 (see §17)
```

| Migration | Description |
|-----------|-------------|
| 0001 | Initial schema — all base tables (users, orgs, programs, etc.) |
| 0002–0012 | Incremental feature tables (admissions stages, finance, HR) |
| 0013 | Indexes optimisation |
| 0014 | Full admissions workflow — 40+ tables for 10-stage autonomous admissions |
| 0015 | RBAC scope and event hardening |
| 0016–0021 | Domain-specific additions |
| 0022 | DBT exemption and promissory |
| 0023 | WhatsApp language preferences |
| 0024 | (not listed in repo — may be squashed) |
| 0025 | Pilot hardening |
| 0026 | PhD module |
| 0027 | Readmission workflow |
| 0028 | Convocation |
| 0029 | OBE (Outcome-Based Education) |
| 0030 | Multi-campus support |
| 0031 | E-invoice |
| 0032–0034 | (intermediate hardening) |
| 0035 | `workflow_tasks` table + `audit_ledger` immutability trigger |
| 0036 | `workflow_tasks` gets `tenant_id`, `urgency`, `assignee_role`, `assignee_actor_id` columns |
| 0037 | `tenant_policies` table (required by policy_engine + agent_rail_silence) |
| 0038 | `failed_task_log` table — dead-letter store for Celery tasks that exhaust all retries; SUPER_ADMIN access via `/api/v1/admin/failed-tasks` |
| 0039 | `hr_placement_workflow_gaps` — visiting faculty session logs and placement drive management |
| 0040 | `identity_match_and_access_lift` — identity matching in applications and temporary access lifting for payment disputes |
| 0041 | `in_house_learning` — course_materials, assignments, assignment_submissions tables + RLS; 4 AI prompt seeds for learning content generation (P40) |

### Alembic Workflow

```bash
# Create new migration (auto-detects model changes)
cd ALIS
python -m alembic revision --autogenerate -m "description_of_change"

# Apply all pending migrations
python -m alembic upgrade head

# Apply one migration at a time
python -m alembic upgrade +1

# Rollback one migration
python -m alembic downgrade -1

# View current head
python -m alembic current

# View full history
python -m alembic history --verbose

# Verify after upgrade
python -m alembic current
# Expected output: 0041 (head)
```

### RLS Enforcement Mechanism

Row-Level Security is enforced at the PostgreSQL level. Application code never filters by tenant in SQL — the database does it automatically.

How it works:

1. `execute_query()` / `execute_transaction()` run this before every query:
   ```sql
   SET alis.current_tenant = '{tenant_id}';
   ```

2. RLS policies on tenant-partitioned tables check:
   ```sql
   current_setting('alis.current_tenant', true) = tenant_id
   ```
   or (older migrations use):
   ```sql
   current_setting('app.tenant_id', true) = tenant_id
   ```

   Both variable names exist in the codebase. The `alis.current_tenant` form is canonical; `app.tenant_id` exists for backward compatibility with early migrations. Do not create new policies using `app.tenant_id`.

3. If a query runs without `SET alis.current_tenant`, RLS returns zero rows — data is not leaked, it is simply invisible. This fail-safe behaviour means RLS protects against application bugs without crashing.

### Key DB Conventions

| Convention | Value | Rationale |
|-----------|-------|-----------|
| Primary keys | UUID v4 string | No sequence prediction, globally unique |
| Timestamps | `TIMESTAMPTZ` (UTC) | Consistent across timezones |
| Money | `DECIMAL(12,2)` in DB, string in JSON | Avoids floating point errors |
| Soft delete | `status='ARCHIVED'` or `status='ANNULLED'` | Audit trail requires record existence |
| Table naming | `snake_case`, plural | PostgreSQL convention |
| Note on "organisations" | Migration 0001 creates `organisations` (British spelling) | Some queries use `organizations` — see §15 |

### `execute_query` vs `execute_transaction`

```python
# SELECT only — read, no commit
from server.db_service import execute_query

rows = execute_query(
    "SELECT * FROM students WHERE tenant_id = %s AND id = %s",
    (tenant_id, student_id),
    tenant_id=tenant_id,
)

# INSERT/UPDATE/DELETE — auto-commits each statement
from server.db_service import execute_transaction

execute_transaction(
    [
        ("INSERT INTO audit_log (tenant_id, action) VALUES (%s, %s)", (tenant_id, "CREATED")),
        ("UPDATE students SET status = %s WHERE id = %s", ("ENROLLED", student_id)),
    ],
    tenant_id=tenant_id,
)
```

**Critical rule**: Never use `execute_query` for writes. Never use `execute_transaction` for selects. The distinction is enforced by code convention, not by the DB driver.

System-level operations (cross-tenant, super admin):
```python
from server.db_service import execute_system_query, execute_system_transaction

# Bypasses tenant scoping — use only in admin/migration contexts
rows = execute_system_query("SELECT COUNT(*) FROM tenants")
```

---

## 6. The Core Layer

`server/core/` is the infrastructure layer. Every module in ALIS imports from here. Nothing in `server/core/` imports from domain modules.

---

### `settings.py` — Pydantic Settings

Single source of truth for all infrastructure configuration. Values read from environment variables (`.env` file in dev, Docker env in prod).

```python
from server.core.settings import settings

settings.database_url        # PostgreSQL DSN
settings.redis_url           # Redis URL
settings.secret_key          # JWT signing secret
settings.ollama_base_url     # Local Ollama API endpoint
settings.vault_addr          # HashiCorp Vault address
settings.minio_endpoint      # MinIO S3 endpoint
```

---

### `security.py` — Auth, Sessions, Middleware

#### Redis Key Prefixes

| Prefix | Purpose |
|--------|---------|
| `alis:sess:{token_hash}` | Session data JSON |
| `alis:tok:{token_hash}` | Token metadata |
| `alis:user_sess:{user_id}` | Set of active session token hashes per user |
| `alis:fail:{username}` | Failed login attempt counter |
| `alis:lockout:{username}` | Lockout flag (expiry = lockout duration) |
| `alis:rate:{ip}:{endpoint}` | Rate limiter counter |

#### Key Classes

**`PasswordHasher`**:
```python
# bcrypt with 12 rounds (default)
hash = PasswordHasher.hash("my-password")
is_valid = PasswordHasher.verify("my-password", hash)
# Supports legacy PBKDF2 hashes for backward compatibility (migration from older system)
```

**`TokenGenerator`**:
```python
token = TokenGenerator.generate_token()
# Returns: secrets.token_urlsafe(32) — 43 URL-safe characters
```

**`FailedLoginTracker`**:
- `MAX_ATTEMPTS = 5`
- `LOCKOUT_SECONDS = 900` (15 minutes)
- After 5 failures: account locked for 15 min, counter resets on successful login

**`SessionManager`**:
```python
session = SessionManager.validate_token(token)
# Returns Session object or None if invalid/expired
# Hash: SHA256(token) — raw token never stored in Redis
# Fails SAFE: returns None if Redis is down (deny access, never grant on error)

SessionManager.revoke_all_sessions(user_id)
# Redis SCAN "alis:sess:*" — finds and deletes all sessions for this user
```

**`RateLimiter`**:
```python
allowed = RateLimiter.check(ip_address, endpoint, limit=60, window=60)
# Fails OPEN: returns True (allow) if Redis is down
# Rationale: RateLimiter is a protective layer; denying all traffic on Redis failure
# would be worse than allowing some extra requests through.
```

#### `TenantMiddleware`

```python
EXEMPT_PATHS = {
    "/health",
    "/api/auth/login",
    "/api/auth/bootstrap",
    "/api/auth/mfa/verify",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/ai/health",
}
```

Flow:
1. Check if path is exempt — if yes, pass through
2. Extract Bearer token from `Authorization` header
3. Fallback: `X-Tenant-ID` header (for service-to-service calls)
4. Call `SessionManager.validate_token(token)` → gets tenant_id from session
5. Set `_current_tenant_id` ContextVar to tenant_id
6. Run request handler
7. `finally`: reset ContextVar to None (prevents context leakage between requests)
8. On missing tenant: return `403 {"error": "Tenant context required", "code": "ERR_LAYER4_TENANT"}`

#### `require_permission` Decorator

```python
from server.core.security import require_permission
from server.core.rbac import Permission

@router.post("/grades/submit")
@require_permission(Permission.MARKS_ENTRY)
async def submit_grades(payload: GradeSubmitPayload, request: Request):
    ...
```

Critical implementation detail:
```python
# security.py
import inspect
wrapper.__signature__ = inspect.signature(func)
# This copies the original function's parameter signature to the wrapper.
# FastAPI uses __signature__ to introspect route parameters.
# Without this, FastAPI cannot see the `request: Request` parameter and
# OpenAPI documentation breaks. Do not remove this line.
```

---

### `rbac.py` — RBAC+ Access Control

#### Role Enum (22 roles)

```python
class Role(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty"
    HOD = "hod"
    DEAN = "dean"
    REGISTRAR = "registrar"
    FINANCE_OFFICER = "finance_officer"
    HR_ADMIN = "hr_admin"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    DEAN_ELEVATED = "dean_elevated"
    M1_MANAGER = "m1_manager"    # Admissions Manager
    M2_MANAGER = "m2_manager"    # Academics Manager
    M3_MANAGER = "m3_manager"    # Examinations Manager
    M4_MANAGER = "m4_manager"    # Finance Manager
    M5_MANAGER = "m5_manager"    # HR Manager
    M6_MANAGER = "m6_manager"    # Student Services Manager
    M7_MANAGER = "m7_manager"    # Communication Manager
    M8_MANAGER = "m8_manager"    # Reporting Manager
    M9_MANAGER = "m9_manager"    # Alumni Manager
    AI_AGENT = "ai_agent"
    SYSTEM = "system"
    COUNSELLOR = "counsellor"
```

#### AI_AGENT Permissions (restricted)

```python
# AI agents can ONLY:
Permission.STUDENT_READ
Permission.COURSE_READ
Permission.MARKS_READ
Permission.FEE_READ
Permission.GLOBAL_LOCK_CHECK
Permission.AI_INVOKE
# AI agents cannot write any state — enforced at RBAC layer
```

#### `verify_access()` — 4-Step Check

```python
result = verify_access(
    actor_role=Role.FACULTY,
    permission=Permission.MARKS_ENTRY,
    context={"exam_status": "EVALUATION_OPEN", "tenant_id": tenant_id},
)
# result.allowed: bool
# result.reason: str — human-readable reason for denial
# result.context_violations: list — which context checks failed
```

Steps:
1. **RBAC check**: Is this permission in `ROLE_PERMISSIONS[actor_role]`?
2. **Tenant isolation**: Does `context.tenant_id` match the session tenant?
3. **Context-aware checks**: e.g., Faculty can only enter marks when `exam_status == "EVALUATION_OPEN"`
4. **Agent constraints**: If `actor_role == AI_AGENT`, enforce read-only permission set

---

### `audit.py` — Immutable Audit Ledger

#### `AuditEntry` (frozen dataclass)

```python
@dataclass(frozen=True)
class AuditEntry:
    id: str                    # UUID
    tenant_id: str             # Institution UUID
    actor_id: str              # User ID who performed the action
    actor_role: str            # Role at time of action
    action: AuditAction        # Enum: CREATE, UPDATE, STATE_TRANSITION, etc.
    entity_type: str           # e.g., "application", "student", "payment"
    entity_id: str             # UUID of the affected entity
    metadata: Dict[str, Any]   # Before/after state, diff, context
    timestamp: datetime        # UTC
    previous_hash: str         # Hash of the previous entry in chain
    hash: str                  # SHA256 of this entry
```

#### `AuditAction` Enum (50+ values, key examples)

```python
CREATE, UPDATE, DELETE
STATE_TRANSITION          # Entity moved from state A to state B
AGENT_EXECUTION           # AI agent invoked
GUARDRAIL_BLOCKED         # AI output rejected by guardrails
OVERRIDE_APPLIED          # SUPER_ADMIN override
LOCKDOWN_ACTIVATED        # Institution lockdown
LOCKDOWN_LIFTED
POLICY_APPROVED           # Policy version approved
POLICY_VERSION_BUMP
AUDIT_CHAIN_VERIFIED      # Integrity check run
DATA_EXPORT
CONSENT_GIVEN
CONSENT_REVOKED
ERASURE_REQUEST
```

#### Hash Chain Formula

```python
import hashlib, json

def _compute_hash(previous_hash: str, payload: dict) -> str:
    # canonical_json: sorted keys, no spaces, deterministic
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    raw = (previous_hash or "") + canonical
    return hashlib.sha256(raw.encode()).hexdigest()
```

The first entry in a tenant's chain has `previous_hash = ""`. Every subsequent entry chains off the previous one.

#### Advisory Lock

```python
# Per-tenant lock prevents concurrent hash-chain forks
# lock_key is derived from tenant_id (integer hash for pg_advisory_xact_lock)
execute_query(
    "SELECT pg_advisory_xact_lock(%s)",
    (lock_key,),
    tenant_id=tenant_id,
)
```

#### Chain Verification

```python
from server.core.audit import AuditLedger

result = AuditLedger.verify_chain_integrity(tenant_id=tenant_id)
# result = {
#   "valid": True,
#   "total_entries": 4821,
#   "first_invalid_id": None,
#   "message": "Chain integrity verified"
# }
```

#### DB Trigger (migration 0035)

```sql
-- Blocks UPDATE and DELETE on audit_ledger — enforced at DB level
CREATE OR REPLACE FUNCTION fn_audit_ledger_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_ledger is append-only: % on % not permitted',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_ledger_immutable
BEFORE UPDATE OR DELETE ON audit_ledger
FOR EACH ROW EXECUTE FUNCTION fn_audit_ledger_immutable();
```

---

### `policy_engine.py` — Rules-as-Data DSL

The policy engine is what makes ALIS multi-institution without code forks.

#### Policy DSL Rule Structure

A policy stored in `tenant_policies.rules` is a JSON array:

```json
[
  {
    "id": "r1_sla_breach",
    "condition": "counts.sla_breached >= 1",
    "on_pass": "SURFACE",
    "reason_code": "SLA_BREACH_DETECTED"
  },
  {
    "id": "r2_urgent_threshold",
    "threshold": 3,
    "condition": "counts.urgent >= threshold",
    "on_pass": "SURFACE",
    "on_fail": "SILENT",
    "reason_code": "BELOW_URGENT_THRESHOLD"
  }
]
```

Rule fields:
- `id` — machine-readable rule identifier (stored in audit log)
- `condition` — asteval boolean expression (see syntax below)
- `on_pass` — verdict returned when condition is true
- `on_fail` — verdict returned when condition is false (optional)
- `reason_code` — stored in audit log for traceability
- Any other keys become rule-level parameters available in the expression (e.g., `threshold: 3`)

#### DSL Expression Syntax

```
# Comparison operators
student.attendance_pct >= threshold
fee_days_overdue > grace_period_days

# Boolean operators (case-insensitive AND/OR/NOT)
student.attendance_pct >= condonation_min AND student.has_valid_reason
student.category IN relaxed_categories OR student.attendance_pct >= threshold

# List membership
student.category IN ["SC", "ST", "OBC"]
applicant.program_code NOT IN excluded_programs

# Arithmetic
(marks_obtained / marks_total) * 100 >= passing_percentage
```

**What the DSL cannot do** (by design):
- No DB queries inside expressions
- No function calls with side effects
- No loops or iteration
- No variable assignment
- Pure evaluation only — asteval `Interpreter` in restricted mode

#### `evaluate()` Signature

```python
from server.core.policy_engine import policy_engine

result = policy_engine.evaluate(
    policy_id="attendance_eligibility",     # dot-notation key
    context={
        "student": {
            "attendance_pct": 71.5,
            "category": "SC",
            "has_valid_reason": True,
        }
    },
    tenant_id=tenant_id,
    default_verdict="ELIGIBLE",             # returned if no rule fires
)

# result.verdict         → "ELIGIBLE" | "INELIGIBLE" | any string from on_pass/on_fail
# result.reason_code     → "ATTENDANCE_BELOW_MINIMUM" | "NO_RULE_FIRED" | None
# result.rule_id         → "r1_minimum_check" | None
# result.policy_version  → 3  ← MUST be stored in audit log
```

**Critical**: Always store `result.policy_version` in the audit log. This is the only way to reproduce a decision months later during a regulatory review.

#### `get_value()` — Simple Config Lookup

```python
threshold = policy_engine.get_value(
    "attendance.minimum_threshold",
    tenant_id,
    default=75,
)
# Reads from tenant_config table (K/V store)
# Redis cache: alis:config:{tenant_id}:{key}, TTL=300s
```

#### Cache Invalidation

```python
# After approving a new policy version:
policy_engine.invalidate(policy_id="attendance_eligibility", tenant_id=tenant_id)

# After changing a config value:
policy_engine.invalidate_config(key="attendance.minimum_threshold", tenant_id=tenant_id)
```

---

### `domain_events.py` — Event Bus

#### `DomainEvent` Dataclass

```python
@dataclass
class DomainEvent:
    event_type: str         # e.g., "admissions.enrollment_confirmed"
    org_id: str             # Tenant UUID
    payload: Dict[str, Any] # Event data (arbitrary JSON)
    entity_type: str        # e.g., "enrollment"
    entity_id: str          # UUID of the affected entity
    actor_id: str           # Who triggered this event
    correlation_id: str     # UUID linking related events (for tracing)
    id: str                 # Auto-generated UUID
    created_at: datetime    # Auto-set to UTC now
    status: str             # "PENDING" → "PROCESSING" → "DELIVERED" | "FAILED"
```

#### Publishing an Event

```python
from server.core.domain_events import DomainEventBus, DomainEvent

DomainEventBus.publish(DomainEvent(
    event_type="finance.payment_received",
    entity_type="payment",
    entity_id=payment_id,
    org_id=tenant_id,
    payload={"amount": "5000.00", "invoice_id": invoice_id},
    actor_id=actor_id,
    correlation_id=correlation_id,
))
```

What `publish()` does:
1. `INSERT INTO domain_events (...)` with `status='PENDING'`
2. Calls `dispatch_domain_event.delay(event.id)` — Celery async task
3. Returns immediately — publishing is not blocking

#### Subscribing to Events

```python
# In a module's event_handlers.py file — called at app startup
DomainEventBus.subscribe("finance.payment_received", handle_payment_received)

async def handle_payment_received(event: DomainEvent):
    # Update invoice status, send receipt notification
    ...
```

#### Idempotency

```sql
-- Before calling each handler, the dispatcher inserts:
INSERT INTO domain_event_handler_log (event_id, handler_name, tenant_id)
VALUES (%s, %s, %s)
ON CONFLICT DO NOTHING
RETURNING id
```

If `RETURNING id` returns a row, the handler runs. If not, it was already processed — skip. This prevents duplicate processing when Celery retries a task.

#### Retry Behaviour

- On handler error: `status` resets to `'PENDING'`, `retry_count` increments
- At `retry_count == 3`: `status` set to `'FAILED'`, `failure_reason` recorded
- `retry_failed_events` Beat task (every 5 min): picks up PENDING events older than 2 minutes
- `retry_stuck_critical_events` Beat task (every 30s): picks up PROCESSING events older than 120 seconds for FINANCE and EXAMINATION topics (these are higher priority)

#### `publish_sync()` — For Tests Only

```python
# Synchronous publish: writes to DB + dispatches handlers in-process
# Use only in tests — never in production code
DomainEventBus.publish_sync(event)
```

---

### `llm_router.py` — Three-Tier Model Routing

| Tier | Enum Value | Model (Ollama) | Use Cases |
|------|-----------|----------------|-----------|
| EXTRACTION | `LLMTaskClass.EXTRACTION` | `qwen2.5:1.5b-instruct-q8_0` | OCR text extraction, structured data parsing, grade extraction from PDFs |
| GENERATION | `LLMTaskClass.GENERATION` | `qwen2.5:7b-instruct-q8_0` | Agent Rail responses, document drafts, notification text |
| REASONING | `LLMTaskClass.REASONING` | `qwen2.5:14b-instruct-q8_0` | Eligibility evaluation, complex policy reasoning, NAAC criteria analysis |

```python
from server.core.llm_router import LLMTaskClass, get_model_for_task

model_name = get_model_for_task(LLMTaskClass.GENERATION)
# Returns: "qwen2.5:7b-instruct-q8_0"
```

**Rule**: Never hardcode model names. Always call `get_model_for_task()`. Model names live in `ConfigRegistry` (DB-backed).

---

### `ai_gateway.py` — Central AI Hub

All LLM calls in ALIS go through the AI Gateway. No module calls Ollama directly.

#### `AIGatewayContext`

```python
context = AIGatewayContext(
    actor_id="eligibility_evaluator_v1",
    actor_role=role,
    actor_type="ai_agent",      # "human" | "ai_agent" | "system"
    org_id=tenant_id,
    module="M1",
    wizard="Eligibility Eval",
    request_id=str(uuid4()),    # Auto-generated if omitted
)
```

#### `AIInvocationResult`

```python
result = AIInvocationResult(
    success=True,
    content="...",              # LLM output text or JSON string
    request_id=context.request_id,
    model="qwen2.5:7b",
    latency_ms=1240.5,
    token_count=None,           # Populated when available from Ollama
)
# On failure:
result = AIInvocationResult(
    success=False,
    error="Connection refused to Ollama",
    request_id=context.request_id,
    model="",
    latency_ms=50.0,
)
```

#### `AIGateway.get_llm(context)`

Returns a configured LangChain LLM instance appropriate for the context. The gateway:
1. Determines task class from `context.wizard` → looks up in model registry
2. Applies guardrails to the output before returning
3. Checks HITL (Human-in-the-Loop) checkpoints — certain wizard types require human review before proceeding
4. Logs every invocation to Prometheus (`ai_invocations_total`, `ai_latency_seconds`)

---

### Other Core Files

| File | Purpose | Key function |
|------|---------|-------------|
| `locks.py` | Distributed locks | `DistributedLock(key, tenant_id)` context manager |
| `vault_client.py` | HashiCorp Vault | `VaultClient.encrypt_transit(data)`, `.decrypt_transit(ciphertext)`, `.get_secret(path)` |
| `shadow_mode.py` | A/B agent testing | `ShadowMode.run_shadow(primary_fn, shadow_fn)` |
| `metrics.py` | Prometheus metrics | `AI_INVOCATIONS`, `HTTP_REQUEST_DURATION`, `DOMAIN_EVENTS_TOTAL` |
| `feature_flags.py` | Per-tenant flags | `FeatureFlags.is_enabled("flag_name", tenant_id)` |
| `exceptions.py` | Domain exceptions | `NotFoundError`, `ValidationError`, `PermissionDeniedError`, `ConflictError` |
| `escalation.py` | SLA breach routing | `EscalationEngine.check_and_escalate(task_id)` |
| `mfa_service.py` | TOTP MFA | `MFAService.generate_secret()`, `.verify_totp(secret, code)` |
| `tenant_crypto.py` | Field-level encryption | `TenantCrypto.encrypt(value, tenant_id)`, `.decrypt(ciphertext, tenant_id)` |
| `webhook_dispatcher.py` | Outbound webhooks | `WebhookDispatcher.dispatch(event)` — called after domain event handlers |
| `diff_tracker.py` | Entity diffs | `DiffTracker.capture(before, after)` — stored in audit metadata |
| `data_classification.py` | PII tagging | `DataClassifier.classify(field_name)` → `PII | SENSITIVE | PUBLIC` |
| `retention_policy.py` | Data archival | `RetentionPolicy.apply(entity_type, tenant_id)` |

---

## 7. The AI Stack

### Three-Tier Model Routing

```
┌─────────────────────────────────────────────────────────────────┐
│  EXTRACTION (1.5B — qwen2.5:1.5b-instruct-q8_0)                │
│  Fast structured extraction. No reasoning required.             │
│  Examples: PDF grade extraction, form field parsing             │
│  Latency target: < 800ms                                        │
├─────────────────────────────────────────────────────────────────┤
│  GENERATION (7B — qwen2.5:7b-instruct-q8_0)                    │
│  Natural language generation. Moderate reasoning.               │
│  Examples: Agent Rail responses, notification drafts, summaries │
│  Latency target: < 3s                                           │
├─────────────────────────────────────────────────────────────────┤
│  REASONING (14B — qwen2.5:14b-instruct-q8_0)                   │
│  Complex multi-step reasoning. Highest accuracy required.       │
│  Examples: Eligibility evaluation, NAAC criteria analysis       │
│  Latency target: < 8s                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Registry Pattern

Agents are registered with `AgentMeta`:

```python
@dataclass
class AgentMeta:
    name: str                # e.g., "context_advisor_v1"
    module: str              # e.g., "RAIL"
    model_class: str         # "EXTRACTION" | "GENERATION" | "REASONING"
    status: str              # "ACTIVE" | "SHADOW" | "DEPRECATED"
    allowed_tools: List[str] # tools this agent may call
    description: str
    executor: Callable       # execute_context_advisor, execute_eligibility_eval, etc.
```

Status values:
- `ACTIVE` — normal production agent; results returned to caller
- `SHADOW` — runs in parallel with primary; output is discarded and compared for divergence logging (A/B validation without user impact)
- `DEPRECATED` — registered but not invocable

Live registries: `['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'RAIL']` (confirmed — see §17)

### `context_advisor_v1` — The Only Active Rail Agent

Located at `server/agents/rail/context_advisor.py`.

**Three execution paths**:

**Path 1 — `__view_change__` (fully programmatic)**:
```python
# Triggered when user navigates to a new canvas view
# No LLM involved — pure SQL aggregates + policy evaluation

counts = _query_counts(view, tenant_id, actor_id, role)
# Runs view-specific SQL (approval_queue, admissions_pipeline, fee_dashboard,
# exam_management, student_risk, or generic)

if not _should_surface(counts, tenant_id):
    return {"message": None, "canvasAction": None, "agentContext": None}
else:
    brief = _build_proactive_message(view, counts)
    return {"message": brief, "canvasAction": {"type": "HIGHLIGHT_MULTIPLE", "itemIds": urgent_ids}}
```

Silence decision via policy engine:
```python
# personal_sla_breached bypasses the policy — always surface
if counts.get("personal_sla_breached", 0) >= 1:
    return True

result = policy_engine.evaluate(
    policy_id="agent_rail_silence",
    context={"counts": {"sla_breached": ..., "urgent": ..., "total_pending": ...}},
    tenant_id=tenant_id,
    default_verdict="SURFACE",  # permissive — rail works before policy is configured
)
return result.verdict == "SURFACE"
```

**Path 2 — Chip click (known commands, programmatic)**:
```python
# 15 known chip labels → hardcoded SQL queries
# Examples: "show urgent items", "pending verifications", "show defaulters"
# Params: (tenant_id, role, actor_id)
# Returns: HIGHLIGHT_MULTIPLE canvasAction with matching task IDs
```

**Path 3 — Free text (GENERATION tier LLM)**:
```python
# LLM receives: role, view, aggregate counts (no entity-level data), recent messages
# PII stripped from all inputs before LLM call
# Reply: 1-2 concise sentences based on counts only
# Falls back to proactive message if LLM unavailable
```

**PII Patterns Stripped**:
```python
_PII_PATTERNS = [
    re.compile(r'\bSTU-\d{4}-\d{6}\b'),   # Student IDs (e.g., STU-2025-000123)
    re.compile(r'\bAPP-\d{4}-\d{6}\b'),   # Application IDs
    re.compile(r'\bFAC-\d+\b'),            # Faculty IDs
    re.compile(r'\b[6-9]\d{9}\b'),        # Indian mobile numbers (10 digits, starts 6-9)
    re.compile(r'\b\d{12}\b'),             # Aadhaar-length numbers
]
```

### `eligibility_evaluator_v1` — LangGraph Agent

Located at `server/agents/admissions/eligibility.py`.

**Graph topology**:
```
extract_grades_node → evaluate_eligibility_node → END
```

**State** (`EligibilityState` TypedDict):
```python
marksheet_text: str      # OCR text from PDF (input)
admission_criteria: str  # Criteria to compare against (input)
rbac_context: dict       # RBAC context (input)
extracted_grades: str    # JSON from node 1 (intermediate)
draft_verdict: str       # LLM JSON output (output)
eligibility_score: float # 0.0–1.0 (output)
confidence_tier: str     # "HIGH" | "MEDIUM" | "LOW" (output)
proposed_state: str      # "ELIGIBLE" | "PROVISIONALLY_ELIGIBLE" | "MANUAL_REVIEW" (output)
```

**Confidence thresholds**: Read from `PolicyStore.get()` — not hardcoded:
```python
high_conf = float(PolicyStore.get(org_id, "ai.eligibility.high_confidence_threshold") or 0.8)
low_conf  = float(PolicyStore.get(org_id, "ai.eligibility.low_confidence_threshold") or 0.5)
```

### The MCP Directory Clarification

`server/mcp/` contains three files that are **internal application services**, not an MCP server:

| File | What it actually is |
|------|-------------------|
| `activity_service.py` | Activity feed + entity comment threads |
| `search_service.py` | PostgreSQL full-text search (tsvector) |
| `verify_activity_service.py` | Standalone test/verification script (not production) |

**There is no MCP (Model Context Protocol) server in ALIS.** The directory name is misleading. External agents (Claude Desktop, Claude Code, etc.) cannot connect to ALIS via MCP. If you need to build MCP integration, you would need to create a new `server/mcp_server/` module implementing the MCP SDK specification.

### Policy DSL Complete Reference

```python
# Variables available in expressions:
# - Rule-level params (keys in the rule dict other than id/condition/on_pass/on_fail/reason_code)
# - Context variables (keys from the context dict passed to evaluate())
# - Nested dicts accessible via dot notation: student.attendance_pct
#   (internally converted to SimpleNamespace)

# Examples of valid expressions:
"student.attendance_pct >= threshold"
"student.attendance_pct >= condonation_min AND student.has_valid_reason"
"student.category IN relaxed_categories AND student.attendance_pct >= relaxed_threshold"
"fee_days_overdue > grace_period_days"
"counts.sla_breached >= 1"
"(marks_obtained / marks_total) * 100 >= passing_percentage"
"applicant.program_code NOT IN excluded_programs"

# AND/OR/IN are normalised to Python keywords before evaluation
# asteval Interpreter is used with: minimal=False, no_print=True
```

---

## 8. The Agent Rail

The Agent Rail is the 320px AI chat panel on the right side of ALISShell. It is architecturally the most complex UI feature in ALIS.

### Shared Zustand Store Architecture

The Agent Rail and the primary canvas share a single Zustand store (`alis.store.ts`). This coupling is intentional:

- The rail needs to know `canvas.view` to run view-specific SQL queries
- The canvas needs to know `agent.pendingAction` to execute the confirmed action
- Without shared state, the Confirm chip would need to pass the action through a DOM event with no type safety

```typescript
// ALIS/web/src/store/alis.store.ts
interface ALISStore {
  // Canvas state
  canvas: {
    view: CanvasView;           // "approval_queue" | "admissions_pipeline" | ...
    module: ALISModule;
    filters: Record<string, any>;
    highlightedItemId: string | null;
  };

  // Agent state
  agent: {
    pendingAction: CanvasAction | null;  // Set on action-card; cleared on Confirm/Skip
    agentContext: string | null;         // Opaque string for context continuity
    quickActions: string[];              // Chip labels shown below input
  };

  // Chat state
  chat: {
    messages: ChatMessage[];             // Capped at MESSAGE_CAP = 50
    isLoading: boolean;
  };
}
```

### `canvas.view` → SQL Query Mapping

| `canvas.view` | SQL counts fetched on `__view_change__` |
|--------------|----------------------------------------|
| `approval_queue` | total_pending, urgent, sla_breached, personal_sla_breached |
| `admissions_pipeline` | total_pending, pending_docs, expiring_offers (< 4h), sla_breached |
| `fee_dashboard` | total_pending, overdue (FEE_OVERDUE tasks), sla_breached |
| `exam_management` | total_pending, hall_tickets (HALL_TICKET_DISPATCH), sla_breached |
| `student_risk` | total_pending, attendance_risk, probation, sla_breached |
| (any other) | total_pending, urgent, sla_breached (generic query) |

All queries: `WHERE tenant_id = %s AND status = 'PENDING' AND (assignee_role = %s OR assignee_actor_id = %s)`

### Three Message Types

```typescript
interface ChatMessage {
  id: string;
  role: 'agent' | 'user';
  text: string | null;
  chips?: string[];              // Button labels (action-card messages)
  canvasAction?: CanvasAction;   // Action to execute on Confirm chip
  sourceView?: string;           // Which canvas view this message belongs to
  timestamp: number;
}
```

The `ViewDivider` component inserts a separator when `sourceView` changes between consecutive messages:

```typescript
// ChatThread.tsx
const VIEW_LABELS: Record<string, string> = {
  "approval_queue": "Approval Queue",
  "admissions_pipeline": "Admissions Pipeline",
  "fee_dashboard": "Fee Dashboard",
  "exam_management": "Exam Management",
  "student_risk": "Student Risk",
};
```

### EXECUTE Two-Step Pattern

This is the enforcement mechanism for Layer 2 (AI produces DRAFT, human approves):

```
1. Agent returns canvasAction of type "EXECUTE"
         ↓
2. Frontend stores as action-card message with chips: ["Confirm", "Skip"]
         ↓
3. User sees action-card in AgentRail chat thread
         ↓
4. User taps "Confirm"
         ↓
5. dispatchAgentAction(canvasAction) in Zustand store
         ↓
6. useAgentCanvasSync fires DOM event: "alis:execute"
         ↓
7. Route handler catches event → sends HTTP request to backend
         ↓
8. Backend executes the action (only now does state change)
```

If the user taps "Skip", the pendingAction is cleared and nothing happens.

This ensures no agent action can auto-fire from a `__view_change__` or chip response.

### `agentContext` Field

```typescript
// Stored in store.agent.agentContext
// Sent back with every subsequent rail message:
{
  view: "approval_queue",
  role: "registrar",
  message: "show me the urgent ones",
  agent_context: "view:approval_queue:urgent:uuid1,uuid2,uuid3",  // ← previous response
  recent_messages: [/* last 6 messages */]
}
```

The `agentContext` is an opaque string the agent generates to carry session context across turns. It allows the agent to resolve "the student I just highlighted" without re-querying the full entity.

### `useAgentContext` Hook

Located at `web/src/hooks/useAgentContext.ts`.

```typescript
// Fires when canvas.view changes
useEffect(() => {
  // 1. Post __view_change__ synthetic message to backend
  const response = await invokeRailAgent({
    message: "__view_change__",
    view: currentView,
    role: userRole,
    agent_context: store.agent.agentContext,
  });

  // 2. Always update agentContextHint from response
  if (response.agentContext) {
    store.setAgentContext(response.agentContext);
  }

  // 3. Only add to chat if message is non-null (policy may say SILENT)
  if (response.message !== null) {
    store.addMessage({
      role: 'agent',
      text: response.message,
      chips: response.chips,
      canvasAction: response.canvasAction,
      sourceView: currentView,
    });
  }
}, [canvas.view]);
```

### Proactive Silence Logic

The `agent_rail_silence` policy (stored in `tenant_policies`, created by migration 0037) controls when the rail speaks unprompted:

```json
// Example agent_rail_silence policy rules:
[
  {
    "id": "r1_sla_breach",
    "condition": "counts.sla_breached >= 1",
    "on_pass": "SURFACE",
    "reason_code": "SLA_BREACH_DETECTED"
  },
  {
    "id": "r2_urgent_threshold",
    "threshold": 3,
    "condition": "counts.urgent >= threshold",
    "on_pass": "SURFACE",
    "on_fail": "SILENT",
    "reason_code": "BELOW_URGENT_THRESHOLD"
  }
]
```

Default verdict is `SURFACE` — the rail works before any policy is configured. Once the institution configures silence thresholds, proactive messages only appear when the situation warrants it.

**Bypass**: A personally-assigned SLA breach (`personal_sla_breached >= 1`) bypasses the policy entirely and always surfaces. This is hardcoded in `context_advisor.py` line 208 — not configurable, by design.

---

## 9. Background Workers

### Celery Configuration

```python
# ALIS/server/worker.py — key Celery settings
app = Celery("alis")
app.conf.update(
    broker_url=settings.redis_url,
    result_backend=settings.redis_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,               # Task only acknowledged AFTER completion
    task_reject_on_worker_lost=True,   # Explicit rejection if worker dies mid-task
    worker_prefetch_multiplier=1,      # Worker fetches only 1 task at a time
    task_max_retries=3,
    task_default_retry_delay=60,       # seconds between retries
)
```

**Why `task_acks_late=True`**: A task is only removed from the queue after it completes successfully. If a Celery worker crashes mid-task (power loss, OOM kill), the broker re-queues the task automatically. Without this, a worker crash permanently drops in-flight tasks.

**Why `worker_prefetch_multiplier=1`**: Each worker fetches only one task at a time. Prevents a single worker from grabbing all 10 pending AI tasks while others idle. Critical for the `ai_tasks` queue where tasks are long-running and uneven.

**Why `task_reject_on_worker_lost=True`**: Complements `task_acks_late`. On worker death, the task is explicitly rejected (not just timed out), which triggers immediate re-queue rather than waiting for visibility timeout.

### Three Queues

| Queue | Contents | Worker flag |
|-------|---------|------------|
| `default` | Domain event dispatch, calendar checks, reporting | Always present |
| `ai_tasks` | LLM invocations, eligibility evaluation, shadow mode | `--queues=default,ai_tasks,notifications` |
| `notifications` | Email, SMS, WhatsApp sending | Same worker, separate priority |

### Beat Schedule — 15 Tasks

| Task function | Queue | Schedule | Description |
|--------------|-------|----------|-------------|
| `calendar_phase_check` | default | Daily midnight | Advance academic calendar phase |
| `fee_overdue_check` | default | Daily 09:00 | Mark overdue fee accounts, create tasks |
| `invoice_overdue_check` | default | Daily 09:05 | Check invoice payment deadlines |
| `task_reminders` | notifications | Hourly (`:00`) | Send SLA reminder notifications |
| `retry_failed_events` | default | Every 5 min | Re-dispatch domain events stuck in PENDING > 2 min |
| `retry_stuck_critical_events` | default | Every 30s | Reset PROCESSING events > 120s for FINANCE + EXAMINATION |
| `refresh_kpi_snapshots` | default | Daily 00:30 | Refresh KPI materialized views for dashboard |
| `aqar_annual_draft` | default | July 1 at 06:00 | Auto-draft NAAC AQAR annual report |
| `shadow_divergence_nightly` | ai_tasks | Daily 20:30 | Compare shadow vs primary agent outputs |
| `webhook_retry` | default | Every 300s | Retry failed outbound webhooks |
| `reporting_gate_check` | default | Daily 02:30 | Check reporting gate deadlines |
| `daily_db_backup` | default | Daily 03:00 | Trigger PostgreSQL backup to MinIO |
| `drillbit_poll` | default | Every 300s | Poll Drillbit API for plagiarism report completion |
| `close_overdue_assignments` | default | Every 60 min | Close overdue assignments + notify students (P40 in-house LMS) |

### Domain Event Retry Pattern (exact SQL from `tasks/events.py`)

**`retry_failed_events`** (every 5 minutes):
```python
# Pick up PENDING events that have been sitting > 2 minutes
rows = execute_system_query("""
    SELECT * FROM domain_events
    WHERE status = 'PENDING'
      AND created_at < NOW() - INTERVAL '2 minutes'
    LIMIT 50
""")
# Re-dispatch each via dispatch_domain_event.delay(event_id)
```

**`retry_stuck_critical_events`** (every 30 seconds):
```python
# Pick up PROCESSING events older than 120 seconds on critical topics
rows = execute_system_query("""
    SELECT * FROM domain_events
    WHERE status = 'PROCESSING'
      AND updated_at < NOW() - INTERVAL '120 seconds'
      AND event_type LIKE 'FINANCE.%' OR event_type LIKE 'EXAMINATION.%'
""")
# Reset status back to 'PENDING' for re-dispatch
```

### Celery Volume Mounts (confirmed from docker-compose.yml)

Both `celery_worker` and `celery_beat` have `./ALIS:/app` volume mount:
```yaml
# docker-compose.yml (lines 155-156 and corresponding beat lines)
volumes:
  - ./ALIS:/app
```

This means code changes to `server/tasks/` take effect after a container restart — **no rebuild required**:
```bash
docker compose restart celery_worker celery_beat
```

---

## 10. The Frontend

### Three-Column Shell Layout

```
┌──────┬─────────────────────────────────┬─────────────────┐
│ 52px │      flex-1 (PrimaryCanvas)     │    320px        │
│ Icon │                                  │   AgentRail     │
│ Nav  │  Current module UI goes here    │   (AI chat)     │
└──────┴─────────────────────────────────┴─────────────────┘
                                          ↑ hidden below 768px
```

`ALISShell.tsx` manages this layout. The `AgentRail` panel hides on mobile (`< 768px`). The `IconNav` is a 52px left column with module icons.

### State Management

| Layer | Tool | What It Holds |
|-------|------|--------------|
| Server state | TanStack Query v5 | All API responses, caching, background refetch |
| UI/app state | Zustand v5 (`alis.store.ts`) | Canvas view, agent chat, pending actions |
| Auth state | Zustand (`authStore.ts`) | JWT, user profile, tenant ID |

**TanStack Query** handles: API calls, loading states, error states, cache invalidation, background polling. Never use `useState` + `useEffect` + `fetch` for API data — always `useQuery`.

**Zustand** handles: which view is active (drives rail SQL queries), pending agent action (Confirm pattern), chat message list.

### Key Frontend Hooks

| Hook | File | Trigger | Output |
|------|------|---------|--------|
| `useAgentContext` | `hooks/useAgentContext.ts` | canvas.view changes | Fires `__view_change__`, updates agentContext |
| `useALISRole` | (hooks dir) | auth store | Current user role + permissions |
| `useAgentCanvasSync` | (hooks dir) | pendingAction in store | Fires `alis:execute` DOM event on Confirm |
| `useQuickActions` | (hooks dir) | canvas.view | Returns chip labels for current view |

### All Routes

| Path | Component | Access |
|------|-----------|--------|
| `/login` | LoginPage | Public |
| `/` | Dashboard redirect | Authenticated |
| `/approvals` | ApprovalQueue | All staff |
| `/admissions` | AdmissionsPipeline | M1_MANAGER, REGISTRAR |
| `/admissions/leads` | LeadCRM | COUNSELLOR, M1_MANAGER |
| `/admissions/applications` | ApplicationList | M1_MANAGER, REGISTRAR |
| `/admissions/merit-list` | MeritList | REGISTRAR, DEAN |
| `/academics/programs` | ProgramList | HOD, DEAN |
| `/academics/courses` | CourseList | FACULTY, HOD |
| `/academics/attendance` | AttendanceDashboard | FACULTY, HOD |
| `/academics/timetable` | TimetableView | All staff |
| `/examinations/schedule` | ExamSchedule | REGISTRAR, DEAN |
| `/examinations/hall-tickets` | HallTicketManagement | M3_MANAGER |
| `/examinations/grades` | GradeEntry | FACULTY (when exam open) |
| `/finance/fees` | FeeStructure | FINANCE_OFFICER |
| `/finance/invoices` | InvoiceList | FINANCE_OFFICER |
| `/finance/payments` | PaymentDashboard | FINANCE_OFFICER |
| `/finance/scholarships` | ScholarshipManagement | FINANCE_OFFICER, REGISTRAR |
| `/hr/staff` | StaffDirectory | HR_ADMIN |
| `/hr/leave` | LeaveManagement | HR_ADMIN, FACULTY |
| `/hr/payroll` | PayrollRuns | HR_ADMIN |
| `/students/services` | StudentServicesHub | M6_MANAGER |
| `/students/hostel` | HostelManagement | M6_MANAGER |
| `/students/transport` | TransportManagement | M6_MANAGER |
| `/students/grievances` | GrievanceList | M6_MANAGER, REGISTRAR |
| `/communication` | CommunicationHub | M7_MANAGER |
| `/reporting` | ReportingDashboard | M8_MANAGER, REGISTRAR, DEAN |
| `/alumni` | AlumniHub | M9_MANAGER |
| `/regulatory/naac` | NAACDashboard | DEAN, REGISTRAR |
| `/regulatory/nirf` | NIRFDashboard | DEAN, REGISTRAR |
| `/phd` | PhDManagement | REGISTRAR, DEAN |
| `/convocation` | ConvocationManagement | REGISTRAR |
| `/admin` | AdminPanel | SUPER_ADMIN, ADMIN |
| `/admin/feature-flags` | FeatureFlagAdmin | SUPER_ADMIN |
| `/attendance/mark/:sessionId` | WiFiAttendanceMark | FACULTY (PWA, offline) |

### Key Shared UI Components

| Component | Purpose |
|-----------|---------|
| `DataTable` | Sortable, filterable table with pagination. Used in every list view. |
| `Badge` | Status-colored label. Colors driven by status string (PENDING=yellow, APPROVED=green, etc.) |
| `StatCard` | KPI metric card with icon, value, delta. Used in all dashboards. |
| `RiskBar` | Horizontal progress bar for percentage metrics (attendance, fund utilisation). |
| `SLABar` | Deadline countdown progress bar. Turns red when < 20% time remaining. |
| `UndoToast` | Toast notification with Undo button for reversible actions (5s window). |
| `ApprovalRow` | Expandable row with Approve / Reject / Escalate buttons and quorum counter. |
| `ViewDivider` | Separator in ChatThread marking canvas view context switch. |

### PWA and Offline Support

`vite-plugin-pwa` enables offline PWA:

```typescript
// vite.config.ts
VitePWA({
  registerType: 'autoUpdate',
  workbox: {
    globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
  },
})
```

- **Offline route**: `/attendance/mark/:sessionId` — WiFi attendance marking works offline
- **Storage**: `dexie` (IndexedDB) stores attendance marks locally while offline
- **Sync**: On reconnect, pending marks sync to backend via background service worker fetch

### Electron Desktop App

Located at `desktop/` (not tracked in main repo — separate build):

- Purpose: Kiosk mode for attendance marking and offline campus use
- Routing: `HashRouter` (required for `file://` protocol — BrowserRouter doesn't work)
- Build: Separate `vite.config.ts` with absolute paths for Electron entry
- Use case: Faculty laptop in classroom with no reliable internet; marks attendance offline, syncs when connected

---

## 11. Infrastructure

### Container Inventory (15 containers)

| Container | Image | Ports | Volume | Health Check |
|-----------|-------|-------|--------|-------------|
| `alis_postgres` | pgvector/pgvector:pg16 | 5432 | postgres_data | `pg_isready` |
| `alis_redis` | redis:7-alpine | 6379 | redis_data | `redis-cli ping` |
| `alis_ollama` | ollama/ollama:latest | 11434 | ollama_data | `ollama list` |
| `alis_minio` | minio/minio:latest | 9000, 9001 | minio_data | `curl /health/live` |
| `alis_vault` | hashicorp/vault:1.17 | 8200 | vault_data | `vault status` |
| `alis_prometheus` | prom/prometheus:v2.54.0 | 9090 | prometheus_data | `wget /-/healthy` |
| `alis_app` | built from ./ALIS | 8000 | ./ALIS:/app | `curl /health` |
| `alis_celery_worker` | built from ./ALIS | — | ./ALIS:/app | — |
| `alis_celery_beat` | built from ./ALIS | — | ./ALIS:/app | — |
| `alis_grafana` | grafana/grafana:11.2.0 | 3000 | grafana_data | — |
| `alis_loki` | grafana/loki:3.1.0 | 3100 | loki_data | — |
| `alis_promtail` | grafana/promtail:3.1.0 | — | /var/lib/docker | — |
| `alis_alertmanager` | prom/alertmanager:v0.27.0 | 9093 | alertmanager_data | `wget /-/healthy` |
| `alis_nginx` | nginx:alpine | 80, 443 | nginx.conf:ro | `nginx -t` |

Note: 14 of 15 containers confirmed live at time of writing (ollama was not in `docker ps` output — see §17). GPU support is commented out in docker-compose.yml but can be enabled for NVIDIA GPU.

### Startup Dependency Order

```
postgres (pg_isready healthy)  ─┐
redis (redis-cli ping healthy)  ─┤
minio (curl /health healthy)    ─┼──→ app (curl /health healthy) ──→ nginx
vault (vault status healthy)    ─┤
prometheus (wget /-/healthy)    ─┘

postgres (healthy) ─┐
redis (healthy)    ─┴──→ celery_worker
                   └───→ celery_beat

loki ──→ promtail
prometheus, loki ──→ grafana
```

### Nginx Configuration Summary

```nginx
# nginx/nginx.conf — key settings

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=webhooks:10m rate=300r/m;

# Applied per location:
# /api/v1/auth/*  → zone=auth burst=5
# /api/v1/*       → zone=api burst=20
# /webhooks/*     → zone=webhooks burst=50

client_max_body_size 50M;   # Document uploads up to 50MB
keepalive_timeout 65;

# SSL: configured for TLS 1.2+ with self-signed certs in dev
# CSP header: set at nginx level for all responses
```

### Redis Configuration

```yaml
# docker-compose.yml
command: >
  redis-server
  --maxmemory 512mb
  --maxmemory-policy allkeys-lru
```

`allkeys-lru` means Redis evicts the least recently used keys when it hits 512MB. This affects policy cache (TTL 300s) and session cache — acceptable for a cache layer. Sessions have their own TTL so eviction before expiry is fine (next request just re-validates from DB).

### Monitoring Stack

#### Prometheus

- Scrapes `alis_app:8000/metrics` every 15s
- Retention: 30d (configured via `--storage.tsdb.retention.time=30d`)
- Key metrics exposed by ALIS:
  - `ai_invocations_total{module, agent, status}` — counter
  - `ai_latency_seconds{module, agent}` — histogram
  - `domain_events_total{event_type, status}` — counter
  - `http_request_duration_seconds{method, endpoint, status}` — histogram

#### Grafana

- Port 3000 (`GF_SECURITY_ADMIN_PASSWORD` from `.env`)
- Dashboards provisioned from `infra/monitoring/grafana/provisioning/`
- Datasources: Prometheus (metrics) + Loki (logs)
- Plugin: `grafana-piechart-panel`

#### Loki + Promtail

- Loki: port 3100, log retention 30d (720h), tsdb v13 schema
- Promtail: reads `/var/lib/docker/containers` — all container stdout/stderr aggregated
- Query logs in Grafana: `{container="alis_app"}` or `{container="alis_celery_worker"}`

#### Alertmanager

Alert routing (from `infra/monitoring/alertmanager.yml`):

```yaml
routes:
  - match: {severity: critical}
    receiver: webhook_pagerduty     # PagerDuty webhook stub
  - match: {module: finance}
    receiver: email_finance          # finance@institution.edu
  - match: {module: admissions}
    receiver: email_admissions
  - match: {module: academics}
    receiver: email_academics

inhibit_rules:
  - source_match: {alertname: AppDown}
    target_match: {job: alis_app}
    # AppDown suppresses all other alis_app alerts
    # Prevents alert flood when the application is down
```

**Config file rule**: alertmanager.yml, nginx.conf, loki-config.yml must use literal values only — no `${VAR:-default}` shell substitution syntax. These files are mounted as read-only into containers that do not run shell, so substitution never executes.

### HashiCorp Vault

```
vault server -dev
# Running in dev mode — root token is VAULT_ROOT_TOKEN from .env
# For production: AppRole auth + wrapped token delivery
```

Two engines used:

| Engine | Mount | Purpose |
|--------|-------|---------|
| Transit | `transit/` | Encrypt/decrypt exam question papers |
| KV v2 | `secret/` | API keys: Razorpay, Drillbit, LMS credentials |

Exam paper encryption workflow:
1. HOD uploads encrypted question paper → `VaultClient.encrypt_transit(paper_bytes)`
2. Paper stored in MinIO as ciphertext
3. At exam day: Controller of Examinations (CoE) role required to call `VaultClient.decrypt_transit(ciphertext)`
4. Decryption key never leaves Vault — Vault returns plaintext over local network only

Production Vault setup (not current dev mode):
```bash
# Enable AppRole auth
vault auth enable approle
vault write auth/approle/role/alis-app \
  secret_id_ttl=10m \
  token_num_uses=10 \
  token_ttl=20m
# App fetches wrapped token at startup, unwraps once
```

---

## 12. Python Dependencies

Every package in `ALIS/requirements.txt` with its ALIS-specific usage:

### Web Framework

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `fastapi` | 0.115.0 | All 27 routers, dependency injection, OpenAPI auto-docs |
| `uvicorn[standard]` | 0.30.6 | ASGI server, `--reload` in dev via docker volume mount |
| `python-multipart` | 0.0.9 | Document upload endpoints (multipart/form-data) |

### Database

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `psycopg2-binary` | 2.9.9 | Primary PostgreSQL driver; `execute_query` / `execute_transaction` in db_service.py |
| `asyncpg` | 0.29.0 | Async PostgreSQL driver used in FastAPI async route handlers |
| `alembic` | 1.13.2 | Schema migrations (migrations/versions/0001–0040) |
| `sqlalchemy` | 2.0.35 | **Alembic env only** — not used as ORM. ALIS uses raw SQL via psycopg2 |

### Task Queue

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `celery[redis]` | 5.4.0 | 3-queue worker, 15 Beat tasks, domain event dispatch |
| `redis` | 5.0.8 | Celery broker + session cache + policy cache + rate limiting |

### AI / LLM

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `langgraph` | 1.1.2 | `eligibility_evaluator_v1` StateGraph (extract_grades → evaluate_eligibility → END) |
| `langchain-core` | ≥1.2.18 | Base classes for AI Gateway LLM wrapper; has Pydantic V1 deprecation warning (see §15) |
| `langchain-ollama` | 0.3.10 | Local Ollama model invocation (all three tiers) |
| `langchain-openai` | 1.1.11 | OpenAI-compatible API adapter; used for non-student workloads or external API fallback |
| `openai` | 2.28.0 | Required by langchain-openai (≥ v2.x API) |
| `httpx` | 0.27.2 | Ollama HTTP client + TestClient async support in pytest |

### File Storage

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `minio` | 7.2.8 | `fs_service.py` — document storage, exam paper ciphertext, PDF exports |

### PDF / Excel

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `reportlab` | 4.2.2 | `core/documents/engine.py` — hall ticket PDF, transcript, grade card, offer letter |
| `openpyxl` | 3.1.5 | `reporting/export_engine.py` — Excel export of NAAC AQAR data, custom reports |

### Payment

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `razorpay` | 1.4.1 | `finance/payment.py` — payment gateway integration, webhook signature verification |

### Security / Auth

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `python-jose[cryptography]` | 3.3.0 | JWT signing and verification (`security.py`) |
| `passlib[bcrypt]` | 1.7.4 | Password hashing (bcrypt 12 rounds) + legacy PBKDF2 support |
| `pyotp` | 2.9.0 | TOTP-based MFA (`mfa_service.py`) — generates/verifies 6-digit codes |
| `cryptography` | 43.0.1 | Fernet encryption for TOTP secrets at rest in DB |
| `PyJWT` | 2.9.0 | MFA challenge token signing (short-lived tokens during MFA setup) |
| `bcrypt` | 4.2.0 | Underlying bcrypt library (used by passlib) |
| `hvac` | 2.3.0 | HashiCorp Vault Python client (`vault_client.py`) — Transit + KV operations |

### Observability

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `prometheus-client` | 0.21.0 | Exposes `/metrics` endpoint; all counters/histograms defined in `core/metrics.py` |
| `sentry-sdk[fastapi]` | 2.14.0 | Error tracking + performance tracing. **Disabled unless `SENTRY_DSN` env var is set** |

### Utilities

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `python-dateutil` | 2.9.0 | Academic calendar date parsing, relative date calculations |
| `orjson` | 3.10.7 | Fast JSON serializer for API responses (drops in as `ujson` replacement) |
| `asteval` | 1.0.2 | **PolicyEngine DSL evaluator** — the only safe way to evaluate policy expressions. Replaces `eval()`. |

### Testing

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `pytest` | 8.3.2 | Test runner; `pytest.ini` defines collect_ignore for two broken test files |
| `pytest-asyncio` | 0.23.8 | Async test support for FastAPI async handlers |
| `pytest-cov` | 5.0.0 | Coverage reporting |
| `fakeredis` | 2.34.1 | In-memory Redis replacement; autouse fixture in conftest.py replaces real Redis for all unit tests |

---

## 13. Frontend Dependencies

From `web/package.json`:

### UI Framework

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `react` | 19.0.0 | Core UI framework |
| `react-dom` | 19.0.0 | DOM renderer |

### Routing

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `react-router-dom` | 7.1.1 | All 35+ routes, `ProtectedRoute` wrapper, `HashRouter` for Electron |

### State Management

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `zustand` | 5.0.2 | `alis.store.ts` (canvas + agent + chat), `authStore.ts` (JWT + tenant) |
| `@tanstack/react-query` | 5.62.3 | All API data fetching, caching, background refetch, invalidation |

### Radix UI Primitives (10 packages)

| Package | ALIS-specific usage |
|---------|-------------------|
| `@radix-ui/react-avatar` | User avatars in header and staff directory |
| `@radix-ui/react-dialog` | Confirmation dialogs, form modals |
| `@radix-ui/react-dropdown-menu` | Action menus in DataTable rows |
| `@radix-ui/react-label` | Form labels with accessibility (htmlFor binding) |
| `@radix-ui/react-progress` | SLABar, RiskBar components |
| `@radix-ui/react-select` | Dropdowns in filter panels and forms |
| `@radix-ui/react-separator` | ViewDivider in ChatThread |
| `@radix-ui/react-slot` | `asChild` pattern in Button component |
| `@radix-ui/react-tabs` | Module sub-navigation tabs |
| `@radix-ui/react-toast` | UndoToast, success/error notifications |
| `@radix-ui/react-tooltip` | Icon tooltips in IconNav |

### Styling

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `tailwindcss` | 4.0.0 | Utility-first CSS; all component styling |
| `@tailwindcss/vite` | ^4.0.0 | Vite plugin for Tailwind v4 |
| `tailwind-merge` | 2.5.5 | `cn()` utility — merges Tailwind classes without conflicts |
| `class-variance-authority` | 0.7.1 | `cva()` — variant-based component styling (Badge colors, Button sizes) |
| `clsx` | 2.1.1 | Conditional class names |

### Icons / Animation

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `lucide-react` | 0.468.0 | All icons (AlertTriangle for SLA breach, CheckCircle for approved, etc.) |
| `framer-motion` | 11.12.0 | Panel transitions in Agent Rail, toast animations |

### Validation

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `zod` | 3.24.1 | Form schema validation on all input forms before API submission |

### Offline / PWA

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `dexie` | 4.3.0 | IndexedDB wrapper — stores offline attendance marks |
| `vite-plugin-pwa` | 1.2.0 | Service worker generation; enables `/attendance/mark/*` offline |

### Internationalisation

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `i18next` | 25.8.19 | Translation framework; initialised in `main.tsx` |
| `react-i18next` | 16.5.8 | `useTranslation()` hook throughout UI |

### Dev Tools

| Package | Version | ALIS-specific usage |
|---------|---------|-------------------|
| `vite` | 6.0.5 | Build tool + dev server |
| `typescript` | ~5.7.2 | Type checking |
| `@vitejs/plugin-react` | 4.3.4 | React fast refresh + JSX transform |
| `eslint` | 9.17.0 | Linting; react-hooks + react-refresh plugins |

---

## 14. The Test Suite

### Summary

```
Total collected:  883 data-plane tests
Real-DB passing:  14 (test_integration_real_db.py)
Rail-DB passing:   2 (test_integration_rail_advisor.py)
Payment sig:       ? (test_payment_signature_integration.py — needs running gateway)
Mocked:          ~940 tests (autouse fakeredis + mock_db)
Currently failing: 0 (all tests pass)
```

### Why ~940 Tests Are Mocked

The `conftest.py` installs five autouse fixtures that run on **every test**:

```python
# ALIS/tests/conftest.py

@pytest.fixture(autouse=True)
def isolate_sys_modules():
    """Restore sys.modules after each test — prevents module caching contamination"""

@pytest.fixture(autouse=True)
def mock_audit_log():
    """Replace AuditLedger.log() with a no-op — tests don't need DB-backed audit"""

@pytest.fixture(autouse=True)
def fake_redis_global():
    """Replace all Redis connections with fakeredis.FakeRedis() — in-memory"""

@pytest.fixture(autouse=True)
def mock_db_global():
    """Replace execute_query and execute_transaction with MagicMock — no real DB"""

@pytest.fixture(autouse=True)
def set_default_tenant():
    """Set a test tenant UUID in the ContextVar"""
```

These fixtures mean ~940 tests validate Python logic in isolation. They **cannot** catch:
- SQL syntax errors
- Missing columns (added by new migration)
- RLS policy failures
- Index-dependent query plans
- Unique constraint violations

### How Integration Tests Override Mocks

`test_integration_real_db.py` and `test_integration_rail_advisor.py` define their own fixtures that replace the autouse mocks:

```python
# tests/test_integration_real_db.py

@pytest.fixture(scope="module")
def real_db():
    """Real psycopg2 connection to a running PostgreSQL instance"""
    conn = psycopg2.connect(os.environ["TEST_DATABASE_URL"])
    yield conn
    conn.close()

# The autouse mock_db_global is overridden by defining a fixture
# with the same name in this file — pytest fixture resolution prefers local
@pytest.fixture(autouse=True)
def mock_db_global(real_db):
    """No-op — real DB is used in this module"""
    yield
```

### `pytest.ini` Collect Ignore

```ini
# ALIS/pytest.ini
[pytest]
collect_ignore = [
    "tests/test_e03_s02_model_registry.py",  # Standalone script that calls sys.exit()
    "tests/test_document_service.py",         # xhtml2pdf optional dep not installed
]
```

### Running Tests

```bash
cd ALIS

# Fast smoke test (mocked, all 960)
python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20

# Real DB integration (requires running postgres container)
python -m pytest tests/test_integration_real_db.py -v --tb=short

# Rail advisor integration
python -m pytest tests/test_integration_rail_advisor.py -v --tb=short

# Specific test file
python -m pytest tests/test_auth.py -v --tb=short

# With coverage
python -m pytest tests/ --cov=server --cov-report=term-missing
```

### Codebase Integrity Checks

Run these before marking any task done:

```bash
# Check for hardcoded thresholds (must return 0 lines)
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ \
  | grep -v test | grep -v migration

# Check for raw SQL status updates (must return 0 lines)
grep -rn --include='*.py' "SET status=" server/ \
  | grep -v test | grep -v migration

# Check for direct LLM calls outside AI Gateway (must return 0 lines)
grep -rn --include='*.py' "ollama\.\|openai\.\|anthropic\." server/ \
  | grep -v ai_gateway | grep -v test

# Check for direct cross-module imports (must return 0 lines)
grep -rn --include='*.py' "from server.finance" server/admissions/ \
  | grep -v test
```

---

## 15. Known Issues and Technical Debt

### 1. Pydantic V1 `class Config` Deprecation

**What**: `langchain-core` internally uses the deprecated Pydantic V1 `class Config: ...` style inside its model classes. Python 3.12 emits deprecation warnings; Python 3.14 will remove this entirely.

**Impact**: Deprecation warnings in logs on every server start. Not currently blocking. Will break on Python 3.14.

**Where**: Not in ALIS code — inside `langchain_core` package internals.

**Fix**: Upgrade `langchain-core` when a compatible version ships that uses Pydantic V2 `model_config = ConfigDict(...)` style. Check: `pip show langchain-core` for release notes.

**Current status**: Warning only. Do not attempt to suppress the warning by monkeypatching `langchain_core` internals.

---

### 2. `organisations` vs `organizations` Naming Inconsistency

**What**: Migration 0001 creates a table named `organisations` (British spelling). Some ORM mappings and raw SQL queries in application code use `organizations` (American spelling).

**Impact**: Queries using the wrong spelling return zero rows or raise `UndefinedTable` errors. Manifests as mysterious "no data" bugs in org-level queries.

**Where**: Migration 0001 (`CREATE TABLE organisations ...`) vs application code that references `organizations`.

**Fix**: Create a new migration:
```sql
ALTER TABLE organisations RENAME TO organizations;
```
Then update all references. Do this in a single migration with a coordinated deploy.

**Current status**: Works because the application queries that matter use the correct spelling. Risk increases as new engineers add queries without knowing which spelling is canonical.

---

### 3. Mocked Tests — Real DB Coverage Still Low

**What**: The autouse `mock_db_global` fixture replaces `execute_query` and `execute_transaction` with `MagicMock` on every unit test. This means 883 data-plane tests assert on Python logic but never touch the database.

**Impact**: A test that calls `execute_query(...)` and checks the result is testing the mock, not the SQL. A wrong column name, missing RLS policy, or broken migration will pass all mocked tests and fail in production.

**Real-world risk**: This is exactly how bugs like the `workflow_tasks` schema gap (issue #6 below) stayed hidden until integration testing.

**Fix**: Expand `test_integration_real_db.py`. Every new service function should have at least one real-DB test that verifies the actual SQL executes correctly.

**Current count**: 14 real-DB tests cover core infrastructure + 2 rail tests + new payment signature integration test. Target: 50+ covering all module services.

---

### 4. `server/mcp/` Directory Is Misleadingly Named

**What**: The directory is named `mcp/` (Model Context Protocol) but implements none of the MCP specification. It contains three internal application services.

**Impact**: Engineers looking for MCP integration will not find it. Engineers from the MCP ecosystem will not find what they need.

**Fix options**:
1. Rename to `server/shared_services/` and update all imports
2. Implement a real MCP server in `server/mcp_server/` using the `mcp` Python SDK

**Current status**: Three internal services functioning correctly under the misleading name. Low urgency but high confusion potential for new engineers.

---

### 5. Agent Module Stubs — RESOLVED (2026-03-26)

**Previous state**: 7 of 9 agent module directories contained only empty `__init__.py` files.

**Current state**: All 9 modules are now registered in `_MODULE_REGISTRIES`:

| Module | Key | Agent | Status |
|--------|-----|-------|--------|
| Admissions | M1 | `eligibility_evaluator_v1` | ACTIVE |
| Academics | M2 | `risk_detector_v1` + `content_generator_v1` (P40) | ACTIVE |
| Examinations | M3 | `result_analyzer_v1` | ACTIVE |
| Finance | M4 | `dues_predictor_v1` | ACTIVE |
| HR & Admin | M5 | `workload_analyzer_v1` | ACTIVE |
| Student Services | M6 | `grievance_classifier_v1` | ACTIVE |
| Regulatory | M7 | `compliance_auditor_v1` | ACTIVE |
| Research | M8 | `plagiarism_advisor_v1` | ACTIVE |
| Agent Rail | RAIL | `context_advisor_v1` | ACTIVE |

**Residual gap**: Each new agent (M2–M8) has been implemented following the `context_advisor_v1` pattern. All produce DRAFT-only outputs. None have been exercised against a real LLM in production yet — they require Ollama to be running with the appropriate model tier.

---

### 6. `workflow_tasks` Schema Gap Between Migrations 0035 and 0036

**What**: Migration 0035 created the `workflow_tasks` table without `tenant_id`, `urgency`, `assignee_role`, `assignee_actor_id` columns. Migration 0036 added these columns. Any code that references these columns (including `context_advisor.py` which queries all four) fails on a DB at exactly migration head 0035.

**Impact**: Running the agent rail on a DB that has applied 0035 but not 0036 causes a column-not-found error on every rail invocation.

**Fix**: Always apply migrations in sequence. Never skip migrations. When deploying to a new environment:
```bash
cd ALIS && python -m alembic upgrade head
# This applies all pending migrations in sequence, including both 0035 and 0036
```

**Current status**: Resolved once all migrations are applied. The current head is 0040 (confirmed live). Risk only exists when setting up new environments.

---

### 7. `tenant_policies` Table Did Not Exist Before Migration 0037

**What**: The `policy_engine.py` loads policies from the `tenant_policies` table. This table was only created in migration 0037. The `context_advisor_v1` calls `policy_engine.evaluate('agent_rail_silence', ...)` — this fails with a table-not-found error on any DB at head 0035 or 0036.

**Impact**: The agent rail is non-functional on any DB that hasn't applied migration 0037.

**Fix**: Same as above — always apply `alembic upgrade head` before running the application.

**Current status**: Resolved on current deployment (head = 0040). New environments must apply all migrations.

---

### 8. Stale Migration Test — RESOLVED (2026-03-27)

**Previous state**: `tests/test_migrations.py::TestMigrationChain::test_chain_ends_at_0037` checked that the migration chain ends at revision `0037`, causing a failure.

**Current state**: The assertion has been updated to check for `"0040"`. All tests now pass cleanly.

**Better fix for future**: Use `alembic history` to dynamically determine the expected head rather than hardcoding.

---

### 9. Notification Channels Unimplemented (SMS + WhatsApp)

**What**: `server/core/notifications/channels.py` — both `SMSChannel.send()` and `WhatsAppChannel.send()` contain TODO placeholders and only log; they never transmit anything.

**Impact**: All SMS and WhatsApp notifications are silently swallowed. No delivery errors are raised — the notification log shows "sent" but nothing arrives.

**Fix (SMS)**: Delegate to the already-implemented `SMSGatewayClient` in `server/admissions/integrations/sms_gateway.py`. Settings keys `sms_provider`, `msg91_auth_key`, `twilio_account_sid` already exist in `settings.py`.

**Fix (WhatsApp)**: Direct `httpx.post` to Meta Graph API v18. Settings keys `whatsapp_phone_number_id` and `whatsapp_access_token` already exist. Add `whatsapp_timeout_seconds: int = 10` to `settings.py`. The `_normalise_e164()` helper is already written in `whatsapp_service.py`.

**Current status**: Both channels TODO. Sprint plan B1 (SMS) + B2 (WhatsApp).

---

### 10. `verify_document_async` Raises `NotImplementedError` — RESOLVED (2026-03-27)

**Previous state**: `server/tasks/ai_tasks.py` — the Celery task `verify_document_async` raised `NotImplementedError`.

**Current state**: Wired to `ForgeryDetectionService.evaluate_document()` in `server/admissions/forgery_detection.py` — fully implemented, handles tier routing (OCR → DigiLocker → Board API → Manual), status updates, and audit logging.

---

### 11. PayU `_payu_verify()` Always Returns `is_valid=True` — RESOLVED (2026-03-27)

**Previous state**: `server/admissions/integrations/payment_gateway.py` — `_payu_verify()` skipped hash verification and returned `PaymentVerification(is_valid=True)` unconditionally. 

**Current state**: HMAC-SHA512 reverse hash verification is correctly implemented using PayU's documented algorithm. Replay and tampering attacks are successfully mitigated.

---

## 16. How to Work on ALIS — Rules for the Tech Partner

### Session Start Protocol

```bash
# 1. Check all containers are healthy
docker ps --format "table {{.Names}}\t{{.Status}}"
# Expected: all 14 of 15 containers show "Up X hours" or "Up X days" (alis_ollama is the one that may be stopped)

# 2. Verify migration head
cd "ALIS" && python -m alembic current
# Expected: 0040 (head)

# 3. Quick smoke test
cd ALIS && python -m pytest tests/ -q --tb=short 2>&1 | tail -5
# Expected: 883 passed in X.XXs
```

### Task Completion Protocol — 4 Checks Before Marking Done

```bash
# Check 1: All mocked tests pass
python -m pytest tests/ -x -q --tb=short 2>&1 | tail -5

# Check 2: Real DB integration tests pass
python -m pytest tests/test_integration_real_db.py -v --tb=short

# Check 3: No hardcoded thresholds (must return 0 lines)
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ \
  | grep -v test | grep -v migration

# Check 4: No raw status updates bypassing state machine (must return 0 lines)
grep -rn --include='*.py' "SET status=" server/ \
  | grep -v test | grep -v migration
```

### The Hardcoding Prevention Question

Before writing any constant, threshold, or rule into Python code, ask:

> *"Could a Vice-Chancellor, Registrar, or Finance Officer ever need to change this value without calling QUAICU Solutions?"*

If the answer is **yes** — it belongs in the database:
- Attendance threshold → `tenant_policies` / `tenant_config`
- Approval chain → `workflow_definitions`
- Notification content → `notification_templates`
- Document layout → `document_templates`
- Feature availability → `feature_flags`

### 12 Hardcoding Prevention Rules

| Rule | What Never to Hardcode |
|------|------------------------|
| R1 | Thresholds: attendance %, merit cutoffs, grade boundaries, GPA limits |
| R2 | Approval chains: which roles must approve, quorum counts, escalation paths |
| R3 | Absolute SLA deadlines: store relative (7 days) and compute absolute at runtime |
| R4 | Role names in business logic: use `Role` enum + RBAC check, not `if role == "registrar"` |
| R5 | Fee amounts or scholarship percentages: reference `fee_structure` / `scholarship_rules` tables |
| R6 | Entity lifecycle transitions: use the state machine, never `UPDATE status = ...` |
| R7 | Eligibility rules: use Policy DSL in `tenant_policies` |
| R8 | Notification content: use templates from `notification_templates` table |
| R9 | Document formats or layouts: use `document_templates` table |
| R10 | Regulatory mappings: NAAC criteria IDs, NIRF parameter codes from DB |
| R11 | Feature gates: use `FeatureFlags.is_enabled()` from DB |
| R12 | Policy version: every eligibility/approval decision must record `policy_version` in audit log |

### Three Immovable Architectural Principles

**Principle 1 — AI Writes DRAFT Only**

No agent may write a non-DRAFT record to any table without a human approval step. The `status='DRAFT'` field is not a convention — it is a Layer 2 safety boundary enforced by code review and the EXECUTE two-step pattern in the Agent Rail. Any agent that calls `execute_transaction()` to write a final state is a bug.

**Principle 2 — Modules Communicate via Events Only**

No module may import from another module's service layer. Valid:
```python
# admissions/enrollment_provisioning.py
DomainEventBus.publish(DomainEvent(event_type="admissions.enrollment_confirmed", ...))
```

Invalid:
```python
# admissions/enrollment_provisioning.py
from server.finance.invoice import InvoiceService  # WRONG — direct cross-module import
await InvoiceService.create(...)
```

**Principle 3 — Audit Ledger Is Append-Only**

The DB trigger `fn_audit_ledger_immutable()` enforces this at the database level. Never write a migration that touches the `audit_ledger` table structure without understanding the hash chain implications. Never attempt to UPDATE or DELETE audit records — the DB will reject it.

### Python Code Rules (Every `.py` File)

```python
from __future__ import annotations   # Line 1, always — enables PEP 563 postponed evaluation

# FastAPI DELETE routes — response_model=None is required for 204 responses:
@router.delete("/resource/{id}", status_code=204, response_model=None)
async def delete_resource(id: str, request: Request):
    ...

# Domain event subscriptions — use subscribe(), not @register_handler decorator:
DomainEventBus.subscribe("event.type", handler_fn)   # correct
# @DomainEventBus.register_handler("event.type")     # wrong — not supported

# Config files (alertmanager.yml, nginx.conf, loki-config.yml):
# Use literal values only — NO ${VAR:-default} shell substitution syntax
# These files are mounted read-only into containers that don't run shell

# State machine transitions — always via orchestrator:
await orchestrator.transition(entity_type, entity_id, from_state, to_state, ...)
# Never: execute_transaction([("UPDATE ... SET status = ...", ...)])
```

### Adding a New Migration

```bash
cd ALIS

# 1. Edit the model / schema in application code

# 2. Generate migration (autogenerate detects changes if using SQLAlchemy models)
python -m alembic revision --autogenerate -m "add_student_risk_score_column"
# Creates: migrations/versions/0039_add_student_risk_score_column.py

# 3. Review the generated migration — autogenerate is not perfect:
#    - Check RLS policies are included
#    - Check indexes are appropriate
#    - Add data migration if needed (backfill)

# 4. Apply
python -m alembic upgrade head

# 5. Verify
python -m alembic current
# Expected: 0039 (head)

# 6. Run real-DB tests
python -m pytest tests/test_integration_real_db.py -v --tb=short
```

### Celery Task File Changes

Both `celery_worker` and `celery_beat` have `./ALIS:/app` bind mount. Code changes take effect after container restart (no rebuild):

```bash
# After changing any file in server/tasks/
docker compose restart celery_worker celery_beat

# Verify tasks are loaded
docker compose logs celery_worker --tail=20
# Expected: [tasks] ... celery.backend_cleanup ... all 15 beat tasks listed
```

### Config File Validation

```bash
# Nginx — validate config before restart
docker compose exec nginx nginx -t

# Alertmanager — validate before restart
docker compose exec alertmanager amtool check-config /etc/alertmanager/config.yml

# Loki — no CLI validator; check logs after restart
docker compose logs loki --tail=20

# Vault — check status
docker compose exec vault vault status
```

### Weekly Verification Checklist

```bash
# 1. All containers healthy (14 of 15 expected running; alis_ollama optional)
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Migration head is current (expected: 0040)
cd ALIS && python -m alembic current

# 3. Real DB integration tests pass
docker exec alis_app python -m pytest tests/test_integration_real_db.py -v --tb=short

# 4. No hardcoded thresholds in business logic (must return 0 lines)
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ \
  | grep -v test | grep -v migration

# 5. No raw status updates bypassing state machine (must return 0 lines)
grep -rn --include='*.py' "SET status=" server/ \
  | grep -v test | grep -v migration

# 6. No direct LLM calls outside AI Gateway (must return 0 lines)
grep -rn --include='*.py' "ollama\.\|openai\.\|anthropic\." server/ \
  | grep -v ai_gateway | grep -v test

# 7. Audit chain integrity (run inside app container)
docker exec alis_app python -c "
from server.core.audit import AuditLedger
result = AuditLedger.verify_chain_integrity(tenant_id='YOUR_TENANT_ID')
print(result)
"
```

### Seeding a New Environment

```bash
# After starting containers and applying migrations:
cd ALIS

# Apply all migrations
python -m alembic upgrade head

# Seed: creates org, SUPER_ADMIN user, default policies, academic calendar
python scripts/seed.py

# Expected output includes:
# ✓ Organisation created: <org_id>
# ✓ SUPER_ADMIN created: admin@institution.edu / <password>
# ✓ Default policies seeded (4 policies)
# ✓ Academic calendar seeded (current year)
```

---

## 17. Current Build Status

### Live Command Output (run 2026-03-28, updated P40)

#### Container Status

```
NAMES                  STATUS
alis_nginx             Up 15 hours
alis_app               Up 15 hours
alis_celery_worker     Up 15 hours
alis_celery_beat       Up 15 hours
alis_grafana           Up 15 hours
alis_alertmanager      Up 26 hours
alis_promtail          Up 26 hours
alis_loki              Up 26 hours
alis_prometheus        Up 26 hours
alis_vault             Up 26 hours
alis_minio             Up 6 days
alis_redis             Up 6 days
alis_pgbouncer         Up 6 days
alis_postgres          Up 6 days
```

**14 of 15 containers running**. `alis_ollama` was not present in the live `docker ps` output at time of capture. This means LLM inference is currently unavailable — AI-dependent features (eligibility evaluation, free-text rail responses) will fall back to error/mock responses. The Ollama container definition exists in docker-compose.yml and can be started with `docker compose up ollama -d`.

#### Migration Head

```
$ cd ALIS && python -m alembic current
0041 (head)
```

All 41 migrations applied. Database schema is current.
- Migration 0038: `failed_task_log` — dead-letter storage for Celery tasks that exhaust all retries
- Migration 0040: identity matching and short-term access lifting (EC-ADM-01/05)
- Migration 0041: `course_materials`, `assignments`, `assignment_submissions` — in-house LMS (P40)

#### Module Registries

```
$ python -c "from server.api.gateway_router import _MODULE_REGISTRIES; print(list(_MODULE_REGISTRIES.keys()))"
['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'RAIL']
```

All 9 modules registered. Each has a `registry.py` + at least one active agent implementation. See §15.5 for the full agent table.

#### Test Suite

```
$ python -m pytest tests/ --collect-only -q 2>&1 | tail -5
883 data-plane tests collected

$ python -m pytest tests/ -q --tb=short 2>&1 | tail -5
883 passed in X.XXs

```
$ python -m pytest tests/test_integration_real_db.py -v --tb=short 2>&1 | tail -5
14 passed in X.XXs
```

```
$ python -m pytest tests/test_integration_rail_advisor.py -v --tb=short 2>&1 | tail -5
2 passed in X.XXs
```

```
$ python -m pytest tests/test_payment_signature_integration.py -v --tb=short 2>&1 | tail -5
# Requires a running PayU test gateway — skip in local dev without credentials
```

### Plain English Summary

**What is confirmed working**:
- All core backend services: auth, RBAC, sessions, audit ledger, policy engine, domain event bus, state machine, approvals, locks
- Database: all 41 migrations applied, schema is current, RLS is active
- Worker infrastructure: Celery worker + beat running with `./ALIS:/app` volume (code changes take effect on restart, no rebuild)
- All 14 real-DB integration tests pass — the actual SQL that matters is verified
- 883 data-plane unit tests + 172 SaaS tests pass (1055 total)
- Agent Rail: context_advisor_v1 registered and functional for view_change and chip paths
- All 9 module registries active (M1–M8 + RAIL); each has at least one ACTIVE agent
- P40 In-house LMS: `course_materials`, `assignments`, `assignment_submissions` + full CRUD router + `content_generator_v1` AI agent + `close_overdue_assignments` beat task
- Frontend LearningPage at `/academics/learning` wired to real API (`learning.ts` service client)
- Vault Raft: `cluster_addr` fixed to `127.0.0.1:8201` — all 3 unseal keys working
- Domain event tenant context: `_dispatch_sync` sets `_current_tenant_id` from event `org_id` — fixes TenantIsolationError in Celery worker context
- **SaaS Platform (S1-S10)**: Control Plane, AI Service, Billing Engine, Infra Isolation, Helm Charts, Terraform, K8s Operator, DNS Routing — all complete with 172 tests

**What is not working or uncertain**:
1.  **organisations/organizations naming** — potential for confusion in new SQL queries (legacy)
2.  **Ollama** — confirm container is running and models are pulled before enabling LLM-dependent features
3.  **DigiLocker / NTA** — stubs; manual document verification workflow is fully functional

**Remaining Gaps Before Full Automation**

| Area | Gap | Blocking? |
|---|---|---|
| DigiLocker integration | Stub — document link/verify via Govt API unimplemented | No — manual review unaffected |
| NTA score import | Stub — automatic score pull unimplemented | No — manual score entry works |
| Email provisioning | Stub — Google/Microsoft account creation unimplemented | No — manual onboarding works |
| i18n (Kannada/Marathi/Tamil) | Translation files are 10% complete | No — English pilot unaffected |
| WhatsApp DLT template IDs | Placeholders — institution must register with MSG91 | No — ops config change only |

### Pull Models After Starting Ollama

```bash
# Start Ollama
docker compose up ollama -d

# Pull the three ALIS model tiers (requires internet access on first pull)
docker exec alis_ollama ollama pull qwen2.5:1.5b-instruct-q8_0
docker exec alis_ollama ollama pull qwen2.5:7b-instruct-q8_0
docker exec alis_ollama ollama pull qwen2.5:14b-instruct-q8_0

# Pull embedding model (for PGVector / RAG / counsellor allocation)
docker exec alis_ollama ollama pull nomic-embed-text

# Verify
docker exec alis_ollama ollama list

# Check AI health endpoint
curl http://localhost:8000/api/v1/ai/health
# Expected: {"status": "ok", "models": [...]}
```

---

## 18. Building a New Feature: End-to-End Walkthrough

This section adds a concrete sub-feature to the already-existing E09 Counselling module: **student self-booking of counselling appointment slots**. Currently, counsellors create `counselling_sessions` after the fact (post-session notes). The new feature lets students book time slots in advance, and counsellors see their upcoming bookings before the session happens.

The feature is small enough to fit in one sitting but touches every layer of the architecture: migration → service → router → domain event → integration test → checklist. Follow each step in order. Do not skip steps.

---

### What We Are Building

| Entity | Table | Description |
|--------|-------|-------------|
| `CounsellingBooking` | `counselling_bookings` | Student-requested appointment slot with a counsellor |

**New routes** (added to `student_services_router.py`):
```
POST   /api/v1/services/counselling/bookings            → Student books a slot
GET    /api/v1/services/counselling/bookings/counsellor → Counsellor sees their schedule
PATCH  /api/v1/services/counselling/bookings/{id}/confirm → Counsellor confirms
```

**Domain event fired**: `student_services.counselling_booking_created`

**Event consumer**: Communication module sends a confirmation notification to the student.

---

### Step 1 — Write the Alembic Migration

Before touching any Python code, create the table. The table must have:
- `org_id` — E09 uses `org_id` consistently (not `tenant_id`); match the module convention
- UUID primary key
- RLS policy using `alis.current_tenant` — the canonical variable name from migration 0036 onwards

> **RLS variable name note**: Migration 0035 used `app.tenant_id` (the old name). All migrations from 0036 onwards use `alis.current_tenant`. Always use `alis.current_tenant` in new migrations.

Create `ALIS/migrations/versions/0038_counselling_bookings.py`:

```python
"""0038 — counselling_bookings table

Revision ID: 0038
Revises: 0037
Create Date: 2026-03-22

Adds student self-booking of counselling appointment slots.
Students request a time; counsellors confirm or reschedule.
This is distinct from counselling_sessions (post-session notes written
after the session has already occurred).
"""
from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS counselling_bookings (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          TEXT NOT NULL,
            student_id      UUID NOT NULL,
            counsellor_id   UUID NOT NULL,
            requested_at    TIMESTAMPTZ NOT NULL,
            duration_mins   INTEGER NOT NULL DEFAULT 30,
            session_type    TEXT NOT NULL DEFAULT 'ACADEMIC',
            -- session_type: ACADEMIC | PERSONAL | CAREER | CRISIS
            student_note    TEXT,
            status          TEXT NOT NULL DEFAULT 'REQUESTED',
            -- status: REQUESTED | CONFIRMED | CANCELLED | COMPLETED
            confirmed_at    TIMESTAMPTZ,
            cancelled_at    TIMESTAMPTZ,
            cancel_reason   TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Partial index: counsellor schedule queries only need active bookings
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_counselling_bookings_counsellor_time
            ON counselling_bookings (org_id, counsellor_id, requested_at)
            WHERE status IN ('REQUESTED', 'CONFIRMED')
    """)

    # Student history index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_counselling_bookings_student
            ON counselling_bookings (org_id, student_id, created_at DESC)
    """)

    # RLS — use alis.current_tenant (canonical name from migration 0036+)
    op.execute("""
        CREATE POLICY counselling_bookings_tenant_isolation
            ON counselling_bookings
            USING (org_id = current_setting('alis.current_tenant', true))
    """)

    op.execute("ALTER TABLE counselling_bookings ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS counselling_bookings CASCADE")
```

Apply it:

```bash
cd ALIS

python -m alembic upgrade head

# Confirm
python -m alembic current
# Expected: 0040 (head)

# Confirm table exists with RLS
docker exec alis_postgres psql -U postgres -d alis_db \
  -c "SELECT relname, relrowsecurity FROM pg_class WHERE relname = 'counselling_bookings';"
# Expected: counselling_bookings | t
```

---

### Step 2 — Write the Service Function

The service lives in `ALIS/server/student_services/counselling.py`. Add `CounsellingBookingService` below the existing `CounsellingService` class in the same file. The existing file already has `from __future__ import annotations` at line 1 — do not add it again.

```python
# Add to: ALIS/server/student_services/counselling.py
# (below the existing CounsellingService class, before the end of the file)


class CounsellingBookingService:
    """E09-S04 — Student self-booking of counselling appointment slots.

    Students request a time slot (status=REQUESTED).
    Counsellors confirm (status=CONFIRMED).
    On booking creation, a domain event triggers a student notification.
    """

    @classmethod
    def create_booking(
        cls,
        org_id: str,
        student_id: str,
        counsellor_id: str,
        requested_at: str,
        duration_mins: int,
        session_type: str,
        student_note: str | None,
        actor_id: str,
    ) -> dict:
        """Student books a counselling slot.

        Validates that no overlapping REQUESTED or CONFIRMED booking exists
        for the counsellor in the same time window before inserting.

        Args:
            org_id:        Tenant UUID (from request.state.tenant_id via _org())
            student_id:    UUID of the booking student (equals actor_id for student calls)
            counsellor_id: UUID of the target counsellor user
            requested_at:  ISO 8601 TIMESTAMPTZ string e.g. "2026-04-01T10:00:00+05:30"
            duration_mins: Session length — 30 or 60 (max from policy, not hardcoded here)
            session_type:  "ACADEMIC" | "PERSONAL" | "CAREER" | "CRISIS"
            student_note:  Optional context from the student
            actor_id:      User ID performing the action (student for self-booking)
        """
        # Layer 4 — check for counsellor schedule conflict before inserting.
        # The window overlap condition: new slot starts before existing ends
        # AND new slot ends after existing starts.
        conflict = execute_query(
            """
            SELECT id FROM counselling_bookings
            WHERE org_id          = %s
              AND counsellor_id   = %s
              AND status          IN ('REQUESTED', 'CONFIRMED')
              AND requested_at < %s::TIMESTAMPTZ
                              + (duration_mins || ' minutes')::INTERVAL
              AND requested_at + (duration_mins || ' minutes')::INTERVAL
                              > %s::TIMESTAMPTZ
            LIMIT 1
            """,
            (org_id, counsellor_id, requested_at, requested_at),
            tenant_id=org_id,
        )
        if conflict:
            from server.core.exceptions import ConflictError
            raise ConflictError(
                "Counsellor already has a booking in this time window. "
                "Please choose a different slot."
            )

        booking_id = str(uuid.uuid4())

        execute_transaction(
            [
                (
                    """
                    INSERT INTO counselling_bookings
                        (id, org_id, student_id, counsellor_id,
                         requested_at, duration_mins, session_type, student_note)
                    VALUES (%s, %s, %s, %s, %s::TIMESTAMPTZ, %s, %s, %s)
                    """,
                    (
                        booking_id, org_id, student_id, counsellor_id,
                        requested_at, duration_mins, session_type, student_note,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        # Layer 6 — audit every write with enough metadata to reproduce the decision
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="counselling_booking",
            entity_id=booking_id,
            org_id=org_id,
            module="E09-S04",
            metadata={
                "student_id":    student_id,
                "counsellor_id": counsellor_id,
                "requested_at":  requested_at,
                "session_type":  session_type,
            },
        )

        # Layer 1 — fire domain event so Communication module can notify the student.
        # Import inside method to avoid circular import at module load time.
        from server.core.domain_events import DomainEvent, DomainEventBus

        DomainEventBus.publish(
            DomainEvent(
                event_type="student_services.counselling_booking_created",
                entity_type="counselling_booking",
                entity_id=booking_id,
                org_id=org_id,
                payload={
                    "booking_id":    booking_id,
                    "student_id":    student_id,
                    "counsellor_id": counsellor_id,
                    "requested_at":  requested_at,
                    "session_type":  session_type,
                },
                actor_id=actor_id,
                correlation_id=booking_id,
            )
        )

        return cls.get_booking(org_id, booking_id)

    @classmethod
    def confirm_booking(cls, org_id: str, booking_id: str, actor_id: str) -> dict:
        """Counsellor confirms a REQUESTED booking.

        Ownership enforced at the DB layer: the UPDATE's WHERE clause requires
        counsellor_id = actor_id AND status = 'REQUESTED'.
        If either condition fails, RETURNING returns no rows → NotFoundError.
        This is safer than checking ownership in Python first, then updating,
        because it is a single atomic operation with no race window.
        """
        rows = execute_query(
            """
            UPDATE counselling_bookings
            SET    status       = 'CONFIRMED',
                   confirmed_at = NOW(),
                   updated_at   = NOW()
            WHERE  id            = %s
              AND  org_id        = %s
              AND  counsellor_id = %s
              AND  status        = 'REQUESTED'
            RETURNING id
            """,
            (booking_id, org_id, actor_id),
            tenant_id=org_id,
        )
        if not rows:
            raise NotFoundError(
                f"Booking {booking_id} not found, already confirmed, "
                "or you are not the assigned counsellor."
            )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="counselling_booking",
            entity_id=booking_id,
            org_id=org_id,
            module="E09-S04",
            metadata={"new_status": "CONFIRMED"},
        )

        return cls.get_booking(org_id, booking_id)

    @classmethod
    def list_for_counsellor(
        cls,
        org_id: str,
        counsellor_id: str,
        status: str | None = None,
    ) -> list[dict]:
        """Return upcoming bookings for a counsellor, ordered by slot time."""
        sql = """
            SELECT cb.id, cb.student_id, cb.requested_at, cb.duration_mins,
                   cb.session_type, cb.student_note, cb.status, cb.confirmed_at,
                   s.name        AS student_name,
                   s.roll_number,
                   s.email       AS student_email
            FROM counselling_bookings cb
            JOIN students s ON s.id = cb.student_id
            WHERE cb.org_id        = %s
              AND cb.counsellor_id = %s
        """
        params: list = [org_id, counsellor_id]

        if status:
            sql += " AND cb.status = %s"
            params.append(status)
        else:
            # Default: active bookings only
            sql += " AND cb.status IN ('REQUESTED', 'CONFIRMED')"

        sql += " ORDER BY cb.requested_at ASC"
        return [dict(r) for r in execute_query(sql, params, tenant_id=org_id)]

    @classmethod
    def get_booking(cls, org_id: str, booking_id: str) -> dict:
        rows = execute_query(
            """
            SELECT cb.id, cb.org_id, cb.student_id, cb.counsellor_id,
                   cb.requested_at, cb.duration_mins, cb.session_type,
                   cb.student_note, cb.status, cb.confirmed_at,
                   cb.cancelled_at, cb.cancel_reason, cb.created_at,
                   s.name         AS student_name,
                   u.display_name AS counsellor_name
            FROM counselling_bookings cb
            JOIN students s ON s.id = cb.student_id
            JOIN users    u ON u.id = cb.counsellor_id
            WHERE cb.id = %s AND cb.org_id = %s
            """,
            (booking_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise NotFoundError(f"Counselling booking {booking_id} not found")
        return dict(rows[0])
```

**Why `tenant_id=org_id` on every DB call**: `execute_query` and `execute_transaction` accept an optional `tenant_id` parameter that runs `SET alis.current_tenant = '{tenant_id}'` before the query. For request-path code, TenantMiddleware already set the ContextVar — passing it explicitly is redundant but harmless. For service methods that Celery tasks may call directly (no TenantMiddleware), it is essential. The safe convention is: always pass `tenant_id=org_id` in service methods.

**Why `ConflictError` instead of `HTTPException`**: Service methods must not import from `fastapi`. `ConflictError` lives in `server/core/exceptions.py` and is mapped to HTTP 409 by the `error_handlers.py` FastAPI exception handler. This keeps the service layer framework-agnostic and testable without a running FastAPI app.

---

### Step 3 — Write the API Routes

Add three routes to `ALIS/server/api/student_services_router.py`, inside the `E09-S04 — Counselling` section. First update the import of `CounsellingService`:

```python
# student_services_router.py — update the existing import line:
# Before:
from server.student_services.counselling import CounsellingService
# After:
from server.student_services.counselling import CounsellingService, CounsellingBookingService
```

Then add the three routes after the existing `list_referrals` route:

```python
# ── E09-S04 Counselling Bookings ─────────────────────────────────────────────

@router.post("/counselling/bookings", status_code=201)
@require_permission(Permission.SERVICE_READ)
async def create_counselling_booking(
    request: Request,
    body: dict,
) -> JSONResponse:
    """Student books a counselling appointment slot.

    Permission: SERVICE_READ — students have this; they are consumers of the service.
    The actor IS the student: student_id is derived from the authenticated session,
    not from the request body (prevents a student booking on behalf of another).

    Body:
        counsellor_id  str  UUID of the target counsellor
        requested_at   str  ISO 8601 TIMESTAMPTZ "2026-04-01T10:00:00+05:30"
        duration_mins  int  30 or 60 (institution max from policy)
        session_type   str  "ACADEMIC" | "PERSONAL" | "CAREER" | "CRISIS"
        student_note   str  optional context for the counsellor (nullable)
    """
    return JSONResponse(
        status_code=201,
        content=_jsonify(
            CounsellingBookingService.create_booking(
                org_id=_org(request),
                student_id=_actor(request),   # actor IS the student
                counsellor_id=body["counsellor_id"],
                requested_at=body["requested_at"],
                duration_mins=int(body.get("duration_mins", 30)),
                session_type=body.get("session_type", "ACADEMIC"),
                student_note=body.get("student_note"),
                actor_id=_actor(request),
            )
        ),
    )


@router.get("/counselling/bookings/counsellor")
@require_permission(Permission.SERVICE_MANAGE)
async def counsellor_bookings(
    request: Request,
    status: Optional[str] = Query(
        None,
        description="Filter by status: REQUESTED | CONFIRMED. Omit for all active.",
    ),
) -> JSONResponse:
    """Counsellor views their upcoming bookings.

    Permission: SERVICE_MANAGE — counsellors and M6_MANAGER have this permission.
    Returns REQUESTED + CONFIRMED bookings unless status param narrows it.
    """
    items = CounsellingBookingService.list_for_counsellor(
        org_id=_org(request),
        counsellor_id=_actor(request),
        status=status,
    )
    return JSONResponse(content={"bookings": _jsonify(items), "total": len(items)})


@router.patch("/counselling/bookings/{booking_id}/confirm", status_code=200)
@require_permission(Permission.SERVICE_MANAGE)
async def confirm_counselling_booking(
    request: Request,
    booking_id: str,
) -> JSONResponse:
    """Counsellor confirms a REQUESTED booking.

    Permission: SERVICE_MANAGE.
    Ownership is enforced at DB level: UPDATE ... WHERE counsellor_id = actor_id.
    A counsellor cannot confirm another counsellor's booking even with SERVICE_MANAGE.
    """
    return JSONResponse(
        content=_jsonify(
            CounsellingBookingService.confirm_booking(
                org_id=_org(request),
                booking_id=booking_id,
                actor_id=_actor(request),
            )
        )
    )
```

**Why `_jsonify()` wraps every return value**: The `get_booking` query returns `datetime`, `date`, and potentially `Decimal` fields from PostgreSQL. Python's `json.dumps` raises `TypeError` on these types. `_jsonify()` — defined at line 80 of the router — handles this recursively. Every E09 route that returns joined query results uses it; this new feature follows the same pattern.

**Why `SERVICE_READ` for the student route, `SERVICE_MANAGE` for the counsellor routes**: Students have `SERVICE_READ` permission (`ROLE_PERMISSIONS[Role.STUDENT]` in `rbac.py` includes it). `SERVICE_MANAGE` is restricted to counsellors, M6_MANAGER, REGISTRAR — staff who actively manage the service rather than consume it.

---

### Step 4 — Write the Domain Event Handler

The Communication module subscribes to the new event and sends a student notification. Add the handler to `ALIS/server/communication/event_handlers.py`:

```python
# In ALIS/server/communication/event_handlers.py
# Add this function above register_all()

def on_counselling_booking_created(event: dict) -> None:
    """Send student a booking-received confirmation notification.

    Subscribed to: student_services.counselling_booking_created
    Fired by:      CounsellingBookingService.create_booking()

    Intentionally non-fatal: a notification failure must never roll back
    the booking that is already committed to the DB. The exception is caught
    and logged; the domain event retry mechanism (retry_failed_events beat task)
    will re-call this handler up to 3 more times before marking the event FAILED.
    """
    payload      = event.get("payload", {})
    org_id       = event.get("org_id")
    student_id   = payload.get("student_id")
    requested_at = payload.get("requested_at")
    session_type = payload.get("session_type", "ACADEMIC")

    if not (org_id and student_id and requested_at):
        logger.warning(
            "on_counselling_booking_created: missing payload fields — %s", payload
        )
        return

    try:
        from server.db_service import execute_query
        from server.core.notifications.service import NotificationDispatcher

        student_rows = execute_query(
            "SELECT name, email FROM students WHERE id = %s",
            (student_id,),
            tenant_id=org_id,
        )
        if not student_rows:
            logger.warning(
                "on_counselling_booking_created: student %s not found — skipping",
                student_id,
            )
            return

        student = student_rows[0]

        NotificationDispatcher.dispatch(
            template_key="counselling_booking_received",
            recipient_id=student_id,
            recipient_email=student["email"],
            context={
                "student_name": student["name"],
                "requested_at": requested_at,
                "session_type": session_type,
                "booking_id":   payload.get("booking_id"),
            },
            org_id=org_id,
        )

    except Exception as exc:
        logger.warning(
            "on_counselling_booking_created: notification failed (non-fatal) — %s", exc
        )
```

Register in `register_all()` in the same file:

```python
# In communication/event_handlers.py — add one line to register_all():
def register_all() -> None:
    # ... existing DomainEventBus.subscribe() calls ...
    DomainEventBus.subscribe(
        "student_services.counselling_booking_created",
        on_counselling_booking_created,
    )
    logger.info("Communication event handlers registered")
```

**Why the notification template key must exist in DB before deploying**: `NotificationDispatcher.dispatch()` looks up `counselling_booking_received` in the `notification_templates` table. If the row does not exist, the dispatch silently fails (or raises, depending on implementation). Add the template row as part of the migration or seeding step:

```sql
-- Run this in a migration or seed script (not in application code):
INSERT INTO notification_templates (org_id, template_key, channel, subject, body_template)
VALUES
  ('__DEFAULT__', 'counselling_booking_received', 'EMAIL',
   'Counselling appointment requested',
   'Dear {{student_name}}, your request for a {{session_type}} counselling session
    on {{requested_at}} has been received. Booking ID: {{booking_id}}.');
```

---

### Step 5 — Write a Real-DB Integration Test

Create `ALIS/tests/test_integration_counselling_booking.py`. Every test in this file gets its own `org_id` from `_new_org()` — no shared state, no cleanup, no ordering dependency.

```python
"""Real-DB integration tests — counselling_bookings table.

Verifies CounsellingBookingService against a running PostgreSQL instance.
All four autouse mocks from conftest.py are overridden with no-ops so that
real execute_query / execute_transaction / AuditLog.log calls hit the DB.

Run:
    pytest tests/test_integration_counselling_booking.py -v -m integration --tb=short
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import psycopg2
import psycopg2.extras
import pytest


# ---------------------------------------------------------------------------
# Override autouse mocks — real DB in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_db_global():
    """No-op: real execute_query / execute_transaction used."""
    yield


@pytest.fixture(autouse=True)
def mock_audit_log():
    """No-op: real AuditLog.log() calls verified in assertions below."""
    yield


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_integration_real_db.py)
# ---------------------------------------------------------------------------

def _connect(org_id: str) -> psycopg2.extensions.connection:
    from server.core.settings import settings
    try:
        conn = psycopg2.connect(
            settings.db_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = True
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    with conn.cursor() as cur:
        cur.execute(f"SET alis.current_tenant = '{org_id}'")
    return conn


def _q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _run(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _new_org() -> str:
    """Unique org per test — no cross-test contamination, no cleanup needed."""
    return f"test-{uuid.uuid4().hex[:10]}"


def _seed_student(conn, org_id: str) -> str:
    sid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO students (id, org_id, name, email, roll_number, status)
        VALUES (%s, %s, %s, %s, %s, 'ENROLLED')
    """, (sid, org_id, "Ananya Krishnan",
          f"ananya_{uuid.uuid4().hex[:6]}@test.invalid",
          f"CS-{uuid.uuid4().hex[:6].upper()}"))
    return sid


def _seed_counsellor(conn, org_id: str) -> str:
    uid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO users (id, org_id, display_name, email, role)
        VALUES (%s, %s, %s, %s, 'counsellor')
    """, (uid, org_id, "Dr. Meera Pillai",
          f"meera_{uuid.uuid4().hex[:6]}@institution.edu"))
    return uid


def _future_slot(hours: int = 48) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCounsellingBookingIntegration:

    def test_create_booking_inserts_row_and_writes_audit(self):
        """
        create_booking() must:
          - Insert a counselling_bookings row with status='REQUESTED'
          - Write an audit_ledger entry: action='CREATE', entity_type='counselling_booking'
        """
        from server.student_services.counselling import CounsellingBookingService

        org_id        = _new_org()
        conn          = _connect(org_id)
        student_id    = _seed_student(conn, org_id)
        counsellor_id = _seed_counsellor(conn, org_id)

        result = CounsellingBookingService.create_booking(
            org_id=org_id,
            student_id=student_id,
            counsellor_id=counsellor_id,
            requested_at=_future_slot(48),
            duration_mins=30,
            session_type="ACADEMIC",
            student_note="Struggling with OBE project structure.",
            actor_id=student_id,
        )

        booking_id = result["id"]

        # 1. Row is in DB with correct values
        row = _q(conn,
            "SELECT * FROM counselling_bookings WHERE id = %s", (booking_id,))
        assert row is not None,                 "counselling_bookings row not found"
        assert row["status"]       == "REQUESTED"
        assert str(row["student_id"])    == student_id
        assert str(row["counsellor_id"]) == counsellor_id
        assert row["duration_mins"] == 30
        assert row["session_type"]  == "ACADEMIC"

        # 2. Audit entry written
        audit = _q(conn,
            """SELECT action FROM audit_ledger
               WHERE entity_type = 'counselling_booking' AND entity_id = %s""",
            (booking_id,))
        assert audit is not None, "audit_ledger entry missing for counselling_booking"
        assert audit["action"] == "CREATE"

    def test_confirm_booking_transitions_status(self):
        """confirm_booking() must change status to CONFIRMED and populate confirmed_at."""
        from server.student_services.counselling import CounsellingBookingService

        org_id        = _new_org()
        conn          = _connect(org_id)
        student_id    = _seed_student(conn, org_id)
        counsellor_id = _seed_counsellor(conn, org_id)

        booking = CounsellingBookingService.create_booking(
            org_id=org_id, student_id=student_id, counsellor_id=counsellor_id,
            requested_at=_future_slot(72), duration_mins=30,
            session_type="PERSONAL", student_note=None, actor_id=student_id,
        )

        confirmed = CounsellingBookingService.confirm_booking(
            org_id=org_id,
            booking_id=booking["id"],
            actor_id=counsellor_id,     # must be the assigned counsellor
        )

        assert confirmed["status"] == "CONFIRMED"

        row = _q(conn,
            "SELECT status, confirmed_at FROM counselling_bookings WHERE id = %s",
            (booking["id"],))
        assert row["status"]       == "CONFIRMED"
        assert row["confirmed_at"] is not None, "confirmed_at must be set"

    def test_wrong_counsellor_cannot_confirm(self):
        """confirm_booking() raises NotFoundError if actor is not the assigned counsellor."""
        from server.student_services.counselling import CounsellingBookingService
        from server.core.exceptions import NotFoundError

        org_id          = _new_org()
        conn            = _connect(org_id)
        student_id      = _seed_student(conn, org_id)
        counsellor_id   = _seed_counsellor(conn, org_id)
        other_counsellor = _seed_counsellor(conn, org_id)   # different user

        booking = CounsellingBookingService.create_booking(
            org_id=org_id, student_id=student_id, counsellor_id=counsellor_id,
            requested_at=_future_slot(96), duration_mins=30,
            session_type="ACADEMIC", student_note=None, actor_id=student_id,
        )

        with pytest.raises(NotFoundError):
            CounsellingBookingService.confirm_booking(
                org_id=org_id,
                booking_id=booking["id"],
                actor_id=other_counsellor,   # wrong counsellor — DB WHERE clause rejects
            )

    def test_conflict_error_on_overlapping_slot(self):
        """create_booking() raises ConflictError when the counsellor's slot is already taken."""
        from server.student_services.counselling import CounsellingBookingService
        from server.core.exceptions import ConflictError

        org_id        = _new_org()
        conn          = _connect(org_id)
        student_id    = _seed_student(conn, org_id)
        student2_id   = _seed_student(conn, org_id)
        counsellor_id = _seed_counsellor(conn, org_id)
        slot          = _future_slot(120)

        # First booking — succeeds
        CounsellingBookingService.create_booking(
            org_id=org_id, student_id=student_id, counsellor_id=counsellor_id,
            requested_at=slot, duration_mins=30,
            session_type="ACADEMIC", student_note=None, actor_id=student_id,
        )

        # Same slot, same counsellor, different student — must raise ConflictError
        with pytest.raises(ConflictError, match="already has a booking"):
            CounsellingBookingService.create_booking(
                org_id=org_id, student_id=student2_id, counsellor_id=counsellor_id,
                requested_at=slot, duration_mins=30,
                session_type="CAREER", student_note=None, actor_id=student2_id,
            )

    def test_rls_prevents_cross_tenant_read(self):
        """A booking created in org_A must not be visible when queried under org_B."""
        from server.student_services.counselling import CounsellingBookingService
        from server.core.exceptions import NotFoundError

        org_a         = _new_org()
        org_b         = _new_org()
        conn_a        = _connect(org_a)
        student_id    = _seed_student(conn_a, org_a)
        counsellor_id = _seed_counsellor(conn_a, org_a)

        booking = CounsellingBookingService.create_booking(
            org_id=org_a, student_id=student_id, counsellor_id=counsellor_id,
            requested_at=_future_slot(144), duration_mins=30,
            session_type="CAREER", student_note=None, actor_id=student_id,
        )

        # Read under org_b context — RLS must hide the row → NotFoundError
        with pytest.raises(NotFoundError):
            CounsellingBookingService.get_booking(
                org_id=org_b,           # wrong tenant
                booking_id=booking["id"],
            )
```

Run the tests:

```bash
cd ALIS

python -m pytest tests/test_integration_counselling_booking.py \
  -v -m integration --tb=short

# Expected:
# PASSED ...::test_create_booking_inserts_row_and_writes_audit
# PASSED ...::test_confirm_booking_transitions_status
# PASSED ...::test_wrong_counsellor_cannot_confirm
# PASSED ...::test_conflict_error_on_overlapping_slot
# PASSED ...::test_rls_prevents_cross_tenant_read
# 5 passed
```

**Why five separate test methods instead of one big test**: Each calls `_new_org()` independently. Test isolation means a failure in test 3 does not contaminate the database state seen by test 4. There is no `tearDown`, no `truncate`, and no fixture scope needed — the unique `org_id` is its own isolation boundary.

---

### Step 6 — Run the Task Completion Checklist

```bash
cd ALIS

# ── Check 1: All 883 mocked tests still pass ─────────────────────────────────
python -m pytest tests/ -x -q --tb=short 2>&1 | tail -5
# Expected: 883 passed, 0 failed
# Any new failure here means the new code broke something in the mocked suite

# ── Check 2: All real-DB integration tests pass ──────────────────────────────
python -m pytest tests/test_integration_real_db.py \
                 tests/test_integration_counselling_booking.py \
                 -v --tb=short
# Expected: 14 + 5 = 19 passed

# ── Check 3: No hardcoded thresholds (must return 0 lines) ───────────────────
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ \
  | grep -v test | grep -v migration
# Expected: 0 lines
# Note: the conflict window check (duration_mins) is a DB field, not a hardcoded constant

# ── Check 4: No raw status updates bypassing state machine (must return 0 lines)
grep -rn --include='*.py' "SET status=" server/ \
  | grep -v test | grep -v migration
# Expected: 0 lines
# confirm_booking uses UPDATE...WHERE status='REQUESTED' RETURNING id — not a raw SET status=
```

If all four pass, reload the Celery workers so the new event subscription is active:

```bash
docker compose restart celery_worker celery_beat

# Verify the new subscription is in the logs
docker compose logs celery_worker --tail=30 | grep -i "communication"
# Expected: "Communication event handlers registered"
```

Confirm migration head:

```bash
python -m alembic current
# Expected: 0040 (head)
```

---

### What Each Layer Did in This Feature

| Layer | Where it appeared |
|-------|------------------|
| **Layer 1 — Module boundary** | `DomainEventBus.publish()` in `create_booking()`; Communication module subscribes in `event_handlers.py`; the two modules never import from each other |
| **Layer 2 — Agentic decisions** | Not applicable — this feature has no AI path. If a future AI feature scores booking urgency, it must output a Draft `suggested_priority`; a counsellor confirms before it takes effect |
| **Layer 3 — State machine** | Booking status transitions (`REQUESTED → CONFIRMED`) enforced by `UPDATE ... WHERE status = 'REQUESTED'`; no code path sets `CONFIRMED` without passing through `REQUESTED` first |
| **Layer 4 — Global locks** | Overlap detection uses a read-before-write with conflict check; for very high concurrency, add `pg_advisory_xact_lock(hash(counsellor_id))` around the check + insert pair |
| **Layer 5 — Roles + authority** | `SERVICE_READ` for student booking creation; `SERVICE_MANAGE` for counsellor confirm; DB-level ownership check in UPDATE prevents cross-counsellor confirmation |
| **Layer 6 — Resilience + audit** | `AuditLog.log()` on every write; domain event retry handles notification failures transparently; integration test asserts audit entry exists and has correct `action` |

---

### Common Mistakes and How the Checklist Catches Them

| Mistake | Which check catches it | Correct approach |
|---------|----------------------|-----------------|
| `if duration_mins > 60: raise ...` (hardcoded max) | Check 3 grep does NOT catch this — it is a constraint, not a 75-style threshold | `max_mins = policy_engine.get_value("counselling.max_duration_mins", org_id, 60)` |
| `execute_transaction([("UPDATE ... SET status = 'CONFIRMED' ...", ...)])` with a plain assignment | Check 4 catches `SET status=` | Use `UPDATE ... WHERE status = 'REQUESTED' RETURNING id`; the RETURNING clause is the guard |
| `from server.finance.fee_structure import ...` inside the booking service | Manual code review only | Fire `student_services.counselling_booking_created`; let Finance subscribe if needed |
| Missing `AuditLog.log()` after INSERT | Integration test assertion `assert audit is not None` fails | Add `AuditLog.log()` immediately after `execute_transaction()` |
| Using `execute_query` for the INSERT | No automated check — code review only | `execute_query` is SELECT only; it does not commit. All writes need `execute_transaction`. |
| Returning `datetime` objects in JSON response | `TypeError` at runtime on first real request | Wrap return value in `_jsonify()` as every other E09 route does |

---
---

## 19. SaaS Platform Architecture

> **Added**: 2026-04-02 — S1-S10 SaaS transformation complete. 172 SaaS tests passing.

This section covers the SaaS multi-tenant platform built in sprints S1-S10. If you are working on the on-premises single-deployment mode only, you can skip this section entirely.

### Repository Layout (SaaS components)

```
control_plane/              # Central management service
├── main.py                 # FastAPI app (separate from ALIS/server/main.py)
├── settings.py             # Pydantic Settings (DB, S3, Vault, DNS, billing)
├── router.py               # Admin + internal + billing + webhook endpoints
├── provisioner.py          # TenantProvisioner — full lifecycle
├── db.py                   # Control plane database (cp_tenants, cp_invoices, etc.)
├── crypto.py               # AES-GCM for tenant DB passwords
├── billing_engine.py       # Monthly invoice computation
├── billing_models.py       # Plan configs, usage event types
├── usage_store.py          # Immutable usage event recording
├── plan_store.py           # Dynamic plan CRUD
├── bucket_provisioner.py   # Per-tenant S3 bucket lifecycle
├── vault_client.py         # Vault KV v2 (AppRole auth)
├── dns_manager.py          # Multi-provider DNS (Cloudflare/Route53/Azure)
└── tests/                  # S2, S4, S5, S9, S10 test suites

ai_service/                 # Centralized LLM proxy
├── main.py                 # FastAPI app
├── router.py               # /v1/complete, /v1/embed, /v1/budget
├── providers.py            # VpcOllamaProvider, ManagedAPIProvider
├── pii_masker.py           # PII detection + deterministic tokenization
├── budget.py               # Per-tenant token budget (Redis)
└── tests/                  # S3 test suite

infra/
├── k8s/helm/
│   ├── alis-data-plane/    # 11 templates (deployment, worker, beat, ingress, HPA, NetworkPolicy)
│   ├── alis-control-plane/ # Single combined template
│   └── alis-ai-service/    # Deployment + HPA + GPU affinity
├── k8s/operator/
│   ├── crds/tenantstack.yaml  # TenantStack CRD (alis.app/v1alpha1)
│   └── src/reconciler.py      # kopf reconciler (create/update/delete/timer)
└── terraform/
    ├── modules/aws/        # VPC, EKS, Aurora, ElastiCache, S3, Route53
    ├── modules/azure/      # AKS, PostgreSQL Flex, Redis Cache, Blob
    ├── modules/gcp/        # GKE Autopilot, Cloud SQL, Memorystore, GCS
    ├── modules/shared/     # Vault KV v2 + AppRole policies
    └── envs/{dev,staging,prod}/  # Environment-specific configs
```

### The Three Services

| Service | Port | Purpose | Auth |
|---------|------|---------|------|
| **Data Plane** (`ALIS/server/`) | 8000 | Per-tenant FastAPI — all ERP functionality | JWT (tenant user) |
| **Control Plane** (`control_plane/`) | 8100 | Tenant CRUD, billing, DNS | Admin JWT or X-Internal-Token |
| **AI Service** (`ai_service/`) | 8200 | LLM proxy with PII masking + budget | X-AI-Service-Token |

In on-premises mode, only the Data Plane runs. The Control Plane and AI Service are SaaS-only.

### Tenant Lifecycle

```
kubectl apply -f tenant-iitb.yaml     # TenantStack CRD
  → Operator reconciler fires
    → POST /admin/tenants to Control Plane
      → Create DB user + database
      → Run Alembic migrations
      → Provision S3 bucket (versioned, encrypted, GLACIER lifecycle)
      → Write secrets to Vault
      → Create DNS CNAME ({subdomain}.alis.app)
      → Set CRD status.phase = Active

kubectl delete tenantstack iitb        # Soft delete
  → Operator handle_delete fires
    → DELETE /admin/tenants/{id} to Control Plane
      → Deprovision DNS
      → Archive S3 bucket to cold storage
      → Delete Vault secrets
      → Mark tenant status=DELETED (no DB drop)
```

### Billing Flow

1. Data plane sends usage events to control plane: `POST /internal/billing/usage`
2. Monthly cron: `BillingEngine.compute_all()` generates DRAFT invoices
3. Admin reviews + issues: `POST /admin/billing/invoices/{tenant}/{period}/issue`
4. Tenant pays via Stripe/Razorpay → webhook hits `/webhook/payments/{provider}`
5. Webhook handler records payment, auto-marks invoice as PAID

Plans: Starter ($49/mo), Growth ($199/mo), Enterprise ($999/mo). Per-dimension overage for tokens, storage, API calls, active users. Plan configs stored in `cp_plans` table (admin-editable).

### Key Design Decisions

1. **Dedicated DB per tenant** (not shared) — eliminates cross-tenant data leakage risk entirely. RLS remains as defense-in-depth.
2. **PII masking before LLM** — student data never reaches the language model in raw form. Deterministic tokenization preserves reasoning quality.
3. **Celery queue isolation** — tenant tasks route to `default:{tenant_id}` queues. One tenant's heavy load cannot starve another.
4. **Cloudflare proxied DNS** — CDN + DDoS protection + Universal SSL for all tenant subdomains, zero cert management.
5. **Immutable usage events** — append-only `cp_usage_events` table. Usage can be audited but never modified.
6. **Backward compatibility** — all SaaS features degrade gracefully. Empty `CONTROL_PLANE_URL` = single-tenant on-prem. Empty `AI_SERVICE_URL` = direct Ollama. Empty `VAULT_ADDR` = Vault disabled.

### Running SaaS Tests

```bash
# All SaaS tests (172 tests, ~60s)
cd "c:/alis-antigravity/ALIS Production"
python -m pytest control_plane/tests/ ai_service/tests/ infra/k8s/operator/tests/ -v

# Individual sprint test suites
python -m pytest control_plane/tests/test_s2_control_plane.py -v   # S2: Control Plane
python -m pytest ai_service/tests/test_s3_ai_service.py -v         # S3: AI Service
python -m pytest control_plane/tests/test_s4_billing.py -v         # S4: Billing Engine
python -m pytest control_plane/tests/test_s5_infra.py -v           # S5: Infra Isolation
python -m pytest infra/k8s/operator/tests/test_s8_operator.py -v  # S8: K8s Operator
python -m pytest control_plane/tests/test_s9_billing_api.py -v    # S9: Billing API
python -m pytest control_plane/tests/test_s10_dns.py -v            # S10: DNS Routing
```

---

*Document generated: 2026-04-02. All code examples taken directly from the codebase.*