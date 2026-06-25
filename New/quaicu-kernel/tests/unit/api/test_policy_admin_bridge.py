"""Policy-admin routes accept a verified API key (the bridge), not only a session JWT.

`/v1/policies` + `/v1/policy-packs/import` go through `_require_policy_admin`, which used to resolve the
actor via the JWT IdentityPort only — so a `qk_` key got "Invalid JWT". The bridge resolves the actor
from the verified principal for `qk_` bearers; an owner key carries `policy_admin`, a narrow key does not.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from adapters.policy.memory import InMemoryPolicyRepository
from core.account.engine import AccountEngine
from core.account.scopes import LEDGER_READ
from core.account.store import AccountStore
from core.entitlements import EntitlementStore
from core.policy.store import PolicyStore
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel

from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy


def _kernel(tenant):
    repo = InMemoryPolicyRepository()
    return Kernel.from_parts(
        tenant=tenant,
        policy=FakePolicy(),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(roles=("role:policy_admin",)),
        policy_store=PolicyStore(repository=repo),
        policy_repository=repo,
    )


@asynccontextmanager
async def _client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def _register_body() -> dict:
    return {
        "id": "p.demo", "version": 1, "governs": "payments.wire", "scope": {"tenant": "*"},
        "condition": "true", "decision": "allow", "approvers": [], "regulatory_refs": [],
    }


async def test_owner_api_key_can_author_policies() -> None:
    accounts = AccountStore()
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    account, key = eng.signup(email="a@b.io", name="Acme")  # owner (tenant-root) key
    app = create_app(_kernel(account.tenant_id), account_engine=eng, require_api_key=True)

    async with _client(app) as c:
        r = await c.post(
            "/v1/policies",
            json=_register_body(),
            headers={"Authorization": f"Bearer {key}", "X-Tenant-Id": str(account.tenant_id)},
        )
    # Bridged: the owner key resolves a policy_admin actor → policy is registered (was 401 "Invalid JWT").
    assert r.status_code in (200, 201), r.text


async def test_narrow_api_key_is_forbidden() -> None:
    accounts = AccountStore()
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    account, _ = eng.signup(email="a@b.io", name="Acme")
    _rec, narrow = eng.issue_api_key(account.tenant_id, scopes={LEDGER_READ})  # no policy:admin scope
    app = create_app(_kernel(account.tenant_id), account_engine=eng, require_api_key=True)

    async with _client(app) as c:
        r = await c.post(
            "/v1/policies",
            json=_register_body(),
            headers={"Authorization": f"Bearer {narrow}", "X-Tenant-Id": str(account.tenant_id)},
        )
    assert r.status_code == 403, r.text
