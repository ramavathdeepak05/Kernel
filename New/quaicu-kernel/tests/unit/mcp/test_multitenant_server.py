"""Multi-tenant GovernedMCPServer: each call is governed by the RESOLVED tenant's kernel + sealed to
its ledger — transport-free, via a stub session_resolver flipping between tenants."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")  # handle_call builds a CallToolResult (mcp.types)

from core.hitl.engine import InProcessHITLPort  # noqa: E402
from core.types import Actor, ActorId, Decision, TenantId  # noqa: E402
from delivery.mcp.auth import ResolvedSession  # noqa: E402
from delivery.mcp.server import GovernedMCPServer  # noqa: E402
from delivery.sdk.kernel import Kernel  # noqa: E402
from tests.unit.lifecycle.fakes import FakeEvents, FakeLedger, FakePolicy  # noqa: E402


def _session(tenant: str, decision: Decision) -> tuple[ResolvedSession, FakeLedger]:
    ledger = FakeLedger()
    kernel = Kernel.from_parts(
        tenant=tenant, policy=FakePolicy(decision=decision), hitl=InProcessHITLPort(),
        ledger=ledger, events=FakeEvents(),
    )
    actor = Actor(id=ActorId(f"user:{tenant}"), tenant=TenantId(tenant))
    return ResolvedSession(TenantId(tenant), actor, kernel), ledger


async def test_calls_are_governed_and_sealed_per_resolved_tenant():
    sess_a, ledger_a = _session("acme", Decision.ALLOW)
    sess_b, ledger_b = _session("globex", Decision.DENY)
    current = {"s": sess_a}

    server = GovernedMCPServer(name="hosted")
    server.register_tool("echo", handler=lambda a: {"echo": a}, policy="mcp.tool")
    server.bind_session_resolver(lambda: current["s"])

    # Tenant A (ALLOW): runs + seals to A's ledger, attributed to A's actor.
    res_a = await server.handle_call("echo", {"x": 1})
    assert res_a.isError is False
    assert res_a.structuredContent == {"echo": {"x": 1}}
    assert len(ledger_a.sealed) == 1
    assert str(ledger_a.sealed[0].actor_id) == "user:acme"
    assert len(ledger_b.sealed) == 0

    # Switch to tenant B (DENY): blocked, and tenant A's ledger is untouched (isolation).
    current["s"] = sess_b
    res_b = await server.handle_call("echo", {"x": 2})
    assert res_b.isError is True
    assert len(ledger_a.sealed) == 1  # A never saw B's call


async def test_resolver_failure_is_fail_closed():
    # A bad key → the resolver raises → the tool never runs (surfaces as an error / propagates).
    def _boom() -> ResolvedSession:
        raise RuntimeError("no valid key")

    ran: list = []
    server = GovernedMCPServer(name="hosted")
    server.register_tool("t", handler=lambda a: ran.append(a), policy="mcp.tool")
    server.bind_session_resolver(_boom)

    with pytest.raises(RuntimeError):
        await server.handle_call("t", {"a": 1})
    assert ran == []  # never executed
