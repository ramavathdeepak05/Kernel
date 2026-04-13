# ALIS OS — Production Readiness Roadmap

> **Date**: 2026-04-13 | **Prepared for**: QUAICU Solutions
>
> Complete gap analysis and phased roadmap to production.

---

## Executive Summary

| Area | Status | Completion |
|------|--------|:----------:|
| Backend Core Infrastructure | 🟢 Strong |
| Backend Domain Modules | 🟡 Code exists, needs hardening | 
| Frontend Web App | 🟠 Shell done, pages partially built | 
| AI Agents & Gateway | 🟡 Foundation solid, agents partial | 
| Desktop App | 🔴 Non-functional, minimal code | 
| Integrations (3rd party) | 🔴 Mostly stubs | 
| Testing | 🟡 Core covered, modules sparse | 
| DevOps & Deployment | 🟢 Docker + CI exists | 
| Documentation | 🟢 Comprehensive | 

**Overall estimate: ~75% to production**

---

## 1. Backend Core Infrastructure — 🟢 

### What's Done ✅
- 6-layer enforcement model fully implemented
- `db_service.py` — tenant-aware connection pooling (asyncpg + psycopg2)
- `security.py` — bcrypt hashing, Redis sessions, MFA, lockout
- `audit.py` — immutable hash-chain ledger with 40+ action types
- `rbac.py` — 10+ roles, 50+ permissions, `@require_permission()` decorator
- `state_registry.py` — 14-state student state machine
- `locks.py` — 7 global lock types
- `domain_events.py` — DB-backed Celery event bus with retry
- `ai_gateway.py` — prompt injection detection, guardrails, PII masking
- `policy_engine.py` — safe expression evaluator (asteval)
- `policy_service.py` — full lifecycle (DRAFT → ACTIVE)
- `policy_resolver.py` — runtime evaluation with caching
- `tenant_crypto.py` — per-tenant Fernet encryption
- `vault_client.py` — HashiCorp Vault integration
- Celery workers with 3 queues + DLQ
- 41 Alembic migrations

### What's Missing ❌
- [ ] **RBAC injection audit** — some routers may still lack `@require_permission()` on every endpoint
- [ ] **Policy engine testing** — complex rule expressions need edge-case coverage
- [ ] **Lockdown mode E2E test** — lockdown activation → write blocking → recovery flow
- [ ] **Shadow mode cleanup** — `shadow_mode.py` + `shadow_mode_middleware.py` may be dead/unused in production
- [ ] **Backpressure tuning** — `backpressure.py` needs load-testing calibration
- [ ] **API versioning** — v2 routes not wired yet

---

## 2. Backend Domain Modules — 🟡 

### Module-by-Module Status

| Module | Files | Services Built | Gaps |
|--------|:-----:|:--------------:|------|
| **Admissions** | 34 | ✅ Full 10-stage pipeline | Some integration stubs (DigiLocker, NTA) |
| **Academics** | 17 | ✅ Programs, OBE, LMS, timetable, attendance | Missing: course registration workflow, academic calendar triggers |
| **Examinations** | 14 | ✅ Scheduling, grading, reeval, hall tickets, transcripts | Missing: question paper encryption, seating algorithm |
| **Finance** | 19 | ✅ Fees, payments, invoicing, scholarships, Tally export | Missing: bank reconciliation, payment gateway webhooks (partial) |
| **HR** | 16 | ✅ Staff, leave, payroll, recruitment, training | Missing: CAS appraisal scoring, statutory compliance reports |
| **Student Services** | 12 | ✅ Hostel, transport, counselling, library, grievance | Missing: hostel fee auto-linking, transport GPS tracking |
| **Communication** | 9 | ✅ Email, SMS, WhatsApp, announcements | Missing: delivery tracking, template versioning |
| **Alumni** | 10 | ✅ Profiles, placement, job board, drives | Missing: alumni engagement metrics |
| **Reporting** | 9 | ✅ Custom reports, export engine, dashboards | Missing: scheduled report delivery |
| **Process Engine** | 8 | ✅ BPMN definitions, executor, forms | Missing: process versioning, rollback |
| **Regulatory** | 7 | ✅ NAAC, NIRF, AISHE, compliance modules | Missing: auto-export to government portals |
| **PhD** | 3 | 🟡 Registration, plagiarism | Missing: DC meeting management, thesis defense, viva scheduling |
| **Convocation** | 2 | 🟡 Basic service | Missing: seating optimization, certificate bulk generation |
| **Consent** | 3 | ✅ DPDP middleware + service | Needs: consent expiry, re-consent flows |
| **Integrations** | 2 | 🔴 Only LMS sync service | Missing: DigiLocker, NTA, Government portals, Razorpay webhooks |

### Priority Gaps (Critical for Production)
- [ ] **Payment gateway webhook handling** — Razorpay/UPI callback verification
- [ ] **DigiLocker integration** — currently a stub
- [ ] **NTA score fetch** — currently a stub
- [ ] **Bank reconciliation** — finance reporting gap
- [ ] **Scheduled report generation** — Celery beat tasks exist but destinations not configured

---

## 3. Frontend Web App — 🟠 

### What's Done ✅
- Shell architecture: ALISShell, IconNav, PrimaryCanvas, AgentRail
- 9 role-specific dashboards (exist but are lightweight ~4-5KB each)
- Routing: 40+ routes defined in `App.tsx`
- Auth flow: login, session management, token refresh
- State management: Zustand stores (auth, alis, ui)
- Service layer: 13 API service files with `apiFetch()`
- Hooks: 12 React Query hooks per module
- Substantial pages: `AdmissionsPage` (34KB), `AcademicsPage` (34KB), `FinancePage` (33KB), `HRPage` (33KB), `StudentServicesPage` (34KB), `LearningPage` (25KB), `OBEPage` (22KB)
- Design system tokens in `index.css`

### What's Stub/Incomplete ❌

| Page | Size | Status |
|------|:----:|--------|
| `RecruitmentPage.tsx` | 2.5KB | Minimal — just a vacancy list, uses raw `fetch()` |
| `TrainingPage.tsx` | 2.7KB | Minimal stub |
| `BudgetPage.tsx` | 4.8KB | Lightweight stub |
| `VendorsPage.tsx` | 4.5KB | Lightweight stub |
| All 9 Dashboards | ~4-5KB each | Skeleton layouts with mock data, not wired to real APIs |
| `ExaminationsPage` | — | Needs verification |
| `CommunicationHubPage` | — | Needs verification |
| `PhDPage` | — | Needs verification |
| `ConvocationPage` | — | Needs verification |
| `RegulatoryPage` | — | Needs verification |
| `ReportsPage` | — | Needs verification |
| `ConsentPage` | — | Needs verification |
| `ProcessEnginePage` | — | Needs verification |
| `WorkflowsPage` | — | Needs verification |

### Frontend Priority Work
- [ ] **Wire dashboards to real APIs** — replace mock data with React Query hooks
- [ ] **Complete stub pages** — Recruitment, Training, Budget, Vendors
- [ ] **Build missing module pages** — PhDPage, ConvocationPage, CommunicationHubPage, ProcessEnginePage
- [ ] **Student self-service pages** — MyCoursesPage, MyExamsPage, MyFeesPage, MyLibraryPage (verify completeness)
- [ ] **Public portal** — ApplicationWizardPage, OfferLetterPage, ApplicationStatusPage
- [ ] **Mobile responsiveness** — AgentBottomSheet exists, but page layouts need responsive treatment
- [ ] **Error states + loading skeletons** — most pages lack proper loading/error UX
- [ ] **Form validation** — inconsistent, needs Zod/Yup schema validation
- [ ] **Accessibility audit** — ARIA labels, keyboard navigation, screen reader support

---

## 4. AI Agents & Gateway — 🟡 

### What's Done ✅
- `AIGateway` — single entry point with guardrails, PII masking, confidence scoring
- `GuardrailChain` — JSON schema, confidence, sensitive data, profanity filters
- `HITLQueue` — human escalation for low-confidence decisions
- `AIObservabilityTracer` — execution tracing
- `PromptRegistry` — version-controlled prompts
- `ModelRegistry` — model metadata management
- `LLMRouter` — tiered model selection (1.5B/7B/14B)
- `ai_service` microservice (port 8002) — provider routing, PII masking, token budgets
- Agent directories exist for: admissions, academics, examinations, finance, HR, regulatory, research, student_services

### What's Incomplete ❌
- [ ] **Most agent subdirectories are empty/minimal** — only admissions agents are fleshed out
- [ ] **Content Generator (P40)** — exists but needs testing with real course data
- [ ] **Answer Evaluation agent** — guard exists but full pipeline incomplete
- [ ] **HR agents** — hiring recommendation, workload optimization not built
- [ ] **Finance agents** — budget forecasting, anomaly detection not built
- [ ] **Regulatory agents** — NAAC data auto-extraction not built
- [ ] **Agent rail (frontend)** — UI skeleton exists, backend `/ai/invoke` wiring incomplete
- [ ] **Confidence threshold tuning** — need production data to calibrate
- [ ] **Prompt optimization** — prompts exist but need domain expert review

---

## 5. Desktop App — 🔴 

### Current State
- Electron shell with Vite (1 main file: `index.ts`, 1 renderer: `App.tsx`)
- `package.json` exists but dependencies may be out of date
- No build artifacts (cleaned up, previously had stale `release/` dirs)
- Not functional — likely just a shell pointing to the web app

### What's Needed
- [ ] Rebuild Electron wrapper around the web app
- [ ] Investigate offline mode + local sync requirements
- [ ] Connect desktop IPC to local services if required

> **Decision**: We are **keeping** the desktop app. It will require dedicated focus in a subsequent phase after the web app is functional.

---

## 6. Integrations — 🔴 

| Integration | Status | Priority |
|------------|--------|----------|
| **Razorpay payment** | 🟡 Partial — service exists, webhooks incomplete | 🔴 Critical |
| **DigiLocker** | 🔴 Stub only | 🟡 High |
| **NTA Scores** | 🔴 Stub only | 🟡 High |
| **MSG91 SMS** | 🟡 Service exists, delivery tracking missing | 🟡 High |
| **Twilio SMS** | 🟡 Partial | 🟢 Medium |
| **WhatsApp** | 🟡 Service exists (26KB), needs production config | 🟡 High |
| **SMTP Email** | ✅ Working via `NotificationDispatcher` | ✅ Done |
| **MinIO/S3 storage** | ✅ Working via `FSService` | ✅ Done |
| **Ollama LLM** | ✅ Working | ✅ Done |
| **HashiCorp Vault** | ✅ Client working | ✅ Done |
| **Tally ERP export** | 🟡 Service exists, not tested with real Tally | 🟡 High |
| **Government portals** (AISHE, NIRF) | 🔴 Not built | 🟢 Medium |
| **Drillbit plagiarism** | 🟡 Polling task exists, submission flow partial | 🟢 Medium |

---

## 7. Testing — 🟡 

### Current Coverage (49 test files)

| Area | Tests | Status |
|------|:-----:|--------|
| Auth & Security | 3 | ✅ Good |
| Audit Ledger | 2 | ✅ Good |
| AI Gateway | 3 | ✅ Good |
| Admissions (full pipeline) | 8 | ✅ Strong |
| Policy Engine | 2 | ✅ Good |
| Data Classification | 1 | ✅ |
| Integration tests | 7 | 🟡 Broad but shallow |
| Escalation & Lockdown | 2 | ✅ |
| DB & Migrations | 2 | ✅ |
| Domain modules (academics, HR, exams, student svc) | 4 | 🔴 Sparse |
| Finance | 0 | 🔴 Missing |
| Communication | 1 | 🟡 |
| Process Engine | 1 | 🟡 |
| Frontend (React components) | 0 | 🔴 None |

### Testing Gaps (Priority Order)
- [ ] **Finance module tests** — zero tests for the most sensitive module
- [ ] **E2E admissions pipeline test** — full 10-stage flow verification
- [ ] **Frontend component tests** — Vitest + React Testing Library
- [ ] **Load testing** — scripts exist in `infra/loadtest/` but need calibration
- [ ] **Domain module unit tests** — each module needs basic CRUD + event handler tests
- [ ] **API contract tests** — request/response schema validation

---

## 8. DevOps & Deployment — 🟢 

### What's Done ✅
- `docker-compose.yml` — 17 services fully defined
- Dockerfiles for all 3 microservices + frontend
- Nginx reverse proxy with rate limiting
- Prometheus + Grafana + Loki + Alertmanager observability stack
- PgBouncer connection pooling
- GitHub Actions CI (linting)
- `.pre-commit-config.yaml` (Ruff)
- Infrastructure configs: k8s manifests, Terraform, Vault policies

### What's Missing ❌
- [ ] **CD pipeline** — no deployment automation to staging/production
- [ ] **SSL certificate management** — self-signed certs in `nginx/certs/`, need Let's Encrypt
- [ ] **Database backup verification** — backup task exists but restore has never been tested
- [ ] **Monitoring dashboards** — Grafana configs exist but may not have ALIS-specific panels
- [ ] **Health check alerting** — Alertmanager rules need ALIS-specific thresholds
- [ ] **Environment per-PR** — no preview environments

---

## Phased Roadmap

### Phase 1: Foundation Hardening (Weeks 1–3)
> **Goal**: Lock down core + fill critical backend gaps

| Task | Owner | Est. Days |
|------|-------|:---------:|
| RBAC audit — ensure all 29 routers have `@require_permission()` | Backend Intern | 3 |
| Finance module tests (unit + integration) | Backend Intern | 4 |
| Payment gateway webhook verification (Razorpay) | Backend Intern | 3 |
| Wire 9 dashboards to real APIs | Frontend Intern | 5 |
| Complete stub pages (Recruitment, Training, Budget, Vendors) | Frontend Intern | 4 |
| Audit + test existing AI agents (admissions) | AI Intern | 4 |
| Review RBAC + agent confidence thresholds | Senior AI Dev | 2 |
| CI pipeline: add pytest + vitest to GitHub Actions | Senior AI Dev | 2 |

### Phase 2: Module Completion (Weeks 4–7)
> **Goal**: All modules feature-complete

| Task | Owner | Est. Days |
|------|-------|:---------:|
| PhD module completion (DC meetings, thesis, viva) | Backend Intern | 5 |
| Convocation completion (seating, certificates, gold medal) | Backend Intern | 4 |
| DigiLocker integration | Backend Intern | 3 |
| NTA scores integration | Backend Intern | 2 |
| Build missing frontend pages (PhD, Convocation, Communication, ProcessEngine) | Frontend Intern | 8 |
| Student self-service pages — wire to APIs | Frontend Intern | 5 |
| Public portal — ApplicationWizard full flow | Frontend Intern | 5 |
| Build HR agents (hiring recommendation) | AI Intern | 5 |
| Build finance agents (anomaly detection) | AI Intern | 5 |
| Content generation agent E2E testing | AI Intern | 3 |
| E2E admissions pipeline: 10-stage test | Senior AI Dev | 3 |
| Domain module unit tests (academics, HR, student svc) | Senior AI Dev | 4 |

### Phase 3: Integration & Polish (Weeks 8–10)
> **Goal**: All integrations working, UX polished

| Task | Owner | Est. Days |
|------|-------|:---------:|
| SMS/WhatsApp production configuration | Backend Intern | 3 |
| Bank reconciliation service | Backend Intern | 4 |
| Tally ERP export testing with real data | Backend Intern | 2 |
| Mobile responsiveness across all pages | Frontend Intern | 5 |
| Loading skeletons + error states across all pages | Frontend Intern | 4 |
| Form validation (Zod schemas) | Frontend Intern | 4 |
| Agent rail — wire `/ai/invoke` to frontend | AI Intern | 5 |
| Regulatory agents — NAAC data extraction | AI Intern | 4 |
| Prompt optimization with domain expert review | Senior AI Dev | 3 |
| Load testing & backpressure calibration | Senior AI Dev | 3 |

### Phase 4: Production Preparation (Weeks 11–12)
> **Goal**: Deploy-ready

| Task | Owner | Est. Days |
|------|-------|:---------:|
| SSL setup with Let's Encrypt | Senior AI Dev | 1 |
| CD pipeline to staging | Senior AI Dev | 3 |
| Database backup + restore drill | Senior AI Dev | 1 |
| Grafana dashboards for ALIS KPIs | Senior AI Dev | 2 |
| Security audit (penetration testing) | Senior AI Dev | 3 |
| Accessibility audit (WCAG 2.1 AA) | Frontend Intern | 3 |
| UAT with pilot institution | All | 5 |
| Bug fixes from UAT | All | 5 |

---

## Decisions Made

> [!NOTE]
> The following decisions have been confirmed and integrated into this roadmap:

1. **Desktop app** — **Keep**. We will maintain and rebuild the Electron app.
2. **External integrations priority** — **Needed**. DigiLocker and NTA integrations will be built.
3. **Pilot institution** — **TBD**. We will decide later depending on readiness.
4. **Government portal integration** — **Manual Export**. NAAC/NIRF auto-submission is not needed for v1.
5. **Mobile app** — **Yes**, it is on the radar. A dedicated mobile track will be planned later.

---

## Team Velocity Assumptions

| Role | Available Hours/Week | Effective Output |
|------|:-------------------:|:----------------:|
| Backend Intern | 40h | ~30h productive |
| Frontend Intern | 40h | ~30h productive |
| AI Agents Intern | 40h | ~25h productive (learning curve) |
| Senior AI Dev | 40h | ~35h productive (reviews + coding) |

**Total team capacity**: ~120 productive hours/week
**Estimated total effort**: ~450–550 hours
**Estimated timeline**: **10–12 weeks** to production-ready (with full team)
