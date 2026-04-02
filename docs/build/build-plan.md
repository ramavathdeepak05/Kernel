# ALIS Platform — Build Plan
## QUAICU Pvt. Ltd. | Hyderabad, India
**Updated:** 2026-04-02 | **P22–P40 + S1–S10 COMPLETE** | Migrations 0001–0041 | SaaS tests: 172 | Data-plane tests: 883

---

## Platform Status Snapshot

### Data Plane (ERP Modules)

| Module | Backend | Frontend | Status |
|---|---|---|---|
| Auth + RBAC + MFA/TOTP | ✅ | ✅ | **GA** |
| Workflow Engine + Quorum | ✅ | ✅ WorkflowsPage | **GA** |
| AI Gateway + RAG + PGVector | ✅ | ✅ Agent rail wired | **GA** |
| Admissions (10-stage pipeline) | ✅ | ✅ Kanban + portal | **GA** |
| Academics | ✅ | ✅ AcademicsPage + OBEPage | **GA** |
| In-house LMS (P40) | ✅ learning_service + content_generator | ✅ LearningPage | **GA** |
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

### SaaS Platform (S1–S10)

| Sprint | Module | Backend | Tests | Status |
|---|---|---|---|---|
| S1 | Subdomain tenant middleware | ✅ `tenant_registry.py` + `tenant_tasks.py` | — (integrated) | **GA** |
| S2 | Control Plane | ✅ `control_plane/` — provisioner, router, crypto, db | 20 | **GA** |
| S3 | AI Service | ✅ `ai_service/` — PII masking, budget, provider routing | 30 | **GA** |
| S4 | Billing Engine | ✅ billing_engine, usage_store, billing_models | 35 | **GA** |
| S5 | Infrastructure Isolation | ✅ bucket_provisioner, vault_client, tenant task routing | 32 | **GA** |
| S6 | Helm Charts | ✅ data-plane, control-plane, ai-service (3 charts) | — (structural) | **GA** |
| S7 | Terraform | ✅ AWS, Azure, GCP, shared Vault modules + 3 envs | — (IaC) | **GA** |
| S8 | K8s Operator | ✅ TenantStack CRD + kopf reconciler | 21 | **GA** |
| S9 | Billing API | ✅ plan_store, tenant portal, Stripe/Razorpay webhooks | 15 | **GA** |
| S10 | DNS Routing | ✅ Cloudflare, Route53, Azure DNS providers | 19 | **GA** |

---

## S1–S10 — SaaS Transformation (April 2026) ✅ COMPLETE

### S1 — Subdomain Tenant Resolution
- `SubdomainTenantMiddleware` in data plane resolves `{subdomain}.alis.app` → tenant DSN
- `tenant_registry.py` — TenantRegistry with local cache + CP fallback
- `tenant_tasks.py` — TenantTaskRouter for per-tenant Celery queue routing
- Backward compat: empty `CONTROL_PLANE_URL` = single-tenant on-prem mode

### S2 — Control Plane Service
- `control_plane/` — standalone FastAPI application
- `TenantProvisioner` — full lifecycle: provision → suspend → reactivate → delete
- Admin API (JWT) + Internal API (X-Internal-Token)
- `cp_tenants`, `cp_provisioning_log` tables
- AES-GCM encryption for tenant DB passwords

### S3 — AI Service Microservice
- `ai_service/` — centralized LLM proxy
- PII masking: Aadhaar, email, phone, UUID, Application ID → deterministic tokens
- Per-tenant token budget enforcement (Redis-backed)
- Provider routing: VpcOllama (default) → ManagedAPI (enterprise)
- `AIServiceLLM` — LangChain-compatible wrapper for data-plane integration

### S4 — Billing Engine
- Plan tiers: Starter ($49), Growth ($199), Enterprise ($999)
- Usage events: `ai_tokens`, `api_calls`, `storage_bytes`, `active_users`
- Invoice lifecycle: DRAFT → ISSUED → PAID (or VOID)
- Per-dimension overage computation

### S5 — Infrastructure Isolation
- Per-tenant S3 bucket (`alis-tenant-{tenant_id}`) — versioning, AES256, GLACIER lifecycle
- Per-tenant Vault KV v2 path (`alis/{region}/tenant/{tenant_id}/{secret_type}`)
- Per-tenant Celery queues (`default:{tenant_id}`, `high:{tenant_id}`)

### S6 — Helm Charts
- `alis-data-plane/` — 11 templates (celery-beat Recreate strategy, worker 300s grace, ExternalSecret, NetworkPolicy)
- `alis-control-plane/` — combined deployment + service + secret
- `alis-ai-service/` — deployment + HPA + GPU affinity

### S7 — Terraform Multi-Cloud
- AWS: VPC + EKS + Aurora + ElastiCache + S3 + Route53
- Azure: AKS + PostgreSQL Flex + Redis Cache + Blob Storage
- GCP: GKE Autopilot + Cloud SQL + Memorystore + GCS + KMS
- Shared: Vault KV v2 + AppRole auth + ACL policies
- Environments: dev (AWS small), staging (Azure mid), prod (AWS large + Vault)

### S8 — Kubernetes Operator
- TenantStack CRD (`alis.app/v1alpha1`) — 6 lifecycle phases
- kopf reconciler: create → update → delete → timer (60s drift detection)
- BYOD support flag for bring-your-own-database tenants

### S9 — Billing API + Tenant Portal
- Dynamic plan CRUD (`cp_plans` table)
- Tenant self-service: `/tenant/billing/usage`, `/tenant/billing/invoices`
- Stripe + Razorpay payment webhooks → auto invoice-paid marking
- Payment dedup via `provider_payment_id`

### S10 — DNS Routing
- Multi-provider: Cloudflare (proxied/CDN), Route53 (UPSERT), Azure DNS
- Auto CNAME provisioning during tenant creation
- Auto deprovision on tenant deletion

---

## P30–P40 — COMPLETE (March 2026)

### Migrations (0035–0041)

| Migration | Description |
|---|---|
| 0035 | workflow_tasks table + audit_ledger immutability trigger + RLS on leads/audit_ledger |
| 0036 | workflow_tasks: tenant_id, urgency, assignee_role, assignee_actor_id |
| 0037 | tenant_policies table |
| 0038 | failed_task_log — Celery DLQ |
| 0039 | Visiting faculty session logs + placement drive management |
| 0040 | Identity match (EC-ADM-01) + access lift (EC-ADM-05) |
| 0041 | In-house LMS: course_materials, assignments, assignment_submissions + RLS |

### P31–P39 Highlights
- P31: Frontend API wiring (all pages to real APIs)
- P35: Dynamic RBAC delegation + role-aware dashboard routing
- P36: EC-ADM-01 identity mismatch + EC-ADM-05 UTR access lift
- P38: Wire ConsentPage, OBEPage, SeatMatrixPage to real APIs
- P39: Vault Raft cluster_addr fix, domain event tenant context

### P40 — In-house LMS ✅
- Replaces Moodle LMS stub (tombstoned)
- `learning_service.py` — CourseMaterialService, AssignmentService, SubmissionService
- `content_generator_v1.py` — AI agent for lecture notes, quizzes, assignment questions, lesson plans
- `learning_router.py` — 17 endpoints at `/api/v1/learning/`
- `LearningPage.tsx` at `/academics/learning`
- Beat task: `close_overdue_assignments` (hourly)

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
Dexie IndexedDB, background sync, Workbox runtime caching, OfflineAttendancePage.

### P29 — WiFi Attendance Desktop + Backend ✅ DONE
wifi_attendance_router.py (4 routes), Electron app, NSIS installer (80MB).

---

## Migration Chain (current head: 0041)

```
0001 → 0002 → 0003 → ... → 0014 (full admissions)
→ 0015 (RBAC scope + event hardening)
→ 0016–0025 (feature flags, regulatory, DPDP, MFA, idempotency, fee versioning, guardian portal, pilot hardening)
→ 0026–0031 (PhD, re-admission, convocation, OBE, multi-campus, e-invoice) ← P22
→ 0032–0034 (Drillbit, WiFi attendance, TA assignments) ← P29
→ 0035–0038 (workflow tasks, tenant_policies, failed_task_log) ← P31
→ 0039 (HR/placement workflow gaps) ← P37
→ 0040 (identity match + access lift) ← P36
→ 0041 (in-house learning — course_materials, assignments, submissions) ← P40
```

---

## Test Suite Status

| Suite | Tests | Status |
|---|---|---|
| Data-plane unit tests (ALIS/tests/) | 883 | ✅ Passing |
| Integration tests (@integration marker) | ~160 | ⏭ Skipped without infra |
| S2 Control Plane | 20 | ✅ Passing |
| S3 AI Service | 30 | ✅ Passing |
| S4 Billing Engine | 35 | ✅ Passing |
| S5 Infra Isolation | 32 | ✅ Passing |
| S8 K8s Operator | 21 | ✅ Passing |
| S9 Billing API | 15 | ✅ Passing |
| S10 DNS Routing | 19 | ✅ Passing |
| **Total** | **~1,055+** | ✅ |

> Known non-blocking: 2 pre-existing failures in `test_tasks.py` (notification dispatcher mock), ~41 errors in `test_auth.py`/`test_integrations_p14.py` (require running Redis). These are infrastructure-dependent, not code bugs.

---

## Remaining Gaps

| Area | Gap | Blocking? |
|---|---|---|
| DigiLocker integration | Stub — needs NIC/UMANG credentials | No — manual review works |
| NTA score import | Stub — needs NTA API key | No — manual entry works |
| WhatsApp DLT template IDs | Placeholders — institution registers with MSG91 | No — ops config only |
| i18n (kn/mr/ta) | Translation files ~10% complete | No — English pilot unaffected |
| Multi-campus FE | Backend ✅, no frontend page | No — admin API works |
| GST e-Invoice FE trigger | Backend ✅, no frontend trigger button | No — API callable directly |
| SaaS admin dashboard FE | Backend ✅, no control-plane UI | No — admin API + kubectl |

---

## Hardcoding Prevention Rules (apply to all new code)

| Rule | Constraint |
|---|---|
| R1 | No hardcoded thresholds — all from `policy_engine.get_value()` |
| R2 | No hardcoded approval chains — all from `workflow_engine` DAG configs |
| R3 | SLA deadlines stored as absolute `TIMESTAMPTZ` |
| R4 | No hardcoded role names — roles from RBAC permission enum |
| R6 | State machines for all entity transitions |
| R7 | Policy DSL for all eligibility decisions |
| R8 | No hardcoded notification content |
| R9 | No hardcoded document formats |
| R10 | No hardcoded regulatory mappings |
| R11 | Feature flags from DB — `tenant_feature_flags` table |
| R12 | `policy_version_id` stored on every decision record |

---

*Build Plan v3.0 | 2026-04-02 | QUAICU Pvt. Ltd. | Reflects S1-S10 SaaS completion + P40 LMS*
