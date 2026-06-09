"""Unit tests for the FastAPI action routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeLedger, FakePolicy

TENANT = TenantId("ciro-bank")


def _app(decision: Decision = Decision.ALLOW, raise_ledger: bool = False):
    kernel = Kernel.from_parts(
        tenant=TENANT,
        policy=FakePolicy(decision=decision),
        hitl=FakeHITL(),
        ledger=FakeLedger(raise_exc=raise_ledger),
        events=FakeEvents(),
    )
    return create_app(kernel)


def _body(idempotency_key: str = "ik-1") -> dict:
    return {
        "type": "ciro.ifrs9.stage_transition",
        "payload": {"loan_id": "4471", "from_stage": 1, "to_stage": 2},
        "idempotency_key": idempotency_key,
        "actor_id": "alice",
        "actor_roles": ["role:risk_analyst"],
    }


@pytest.fixture
def allow_app():
    return _app(Decision.ALLOW)


@pytest.fixture
def deny_app():
    return _app(Decision.DENY)


# ── POST /v1/actions/propose ─────────────────────────────────────────────────────


async def test_propose_allow_returns_202(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json=_body())
    assert resp.status_code == 202
    data = resp.json()
    assert data["state"] == "COMPLETED"
    assert data["type"] == "ciro.ifrs9.stage_transition"


async def test_propose_deny_returns_403(deny_app):
    async with AsyncClient(transport=ASGITransport(app=deny_app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json=_body())
    assert resp.status_code == 403


async def test_propose_missing_fields_returns_422(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json={"type": "x"})  # missing idempotency_key, actor_id
    assert resp.status_code == 422


async def test_propose_ledger_failure_returns_422():
    app = _app(raise_ledger=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json=_body())
    assert resp.status_code == 422


async def test_propose_response_has_action_id(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json=_body())
    assert "action_id" in resp.json()


async def test_propose_response_has_tenant(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.post("/v1/actions/propose", json=_body())
    assert resp.json()["tenant"] == "ciro-bank"


# ── GET /v1/actions/{id} ──────────────────────────────────────────────────────────


async def test_get_action_not_found_returns_404(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.get("/v1/actions/nonexistent-id")
    assert resp.status_code == 404


async def test_get_action_after_propose(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        propose = await client.post("/v1/actions/propose", json=_body("ik-get-test"))
        action_id = propose.json()["action_id"]
        get_resp = await client.get(f"/v1/actions/{action_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["action_id"] == action_id


# ── GET /health ───────────────────────────────────────────────────────────────────


async def test_health_endpoint(allow_app):
    async with AsyncClient(transport=ASGITransport(app=allow_app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
