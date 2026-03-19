# ALIS OS — Claude Code Reference
> **Autonomous Institutional Operating System** | QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India
> 
> This document is the single source of truth for Claude Code when working on the ALIS codebase.
> Read this file before writing any code, making any architectural decision, or modifying any module.

---

## Table of Contents

1. [What ALIS Is](#1-what-alis-is)
2. [Core Philosophy — Non-Negotiable](#2-core-philosophy--non-negotiable)
3. [Current Tech Stack](#3-current-tech-stack)
4. [Architecture — 6-Layer Model](#4-architecture--6-layer-model)
5. [Module Map](#5-module-map)
6. [Database Conventions](#6-database-conventions)
7. [RBAC & Security Model](#7-rbac--security-model)
8. [Event-Driven Design](#8-event-driven-design)
9. [AI & LLM Layer](#9-ai--llm-layer)
10. [Policy Engine — Rules-as-Data](#10-policy-engine--rules-as-data)
11. [Workflow Engine — Workflows-as-Data](#11-workflow-engine--workflows-as-data)
12. [Feature Flags — Institutional Granularity](#12-feature-flags--institutional-granularity)
13. [Plugin System](#13-plugin-system)
14. [Known Issues — Fix Before Anything Else](#14-known-issues--fix-before-anything-else)
15. [Cross-Module Event Contract](#15-cross-module-event-contract)
16. [Critical DO NOTs](#16-critical-do-nots)
17. [File Structure](#17-file-structure)
18. [API Conventions](#18-api-conventions)
19. [Testing Standards](#19-testing-standards)
20. [Build Sequence](#20-build-sequence)

---

## 1. What ALIS Is

ALIS is an **Autonomous Institutional Operating System** for universities. It is not an ERP. It is not a CRM. It is a platform that runs many configurations of one product — one codebase serving many institutions, each with different rules, workflows, roles, and policies.

**Scope:** Complete university lifecycle from prospect lead → student enrollment → academics → examinations → graduation → alumni.

**Deployment model:** On-premises or private cloud. No hard dependencies on AWS/GCP managed services. Every service must run on Docker Compose or K3s on institution hardware.

**Commercial model:** Hardware sale + annual software license per institution (tenant).

**Regulatory context:** India-first. DPDP Act 2023 compliance mandatory. UGC, AICTE, NAAC, NIRF, NBA, AISHE frameworks built in. GST/TDS/PF/ESI statutory compliance in Finance module.

---

## 2. Core Philosophy — Non-Negotiable

These principles govern every line of code written for ALIS. Do not deviate.

### AI Proposes. Rules Enforce. Humans Only Approve or Reject.

```
AI generates / computes / drafts
        │
        ▼
Rules engine validates against policy
        │
        ▼
Delivered to Actor's approval queue (if required)
        │
        ├── Actor approves  ──► Executed + audit logged
        ├── Actor edits     ──► AI updates, re-queued
        └── Actor rejects   ──► AI re-generates with reason
```

The LLM **never** makes a final decision. The rules engine enforces policy. Humans exercise judgment at defined gates only.

If an Actor does not act within the SLA window:
- **Low-stakes** (attendance reports, reminders): auto-approved
- **High-stakes** (grade cards, enrollment, financial transactions): escalated to next role up

No task is ever blocked indefinitely waiting for a human.

### Configuration is Data, Not Code

Every institution-specific value — attendance thresholds, approval chains, role names, fee rules, progression criteria — **must be stored in the database and read at runtime**. Never hardcode tenant-specific logic.

```python
# WRONG — never do this
if tenant_id == "woxsen":
    threshold = 0.75
else:
    threshold = 0.80

# RIGHT — always do this
threshold = policy_engine.get_value("attendance.minimum_threshold", tenant_id)
```

### Events Over Direct Calls

Modules **never call each other directly**. All cross-module communication goes through the Domain Event Bus. A module publishes an event. Other modules subscribe and react.

```python
# WRONG — direct module coupling
academic_service.initialize_student(student_id)  # from admissions code

# RIGHT — event-driven
await domain_event_bus.publish(DomainEvent(
    event_type="student.enrolled",
    tenant_id=tenant_id,
    payload={"student_id": student_id, "program": program, ...}
))
# Academic module's handler picks this up independently
```

### Immutable Audit Trail

Every state change, every AI decision, every approval, every policy evaluation **must** be written to the audit ledger. No exceptions. The ledger uses a hash chain — each entry stores `SHA256(previous_hash + event_payload)`.

---

## 3. Current Tech Stack

### Backend

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Web Framework | FastAPI | 0.115.0 |
| ASGI Server | Uvicorn | 0.30.6 |
| Data Validation | Pydantic v2 | 2.8.2 |
| Task Queue | Celery | 5.4.0 |
| Message Broker | Redis | 7-alpine |
| Scheduler | Celery Beat | — |

### Database

| Component | Technology | Notes |
|---|---|---|
| Primary DB | PostgreSQL 16 + pgvector | Schema-per-tenant isolation |
| DB Driver | **Must migrate to asyncpg** | See Known Issues §14 |
| Migrations | Alembic | 0001–0014 deployed |
| Vector Store | pgvector (768-dim) | RAG / semantic search |
| Cache | Redis | Sessions, feature flags, policy cache |
| Object Store | MinIO | S3-compatible, on-prem |

### AI Stack

| Component | Technology | Notes |
|---|---|---|
| Primary LLM | Ollama — `qwen2.5:1.5b` | Small tasks only — see §9 |
| Embeddings | `nomic-embed-text` | 768-dim, via Ollama |
| Agent Framework | LangGraph 1.1.2 | Domain agent orchestration |
| External fallback | NVIDIA NIM / OpenAI | Configurable per tenant |
| Secret Vault | **HashiCorp Vault — not yet installed** | Required for question paper vault |

### Infrastructure

| Service | Image | Port | Purpose |
|---|---|---|---|
| PostgreSQL | pgvector/pgvector:pg16 | 5432 | Primary DB |
| Redis | redis:7-alpine | 6379 | Broker, cache, sessions |
| Ollama | ollama/ollama | 11434 | Local LLM inference |
| MinIO | minio/minio | 9000/9001 | Object storage |
| ALIS API | python:3.11-slim | 8000 | FastAPI app |
| Celery Worker | same image | — | Async tasks |
| Celery Beat | same image | — | Scheduled tasks |
| Nginx | nginx:alpine | 80/443 | Reverse proxy, rate limiting |

### Frontend

| Component | Technology | Version |
|---|---|---|
| Language | TypeScript | 5.7.2 |
| UI Library | React | 19.0.0 |
| State | Zustand + TanStack React Query | 5.x |
| Styling | Tailwind CSS 4 + Radix UI | — |
| Bundler | Vite | 6.0.5 |

---

## 4. Architecture — 6-Layer Model

Applied uniformly across all 13+ epics:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Module Purpose (Domain Business Logic)            │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 — Agentic Decisions (LLM Agent Proposals)           │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 — State Machines (Entity Lifecycle Transitions)     │
├─────────────────────────────────────────────────────────────┤
│  Layer 4 — Global Locks (Race Condition Prevention)          │
├─────────────────────────────────────────────────────────────┤
│  Layer 5 — Roles / Quorum (RBAC + Approval Workflows)        │
├─────────────────────────────────────────────────────────────┤
│  Layer 6 — Resilience (SLA enforcement, Escalation)          │
└─────────────────────────────────────────────────────────────┘
                  ↕  AuditLedger (cross-cutting, all layers)
```

**Key invariants:**
- LLM agents produce `DRAFT` state only. Orchestrators validate against the rules engine before executing any state transition.
- Every DB query is scoped by `SET LOCAL alis.current_tenant = '{tenant_id}'` — enforced by `TenantMiddleware`.
- All money amounts stored as `DECIMAL(12,2)` in DB, returned as strings in JSON.
- All IDs are UUID v4 strings — never integers.

---

## 5. Module Map

| Epic | Module | Status | Key Tables |
|---|---|---|---|
| E01 | Auth + Users + RBAC | ✅ Complete | users, roles, role_assignments, permissions |
| E02 | Workflow Engine + Approvals | ✅ Complete | workflow_definitions, workflow_steps, approval_tasks |
| E03 | AI Gateway + Guardrails + HITL | ✅ Complete | ai_invocations, guardrail_logs |
| E04 | Admissions (10 stages) | ✅ Complete | 40+ tables, 87 API routes |
| E05 | Academics (10 modules) | ✅ Complete | courses, timetables, attendance, mentorship |
| E06 | Examinations (12 stages) | ✅ Complete | hall_tickets, answer_scripts, results, revaluation |
| E07 | Finance (7 domains) | ✅ Complete | fee_ledger, invoices, scholarships, payroll |
| E08 | HR & Payroll (6 domains) | ✅ Complete | employees, leave, appraisals, payroll_runs |
| E09 | Student Services (8 domains) | ✅ Complete | hostel, library, placement, grievances |
| E10 | Communication Hub | ✅ Complete | notification_templates, delivery_log |
| E11 | Reporting & Analytics | ✅ Complete | kpi_snapshots, audit_reports |
| E12 | Alumni & Placement | ✅ Complete | alumni_profiles, engagement_events |
| E13 | Dynamic Process Engine | ✅ Complete | workflow_definitions (runtime DAG) |
| **E14** | **Regulatory & Accreditation** | ❌ Not built | regulatory_metrics, naac_evidence, nirf_data |
| **E15** | **PhD / Doctoral Research** | ❌ Not built | phd_scholars, dc_meetings, thesis_submissions |
| **E16** | **Parent / Guardian Portal** | ❌ Not built | guardian_accounts, guardian_student_links |
| **E17** | **Re-admission & Credit Transfer** | ❌ Not built | readmission_applications, credit_transfer_records |
| **E18** | **Convocation Management** | ❌ Not built | convocation_cycles, degree_award_records |
| **E19** | **Quota Seat Matrix Engine** | ❌ Not built | seat_matrix, quota_allocations, waitlist_positions |
| **E20** | **OBE / CO-PO Mapping** | ❌ Not built | course_outcomes, program_outcomes, co_po_mappings |
| **E21** | **DPDP Consent Management** | ❌ Not built | consent_records, data_subjects, erasure_requests |
| **PAA** | **Policy Authoring Agent** | ❌ Not built | See §10b |

**Build order:** E14 → E21 → E16 → E19 → E15 → E17 → E18 → E20 → PAA
Full implementation specs for E15–E21 are in `references/gaps.md`.
For go-live blockers (§21–§28) and platform gaps (§29–§32) see below.

### Admissions Pipeline (E04) — 10 Stages
```
Stage 1  → Lead CRM
Stage 2  → Application Form (APP-YEAR-XXXXXX ID)
Stage 3  → Document Collection & Verification
Stage 4  → Eligibility Screening (rules engine — not LLM)
Stage 5  → Entrance Test / Interview
Stage 6  → Merit List & Selection
Stage 7  → Offer Letter Issuance
Stage 8  → Fee Payment & Seat Confirmation
Stage 9  → Final Document Verification
Stage 10 → Enrollment & Roll Number Assignment
```

### Examination Pipeline (E06) — 12 Stages
```
Stage 1  → Exam Registration & Eligibility
Stage 2  → Exam Schedule Generation
Stage 3  → Question Paper Management (AES-256 encrypted, Vault-gated)
Stage 4  → Hall Ticket Generation
Stage 5  → Seating & Invigilation Arrangement
Stage 6  → Exam Conduct & Attendance
Stage 7  → Answer Script Management
Stage 8  → Evaluation & Marks Entry
Stage 9  → Result Computation & Publication
Stage 10 → Revaluation & Rechecking
Stage 11 → Supplementary / Re-appear Examination
Stage 12 → Transcript & Score Card Generation
```

---

## 6. Database Conventions

### Always Follow

| Convention | Rule |
|---|---|
| IDs | UUID v4 strings everywhere. Never integer PKs. |
| Timestamps | `TIMESTAMPTZ` in DB. ISO 8601 UTC in API responses. |
| Money | `DECIMAL(12,2)` in DB. String in JSON (`"15000.00"`). |
| Currency | INR default. |
| Soft deletes | `status='ARCHIVED'` (lifecycle entities). `status='ANNULLED'` (state machine entities). Never physical row deletion. |
| Tenant scoping | `SET LOCAL alis.current_tenant = '{tenant_id}'` on every connection — enforced by TenantMiddleware. |
| Migrations | Alembic only. Never raw SQL in production. |
| Indexes | Always index on `(tenant_id, <query_field>)` composite — never on `<query_field>` alone. |

### Query Helpers (use exclusively — no raw psycopg2)

```python
execute_query(sql, params)            # SELECT only — no commit
execute_transaction([(sql, params)])  # INSERT/UPDATE/DELETE — commits atomically
```

### Multi-Tenancy — Schema-per-Tenant

Each institution gets its own PostgreSQL schema: `tenant_woxsen.*`, `tenant_gitam.*`, etc.

This gives hard data isolation, easy per-tenant backup/restore, and DPDP Act compliance. Never mix tenant data in a shared table.

### State Machine Enforcement

Every entity with a lifecycle (application, student, exam, invoice) has an explicit status column. **Never** update status with a raw `UPDATE` — always go through the state machine class which enforces valid transitions and rejects illegal jumps.

```python
# WRONG
await execute_transaction([("UPDATE applications SET status='Enrolled' WHERE id=$1", [app_id])])

# RIGHT
await application_state_machine.transition(app_id, "Enrolled", actor_id=registrar_id)
# State machine checks: is this transition valid from current state?
# If yes: updates + writes audit log entry
# If no: raises InvalidTransitionError
```

---

## 7. RBAC & Security Model

### Core Principle

Permissions are **never** assigned directly to users. Always via roles. Role assignments carry three mandatory dimensions:

```
role_assignment = {
    principal_id:  UUID,          # user or service account
    role_id:       UUID,          # role definition
    scope_id:      UUID | None,   # department / batch / course / global
    valid_from:    TIMESTAMPTZ,
    valid_until:   TIMESTAMPTZ | None,   # null = permanent
    delegated_by:  UUID | None,   # for delegation chains
}
```

### System Roles (pre-seeded, cannot be deleted)

```
super_admin → registrar → exam_controller → hod → faculty → student → alumni
                       └→ finance_officer
                       └→ hostel_warden (scoped to block)
                       └→ placement_officer
                       └→ librarian
```

Role hierarchy: parent inherits all child permissions automatically.

### Permission Check Pattern

```python
# Every route handler — no exceptions
async def get_attendance(req: Request, course_id: str):
    if not await req.can("attendance", "read", scope_ref=course_id):
        raise HTTPException(403, "Forbidden")
    # proceed
```

**Never** use role names in business logic:
```python
# WRONG — brittle, breaks on role rename
if user.role == "hod":
    ...

# RIGHT — stable
if await req.can("timetable", "approve", scope_ref=department_id):
    ...
```

### JWT

- Algorithm: HS256 (migrate to RS256 when scaling beyond single server)
- Access token TTL: 60 minutes
- Refresh token TTL: 7 days
- Redis-backed session manager — stateless tokens are not enough; sessions are revocable

### Security Headers (enforced by SecurityHeadersMiddleware)

`X-Frame-Options: DENY` | `X-Content-Type-Options: nosniff` | `Referrer-Policy: strict-origin` | `Permissions-Policy: geolocation=()`

---

## 8. Event-Driven Design

### Domain Event Bus

All cross-module communication uses domain events. Modules never import from each other.

```python
# Publishing an event
await domain_event_bus.publish(DomainEvent(
    event_type="student.enrolled",
    tenant_id=tenant_id,
    aggregate_id=student_id,
    payload={
        "student_id": student_id,
        "roll_number": roll_number,
        "program": program,
        "batch": batch,
        "hostel_opted": hostel_opted,
        # Risk baseline fields — required for Academics module
        "entrance_score": entrance_score,
        "twelfth_percentage": twelfth_percentage,
        "is_first_gen": is_first_gen,
        "category": category,
    }
))
```

### Durability Guarantee

Events are persisted to `domain_events` table **before** dispatch. If worker crashes, Celery Beat retries every 5 minutes. Failed events after 3 retries are marked `FAILED` for manual inspection.

For financial and examination events specifically, the Beat retry interval must be ≤ 30 seconds (not 5 minutes). Configure separate Beat schedules for these topic classes.

### Multi-Condition Event Aggregation

Some state transitions require multiple events to all be true before proceeding. This is a **saga pattern** — use a Temporal workflow, not ad-hoc Celery logic.

Example: Alumni transition requires `result.final_published` AND `dues_cleared` AND `graduation.verified`.

```python
@workflow.defn
class AlumniTransitionSaga:
    @workflow.run
    async def run(self, student_id: str, tenant_id: str):
        # Wait for all three conditions — with timeout
        results_done = False
        dues_cleared = False
        graduation_verified = False
        
        while not (results_done and dues_cleared and graduation_verified):
            signal = await workflow.wait_for_signal("condition_met", timeout=timedelta(days=90))
            if signal.type == "result.final_published":
                results_done = True
            elif signal.type == "student.dues_cleared":
                dues_cleared = True
            elif signal.type == "graduation.verified":
                graduation_verified = True
        
        await workflow.execute_activity(transition_to_alumni, args=[student_id, tenant_id])
```

### Complete Cross-Module Event Registry

| Event | Publisher | Subscribers |
|---|---|---|
| `student.enrolled` | Admissions | Academics, Finance, Student Services (Hostel, Library), HR (if faculty) |
| `student.cancelled` | Admissions | Finance (refund trigger), Student Services |
| `student.dues_cleared` | Finance | Examinations (hall ticket gate) |
| `fee.paid` | Finance | Admissions (seat confirmation) |
| `scholarship.awarded` | Student Services | Finance (ledger credit) |
| `scholarship.disbursed` | Finance | Student Services (renewal tracking) |
| `exam.eligibility_confirmed` | Examinations | — (triggers hall ticket generation internally) |
| `exam.malpractice_flagged` | Examinations | Student Services SS-5 (disciplinary pipeline) |
| `exam.backlog_cleared` | Examinations | Student Services SS-3 (placement re-evaluation) |
| `result.published` | Examinations | Student Services, Academics (progression), Alumni |
| `result.final_published` | Examinations | Alumni transition saga |
| `hostel.checkin` | Student Services | Finance (hostel fee component) |
| `hostel.cleared` | Student Services | Finance (security deposit refund), Examinations |
| `library.cleared` | Student Services | Examinations (hall ticket), Graduation |
| `employee.joined` | HR | Finance (payroll creation), Academics (faculty timetable) |
| `employee.promoted` | HR | Finance (pay scale update) |
| `payroll.inputs_ready` | HR | Finance FM-5 (payroll computation) |
| `hr.payroll_input_amended` | HR | Finance FM-5 (recomputation trigger) |
| `budget.approved` | Finance | HR (vacancy sanction gate) |
| `academic_calendar.updated` | Academics | Student Services (hostel blackout cache invalidation) |
| `academics.faculty_activity_summary` | Academics | HR (CAS appraisal Category I data) |
| `grievance.closed` | Student Services | Regulatory E14 (NAAC metric update) |
| `offer.received` | Student Services | Regulatory E14 (placement stats) |

**E14 Regulatory subscribes to all of the above** — plus the following additional events for accreditation metrics:

| Event | Source | Regulatory Metric Updated |
|---|---|---|
| `student.enrolled` | Admissions | Enrollment count, student-faculty ratio |
| `student.cancelled` | Admissions | Dropout/attrition rate |
| `result.published` | Examinations | Pass percentage, SGPA distribution |
| `scholarship.disbursed` | Finance | % students receiving financial aid |
| `employee.joined` | HR | Faculty qualifications %, sanctioned vs filled |
| `hr.appraisal_submitted` | HR | Research publications (API Cat III) |
| `library.catalogue_updated` | Student Services | Library holdings count |
| `grievance.closed` | Student Services | Grievance resolution rate |
| `training.completed` | HR | FDP completion, UGC mandatory programmes |

---

## 9. AI & LLM Layer

### Task Class → Model Tier Routing

**Never use one model for all tasks.** Route by task class:

| Task Class | Examples | Model Tier | Notes |
|---|---|---|---|
| `EXTRACTION` | Eligibility check inputs, slot filling, data parsing | Small (1.5B) | Current model fine |
| `DRAFTING` | Offer letters, parent alerts, shortage notices, appointment letters | Medium (7B+) | **Current model insufficient** |
| `GENERATION` | Lecture PPTs, course outlines, assignment rubrics | Medium (7B+) | **Current model insufficient** |
| `REASONING` | CAS eligibility, progression rules, UFM penalty | **Rules Engine — NOT LLM** | Never use LLM for policy decisions |
| `NARRATIVE` | NAAC SSR criterion narrative, NIRF SWOC analysis | Large (70B or API) | |
| `EMBEDDING` | RAG, semantic search, syllabus matching | Dedicated embedding model | `nomic-embed-text` is correct |

### LLM Router — How to Call

```python
# Always go through the router — never call Ollama/OpenAI directly
result = await llm_router.complete(
    task_class=TaskClass.DRAFTING,
    prompt=prompt,
    output_schema=OfferLetterDraft,   # always structured output
    tenant_id=tenant_id,
)
```

### Structured Outputs — Mandatory

Every LLM call must return a Pydantic model. Free text never enters the database.

```python
class OfferLetterDraft(BaseModel):
    applicant_name: str
    program: str
    specialization: str
    intake_year: int
    fee_structure: list[FeeComponent]
    acceptance_deadline: date
    generated_body: str           # the letter text
    requires_human_review: bool   # flag borderline quality

# Validate before any DB write
try:
    draft = OfferLetterDraft.model_validate_json(llm_raw_output)
except ValidationError as e:
    await audit_log.record_llm_validation_failure(prompt_id, e)
    raise LLMOutputInvalidError(e)
```

### AI Gateway Flow

```
User Request / Scheduled Trigger
        │
        ▼
AI Gateway (ai_gateway.py) — validates intent, enforces guardrails
        │
        ▼
Rules Engine — pre-execution policy check (blocks invalid proposals)
        │
        ▼
LLM Router — routes to correct model tier and provider
        │
        ▼
LLM Agent (LangGraph) — produces DRAFT only
        │
        ▼
Output Validation (Pydantic schema)
        │
        ▼
Approval Queue (if HITL required) OR Auto-execute (if low-stakes)
        │
        ▼
AuditLedger — records: model used, prompt hash, output hash, actor decision
```

### Local-First Inference (Air-Gapped Institutions)

When `ai.local_inference_only = true` for a tenant, all calls route to Ollama only. Cloud providers are blocked. The LLM router handles this automatically via the feature flag check.

Ensure Ollama has these models pulled:
- `qwen2.5:1.5b-instruct-q8_0` — small tasks
- `llama3.1:8b` — medium tasks (drafting, generation)
- `llama3.1:70b` — large tasks (narrative) — requires GPU server

---

## 10. Policy Engine — Rules-as-Data

This is the mechanism that makes ALIS multi-institution without code forks.

### Storage

Policies are stored as JSONB in `tenant_policies` table. Loaded at runtime. Cached in Redis (5-min TTL). Version-controlled — every change creates a new version, old versions retained for audit.

```sql
CREATE TABLE tenant_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    policy_id       TEXT NOT NULL,          -- 'attendance_eligibility'
    version         INTEGER NOT NULL,
    scope           JSONB,                  -- {program: 'B.Tech', batch: '2023'} or null for global
    rules           JSONB NOT NULL,         -- rule definitions
    effective_from  TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,            -- null = currently active
    created_by      UUID NOT NULL,
    UNIQUE(tenant_id, policy_id, version)
);
```

### Policy DSL — Rule Format

```yaml
# Example: Attendance eligibility policy
policy_id: "attendance_eligibility"
rules:
  - id: "min_attendance"
    condition: "student.attendance_pct >= threshold"
    threshold: 75                           # Institution sets this value
    on_fail: "INELIGIBLE"
    reason_code: "ATTENDANCE_BELOW_MINIMUM"
  
  - id: "condonation_window"
    condition: "student.attendance_pct >= condonation_min AND student.has_valid_reason"
    condonation_min: 65
    on_pass: "CONDONATION_PENDING"
  
  - id: "category_relaxation"
    condition: "student.category IN relaxed_categories AND student.attendance_pct >= relaxed_threshold"
    relaxed_categories: ["SC", "ST"]
    relaxed_threshold: 65
    on_pass: "ELIGIBLE"
```

### PolicyEngine Usage

```python
# Never evaluate rules inline — always go through PolicyEngine
result = await policy_engine.evaluate(
    policy_id="attendance_eligibility",
    context={
        "student": {
            "attendance_pct": 71.5,
            "category": "SC",
            "has_valid_reason": True,
        }
    },
    tenant_id=tenant_id,
)

# Result carries: verdict, reason_code, rule_id, policy_version
# policy_version is stored in audit log for regulatory traceability
await audit_log.record_policy_decision(student_id, result)
```

### Policies That Must Be in DSL (Not Hardcoded)

| Policy | Key Parameters |
|---|---|
| `attendance_eligibility` | minimum %, condonation window, category relaxations |
| `exam_eligibility` | attendance %, dues cleared, IA completion, disciplinary hold |
| `student_progression` | pass criteria, backlog threshold, probation CGPA |
| `fee_late_charge` | grace period days, daily rate, waiver conditions |
| `cas_promotion_eligibility` | years of service per stage, API score thresholds |
| `merit_list_formula` | weightage: 12th marks / entrance score / interview |
| `refund_policy` | cancellation timeline slabs, refund percentages |
| `scholarship_retention` | minimum CGPA, attendance, income slab |

---

## 10b. Policy Authoring Agent (PAA) — Chat → Live Rule Update

This is the capability that lets an authorised user (typically the VC or Registrar) type a natural-language policy change into the agent chat and have it route through approval to the live rules engine. The AI engine context is then automatically refreshed to reflect the new policy.

**Status: NOT YET BUILT.** Build after E14 Regulatory. Build sequence: conflict detector → impact calculator → intent translator → approval wiring → context broadcast.

**The core invariant that must never be violated:** A policy with `status='DRAFT'` is NEVER evaluated by `PolicyEngine.evaluate()`. Only `status='APPROVED'` policies are live. There is no bypass — not even for the VC. The approval step is governance, not bureaucracy.

### Architecture — four layers

```
User types in agent chat
        │
        ▼
Layer 1 — Intent classifier + conflict detector (no LLM for conflict check)
        │
        ▼
Layer 2 — PolicyAuthoringAgent.translate_intent() → PolicyChangeDraft (LLM: EXTRACTION tier)
        │
        ▼
Layer 3 — Approval gate (routed by POLICY_RISK_TIERS, via E13 Dynamic Workflow)
        │
        ▼
Layer 4 — broadcast_policy_update() → Redis cache invalidation + AI context refresh
```

Every step is written to the AuditLedger with `policy_version`.

### Layer 1 — PolicyConflictDetector

Pure data queries — no LLM involved. Runs before the LLM is ever called.

```python
class PolicyConflictDetector:
    async def check(self, draft: PolicyChangeDraft, tenant_id: str) -> ConflictReport:
        conflicts = []

        # Hard check: does proposed value breach a UGC/AICTE regulatory floor?
        if draft.policy_id == "attendance_eligibility":
            new_threshold = draft.parameter_changes.get("threshold")
            if new_threshold and new_threshold < 65:
                conflicts.append(ConflictItem(
                    severity="BLOCKING",
                    rule="UGC minimum attendance",
                    detail="UGC mandates minimum 65% for condonation. Cannot go below this.",
                ))

        # Soft check: does this overlap an existing active policy in the same module?
        related = await policy_repo.get_by_module(draft.policy_id.split("_")[0], tenant_id)
        for policy in related:
            overlap = self._find_rule_overlap(draft, policy)
            if overlap:
                conflicts.append(ConflictItem(
                    severity="WARNING",
                    rule=policy.policy_id,
                    detail=f"Overlaps with rule '{overlap}' in {policy.policy_id}",
                ))

        return ConflictReport(
            conflicts=conflicts,
            blocking=any(c.severity == "BLOCKING" for c in conflicts)
        )
```

If `ConflictReport.blocking` is `True`, the agent tells the user why and stops. No draft is created.

### Layer 1b — PolicyImpactCalculator

Shows the approver exactly who is affected before they sign off. Mandatory for all medium and high-risk policy changes.

```python
class PolicyImpactCalculator:
    async def calculate(self, draft: PolicyChangeDraft, tenant_id: str) -> ImpactReport:
        if draft.policy_id == "attendance_eligibility":
            old = await policy_repo.get_current_value(draft.policy_id, "threshold", tenant_id)
            new = draft.parameter_changes["threshold"]

            affected = await execute_query("""
                SELECT COUNT(*) FROM student_attendance_summary
                WHERE tenant_id = $1
                  AND attendance_pct >= $2
                  AND attendance_pct < $3
                  AND semester = current_semester()
            """, [str(tenant_id), new, old])

            return ImpactReport(
                students_affected=affected[0]["count"],
                direction="more_restrictive" if new > old else "more_lenient",
                summary=(
                    f"{affected[0]['count']} students currently between "
                    f"{new}% and {old}% will be newly affected."
                ),
                effective_date=draft.effective_from,
            )
```

The impact report is attached to the approval task card — the approver sees it before they can click Approve.

### Layer 2 — PolicyAuthoringAgent.translate_intent()

This is the only LLM call in the entire PAA pipeline. Use the `EXTRACTION` task class (small model tier). Always structured output — `PolicyChangeDraft` Pydantic model.

```python
class PolicyAuthoringAgent:

    async def translate_intent(
        self, user_message: str, tenant_id: str
    ) -> PolicyChangeDraft:

        # Feed current active policies as context — LLM needs to know what exists
        active_policies = await policy_repo.get_all_active(tenant_id)
        policy_schema = self._build_schema_context(active_policies)

        prompt = f"""
You are a policy authoring assistant for a university OS.

CURRENT ACTIVE POLICIES:
{policy_schema}

USER REQUEST:
"{user_message}"

Identify:
1. Which policy_id is being changed
2. Which specific rules are affected
3. The new parameter values
4. The scope (global / program-specific / batch-specific)
5. When it should take effect

Respond ONLY with JSON matching PolicyChangeDraft schema.
If the request is ambiguous, populate the 'ambiguities' list with
specific clarifying questions — do not guess.
"""
        result = await llm_router.complete(
            task_class=TaskClass.EXTRACTION,  # small model — never use REASONING here
            prompt=prompt,
            output_schema=PolicyChangeDraft,
            tenant_id=tenant_id,
        )

        # If confidence is low or questions remain, ask user before proceeding
        if result.confidence < 0.80 or result.ambiguities:
            return PolicyChangeDraft(status="NEEDS_CLARIFICATION", **result.dict())

        return result


class PolicyChangeDraft(BaseModel):
    policy_id: str
    change_type: Literal["modify_threshold", "add_rule", "remove_rule", "change_scope"]
    affected_rules: list[str]
    parameter_changes: dict[str, Any]   # {old_key: old_value, new_key: new_value}
    scope: dict                          # {"type": "global"|"program"|"batch", "ref": str|None}
    effective_from: str                  # "YYYY-MM-DD" | "next_semester" | "immediate"
    confidence: float                    # 0.0–1.0
    ambiguities: list[str]              # clarifying questions if confidence < 0.80
    status: str = "DRAFT"               # DRAFT until approved — never APPROVED here
```

**Critical:** The LLM output is used only to populate the `PolicyChangeDraft` struct. The actual DSL YAML is assembled deterministically from that struct — not generated by the LLM directly. Never trust LLM-generated YAML as policy.

### Layer 3 — Approval gate (risk-tiered)

Every policy change is routed through E13 Dynamic Process Engine. The risk tier determines the approval chain.

```python
POLICY_RISK_TIERS: dict[str, dict] = {
    # Low risk — single approver, 24h SLA
    "notification_templates":     {"approver": "registrar",       "sla_hours": 24,  "dual_auth": False},
    "sla_defaults":               {"approver": "registrar",       "sla_hours": 24,  "dual_auth": False},
    "late_fee_grace_period":      {"approver": "finance_officer", "sla_hours": 48,  "dual_auth": False},

    # Medium risk — VC approval, impact preview mandatory
    "attendance_eligibility":     {"approver": "vc", "sla_hours": 72,  "dual_auth": False, "impact_preview": True},
    "scholarship_retention":      {"approver": "vc", "sla_hours": 72,  "dual_auth": False, "impact_preview": True},
    "merit_list_formula":         {"approver": "vc", "sla_hours": 72,  "dual_auth": False, "impact_preview": True},

    # High risk — dual auth + full impact preview + conflict check mandatory
    "student_progression":        {"approver": "vc", "sla_hours": 96, "dual_auth": True,
                                   "second_approver": "academic_council", "impact_preview": True},
    "exam_eligibility":           {"approver": "vc", "sla_hours": 96, "dual_auth": True,
                                   "second_approver": "coe",             "impact_preview": True},
    "refund_policy":              {"approver": "vc", "sla_hours": 96, "dual_auth": True,
                                   "second_approver": "finance_officer", "impact_preview": True},

    # BLOCKED — cannot be changed via chat under any circumstances
    "audit_ledger_retention":     {"approver": "QUAICU_ONLY"},
    "tenant_isolation":           {"approver": "QUAICU_ONLY"},
    "dpdp_compliance_mode":       {"approver": "QUAICU_ONLY"},
    "rbac_system_roles":          {"approver": "QUAICU_ONLY"},
}
```

When `approver == "QUAICU_ONLY"`, the agent responds: *"This policy governs platform-level compliance and cannot be changed through ALIS. Please contact QUAICU support."* No draft is created, no workflow is triggered.

The approval task card shown to the approver must include:
- Plain-language summary of what changes
- Side-by-side old vs new values for every affected rule
- `ImpactReport` (how many students/staff affected)
- `ConflictReport` (any warnings, even if non-blocking)
- Effective date

### Layer 4 — broadcast_policy_update()

Called immediately after the approval workflow completes. Must run as a Celery task (not inline) so the approval response is not delayed.

```python
@celery_app.task(queue="default", bind=True, max_retries=3)
async def broadcast_policy_update(self, tenant_id: str, policy_id: str, new_version: int):
    try:
        # 1. Load all active policies for this tenant
        active_policies = await policy_repo.get_all_active(tenant_id)

        # 2. Build plain-language policy summary for the AI system prompt
        policy_summary = _format_policies_for_llm(active_policies)

        # 3. Push to Redis — AI gateway reads this on every agent invocation
        await redis.set(
            f"alis:ai_policy_context:{tenant_id}",
            policy_summary,
            ex=3600,  # 1-hour TTL; refreshed on every policy change regardless
        )

        # 4. Invalidate the policy evaluation cache
        # (all per-student cached results are now stale)
        async for key in redis.scan_iter(f"alis:policy_eval:{tenant_id}:*"):
            await redis.delete(key)

        # 5. Audit log
        await audit_ledger.record(
            tenant_id=tenant_id,
            event_type="policy.context_broadcast",
            payload={"policy_id": policy_id, "version": new_version},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

The AI gateway injects the cached policy context into every agent system prompt:

```python
class AIGateway:
    async def build_system_prompt(self, tenant_id: str, domain: str) -> str:
        policy_context = await redis.get(f"alis:ai_policy_context:{tenant_id}") or ""
        return f"""
You are the ALIS {domain} agent.

CURRENT INSTITUTIONAL POLICIES (live as of today):
{policy_context}

Never propose an action that violates these policies.
If a user asks you to do something that conflicts with policy,
explain the constraint and offer to raise a policy change request
through the proper PAA channel.
"""
```

### End-to-end conversation flow — reference implementation

This is the exact experience the PAA must produce. Use it as your acceptance test:

```
VC:    "Change minimum attendance from 75% to 80% for B.Tech students
        starting next semester. Keep SC/ST at 75%."

Agent: "Here's what I'm proposing:

        Policy: attendance_eligibility
        Scope: B.Tech program (all batches from July 2026)

        Current → Proposed:
        General:    75% → 80%
        SC/ST:      70% → 75%  [5% relaxation preserved]
        Condonation: 65% → 70%

        Impact: 234 B.Tech students currently between 75–80%
        would be newly ineligible if applied today.
        From July 2026, this affects the incoming batch only.

        No conflicts with UGC minimum requirements found.

        This requires VC approval (96-hour SLA). Send to queue?"

VC:    "Yes."

Agent: "Sent. Task ID: POL-2026-0047. You'll receive a formal
        approval card in your queue with the full impact report.
        On approval, the policy takes effect for July 2026 intake."

[VC approves in approval queue]

Agent: "POL-2026-0047 approved and live. Attendance threshold
        updated to 80% for B.Tech from July 2026. All eligibility
        checks, hall ticket gates, and parent alerts will use
        the new threshold automatically. Audit entry recorded."
```

### PAA file locations

```
ALIS/server/core/
├── policy_engine.py              # existing — PolicyEngine.evaluate() (read at runtime)
└── policy_authoring_agent.py     # CREATE THIS — PAA pipeline

ALIS/server/core/policy_authoring_agent.py contains:
    PolicyAuthoringAgent          # translate_intent() — the LLM call
    PolicyConflictDetector        # check() — pure data queries
    PolicyImpactCalculator        # calculate() — affected student counts
    broadcast_policy_update       # Celery task — Layer 4 context refresh
    POLICY_RISK_TIERS             # the approval routing map
```

---

## 11. Workflow Engine — Workflows-as-Data

Approval chains are stored as DAGs in the database. The Temporal runtime executes them without knowing what the workflow does.

### Storage

```sql
CREATE TABLE workflow_definitions (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    name          TEXT NOT NULL,           -- 'hall_ticket_approval'
    trigger_event TEXT NOT NULL,           -- 'exam.eligibility_confirmed'
    version       INTEGER NOT NULL,
    is_active     BOOLEAN DEFAULT true
);

CREATE TABLE workflow_steps (
    id                     UUID PRIMARY KEY,
    workflow_id            UUID REFERENCES workflow_definitions(id),
    step_order             INTEGER NOT NULL,
    step_type              TEXT NOT NULL,   -- 'approval' | 'auto' | 'parallel' | 'condition'
    assigned_role          TEXT,            -- RBAC role key
    sla_hours              INTEGER,
    on_approve             UUID REFERENCES workflow_steps(id),
    on_reject              UUID REFERENCES workflow_steps(id),
    on_sla_breach          UUID REFERENCES workflow_steps(id),
    auto_approve_on_breach BOOLEAN DEFAULT false,
    condition_expr         TEXT             -- Policy DSL expression for 'condition' steps
);
```

### Temporal Generic Runner

```python
@workflow.defn
class DynamicApprovalWorkflow:
    @workflow.run
    async def run(self, ctx: WorkflowContext) -> WorkflowResult:
        definition = await workflow.execute_activity(
            load_workflow_definition, args=[ctx.workflow_name, ctx.tenant_id]
        )
        current_step = definition.first_step
        
        while current_step:
            if current_step.step_type == "auto":
                await workflow.execute_activity(execute_auto_step, args=[current_step, ctx])
                current_step = current_step.on_approve
                
            elif current_step.step_type == "approval":
                await workflow.execute_activity(create_approval_task, args=[current_step, ctx])
                try:
                    signal = await workflow.wait_for_signal(
                        "approval_decision",
                        timeout=timedelta(hours=current_step.sla_hours)
                    )
                    current_step = current_step.on_approve if signal.approved \
                                   else current_step.on_reject
                except asyncio.TimeoutError:
                    if current_step.auto_approve_on_breach:
                        current_step = current_step.on_approve
                    else:
                        current_step = current_step.on_sla_breach
                        
            elif current_step.step_type == "condition":
                passed = await policy_engine.evaluate(current_step.condition_expr, ctx.data)
                current_step = current_step.on_approve if passed else current_step.on_reject
        
        return WorkflowResult(status="COMPLETE")
```

---

## 12. Feature Flags — Institutional Granularity

Feature flags control what is enabled per tenant. They are stored in DB, cached in Redis.

### Flag Categories

```
MODULE FLAGS
├── admissions.digilocker_verification     # requires DigiLocker API key per tenant
├── admissions.nta_score_import            # engineering programs only
├── academics.ai_ppt_generation            # premium tier
├── academics.ai_assignment_drafting       # premium tier
├── examinations.online_proctoring         # requires proctoring vendor contract
├── examinations.qr_hall_entry             # requires hardware QR scanners
├── examinations.question_paper_vault      # requires HashiCorp Vault installed
├── finance.emi_payment_plans              # configurable per institution
├── finance.gst_auto_filing               # requires GST portal API
├── hr.cas_promotion_tracking              # UGC-affiliated only
└── regulatory.naac_evidence_collection   # E14 — off until built

AI CAPABILITY FLAGS
├── ai.model_tier.extraction              # 'small' | 'medium' | 'large'
├── ai.model_tier.drafting               # 'small' | 'medium' | 'large'
├── ai.model_tier.generation             # 'small' | 'medium' | 'large'
├── ai.model_tier.narrative              # 'small' | 'medium' | 'large'
├── ai.local_inference_only              # blocks all cloud LLM calls
└── ai.content_generation_enabled        # master switch for all LLM tasks

COMPLIANCE FLAGS
├── compliance.dpdp_strict_mode          # all data ops require explicit consent log
├── compliance.ugc_fee_regulation_checks # blocks mid-year fee changes
└── compliance.naac_evidence_collection  # starts live metric harvesting
```

### Usage Pattern

```python
# Check before any gated feature
if not await feature_flags.is_enabled("academics.ai_ppt_generation", tenant_id):
    return await self.request_manual_content_upload(course_id)

# Get flag config (flags can carry parameters)
model_tier = await feature_flags.get_config("ai.model_tier.drafting", tenant_id, default="medium")
```

---

## 13. Plugin System

Custom modules per institution are implemented as plugins. They integrate with core systems (event bus, RBAC, workflow engine) without modifying core code.

### Plugin Interface

```python
class ALISPlugin(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str: ...
    
    @abstractmethod
    def get_event_subscriptions(self) -> list[EventSubscription]: ...
    
    @abstractmethod
    def get_emitted_events(self) -> list[str]: ...
    
    @abstractmethod
    def get_rbac_permissions(self) -> list[Permission]: ...
    
    @abstractmethod
    def get_workflow_definitions(self) -> list[WorkflowDefinition]: ...
    
    @abstractmethod
    async def on_install(self, tenant_id: str, config: dict) -> None: ...
    
    @abstractmethod
    async def on_uninstall(self, tenant_id: str) -> None: ...
```

Plugins are registered at startup and enabled per tenant via `tenant_plugins` table. Installing a plugin auto-registers its event subscriptions, RBAC permissions, and workflow definitions.

---

## 14. Known Issues — Fix Before Anything Else

These are production blockers. Do not add new features until these are resolved.

### P0 — SimpleConnectionPool → asyncpg (CRITICAL)

**File:** `ALIS/server/db_service.py`

`psycopg2.pool.SimpleConnectionPool` is synchronous and not safe for concurrent async use in FastAPI. Under load, two coroutines can grab the same connection causing data corruption and potential cross-tenant data leakage.

**Fix:** Replace with `asyncpg.create_pool()`. The `execute_query` and `execute_transaction` helpers are the correct abstraction — swap the driver underneath them. The tenant isolation `SET LOCAL` must be re-applied per connection checkout.

```python
# Target implementation
import asyncpg

async def create_pool():
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=20,
        command_timeout=30,
    )

async def execute_query(sql: str, params: list, tenant_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL alis.current_tenant = '{tenant_id}'")
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
```

### P0 — HashiCorp Vault for Question Paper Encryption

**Context:** Examination Stage 3 requires AES-256 encryption for question papers with CoE-only decrypt access and a full chain-of-custody audit log. MinIO server-side encryption alone is insufficient.

**Fix:** Install HashiCorp Vault in Docker Compose. Store question paper encryption keys in Vault, not in the application. Every decrypt operation must go through Vault and produce an audit log entry. Unauthorised access attempts must trigger immediate alerts to CoE + Registrar.

```yaml
# Add to docker-compose.yml
vault:
  image: hashicorp/vault:latest
  ports:
    - "8200:8200"
  environment:
    VAULT_DEV_ROOT_TOKEN_ID: ${VAULT_ROOT_TOKEN}
  cap_add:
    - IPC_LOCK
```

### P0 — LLM Model Tier for Drafting Tasks

**Current:** `qwen2.5:1.5b` used for all tasks including offer letters, parent alerts, appointment letters.

**Fix:** Pull `llama3.1:8b` via Ollama. Route `DRAFTING` and `GENERATION` task classes to the 8B model. The `qwen2.5:1.5b` remains correct for `EXTRACTION` tasks only.

```bash
ollama pull llama3.1:8b
```

### P1 — RBAC Scope on Role Assignments

**Verify:** Migration `0001` must have a `scope_id` column on `role_assignments` table. Without scope, HODs get institution-wide access instead of department-scoped access.

**Fix if missing:** Add migration to add `scope_id UUID REFERENCES scopes(id)` to `role_assignments`. Update permission check function to filter by scope.

### P1 — Finance Dues Race Condition

**Context:** Student pays dues → `student.dues_cleared` event fires → Examinations issues hall ticket. But a library fine added the same day invalidates the clearance. Hall ticket is already issued.

**Fix:** Examinations must query a `student_dues_status` read model at hall-ticket generation time, not just listen to the event. The read model is updated by all dues-posting modules in real time.

### P1 — DigiLocker Integration (Stub → Live)

**File:** Integration marked as Stub in tech overview.

**Fix:** Implement the NIC DigiLocker institutional API before first pilot. Document verification is the highest-friction point in admissions. Without this, staff verify documents manually — defeating the product value proposition.

---

## 15. Cross-Module Event Contract

### student.enrolled — Payload Specification

This is the most important event in the system. Every downstream module depends on it. The payload must carry all fields below.

```python
class StudentEnrolledPayload(BaseModel):
    student_id: str
    roll_number: str
    program: str
    specialization: str
    batch: str
    intake_year: int
    semester: int = 1
    section: str | None = None
    category: str                    # General / SC / ST / OBC-NCL / EWS / PwD
    is_first_gen: bool
    hostel_opted: bool
    transport_opted: bool = False
    email: str
    phone: str
    parent_email: str | None
    parent_phone: str | None
    # Risk baseline — required by Academics Module 7
    entrance_score: float | None
    twelfth_percentage: float
    twelfth_subjects: list[str]
    # Finance
    fee_category: str                # general / sc_st / management_quota / nri
    scholarship_type: str | None
    # Admissions trace
    application_id: str
    counselor_id: str | None
```

### exam.eligibility_confirmed — Payload Specification

```python
class ExamEligibilityPayload(BaseModel):
    student_id: str
    semester: int
    academic_year: str
    eligible_courses: list[str]      # course IDs student can appear for
    ineligible_courses: list[IneligibleCourse]
    condonation_courses: list[str]   # approved condonation cases
    dues_cleared: bool
    disciplinary_hold: bool
    eligibility_locked_at: datetime  # timestamp — immutable after this
```

---

## 16. Critical DO NOTs

Read these before writing any code.

```
DO NOT hardcode any tenant-specific value — use PolicyEngine
DO NOT call another module's service class directly — use domain events
DO NOT use SimpleConnectionPool — migrate to asyncpg
DO NOT use Python eval() for policy expressions — use asteval or custom parser
DO NOT store LLM free text in the database — always use structured Pydantic output
DO NOT use the LLM for policy decisions (eligibility, progression, penalties) — use rules engine
DO NOT write migrations in raw SQL — use Alembic
DO NOT delete records — use status='ARCHIVED' or status='ANNULLED'
DO NOT skip audit log entries — every state change must be logged
DO NOT give the LLM access to write directly to the database — always through approval workflow
DO NOT use integer PKs — always UUID v4
DO NOT expose stack traces in API error responses
DO NOT store question paper decryption keys in .env or application config — use HashiCorp Vault
DO NOT let approval tasks block indefinitely — every gate has an SLA and escalation path
DO NOT skip the tenant scope SET LOCAL on database connections
```

---

## 17. File Structure

```
ALIS/
├── server/
│   ├── main.py                    # FastAPI app, middleware, router registration, health probes
│   ├── worker.py                  # Celery app + Beat schedule definitions
│   ├── db_service.py              # DB connection pool, execute_query, execute_transaction
│   ├── core/
│   │   ├── settings.py            # All infrastructure config (Pydantic Settings)
│   │   ├── domain_events.py       # Domain Event Bus + handler registry
│   │   ├── ai_gateway.py          # AI invocation, guardrails, HITL orchestration
│   │   ├── security.py            # TenantMiddleware, RBAC, JWT
│   │   ├── policy_engine.py       # Rules-as-data DSL interpreter
│   │   ├── feature_flags.py       # Institutional feature flag system
│   │   ├── llm_router.py          # Task class → model tier → provider routing
│   │   ├── audit_ledger.py        # Immutable hash-chain audit log
│   │   └── plugin_registry.py     # Plugin installation and event wiring
│   ├── modules/
│   │   ├── admissions/            # E04 — 87 routes, 40+ tables
│   │   ├── academics/             # E05
│   │   ├── examinations/          # E06
│   │   ├── finance/               # E07
│   │   ├── hr/                    # E08
│   │   ├── student_services/      # E09
│   │   ├── communication/         # E10
│   │   ├── reporting/             # E11
│   │   ├── alumni/                # E12
│   │   ├── workflow_engine/       # E13 — Dynamic Process Engine
│   │   └── regulatory/            # E14 — NOT YET BUILT
│   └── api/
│       └── admissions_router.py   # 87-route admissions API (example)
├── migrations/
│   └── versions/
│       ├── 0001_foundation.py     # auth, users, RBAC
│       ├── 0002-0012_*.py         # core module tables
│       ├── 0013_indexes.py        # performance indexes
│       └── 0014_admissions.py     # full admissions schema
├── web/                           # React frontend (in progress — P15)
├── nginx/
│   └── nginx.conf                 # Reverse proxy, rate limiting, SSL
├── docker-compose.yml             # Full 8-service stack
└── .github/
    └── workflows/
        └── ci.yml                 # CI/CD pipeline
```

---

## 18. API Conventions

| Convention | Standard |
|---|---|
| API prefix | `/api/v1/` |
| IDs | UUID v4 strings |
| Timestamps | ISO 8601 UTC |
| Money | String in JSON (`"15000.00"`) |
| Soft deletes | `status` field change — never physical deletion |
| Application IDs | `APP-{YEAR}-{6-digit-seq}` e.g. `APP-2025-000047` |
| Roll numbers | `{YY}{ProgramCode}{Sequential}` e.g. `25BCE0001` — configurable per institution |
| Error format | `{"error": "...", "code": "...", "detail": {}}` |
| Pagination | `limit` / `offset` query params |
| Tenant header | `X-Tenant-ID` — extracted by TenantMiddleware |

### Rate Limiting (Nginx zones)

| Zone | Limit |
|---|---|
| Auth endpoints | 10 req/min |
| General API | 60 req/min |
| AI endpoints | 10 req/min |
| Health/readiness | exempt |

---

## 19. Testing Standards

- **846 tests, all passing** — do not break this
- Every new feature requires unit tests before merge
- Integration tests marked with `@pytest.mark.integration`
- AI tests excluded from CI (`test_e03_s02_model_registry.py` — standalone)
- Use `fakeredis` for all Redis-dependent tests — never connect to real Redis in unit tests
- Use `TestClient` with JWT auth headers injected via fixtures
- Never write tests that depend on insertion order — use explicit ordering
- Test state machine transitions: valid path AND all invalid transitions (must raise `InvalidTransitionError`)

```python
# Required test pattern for state machines
def test_invalid_transition_blocked():
    with pytest.raises(InvalidTransitionError):
        application_state_machine.transition(
            app_id, "Enrolled",  # jumping from Submitted to Enrolled — illegal
            actor_id=registrar_id
        )
```

---

## 20. Build Sequence

When implementing new work, follow this sequence:

### For new features within an existing module
1. Check if the feature requires a new policy → add to `tenant_policies` DSL, not code
2. Check if the feature requires a new approval gate → add to workflow DAG, not code
3. Check if the feature crosses module boundaries → add a domain event, not a direct call
4. Write the feature behind a feature flag
5. Write tests first (unit + integration)
6. Add Alembic migration if schema changes
7. Update audit log calls
8. Update this reference document

### For E14 Regulatory Module (Next Priority)
1. Create `regulatory/` module folder under `modules/`
2. Create `regulatory_metrics` table — one row per metric per tenant per date
3. Register event subscriptions for all events listed in §15's E14 subscriber list
4. Each event handler updates the relevant metric row — pure writes, no cross-module reads
5. Build NAAC dashboard as a read from `regulatory_metrics` — no live module queries
6. Gate behind `regulatory.naac_evidence_collection` feature flag
7. Add NIRF, AISHE, UGC as additional metric consumers of the same event stream

### For new institutions (onboarding)
1. Create tenant schema in PostgreSQL
2. Run Alembic migrations for tenant schema
3. Seed system roles (from §7 role list)
4. Configure `tenant_policies` for all 8 policy types in §10
5. Enable/disable feature flags per institution tier
6. Configure workflow DAGs (or use platform defaults)
7. Set LLM model tier preferences
8. Run integration tests against new tenant

---

## Appendix: Scheduled Tasks (Celery Beat)

| Schedule | Task | Module |
|---|---|---|
| Daily midnight | Academic calendar phase checks | Academics |
| Daily 09:00 | Fee overdue detection | Finance |
| Daily 09:05 | Invoice overdue detection | Finance |
| Hourly | Workflow task SLA reminders | Workflow Engine |
| Every 5 min | Failed domain event retry | All |
| **Every 30 sec** | **Financial/exam event retry** | **Finance, Examinations** |
| Daily 00:30 | KPI snapshot generation | Reporting |
| Monthly | Scholarship renewal check | Student Services |
| Annual (March 1) | Appraisal cycle initiation | HR |
| Annual (July) | AQAR data compilation draft | Regulatory (E14) |

---

## Appendix: GST Treatment Reference (Finance Module)

| Fee Head | GST Status | Rate |
|---|---|---|
| Tuition Fee (UGC-recognised program) | EXEMPT | 0% |
| Examination Fee | EXEMPT | 0% |
| Development / Infrastructure Fee | EXEMPT | 0% |
| Hostel Fee (institution-run) | EXEMPT | 0% |
| Hostel Fee (third-party managed) | TAXABLE | 18% |
| Transport Fee (institution bus) | TAXABLE | 5% |
| Canteen / Mess (third-party) | TAXABLE | 18% |
| Library Fine | TAXABLE | 18% |
| Late Fee | TAXABLE | 18% |
| Alumni Donation (80G registered) | EXEMPT | 0% |

---

## Appendix: TDS Rate Reference (Finance Module, FY 2025-26)

| Section | Payment Type | Rate | Threshold |
|---|---|---|---|
| 194J | Professional services | 10% | ₹50,000/year |
| 194J | Technical services | 2% | ₹50,000/year |
| 194I | Rent (land/building) | 10% | ₹2,40,000/year |
| 194C | Contractor payments | 1% individual / 2% company | ₹30,000/txn |
| 192 | Salary | Per tax slab | Above exemption |

Deposit due: 7th of following month. 26Q filing: quarterly.

---

---

## 21. Go-Live Blocker: Parent / Guardian Portal (E16)

Every parent needs read-only access to their child's key data. This is the most-requested feature at every Indian university deployment. Without it, parents call the Dean directly.

**RBAC:** `guardian` role — scoped to a single `student_id`. Read-only. No edit access anywhere. Provisioned automatically on `student.enrolled` using `parent_phone` from the enrollment payload.

**Authentication:** OTP-only via mobile — no username/password. Parents authenticate with their registered mobile number, receive a 6-digit OTP, get a 30-minute session. No permanent session tokens for guardians.

**What guardians can see:**
- Attendance % per course, trend chart (last 30 days)
- Current semester dues and payment history
- Upcoming exam schedule
- Results when published
- Any communications sent to the student
- Risk level as a simple traffic light (Green / Amber / Red) — no clinical detail

**What guardians can never see:** Counseling session notes, grievance details, placement negotiation data, other students' data.

```python
class GuardianPortalEventHandler:
    """Subscribes to student events and keeps guardian view current."""

    async def handle_student_enrolled(self, event: DomainEvent):
        payload = StudentEnrolledPayload(**event.payload)
        if not payload.parent_phone:
            return
        await execute_transaction([(
            """INSERT INTO guardian_accounts
               (id, tenant_id, student_id, phone, otp_verified, created_at)
               VALUES ($1, $2, $3, $4, false, now())
               ON CONFLICT (tenant_id, phone, student_id) DO NOTHING""",
            [str(uuid4()), payload.tenant_id, payload.student_id, payload.parent_phone]
        )])
        await send_whatsapp(
            payload.parent_phone,
            template="guardian_portal_welcome",
            params={"student_name": payload.full_name, "portal_url": portal_url}
        )
```

```sql
CREATE TABLE guardian_accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    student_id  UUID NOT NULL,
    phone       TEXT NOT NULL,
    otp_verified BOOLEAN DEFAULT false,
    last_login  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, phone, student_id)
);
CREATE INDEX idx_guardian_phone ON guardian_accounts(tenant_id, phone);
```

**Feature flag:** `portal.guardian_access` — off by default, enabled per institution.

---

## 22. Go-Live Blocker: DPDP Consent Management (E21)

India's Digital Personal Data Protection Act 2023 requires explicit, purpose-specific consent before collecting personal data. Non-compliance from day one is a legal liability.

**Core tables:**

```sql
CREATE TABLE consent_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    data_subject_id UUID NOT NULL,        -- student_id or employee_id
    subject_type    TEXT NOT NULL CHECK (subject_type IN ('student','employee','guardian')),
    purpose         TEXT NOT NULL,         -- 'academic_records','financial_data','placement_data'
    legal_basis     TEXT NOT NULL,         -- 'consent','legitimate_interest','legal_obligation'
    consent_given   BOOLEAN NOT NULL,
    consent_text    TEXT NOT NULL,         -- exact text shown at time of consent
    ip_address      INET,
    user_agent      TEXT,
    given_at        TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ,          -- null = indefinite
    withdrawn_at    TIMESTAMPTZ,
    withdrawal_reason TEXT
);

CREATE TABLE erasure_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    data_subject_id UUID NOT NULL,
    requested_at    TIMESTAMPTZ DEFAULT now(),
    status          TEXT DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','IN_PROGRESS','COMPLETED','REJECTED')),
    rejection_reason TEXT,                -- e.g. 'legal_hold_active'
    completed_at    TIMESTAMPTZ,
    -- Erasure cascades across all modules but preserves anonymised statistical aggregates
    modules_cleared JSONB DEFAULT '{}'
);
```

**Erasure workflow:** When a student exercises right to erasure, a Temporal workflow cascades deletion across all modules (PII fields set to NULL or hashed), while preserving anonymised records needed for NAAC/NIRF statistical reporting. Legal holds (active disciplinary case, pending fee dispute) block erasure and must be resolved first.

```python
@workflow.defn
class DataErasureWorkflow:
    @workflow.run
    async def run(self, request_id: str, subject_id: str, tenant_id: str):
        # Check for legal holds before proceeding
        holds = await workflow.execute_activity(check_legal_holds, args=[subject_id, tenant_id])
        if holds:
            await workflow.execute_activity(reject_erasure, args=[request_id, holds])
            return

        # Cascade anonymisation across all modules
        for module in ['admissions','academics','examinations','finance','hr','student_services']:
            await workflow.execute_activity(anonymise_module_data, args=[module, subject_id, tenant_id])
            await workflow.execute_activity(mark_module_cleared, args=[request_id, module])

        await workflow.execute_activity(complete_erasure, args=[request_id])
```

**Every data collection point** (application form, document upload, fee payment, placement profile) must log a consent record before writing data. The `ConsentMiddleware` enforces this for student-facing endpoints.

---

## 23. Go-Live Blocker: MFA / Two-Factor Authentication

Admin, Registrar, Finance, CoE, and HR roles must use MFA. These accounts have access to sensitive PII and financial records.

```python
class MFAConfig(BaseModel):
    enabled: bool = True
    method: Literal["totp", "sms_otp", "email_otp"] = "totp"
    backup_codes_count: int = 8
    session_duration_minutes: int = 480    # 8 hours for admin roles
    remember_device_days: int = 30

# Roles that MUST have MFA enabled — enforced at login, not optional
MFA_REQUIRED_ROLES = {
    "super_admin", "registrar", "exam_controller",
    "finance_officer", "hr_officer", "vc"
}
```

```sql
ALTER TABLE users
    ADD COLUMN mfa_secret      TEXT,          -- TOTP secret (encrypted at rest)
    ADD COLUMN mfa_enabled     BOOLEAN DEFAULT false,
    ADD COLUMN mfa_backup_codes JSONB DEFAULT '[]',  -- hashed backup codes
    ADD COLUMN mfa_enrolled_at TIMESTAMPTZ;

CREATE TABLE mfa_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    tenant_id   UUID NOT NULL,
    device_hash TEXT NOT NULL,    -- hash of user-agent + IP for "remember device"
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

**Login flow with MFA:**
1. User submits username + password → credential check passes → `MFA_REQUIRED` response (not a full JWT yet)
2. Frontend shows TOTP input / OTP input
3. User submits OTP → validated → full JWT issued
4. "Remember this device" option hashes device fingerprint, stores in `mfa_sessions` for `remember_device_days`

**Feature flag:** `security.mfa_required` — enforced for all roles in `MFA_REQUIRED_ROLES`. Cannot be disabled for these roles.

---

## 24. Go-Live Blocker: WhatsApp Business API (E10 Extension)

WhatsApp is the primary communication channel for Indian university students and parents. Email open rates in this demographic are below 20%. WhatsApp open rates exceed 90%.

**Integration:** MSG91 WhatsApp Business API (primary), Gupshup (fallback). Both support template-based messages required by WhatsApp Business policy.

```python
class WhatsAppChannel:
    """First-class channel in E10 Communication Hub."""

    TEMPLATE_MAP = {
        # Admissions
        "application_submitted":     "alis_app_submitted_v1",
        "document_rejected":         "alis_doc_rejected_v1",
        "offer_issued":              "alis_offer_letter_v1",
        "seat_confirmed":            "alis_seat_confirmed_v1",
        # Academics
        "attendance_below_75":       "alis_attendance_alert_v1",
        "assignment_deadline_t2":    "alis_assignment_reminder_v1",
        "timetable_published":       "alis_timetable_v1",
        # Examinations
        "hall_ticket_ready":         "alis_hall_ticket_v1",
        "result_published":          "alis_result_v1",
        # Finance
        "fee_due":                   "alis_fee_reminder_v1",
        "payment_confirmed":         "alis_payment_receipt_v1",
        # Guardian-specific
        "guardian_attendance_alert": "alis_guardian_alert_v1",
        "guardian_result":           "alis_guardian_result_v1",
    }

    async def send(self, phone: str, template_key: str, params: dict, tenant_id: str):
        if not await feature_flags.is_enabled("communication.whatsapp", tenant_id):
            return  # fall back to SMS silently

        template = self.TEMPLATE_MAP[template_key]
        provider = await self._get_provider(tenant_id)  # MSG91 or Gupshup
        await provider.send_template(phone=phone, template=template, params=params)
        await delivery_log.record(channel="whatsapp", phone=phone, template=template)
```

**Two-way messaging:** Students can reply to WhatsApp notifications. Inbound messages are routed to the agent chat via a webhook endpoint (`POST /api/v1/communication/whatsapp/inbound`). The agent responds in WhatsApp for simple queries (fee balance, exam date) and escalates complex ones to the staff portal.

**Feature flag:** `communication.whatsapp` — off by default, requires MSG91 API key per institution.

---

## 25. Go-Live Blocker: Observability Stack

Without structured observability, production debugging is impossible and SLA commitments cannot be honoured.

**Docker Compose additions:**

```yaml
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus:latest
  ports: ["9090:9090"]
  volumes: ["./prometheus.yml:/etc/prometheus/prometheus.yml"]

grafana:
  image: grafana/grafana:latest
  ports: ["3000:3000"]
  environment:
    GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}

loki:
  image: grafana/loki:latest
  ports: ["3100:3100"]
```

**Structured logging — every log line must carry these fields:**

```python
import structlog

log = structlog.get_logger()

# Every request handler — injected by middleware
log.info("api.request",
    tenant_id=tenant_id,
    request_id=request_id,
    user_id=user_id,
    method=request.method,
    path=request.url.path,
    duration_ms=elapsed,
    status_code=response.status_code,
)

# Every LLM call
log.info("llm.call",
    tenant_id=tenant_id,
    task_class=task_class,
    model=model_used,
    prompt_tokens=usage.prompt_tokens,
    completion_tokens=usage.completion_tokens,
    latency_ms=latency,
    cost_usd=cost,
)

# Every domain event
log.info("domain_event.published",
    tenant_id=tenant_id,
    event_type=event.event_type,
    aggregate_id=event.aggregate_id,
)
```

**Key Prometheus metrics to expose:**

```python
from prometheus_client import Counter, Histogram, Gauge

api_requests_total = Counter("alis_api_requests_total", "Total API requests", ["tenant_id","method","path","status"])
api_latency = Histogram("alis_api_latency_seconds", "API latency", ["path"])
celery_queue_depth = Gauge("alis_celery_queue_depth", "Celery queue depth", ["queue"])
llm_calls_total = Counter("alis_llm_calls_total", "LLM calls", ["task_class","model","tenant_id"])
llm_cost_usd = Counter("alis_llm_cost_usd_total", "LLM cost in USD", ["tenant_id"])
policy_evaluations = Counter("alis_policy_evals_total", "Policy evaluations", ["policy_id","verdict","tenant_id"])
temporal_workflow_failures = Counter("alis_temporal_failures_total", "Temporal workflow failures", ["workflow_name"])
```

**Alerting rules (Prometheus AlertManager):**

```yaml
groups:
  - name: alis_critical
    rules:
      - alert: APIErrorRateHigh
        expr: rate(alis_api_requests_total{status=~"5.."}[5m]) > 0.05
        for: 2m
        annotations:
          summary: "API error rate above 5% for 2 minutes"

      - alert: CeleryQueueBacklog
        expr: alis_celery_queue_depth{queue="default"} > 500
        for: 5m
        annotations:
          summary: "Celery queue backlog exceeding 500 tasks"

      - alert: LLMCostSpike
        expr: increase(alis_llm_cost_usd_total[1h]) > 10
        annotations:
          summary: "LLM cost spike: >$10 in last hour for a tenant"
```

---

## 26. Go-Live Blocker: Fee Structure Versioning

Fee structures must be locked per intake batch. A student admitted in 2022 must be billed under the 2022 fee structure for all 4 years regardless of subsequent changes.

```sql
-- Replace the existing fee_master table approach
CREATE TABLE fee_structures (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    program_id          UUID NOT NULL,
    intake_year         INTEGER NOT NULL,    -- 2022, 2023, 2024 ...
    valid_for_batches   INTEGER[],           -- [2022, 2023] — which intake years this applies to
    fee_heads           JSONB NOT NULL,      -- itemised fee breakdown
    total_annual        DECIMAL(12,2) NOT NULL,
    approved_by         UUID NOT NULL,       -- VC who approved this structure
    published_at        TIMESTAMPTZ NOT NULL,-- cannot be changed after this
    is_locked           BOOLEAN DEFAULT false, -- true = immutable
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, program_id, intake_year)
);

-- When student is enrolled, their fee structure is snapshotted
CREATE TABLE student_fee_assignments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    student_id       UUID NOT NULL UNIQUE,
    fee_structure_id UUID NOT NULL REFERENCES fee_structures(id),
    assigned_at      TIMESTAMPTZ DEFAULT now(),
    -- This record is immutable after creation
    CONSTRAINT no_update CHECK (true)  -- enforced via trigger
);
```

**Critical rule:** `fee_structures.is_locked = true` once any student is enrolled under it. Locked structures cannot be modified — only a new structure for the next intake year can be created. The `FeeStructureService` enforces this:

```python
class FeeStructureService:
    async def update_fee_structure(self, structure_id: UUID, updates: dict, tenant_id: str):
        structure = await get_fee_structure(structure_id, tenant_id)
        if structure.is_locked:
            raise FeeStructureLockedError(
                f"Fee structure for {structure.intake_year} is locked. "
                "Create a new structure for the next intake year."
            )
```

---

## 27. Go-Live Blocker: Data Migration Tooling

Every new institution has existing data. Without structured migration tooling, go-live takes months and produces bad data.

**Migration pipeline per entity type:**

```python
class MigrationPipeline:
    """
    Three-phase pipeline: validate → dry-run → commit.
    Never skips validation. Never commits without dry-run confirmation.
    """

    SUPPORTED_ENTITIES = [
        "students", "faculty", "courses", "fee_records",
        "historical_attendance", "exam_results", "alumni"
    ]

    async def run(
        self,
        entity_type: str,
        file_path: str,
        tenant_id: str,
        mode: Literal["validate", "dry_run", "commit"],
    ) -> MigrationReport:

        # Phase 1: Parse and validate every row through the rules engine
        rows = await self.parse_file(file_path, entity_type)
        errors = []
        warnings = []

        for i, row in enumerate(rows):
            result = await self.validate_row(row, entity_type, tenant_id)
            if result.has_errors:
                errors.append(RowError(row=i+1, fields=result.errors))
            if result.has_warnings:
                warnings.append(RowWarning(row=i+1, fields=result.warnings))

        if errors:
            return MigrationReport(
                status="VALIDATION_FAILED",
                total_rows=len(rows),
                error_count=len(errors),
                errors=errors,
                warnings=warnings,
                committed=False
            )

        if mode == "validate":
            return MigrationReport(status="VALIDATION_PASSED", ...)

        # Phase 2: Dry run — show what will be created without writing
        if mode == "dry_run":
            preview = [self.preview_insert(row, entity_type) for row in rows]
            return MigrationReport(status="DRY_RUN_COMPLETE", preview=preview, ...)

        # Phase 3: Commit — write to DB atomically
        async with db.transaction():
            for row in rows:
                await self.insert_row(row, entity_type, tenant_id)
                await audit_ledger.record(
                    event_type=f"migration.{entity_type}.imported",
                    payload={"row": row, "source": "migration_pipeline"}
                )

        return MigrationReport(status="COMMITTED", total_rows=len(rows), ...)
```

**CSV templates** — one per entity type, downloadable from the admin console. Every template has: required columns, optional columns, allowed values, example data. Template validation is enforced before the file can be uploaded.

**Duplicate detection during migration:** Before inserting a student record, run Jaro-Winkler match against existing records on (name, DOB, phone). Flag matches above 0.90 similarity for human review — don't auto-merge.

---

## 28. Go-Live Blocker: Shadow Mode Onboarding

Shadow mode runs ALIS in parallel with the existing system for 4–8 weeks before go-live. ALIS computes everything but sends no external communications and drives no consequential actions.

```python
class ShadowModeConfig(BaseModel):
    enabled: bool
    started_at: datetime
    target_go_live: datetime
    # Divergence thresholds — go-live is blocked until these are met
    max_attendance_divergence_pct: float = 2.0   # ALIS vs manual: max 2% diff
    max_fee_divergence_pct: float = 0.1           # max 0.1% diff — financial
    max_eligibility_divergence_pct: float = 1.0
    # Communication suppression — all outbound blocked in shadow mode
    suppress_sms: bool = True
    suppress_email: bool = True
    suppress_whatsapp: bool = True
    suppress_portal_updates: bool = False  # staff can see ALIS outputs, students cannot
```

**Shadow mode middleware — wraps all outbound communication:**

```python
class ShadowModeMiddleware:
    async def before_send_notification(self, notification: Notification, tenant_id: str):
        config = await get_shadow_config(tenant_id)
        if not config or not config.enabled:
            return notification  # normal mode — send

        # In shadow mode: log what WOULD have been sent, but suppress it
        await shadow_log.record(
            tenant_id=tenant_id,
            channel=notification.channel,
            recipient=notification.recipient,
            content=notification.content,
            trigger_event=notification.trigger_event,
            suppressed=True,
        )
        raise SuppressedByShadowMode()  # caller catches and skips send
```

**Divergence tracker — Celery Beat job runs nightly:**

```python
@celery_app.task
async def compute_shadow_divergence(tenant_id: str):
    """Compare ALIS output vs staff-entered actuals. Log divergences."""
    # Attendance divergence: compare ALIS-computed % vs manually marked register
    attendance_diff = await compare_attendance_records(tenant_id)
    # Fee divergence: compare ALIS-computed dues vs Tally records
    fee_diff = await compare_fee_records(tenant_id)

    report = DivergenceReport(
        tenant_id=tenant_id,
        date=date.today(),
        attendance_divergence_pct=attendance_diff.pct,
        fee_divergence_pct=fee_diff.pct,
        divergent_records=attendance_diff.records + fee_diff.records,
    )
    await save_divergence_report(report)

    # Auto-escalate to QUAICU if divergence is outside threshold
    config = await get_shadow_config(tenant_id)
    if report.attendance_divergence_pct > config.max_attendance_divergence_pct:
        await notify_quaicu_team(tenant_id, report)
```

**Go-live gate:** The system won't allow disabling shadow mode until all divergence metrics are below threshold for 5 consecutive days. This is enforced in the admin console — the "Go Live" button is greyed out until the gate passes.

---

## 29. Platform Gap: API Versioning Strategy

As ALIS evolves, breaking API changes must not break existing institution integrations.

**URL versioning:** `/api/v1/` is current. When breaking changes are needed, `/api/v2/` is created. Both versions run simultaneously. Minimum deprecation window: 12 months. Deprecation notice is sent as a response header: `Deprecation: true`, `Sunset: {ISO date}`.

```python
# FastAPI router versioning pattern
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")

# Deprecation middleware for v1 routes
class DeprecationMiddleware:
    DEPRECATED_AFTER = {"v1": date(2027, 3, 1)}

    async def __call__(self, request: Request, call_next):
        response = await call_next(request)
        version = self._extract_version(request.url.path)
        if version in self.DEPRECATED_AFTER:
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = self.DEPRECATED_AFTER[version].isoformat()
        return response
```

**Changelog discipline:** Every API change (including additive changes) is logged in `CHANGELOG.md` with the affected endpoint, change type, migration guide, and the version it applies to. Claude Code must update `CHANGELOG.md` for every API change, not just breaking ones.

---

## 30. Platform Gap: Multi-Campus / Group Entity Model

University groups (KL, Manipal, Amity, etc.) have multiple campuses. Group-level reporting and administration must span tenants without breaking per-campus isolation.

```sql
CREATE TABLE institution_groups (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE group_tenant_memberships (
    group_id   UUID NOT NULL REFERENCES institution_groups(id),
    tenant_id  UUID NOT NULL,
    campus_name TEXT NOT NULL,
    PRIMARY KEY (group_id, tenant_id)
);

-- Group-level admin role — read-only cross-tenant
-- Uses a special "group_context" session variable instead of per-tenant
```

**Group-level read model:** A separate `group_metrics` table is populated by event consumers that subscribe to events from all tenants in a group. This is a read-only aggregation — it never writes back to any tenant schema.

**Group-level NIRF:** The Regulatory module (E14) can generate a consolidated NIRF submission that aggregates `regulatory_metrics` across all campuses in a group. Each campus remains independently accreditable (NAAC per campus) but the group NIRF submission is consolidated.

---

## 31. Platform Gap: Outbound Webhook API

Institutions have existing tools (student apps, fee kiosks, biometric devices, state government portals) that need real-time events from ALIS.

```sql
CREATE TABLE webhook_subscriptions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    name         TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    secret       TEXT NOT NULL,       -- HMAC signing secret
    event_types  TEXT[] NOT NULL,     -- which events to receive
    is_active    BOOLEAN DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE webhook_delivery_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    attempt_count   INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    status          TEXT DEFAULT 'PENDING',
    response_status INTEGER,
    response_body   TEXT
);
```

**Delivery worker — Celery task with exponential backoff:**

```python
@celery_app.task(bind=True, max_retries=5)
async def deliver_webhook(self, delivery_id: str):
    delivery = await get_webhook_delivery(delivery_id)
    subscription = await get_webhook_subscription(delivery.subscription_id)

    payload_str = json.dumps(delivery.payload)
    signature = hmac.new(subscription.secret.encode(), payload_str.encode(), "sha256").hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                subscription.endpoint_url,
                content=payload_str,
                headers={
                    "Content-Type": "application/json",
                    "X-ALIS-Signature": f"sha256={signature}",
                    "X-ALIS-Event": delivery.event_type,
                }
            )
        await mark_delivered(delivery_id, response.status_code)
    except Exception as exc:
        backoff = 2 ** self.request.retries * 60  # 1min, 2min, 4min, 8min, 16min
        raise self.retry(exc=exc, countdown=backoff)
```

---

## 32. Platform Gap: Backup and Disaster Recovery

Every institution's ALIS instance must have defined RTO (4 hours) and RPO (24 hours).

**Backup schedule — Celery Beat jobs:**

```python
CELERY_BEAT_SCHEDULE = {
    # Daily pg_dump — all tenant schemas
    "daily-pg-backup": {
        "task": "backup.postgresql_dump",
        "schedule": crontab(hour=2, minute=0),
        "args": ["all_tenants"],
    },
    # MinIO bucket sync to backup storage
    "daily-minio-backup": {
        "task": "backup.minio_sync",
        "schedule": crontab(hour=2, minute=30),
    },
    # Verify yesterday's backup is restorable (dry-run restore to temp schema)
    "daily-backup-verify": {
        "task": "backup.verify_restore",
        "schedule": crontab(hour=4, minute=0),
    },
}
```

**Recovery runbook — documented steps:**
1. Restore PostgreSQL from latest daily dump to new instance
2. Restore MinIO objects from backup bucket
3. Replay Temporal workflow state from checkpoint
4. Run `alembic upgrade head` to confirm schema integrity
5. Run smoke test suite (`pytest -m smoke`) — 15 critical paths
6. Enable read traffic, verify, enable write traffic
7. Total target: < 4 hours

**Backup retention:** 7 daily, 4 weekly, 12 monthly. All backups encrypted with institution-specific key stored in HashiCorp Vault.

**Smoke test suite (must exist):** 15 tests covering: login, student enrollment, fee payment, attendance marking, hall ticket generation, result publication, document upload, approval workflow, and report generation. These run after every restore to confirm system integrity.

---

## 33. Platform Gap: OBE / CO-PO Mapping (E20)

Outcome-Based Education is mandatory for NBA accreditation. Every course needs Course Outcomes (COs), every program needs Program Outcomes (POs), and every assessment must map to COs.

```sql
CREATE TABLE course_outcomes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    course_id   UUID NOT NULL,
    co_code     TEXT NOT NULL,          -- 'CO1', 'CO2', etc.
    description TEXT NOT NULL,
    bloom_level TEXT NOT NULL           -- 'Remember'|'Understand'|'Apply'|'Analyse'|'Evaluate'|'Create'
);

CREATE TABLE program_outcomes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    program_id  UUID NOT NULL,
    po_code     TEXT NOT NULL,          -- 'PO1' through 'PO12' (NBA standard)
    description TEXT NOT NULL
);

CREATE TABLE co_po_mapping (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    co_id        UUID NOT NULL REFERENCES course_outcomes(id),
    po_id        UUID NOT NULL REFERENCES program_outcomes(id),
    correlation  INTEGER NOT NULL CHECK (correlation IN (1,2,3)),  -- 1=Low,2=Med,3=High
    UNIQUE(co_id, po_id)
);

CREATE TABLE co_attainment_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    co_id           UUID NOT NULL,
    semester        TEXT NOT NULL,
    direct_attainment  DECIMAL(5,2),   -- from exam marks
    indirect_attainment DECIMAL(5,2),  -- from student feedback survey
    final_attainment   DECIMAL(5,2),   -- weighted: 80% direct + 20% indirect
    target_attainment  DECIMAL(5,2),   -- set by department (typically 60%)
    target_met      BOOLEAN GENERATED ALWAYS AS (final_attainment >= target_attainment) STORED
);
```

**AI-assisted CO generation:** When a faculty member creates a new course and uploads the syllabus, the AI generates suggested COs mapped to Bloom's taxonomy. Faculty review and confirm. This removes the blank-page problem that causes CO definition to be done poorly or skipped.

**Attainment computation:** After every exam, CO attainment is automatically computed by mapping each question in the question paper to its COs (set by faculty during paper creation) and aggregating student scores per CO. This feeds directly into the NBA SAR in E14.

---

## Appendix: Updated Scheduled Tasks (Celery Beat)

| Schedule | Task | Module |
|---|---|---|\
| Daily midnight | Academic calendar phase checks | Academics |
| Daily 02:00 | PostgreSQL backup — all tenants | Infrastructure |
| Daily 02:30 | MinIO backup sync | Infrastructure |
| Daily 04:00 | Backup restore verification | Infrastructure |
| Daily 09:00 | Fee overdue detection | Finance |
| Daily 09:05 | Invoice overdue detection | Finance |
| Daily 09:10 | Shadow mode divergence computation | Shadow Mode |
| Daily 09:15 | DPDP consent expiry check | E21 |
| Hourly | Workflow task SLA reminders | Workflow Engine |
| Every 5 min | Failed domain event retry | All |
| Every 30 sec | Financial/exam event retry | Finance, Examinations |
| Daily 00:30 | KPI snapshot generation | Reporting |
| Weekly (Mon) | Publication discovery for faculty | E14/HR |
| Monthly | Scholarship renewal check | Student Services |
| Annual (March 1) | Appraisal cycle initiation | HR |
| Annual (July) | AQAR data compilation draft | Regulatory E14 |

*Document version: 2.0 | March 2026*
*Maintained by: QUAICU Pvt. Ltd. Engineering*
