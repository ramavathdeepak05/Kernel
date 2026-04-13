# ALIS OS — Complete Codebase Map

> **Version**: 1.0 | **Date**: 2026-04-13 | **Audience**: All team members
>
> This is the **single source of truth** for understanding the codebase structure. Every folder and key file is documented with its purpose, dependencies, connections, and rules.

---

## Quick Reference

| What | Where |
|------|-------|
| Main backend API | `ALIS/server/main.py` → port 8000 |
| Frontend React app | `web/src/App.tsx` → port 5173 (dev) |
| AI inference service | `ai_service/main.py` → port 8002 |
| SaaS control plane | `control_plane/main.py` → port 8001 |
| Database migrations | `ALIS/migrations/versions/` |
| Docker orchestration | `docker-compose.yml` |
| Environment config | `.env` (from `.env.example`) |
| CI/CD workflows | `.github/workflows/` |

---

## Repository Root

```
ALIS Production/
├── ALIS/                    # 🔵 Backend data plane (FastAPI + Celery)
├── web/                     # 🟢 Frontend React SPA
├── ai_service/              # 🟠 Centralized AI inference microservice
├── control_plane/           # 🟣 SaaS tenant management microservice
├── desktop/                 # ⚪ Electron desktop app (experimental)
├── infra/                   # 🔧 Infrastructure configs (k8s, terraform, monitoring)
├── nginx/                   # 🔧 Reverse proxy configuration
├── docs/                    # 📄 Documentation
├── scripts/                 # 🛠️ Dev tools & analysis scripts
├── specs/                   # 📋 Architecture skill specs
├── .agents/                 # 🤖 AI agent skills & workflows
├── .github/                 # ⚙️ CI/CD workflows
├── .code-review-graph/      # 📊 Generated dependency analysis (gitignored)
│
├── CONTRIBUTING.md          # Team contribution rules
├── README.md                # Project overview
├── AGENTS.md                # AI coding agent instructions
├── CLAUDE.md                # Claude agent config
├── GEMINI.md                # Gemini agent config
├── docker-compose.yml       # Full stack orchestration (17 services)
├── docker-compose.override.yml  # Local dev overrides
├── .env.example             # Environment variable template
├── .env.production          # Production env template
├── .gitignore               # Git ignore rules
└── .pre-commit-config.yaml  # Pre-commit hooks (Ruff)
```

---

## 1. Backend — `ALIS/` (Data Plane)

The main FastAPI application. Handles all business logic, API endpoints, background tasks, and database operations.

**Owner**: Backend Intern + Senior AI Dev

### 1.1 Root Files

| File | Purpose | Depends On | Depended By |
|------|---------|------------|-------------|
| `server/main.py` | FastAPI app factory. Mounts 29+ routers, registers 8 middleware, exposes `/health`, `/ready`, `/metrics`. Manages asyncpg pool via lifespan. | `core/settings`, `core/security`, `core/audit`, `db_service`, all routers | Uvicorn, Docker, Nginx |
| `server/db_service.py` | Tenant-aware DB access layer. Per-tenant asyncpg + psycopg2 pools. Enforces tenant isolation via `SET alis.current_tenant`. | `core/settings`, `core/tenant_registry` | Every service, every router |
| `server/worker.py` | Celery app with 3 queues (default, high_priority, dead_letter). Registers domain event handlers at startup. | `core/settings`, `core/tenant_tasks`, all task modules | Docker, Celery Beat |
| `server/fs_service.py` | MinIO-backed file storage (upload, download, delete, presigned URLs). | `core/settings` | Document services, admissions |
| `Dockerfile` | Container build for backend | `requirements.txt` | `docker-compose.yml` |
| `requirements.txt` | Python dependencies (FastAPI, asyncpg, celery, etc.) | — | `Dockerfile`, pip |
| `alembic.ini` | Alembic migration config | — | `alembic` CLI |

### 1.2 Core Infrastructure — `server/core/` (55 files)

> **Rule**: This is the foundation layer. Changes here affect the entire system. **All core changes require Senior AI Dev review.**

#### Authentication & Security

| File | Purpose | Key Exports |
|------|---------|-------------|
| `security.py` | Password hashing (bcrypt), session management (Redis-backed), failed login tracking, account lockout, MFA challenge flow | `PasswordHasher`, `create_session()`, `get_session()`, `revoke_session()` |
| `mfa_service.py` | TOTP-based MFA enrollment, verification, backup codes. Secrets encrypted via Fernet + Vault. | `MFAService.enroll_device()`, `MFAService.verify_totp()` |
| `lockdown.py` | Incident response — blocks all writes and AI invocations system-wide | `activate_lockdown()`, `deactivate_lockdown()` |
| `escalation.py` | Temporary privilege elevation with time limits and audit trail | `EscalationManager`, `DualControlManager` |
| `overrides.py` | Policy exception handling — request → approve → execute with full audit | `OverrideApprovalManager` |

#### Authorization (RBAC)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `rbac.py` | 10+ roles, 50+ permissions, default-deny. Context-aware authorization. | `Role` enum, `Permission` enum, `verify_access()`, `@require_permission()` |
| `approvals.py` | Multi-approver workflows: SINGLE (any 1), ANY (N of M), ALL | `ApprovalManager.request_approval()`, `.approve()` |

> **Rule**: Every API endpoint MUST have `@require_permission()` — no unprotected routes.

#### AI Governance

| File | Purpose | Key Exports |
|------|---------|-------------|
| `ai_gateway.py` | **Single entry point for ALL AI calls.** Enforces prompt injection detection, JSON schema validation, STATE_IMPACT check, confidence scoring, PII masking. | `AIGateway.invoke()` |
| `guardrails.py` | Post-LLM output validation chain (JSON schema, confidence threshold, sensitive data, profanity) | `GuardrailChain` |
| `hitl.py` | Human-in-the-loop escalation queue for low-confidence AI decisions | `HITLQueue.enqueue()`, `.approve()`, `.reject()` |
| `ai_observability.py` | Traces agent execution with timing, tool calls, decisions | `AIObservabilityTracer` |
| `ai_providers.py` | Pluggable AI provider interface (Ollama, OpenAI) | `OllamaProvider`, `OpenAIProvider` |
| `ai_service_provider.py` | Routes AI calls to the external AI service (port 8002) | `AIServiceProvider` |
| `llm_router.py` | Tiered model selection: extraction (1.5B), generation (7B), reasoning (14B) | `LLMRouter.select_model()` |
| `prompt_registry.py` | Version-controlled prompt templates with variable resolution | `PromptRegistry.get()`, `.resolve()` |
| `model_registry.py` | AI model metadata (name, provider, cost, capabilities) | `ModelRegistry` |
| `tool_registry.py` | Registry of tools available to AI agents. Schema validation on tool calls | `ToolRegistry` |
| `policy_authoring_agent.py` | AI co-author for policy drafting | — |

> **Rule**: AI agents MUST output `DRAFT` or `PROVISIONAL` only — never `FINAL`, `COMMIT`, or `OVERRIDE`.

#### State Machines & Events

| File | Purpose | Key Exports |
|------|---------|-------------|
| `state_registry.py` | Central state machine validation. `StudentState` has 14 states | `StateRegistry.validate_transition()` |
| `locks.py` | Global invariant enforcement. 7 lock types prevent invalid cross-module operations | `check_global_locks()`, `LockType` |
| `domain_events.py` | DB-backed, Celery-dispatched cross-module event bus. Events persisted first, then dispatched | `DomainEventBus.publish()`, `.subscribe()` |
| `events.py` | In-process pub/sub for local signaling | `EventBus.subscribe()`, `.publish()` |
| `workflow.py` | Abstract base for ALIS wizards (check locks → approval → execute → transition) | `BaseWorkflow` |
| `workflow_schema.py` | Pydantic models for workflow context | `WorkflowContext` |

> **Rule**: State transitions MUST go through `StateRegistry` — no raw status column updates. Modules communicate ONLY via Domain Events.

#### Policy Engine

| File | Purpose | Key Exports |
|------|---------|-------------|
| `policy_engine.py` | Safe expression evaluator using `asteval` (replaces `eval()`) | `PolicyEngine.evaluate()` |
| `policy_service.py` | Policy lifecycle: DRAFT → SUBMITTED → APPROVED → ACTIVE | `PolicyService` |
| `policy_store.py` | Policy persistence layer | `PolicyStore` |
| `policy_resolver.py` | Runtime policy evaluation + caching | `PolicyResolver` |

#### Data Governance

| File | Purpose | Key Exports |
|------|---------|-------------|
| `data_classification.py` | Sensitivity levels (PUBLIC → REGULATED), data type tags (PII, FINANCE, BIOMETRIC) | `SensitivityLevel`, `DataClassifier` |
| `diff_tracker.py` | Field-level change tracking with audit trail | `DiffTracker` |
| `retention_policy.py` | Data lifecycle: archival or hard-delete after retention period | `RetentionPolicyManager` |
| `tenant_crypto.py` | Per-tenant Fernet encryption (AES-128-CBC). Keys from Vault. | `TenantCrypto.encrypt()`, `.decrypt()` |

#### Audit & Observability

| File | Purpose | Key Exports |
|------|---------|-------------|
| `audit.py` | **Immutable, append-only audit ledger** with SHA-256 hash chaining. 40+ audit actions. DB triggers block UPDATE/DELETE/TRUNCATE. | `AuditLog.log()`, `AuditLog.verify_chain()` |
| `metrics.py` | Prometheus counters: HTTP requests, duration, domain events | `generate_latest()` |
| `exceptions.py` | Exception hierarchy: `ALISError` → `BusinessRuleViolation`, `IllegalStateTransitionError`, etc. | All exception classes |
| `error_handlers.py` | Global FastAPI exception handlers → JSON error responses | `register_exception_handlers()` |

> **Rule**: Every database mutation MUST be followed by `AuditLedger.log()`.

#### Configuration & Multi-Tenancy

| File | Purpose | Key Exports |
|------|---------|-------------|
| `settings.py` | Pydantic `BaseSettings` — all infrastructure config from `.env` | `Settings` singleton |
| `config.py` | Institution-specific business policies (separate from infra) | `ConfigRegistry` |
| `feature_flags.py` | Percentage-based rollout, org-specific toggles | `FeatureFlagRegistry` |
| `tenant_registry.py` | Resolves per-tenant DB config from control plane or local fallback | `TenantRegistry` |
| `tenant_tasks.py` | Routes Celery tasks to per-tenant queues | `TenantTaskRouter` |
| `vault_client.py` | HashiCorp Vault KV v2 client. AppRole auth. Per-tenant secret paths | `VaultClient` |

#### Other Core

| File | Purpose |
|------|---------|
| `models.py` | Canonical entities: `User`, `Organization`, `ActorType`, `BaseEntity` |
| `schema.py` | Base `Event` model for EventBus |
| `campus_service.py` | Multi-campus location management |
| `api_versioning.py` | API v1/v2 versioning with deprecation headers |
| `shadow_mode.py` | Dual-write testing mode for shadow DB comparison |
| `shadow_mode_middleware.py` | Middleware wrapper for shadow mode |
| `webhook_dispatcher.py` | Outbound webhooks with retry + idempotency |
| `backup_service.py` | Daily database backups to MinIO/S3 |
| `backpressure.py` | Request backpressure / rate limiting |
| `perf.py` | Performance optimization utilities |
| `request_context.py` | Request-scoped context (current user, tenant) |
| `tasks.py` | Core Celery task definitions |
| `notifications/` | Multi-channel notification dispatcher (Email/SMS/WhatsApp) |
| `documents/` | HTML → PDF generation via ReportLab |

---

### 1.3 Domain Modules

Each module is a self-contained business domain. Modules communicate ONLY through Domain Events.

> **Rule**: Never import directly from one module into another. Use `DomainEventBus.publish()`.

#### `server/admissions/` — 34 files, 10-Stage Pipeline

| File | Stage | Purpose |
|------|-------|---------|
| `lead_service.py` | 1 | Lead acquisition, consultant tracking, referral codes |
| `counsellor_service.py` | 1 | Counsellor CRUD + PGVector ETL trigger |
| `counsellor_allocation.py` | 1 | AI vector search or load-balanced allocation |
| `deduplication.py` | 1 | Email/phone/name fuzzy match dedup |
| `deduplication_service.py` | 1 | Extended deduplication logic |
| `application_form.py` | 2 | Multi-step wizard (6 sub-forms) |
| `document_verification.py` | 3 | Upload, verify, AI-assisted check |
| `forgery_detection.py` | 3 | AI-powered document forgery detection |
| `identity_match.py` | 3 | EC-ADM-01 identity matching |
| `eligibility_service.py` | 4 | Evaluate applicant eligibility |
| `eligibility_criteria.py` | 4 | Define criteria per program |
| `policy_engine.py` | 4 | Admissions-specific policy rules |
| `entrance_test.py` | 5A | Test scheduling, registration, scoring |
| `interview.py` | 5B | Panel management, scheduling, scorecards |
| `merit_list.py` | 6 | Merit ranking + seat matrix |
| `seat_matrix_service.py` | 6 | Seat availability management |
| `offer_letter.py` | 7 | PDF generation + notification |
| `confirmation.py` | 8 | Seat accept/decline |
| `payment_v2.py` | 8 | Demand drafts, refund requests |
| `final_verification.py` | 9 | Pre-enrollment checklist |
| `enrollment_provisioning.py` | 10 | Student ID, LMS sync, hostel, library |
| `enrollment_handover.py` | 10 | Transition to academics module |
| `readmission_service.py` | — | Returning student workflow |
| `credit_transfer_service.py` | — | Cross-institution credit transfer |
| `intake_quality.py` | — | Batch-level quality metrics |
| `review_queue.py` | — | Manual review for borderline cases |
| `reporting_gate.py` | — | Regulatory reporting |
| `automation_pipeline.py` | — | Orchestrates all stages via domain events |
| `admissions_templates.py` | — | 25+ email/SMS templates |
| `event_handlers.py` | — | Domain event subscriptions |
| `models.py` | — | 20+ Pydantic models, `ApplicantStatus` (14 states) |
| `service.py` | — | Core admissions service facade |
| `policy_store.py` | — | Admissions policy persistence |
| `integrations/` | — | DigiLocker, NTA, Razorpay, SMS, email, doc storage, LMS |

#### Other Domain Modules

| Module | Path | Files | Purpose |
|--------|------|-------|---------|
| **Academics** | `server/academics/` | programs, OBE, TA assignment, learning, timetable, attendance | Programs, courses, OBE (CO-PO mapping), in-house LMS |
| **Examinations** | `server/examinations/` | scheduling, grading, reeval | Exam management, hall tickets, results, AI answer eval |
| **Finance** | `server/finance/` | 19 files | Fee structures, invoices, payments, scholarships, waivers, e-invoicing, Tally export, tax, budget, vendor purchasing |
| **HR** | `server/hr/` | staff, leave, payroll, performance | Staff profiles, leave management, payroll, reviews |
| **Student Services** | `server/student_services/` | hostel, transport, counselling, library | Accommodation, transport routes, counselling sessions |
| **Communication** | `server/communication/` | templates, WhatsApp | Multi-channel notifications, bulk messaging |
| **Reporting** | `server/reporting/` | models, analytics | Saved reports, export jobs, KPI snapshots |
| **Alumni** | `server/alumni/` | profiles, placements | Alumni profiles, job board, recruitment drives |
| **Process Engine** | `server/process_engine/` | definition, executor, forms | Dynamic BPMN-like workflows |
| **Consent** | `server/consent/` | middleware | DPDP Act 2023 consent tracking |
| **Regulatory** | `server/regulatory/` | models | NAAC, NIRF, AISHE, UGC compliance |
| **PhD** | `server/phd/` | — | Doctoral programs, milestones, thesis |
| **Convocation** | `server/convocation/` | — | Degree audits, seating, gold medals, certificates |

---

### 1.4 AI Agents — `server/agents/`

| Subdirectory | Agent Type | Purpose |
|-------------|-----------|---------|
| `admissions/` | Eligibility, Document Verification, Counsellor Recommendation, Merit List | Admissions pipeline AI |
| `academics/` | Content Generator | LMS content generation |
| `examinations/` | Answer Evaluation | AI-assisted grading |
| `finance/` | Financial analysis agents | — |
| `hr_admin/` | HR decision support | — |
| `regulatory/` | Compliance analysis | — |
| `research/` | Research support | — |
| `student_services/` | Student support agents | — |
| `rail/` | Agent rail (frontend AI panel) | — |

> **Rule**: All agents route through `AIGateway` → guardrails → audit → HITL if low confidence.
>
> **Owner**: AI Agents Intern + Senior AI Dev

---

### 1.5 API Routers — `server/api/` (31 files)

| Router | Prefix | Connects To |
|--------|--------|-------------|
| `auth_router.py` | `/auth` | `core/security`, `core/mfa_service` |
| `users_router.py` | `/users` | `core/models`, `core/rbac` |
| `roles_router.py` | `/roles` | `core/rbac` |
| `organizations_router.py` | `/organizations` | `core/models` |
| `admissions_router.py` | `/admissions` | `admissions/*` (largest router: 91KB) |
| `academics_router.py` | `/academics` | `academics/*` |
| `examinations_router.py` | `/examinations` | `examinations/*` |
| `finance_router.py` | `/finance` | `finance/*` |
| `hr_router.py` | `/hr` | `hr/*` |
| `student_services_router.py` | `/student-services` | `student_services/*` |
| `communication_router.py` | `/communications` | `communication/*` |
| `reporting_router.py` | `/reports` | `reporting/*` |
| `alumni_router.py` | `/alumni` | `alumni/*` |
| `process_engine_router.py` | `/process-engine` | `process_engine/*` |
| `learning_router.py` | `/learning` | `academics/learning_service` |
| `phd_router.py` | `/phd` | `phd/*` |
| `convocation_router.py` | `/convocation` | `convocation/*` |
| `regulatory_router.py` | `/regulatory` | `regulatory/*` |
| `consent_router.py` | `/consent` | `consent/*` |
| `policy_router.py` | `/policies` | `core/policy_service` |
| `approvals_router.py` | `/approvals` | `core/approvals` |
| `audit_router.py` | `/audit` | `core/audit` |
| `gateway_router.py` | `/ai` | `core/ai_gateway` |
| `workflows_router.py` | `/workflows` | `core/workflow` |
| `feature_flags_router.py` | `/feature-flags` | `core/feature_flags` |
| `admin_router.py` | `/admin` | `core/shadow_mode`, webhooks |
| `intake_router.py` | `/intake` | Public intake form |
| `wifi_attendance_router.py` | `/wifi-attendance` | Passive WiFi attendance |
| `ai_providers_router.py` | `/ai-providers` | `core/ai_providers` |
| `integrations_router.py` | `/integrations` | External service integrations |

---

### 1.6 Celery Tasks — `server/tasks/` (16 files)

| File | Key Tasks | Schedule |
|------|-----------|----------|
| `notifications.py` | `send_email()`, `send_sms()` | On-demand |
| `ai_tasks.py` | `verify_document_ai()`, `score_eligibility_ai()` | On-demand |
| `events.py` | `dispatch_domain_event()` | On-demand + retry |
| `admissions.py` | `run_automation_step()`, `generate_merit_list_async()` | On-demand |
| `finance.py` | `process_monthly_payroll()`, `charge_overdue_fees()` | Monthly / Daily |
| `reporting.py` | `generate_report_async()`, `export_to_excel()` | On-demand |
| `calendar.py` | `trigger_academic_calendar_event()` | Calendar-based |
| `backup.py` | `backup_database_daily()` | Daily |
| `shadow_divergence.py` | `detect_shadow_divergences()` | Nightly |
| `webhook_retry.py` | `retry_failed_webhooks()` | Every 5m |
| `plagiarism_poll.py` | `poll_plagiarism_results()` | Hourly |
| `learning_tasks.py` | `close_overdue_assignments()` | Hourly |
| `lms_sync.py` | LMS enrollment sync | On-demand |
| `partition_mgmt.py` | DB partition management | Scheduled |
| `perf_tasks.py` | Performance monitoring tasks | Scheduled |

---

### 1.7 Database Migrations — `ALIS/migrations/versions/`

41 migration files (0001–0041). Key milestones:

| Range | What It Creates |
|-------|----------------|
| 0001 | Core: users, orgs, roles, audit_ledger, domain_events |
| 0002 | Admissions: applicants, documents, counsellors, offers |
| 0003–0007 | Academics, Exams, Finance, HR, Student Services |
| 0008–0011 | Communication, Reporting, Alumni, Process Engine |
| 0014 | Full admissions 10-stage pipeline (40+ tables) |
| 0017–0021 | Regulatory, Consent, MFA, Idempotency |
| 0025–0030 | Workflows, OBE, Multi-Campus, Custom Roles |
| 0033–0041 | PhD, Convocation, LMS, Compliance fixes |

---

## 2. Frontend — `web/`

React 19 + TypeScript + Vite + Tailwind CSS v4 single-page application.

**Owner**: Frontend Intern

### 2.1 Entry & Config

| File | Purpose |
|------|---------|
| `index.html` | Root HTML shell. Preconnects Google Fonts. |
| `src/main.tsx` | React entry point. Renders `<App />` in `StrictMode`. |
| `src/App.tsx` | Central router (React Router 7). 40+ routes. `QueryClientProvider` + `ErrorBoundary`. |
| `src/index.css` | Full design system: ALIS Green accent, typography, glassmorphism, animations |
| `vite.config.ts` | Vite 6 config. React + Tailwind plugins. PWA + path alias `@` → `./src`. Proxy `/api` → port 8000. |
| `package.json` | Dependencies: React 19, React Router, Zustand, TanStack Query, Radix UI, Lucide icons |

### 2.2 State Management — `src/store/`

| File | Purpose | Used By |
|------|---------|---------|
| `authStore.ts` | Zustand: `isAuthenticated`, `user`, `token` in `sessionStorage` | All protected routes |
| `alis.store.ts` | Zustand: canvas state, agent rail state, UI sync | Shell components |
| `uiStore.ts` | Zustand: UI preferences | Shell |

### 2.3 Shell — `src/shell/` + `src/components/shell/`

| Component | Purpose |
|-----------|---------|
| `ALISShell.tsx` | 3-column layout: 56px nav ∣ flex-1 canvas ∣ 320px agent rail |
| `IconNav.tsx` | Collapsible left sidebar (52px → 200px on hover). Role-filtered nav items. |
| `PrimaryCanvas.tsx` | `<Outlet />` host. Updates canvas store on route change. |
| `AgentRail/AgentRail.tsx` | Right sidebar for AI context advisor |
| `AgentRail/ChatThread.tsx` | Message history (capped 50) |
| `AgentRail/ChatInput.tsx` | User input textarea |
| `AgentRail/QuickActions.tsx` | Context-aware action chips per role |
| `AgentBottomSheet.tsx` | Mobile: 50vh bottom sheet on FAB tap |

### 2.4 Pages — `src/pages/` (24 directories)

| Category | Directory | Key Pages |
|----------|-----------|-----------|
| Auth | `auth/` | `LoginPage` |
| Dashboards | `dashboards/` | 9 role-specific dashboards (SuperAdmin, Registrar, Dean, HOD, Faculty, Student, Finance, CoE, HR) |
| Admissions | `admissions/` | `AdmissionsPage`, `ReadmissionPage`, `SeatMatrixPage` |
| Academics | `academics/` | `AcademicsPage`, `OBEPage`, `LearningPage` |
| Examinations | `examinations/` | `ExaminationsPage` |
| Finance | `finance/` | `FinancePage`, `BudgetPage`, `VendorsPage` |
| HR | `hr/` | `HRPage`, `RecruitmentPage`, `TrainingPage` |
| Student Self | `student/` | `MyCoursesPage`, `MyExamsPage`, `MyFeesPage`, `MyLibraryPage` |
| Admin | `admin/` | `OnboardingWizardPage`, `PolicyStudioPage`, `TeamManagementPage` |
| Portal | `portal/` | `PortalHomePage`, `ApplicationWizardPage`, `OfferLetterPage` |

### 2.5 Hooks — `src/hooks/` (12 files)

| Hook | Purpose |
|------|---------|
| `useALISRole.ts` | Maps backend role → `ALISRole` enum. Returns role, modules, density. |
| `useAgentContext.ts` | Fires proactive backend context query on view change |
| `useAgentCanvasSync.ts` | Syncs agent `CanvasAction`s to UI |
| `useQuickActions.ts` | Context-aware quick action chips per view + role |
| `use-admissions.ts` | React Query hooks for all admissions data |
| `use-academics.ts` | React Query hooks for academic data |
| `use-examinations.ts` | React Query hooks for exam data |
| `use-finance.ts` | React Query hooks for finance data |
| `use-hr.ts` | React Query hooks for HR data |
| `use-alumni.ts` | React Query hooks for alumni data |
| `use-communication.ts` | React Query hooks for communication data |
| `use-reporting.ts` | React Query hooks for reports |

### 2.6 Services — `src/services/` (13 files)

API service clients. Every file uses `apiFetch()` — never raw `fetch()`.

| Service | Backend Prefix |
|---------|---------------|
| `auth.ts` | `/auth` |
| `admissions.ts` | `/admissions` |
| `academics.ts` | `/academics` |
| `examinations.ts` | `/examinations` |
| `finance.ts` | `/finance` |
| `hr.ts` | `/hr` |
| `alumni.ts` | `/alumni` |
| `communication.ts` | `/communications` |
| `learning.ts` | `/learning` |
| `reporting.ts` | `/reports` |
| `regulatory.ts` | `/regulatory` |
| `student-services.ts` | `/student-services` |
| `guardian.ts` | `/guardian` |

### 2.7 Shared Components — `src/components/`

| Component | Purpose |
|-----------|---------|
| `DataTable.tsx` | TanStack Table data grid |
| `StatCard.tsx` | Dashboard KPI card |
| `Badge.tsx` | Status badge |
| `ApprovalRow.tsx` | Approval queue item |
| `RiskBar.tsx` | Visual risk indicator |
| `SLABar.tsx` | SLA deadline bar |
| `PermissionPicker.tsx` | Role/permission selector |
| `CampusSwitcher.tsx` | Multi-campus selector |
| `RoleSwitch.tsx` | Role toggling |
| `UndoToast.tsx` | Toast with undo |
| `TAAssignmentPanel.tsx` | TA assignment UI |
| `TimelinePanel.tsx` | Activity timeline |
| `ErrorBoundary.tsx` | React error boundary |
| `ui/` | Tabs, progress, text reveal, popover, stepper |
| `dashboard/` | `RoleDashboard.tsx` — switches by role |
| `layout/` | `Header.tsx`, `ChatPanel.tsx` |

---

## 3. AI Service — `ai_service/`

Centralized AI inference microservice (port 8002). Handles model routing, PII masking, and token budgets.

**Owner**: Senior AI Dev

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app with health check |
| `router.py` | `/v1/generate`, `/v1/embed`, `/v1/models` endpoints |
| `providers.py` | Multi-provider support: Ollama (local), OpenAI, Azure, AWS Bedrock |
| `pii_masker.py` | PII detection and masking (SSN, Aadhaar, email, phone) before LLM |
| `budget.py` | Per-tenant monthly token budget tracking via Redis |
| `models.py` | Request/response Pydantic models |
| `settings.py` | AI service configuration |

---

## 4. Control Plane — `control_plane/`

SaaS tenant lifecycle management (port 8001). Provisions new institutions, manages billing, DNS, and storage.

**Owner**: Senior AI Dev only

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app |
| `router.py` | Tenant CRUD, billing, DNS, bucket provisioning endpoints |
| `provisioner.py` | Full tenant provisioning pipeline |
| `billing_engine.py` | Plan management, usage tracking, invoicing |
| `dns_manager.py` | Cloudflare, Route53, Azure DNS management |
| `bucket_provisioner.py` | S3/MinIO bucket provisioning per tenant |
| `repository.py` | Tenant data access layer |
| `db.py` | Control plane database service |
| `vault_client.py` | Secrets management for tenant credentials |
| `plan_store.py` | Billing plan persistence |
| `usage_store.py` | Usage metrics persistence |
| `crypto.py` | Control plane encryption utilities |

---

## 5. Infrastructure — `infra/`

| Directory | Purpose |
|-----------|---------|
| `k8s/` | Kubernetes manifests for production deployment |
| `terraform/` | Infrastructure-as-code for cloud provisioning |
| `monitoring/` | Prometheus rules, Grafana dashboards, alert configs |
| `nginx/` | Nginx configuration templates |
| `vault/` | HashiCorp Vault policies and setup |
| `backup/` | Backup scripts and schedules |
| `loadtest/` | Load testing scripts and configs |

---

## 6. Documentation — `docs/`

| File/Directory | Purpose |
|---------------|---------|
| `ALIS_SYSTEM_DOCUMENTATION.md` | Complete system documentation (2000+ lines) |
| `ALIS_FRONTEND_SPEC.md` | Frontend rebuild specification |
| `CODEBASE_MAP.md` | **This file** — annotated directory tree |
| `ONBOARDING.md` | New team member setup guide |
| `api-versioning.md` | API version strategy |
| `vault-degradation-runbook.md` | Vault failure recovery |
| `architecture/` | Architecture diagrams + overview |
| `build/` | Build plans and engineering guidelines |
| `runbooks/` | Operational runbooks (restore, SSL) |
| `archive/` | Legacy documentation |

---

## 7. Developer Scripts — `scripts/`

| File | Purpose | Safe to Run? |
|------|---------|-------------|
| `lint_alis.py` | Custom ALIS architectural linter | ✅ Read-only |
| `load_mockdata.py` | Seed mock development data | ⚠️ Mutates DB |
| `generate_module_graph.py` | Generate dependency graph HTML | ✅ Read-only |
| `analyze_graph.py` | Analyze code-review graph DB | ✅ Read-only |
| `find_bugs_graph.py` | Find bugs via dependency analysis | ✅ Read-only |
| `dump_db_schema.py` | Dump current DB schema | ✅ Read-only |
| `inspect_db.py` | Quick DB inspection utility | ✅ Read-only |
| `violation_details.py` | Show architectural violation details | ✅ Read-only |
| `alis_lint/` | Custom lint rules package | — |

---

## 8. Dependency Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  Nginx (:80/:443)                                                │
│  Rate limits → SSL termination → reverse proxy                   │
└────────────────────┬─────────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
  ┌───────────────┐    ┌───────────────┐
  │  Frontend     │    │  Data Plane   │◄──── Celery Workers
  │  React (:5173)│───▶│  FastAPI(:8000)│      (background jobs)
  └───────────────┘    └───────┬───────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │ AI Service   │ │ Control Plane│ │ Data Stores  │
     │ FastAPI(:8002)│ │ FastAPI(:8001)│ │ PG/Redis/    │
     └──────┬───────┘ └──────────────┘ │ MinIO/Vault  │
            │                          └──────────────┘
            ▼
     ┌──────────────┐
     │ Ollama       │
     │ Local LLM    │
     │ (:11434)     │
     └──────────────┘
```

---

## 9. File Ownership Matrix

| Directory | AI Intern | Backend Intern | Frontend Intern | Senior AI Dev |
|-----------|:---------:|:--------------:|:---------------:|:-------------:|
| `ALIS/server/agents/` | ✅ Write | ❌ | ❌ | ✅ Review |
| `ALIS/server/core/ai_*` | 👀 Read | ❌ | ❌ | ✅ Write |
| `ALIS/server/core/` (other) | 👀 Read | 👀 Read | ❌ | ✅ Write |
| `ALIS/server/api/` | ❌ | ✅ Write | ❌ | ✅ Review |
| `ALIS/server/<modules>/` | ❌ | ✅ Write | ❌ | ✅ Review |
| `ALIS/server/tasks/` | ❌ | ✅ Write | ❌ | ✅ Review |
| `ALIS/migrations/` | ❌ | ✅ Write | ❌ | ✅ Review |
| `web/src/` | ❌ | ❌ | ✅ Write | ✅ Review |
| `ai_service/` | 👀 Read | ❌ | ❌ | ✅ Write |
| `control_plane/` | ❌ | ❌ | ❌ | ✅ Write |
| `infra/` | ❌ | ❌ | ❌ | ✅ Write |
| `docs/` | ✅ Write | ✅ Write | ✅ Write | ✅ Write |

**Legend**: ✅ Write = can modify | 👀 Read = read-only for reference | ❌ = don't touch

---

## 10. Critical Rules Summary

### 🔴 Never Do

1. **Never push directly to `main` or `develop`**
2. **Never use `float` for money** — always `Decimal(12,2)`
3. **Never call LLM directly** — always through `AIGateway.invoke()`
4. **Never import across domain modules** — use Domain Events
5. **Never skip `AuditLedger.log()` after a write**
6. **Never skip `@require_permission()` on endpoints**
7. **Never use raw `fetch()` in frontend** — use `apiFetch()`
8. **Never commit `.env`, secrets, or build artifacts**

### 🟢 Always Do

1. **Always branch from `develop`**
2. **Always run lint before committing** (`ruff check` / `eslint`)
3. **Always scope queries by `org_id`** (tenant isolation)
4. **Always use `StateRegistry` for state transitions**
5. **Always add audit logging for mutations**
6. **Always request code review from Senior AI Dev**
