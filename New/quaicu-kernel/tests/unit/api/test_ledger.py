"""Unit tests for the FastAPI ledger routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeLedger, FakePolicy

TENANT = TenantId("ciro-bank")


def _kernel(decision: Decision = Decision.ALLOW) -> Kernel:
    return Kernel.from_parts(
        tenant=TENANT,
        policy=FakePolicy(decision=decision),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
    )


def _app(decision: Decision = Decision.ALLOW):
    return create_app(_kernel(decision))


def _propose_body(idempotency_key: str = "ik-ledger-1") -> dict:
    return {
        "type": "ciro.ifrs9.stage_transition",
        "payload": {"loan_id": "4471", "from_stage": 1, "to_stage": 2},
        "idempotency_key": idempotency_key,
        "actor_id": "alice",
        "actor_roles": ["role:risk_analyst"],
    }


# ── GET /v1/ledger/{tenant}/trail ────────────────────────────────────────────────


async def test_empty_trail_returns_zero_entries():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/ledger/{TENANT}/trail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["entries"] == []


async def test_trail_has_entry_after_allow():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/actions/propose", json=_propose_body("ik-trail-1"))
        resp = await client.get(f"/v1/ledger/{TENANT}/trail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["entries"][0]["action_type"] == "ciro.ifrs9.stage_transition"


async def test_trail_entry_has_required_fields():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/actions/propose", json=_propose_body("ik-trail-fields"))
        resp = await client.get(f"/v1/ledger/{TENANT}/trail")
    entry = resp.json()["entries"][0]
    assert "ledger_seq" in entry
    assert "action_id" in entry
    assert "action_type" in entry
    assert "actor_id" in entry
    assert "decision" in entry
    assert "sealed_at" in entry


async def test_trail_tenant_filter():
    """Trail returns only entries for the requested tenant."""
    app = _app()
    other_tenant = "other-bank"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/actions/propose", json=_propose_body("ik-filter-1"))
        resp = await client.get(f"/v1/ledger/{other_tenant}/trail")
    data = resp.json()
    assert data["count"] == 0


async def test_trail_count_grows_with_each_action():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(3):
            await client.post("/v1/actions/propose", json=_propose_body(f"ik-count-{i}"))
        resp = await client.get(f"/v1/ledger/{TENANT}/trail")
    assert resp.json()["count"] == 3


async def test_trail_decision_field_is_allow():
    app = _app(Decision.ALLOW)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/actions/propose", json=_propose_body("ik-decision"))
        resp = await client.get(f"/v1/ledger/{TENANT}/trail")
    entry = resp.json()["entries"][0]
    assert entry["decision"] == "allow"


# ── GET /v1/ledger/health ────────────────────────────────────────────────────────


async def test_ledger_health_returns_ok():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/ledger/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
