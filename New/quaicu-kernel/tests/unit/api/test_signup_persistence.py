"""Regression: self-serve signup must persist the STARTER plan DURABLY, not cache-only.

`AccountEngine.signup` writes the plan to the entitlement cache (sync); the route must additionally
persist it (async `upsert_persisted`), else the plan is lost on the next redeploy and tenant→kernel
routing fails PLAN_NOT_FOUND (dashboard/audit/approvals 503).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from core.account.model import Account, AccountStatus
from core.types import TenantId
from delivery.api.routes.signup import _persist_starter_plan


class _RecordingStore:
    def __init__(self) -> None:
        self.saved: list = []

    async def upsert_persisted(self, plan):  # noqa: ANN001
        self.saved.append(plan)
        return plan


def _request(store) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entitlement_store=store)))


def _account() -> Account:
    return Account(
        account_id="acct_x",
        tenant_id=TenantId("acme-123"),
        email="x@acme-bank.com",
        name="Acme",
        status=AccountStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )


def test_signup_persists_starter_plan_durably():
    store = _RecordingStore()
    asyncio.run(_persist_starter_plan(_request(store), _account()))
    assert len(store.saved) == 1
    plan = store.saved[0]
    assert str(plan.tenant_id) == "acme-123"
    assert plan.tier.value == "STARTER" and plan.status.value == "ACTIVE"


def test_no_entitlement_store_is_a_noop():
    # In-memory / no-durable deploys: nothing to persist, must not error.
    asyncio.run(_persist_starter_plan(_request(None), _account()))
