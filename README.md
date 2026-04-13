# ALIS — Autonomous Institution Management System

AI-native, sovereign University Operating System.
Policy-driven, event-sourced, local-first.
Developed by QUAICU Solutions Private Limited.

---

## 📚 Documentation & Onboarding

If you are a new team member, start here:
1. [**CONTRIBUTING.md**](./CONTRIBUTING.md) — Git workflow, PR rules, and coding standards.
2. [**ONBOARDING.md**](./docs/ONBOARDING.md) — Environment setup and role-specific guides.
3. [**CODEBASE_MAP.md**](./docs/CODEBASE_MAP.md) — Master map of every folder and critical file dependencies.
4. [**PRODUCTION_ROADMAP.md**](./docs/PRODUCTION_ROADMAP.md) — The path to v1 (Currently at **~75% completion**).

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, PostgreSQL 16 + pgvector, asyncpg (FastAPI) + psycopg2 (Celery workers) |
| Task queue | Celery + Redis |
| AI | Ollama (`qwen2.5:1.5b-instruct-q8_0` + `nomic-embed-text`) |
| Object storage | MinIO |
| Secrets | HashiCorp Vault (Transit + KV v2) — TTL-cached, fail-closed tiers |
| Frontend | React 19 + TypeScript, Vite 7, Tailwind v4, Radix UI |
| Proxy | Nginx |
| Control Plane | Standalone FastAPI microservice (tenant provisioning, billing, DNS) |
| AI Service | Standalone FastAPI microservice (PII masking, provider routing, budget) |

---

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env

# Start all services
docker compose up -d

# Run migrations
docker compose exec app alembic upgrade head

# Seed bootstrap data (org + SUPER_ADMIN + policies)
docker compose exec app python scripts/seed.py

# Run tests
docker compose exec app pytest
```

Default URLs:
- API: http://localhost:8000/api/v1/
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:5173
- Control Plane: http://localhost:8100
- AI Service: http://localhost:8200
- Grafana: http://localhost:3000 (admin / see `.env`)
- Prometheus: http://localhost:9090
- Vault: http://localhost:8200

---

## Repository Structure

```
ALIS Production/
├── ALIS/                        # Backend — Python / FastAPI (QUAICU)
│   ├── server/
│   │   ├── api/                 # FastAPI routers (one per module)
│   │   ├── core/                # RBAC, events, policy, audit, security, Vault,
│   │   │                        #   AI gateway, guardrails, HITL, model registry,
│   │   │                        #   prompt registry, shadow mode, lockdown,
│   │   │                        #   feature flags, tenant crypto, diff tracker
│   │   ├── admissions/          # 10-stage admissions workflow (87 routes)
│   │   ├── academics/           # Courses, timetable, syllabus, OBE/CO-PO
│   │   ├── examinations/        # Tests, grading, hall tickets
│   │   ├── finance/             # Fees, payments, exemptions, e-invoice, ledger
│   │   ├── hr/                  # Staff, payroll, leave, TA assignments
│   │   ├── student_services/    # Grievances, hostel, library, in-house learning
│   │   ├── communication/       # Email, WhatsApp, notifications
│   │   ├── regulatory/          # Accreditation, NAAC, statutory compliance
│   │   ├── consent/             # DPDP consent management
│   │   ├── alumni/              # Alumni tracking and placement
│   │   ├── reporting/           # Analytics and dashboards
│   │   ├── process_engine/      # Dynamic workflow engine
│   │   ├── phd/                 # PhD / Doctoral research module
│   │   ├── convocation/         # Convocation management
│   │   ├── agents/              # AI agent pipeline definitions
│   │   ├── rules/               # Rules-as-data engine
│   │   ├── integrations/        # DigiLocker, Drillbit, WiFi attendance, e-invoice
│   │   ├── mcp/                 # Model Context Protocol server
│   │   └── tools/               # Agent tool registry
│   ├── migrations/              # Alembic migrations (0001–0041)
│   └── tests/                   # Test suite (1 055+ tests)
│
├── web/                         # Frontend — React 19 / TypeScript
│   └── src/
│       ├── pages/               # Module screens (22 page areas)
│       │   ├── admissions/      ├── academics/   ├── examinations/
│       │   ├── finance/         ├── hr/          ├── student-services/
│       │   ├── communications/  ├── regulatory/  ├── alumni/
│       │   ├── reports/         ├── phd/         ├── convocation/
│       │   ├── consent/         ├── dashboard/   ├── auth/
│       │   ├── admin/           ├── attendance/  ├── settings/
│       │   ├── security/        ├── workflows/   ├── process-engine/
│       │   └── portal/
│       ├── components/          # Shared UI component library
│       ├── hooks/               # Module-specific TanStack Query hooks
│       ├── services/            # apiFetch service layer
│       ├── store/               # Zustand auth + global state
│       └── shell/               # App shell, sidebar, layout
│
├── control_plane/               # SaaS control plane microservice
│   ├── provisioner.py           # Tenant provisioning orchestration
│   ├── billing_engine.py        # Usage billing and plan enforcement
│   ├── dns_manager.py           # Subdomain / DNS provisioning
│   └── bucket_provisioner.py    # MinIO bucket per-tenant setup
│
├── ai_service/                  # AI gateway microservice
│   ├── providers.py             # Ollama / external LLM routing
│   ├── pii_masker.py            # PII masking before LLM calls
│   └── budget.py                # Per-tenant AI token budget
│
├── infra/                       # Infrastructure configuration
│   ├── nginx/                   # Reverse proxy config
│   └── monitoring/              # Prometheus, Grafana, Loki, Promtail
│
├── specs/                       # Platform specification (authoritative)
│   ├── SKILL.md                 # Master build guide and invariants
│   └── references/
│       ├── architecture.md      # Full system design
│       ├── frontend.md          # UI/UX spec and design system
│       ├── edge-cases.md        # Failure mode resolvers
│       └── gaps.md              # Unbuilt epics
│
├── docs/                        # Documentation
│   ├── CODEBASE_MAP.md          # Full codebase directory map
│   ├── ONBOARDING.md            # Developer setup guide
│   ├── PRODUCTION_ROADMAP.md    # Phased release plan and gap analysis
│   ├── ALIS_SYSTEM_DOCUMENTATION.md # Core architecture docs
│   ├── ALIS_FRONTEND_SPEC.md    # Frontend rebuild spec
│   ├── architecture/            # System overview block diagrams
│   └── archive/                 # Historical references
│
├── partners/                    # Cross-institutional collaboration
│   └── woxsen/
│       ├── README.md            # Partner orientation
│       ├── legal/               # MCA, SOW, NDA, Project Agreement
│       ├── onboarding/          # Dev environment setup for Woxsen team
│       └── data/                # Anonymised datasets (not committed)
│
├── scripts/                     # Seed, migration, and utility scripts
├── .agents/                     # AI skill definitions and workflows
├── docker-compose.yml
├── .env.example
├── CONTRIBUTING.md
└── README.md
```

---

## Build Status

### Backend (FastAPI)
All 21 core epics complete. **1 055+ tests passing.** 41 Alembic migrations shipped.
SaaS transformation (S1–S10) complete. Control Plane and AI Service microservices operational.

| Epic | Module | Backend | Frontend |
|------|--------|---------|----------|
| E01 | Auth + RBAC + MFA/TOTP | ✅ | ✅ login/session |
| E02 | Workflow Engine + Approval Quorum | ✅ | ✅ |
| E03 | AI Gateway + RAG + PGVector | ✅ | — |
| E04 | Admissions (10-stage, 87 routes) | ✅ | ✅ |
| E05 | Academics | ✅ | ✅ |
| E06 | Examinations & Grades | ✅ | ✅ |
| E07 | Finance | ✅ | ✅ |
| E08 | HR & Staff | ✅ | ✅ |
| E09 | Student Services | ✅ | ✅ |
| E10 | Communication Hub | ✅ | ✅ |
| E11 | Reporting & Analytics | ✅ | ✅ |
| E12 | Alumni & Placement | ✅ | ✅ |
| E13 | Dynamic Process Engine | ✅ | ✅ |
| E14 | Regulatory & Accreditation | ✅ | ✅ |
| E15 | PhD / Doctoral Research | ✅ | ✅ |
| E16 | Parent / Guardian Portal | ✅ | ✅ portal/ |
| E17 | Re-admission & Credit Transfer | ✅ | — |
| E18 | Convocation Management | ✅ | ✅ |
| E19 | Quota Seat Matrix Engine | ✅ | — |
| E20 | OBE / CO-PO Mapping | ✅ | — |
| E21 | DPDP Consent Management | ✅ | ✅ |

### Phase 1 Hardening

| Task | Status |
|------|--------|
| EC-CROSS-01/02/03 — idempotency, audit RLS, tenant isolation | ✅ |
| MFA/TOTP — enroll, verify, trusted devices | ✅ |
| DPDP Consent — middleware, erasure, 451 enforcement | ✅ |
| Observability — Prometheus + Grafana + Loki | ✅ |
| Fee structure versioning (intake_year lock) | ✅ |
| Payment webhook idempotency + UTR disputes | ✅ |
| EC-FIN-01/02 — DBT exemption + promissory ledger | ✅ |
| DigiLocker live integration | ✅ |
| Drillbit plagiarism integration | ✅ |
| WiFi attendance integration | ✅ |
| e-Invoice (GST) integration | ✅ |
| In-house learning module | ✅ |
| Identity match & access lift | ✅ |
| HR + placement workflow gaps | ✅ |
| Multi-campus support (migration 0030) | ✅ |
| Shadow mode (advisory-only AI dry-run) | ✅ |
| Model Context Protocol (MCP) server | ✅ |
| Control Plane microservice (SaaS provisioning + billing) | ✅ |
| AI Service microservice (PII masking + provider routing) | ✅ |
| E10 WhatsApp Business API (MSG91 + templates) | 🔲 pending |
| Guardian-initiated portal self-service flows | 🔲 pending |

---

### Phase 2 Architectural Hardening (April 2026)

| Item | Status |
|------|--------|
| Security fixes (20): tenant spoofing, RBAC bypass, session revocation, OTP atomicity | ✅ |
| `execute_query` / `execute_transaction` async-loop guard — psycopg2 enforced to Celery only | ✅ |
| `VaultClient` — TTL-based LRU cache (5 min), fail-closed critical tiers, `VaultUnavailableError` | ✅ |
| `/ready` health probe — Vault connectivity check added | ✅ |
| `AIGateway._extract_json` — upgraded to `JSONDecoder.raw_decode` (nested JSON) | ✅ |
| `PolicyEngine` — default verdict `INELIGIBLE`, cache serialization fixes | ✅ |
| `AuditLedger` — per-tenant async pool writes, chunked chain integrity (10 k rows) | ✅ |
| `INTERNAL_SERVICE_SECRET` guard on `X-Tenant-ID` header (tenant spoofing prevention) | ✅ |

---

## Key Conventions

- API prefix: `/api/v1/`
- Money: `DECIMAL(12,2)` in DB, string in JSON, INR default
- IDs: UUID v4 everywhere
- Timestamps: `TIMESTAMPTZ` (UTC) in DB, ISO 8601 in API
- Tenant isolation: RLS via `SET LOCAL alis.current_tenant`
- Soft delete: `status='ARCHIVED'` (lifecycle) or `status='ANNULLED'` (state machine)
- AI outputs: advisory-only (`AIResponse` with `confidence` + `state_impact`), never auto-committed
- Policy lifecycle: `DRAFT → SUBMITTED → ACTIVATED` via `PolicyService`
- All DB writes: `execute_transaction_async()` in FastAPI; `execute_transaction()` (psycopg2) in Celery workers only
- All DB reads: `execute_query_async()` in FastAPI; `execute_query()` in Celery workers only

See `specs/SKILL.md` for full development reference and invariants.

---

## License

Proprietary — QUAICU Solutions Private Limited. See `partners/woxsen/legal/` for terms.
