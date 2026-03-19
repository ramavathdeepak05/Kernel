# ALIS — Autonomous Institution Management System

AI-native, sovereign University Operating System.
Policy-driven, event-sourced, local-first.
Developed by QUAICU Solutions Private Limited in partnership with Woxsen University.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, PostgreSQL 16 + pgvector, asyncpg + psycopg2 |
| Task queue | Celery + Redis |
| AI | Ollama (`qwen2.5:1.5b-instruct-q8_0` + `nomic-embed-text`) |
| Object storage | MinIO |
| Secrets | HashiCorp Vault (Transit + KV v2) |
| Frontend | React 19 + TypeScript, Vite 7, Tailwind v4, Radix UI |
| Proxy | Nginx |

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
│   │   ├── core/                # RBAC, events, policy, audit, security, Vault
│   │   ├── admissions/          # 10-stage admissions workflow
│   │   ├── academics/           # Courses, timetable, syllabus
│   │   ├── examinations/        # Tests, grading, hall tickets
│   │   ├── finance/             # Fees, payments, exemptions, ledger
│   │   ├── hr/                  # Staff, payroll, leave
│   │   ├── student_services/
│   │   ├── communication/
│   │   ├── regulatory/
│   │   ├── consent/
│   │   ├── alumni/
│   │   ├── reporting/
│   │   └── process_engine/
│   ├── migrations/              # Alembic migrations (0001–0023)
│   └── tests/                   # 904 tests
│
├── web/                         # Frontend — React 19 / TypeScript (shared)
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
│       └── gaps.md              # Unbuilt epics (E15–E20)
│
├── docs/                        # Documentation
│   ├── architecture/            # System overview
│   ├── build/                   # Build plan and timelines
│   └── archive/                 # Historical references
│
├── partners/                    # Cross-institutional collaboration
│   └── woxsen/
│       ├── README.md            # Partner orientation
│       ├── legal/               # MCA, SOW, NDA, Project Agreement
│       ├── onboarding/          # Dev environment setup for Woxsen team
│       └── data/                # Anonymised datasets (not committed)
│
├── .agents/                     # Claude Code AI skill definitions
├── docker-compose.yml
├── .env.example
├── CONTRIBUTING.md
└── README.md
```

---

## Build Status

### Backend (FastAPI)
All 13 core epics complete. 846 tests passing.

| Epic | Module | Backend | Frontend |
|------|--------|---------|----------|
| E01 | Auth + RBAC + MFA/TOTP | ✅ | ✅ login/session |
| E02 | Workflow Engine + Approval Quorum | ✅ | — |
| E03 | AI Gateway + RAG + PGVector | ✅ | — |
| E04 | Admissions (10-stage, 87 routes) | ✅ | 🔲 pending |
| E05 | Academics | ✅ | ✅ |
| E06 | Examinations & Grades | ✅ | ✅ |
| E07 | Finance | ✅ | ✅ |
| E08 | HR & Staff | ✅ | ✅ |
| E09 | Student Services | ✅ | ✅ |
| E10 | Communication Hub | ✅ | ✅ |
| E11 | Reporting & Analytics | ✅ | ✅ |
| E12 | Alumni & Placement | ✅ | ✅ |
| E13 | Dynamic Process Engine | ✅ | — |
| E21 | DPDP Consent Management | ✅ | 🔲 pending |

### Phase 1 Hardening

| Task | Status |
|------|--------|
| EC-CROSS-01/02/03 — idempotency, audit RLS, tenant isolation | ✅ |
| MFA/TOTP — enroll, verify, trusted devices | ✅ |
| DPDP Consent — middleware, erasure, 451 enforcement | ✅ |
| Observability — Prometheus + Grafana + Loki | 🔲 pending |
| Fee structure versioning (intake_year lock) | 🔲 pending |
| Payment webhook idempotency + UTR disputes | 🔲 pending |
| EC-FIN-01/02 — DBT exemption + promissory ledger | 🔲 pending |
| E10 WhatsApp Business API (MSG91 + templates) | 🔲 pending |
| E16 Parent/Guardian portal | 🔲 pending |
| DigiLocker live integration | 🔲 pending |
| Data migration pipeline (validate → dry-run → commit) | 🔲 pending |

---

## Key Conventions

- API prefix: `/api/v1/`
- Money: `DECIMAL(12,2)` in DB, string in JSON, INR default
- IDs: UUID v4 everywhere
- Timestamps: `TIMESTAMPTZ` (UTC) in DB, ISO 8601 in API
- Tenant isolation: RLS via `SET LOCAL alis.current_tenant`
- Soft delete: `status='ARCHIVED'` (lifecycle) or `status='ANNULLED'` (state machine)

See `specs/SKILL.md` for full development reference and invariants.

---

## Partnership

ALIS is co-developed with Woxsen University under a Master Collaboration Agreement.
See `partners/woxsen/` for SOW, legal documents, and onboarding guides.

---

## License

Proprietary — QUAICU Solutions Private Limited. See `partners/woxsen/legal/` for terms.
