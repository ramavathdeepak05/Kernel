# Contributing to ALIS OS

> **QUAICU Solutions Private Limited — Internal**
> Last updated: 2026-04-13

Welcome to the ALIS codebase. This guide defines how our team collaborates. **Read this fully before your first commit.**

---

## Team Structure

| Role | Scope | Primary Directories |
|------|-------|-------------------|
| **Senior AI Developer** | Architecture decisions, AI agents, code reviews, merge authority | `ALIS/server/core/ai_*`, `ALIS/server/agents/`, `ai_service/` |
| **AI Agents Intern** | AI agent implementation, prompt engineering, guardrails | `ALIS/server/agents/`, `ALIS/server/core/prompt_registry.py`, `ALIS/server/core/guardrails.py` |
| **Backend Intern** | API routes, services, domain modules, migrations | `ALIS/server/api/`, `ALIS/server/*/`, `ALIS/migrations/` |
| **Frontend Intern** | React pages, components, hooks, services | `web/src/` |

---

## Branch Strategy

```
main ← protected, always deployable
 └── develop ← integration branch, PRs merge here
      ├── feat/<module>/<short-description>
      ├── fix/<module>/<short-description>
      ├── refactor/<module>/<short-description>
      └── docs/<short-description>
```

### Rules

1. **Never push directly to `main` or `develop`** — always use Pull Requests
2. **Branch from `develop`**, not from `main`
3. **One feature per branch** — keep branches small and focused
4. **Delete branches after merge** — no stale branches

### Branch Naming Examples

```
feat/admissions/merit-list-caching
fix/finance/decimal-precision-payroll
refactor/core/async-audit-logging
docs/onboarding-guide
```

---

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short description>

[optional body]
```

### Types

| Type | When to Use |
|------|------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `chore` | Build, CI, tooling changes |
| `perf` | Performance improvement |

### Examples

```
feat(admissions): add document forgery detection agent
fix(finance): correct Decimal precision in payroll computation
refactor(core): migrate audit logging to async queue
docs: update onboarding guide with Docker setup
test(academics): add OBE attainment calculation tests
```

---

## Pull Request Workflow

### 1. Create Your Branch

```bash
git checkout develop
git pull origin develop
git checkout -b feat/admissions/your-feature
```

### 2. Make Your Changes

- Write code following [ALIS architectural rules](#architectural-rules-checklist)
- Add/update tests for new functionality
- Run linting before committing:
  ```bash
  # Backend
  cd ALIS && ruff check server/ --fix

  # Frontend
  cd web && npx eslint src/ --fix
  ```

### 3. Push & Create PR

```bash
git push origin feat/admissions/your-feature
```

Create a PR on GitHub targeting `develop` with:
- **Title**: Same format as commit (`feat(admissions): add merit list caching`)
- **Description**: What changed, why, how to test
- **Labels**: `backend`, `frontend`, `ai-agents`, `docs` as appropriate

### 4. Code Review

- **Minimum 1 reviewer** — the Senior AI Developer reviews all PRs
- **All CI checks must pass** (Ruff lint, ESLint, type checks)
- **Respond to review comments** within 24 hours
- **Request re-review** after addressing feedback

### 5. Merge

- Only the **Senior AI Developer** or the PR author (after approval) merges
- Use **Squash and Merge** for feature branches
- Delete the branch after merge

---

## Architectural Rules Checklist

**Every PR must comply with these rules.** Reviewers will check for violations.

### Backend Rules

- [ ] **Database reads use `execute_query()`** — never use it for writes
- [ ] **Database writes use `execute_transaction()`** — always
- [ ] **Every mutation has an `AuditLedger.log()` call** — no silent writes
- [ ] **Every router endpoint has `@require_permission()`** — no unprotected endpoints
- [ ] **All financial values use `Decimal`** — never `float`
- [ ] **Every query is scoped by `org_id`** — tenant isolation is mandatory
- [ ] **AI agents output DRAFT/PROVISIONAL only** — never FINAL, COMMIT, or OVERRIDE
- [ ] **No direct imports across domain modules** — use Domain Events for cross-module communication
- [ ] **State transitions go through `StateRegistry`** — no raw status updates

### Frontend Rules

- [ ] **Use `apiFetch()` for all API calls** — never raw `fetch()`
- [ ] **Role-based rendering uses `useALISRole()`** — no hardcoded role checks
- [ ] **No new dependencies without approval** — discuss in PR first
- [ ] **Follow design tokens** from `src/styles/tokens.css` — no hardcoded colors
- [ ] **Components in `src/components/ui/`** must be reusable and role-agnostic

### AI Agent Rules

- [ ] **All agent calls route through `AIGateway.invoke()`** — no direct LLM calls
- [ ] **Agent output schema includes `confidence` + `state_impact`** — mandatory fields
- [ ] **`state_impact` must be `DRAFT` or `PROVISIONAL`** — never `FINAL`
- [ ] **Low confidence (< threshold) triggers HITL** — automatic escalation
- [ ] **PII is masked before LLM invocation** — use `DataMasker`

---

## Code Review Guide

### What Reviewers Check

1. **Architecture compliance** — does it follow the 6-layer model?
2. **Audit trail** — are all mutations logged?
3. **Tenant isolation** — are queries scoped by `org_id`?
4. **RBAC coverage** — are endpoints protected?
5. **Error handling** — proper exception hierarchy used?
6. **Test coverage** — are new features tested?
7. **No dead code** — no commented-out blocks, no unused imports

### How to Review

```
✅ Approve — ready to merge
🔄 Request Changes — must fix before merge
💬 Comment — suggestions, not blocking
```

---

## Communication

- **Daily standups** — brief async update on what you're working on
- **Blocked?** — flag it immediately, don't wait for standup
- **Architecture questions** — ask the Senior AI Developer before building
- **PR turnaround** — review within 24 hours of request

---

## Quick Reference

| Action | Command |
|--------|---------|
| Run backend | `docker compose up app` |
| Run frontend | `cd web && npm run dev` |
| Run all services | `docker compose up` |
| Backend lint | `cd ALIS && ruff check server/` |
| Frontend lint | `cd web && npx eslint src/` |
| Run backend tests | `cd ALIS && pytest tests/` |
| Create migration | `cd ALIS && alembic revision --autogenerate -m "description"` |
| Seed database | `cd ALIS && python scripts/seed.py` |
