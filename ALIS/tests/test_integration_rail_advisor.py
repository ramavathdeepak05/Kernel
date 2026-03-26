"""
Integration test — Agent Rail context_advisor_v1

Hits the live PostgreSQL instance directly.
No mocks for the DB layer — this test exercises the full executor path:

    execute_context_advisor()
        -> _query_counts()       (real SELECT on workflow_tasks)
        -> _should_surface()     (real policy_engine.evaluate on tenant_policies)
        -> _build_proactive_message()

Schema is fully provisioned by migrations 0036 (workflow_tasks agent-rail
columns) and 0037 (tenant_policies). No DDL is created by this test.

Run:
    pytest tests/test_integration_rail_advisor.py -v
"""
from __future__ import annotations

import json
import uuid

import psycopg2
import pytest

from server.core.ai_gateway import AIGatewayContext
from server.core.rbac import Role
from server.core.settings import settings
from server.agents.rail.context_advisor import execute_context_advisor

# ---------------------------------------------------------------------------
# Isolated test tenant — safe to DELETE without touching real data
# ---------------------------------------------------------------------------
TEST_ORG_ID  = "99000000-0000-0000-0000-000000000001"
TEST_USER_ID = "99000000-0000-0000-0000-000000000002"
TEST_ROLE    = "registrar"


# ---------------------------------------------------------------------------
# Override conftest autouse fixtures — this module uses the real DB
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="module")
def mock_db_global():
    """No-op: let execute_query reach the real Postgres instance."""
    yield


@pytest.fixture(autouse=True, scope="module")
def fake_redis_global():
    """No-op: no Redis calls on the __view_change__ path."""
    yield


@pytest.fixture(autouse=True, scope="module")
def mock_audit_log():
    """No-op: execute_context_advisor is called directly, bypassing registry audit hooks."""
    yield


# ---------------------------------------------------------------------------
# Real DB fixture — opens a direct connection and cleans up test rows
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_db():
    """
    Direct psycopg2 connection to the live Postgres instance.
    Schema is already provisioned by migrations 0036 and 0037.
    Deletes test rows in teardown — schema is left untouched.
    """
    conn = psycopg2.connect(settings.db_url)
    conn.autocommit = True
    yield conn

    # Teardown: remove rows inserted during this test module
    cur = conn.cursor()
    cur.execute("DELETE FROM workflow_tasks  WHERE tenant_id = %s", (TEST_ORG_ID,))
    cur.execute("DELETE FROM tenant_policies WHERE tenant_id = %s", (TEST_ORG_ID,))
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> AIGatewayContext:
    return AIGatewayContext(
        actor_id=TEST_USER_ID,
        actor_role=Role.REGISTRAR,
        actor_type="human",
        org_id=TEST_ORG_ID,
        module="RAIL",
    )


def _view_change(view: str = "approval_queue") -> dict:
    return {"view": view, "role": TEST_ROLE, "message": "__view_change__"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContextAdvisorIntegration:

    def test_sla_breach_surfaces_message(self, real_db):
        """
        Personally-assigned task past SLA → personal_sla_breached >= 1 →
        _should_surface() returns True without consulting policy engine →
        _build_proactive_message() returns a non-None brief.
        """
        cur = real_db.cursor()
        task_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO workflow_tasks (
                id, org_id, tenant_id,
                workflow_type, task_type, resource_id,
                status, urgency, assignee_role, assignee_actor_id,
                sla_deadline, created_by
            ) VALUES (
                %s, %s, %s,
                'APPROVAL', 'DOCUMENT_VERIFY', %s,
                'PENDING', 'HIGH', %s, %s,
                NOW() - INTERVAL '1 hour', %s
            )
            """,
            (
                task_id, TEST_ORG_ID, TEST_ORG_ID,
                str(uuid.uuid4()),
                TEST_ROLE, TEST_USER_ID,
                TEST_USER_ID,
            ),
        )

        result = execute_context_advisor(context=_ctx(), input_data=_view_change())

        cur.execute("DELETE FROM workflow_tasks WHERE id = %s", (task_id,))

        assert result.success, f"Executor failed: {result.error}"
        resp = json.loads(result.content)
        assert resp["message"] is not None, (
            "Expected a proactive brief for the SLA-breached task, got silence.\n"
            f"Full response: {resp}"
        )

    def test_zero_tasks_stays_silent(self, real_db):
        """
        No pending tasks for the test tenant → all counts zero →
        _build_proactive_message() returns None → rail stays silent.

        Policy engine will fall back to default_verdict='SURFACE' (no policy
        seeded for this test tenant), so _should_surface() returns True —
        but _build_proactive_message() short-circuits on total==0 and sla==0,
        so message is still None.
        """
        cur = real_db.cursor()
        cur.execute(
            "DELETE FROM workflow_tasks WHERE tenant_id = %s", (TEST_ORG_ID,)
        )

        result = execute_context_advisor(context=_ctx(), input_data=_view_change())

        assert result.success, f"Executor failed: {result.error}"
        resp = json.loads(result.content)
        assert resp["message"] is None, (
            f"Expected silence with zero tasks, but got: {resp['message']!r}"
        )
