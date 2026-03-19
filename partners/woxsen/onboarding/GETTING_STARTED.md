# Getting Started — Woxsen Engineering Team
ALIS Platform  |  QUAICU x Woxsen Co-Development

---

## Before You Write Any Code

1. Read `legal/SOW.md` — understand exactly what Woxsen owns and what QUAICU owns.
2. Read `specs/references/architecture.md` — three invariants govern every line of code.
3. Read `specs/SKILL.md` — the 23 must-never-do rules and the five-question checklist.
4. Your IP Assignment Agreement must be signed and filed with Woxsen before your first commit.
5. Complete QUAICU's Platform onboarding session (coordinate with QUAICU Technical Lead).

---

## Repository Access

Woxsen engineers have access to the following paths only:

```
ALIS/server/          Backend source (read for context, write only in your modules)
web/src/              Frontend source (write for your dashboard/portal screens)
specs/                Platform specification (read only)
docs/                 Documentation (read only)
partners/woxsen/      Your workspace (full access)
```

Access to QUAICU's core AI orchestrator, Vault configuration, and infrastructure
secrets is restricted. Do not request elevated access outside your SOW scope.

---

## Development Environment Setup

### Prerequisites
- Docker Desktop (or Docker Engine + Compose v2 on Linux)
- Node.js 20+
- Python 3.11+
- Git

### Clone and start
```bash
git clone <repository-url>
cd "ALIS Production"
cp .env.example .env          # fill in values with QUAICU team
docker compose up -d          # starts Postgres, Redis, MinIO, Ollama
```

### Backend
```bash
cd ALIS
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
alembic upgrade head           # run all migrations
python scripts/seed.py         # seed base org + roles
uvicorn server.main:app --reload
```

### Frontend
```bash
cd web
npm install
npm run dev                    # starts at http://localhost:5173
```

### Run tests
```bash
cd ALIS
pytest                         # must be 100% green before any PR
```

---

## Contribution Rules

### Branch naming
```
woxsen/<phase>/<short-description>
# examples:
woxsen/phase4/faculty-dashboard
woxsen/phase5/phd-schema
woxsen/phase2/ec-admissions-identity-mismatch
```

### Before opening a PR
- [ ] `pytest` passes with no regressions
- [ ] New code has unit tests (happy path + failure path)
- [ ] No direct imports between modules (use domain events)
- [ ] No hardcoded tenant values
- [ ] No PII in log lines
- [ ] Sovereignty Test passes (test against local Docker stack with no internet)

### PR checklist (include in PR description)
```
- [ ] Linked SOW deliverable: [Phase X, item Y]
- [ ] Tests added/updated: yes
- [ ] Sovereignty Test: passed / not applicable
- [ ] UAT completed: yes / pending (frontend only)
- [ ] Domain expert sign-off: yes / not applicable (E14/E15/E18/E20 only)
```

---

## Architecture Quick Reference

**Never do this (cross-module direct call):**
```python
from server.finance.fee_service import FeeService   # WRONG
```

**Always do this (domain event):**
```python
await DomainEventBus.publish("student.enrolled", payload, tenant_id)
```

**Database writes:**
```python
await execute_transaction([(sql, params)])   # INSERT / UPDATE / DELETE
```

**Database reads:**
```python
await execute_query(sql, params)             # SELECT only
```

**Every query must include tenant_id in WHERE clause.** RLS is enforced at the
connection level — a missing tenant_id is a security defect, not a bug.

---

## Getting Help

- Architecture questions: QUAICU Technical Lead (see contacts in `partners/woxsen/README.md`)
- Domain / policy questions: your Woxsen IQAC Coordinator or Research Dean
- Access issues: QUAICU Project Manager

---

*QUAICU Solutions Private Limited — Confidential*
