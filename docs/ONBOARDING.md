# ALIS OS — New Team Member Onboarding

> Last updated: 2026-04-13

Welcome to ALIS. This guide gets you productive as fast as possible.

---

## Step 1: Read These First

| Priority | Document | What You'll Learn |
|----------|----------|------------------|
| 🔴 Must | [CONTRIBUTING.md](../CONTRIBUTING.md) | Branch strategy, PR rules, code review |
| 🔴 Must | [CODEBASE_MAP.md](./CODEBASE_MAP.md) | Every file and folder explained |
| 🟡 Role | [ALIS_SYSTEM_DOCUMENTATION.md](./ALIS_SYSTEM_DOCUMENTATION.md) | Full backend architecture (Backend + AI interns) |
| 🟡 Role | [ALIS_FRONTEND_SPEC.md](./ALIS_FRONTEND_SPEC.md) | Frontend architecture (Frontend intern) |
| 🟢 Ref | [Architecture Overview](./architecture/overview.md) | Mermaid diagrams of system topology |
| 🟢 Ref | [API Versioning](./api-versioning.md) | How API versions work |

---

## Step 2: Environment Setup

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Git | Latest | Version control |
| Docker Desktop | Latest | Run all services |
| Python | 3.11+ | Backend development |
| Node.js | 20 LTS | Frontend development |
| VS Code / Cursor | Latest | Recommended IDE |

### Clone & Setup

```bash
# Clone the repository
git clone <repository-url>
cd "ALIS Production"

# Copy environment config
cp .env.example .env
# Edit .env with your local settings (the team lead will provide values)

# Start all services
docker compose up -d

# Verify services are running
curl http://localhost:8000/health   # Backend
curl http://localhost:8001/health   # Control Plane
curl http://localhost:8002/health   # AI Service
```

### Frontend-Specific Setup

```bash
cd web
npm install
npm run dev
# Open http://localhost:5173
```

### Backend-Specific Setup

```bash
cd ALIS
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Seed sample data
python scripts/seed.py
```

---

## Step 3: Understand the Architecture

ALIS is a **3-service microservice** system:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Frontend   │────▶│  Data Plane   │────▶│ AI Service  │
│ React (5173) │     │ FastAPI(8000) │     │ FastAPI(8002)│
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                    ┌──────────────┐
                    │Control Plane │
                    │ FastAPI(8001)│
                    └──────────────┘
```

| Service | Port | Directory | You Touch If You're... |
|---------|------|-----------|----------------------|
| Frontend (React SPA) | 5173 (dev) | `web/` | Frontend Intern |
| Data Plane (main API) | 8000 | `ALIS/server/` | Backend + AI Interns |
| Control Plane (SaaS) | 8001 | `control_plane/` | Senior AI Dev only |
| AI Service | 8002 | `ai_service/` | AI Intern + Senior |

---

## Step 4: Your Role-Specific Guide

### 🤖 AI Agents Intern

**Your focus:** Build and improve AI agents that evaluate, recommend, and assist.

**Your directories:**
- `ALIS/server/agents/` — agent implementations
- `ALIS/server/core/ai_gateway.py` — understand this, don't modify without approval
- `ALIS/server/core/guardrails.py` — output validation rules
- `ALIS/server/core/prompt_registry.py` — prompt templates

**Key rules:**
- Every agent MUST route through `AIGateway.invoke()`
- Agent outputs MUST include `confidence` and `state_impact`
- `state_impact` can only be `DRAFT` or `PROVISIONAL` — never `FINAL`
- Read the `alis-agent-builder` skill doc before writing any agent

**Start with:** Read `ALIS/server/agents/eligibility_agent.py` as a reference implementation.

---

### ⚙️ Backend Intern

**Your focus:** API endpoints, services, domain logic, database migrations.

**Your directories:**
- `ALIS/server/api/` — API routers
- `ALIS/server/admissions/`, `server/academics/`, etc. — domain modules
- `ALIS/server/tasks/` — Celery background tasks
- `ALIS/migrations/` — Alembic migrations

**Key rules:**
- `execute_query()` for reads, `execute_transaction()` for writes
- Every endpoint needs `@require_permission()` decorator
- Every write needs `AuditLedger.log()`
- All queries MUST be scoped by `org_id` (tenant isolation)
- Read the `alis-backend-patterns` skill doc first

**Start with:** Read `ALIS/server/api/auth_router.py` and `ALIS/server/admissions/lead_service.py` as reference.

---

### 🎨 Frontend Intern

**Your focus:** React pages, components, hooks, design system.

**Your directories:**
- `web/src/pages/` — page components
- `web/src/components/` — shared components
- `web/src/hooks/` — custom React hooks
- `web/src/services/` — API service layer

**Key rules:**
- Use `apiFetch()` for all API calls — never raw `fetch()`
- Use `useALISRole()` for role-based rendering
- Follow the design token system in `src/index.css`
- No new npm packages without approval
- Read the `alis-frontend-developer` skill doc first

**Start with:** Read `web/src/App.tsx` for routing and `web/src/hooks/useALISRole.ts` for role system.

---

### 🧠 Senior AI Developer

**Your scope:** Architecture decisions, code reviews, AI infrastructure.

**Your directories:** All, with primary focus on:
- `ALIS/server/core/` — core infrastructure
- `ai_service/` — centralized AI inference
- `control_plane/` — SaaS tenant management
- Architecture and design decisions

**Responsibilities:**
- Review ALL pull requests before merge
- Approve any new dependency additions
- Make architecture decisions
- Manage deployment pipeline
- Mentor interns on ALIS patterns

---

## Step 5: First Contribution

1. Pick a task assigned to you
2. Create a branch: `git checkout -b feat/<module>/<task-name>`
3. Make your changes following the rules above
4. Run lint: `ruff check` (backend) or `npx eslint src/` (frontend)
5. Commit with conventional format: `feat(module): description`
6. Push and create a PR targeting `develop`
7. Request review from the Senior AI Developer

---

## Need Help?

- **Architecture questions** → Senior AI Developer
- **Blocked on setup** → Flag immediately in standup
- **Not sure where code belongs** → Check [CODEBASE_MAP.md](./CODEBASE_MAP.md)
- **Not sure about a pattern** → Check the `.agents/skills/` directory for relevant skill docs
