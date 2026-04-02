---
name: alis-claudecode-quality
description: >
  Use this skill at the START of every Claude Code session working on ALIS OS.
  It defines the verification protocol, prevention rules, and quality gates that
  must be followed before any task is marked complete. This skill exists because
  every major bug in ALIS history came from code that was written but never run
  against the real environment. These rules prevent that.
---

# ALIS Claude Code — Quality & Verification Skill

## The Prime Directive

**A task is not done until the system proves it works. Not when the code looks right. Not when the tests pass against mocks. When the running containers confirm it.**

Every major bug in this codebase — 214 missing imports, 7 broken API routes, Celery crashes, Nginx failures, Alertmanager config errors — was caused by the same thing: code written and counted as done without being run against the real environment. This skill prevents that from happening again.

---

## Session Start Protocol

**Run these two commands at the start of every session before touching any code.**
Do not proceed if either fails.

```bash
# 1. All containers must be healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. The 9 real database integration tests must pass
docker exec alis_app python -m pytest tests/test_integration_real_db.py -v --tb=short 2>&1 | tail -15
```

**Expected healthy containers:**
- `alis_postgres` — healthy
- `alis_redis` — healthy
- `alis_minio` — healthy
- `alis_app` — healthy
- `alis_celery_worker` — Up (no healthcheck configured)
- `alis_celery_beat` — Up (no healthcheck configured)
- `alis_nginx` — healthy
- `alis_vault` — healthy
- `alis_ollama` — healthy
- `alis_prometheus` — healthy
- `alis_alertmanager` — healthy

If any container shows `Restarting` or `unhealthy` — fix it before proceeding. Show the crash logs:
```bash
docker logs <container_name> --tail 30
```

---

## Task Completion Protocol

**Every task must pass ALL of the following checks before being marked done.**
Not some. All.

### Check 1 — Application starts

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep alis_app
```
Must show: `alis_app   Up X (healthy)`

If unhealthy, show full logs:
```bash
docker logs alis_app --tail 50
```

### Check 2 — Celery is running

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep celery
docker logs alis_celery_worker --tail 5
```
Must show both containers `Up` with no crash errors in logs.
The last log line should be `celery@xxxx ready.` for the worker,
or a scheduled task dispatch line for Beat.

### Check 3 — The 9 real database integration tests pass

```bash
docker exec alis_app python -m pytest tests/test_integration_real_db.py -v --tb=short
```
Must show `9 passed`. If any fail after a new feature, the new feature broke something.
Do not proceed until all 9 pass.

### Check 4 — New feature has a real database test

Every new feature must have at least one test added to `tests/test_integration_real_db.py` that:
- Connects to the real running database
- Does NOT mock `execute_query` or `execute_transaction`
- Proves the feature works with real data

If the feature cannot be tested this way, explain why before proceeding.

---

## Environment Verification Commands

Run these before writing code that depends on the environment.

### Python version and key package versions
```bash
docker exec alis_app python --version
docker exec alis_app pip show fastapi pydantic celery | grep -E "^Name|^Version"
```

### Check if a command exists in a specific container
```bash
docker exec <container_name> which <command>
# Example: docker exec alis_ollama which curl
```
**Never use a shell command in a health check or entrypoint without verifying it exists in that container.**

### Check what Python version is actually running
The codebase requires `from __future__ import annotations` in every Python file.
Check before writing any new file:
```bash
grep -l "from __future__ import annotations" server/ -r | wc -l
grep -rL "from __future__ import annotations" server/ --include="*.py" | wc -l
```
The second number must be 0. If it is not 0, add the import to all missing files before proceeding.

---

## Config File Validation Protocol

**Before restarting any infrastructure container after a config change, run the service's built-in validation.**

### Nginx
```bash
docker exec alis_nginx nginx -t
```
Must show: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

### Alertmanager
```bash
docker exec alis_alertmanager amtool check-config /etc/alertmanager/config.yml
```

### Loki
```bash
docker exec alis_loki loki -config.file=/etc/loki/local-config.yaml -verify-config 2>&1 | tail -5
```

### PostgreSQL migration
```bash
docker exec alis_app alembic check 2>&1
```
Must show no pending migrations after applying.

**Never restart a service container after a config change without running validation first.**

---

## Celery File Change Protocol

The Celery containers (`alis_celery_worker`, `alis_celery_beat`) now have **the same volume mount as `alis_app`**:
`./ALIS:/app` (added to `docker-compose.yml` in March 2026 session).

Code changes to any file under `server/` are picked up automatically — no `docker cp` needed.
Simply restart the containers after a code change:

```bash
docker restart alis_celery_worker alis_celery_beat

# Wait and verify stability (must be Up for 25+ seconds without restarting)
sleep 25 && docker ps --format "table {{.Names}}\t{{.Status}}" | grep celery

# Verify no errors in logs
docker logs alis_celery_worker --tail 10
docker logs alis_celery_beat --tail 10
```

**If containers were ever recreated without the volume mount (e.g. after `docker compose up` from an old image),
verify the mount is present:**
```bash
docker inspect alis_celery_worker --format '{{json .Mounts}}'
# Must show: "Source": "...ALIS Production\\ALIS", "Destination": "/app"
```
If the mount is missing, recreate with:
```bash
cd "c:/alis-antigravity/ALIS Production"
docker compose up -d --no-deps --force-recreate celery_worker celery_beat
```

---

## Known Bugs That Will Crash Production

These three issues are confirmed in the schema and must be fixed before pilot.
If any task touches these areas, fix the underlying issue, not just the symptom.

### 1. `workflow_tasks` table does not exist

Three service files reference a table that was never created:
- `server/academics/course_handover_workflow.py`
- `server/admissions/deduplication_service.py`
- `server/admissions/forgery_detection.py`

These will throw `psycopg2.errors.UndefinedTable` on first real use.
**Fix:** Create migration 0035 for the `workflow_tasks` table before these services are called.

### 2. Audit ledger has no immutability trigger

```bash
docker exec alis_postgres psql -U postgres -d alis_db -c \
  "SELECT trigger_name FROM information_schema.triggers WHERE event_object_table = 'audit_ledger';"
```
Returns 0 rows. Anyone with database access can UPDATE or DELETE audit entries.
**Fix:** Create a PostgreSQL trigger that raises an exception on any UPDATE or DELETE on `audit_ledger`.

### 3. State machine has no database-level enforcement

```bash
docker exec alis_postgres psql -U postgres -d alis_db -c \
  "SELECT trigger_name FROM information_schema.triggers WHERE trigger_name LIKE 'trg_%state%' OR trigger_name LIKE 'trg_%status%';"
```
Returns 0 rows. Raw SQL can bypass state machine logic.
**Fix:** Create triggers on key entity tables (`applicants`, `students`, etc.) that enforce valid status transitions.

---

## Weekly Verification Checklist

Run these five checks once per week. All must pass. Any failure must be fixed before new features are added.

```bash
# 1. All containers healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Real database tests passing
docker exec alis_app python -m pytest tests/test_integration_real_db.py -v --tb=short 2>&1 | tail -5

# 3. No hardcoded thresholds in business logic
grep -rn --include='*.py' '>= 75\|>= 0.75\|< 75\|== 75' server/ | grep -v test | grep -v migration | grep -v alembic

# 4. No raw status updates bypassing state machine
grep -rn --include='*.py' "SET status=" server/ | grep -v test | grep -v migration | grep -v alembic

# 5. No direct LLM calls outside AI Gateway
grep -rn --include='*.py' "ollama\.\|openai\.\|anthropic\." server/ | grep -v ai_gateway | grep -v test
```

Checks 3, 4, and 5 must return zero results. Any match is a violation of the build guidelines.

---

## Python Code Quality Rules

These apply to every Python file written or modified.

### Every new .py file must have this as the first non-docstring line:
```python
from __future__ import annotations
```

### FastAPI routes returning nothing must be explicit:
```python
# CORRECT — explicit response_model=None on any 204 route
@router.delete("/resource/{id}", status_code=204, response_model=None)
async def delete_resource(id: str) -> None:
    ...

# WRONG — omitting response_model=None with 204 causes AssertionError on startup
@router.delete("/resource/{id}", status_code=204)
async def delete_resource(id: str) -> None:
    ...
```

### DomainEventBus event registration — use subscribe(), not decorators:
```python
# CORRECT — register after function definition
async def _handle_my_event(payload: dict) -> None:
    ...

_DomainEventBus.subscribe("my.event", _handle_my_event)

# WRONG — DomainEventBus has no register_handler method
@_DomainEventBus.register_handler("my.event")
async def _handle_my_event(payload: dict) -> None:
    ...
```

### No shell-style variable substitution in config files:
```yaml
# CORRECT — literal values in alertmanager.yml, nginx.conf, loki-config.yml
smtp_smarthost: "localhost:25"

# WRONG — Alertmanager/Nginx/Loki do not expand shell syntax
smtp_smarthost: "${SMTP_HOST:-localhost:25}"
```

---

## Database Rules — Never Violate These

```python
# NEVER — raw SQL status update bypasses state machine
await execute_transaction([("UPDATE applicants SET status='enrolled' WHERE id=$1", [id])])

# ALWAYS — go through state machine
await applicant_state_machine.transition(id, "enrolled", actor_id, tenant_id)
```

```python
# NEVER — hardcoded threshold in business logic
if student.attendance_pct >= 75:
    return "ELIGIBLE"

# ALWAYS — read from policy engine at runtime
threshold = await policy_engine.get_value("attendance.minimum_threshold", tenant_id)
if student.attendance_pct >= threshold:
    return "ELIGIBLE"
```

```python
# NEVER — modify audit ledger entries
await execute_transaction([("UPDATE audit_ledger SET ... WHERE id=$1", [id])])
await execute_transaction([("DELETE FROM audit_ledger WHERE id=$1", [id])])

# ALWAYS — append only, never modify
await audit_ledger.append(event)
```

---

## The Single Question Before Writing Any Value Into Code

> **"Could a VC, Registrar, or Finance Officer ever need to change this without calling QUAICU?"**

If yes — it goes in `institution_policies` or `workflow_definitions` or `notification_templates` or `document_templates` in the database. Not in code.

---

## Quick Reference — What Each Container Does

| Container | Purpose | Volume Mount | Config Location |
|---|---|---|---|
| `alis_app` | FastAPI application | Yes — `/app` mounted from host | `server/` |
| `alis_celery_worker` | Background tasks | Yes — `/app` mounted from host | `server/` |
| `alis_celery_beat` | Scheduled tasks | Yes — `/app` mounted from host | `server/` |
| `alis_postgres` | Database | Volume | `docker-compose.yml` |
| `alis_redis` | Cache + Celery broker | Volume | `docker-compose.yml` |
| `alis_nginx` | Reverse proxy | Bind mount — `nginx/nginx.conf` | `nginx/nginx.conf` |
| `alis_vault` | Secrets | Volume | `docker-compose.yml` |
| `alis_ollama` | Local LLM inference | Volume | `docker-compose.yml` |
| `alis_minio` | File storage | Volume | `docker-compose.yml` |
| `alis_prometheus` | Metrics collection | Bind mount | `infra/monitoring/prometheus.yml` |
| `alis_alertmanager` | Alert routing | Bind mount | `infra/monitoring/alertmanager.yml` |
| `alis_loki` | Log aggregation | Bind mount | `infra/monitoring/loki-config.yml` |
| `alis_grafana` | Dashboards | Bind mount | `infra/monitoring/grafana/` |

---

## The Root Cause Summary

Every bug fixed in the March 2026 verification sessions came from one pattern:

**Code was written and counted as done without being run against the real environment.**

Bugs found and fixed in these sessions:
- 214 Python files missing `from __future__ import annotations` → all `list[dict]` return types crashed on startup
- 7 FastAPI DELETE routes with `status_code=204` and no `response_model=None` → assertion error on startup
- `DomainEventBus.register_handler()` called as a decorator — method doesn't exist → Celery crash on import
- `add_header Content-Security-Policy` split across multiple quoted strings → Nginx refused to start
- SSL cert directory empty → Nginx refused to start
- Alertmanager `${VAR:-default}` shell syntax → config parse failure and crash loop
- Loki `retention_enabled: true` without `delete_request_store` → config validation failure and crash loop
- Ollama health check used `curl` which isn't installed in the image → permanent `unhealthy`
- Celery containers had no volume mount → every code change required manual `docker cp`

The prevention is simple:
1. Start the system
2. Show me it is healthy
3. Show me the real database tests pass
4. Then, and only then, mark the task done

*QUAICU Solutions Private Limited | ALIS OS | Version 1.0 | March 2026 | Confidential*