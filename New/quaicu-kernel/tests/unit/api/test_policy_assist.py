"""POST /v1/policies/assist — the AI policy-drafting route (a fake assistant stands in for the LLM)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from core.policy.authoring import PolicySuggestion
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import (
    FakeEvents,
    FakeHITL,
    FakeIdentity,
    FakeLedger,
    FakePolicy,
)


def _kernel(tenant: str = "acme") -> Kernel:
    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


class _FakeAssistant:
    def __init__(self, suggestion: PolicySuggestion) -> None:
        self._s = suggestion
        self.calls: list[dict] = []

    async def suggest(self, **kwargs) -> PolicySuggestion:
        self.calls.append(kwargs)
        return self._s


async def test_assist_returns_suggestion():
    suggestion = PolicySuggestion(
        condition='action_type == "loan.approve" && payload_amount > 1000000',
        decision="require_approval",
        explanation="High-value loans need a human.",
        valid=True,
    )
    assistant = _FakeAssistant(suggestion)
    app = create_app(_kernel(), policy_assistant=assistant)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/policies/assist",
            json={"description": "loans over 1M need a human", "payload_fields": ["amount"]},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["decision"] == "require_approval"
    assert "loan.approve" in body["condition"]
    # The route threaded the request through to the assistant.
    assert assistant.calls and assistant.calls[0]["description"] == "loans over 1M need a human"
    assert assistant.calls[0]["payload_fields"] == ["amount"]


async def test_assist_503_when_not_configured():
    app = create_app(_kernel())  # no policy_assistant wired
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/policies/assist", json={"description": "block everything"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "ASSISTANT_DISABLED"


async def test_assist_surfaces_invalid_cel_to_caller():
    suggestion = PolicySuggestion(
        condition="action_type == (broken",
        decision="deny",
        explanation="x",
        valid=False,
        error="CEL parse error",
    )
    app = create_app(_kernel(), policy_assistant=_FakeAssistant(suggestion))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/policies/assist", json={"description": "x"})
    assert resp.status_code == 200  # the draft is returned; the caller sees it didn't compile
    body = resp.json()
    assert body["valid"] is False and body["error"]
