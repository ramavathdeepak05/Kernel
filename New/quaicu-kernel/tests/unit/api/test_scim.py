"""SCIM 2.0 provisioning endpoint (W6-1) — /scim/v2/Users."""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.account.scopes import LEDGER_READ, SCIM_ADMIN
from core.entitlements import EntitlementStore
from core.types import Decision, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger, FakePolicy


def _build(tenant: str = "acme"):
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id=f"acct_{tenant}",
            tenant_id=TenantId(tenant),
            email=f"{tenant}@b.io",
            name=tenant,
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    kernel = Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    return app, eng, accounts


def _scim_key(eng) -> str:
    _, plaintext = eng.issue_api_key(TenantId("acme"), scopes=[SCIM_ADMIN])
    return plaintext


async def test_scim_requires_scim_admin_scope():
    app, eng, _ = _build()
    _, weak = eng.issue_api_key(TenantId("acme"), scopes=[LEDGER_READ])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/scim/v2/Users", headers={"Authorization": f"Bearer {weak}"})
    assert r.status_code == 403


async def test_scim_missing_bearer_is_401():
    app, _, _ = _build()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/scim/v2/Users")
    assert r.status_code == 401


async def test_provision_list_and_deactivate_via_patch():
    app, eng, accounts = _build()
    key = _scim_key(eng)
    auth = {"Authorization": f"Bearer {key}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Provision
        created = await client.post(
            "/scim/v2/Users",
            headers=auth,
            json={"userName": "alice@acme.io", "displayName": "Alice", "role": "ADMIN",
                  "externalId": "okta-1"},
        )
        assert created.status_code == 201
        uid = created.json()["id"]
        assert created.json()["active"] is True and created.json()["userName"] == "alice@acme.io"

        # List + filter
        listed = await client.get('/scim/v2/Users?filter=userName eq "alice@acme.io"', headers=auth)
        assert listed.status_code == 200
        assert listed.json()["totalResults"] == 1

        # Bind a key to the member, then de-provision via PATCH active=false → key revoked
        rec, _ = eng.issue_api_key(TenantId("acme"), scopes=[LEDGER_READ], member_id=uid)
        patched = await client.patch(
            f"/scim/v2/Users/{uid}",
            headers=auth,
            json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                  "Operations": [{"op": "replace", "value": {"active": False}}]},
        )
        assert patched.status_code == 200 and patched.json()["active"] is False
        assert accounts.get_api_key(rec.key_id).revoked is True


async def test_provision_is_idempotent_by_external_id():
    app, eng, _ = _build()
    auth = {"Authorization": f"Bearer {_scim_key(eng)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        a = await client.post("/scim/v2/Users", headers=auth,
                              json={"userName": "x@acme.io", "externalId": "e1"})
        b = await client.post("/scim/v2/Users", headers=auth,
                              json={"userName": "x@acme.io", "externalId": "e1", "role": "ADMIN"})
    assert a.json()["id"] == b.json()["id"]


async def test_scim_tenant_isolation():
    app, eng, _ = _build()
    # A member that belongs to another tenant must be invisible to acme's SCIM token.
    other = eng.provision_member(TenantId("other"), email="z@other.io", role="VIEWER")
    auth = {"Authorization": f"Bearer {_scim_key(eng)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/scim/v2/Users/{other.member_id}", headers=auth)
    assert r.status_code == 404
