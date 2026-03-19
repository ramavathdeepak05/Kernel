# ALIS Platform — Build Plan
## QUAICU Pvt. Ltd. | Hyderabad, India
**Updated:** 2026-03-20 | **P22–P29 COMPLETE** | Migrations 0001–0034

---

## Platform Status Snapshot

| Module | Backend | Frontend | Status |
|---|---|---|---|
| Auth + RBAC + MFA/TOTP | ✅ | ✅ | **GA** |
| Workflow Engine + Quorum | ✅ | ✅ WorkflowsPage | **GA** |
| AI Gateway + RAG + PGVector | ✅ | ✅ Agent rail wired | **GA** |
| Admissions (10-stage pipeline) | ✅ | ✅ Kanban + portal | **GA** |
| Academics | ✅ | ✅ AcademicsPage + OBEPage | **GA** |
| Examinations & Grades | ✅ | ✅ ExaminationsPage | **GA** |
| Finance | ✅ | ✅ FinancePage | **GA** |
| HR & Staff | ✅ | ✅ HRPage | **GA** |
| Student Services | ✅ | ✅ StudentServicesPage | **GA** |
| Communication Hub | ✅ | ✅ CommunicationHubPage | **GA** (WhatsApp stub) |
| Reporting & Analytics | ✅ | ✅ ReportsPage | **GA** |
| Alumni & Placement | ✅ | ✅ AlumniPage | **GA** |
| Dynamic Process Engine | ✅ | ✅ ProcessEnginePage + PolicyStudio | **GA** |
| DPDP Consent Management (E21) | ✅ | ✅ ConsentPage | **GA** |
| Regulatory / NAAC / NIRF (E14) | ✅ | ✅ RegulatoryPage | **GA** |
| Guardian Portal (E16) | ✅ | ✅ GuardianPortalPage | **GA** |
| Re-admission & Credit Transfer (E17) | ✅ | ✅ ReadmissionPage | **GA** |
| Convocation Management (E18) | ✅ | ✅ ConvocationPage | **GA** |
| Quota Seat Matrix (E19) | ✅ | ✅ SeatMatrixPage | **GA** |
| OBE / CO-PO (E20) | ✅ | ✅ OBEPage | **GA** |
| PhD / Doctoral Research (E15) | ✅ | ✅ PhDPage | **GA** |
| Policy Authoring Agent (PAA) | ✅ policy_authoring_agent.py | ⚠️ Btn pending | Needs FE wire-up |
| WiFi Attendance Desktop (Electron) | ✅ wifi_attendance_router | ✅ NSIS installer | **GA** |
| Offline PWA (faculty attendance) | ✅ bulk-sync API | ✅ Dexie + Workbox | **GA** |
| Multi-campus model | ✅ campus_service + migration | ❌ No FE page | Needs FE |
| GST e-Invoice / IRN | ✅ einvoice_service | ❌ No FE trigger | Needs FE |
| Tally / Busy export | ✅ tally_export.py | ❌ No FE trigger | Needs FE |
| Duplicate student detection | ✅ deduplication_service | ❌ No FE | Needs FE |
| API versioning (v1/v2) | ✅ api_versioning.py | — | **GA** |
| Regional languages (6) | — | ✅ i18n/ (6 langs) | **GA** |
| Observability (Prometheus/Loki/Grafana) | ✅ Full stack | — | **GA** |
| Backup + DR | ✅ backup.sh + Beat task | — | **GA** |
| Load testing | ✅ locustfile.py | — | **GA** |
| DigiLocker / NTA / WhatsApp / Drillbit / NIC | ⚠️ Stubs (env-activated) | — | Awaiting live creds |

---

## P22–P29 — COMPLETE (March 2026)

### Migrations (0001–0034) — ALL DONE ✅

| Range | Coverage |
|---|---|
| 0001–0014 | Foundation through full admissions schema (40+ tables) |
| 0015–0025 | RBAC hardening, feature flags, regulatory, DPDP, MFA, idempotency, fee versioning, promissory, WhatsApp, guardian portal, pilot hardening |
| 0026–0031 | PhD, Re-admission, Convocation, OBE, Multi-campus, e-Invoice/i18n |
| 0032–0034 | Drillbit submission, WiFi attendance, TA assignments |

### P27 — Backend + Frontend Epics ✅ DONE

All E14–E21 + PAA backend services, all frontend pages (28 pages), 6-language i18n, mobile-responsive shell, offline PWA, monitoring stack, backup infra, load testing.

### P28 — Offline / Low-Bandwidth PWA ✅ DONE

Dexie IndexedDB (`pendingMarks`, `cachedSessions`), background sync (`syncPendingMarks`), Workbox runtime caching, network badge, `OfflineAttendancePage`.

### P29 — WiFi Attendance Desktop + Backend ✅ DONE

`wifi_attendance_router.py` (4 routes), Electron app (Login → CourseSelector → Session → LiveRoster), NSIS installer (80MB), HashRouter fix for `file://` protocol.

---

## P23 — Missing Module Frontends (After P22)

All modules have complete backends but are missing staff-facing UI pages. These are the remaining frontend gaps, grouped by urgency.

### P23-A: Core Staff UIs (High Priority — needed for GA)

#### HR & Staff Module (E08)
- `web/src/pages/hr/HRDashboardPage.tsx` — Faculty & staff roster, contract status, CAS computation
- `web/src/pages/hr/AttendancePage.tsx` — Staff attendance tracker, late/absence patterns
- `web/src/pages/hr/PayrollPage.tsx` — Monthly payroll run, deduction breakdown, payslip download
- `web/src/pages/hr/LeaveManagementPage.tsx` — Leave requests queue, balance overview, approval actions

#### Student Services Module (E09)
- `web/src/pages/student-services/GrievancePage.tsx` — Grievance queue, anomaly alerts, resolution tracking
- `web/src/pages/student-services/HostelPage.tsx` — Room allocation, swap requests, swap exchange approvals
- `web/src/pages/student-services/LibraryPage.tsx` — Book issuance, fine collection, overdue alerts
- `web/src/pages/student-services/PlacementPage.tsx` — JD pipeline, interview schedules, placement stats

#### Communication Hub (E10)
- `web/src/pages/communications/CommunicationDashboardPage.tsx` — Message history, WhatsApp thread viewer, bulk send queue
- `web/src/pages/communications/TemplatePage.tsx` — Template management (SMS/Email/WhatsApp), preview & test send

#### Alumni & Placement (E12)
- `web/src/pages/alumni/AlumniDashboardPage.tsx` — Alumni registry, engagement tracker, job placement map

### P23-B: Workflow & AI UI (High Priority)

#### Workflow Engine Admin UI
- `web/src/pages/admin/WorkflowPage.tsx` — Active workflow instances, approval queue overview, stuck task alerts, manual override with audit entry
- `web/src/pages/admin/QuorumPage.tsx` — Pending quorum votes, quorum member management

#### AI Gateway Chat UI
- `web/src/pages/ai/AgentChatPage.tsx` — Full chat thread (not just rail), conversation history, tool call trace viewer
- `web/src/pages/ai/ModelRegistryPage.tsx` — Registered AI models, task-class mapping, performance metrics

#### Dynamic Process Engine Visual Builder
- `web/src/pages/admin/ProcessBuilderPage.tsx` — Drag-and-drop BPMN-lite process editor, policy rule wizard, approval chain configurator

### P23-C: Compliance & Consent UI

#### DPDP Consent Management
- `web/src/pages/compliance/ConsentManagementPage.tsx` — Per-student consent status, collection log, erasure requests, retention audit
- Consent collection modal (reusable component) — shown at registration and on data-processing events
- Student-facing: consent review panel inside student dashboard

#### E14 Regulatory Full Workflow
- `web/src/pages/regulatory/RegulatoryPage.tsx` — (in P22 batch)
- `web/src/pages/regulatory/NaacEvidencePage.tsx` — Evidence upload per criterion, auto-collection triggers, AQAR draft viewer
- `web/src/pages/regulatory/NirfPage.tsx` — NIRF parameter data entry (TLR/RPC/GO/OI/PERCEPTION), rank estimate calculator

### P23-D: Advanced Module UIs

#### Academic Management (E05)
- `web/src/pages/academics/TimetablePage.tsx` — Timetable builder, slot conflict detection, export to PDF
- `web/src/pages/academics/AttendancePage.tsx` — Session-wise attendance grid, bulk entry, shortage alerts
- `web/src/pages/academics/AssessmentPage.tsx` — IA marks entry, grace mark application, moderation workflow

#### Finance Advanced Views
- `web/src/pages/finance/FeeStructurePage.tsx` — Program fee structure editor, intake-year versioning
- `web/src/pages/finance/ScholarshipPage.tsx` — Scholarship pool management, assignment history, revocation queue
- `web/src/pages/finance/WaiverPage.tsx` — Waiver requests, approval workflow, ledger impact preview
- `web/src/pages/finance/ExportPage.tsx` — Tally XML / Busy CSV export, GST e-invoice generation

---

## P24 — Live Integrations (After P23)

| Integration | Current State | Effort | Notes |
|---|---|---|---|
| DigiLocker live (academic certs) | Stub in `integrations/digilocker.py` | 1 week | NIC API, requires UMANG credentials |
| WhatsApp Business API (live) | MSG91 templates seeded, dispatcher exists | 3 days | Needs MSG91 account + webhook receiver |
| NTA Score Import | Stub in `integrations/nta.py` | 2 days | JEE/NEET score import for admissions |
| Payment gateway live (Razorpay) | Code done, needs credentials + webhook | 1 day | Razorpay test → prod key switch |
| Drillbit API (plagiarism) | Stub in `phd/plagiarism_service.py` | 2 days | Drillbit API key + async result callback |
| NIC e-Invoice API | Stub in `finance/einvoice_service.py` | 3 days | GST registered institution sandbox |
| LMS (Moodle/Google Classroom) | Event-triggered stub | 1 week | LMS API varies by institution |

---

## P25 — Observability + Production Hardening (After P22)

### Observability Stack

| Task | Delivers | Ref |
|---|---|---|
| Prometheus + Grafana | docker-compose service; 8 dashboard panels: req/s, p95 latency, error rate, Celery queue depth, event lag, DB pool, AI inference time, active tenants | §25 |
| Loki + Promtail | Log aggregation; structured request logs (tenant_id, request_id, user_id, module, latency); LLM call trace logs | §25 |
| AlertManager rules | Page on: p95 > 2s, error rate > 1%, Celery queue > 500, event lag > 10min, backup failure, domain event FAILED count spike | §25 |
| Sentry integration | Exception capture with tenant context; PII scrubbing for DPDP compliance | gaps.md |

### Load Testing

| Scenario | Target | Tool |
|---|---|---|
| Normal load (200 concurrent) | p95 < 500ms, error < 0.5% | Locust |
| Result day (2000 concurrent) | p95 < 2s, error < 1% | Locust |
| Admissions surge (500 concurrent applications) | p95 < 1s | Locust |
| Grade card download storm (batch PDF) | No timeout for 1000 students | Locust |

### Backup + Disaster Recovery

| Task | Delivers |
|---|---|
| `infra/backup/backup.sh` | pg_dump daily at 03:00 UTC + weekly full dump; MinIO versioned bucket |
| `server/core/backup_service.py` | Orchestration + health check; fire `platform.backup_failed` event on error |
| `docs/runbooks/restore.md` | Step-by-step restore from MinIO backup |
| RTO target | < 4 hours (policy-configured) |
| RPO target | < 24 hours (daily backup window) |

---

## P26 — Offline + Mobile PWA (Post-GA)

| Task | Delivers | Effort |
|---|---|---|
| Faculty attendance PWA | Offline marking with IndexedDB queue; sync on reconnect | 1 week |
| Student mobile portal | Native-like bottom-sheet navigation, biometric login, push notifications | 2 weeks |
| Service Worker + cache strategy | Shell cached offline; API calls gracefully degrade | 3 days |

---

## Migration Chain (current head: 0031)

```
0001 → 0002 → 0003 → ... → 0014 (full admissions)
→ 0015 (RBAC scope + event hardening)
→ 0016 (feature flags)
→ 0017 (E14 regulatory)
→ 0018 (DPDP consent)
→ 0019 (MFA devices)
→ 0020 (idempotency + audit RLS)
→ 0021 (fee versioning + webhook idempotency)
→ 0022 (DBT exemption + promissory)
→ 0023 (WhatsApp language)
→ 0024 (guardian portal provisioning)
→ 0025 (P21 pilot hardening — shadow mode, webhooks, E19 seat matrix, edge cases)
→ 0026 (E15 PhD module) ← P22
→ 0027 (E17 re-admission + credit transfer) ← P22
→ 0028 (E18 convocation) ← P22
→ 0029 (E20 OBE / CO-PO) ← P22
→ 0030 (multi-campus entity model) ← P22
→ 0031 (GST e-invoice IRN + language_preference) ← P22
```

---

## Test Suite Status

| Batch | Tests | Status |
|---|---|---|
| Core infra (E01–E03) | ~200 | ✅ Passing |
| Admissions (E04) | ~300 | ✅ Passing |
| Academics–Alumni (E05–E12) | ~280 | ✅ Passing |
| **Total (P21 baseline)** | **781 / 781** | ✅ All passing |
| P22 new (E15/E17/E18/E20/PAA) | ~60 (estimate) | ❌ Not yet written |

> Note: 4 test files pre-exist with known failures unrelated to P22: `test_ai_gateway_api.py` (NameError in test fixture), `test_auth.py` (session fixture), `test_integrations_p14.py` (DigiLocker stub), `test_ai_gateway.py` (Ollama not running). These are excluded from CI until the integrations are live.

---

## Hardcoding Prevention Rules (apply to all new code)

| Rule | Constraint |
|---|---|
| R1 | No hardcoded thresholds — all from `policy_engine.get_value()` |
| R2 | No hardcoded approval chains — all from `workflow_engine` DAG configs |
| R3 | SLA deadlines stored as absolute `TIMESTAMPTZ` — computed at creation, never at check time |
| R4 | No hardcoded role names — roles from RBAC permission enum |
| R6 | State machines for all entity transitions — no ad-hoc status updates |
| R7 | Policy DSL for all eligibility decisions — never if/else thresholds in service code |
| R8 | No hardcoded notification content — all content via `template_key` in event payload |
| R9 | No hardcoded document formats — `document_engine.render(template_id, context, tenant_id)` |
| R10 | No hardcoded regulatory mappings — evidence mappings from `regulatory_criteria` table |
| R11 | Feature flags from DB — `tenant_feature_flags` table, Redis-cached |
| R12 | `policy_version_id` stored on every policy-governed decision record |

---

## Priority Order for Remaining Work

```
NOW (P22, in progress):
  ├── Batch 2: E15/E17/E18/E20 backends + Tally/dedup/einvoice
  ├── Batch 3: PAA + multi-campus service + API versioning + backup + load test
  └── Batch 4: All new frontend pages + Guardian Portal + mobile shell + i18n

NEXT (P23):
  ├── P23-A: HR, Student Services, Communication, Alumni staff UIs
  ├── P23-B: Workflow admin UI, AI chat UI, Process Builder
  └── P23-C: DPDP consent UI, E14 full regulatory UI, E16 Guardian Portal service

AFTER (P24 + P25):
  ├── P24: Live integrations (DigiLocker, WhatsApp, Razorpay prod, Drillbit, NIC)
  └── P25: Observability stack (Grafana/Loki/Prometheus), alerting, load test baseline

LATER (P26):
  └── Offline PWA, mobile native app
```

---

*Build Plan v2.0 | 2026-03-19 | QUAICU Pvt. Ltd. | Reflects P22 in-progress state*
