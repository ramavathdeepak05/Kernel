"""End-to-end: a COMPLIANCE member logs in and approves in-browser; SoD holds (D1-5).

Wires the account engine's session secret to the kernel's JWT IdentityPort (as in production) so a member
session token resolves to the member's governance actor. Proves: member login → /v1/approvals decide →
the action resumes with the MEMBER sealed as approver; a member cannot approve an action they proposed.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from adapters.identity.jwt_adapter import JWTIdentityAdapter
from core.account import AccountEngine, AccountStore
from core.account.roles import Role
from core.entitlements import EntitlementStore
from core.errors import LifecyclePendingApprovalError
from core.hitl.engine import InProcessHITLPort
from core.types import (
    ActionId,
    ActionState,
    Actor,
    ActorId,
    ApproverRef,
    Decision,
    TenantId,
)
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeLedger, FakePolicy

SECRET = "test-jwt-secret"
EMAIL = "checker@acme.io"
PASSWORD = "s3cret-passphrase"


def _setup():
    engine = AccountEngine(AccountStore(), EntitlementStore(), session_secret=SECRET)
    member = engine.provision_member(
        TenantId("acme"), email=EMAIL, role=Role.COMPLIANCE.value, display_name="Checker"
    )
    engine.set_member_password(
        token=engine.mint_member_set_password_token(member), new_password=PASSWORD
    )
    kernel = Kernel.from_parts(
        tenant="acme",
        policy=FakePolicy(
            decision=Decision.REQUIRE_APPROVAL, approvers=(ApproverRef("role:compliance"),)
        ),
        hitl=InProcessHITLPort(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=JWTIdentityAdapter(secret_or_key=SECRET, algorithms=["HS256"], verify=True),
    )
    return create_app(kernel, account_engine=engine), engine, member, kernel


async def _make_pending(kernel, proposer_id: str) -> tuple[str, str]:
    @kernel.guard(policy="x.act")
    async def act() -> dict:
        return {"ok": True}

    proposer = Actor(id=ActorId(proposer_id), tenant=TenantId("acme"), roles=())
    with pytest.raises(LifecyclePendingApprovalError) as ei:
        async with kernel.actor_context(proposer):
            await act()
    return ei.value.detail["handle_id"], ei.value.detail["action_id"]


async def _login(client: AsyncClient) -> str:
    r = await client.post("/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


async def test_member_logs_in_and_approves_sealing_member_identity() -> None:
    app, _engine, member, kernel = _setup()
    handle_id, action_id = await _make_pending(kernel, "agent:maker")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        token = await _login(c)
        resp = await c.post(
            f"/v1/approvals/{handle_id}/approve", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200, resp.text
    # Sealed approver identity is the member (not the account owner).
    record = kernel._in_process_hitl().get_record(handle_id)
    assert str(record.decided_by) == member.member_id
    action = await kernel.engine._repo.get_by_id(TenantId("acme"), ActionId(action_id))
    assert action is not None and action.state is ActionState.COMPLETED


async def test_member_cannot_approve_their_own_action() -> None:
    app, _engine, member, kernel = _setup()
    # The member is the proposer → self-approval must be blocked (separation of duties).
    handle_id, _ = await _make_pending(kernel, member.member_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        token = await _login(c)
        resp = await c.post(
            f"/v1/approvals/{handle_id}/approve", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 409  # SoD: proposer cannot approve
