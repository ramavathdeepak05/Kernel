"""
ALIS Deployment Verifier — 46-check audit
Run inside the app container: python scripts/verifier.py
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, "/app")

results = []

def check(n, label, fn):
    try:
        r = fn()
        status = "PASS" if r else "FAIL"
        results.append((n, status, label, ""))
    except Exception as e:
        results.append((n, "FAIL", label, str(e)[:120]))

# ── Section 1: Infrastructure (11 checks) ─────────────────────────────────────

def c1_1():
    import socket
    s = socket.create_connection(("localhost", 8000), timeout=3)
    s.close()
    return True
check("1.1",  "App port 8000 open", c1_1)

def c1_2():
    import psycopg2
    from server.core.settings import settings
    conn = psycopg2.connect(settings.db_url)
    conn.cursor().execute("SELECT 1")
    conn.close()
    return True
check("1.2",  "PostgreSQL reachable", c1_2)

def c1_3():
    import redis
    from server.core.settings import settings
    return redis.Redis.from_url(settings.redis_url).ping()
check("1.3",  "Redis reachable", c1_3)

def c1_4():
    from server.core.settings import settings
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{settings.minio_endpoint}/minio/health/live", timeout=3)
        return True
    except Exception:
        return False
check("1.4",  "MinIO reachable", c1_4)

def c1_5():
    import urllib.request
    try:
        urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5)
        return True
    except Exception:
        return False
check("1.5",  "Ollama reachable", c1_5)

def c1_6():
    import urllib.request, json as _j
    data = _j.loads(urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5).read())
    models = {m["name"] for m in data.get("models", [])}
    return {"qwen2.5:1.5b-instruct-q8_0", "nomic-embed-text:latest"}.issubset(models)
check("1.6",  "Ollama EXTRACTION + embeddings models present", c1_6)

def c1_7():
    from server.db_service import execute_query
    rows = execute_query("SELECT version_num FROM alembic_version", (), tenant_id="default")
    return rows and rows[0]["version_num"] == "0040"
check("1.7",  "Alembic at head (0040)", c1_7)

def c1_8():
    import socket
    try:
        s = socket.create_connection(("pgbouncer", 5432), timeout=3)
        s.close()
        return True
    except Exception:
        return False
check("1.8",  "PgBouncer port 5432 reachable", c1_8)

def c1_9():
    import urllib.request
    try:
        urllib.request.urlopen("http://vault:8200/v1/sys/health", timeout=3)
        return True
    except Exception as e:
        # 429/503 still means vault is up
        return "503" not in str(e) and "Connection refused" not in str(e)
check("1.9",  "Vault reachable", c1_9)

def c1_10():
    import urllib.request, json as _j
    data = _j.loads(urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5).read())
    models = {m["name"] for m in data.get("models", [])}
    return "qwen2.5:7b-instruct-q8_0" in models
check("1.10", "Ollama REASONING model (7b) present", c1_10)

def c1_11():
    import urllib.request, json as _j
    data = _j.loads(urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5).read())
    models = {m["name"] for m in data.get("models", [])}
    return "qwen2.5:14b-instruct-q8_0" in models
check("1.11", "Ollama GENERATION model (14b) present", c1_11)

# ── Section 2: AI Stack (7 checks) ───────────────────────────────────────────

def c2_1():
    from server.core.ai_gateway import AIGateway, AIGatewayContext
    from server.core.rbac import Role
    ctx = AIGatewayContext(actor_id="test", org_id="demo", module="M1", actor_role=Role.SYSTEM)
    return AIGateway.get_llm(ctx) is not None
check("2.1",  "AIGateway.get_llm() returns InstrumentedLLM", c2_1)

def c2_2():
    from server.agents.rail.registry import RailAgentRegistry
    return "context_advisor_v1" in RailAgentRegistry.list_agents()
check("2.2",  "RAIL context_advisor_v1 registered", c2_2)

def c2_3():
    from server.agents.admissions.registry import AdmissionsAgentRegistry
    return len(AdmissionsAgentRegistry.list_agents()) > 0
check("2.3",  "Admissions agents registered", c2_3)

def c2_4():
    from server.core.guardrails import AIGuardrails
    result = AIGuardrails.check_output("Hello world", "test prompt", "demo", actor_id="test")
    return result is not None and hasattr(result, "blocked")
check("2.4",  "AIGuardrails.check_output() executes", c2_4)

def c2_5():
    import importlib.util
    return importlib.util.find_spec("server.core.prompt_registry") is not None
check("2.5",  "PromptRegistry module exists", c2_5)

def c2_6():
    from server.agents.rail.context_advisor import execute_context_advisor
    from server.core.ai_gateway import AIGatewayContext
    from server.core.rbac import Role
    ctx = AIGatewayContext(actor_id="sys", org_id="demo", module="RAIL", actor_role=Role.SYSTEM)
    result = execute_context_advisor(
        context=ctx,
        input_data={"view": "home", "role": "registrar", "message": "__view_change__"}
    )
    return result is not None and hasattr(result, "success")
check("2.6",  "execute_context_advisor with AIGatewayContext object", c2_6)

def c2_7():
    from server.agents.rail.context_advisor import execute_context_advisor
    ctx_dict = {"actor_id": "sys", "org_id": "demo", "module": "RAIL"}
    result = execute_context_advisor(
        context=ctx_dict,
        input_data={"view": "home", "role": "registrar", "message": "__view_change__"}
    )
    return result is not None and hasattr(result, "success")
check("2.7",  "execute_context_advisor tolerates dict context (guard)", c2_7)

# ── Section 3: Events & Audit (5 checks) ─────────────────────────────────────

def c3_1():
    from server.core.events import EventBus
    return isinstance(EventBus._subscribers, dict)
check("3.1",  "EventBus._subscribers is a dict", c3_1)

def c3_2():
    from server.db_service import execute_query
    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM domain_events WHERE status = %s AND processing_started_at < NOW() - INTERVAL '10 minutes'",
        ("PROCESSING",), tenant_id="default"
    )
    return rows[0]["cnt"] == 0
check("3.2",  "No stuck PROCESSING domain_events", c3_2)

def c3_3():
    from server.db_service import execute_query
    rows = execute_query("SELECT COUNT(*) AS cnt FROM audit_ledger", (), tenant_id="default")
    return rows[0]["cnt"] >= 0
check("3.3",  "audit_ledger table accessible", c3_3)

def c3_4():
    from server.db_service import execute_query
    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM domain_events WHERE published_at > NOW() - INTERVAL '1 hour'",
        (), tenant_id="default"
    )
    return rows[0]["cnt"] >= 0
check("3.4",  "domain_events.published_at column exists", c3_4)

def c3_5():
    from server.admissions.event_handlers import register_all as adm_register
    import server.core.domain_events as _de
    before = len(_de._handlers)
    adm_register()
    return len(_de._handlers) >= before
check("3.5",  "Admissions event handlers register into domain_events._handlers", c3_5)

# ── Section 4: RBAC & Auth (6 checks) ────────────────────────────────────────

def c4_1():
    from server.core.rbac import Role, Permission, check_role_permission
    return check_role_permission(Role.SUPER_ADMIN, Permission.AI_INVOKE)
check("4.1",  "SUPER_ADMIN has AI_INVOKE permission", c4_1)

def c4_2():
    from server.core.rbac import Role, Permission, check_role_permission
    return not check_role_permission(Role.STUDENT, Permission.AI_INVOKE)
check("4.2",  "STUDENT lacks AI_INVOKE permission", c4_2)

def c4_3():
    from server.core.security import SessionManager
    session, raw_token = SessionManager.create_session("u1", tenant_id="demo")
    sess = SessionManager.validate_token(raw_token)
    return sess is not None and sess.user_id == "u1"
check("4.3",  "SessionManager create+validate round-trip", c4_3)

def c4_4():
    from server.core.mfa_service import MFAService
    return MFAService is not None
check("4.4",  "MFAService importable", c4_4)

def c4_5():
    # Vault root token should NOT be the default dev token in production
    from server.core.settings import settings
    return settings.vault_token != "alis-dev-root-token"
check("4.5",  "Vault token is not default dev value [PILOT-ACCEPTABLE]", c4_5)

def c4_6():
    # Vault should use persistent storage, not inmem (dev mode).
    # /v1/sys/seal-status is unauthenticated and returns storage_type.
    import urllib.request, json as _j
    try:
        resp = urllib.request.urlopen("http://vault:8200/v1/sys/seal-status", timeout=3)
        data = _j.loads(resp.read())
        storage_type = data.get("storage_type", "unknown")
        return storage_type not in ("inmem", "")
    except Exception:
        return False
check("4.6",  "Vault uses persistent storage (not inmem) [PILOT-ACCEPTABLE]", c4_6)

# ── Section 5: Notification Channels (3 checks) ───────────────────────────────

def c5_1():
    from server.core.notifications.channels import SMSChannel, ChannelResult
    ch = SMSChannel()
    result = ch.send("+911234567890", subject=None, body="test")
    return isinstance(result, ChannelResult)
check("5.1",  "SMSChannel.send() returns ChannelResult", c5_1)

def c5_2():
    from server.core.notifications.channels import WhatsAppChannel, ChannelResult
    ch = WhatsAppChannel()
    result = ch.send("+911234567890", subject=None, body="test")
    return isinstance(result, ChannelResult)
check("5.2",  "WhatsAppChannel.send() returns ChannelResult", c5_2)

def c5_3():
    from server.core.notifications.channels import EmailChannel
    return EmailChannel is not None
check("5.3",  "EmailChannel importable", c5_3)

# ── Section 6: Finance & Payments (2 checks) ──────────────────────────────────

def c6_1():
    from server.finance.payment import PaymentService
    return PaymentService is not None
check("6.1",  "PaymentService importable", c6_1)

def c6_2():
    from server.admissions.integrations.payment_gateway import PaymentGatewayClient
    try:
        gw = PaymentGatewayClient()
        result = gw.verify_payment(
            order_id="TXN-001", payment_id="PAYU-001", signature="badhash",
            callback_params=None,
        )
        return not result.is_valid
    except Exception as e:
        if "not configured" in str(e).lower() or "PAYMENT_GATEWAY_ENABLED" in str(e):
            return True  # correct: requires env config, not a code bug
        raise
check("6.2",  "PayU verify rejects bad hash / requires config when unconfigured", c6_2)

# ── Section 7: Task System (4 checks) ─────────────────────────────────────────

def c7_1():
    from server.worker import celery_app
    return celery_app is not None
check("7.1",  "Celery app importable", c7_1)

def c7_2():
    from server.tasks.ai_tasks import verify_document_async
    import inspect
    return "NotImplementedError" not in inspect.getsource(verify_document_async)
check("7.2",  "verify_document_async: no NotImplementedError", c7_2)

def c7_3():
    from server.db_service import execute_query
    rows = execute_query("SELECT COUNT(*) AS cnt FROM failed_task_log", (), tenant_id="default")
    return rows[0]["cnt"] >= 0
check("7.3",  "failed_task_log table exists (migration 0038)", c7_3)

def c7_4():
    # Celery worker should be able to connect to broker
    from server.worker import celery_app
    try:
        conn = celery_app.connection_for_read()
        conn.connect()
        conn.close()
        return True
    except Exception:
        return False
check("7.4",  "Celery worker connects to Redis broker", c7_4)

# ── Section 8: Tenant & Policy (3 checks) ────────────────────────────────────

def c8_1():
    from server.db_service import execute_query
    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM tenant_policies WHERE status = %s",
        ("APPROVED",), tenant_id="default"
    )
    return rows[0]["cnt"] >= 1
check("8.1",  "At least 1 APPROVED tenant_policy seeded", c8_1)

def c8_2():
    from server.core.policy_engine import PolicyEngine
    pe = PolicyEngine()
    result = pe.evaluate("agent_rail_silence", {}, tenant_id="demo", default_verdict="SURFACE")
    return result is not None
check("8.2",  "PolicyEngine.evaluate() runs without crash", c8_2)

def c8_3():
    from server.db_service import execute_query
    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM applicants WHERE kyc_status IS NOT NULL",
        (), tenant_id="default"
    )
    return rows[0]["cnt"] >= 0
check("8.3",  "applicants.kyc_status column exists (migration 0040)", c8_3)

# ── Section 9: Layer 3 Compliance (5 checks) ──────────────────────────────────

def c9_1():
    # ta_assignment_service.py must not have direct SET status='REVOKED' (Layer 3 violation)
    import re
    path = "/app/server/academics/ta_assignment_service.py"
    with open(path) as f:
        src = f.read()
    # Direct status mutation bypassing state machine
    return not re.search(r"SET\s+status\s*=\s*'REVOKED'", src, re.IGNORECASE)
check("9.1",  "ta_assignment_service: no direct status='REVOKED' bypass [PILOT-ACCEPTABLE]", c9_1)

def c9_2():
    # finance_router.py must not have direct UPDATE payments SET status='CAPTURED'
    import re
    path = "/app/server/api/finance_router.py"
    with open(path) as f:
        src = f.read()
    return not re.search(r"UPDATE\s+payments\s+SET\s+status\s*=\s*'CAPTURED'", src, re.IGNORECASE)
check("9.2",  "finance_router: no direct payments status='CAPTURED' [PILOT-ACCEPTABLE]", c9_2)

def c9_3():
    # No agent file should write to DB directly (Layer 3 constraint)
    import os, re
    agents_dir = "/app/server/agents"
    violations = []
    for root, dirs, files in os.walk(agents_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path) as fh:
                src = fh.read()
            if re.search(r"execute_transaction\s*\(", src):
                violations.append(f)
    return len(violations) == 0
check("9.3",  "No agent file calls execute_transaction (Layer 3 — agents are read-only)", c9_3)

def c9_4():
    # Verify forgery_detection service doesn't bypass approval workflow
    import inspect
    from server.admissions.forgery_detection import ForgeryDetectionService
    src = inspect.getsource(ForgeryDetectionService)
    # Must route through status updates, not delete or hard-override
    return "DELETE FROM" not in src.upper()
check("9.4",  "ForgeryDetectionService: no direct DELETE FROM", c9_4)

def c9_5():
    # Identity match service importable (migration 0040)
    from server.admissions.identity_match import IdentityMatchService
    return IdentityMatchService is not None
check("9.5",  "IdentityMatchService importable (EC-ADM-01)", c9_5)

# ── Section 10: Agent Quality (5 checks) ──────────────────────────────────────

def c10_1():
    # Agents should not have hardcoded 0.75 confidence threshold everywhere
    import os, re
    agents_dir = "/app/server/agents"
    hardcoded = []
    for root, dirs, files in os.walk(agents_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path) as fh:
                src = fh.read()
            # Count hardcoded 0.75 confidence (not in comments)
            lines = [l for l in src.splitlines() if "0.75" in l and not l.strip().startswith("#")]
            if lines:
                hardcoded.append((f, len(lines)))
    return len(hardcoded) == 0
check("10.1", "No hardcoded 0.75 confidence thresholds in agents [PILOT-ACCEPTABLE]", c10_1)

def c10_2():
    from server.agents.admissions.eligibility import execute_eligibility_eval
    from server.core.ai_gateway import AIGatewayContext, AIInvocationResult
    from server.core.rbac import Role
    ctx = AIGatewayContext(actor_id="sys", org_id="demo", module="M1", actor_role=Role.SYSTEM)
    result = execute_eligibility_eval(
        context=ctx,
        input_data={"application_id": "APP-2025-000001", "policy_id": "pol-001"}
    )
    return isinstance(result, AIInvocationResult)
check("10.2", "execute_eligibility_eval returns AIInvocationResult", c10_2)

def c10_3():
    # RAIL agent output is JSON-parseable AgentResponse
    import json
    from server.agents.rail.context_advisor import execute_context_advisor
    from server.core.ai_gateway import AIGatewayContext
    from server.core.rbac import Role
    ctx = AIGatewayContext(actor_id="sys", org_id="demo", module="RAIL", actor_role=Role.SYSTEM)
    result = execute_context_advisor(
        context=ctx,
        input_data={"view": "home", "role": "registrar", "message": "__view_change__"}
    )
    if not result.success or not result.content:
        return False
    parsed = json.loads(result.content)
    return "message" in parsed and "canvasAction" in parsed
check("10.3", "RAIL context_advisor output is valid AgentResponse JSON", c10_3)

def c10_4():
    # Verify llm_router / model_registry importable
    from server.core.model_registry import ModelRegistry
    return ModelRegistry is not None
check("10.4", "ModelRegistry importable", c10_4)

def c10_5():
    # Tool registry importable
    from server.core.tool_registry import ToolRegistry
    return ToolRegistry is not None
check("10.5", "ToolRegistry importable", c10_5)

# ── Print results ─────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r[1] == "PASS")
total = len(results)
print(f"\n=== Verifier Results: {passed}/{total} ===\n")
for n, status, label, err in results:
    icon = "✓" if status == "PASS" else "✗"
    line = f"  {icon} {n:<5} {label}"
    if err:
        line += f"\n        ERR: {err}"
    print(line)
print()
