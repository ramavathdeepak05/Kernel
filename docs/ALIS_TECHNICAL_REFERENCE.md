# ALIS — Autonomous Learning & Institutional System
## Comprehensive Technical Reference

*QUAICU Solutions Private Limited | Version 1.0 | March 2026 | Confidential*

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Infrastructure — Docker Services](#3-infrastructure--docker-services)
4. [Database — Migration History](#4-database--migration-history)
5. [Backend Modules](#5-backend-modules)
6. [API Routes](#6-api-routes)
7. [Core Layer](#7-core-layer)
8. [Background Workers (Celery)](#8-background-workers-celery)
9. [Python Dependencies](#9-python-dependencies)
10. [Frontend Application](#10-frontend-application)
11. [Frontend Dependencies](#11-frontend-dependencies)
12. [Security Model](#12-security-model)
13. [AI Stack](#13-ai-stack)
14. [RBAC — Roles & Permissions](#14-rbac--roles--permissions)
15. [Configuration Reference](#15-configuration-reference)
16. [Production Quality Rules](#16-production-quality-rules)

---

## 1. System Overview

**ALIS** (Autonomous Learning & Institutional System) is a policy-driven, event-sourced ERP platform for Indian higher-education institutions. It is designed to operate autonomously — AI agents propose, rules enforce, and human staff handle exceptions only.

### Who it serves
| Role | Primary Use |
|---|---|
| Registrar | Admissions pipeline, enrollment, examinations, compliance |
| Finance Officer | Fee structures, invoices, payments, Tally/e-invoice export |
| HOD / Faculty | Academics, attendance, marks, OBE/CO-PO |
| HR Admin | Staff records, leave, payroll |
| Student | Dashboard, fee payments, attendance, grievances |
| Guardian / Parent | OTP portal — attendance, dues, communication |
| PhD Scholar | Milestone tracking, DC meetings, plagiarism |
| Super Admin | Policy Studio, feature flags, multi-campus, tenant management |

### Design Principles
1. **AI proposes, rules enforce** — LLM agents produce DRAFT only; orchestrators execute state transitions
2. **Policy-driven, never hardcoded** — thresholds, approval chains, SLAs live in `institution_policies` DB table
3. **Event-driven cross-module** — modules communicate exclusively via domain events; no direct cross-module calls
4. **Append-only audit ledger** — every action is immutably recorded; no UPDATE or DELETE on `audit_ledger`
5. **Multi-tenant isolation** — PostgreSQL Row-Level Security enforces tenant boundaries at the DB layer
6. **No cloud LLM dependency** — all AI runs on-premises via Ollama; external API optional override

---

## 2. Architecture

### 6-Layer Model

```
Layer 1 — Module Purpose          What each module does (E01–E20)
Layer 2 — Agentic Decisions       AI agents draft decisions; humans/quorum approve
Layer 3 — State Machines          Every entity lifecycle enforced via state machine
Layer 4 — Global Locks            Locks prevent concurrent conflicting operations
Layer 5 — Roles, Authority & Quorum  RBAC+ with context-awareness; quorum for critical decisions
Layer 6 — Resilience              AuditLedger (immutable), DomainEventBus, idempotency
```

The **AuditLedger** is cross-cutting — every write in all layers emits an audit entry.

### Event-Driven Module Communication

Modules never call each other directly. They publish and subscribe to domain events via `DomainEventBus`:

```
Admissions → student.enrolled → Finance (create invoice), Academics (enroll in courses),
                                  Communication (send welcome SMS), HR (add to roster)
Finance → fee.paid → Academics (update payment gate), Communication (receipt SMS)
Examinations → result.published → Communication (notify students), Alumni (graduation check)
```

### State Machines

All entity lifecycle transitions go through state machines — never raw SQL:

| Entity | Machine | States |
|---|---|---|
| Applicant | `StudentState` | 22 states from LEAD → ENROLLED → GRADUATED |
| Student Invoice | invoice FSM | UNPAID → PARTIAL → PAID → OVERDUE |
| Document | doc FSM | PENDING → UNDER_REVIEW → APPROVED / REJECTED / REUPLOAD |
| Approval Request | approval FSM | PENDING → APPROVED / REJECTED / ESCALATED |
| PhD Registration | phd FSM | REGISTERED → MILESTONE_1 … → THESIS_SUBMITTED → DEGREE_AWARDED |

---

## 3. Infrastructure — Docker Services

All services run in Docker Compose on the `alis_network` bridge.

| Container | Image | Ports | Purpose | Volume | Health Check |
|---|---|---|---|---|---|
| `alis_postgres` | `pgvector/pgvector:pg16` | 5432 | PostgreSQL 16 + pgvector extension | `postgres_data` | `pg_isready` |
| `alis_redis` | `redis:7-alpine` | 6379 | Celery broker + result backend + session store | `redis_data` | `redis-cli ping` |
| `alis_ollama` | `ollama/ollama:latest` | 11434 | Local LLM inference (Qwen 2.5 series) | `ollama_data` | `ollama list` |
| `alis_minio` | `minio/minio:latest` | 9000 (S3), 9001 (console) | S3-compatible file/document storage | `minio_data` | curl `/minio/health/live` |
| `alis_app` | build `./ALIS` | 8000 | FastAPI application | `./ALIS:/app` (live reload) | curl `/health` |
| `alis_celery_worker` | build `./ALIS` | — | Background task processor (4 workers) | `./ALIS:/app` | — |
| `alis_celery_beat` | build `./ALIS` | — | Periodic task scheduler | `./ALIS:/app` | — |
| `alis_vault` | `hashicorp/vault:1.17` | 8200 | Secrets + exam paper encryption (Transit KV) | `vault_data` | `vault status` |
| `alis_prometheus` | `prom/prometheus:v2.54.0` | 9090 | Metrics scraping (30-day retention) | `prometheus_data` + bind mount config | `wget /-/healthy` |
| `alis_grafana` | `grafana/grafana:11.2.0` | 3000 | Dashboards + alerting UI | `grafana_data` + provisioning bind mount | — |
| `alis_loki` | `grafana/loki:3.1.0` | 3100 | Log aggregation (30-day retention, compaction) | `loki_data` + bind config | — |
| `alis_promtail` | `grafana/promtail:3.1.0` | — | Log shipper — reads Docker container logs → Loki | bind `/var/log`, `/var/lib/docker/containers` | — |
| `alis_alertmanager` | `prom/alertmanager:v0.27.0` | 9093 | Routes Prometheus alerts → email / webhook | bind config | `wget /-/healthy` |
| `alis_nginx` | `nginx:alpine` | 80, 443 | Reverse proxy + SSL termination + rate limiting | bind `nginx/nginx.conf`, `nginx/certs/` | `nginx -t` |

### Celery Queues
Worker processes 3 named queues: `default`, `ai_tasks`, `notifications`

### Inter-service Dependencies (startup order)
`postgres` + `redis` + `minio` + `vault` + `prometheus` → `alis_app` → `celery_worker` + `celery_beat` → `nginx`

---

## 4. Database — Migration History

All migrations use Alembic. Current head: **0035**.

| Migration | Description |
|---|---|
| `0001_initial_schema` | All core tables: organizations, users, roles, applicants, students, approval_requests, approval_actions, audit_ledger, institution_policies, feature_flags, domain_events |
| `0002_autonomous_admissions` | Policy store, review queue, org API keys |
| `0003_academics` | programs, courses, course_enrollments, attendance_sessions, attendance_records |
| `0004_examinations` | exam_papers, exam_slots, exam_registrations, exam_marks, grade_cards |
| `0005_finance` | fee_structures, fee_items, student_invoices, payments |
| `0006_hr_staff` | staff_profiles, staff_documents, leave_requests, payroll_cycles, payroll_entries |
| `0007_student_services` | hostel_rooms, hostel_allocations, transport_routes, bus_passes, scholarships, scholarship_applications, grievances |
| `0008_communication_hub` | notification_templates, notification_logs, in_app_notifications, bulk_message_jobs, announcements |
| `0009_reporting` | saved_reports, report_schedules, kpi_snapshots |
| `0010_alumni_placement` | alumni_profiles, placement_drives, drive_applications, job_postings |
| `0011_process_engine` | process_definitions, process_steps, process_instances, form_submissions |
| `0012_schema_corrections` | Alignment corrections between DB and codebase |
| `0013_missing_indexes` | Performance indexes on hot-path columns (tenant, status, created_at) |
| `0014_admissions_full_workflow` | Full 10-stage admissions: leads, application_forms, entrance_tests, interview_panels, merit_list_configs, seat_matrix, offer_letters, payment_v2, final_verifications, enrollment_provisioning, 40+ tables |
| `0015_rbac_scope_and_event_hardening` | RBAC scope model + domain_events idempotency + RLS on users/applicants/students |
| `0016_feature_flags` | Per-tenant feature flag system with audit trail |
| `0017_e14_regulatory` | NAAC criteria tables, NIRF parameters, compliance_items, evidence_submissions |
| `0018_dpdp_consent` | DPDP consent_records, erasure_requests, purpose_registry |
| `0019_mfa_devices` | mfa_devices, trusted_devices (TOTP-based 2FA) |
| `0020_phase0_idempotency_and_audit_rls` | Celery task idempotency keys, audit_ledger RLS policies |
| `0021_fee_versioning_and_webhook_idempotency` | fee_structure versioning, webhook_deliveries idempotency |
| `0022_dbt_exemption_and_promissory` | DBT exemption records, promissory_note_ledger |
| `0023_whatsapp_language` | WhatsApp Business API language variants, delivery_log |
| `0024_guardian_portal_provisioning` | guardian_accounts, student-guardian links (OTP auth) |
| `0025_pilot_hardening` | Shadow mode tables, data_migration_batches, outbound_webhooks, edge case guards |
| `0026_phd_module` | phd_registrations, phd_milestones, phd_dc_meetings, phd_plagiarism_reports, phd_thesis_submissions |
| `0027_readmission` | readmission_applications, credit_transfer_requests, credit_equivalency_records |
| `0028_convocation` | convocation_events, convocation_degree_audits, convocation_seating, gold_medal_computations |
| `0029_obe` | program_outcomes, course_outcomes, co_po_mapping, assessment_rubrics, attainment_records |
| `0030_multi_campus` | campus_entities, campus_user_assignments; ALTER organizations: parent_org_id, entity_type |
| `0031_einvoice` | ALTER student_invoices: add irn, irn_generated_at |
| `0032_drillbit_submission_id` | ALTER phd_plagiarism_reports: add drillbit_submission_id |
| `0033_wifi_attendance` | attendance_wifi_sessions, attendance_wifi_verifications |
| `0034_ta_assignments` | course_ta_assignments, session_ta_assignments |
| `0035_workflow_tasks_audit_rls` | workflow_tasks table + immutability trigger on audit_ledger + RLS on leads + audit_ledger |

### Key DB Conventions
- All IDs: `UUID v4`
- All timestamps: `TIMESTAMPTZ` (UTC stored, IST displayed)
- Money: `DECIMAL(12,2)` in DB, string in JSON
- Soft delete: `status='ARCHIVED'` (lifecycle) or `status='ANNULLED'` (state machine)
- All tenant tables: RLS via `current_setting('app.tenant_id', true)` or `alis.current_tenant`

---

## 5. Backend Modules

All backend code lives under `ALIS/server/`. API prefix: `/api/v1/`.

### E01 — Authentication, Users & RBAC
**Path:** `server/core/security.py`, `server/api/auth_router.py`, `server/api/users_router.py`, `server/api/roles_router.py`

- JWT authentication (HS256 / RS256 switchable)
- Session management via Redis (`alis:sess:*`, `alis:tok:*`, `alis:user_sess:*`)
- Failed login tracking + account lockout (`alis:fail:*`, `alis:lockout:*`)
- Rate limiting (`alis:rate:*`)
- MFA (TOTP) — required for SUPER_ADMIN, ADMIN, REGISTRAR, FINANCE_OFFICER, HOD, COE
- RBAC+ with context-aware access (tenant isolation, exam window checks, agent constraints)
- Dynamic role creation by Module Managers within their scope

### E02 — Workflow Engine & Approvals
**Path:** `server/api/approvals_router.py`, `server/api/workflows_router.py`

- Multi-step approval workflows (ANY / ALL / quorum modes)
- Dual-control approvals for financial overrides and grade changes
- Escalation requests and temporary role elevation (DEAN_ELEVATED)
- `approval_requests` + `approval_actions` tables

### E03 — AI Gateway & Guardrails
**Path:** `server/api/gateway_router.py`, `server/core/llm_router.py`, `server/agents/`

- Centralized LLM invocation — all AI calls route through gateway, never direct
- 3-tier model routing: EXTRACTION (1.5B), GENERATION (7B), REASONING (14B)
- Guardrails: output validation, DRAFT-only writes, HITL checkpoints
- PGVector embeddings for counsellor allocation, document search, RAG
- Tool registry (`server/tools/`) — AI agents access business functions via typed tools
- MCP (Model Context Protocol) server for external agent integration

### E04 — Autonomous Admissions (10 stages, 87 API routes)
**Path:** `server/admissions/`, `server/api/admissions_router.py`, `server/api/intake_router.py`

| Stage | Service | Key Functions |
|---|---|---|
| 1. Lead CRM | `lead_service.py` | Lead capture, consultant assignment, referral codes, status funnel |
| 2. Application | `application_form.py` | Multi-step wizard, APP-{YEAR}-{SEQ} IDs, draft/submit/fee |
| 3. Documents | doc review workflow | PENDING → UNDER_REVIEW → APPROVED / REJECTED / REUPLOAD |
| 4. Eligibility | `eligibility_service.py` | Subject criteria, category relaxations, policy-driven thresholds |
| 5A. Entrance Test | `entrance_test.py` | Test creation, slots, registrations, admit cards, score import |
| 5B. Interviews | `interview.py` | Panels, scheduling, scorecards, aggregate scoring |
| 6. Merit List | `merit_list.py` | Seat matrix, configurable formula, ranked generation, waitlist |
| 7. Offer Letter | `offer_letter.py` | Generation, acceptance/decline, countersign, expiry |
| 8. Payment | `payment_v2.py` | Fee schedule, Razorpay gateway, reconciliation, refunds |
| 9. Final Verification | `final_verification.py` | Doc cross-check, background screening, approval quorum |
| 10. Enrollment | `enrollment_provisioning.py` | Student ID, roll number, LMS sync, hostel, library |
| Notifications | `admissions_templates.py` | 25+ templates across all touchpoints |
| Re-admission | `readmission_service.py` | RE-prefix roll, completed semester lock |
| Credit Transfer | `credit_transfer_service.py` | AI-assisted equivalency, policy max credits |
| Deduplication | `deduplication_service.py` | Jaro-Winkler matching, dual-auth merge |
| Forgery Detection | `forgery_detection.py` | AI-assisted document fraud flagging |

### E05 — Academics
**Path:** `server/academics/`, `server/api/academics_router.py`

- Programs, courses, semester management
- Attendance marking + eligibility (threshold from `institution_policies`, never hardcoded)
- Timetable management
- Course handover workflow (`course_handover_workflow.py`)
- TA assignments (course-level and session-level)
- OBE / CO-PO mapping (`obe_service.py`) — outcome attainment calculation, NBA/NAAC reports

### E06 — Examinations & Grades
**Path:** `server/examinations/`, `server/api/examinations_router.py`

- Exam paper creation + Vault-encrypted storage (CoE-only decrypt)
- Hall ticket batch generation
- Internal/external marks entry (faculty → finalize → publish)
- AI-assisted score anomaly detection (flags for human review, never auto-overrides)
- Grade card generation (PDF via ReportLab)
- Revaluation and supplementary exam tracking
- Result publication (locked after REGISTRAR approval)

### E07 — Finance
**Path:** `server/finance/`, `server/api/finance_router.py`

- Fee structure management with versioning
- Invoice generation (automatic on enrollment)
- Payment gateway: Razorpay primary (HMAC-verified webhook), PayU fallback
- Manual payment recording (CASH / CHEQUE / DD / NEFT)
- DBT exemption + promissory note ledger
- Fee waiver management (approval workflow required)
- Tally XML export + Busy CSV export (for accounting)
- GST e-Invoice / IRN generation (NIC API, feature-flagged)
- Finance analytics: collection rate, aging, pending dues

### E08 — HR & Staff
**Path:** `server/hr/`, `server/api/hr_router.py`

- Staff profile management (faculty, admin, support)
- Staff document upload and verification
- Leave management (apply, approve, balance tracking)
- Payroll cycles + salary computation
- Appraisal management

### E09 — Student Services
**Path:** `server/student_services/`, `server/api/student_services_router.py`

- Hostel room allocation and management
- Transport route + bus pass management
- Scholarship applications and disbursement
- Grievance management (LODGED → UNDER_REVIEW → RESOLVED / ESCALATED)
- Bonafide certificate and document request

### E10 — Communication Hub
**Path:** `server/communication/`, `server/api/communication_router.py`

- Template-based notifications (email, SMS, WhatsApp, in-app)
- WhatsApp Business API (multi-language: Telugu, Kannada, Tamil, Marathi, Hindi)
- Bulk messaging with delivery tracking
- Announcement broadcasts
- Communication preference management

### E11 — Reporting & Analytics
**Path:** `server/reporting/`, `server/api/reporting_router.py`

- KPI snapshots (daily batch at 00:30)
- Saved report library
- Scheduled report delivery
- NAAC Annual Quality Assurance Report (AQAR) draft compilation
- Module analytics: admissions funnel, finance collection, attendance heatmap

### E12 — Alumni & Placement
**Path:** `server/alumni/`, `server/api/alumni_router.py`

- Alumni profile directory
- Placement drive management (company → eligibility → registrations → selections)
- Job board
- Industry mentorship connections

### E13 — Dynamic Process Engine
**Path:** `server/process_engine/`, `server/api/process_engine_router.py`

- Configurable multi-step workflows (drag-and-drop in Policy Studio)
- Form builder (dynamic field definitions)
- Process instance tracking with audit
- Policy DSL for eligibility rules (`asteval` for safe expression evaluation)
- Policy authoring agent (LLM-assisted draft → human approval)

### E14 — Regulatory & Accreditation
**Path:** `server/regulatory/`, `server/api/regulatory_router.py`

- NAAC criteria tracking (C1–C7) with evidence upload
- NIRF parameter management (TLR, RPC, GO, OI, PERCEPTION)
- Compliance item registry
- AQAR auto-compilation (Celery Beat: annually 1 July)

### E15 — PhD / Doctoral Research
**Path:** `server/phd/`, `server/api/phd_router.py`

- PhD scholar registration + supervisor assignment (max 8 scholars per supervisor — from policy)
- 9-milestone lifecycle state machine
- DC meeting scheduler (every 6 months — from policy)
- Plagiarism check via Drillbit API (threshold from policy, never hardcoded)
- Thesis submission workflow

### E18 — Convocation Management
**Path:** `server/convocation/`, `server/api/convocation_router.py`

- Convocation event planning
- Automated degree audit (runs after final semester lock)
- Gold medal computation (highest CGPA per program, grace marks excluded — R1)
- Seating arrangement generation
- Certificate PDF queue

### E21 — DPDP Consent Management
**Path:** `server/consent/`, `server/api/consent_router.py`

- DPDP-compliant consent records per data purpose
- Consent withdrawal + erasure request workflow
- `ConsentMiddleware` — enforces consent at API layer before data access

### P14 — External Integrations
**Path:** `server/integrations/`, `server/api/integrations_router.py`

- DigiLocker (Indian Government document vault)
- NTA (National Testing Agency) score import
- LMS sync (Moodle / Canvas REST API)
- Google Workspace / Microsoft 365 email provisioning

### P21 — Admin & Platform Hardening
**Path:** `server/api/admin_router.py`, `server/core/shadow_mode_middleware.py`

- Shadow mode (new workflow runs alongside old, divergences reported — safe pilot rollout)
- Data migration batching
- Outbound webhook management + retry logic
- Guardian portal provisioning

### P29 — WiFi Proximity Attendance
**Path:** `server/api/wifi_attendance_router.py`

- Faculty starts hotspot session → backend issues `session_token` + SSID
- Students connect → public IP match → auto-marked PRESENT
- Session countdown timer + live roster
- Auto-mark absentees on session end

---

## 6. API Routes

All routes are under prefix `/api/v1/` unless noted. `[auth]` = JWT required. `[admin]` = SUPER_ADMIN / ADMIN only.

### Auth (`/api/v1/auth/`)
| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Username + password login → JWT + refresh token |
| POST | `/auth/login/mfa` | Complete MFA challenge (TOTP code) |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Revoke session |
| POST | `/auth/logout-all` | Revoke all sessions for current user |
| POST | `/auth/mfa/setup` | Initiate MFA device setup |
| POST | `/auth/mfa/verify` | Verify and activate MFA device |
| DELETE | `/auth/mfa/disable` | Disable MFA (requires elevated auth) |

### Users (`/api/v1/users/`)
| Method | Path | Description |
|---|---|---|
| GET | `/users/` | List users [auth][admin] |
| POST | `/users/` | Create user [auth][admin] |
| GET | `/users/{user_id}` | Get user [auth] |
| PATCH | `/users/{user_id}` | Update user [auth] |
| DELETE | `/users/{user_id}` | Deactivate user [auth][admin] |
| GET | `/users/me` | Get current user profile [auth] |

### Organizations (`/api/v1/organizations/`)
| Method | Path | Description |
|---|---|---|
| POST | `/organizations/` | Create organization (tenant) [admin] |
| GET | `/organizations/{org_id}` | Get organization [auth] |
| PATCH | `/organizations/{org_id}` | Update organization [auth][admin] |
| POST | `/organizations/campuses` | Create campus under group entity [admin] |
| GET | `/organizations/group-summary` | Cross-campus aggregate view [admin] |
| POST | `/organizations/bootstrap` | Bootstrap org + SUPER_ADMIN + seed data |

### Approvals (`/api/v1/approvals/`)
| Method | Path | Description |
|---|---|---|
| POST | `/approvals/` | Create approval request |
| GET | `/approvals/{request_id}` | Get request status |
| POST | `/approvals/{request_id}/action` | Submit approve/reject/escalate action |
| GET | `/approvals/pending` | List pending requests for actor |
| POST | `/approvals/escalation/request` | Request temporary role elevation |
| POST | `/approvals/escalation/{id}/grant` | Grant escalation (ADMIN+) |
| POST | `/approvals/escalation/{id}/revoke` | Revoke escalation |

### AI Gateway (`/api/v1/ai/`)
| Method | Path | Description |
|---|---|---|
| POST | `/ai/invoke` | Invoke AI task through gateway [auth] |
| GET | `/ai/models` | List available models [auth] |
| POST | `/ai/embed` | Generate embedding for text [auth] |
| GET | `/ai/guardrails` | Get guardrail configuration [admin] |

### Admissions (`/api/v1/admissions/`)
87 routes covering all 10 stages — key routes:
| Method | Path | Description |
|---|---|---|
| POST | `/admissions/leads` | Create lead |
| GET | `/admissions/leads` | List leads with filters |
| POST | `/admissions/applications` | Start application |
| GET | `/admissions/applications/{id}` | Get application status |
| POST | `/admissions/applications/{id}/submit` | Submit complete application |
| POST | `/admissions/documents/{id}/upload` | Upload document |
| POST | `/admissions/documents/{id}/review` | Review document (staff) |
| POST | `/admissions/eligibility/{applicant_id}/check` | Run eligibility check |
| POST | `/admissions/entrance-tests` | Create entrance test |
| POST | `/admissions/entrance-tests/{id}/scores` | Import scores |
| POST | `/admissions/interviews/panels` | Create interview panel |
| POST | `/admissions/merit-list/generate` | Generate merit list |
| POST | `/admissions/offers` | Issue offer letter |
| POST | `/admissions/offers/{id}/accept` | Accept offer |
| POST | `/admissions/final-verification/{id}/approve` | Approve final verification |
| POST | `/admissions/enrollment/{id}/complete` | Complete enrollment (creates student) |
| GET | `/admissions/students/duplicates` | Find duplicate students |
| POST | `/admissions/students/merge` | Merge duplicate records (dual-auth) |
| POST | `/admissions/readmission` | Submit re-admission application |
| POST | `/admissions/credit-transfer` | Submit credit transfer request |
| POST | `/intake/webhooks/razorpay` | Razorpay payment webhook |
| POST | `/intake/webhooks/digilocker` | DigiLocker callback |
| POST | `/intake/portal/status` | Public portal status check |

### Academics (`/api/v1/academics/`)
| Method | Path | Description |
|---|---|---|
| POST | `/academics/programs` | Create program |
| GET | `/academics/programs` | List programs |
| POST | `/academics/courses` | Create course |
| GET | `/academics/courses` | List courses |
| POST | `/academics/courses/{id}/enroll` | Enroll student |
| POST | `/academics/attendance/sessions` | Create session |
| POST | `/academics/attendance/sessions/{id}/mark` | Mark attendance |
| GET | `/academics/attendance/student/{id}/summary` | Attendance summary with at_risk flag |
| POST | `/academics/courses/{id}/handover` | Initiate course handover |
| GET | `/academics/obe/attainment/{program_id}` | CO-PO attainment |
| POST | `/academics/obe/outcomes` | Define program/course outcomes |
| POST | `/academics/obe/mapping` | Map CO → PO |

### Examinations (`/api/v1/examinations/`)
| Method | Path | Description |
|---|---|---|
| POST | `/examinations/papers` | Create exam paper (stored encrypted in Vault) |
| GET | `/examinations/hall-tickets/batch` | Batch generate hall tickets |
| POST | `/examinations/marks` | Enter marks (faculty) |
| POST | `/examinations/marks/{id}/finalize` | Finalize marks (HOD) |
| POST | `/examinations/results/{exam_id}/publish` | Publish results (Registrar) |
| GET | `/examinations/grade-cards/{student_id}` | Get grade card |
| POST | `/examinations/revaluation` | Submit revaluation request |
| GET | `/examinations/faculty/review-queue` | AI-flagged anomaly queue |

### Finance (`/api/v1/finance/`)
| Method | Path | Description |
|---|---|---|
| POST | `/finance/fee-structures` | Create fee structure |
| POST | `/finance/invoices` | Generate invoice |
| GET | `/finance/invoices/{student_id}` | List student invoices |
| POST | `/finance/payments/razorpay/order` | Create Razorpay order |
| POST | `/finance/payments/razorpay/verify` | Verify & capture Razorpay payment |
| POST | `/finance/payments/manual` | Record manual payment (CASH/CHEQUE/DD/NEFT) |
| POST | `/finance/waivers` | Request fee waiver (triggers approval workflow) |
| POST | `/finance/export/tally` | Export to Tally XML |
| POST | `/finance/export/busy` | Export to Busy CSV |
| POST | `/finance/invoices/{id}/generate-irn` | Generate GST e-Invoice IRN |

### HR (`/api/v1/hr/`)
| Method | Path | Description |
|---|---|---|
| POST | `/hr/staff` | Create staff profile |
| GET | `/hr/staff` | List staff |
| POST | `/hr/leave/apply` | Apply for leave |
| POST | `/hr/leave/{id}/approve` | Approve leave (HOD/Admin) |
| GET | `/hr/payroll/cycles` | List payroll cycles |
| POST | `/hr/payroll/process` | Process payroll cycle |

### Student Services (`/api/v1/student-services/`)
| Method | Path | Description |
|---|---|---|
| GET | `/student-services/hostel/rooms` | List hostel rooms |
| POST | `/student-services/hostel/allocate` | Allocate room to student |
| POST | `/student-services/transport/bus-pass` | Issue bus pass |
| POST | `/student-services/scholarships/apply` | Apply for scholarship |
| POST | `/student-services/grievances` | Lodge grievance |
| PATCH | `/student-services/grievances/{id}` | Update grievance status |

### Communication (`/api/v1/communication/`)
| Method | Path | Description |
|---|---|---|
| GET | `/communication/templates` | List notification templates |
| POST | `/communication/templates` | Create template |
| POST | `/communication/send` | Send notification (single) |
| POST | `/communication/bulk` | Send bulk message |
| POST | `/communication/announcements` | Create announcement |

### Reporting (`/api/v1/reports/`)
| Method | Path | Description |
|---|---|---|
| GET | `/reports/kpi` | Get KPI snapshot |
| POST | `/reports/saved` | Save report configuration |
| GET | `/reports/saved` | List saved reports |
| POST | `/reports/schedule` | Schedule report delivery |
| GET | `/reports/pipeline-summary` | Admissions pipeline summary |
| GET | `/reports/review-queue` | Approval review queue stats |

### Alumni (`/api/v1/alumni/`)
| Method | Path | Description |
|---|---|---|
| GET | `/alumni/profiles` | List alumni |
| POST | `/alumni/placement-drives` | Create placement drive |
| POST | `/alumni/placement-drives/{id}/register` | Student registers for drive |
| GET | `/alumni/job-board` | Public job board |

### Process Engine (`/api/v1/process-engine/`)
| Method | Path | Description |
|---|---|---|
| POST | `/process-engine/definitions` | Define workflow |
| POST | `/process-engine/instances` | Start workflow instance |
| GET | `/process-engine/instances/{id}` | Get instance status |
| POST | `/process-engine/policies` | Create/update policy rule |
| GET | `/process-engine/policies` | List policies |
| POST | `/admin/policies/draft-with-ai` | LLM-assisted policy draft (SUPER_ADMIN) |

### Feature Flags (`/api/v1/feature-flags/`)
| Method | Path | Description |
|---|---|---|
| GET | `/feature-flags/` | List all feature flags (admin) |
| POST | `/feature-flags/` | Create feature flag |
| PATCH | `/feature-flags/{key}` | Enable/disable flag per tenant |
| GET | `/feature-flags/{key}` | Get flag status |

### Regulatory (`/api/v1/regulatory/`)
| Method | Path | Description |
|---|---|---|
| GET | `/regulatory/naac/criteria` | Get NAAC criteria progress |
| POST | `/regulatory/naac/evidence` | Upload NAAC evidence |
| GET | `/regulatory/nirf/parameters` | Get NIRF parameter values |
| GET | `/regulatory/compliance` | List compliance items |

### Consent (`/api/v1/consent/`)
| Method | Path | Description |
|---|---|---|
| GET | `/consent/purposes` | List data purposes requiring consent |
| POST | `/consent/grant` | Grant consent for purpose |
| POST | `/consent/revoke` | Revoke consent |
| POST | `/consent/erasure` | Submit erasure (right to be forgotten) request |

### PhD (`/api/v1/phd/`)
| Method | Path | Description |
|---|---|---|
| POST | `/phd/register` | Register PhD scholar |
| GET | `/phd/scholars` | List scholars |
| POST | `/phd/milestones/{id}/complete` | Mark milestone complete |
| POST | `/phd/thesis/submit` | Submit thesis |
| GET | `/phd/plagiarism/{id}` | Get plagiarism report |

### Convocation (`/api/v1/convocation/`)
| Method | Path | Description |
|---|---|---|
| POST | `/convocation` | Create convocation event |
| GET | `/convocation/{id}/audit` | Run degree audit |
| POST | `/convocation/{id}/generate-seating` | Generate seating arrangement |
| GET | `/convocation/{id}/gold-medals` | Get gold medal computations |

### WiFi Attendance (`/api/v1/attendance/wifi/`)
| Method | Path | Description |
|---|---|---|
| POST | `/attendance/wifi/start` | Faculty starts session |
| GET | `/attendance/wifi/sessions/{id}` | Poll session status + live roster |
| POST | `/attendance/wifi/verify` | Student self check-in |
| POST | `/attendance/wifi/sessions/{id}/end` | End session, auto-mark absentees |

### System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks postgres, redis, ollama, minio) |
| GET | `/metrics` | Prometheus metrics (internal only) |

---

## 7. Core Layer

All files under `ALIS/server/core/`:

| File | Purpose |
|---|---|
| `settings.py` | Pydantic Settings — single source of truth for all infra config |
| `security.py` | JWT creation/verification, TenantMiddleware, session management, MFA |
| `rbac.py` | Role/Permission definitions, RBAC+ context-aware access check |
| `domain_events.py` | DomainEventBus — pub/sub event bus for cross-module communication |
| `audit.py` | AuditLog — append-only ledger writer |
| `error_handlers.py` | FastAPI exception handlers (BusinessRuleViolation, NotFoundError, PermissionDenied, etc.) |
| `exceptions.py` | Custom exception classes |
| `feature_flags.py` | Per-tenant feature flag evaluation |
| `llm_router.py` | Tiered LLM routing (EXTRACTION/GENERATION/REASONING) → Ollama or external API |
| `metrics.py` | Prometheus counter/histogram/gauge definitions |
| `mfa_service.py` | TOTP generation, verification, Fernet-encrypted secret storage |
| `models.py` | Base Pydantic models (BaseEntity, etc.) |
| `policy_engine.py` | Runtime policy evaluation (reads from `institution_policies` table) |
| `policy_authoring_agent.py` | LLM-assisted policy draft (DRAFT status only; requires human approval) |
| `shadow_mode_middleware.py` | Shadow mode request interception and divergence logging |
| `vault_client.py` | HashiCorp Vault client (Transit encryption, KV secrets) |
| `api_versioning.py` | DeprecationMiddleware (Sunset headers on v1) + v2 router factory |

### DomainEventBus

Events are published synchronously within the request, then dispatched asynchronously via Celery:

```python
DomainEventBus.publish(DomainEvent(
    event_type="student.enrolled",
    entity_type="student",
    entity_id=student_id,
    org_id=org_id,
    payload={...},
    actor_id=actor_id,
))
```

Subscribers register via `DomainEventBus.subscribe("event.type", handler_fn)`.

Failed events are retried every 5 minutes by the `retry-failed-events` Beat task.

---

## 8. Background Workers (Celery)

### Task Modules

| Module | Tasks |
|---|---|
| `server.tasks.notifications` | `send_pending_reminders` — hourly reminder sweep |
| `server.tasks.ai_tasks` | Document verification, eligibility assessment, forgery detection |
| `server.tasks.events` | `retry_failed_events` (5 min), `retry_stuck_events` (30 sec — FINANCE+EXAMINATION), `compile_aqar_draft` (annual) |
| `server.tasks.calendar` | `check_calendar_phases` — midnight academic calendar transitions |
| `server.tasks.admissions` | `check_fee_overdue` (daily 09:00), `check_reporting_deadlines` (daily 02:30 UTC) |
| `server.tasks.finance` | `check_invoice_overdue` (daily 09:05) — mark UNPAID → OVERDUE |
| `server.tasks.reporting` | `refresh_kpi_snapshots` (daily 00:30) |
| `server.tasks.shadow_divergence` | `run_shadow_divergence` (nightly 20:30 UTC) |
| `server.tasks.webhook_retry` | `retry_pending_webhooks` (every 5 minutes) |
| `server.tasks.backup` | `run_daily_backup` (daily 03:00 UTC) — pg_dump to MinIO |
| `server.tasks.plagiarism_poll` | `poll_drillbit_results` (every 5 minutes) |
| `server.tasks.lms_sync` | `sync_lms_grades` (weekly Sunday 01:00 UTC) |

### Beat Schedule Summary

| Schedule | Task |
|---|---|
| Daily 00:00 | Academic calendar phase check |
| Daily 00:30 | KPI snapshot refresh |
| Daily 02:30 UTC | Admissions reporting gate deadline check |
| Daily 03:00 UTC | Database backup (pg_dump → MinIO) |
| Daily 09:00 | Fee overdue check (admissions offers) |
| Daily 09:05 | Invoice overdue check |
| Every hour | Send pending notification reminders |
| Every 5 min | Retry failed domain events |
| Every 30 sec | Retry stuck critical events (FINANCE, EXAMINATION topics) |
| Every 5 min | Webhook retry |
| Every 5 min | Drillbit plagiarism result polling |
| Weekly Sun 01:00 UTC | LMS grade sync |
| Annually 1 July 06:00 | AQAR annual draft compilation |

### Celery Configuration
- Serializer: JSON
- Result expiry: 3600 seconds
- Timezone: Asia/Kolkata (IST)
- `task_acks_late = True` — re-queue on worker crash
- `task_reject_on_worker_lost = True`
- `worker_prefetch_multiplier = 1` — fair dispatch
- Max retries: 3, retry delay: 60 seconds

---

## 9. Python Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.0 | Web framework |
| `uvicorn[standard]` | 0.30.6 | ASGI server |
| `python-multipart` | 0.0.9 | File upload support |
| `pydantic` | ≥2.9.0,<3.0 | Data validation + settings |
| `pydantic-settings` | ≥2.4.0 | Environment variable settings |
| `psycopg2-binary` | 2.9.9 | PostgreSQL sync driver |
| `asyncpg` | 0.29.0 | PostgreSQL async driver (FastAPI handlers) |
| `alembic` | 1.13.2 | Database migrations |
| `sqlalchemy` | 2.0.35 | Alembic env only |
| `celery[redis]` | 5.4.0 | Async task queue |
| `redis` | 5.0.8 | Redis client (sessions, cache, broker) |
| `langgraph` | 1.1.2 | Agent orchestration framework |
| `langchain-core` | ≥1.2.18 | LLM abstraction layer |
| `langchain-ollama` | 0.3.10 | Ollama LangChain integration |
| `langchain-openai` | 1.1.11 | OpenAI-compatible API (NVIDIA NIM, OpenAI) |
| `openai` | 2.28.0 | OpenAI SDK (OpenAI-compatible APIs) |
| `httpx` | 0.27.2 | HTTP client (Ollama + test client) |
| `minio` | 7.2.8 | MinIO / S3-compatible storage |
| `reportlab` | 4.2.2 | PDF generation (grade cards, certificates) |
| `openpyxl` | 3.1.5 | Excel export (M8 reports) |
| `razorpay` | 1.4.1 | Payment gateway SDK |
| `python-jose[cryptography]` | 3.3.0 | JWT creation / verification |
| `passlib[bcrypt]` | 1.7.4 | Password hashing |
| `pyotp` | 2.9.0 | TOTP / MFA |
| `cryptography` | 43.0.1 | Fernet encryption for TOTP secrets |
| `PyJWT` | 2.9.0 | MFA challenge token signing |
| `hvac` | 2.3.0 | HashiCorp Vault client |
| `prometheus-client` | 0.21.0 | Prometheus metrics |
| `sentry-sdk[fastapi]` | 2.14.0 | Error tracking (optional, set SENTRY_DSN) |
| `python-dateutil` | 2.9.0 | Date arithmetic utilities |
| `orjson` | 3.10.7 | Fast JSON serializer |
| `asteval` | 1.0.2 | Safe expression evaluator for Policy DSL |
| `bcrypt` | 4.2.0 | Password hashing (bcrypt) |
| `pytest` | 8.3.2 | Testing framework |
| `pytest-asyncio` | 0.23.8 | Async test support |
| `pytest-cov` | 5.0.0 | Coverage |
| `fakeredis` | 2.34.1 | In-memory Redis for unit tests |

---

## 10. Frontend Application

**Stack:** Vite 6 + React 19 + TypeScript + Tailwind CSS v4 + Radix UI

**Entry:** `web/src/main.tsx` → `web/src/App.tsx`

### Routes

| Path | Component | Access |
|---|---|---|
| `/login` | `LoginPage` | Public |
| `/apply` | `PortalHomePage` | Public |
| `/apply/application` | `ApplicationWizardPage` | Public |
| `/apply/status` | `ApplicationStatusPage` | Public |
| `/apply/offer` | `OfferLetterPage` | Public |
| `/guardian` | `GuardianPortalPage` | Public (OTP auth) |
| `/attendance/mark/:sessionId` | `OfflineAttendancePage` | Public (PWA installable) |
| `/dashboard` | `RegistrarDashboard` | Protected |
| `/dashboard/faculty` | `FacultyDashboard` | Protected |
| `/dashboard/student` | `StudentDashboard` | Protected |
| `/dashboard/finance` | `FinanceDashboard` | Protected |
| `/dashboard/hod` | `HODDashboard` | Protected |
| `/dashboard/exam-controller` | `ExamControllerDashboard` | Protected |
| `/admissions` | `AdmissionsPage` | Protected |
| `/admissions/seat-matrix` | `SeatMatrixPage` | Protected |
| `/admissions/pipeline` | `AdmissionsModulePage` | Protected |
| `/admissions/readmission` | `ReadmissionPage` | Protected |
| `/academics` | `AcademicsPage` | Protected |
| `/academics/obe` | `OBEPage` | Protected |
| `/examinations` | `ExaminationsPage` | Protected |
| `/finance` | `FinancePage` | Protected |
| `/hr` | `HRPage` | Protected |
| `/students` | `StudentServicesPage` | Protected |
| `/communications` | `CommunicationHubPage` | Protected |
| `/reports` | `ReportsPage` | Protected |
| `/alumni` | `AlumniPage` | Protected |
| `/regulatory` | `RegulatoryPage` | Protected |
| `/admin/policies` | `PolicyStudioPage` | Protected (SUPER_ADMIN) |
| `/phd` | `PhDPage` | Protected |
| `/convocation` | `ConvocationPage` | Protected |
| `/workflows` | `WorkflowsPage` | Protected |
| `/process-engine` | `ProcessEnginePage` | Protected |
| `/consent` | `ConsentPage` | Protected |

### Shell Structure

`ALISShell` — three-column layout:
- Left: `IconNav` — module navigation icons
- Centre: `<Outlet />` — current page
- Right: `AgentRail` — AI agent chat thread + quick actions

### State Management

| Store | File | Purpose |
|---|---|---|
| Auth | `store/authStore.ts` | JWT token, user profile, tenant |
| ALIS | `store/alis.store.ts` | Global app state, agent canvas sync |

### Key Hooks

| Hook | File | Purpose |
|---|---|---|
| `useALISRole` | `hooks/useALISRole.ts` | Current user role + permissions |
| `useAgentCanvasSync` | `hooks/useAgentCanvasSync.ts` | Sync agent suggestions to canvas |
| `useQuickActions` | `hooks/useQuickActions.ts` | Role-based quick action buttons |
| `use-alumni` | `hooks/use-alumni.ts` | Alumni + placement data |
| `use-communication` | `hooks/use-communication.ts` | Notification + bulk message |
| `use-reporting` | `hooks/use-reporting.ts` | KPI + report queries |

### Key Components

| Component | Purpose |
|---|---|
| `ApprovalRow` | Approval request row with approve/reject actions |
| `Badge` | Status badge (PENDING, APPROVED, etc.) |
| `DataTable` | Generic sortable/filterable table |
| `RiskBar` | Attendance / risk percentage bar |
| `SLABar` | SLA deadline progress bar |
| `StatCard` | KPI metric card |
| `UndoToast` | Undo-able action toast notification |

### Services (API clients)

| Service | File | Endpoints covered |
|---|---|---|
| `alumni` | `services/alumni.ts` | Alumni + placement |
| `communication` | `services/communication.ts` | Notifications + bulk |
| `reporting` | `services/reporting.ts` | KPI + reports |

---

## 11. Frontend Dependencies

### Runtime
| Package | Version | Purpose |
|---|---|---|
| `react` | ^19.0.0 | UI framework |
| `react-dom` | ^19.0.0 | DOM rendering |
| `react-router-dom` | ^7.1.1 | Client-side routing |
| `@tanstack/react-query` | ^5.62.3 | Server state management + caching |
| `zustand` | ^5.0.2 | Client state management |
| `tailwindcss` | ^4.0.0 | Utility-first CSS |
| `@tailwindcss/vite` | ^4.0.0 | Tailwind Vite plugin |
| `@radix-ui/react-*` | various | Accessible headless UI components |
| `framer-motion` | ^11.12.0 | Animations |
| `lucide-react` | ^0.468.0 | Icon library |
| `zod` | ^3.24.1 | Schema validation |
| `clsx` / `tailwind-merge` | latest | Class name utilities |
| `class-variance-authority` | ^0.7.1 | Component variant system |
| `dexie` | ^4.3.0 | IndexedDB wrapper (offline PWA attendance) |
| `i18next` | ^25.8.19 | Internationalization |
| `react-i18next` | ^16.5.8 | React i18n bindings |
| `vite-plugin-pwa` | ^1.2.0 | Progressive Web App support |

### Dev
| Package | Purpose |
|---|---|
| `vite` ^6.0.5 | Build tool |
| `typescript` ~5.7.2 | Type checking |
| `@vitejs/plugin-react` | React fast refresh |
| `eslint` + plugins | Linting |

---

## 12. Security Model

### Authentication Flow

```
1. POST /auth/login → verify password (bcrypt) → check if MFA required
2a. MFA NOT required → issue access_token (60 min) + refresh_token (7 days) → store session in Redis
2b. MFA required → issue mfa_challenge_token (5 min, short-lived JWT)
3b. POST /auth/login/mfa → verify TOTP code → issue full tokens
4. Every request → TenantMiddleware extracts JWT → sets tenant context in ContextVar
5. Route handler → RBAC+ check → DB query with RLS enforced
6. POST /auth/refresh → validate refresh_token → issue new access_token
7. POST /auth/logout → delete session from Redis
```

### Redis Key Prefixes
| Prefix | Purpose |
|---|---|
| `alis:sess:{token}` | Session data |
| `alis:tok:{token}` | Token → user mapping |
| `alis:user_sess:{user_id}` | All sessions for a user |
| `alis:fail:{identifier}` | Failed login counters |
| `alis:lockout:{identifier}` | Locked account markers |
| `alis:rate:{identifier}` | Rate limiting counters |

### Row-Level Security (RLS) — Tables with RLS Enabled

| Table | Policy | Column |
|---|---|---|
| `students` | tenant isolation | `org_id` |
| `student_invoices` | tenant isolation | `org_id` |
| `applicants` | tenant isolation | `org_id` |
| `audit_ledger` | INSERT + SELECT only; UPDATE/DELETE blocked by trigger | `tenant_id` |
| `leads` | tenant isolation | `org_id` |
| `workflow_tasks` | tenant isolation | `org_id` |
| + all other entity tables | tenant isolation | `org_id` |

### Vault (HashiCorp) Usage
- **Transit engine** — encrypt/decrypt exam paper content (CoE role required for decrypt)
- **KV engine** — store integration secrets (Razorpay keys, Drillbit API key, etc.)
- Dev mode: root token. Production: AppRole + wrapped token.

### Security Headers (all responses)
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### Nginx Security
- Rate limiting: API routes `10r/s` burst `20`, auth routes `5r/s` burst `10`
- CSP header on frontend routes
- TLS termination (self-signed cert in dev; replace with Let's Encrypt / org cert in prod)
- `/metrics` endpoint blocked from external access (internal only)

---

## 13. AI Stack

### Models (Ollama — all local)

| Tier | Model | Use Cases |
|---|---|---|
| EXTRACTION | `qwen2.5:1.5b-instruct-q8_0` | JSON extraction, slot filling, structured output, classification |
| GENERATION | `qwen2.5:7b-instruct` | Document drafting, email composition, briefing summaries |
| REASONING | `qwen2.5:14b-instruct` | Eligibility decisions, risk scoring, complex multi-step logic |
| EMBEDDING | `nomic-embed-text` | PGVector embeddings, semantic search, counsellor allocation |

External override: set `LLM_API_KEY` + `LLM_API_BASE_URL` to route to NVIDIA NIM or OpenAI.

### LLM Router (`server/core/llm_router.py`)
- Selects model tier based on task type
- Falls back to Ollama if external API unavailable
- All invocations logged to `audit_ledger` with token counts

### AI Gateway (`server/api/gateway_router.py`)
- Single entry point — no module calls LLM directly
- Guardrails: output schema validation, PII stripping before logging
- HITL checkpoints: AI output status = DRAFT until human approves

### Tool Registry (`server/tools/`)
- AI agents access business functions via typed tool definitions
- Tools: read student data, check eligibility, draft documents, look up policies
- Write tools require HITL approval before execution

### MCP Server (`server/mcp/`)
- Exposes ALIS as an MCP server for external agent frameworks
- Enables Claude Desktop and other MCP clients to interact with ALIS data

### Policy Authoring Agent
- Takes plain English description → generates policy DSL JSON
- Always produces DRAFT status — cannot activate without human APPROVE
- Never directly modifies `institution_policies` table

### PGVector Usage
- Counsellor allocation: embed applicant profile → find closest available counsellor
- Document RAG: embed regulatory criteria → find relevant evidence
- Semantic search in alumni directory

---

## 14. RBAC — Roles & Permissions

### Human Roles

| Role | Key Permissions |
|---|---|
| `student` | student:read, course:read, marks:read, fee:read, notification:read, service:read, alumni:read |
| `faculty` | student:read, course:read, marks:read, marks:entry, notification:read |
| `hod` | All faculty permissions + course:create/update, marks:finalize, override:request, escalation:request |
| `registrar` | student full CRUD, hall_ticket:generate, result:publish, override:approve, policy:read, report:read/export, process:manage |
| `finance_officer` | fee full CRUD, payment:process, ledger:read, override:request, dual_control:approve |
| `admin` | user management, config, audit, override:approve, escalation management, policy full CRUD, feature_flag:manage |
| `super_admin` | All permissions |
| `dean_elevated` | Temporary elevated role granted via escalation workflow |

### Module Manager Roles (M1–M9)
Each manager owns their module's permissions + can create dynamic roles within their scope.

| Role | Module |
|---|---|
| `m1_manager` | M1 — Admissions & Marketing |
| `m2_manager` | M2 — Academics |
| `m3_manager` | M3 — Examinations |
| `m4_manager` | M4 — Finance |
| `m5_manager` | M5 — HR & Payroll |
| `m6_manager` | M6 — Student Services |
| `m7_manager` | M7 — Communication Hub |
| `m8_manager` | M8 — Reporting & Analytics |
| `m9_manager` | M9 — Alumni & Placement |

### System Roles
| Role | Permissions |
|---|---|
| `ai_agent` | READ only (student, course, marks, fee) + global_lock:check + ai:invoke. Cannot write. Cannot override tenant context. |
| `system` | All permissions (internal operations only) |

### Full Permission Catalog
`user:read/create/update/delete` · `student:read/create/update/read_pii` · `academics:read/manage` · `course:read/create/update` · `marks:read/entry/finalize` · `fee:read/create` · `payment:process` · `ledger:read` · `exam_paper:read/create` · `hall_ticket:generate` · `result:publish` · `override:request/approve` · `audit_log:read` · `config:read/write` · `global_lock:check` · `ai:invoke` · `escalation:request/grant/revoke` · `dual_control:approve` · `retention:manage/hard_delete` · `policy:draft/submit/approve/read` · `staff:read/create/update` · `leave:approve` · `payroll:read/process` · `service:read/manage` · `hostel:manage` · `transport:manage` · `notification:read/manage` · `announcement:create` · `bulk_message:send` · `report:read/create/export` · `alumni:read/manage` · `placement:manage` · `compliance:read/submit` · `grievance:manage` · `research:read/create/submit` · `process:read/manage` · `phd:read/manage` · `role:create/manage/approve` · `system:read` · `feature_flag:read/manage` · `convocation:read/manage`

---

## 15. Configuration Reference

All environment variables with their defaults (set in `.env`):

### Application
| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | development / staging / production |
| `APP_SECRET_KEY` | (must change) | General app secret |
| `APP_DEBUG` | `false` | Debug mode |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS allowed origins |

### Database
| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `alis_db` | Database name |
| `DB_USER` | `postgres` | DB user |
| `DB_PASSWORD` | `postgres` | DB password |
| `DB_POOL_MIN` | `2` | Connection pool min |
| `DB_POOL_MAX` | `20` | Connection pool max |

### Redis
| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis DB index |

### JWT Auth
| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | (must change in prod) | HS256 signing key |
| `JWT_ALGORITHM` | `HS256` | HS256 or RS256 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `JWT_RSA_PRIVATE_KEY` | — | PEM key for RS256 |
| `JWT_RSA_PUBLIC_KEY` | — | PEM key for RS256 |

### AI / Ollama
| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_EXTRACTION_MODEL` | `qwen2.5:1.5b-instruct-q8_0` | Extraction tier |
| `OLLAMA_GENERATION_MODEL` | `qwen2.5:7b-instruct` | Generation tier |
| `OLLAMA_REASONING_MODEL` | `qwen2.5:14b-instruct` | Reasoning tier |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `LLM_API_KEY` | — | External LLM API key (overrides Ollama) |
| `LLM_API_BASE_URL` | — | External LLM base URL |

### Storage / MinIO
| Variable | Default | Description |
|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO S3 endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | Access key |
| `MINIO_SECRET_KEY` | `minioadmin` | Secret key |
| `MINIO_BUCKET` | `alis-files` | Default bucket |

### Vault
| Variable | Default | Description |
|---|---|---|
| `VAULT_ADDR` | `http://localhost:8200` | Vault server |
| `VAULT_TOKEN` | `alis-dev-root-token` | Vault token (AppRole in prod) |

### Payment
| Variable | Default | Description |
|---|---|---|
| `RAZORPAY_KEY_ID` | — | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | — | Razorpay key secret |
| `RAZORPAY_WEBHOOK_SECRET` | — | **Required for webhook HMAC verification** |
| `PAYMENT_GATEWAY_ENABLED` | `false` | Enable payment gateway |

### Notifications
| Variable | Default | Description |
|---|---|---|
| `SMTP_HOST` | `localhost` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` / `SMTP_PASSWORD` | — | SMTP credentials |
| `SMS_PROVIDER` | `MSG91` | MSG91 or TWILIO |
| `SMS_GATEWAY_ENABLED` | `false` | Enable SMS |

### Integrations
| Variable | Description |
|---|---|
| `DIGILOCKER_CLIENT_ID/SECRET` | DigiLocker OAuth |
| `NTA_API_KEY` | NTA score import |
| `LMS_BASE_URL` / `LMS_API_TOKEN` | Moodle / Canvas |
| `DRILLBIT_API_KEY` | Plagiarism detection (PhD module) |
| `NIC_EINVOICE_*` | GST e-Invoice API |

### Observability
| Variable | Default | Description |
|---|---|---|
| `SENTRY_DSN` | — | Sentry DSN (leave empty to disable) |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.05` | 5% transaction sampling |

---

## 16. Production Quality Rules

### Code Rules (every .py file)
1. `from __future__ import annotations` must be the first non-docstring line
2. FastAPI DELETE routes with `status_code=204` must have `response_model=None`
3. DomainEventBus handlers use `subscribe()`, never decorator-style `register_handler()`
4. Config files (alertmanager.yml, nginx.conf, loki-config.yml) use literal values — no `${VAR:-default}` shell syntax

### Database Rules — Never Violate
1. **No raw status updates** — all transitions through state machine (`applicant_state_machine.transition()`)
2. **No hardcoded thresholds** — read from `institution_policies` via `policy_engine.get_value()`
3. **No audit ledger mutations** — append only; `UPDATE`/`DELETE` blocked by DB trigger
4. **execute_query** = SELECT only; **execute_transaction** = INSERT/UPDATE/DELETE

### The Hardcoding Prevention Question
> *"Could a VC, Registrar, or Finance Officer ever need to change this without calling QUAICU?"*

If yes → goes in `institution_policies`, `workflow_definitions`, `notification_templates`, or `document_templates` in the database. Never in code.

### 12 Hardcoding Prevention Rules
| Rule | What |
|---|---|
| R1 | No hardcoded thresholds (attendance %, merit cutoffs, grade boundaries) |
| R2 | No hardcoded approval chains (approval required roles, quorum counts) |
| R3 | Absolute TIMESTAMPTZ SLAs (not relative "7 days") |
| R4 | No hardcoded role names in business logic |
| R6 | State machines for all entity lifecycle transitions |
| R7 | Policy DSL for eligibility evaluation |
| R8 | No hardcoded notification content |
| R9 | No hardcoded document formats |
| R10 | No hardcoded regulatory mappings |
| R11 | Feature flags from DB (not code conditionals) |
| R12 | Policy versioning on every decision |

### Weekly Verification Checklist
```bash
# 1. All containers healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Real database integration tests (14/14 must pass)
docker exec alis_app python -m pytest tests/test_integration_real_db.py -v --tb=short

# 3. No hardcoded thresholds in business logic (must return 0)
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ | grep -v test | grep -v migration

# 4. No raw status updates bypassing state machine (must return 0)
grep -rn --include='*.py' "SET status=" server/ | grep -v test | grep -v migration

# 5. No direct LLM calls outside AI Gateway (must return 0)
grep -rn --include='*.py' "ollama\.\|openai\.\|anthropic\." server/ | grep -v ai_gateway | grep -v test
```

---

*QUAICU Solutions Private Limited | ALIS OS v1.0 | March 2026 | Confidential*
*Document generated: 2026-03-20*
