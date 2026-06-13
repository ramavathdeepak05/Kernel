"""API-key authentication middleware + RBAC scope enforcement (ADR-0011, WS-D).

These exercise ``create_app(..., require_api_key=True)``: the management surface requires a valid,
tenant-matched ``qk_`` key, and routes assert the scope they need. The legacy single-kernel path
(``require_api_key`` defaulting to False) stays unauthenticated-by-key — covered by the other API
suites, which still pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.account.scopes import ACTIONS_READ, LEDGER_READ
from core.entitlements import EntitlementStore
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


def _kernel(tenant: str) -> Kernel:
    return Kernel.from_parts(
        tenant=TenantId(tenant),
        policy=FakePolicy(decision=Decision.ALLOW),
        hitl=FakeHITL(),
        ledger=FakeLedger(),
        events=FakeEvents(),
        identity=FakeIdentity(),
    )


def _account_engine() -> tuple[AccountEngine, AccountStore]:
    return AccountEngine(accounts := AccountStore(), EntitlementStore()), accounts


def _add_account(accounts: AccountStore, tenant: str) -> None:
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


def _app(*, tenant: str = "acme", require_api_key: bool = True):
    eng, accounts = _account_engine()
    _add_account(accounts, tenant)
    app = create_app(
        _kernel(tenant),
        account_engine=eng,
        require_api_key=require_api_key,
        rate_limit=False,
    )
    return app, eng


async def test_protected_route_without_key_is_401():
    app, _ = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/ledger/acme/trail")
    assert resp.status_code == 401
    assert resp.json()["code"] == "API_KEY_REQUIRED"


async def test_valid_key_authorizes_request():
    app, eng = _app()
    _, key = eng.issue_api_key(TenantId("acme"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/ledger/acme/trail", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant"] == "acme"


async def test_key_for_another_tenant_is_403():
    app, eng = _app(tenant="acme")
    # A key owned by a different tenant cannot act against the acme deployment.
    eng._accounts.add_account(  # type: ignore[attr-defined]
        Account(
            account_id="acct_other",
            tenant_id=TenantId("other"),
            email="other@b.io",
            name="other",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    _, other_key = eng.issue_api_key(TenantId("other"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/ledger/acme/trail", headers={"Authorization": f"Bearer {other_key}"}
        )
    assert resp.status_code == 403
    assert resp.json()["code"] == "TENANT_ISOLATION"


async def test_revoked_key_is_401():
    app, eng = _app()
    record, key = eng.issue_api_key(TenantId("acme"))
    eng.revoke_api_key(record.key_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/ledger/acme/trail", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "API_KEY_INVALID"


async def test_key_missing_required_scope_is_403():
    app, eng = _app()
    # Key can read actions but NOT the ledger.
    _, key = eng.issue_api_key(TenantId("acme"), scopes={ACTIONS_READ})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/ledger/acme/trail", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "INSUFFICIENT_SCOPE"
    assert resp.json()["detail"]["detail"]["required"] == LEDGER_READ


async def test_signup_is_exempt_from_api_key_requirement():
    # Onboarding must work without a key even when require_api_key is on.
    eng, _ = _account_engine()
    app = create_app(_kernel("acme"), account_engine=eng, require_api_key=True, rate_limit=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/signup", json={"email": "n@b.io", "name": "New"})
    assert resp.status_code == 201
    assert resp.json()["api_key"].startswith("qk_")
