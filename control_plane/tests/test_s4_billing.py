"""
S4 Billing Engine — Unit Tests

Tests for:
- PlanConfig         : correct quota / pricing values
- BillingEngine      : line-item computation, overage math, invoice persistence
- UsageStore         : record, aggregate, list events
- HTTP API           : /internal/billing/usage, /admin/billing/invoices/* endpoints
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# In-memory DB fixture (shared across all test classes)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_cp_db():
    """Replace all control_plane.db calls with in-memory stores."""
    _tenants: list[dict] = []
    _usage: list[dict] = []
    _invoices: list[dict] = []
    _lastval: list[int] = [0]

    def _query(sql: str, params=None) -> list:
        su = sql.upper().strip()

        # lastval() — return the last-inserted usage ID
        if "LASTVAL()" in su:
            return [{"id": _lastval[0]}]

        # COUNT(*) for invoices list
        if "COUNT(*)" in su and "CP_INVOICES" in su:
            rows = _invoices[:]
            if params:
                # Apply simple filters
                for p in params:
                    if p and str(p) in [r.get("tenant_id", "") for r in rows]:
                        rows = [r for r in rows if r.get("tenant_id") == str(p)]
            return [{"n": len(rows)}]

        # cp_usage_events aggregate
        if "CP_USAGE_EVENTS" in su and ("SUM(" in su or "MAX(" in su):
            tid = params[0] if params else None
            filtered = [r for r in _usage if str(r.get("tenant_id")) == str(tid)]
            # Group by event_type
            groups: dict = {}
            for r in filtered:
                et = r["event_type"]
                q = Decimal(str(r["quantity"]))
                if et not in groups:
                    groups[et] = {"total": Decimal("0"), "peak": Decimal("0")}
                groups[et]["total"] += q
                if q > groups[et]["peak"]:
                    groups[et]["peak"] = q
            return [
                {"event_type": et, "total": str(v["total"]), "peak": str(v["peak"])}
                for et, v in groups.items()
            ]

        # cp_usage_events list
        if "CP_USAGE_EVENTS" in su and "SELECT" in su and "SUM" not in su:
            tid = params[0] if params else None
            return [r for r in _usage if str(r.get("tenant_id")) == str(tid)]

        # cp_invoices SELECT single
        if "CP_INVOICES" in su and "WHERE TENANT_ID = %S AND PERIOD = %S" in su.replace(
            "tenant_id", "TENANT_ID"
        ).replace("period", "PERIOD"):
            tid, period = str(params[0]), str(params[1])
            return [r for r in _invoices if r["tenant_id"] == tid and r["period"] == period]

        # cp_invoices SELECT list
        if "CP_INVOICES" in su and "ORDER BY PERIOD DESC" in su:
            rows = _invoices[:]
            if params:
                p_list = list(params)
                for p in p_list:
                    if isinstance(p, str) and "-" in p and len(p) == 7:  # period filter
                        rows = [r for r in rows if r.get("period") == p]
                    elif isinstance(p, str) and len(p) == 36:  # UUID
                        rows = [r for r in rows if r.get("tenant_id") == p]
            return rows

        # cp_tenants for compute_all_active
        if "CP_TENANTS" in su and "STATUS = 'ACTIVE'" in su:
            return [r for r in _tenants if r.get("status") == "active"]

        # cp_tenants single lookup
        if "CP_TENANTS" in su and "WHERE TENANT_ID = %S" in su.replace("tenant_id", "TENANT_ID"):
            tid = str(params[0]) if params else None
            return [r for r in _tenants if str(r.get("tenant_id")) == tid]

        return []

    def _execute(sql: str, params=None) -> None:
        su = sql.upper().strip()
        if "INSERT INTO CP_TENANTS" in su:
            _tenants.append({
                "tenant_id": str(params[0]),
                "subdomain": params[1],
                "plan": params[4] if len(params) > 4 else "starter",
                "status": "active",
            })
        elif "INSERT INTO CP_USAGE_EVENTS" in su:
            _lastval[0] = len(_usage) + 1
            _usage.append({
                "id": _lastval[0],
                "tenant_id": str(params[0]),
                "event_type": params[1],
                "quantity": params[2],
                "metadata": json.loads(params[3]) if params[3] else {},
            })
        elif "INSERT INTO CP_INVOICES" in su:
            _invoices.append({
                "id": len(_invoices) + 1,
                "tenant_id": str(params[0]),
                "period": params[1],
                "period_start": params[2],
                "period_end": params[3],
                "plan": params[4],
                "line_items": params[5],
                "subtotal": params[6],
                "tax": params[7],
                "total": params[8],
                "currency": params[9],
                "status": params[10],
                "created_at": None,
                "issued_at": None,
            })
        elif "UPDATE CP_INVOICES" in su and "LINE_ITEMS" in su:
            # recompute update
            tid, period = str(params[-2]), str(params[-1])
            for inv in _invoices:
                if inv["tenant_id"] == tid and inv["period"] == period:
                    inv["line_items"] = params[0]
                    inv["subtotal"] = params[1]
                    inv["tax"] = params[2]
                    inv["total"] = params[3]
                    inv["plan"] = params[4]
        elif "UPDATE CP_INVOICES" in su and "SET STATUS = 'ISSUED'" in su:
            tid, period = str(params[0]), str(params[1])
            for inv in _invoices:
                if inv["tenant_id"] == tid and inv["period"] == period:
                    inv["status"] = "issued"
                    inv["issued_at"] = "2026-04-01T00:00:00Z"
        elif "UPDATE CP_INVOICES" in su and "SET STATUS = 'PAID'" in su:
            tid, period = str(params[0]), str(params[1])
            for inv in _invoices:
                if inv["tenant_id"] == tid and inv["period"] == period:
                    inv["status"] = "paid"
        elif "UPDATE CP_TENANTS" in su:
            pass

    with patch("control_plane.db.query", side_effect=_query), \
         patch("control_plane.db.execute", side_effect=_execute):
        # Also expose stores for test inspection
        yield {
            "tenants": _tenants,
            "usage": _usage,
            "invoices": _invoices,
        }


@pytest.fixture
def test_client(patch_cp_db):
    """FastAPI TestClient for the control plane app."""
    from control_plane.main import create_app
    with patch("control_plane.db.init_db_pool"), \
         patch("control_plane.db.init_schema"):
        app = create_app()
    return TestClient(app)


def _internal_headers():
    from control_plane.settings import settings
    return {"X-Internal-Token": settings.internal_token}


def _admin_headers():
    """Return a signed admin JWT for tests."""
    import time
    import jwt as _pyjwt
    from control_plane.settings import settings

    token = _pyjwt.encode(
        {"sub": "test-admin", "role": "SUPER_ADMIN", "exp": int(time.time()) + 3600},
        settings.admin_jwt_secret,
        algorithm=settings.admin_jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# TestPlanConfig
# ---------------------------------------------------------------------------

class TestPlanConfig:

    def test_starter_base_price(self):
        from control_plane.billing_models import PLAN_CONFIGS
        assert PLAN_CONFIGS["starter"].monthly_price_usd == Decimal("49.00")

    def test_growth_token_quota(self):
        from control_plane.billing_models import PLAN_CONFIGS
        assert PLAN_CONFIGS["growth"].token_quota == 1_000_000

    def test_enterprise_storage_quota(self):
        from control_plane.billing_models import PLAN_CONFIGS
        assert PLAN_CONFIGS["enterprise"].storage_gb_quota == 500

    def test_all_plans_defined(self):
        from control_plane.billing_models import PLAN_CONFIGS
        assert set(PLAN_CONFIGS.keys()) == {"starter", "growth", "enterprise"}

    def test_overage_prices_decrease_with_plan_tier(self):
        from control_plane.billing_models import PLAN_CONFIGS
        # Higher-tier plans have lower overage rates (volume discount)
        assert (
            PLAN_CONFIGS["starter"].overage_token_per_1k
            > PLAN_CONFIGS["growth"].overage_token_per_1k
            > PLAN_CONFIGS["enterprise"].overage_token_per_1k
        )


# ---------------------------------------------------------------------------
# TestBillingEngine — line item math
# ---------------------------------------------------------------------------

class TestBillingEngine:

    def _engine(self):
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        mock_store = MagicMock(spec=UsageStore)
        return BillingEngine(usage_store=mock_store), mock_store

    def test_base_subscription_line_item(self):
        from control_plane.billing_models import PLAN_CONFIGS, UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03"
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        base = inv.line_items[0]
        assert "monthly subscription" in base.description
        assert base.amount == Decimal("49.00")

    def test_no_overage_within_quota(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            ai_tokens=50_000,  # under 100K starter quota
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        assert len(inv.line_items) == 1  # base only
        assert inv.total == Decimal("49.00")

    def test_token_overage_computed_correctly(self):
        from control_plane.billing_models import PLAN_CONFIGS, UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            ai_tokens=150_000,  # 50K over starter quota of 100K
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        # 50K tokens / 1K * $0.50 = $25.00
        overage_item = next(li for li in inv.line_items if "token overage" in li.description)
        assert overage_item.amount == Decimal("25.00")

    def test_api_call_overage(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            api_calls=60_000,  # 10K over starter quota of 50K
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        overage = next(li for li in inv.line_items if "API call overage" in li.description)
        # 10K calls / 1K * $0.20 = $2.00
        assert overage.amount == Decimal("2.00")

    def test_storage_overage(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            storage_gb=Decimal("8"),  # 3 GB over starter quota of 5
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        overage = next(li for li in inv.line_items if "Storage overage" in li.description)
        # 3 GB * $0.10 = $0.30
        assert overage.amount == Decimal("0.30")

    def test_active_user_overage(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            active_users=30,  # 5 over starter quota of 25
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        overage = next(li for li in inv.line_items if "user overage" in li.description)
        # 5 users * $2.00 = $10.00
        assert overage.amount == Decimal("10.00")

    def test_total_equals_sum_of_line_items(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03",
            ai_tokens=200_000,
            api_calls=100_000,
            storage_gb=Decimal("10"),
            active_users=50,
        )
        inv = engine.compute_invoice("t1", "starter", "2026-03", persist=False)
        expected = sum(li.amount for li in inv.line_items)
        assert inv.total == expected

    def test_period_dates_correct(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-02")
        inv = engine.compute_invoice("t1", "starter", "2026-02", persist=False)
        assert inv.period_start == date(2026, 2, 1)
        assert inv.period_end == date(2026, 2, 28)

    def test_december_period_dates(self):
        from control_plane.billing_models import UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2025-12")
        inv = engine.compute_invoice("t1", "starter", "2025-12", persist=False)
        assert inv.period_start == date(2025, 12, 1)
        assert inv.period_end == date(2025, 12, 31)

    def test_unknown_plan_falls_back_to_starter(self):
        from control_plane.billing_models import PLAN_CONFIGS, UsageSummary

        engine, mock_store = self._engine()
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-03")
        inv = engine.compute_invoice("t1", "unknown_plan", "2026-03", persist=False)
        assert inv.plan == "unknown_plan"
        # falls back to starter config
        assert inv.line_items[0].amount == Decimal("49.00")


# ---------------------------------------------------------------------------
# TestUsageStore
# ---------------------------------------------------------------------------

class TestUsageStore:

    def test_record_returns_event_id(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        event_id = store.record("tenant-1", UsageEventType.AI_TOKENS, Decimal("500"))
        assert event_id > 0

    def test_usage_events_stored_in_db(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        store.record("t-abc", UsageEventType.API_CALLS, Decimal("1000"))
        assert len(patch_cp_db["usage"]) == 1
        assert patch_cp_db["usage"][0]["event_type"] == "api_calls"

    def test_get_summary_aggregates_tokens(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        store.record("t1", UsageEventType.AI_TOKENS, Decimal("40000"))
        store.record("t1", UsageEventType.AI_TOKENS, Decimal("60000"))
        summary = store.get_summary("t1", "2026-03")
        assert summary.ai_tokens == 100_000

    def test_get_summary_uses_peak_for_storage(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        store.record("t1", UsageEventType.STORAGE_GB, Decimal("3"))
        store.record("t1", UsageEventType.STORAGE_GB, Decimal("7"))  # peak
        store.record("t1", UsageEventType.STORAGE_GB, Decimal("5"))
        summary = store.get_summary("t1", "2026-03")
        assert summary.storage_gb == Decimal("7")

    def test_get_summary_uses_peak_for_active_users(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        store.record("t1", UsageEventType.ACTIVE_USERS, Decimal("20"))
        store.record("t1", UsageEventType.ACTIVE_USERS, Decimal("35"))
        summary = store.get_summary("t1", "2026-03")
        assert summary.active_users == 35

    def test_tenants_do_not_see_each_others_usage(self, patch_cp_db):
        from control_plane.billing_models import UsageEventType
        from control_plane.usage_store import UsageStore

        store = UsageStore()
        store.record("tenant-A", UsageEventType.AI_TOKENS, Decimal("100000"))
        store.record("tenant-B", UsageEventType.AI_TOKENS, Decimal("999"))
        summary_a = store.get_summary("tenant-A", "2026-03")
        assert summary_a.ai_tokens == 100_000


# ---------------------------------------------------------------------------
# TestBillingEngineWithDB — persist=True (uses patched DB)
# ---------------------------------------------------------------------------

class TestBillingEngineWithDB:

    def test_invoice_persisted_on_compute(self, patch_cp_db):
        from control_plane.billing_models import UsageSummary
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        mock_store = MagicMock(spec=UsageStore)
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-03")

        engine = BillingEngine(usage_store=mock_store)
        engine.compute_invoice("t1", "starter", "2026-03", persist=True)

        assert len(patch_cp_db["invoices"]) == 1
        assert patch_cp_db["invoices"][0]["period"] == "2026-03"

    def test_draft_invoice_recomputed(self, patch_cp_db):
        from control_plane.billing_models import UsageSummary
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        mock_store = MagicMock(spec=UsageStore)
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-03")

        engine = BillingEngine(usage_store=mock_store)
        engine.compute_invoice("t1", "starter", "2026-03", persist=True)

        # Recompute — same tenant, same period, still draft → should update
        mock_store.get_summary.return_value = UsageSummary(
            tenant_id="t1", period="2026-03", ai_tokens=200_000
        )
        engine.compute_invoice("t1", "starter", "2026-03", persist=True)

        # Still only one invoice row (upserted)
        assert len(patch_cp_db["invoices"]) == 1

    def test_mark_issued(self, patch_cp_db):
        from control_plane.billing_models import UsageSummary
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        mock_store = MagicMock(spec=UsageStore)
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-03")

        engine = BillingEngine(usage_store=mock_store)
        engine.compute_invoice("t1", "starter", "2026-03", persist=True)
        engine.mark_issued("t1", "2026-03")

        assert patch_cp_db["invoices"][0]["status"] == "issued"

    def test_mark_paid(self, patch_cp_db):
        from control_plane.billing_models import UsageSummary
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        mock_store = MagicMock(spec=UsageStore)
        mock_store.get_summary.return_value = UsageSummary(tenant_id="t1", period="2026-03")

        engine = BillingEngine(usage_store=mock_store)
        engine.compute_invoice("t1", "starter", "2026-03", persist=True)
        engine.mark_issued("t1", "2026-03")
        engine.mark_paid("t1", "2026-03")

        assert patch_cp_db["invoices"][0]["status"] == "paid"

    def test_compute_all_active(self, patch_cp_db):
        from control_plane.billing_models import UsageSummary
        from control_plane.billing_engine import BillingEngine
        from control_plane.usage_store import UsageStore

        # Seed two active tenants
        patch_cp_db["tenants"].append({"tenant_id": "t1", "plan": "starter", "status": "active"})
        patch_cp_db["tenants"].append({"tenant_id": "t2", "plan": "growth", "status": "active"})

        mock_store = MagicMock(spec=UsageStore)
        mock_store.get_summary.return_value = UsageSummary(tenant_id="x", period="2026-03")

        engine = BillingEngine(usage_store=mock_store)
        invoices = engine.compute_all_active("2026-03")

        assert len(invoices) == 2


# ---------------------------------------------------------------------------
# TestBillingAPI — HTTP endpoints
# ---------------------------------------------------------------------------

class TestBillingAPI:

    def test_record_usage_event(self, test_client, patch_cp_db):
        resp = test_client.post(
            "/internal/billing/usage",
            json={
                "tenant_id": "t-001",
                "event_type": "ai_tokens",
                "quantity": "5000",
                "metadata": {},
            },
            headers=_internal_headers(),
        )
        assert resp.status_code == 201
        assert resp.json()["recorded"] is True

    def test_record_usage_requires_internal_token(self, test_client):
        resp = test_client.post(
            "/internal/billing/usage",
            json={"tenant_id": "t1", "event_type": "ai_tokens", "quantity": "100"},
        )
        assert resp.status_code == 422  # missing header → validation error (not 401)

    def test_get_usage_summary(self, test_client, patch_cp_db):
        # Seed usage
        patch_cp_db["usage"].append({
            "id": 1,
            "tenant_id": "t-002",
            "event_type": "ai_tokens",
            "quantity": "80000",
            "metadata": {},
        })
        resp = test_client.get(
            "/internal/billing/usage/t-002",
            params={"period": "2026-03"},
            headers=_internal_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "t-002"
        assert data["ai_tokens"] == 80_000

    def test_generate_tenant_invoice(self, test_client, patch_cp_db):
        from control_plane.crypto import encrypt

        tid = str(uuid.uuid4())
        patch_cp_db["tenants"].append({
            "tenant_id": tid,
            "subdomain": "testuni",
            "display_name": "Test Uni",
            "region": "in-central",
            "db_host": "localhost",
            "db_port": 5432,
            "db_name": f"alis_testuni",
            "db_user": "alis_testuni",
            "db_password_enc": encrypt("pw"),
            "plan": "growth",
            "feature_flags": {},
            "status": "active",
            "created_at": None,
            "updated_at": None,
            "suspended_at": None,
            "deleted_at": None,
        })

        resp = test_client.post(
            f"/admin/billing/invoices/{tid}/2026-03",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == tid
        assert data["period"] == "2026-03"
        assert len(data["line_items"]) >= 1

    def test_generate_invoices_all(self, test_client, patch_cp_db):
        patch_cp_db["tenants"].append(
            {"tenant_id": str(uuid.uuid4()), "plan": "starter", "status": "active"}
        )
        resp = test_client.post(
            "/admin/billing/invoices/generate",
            params={"period": "2026-03"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["generated"] >= 1

    def test_issue_invoice(self, test_client, patch_cp_db):
        tid = str(uuid.uuid4())
        patch_cp_db["tenants"].append({"tenant_id": tid, "plan": "starter", "status": "active"})
        patch_cp_db["invoices"].append({
            "id": 1,
            "tenant_id": tid,
            "period": "2026-02",
            "period_start": date(2026, 2, 1),
            "period_end": date(2026, 2, 28),
            "plan": "starter",
            "line_items": "[]",
            "subtotal": "49.00",
            "tax": "0.00",
            "total": "49.00",
            "currency": "USD",
            "status": "draft",
            "created_at": None,
            "issued_at": None,
        })

        resp = test_client.put(
            f"/admin/billing/invoices/{tid}/2026-02/issue",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "issued"

    def test_issue_non_draft_invoice_returns_409(self, test_client, patch_cp_db):
        tid = str(uuid.uuid4())
        patch_cp_db["invoices"].append({
            "id": 2,
            "tenant_id": tid,
            "period": "2026-01",
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "plan": "starter",
            "line_items": "[]",
            "subtotal": "49.00",
            "tax": "0.00",
            "total": "49.00",
            "currency": "USD",
            "status": "paid",
            "created_at": None,
            "issued_at": None,
        })

        resp = test_client.put(
            f"/admin/billing/invoices/{tid}/2026-01/issue",
            headers=_admin_headers(),
        )
        assert resp.status_code == 409

    def test_get_invoice_not_found(self, test_client, patch_cp_db):
        resp = test_client.get(
            f"/admin/billing/invoices/{uuid.uuid4()}/2026-03",
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    def test_list_invoices(self, test_client, patch_cp_db):
        resp = test_client.get(
            "/admin/billing/invoices",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert "invoices" in resp.json()
        assert "total" in resp.json()
