"""
S9 Billing API + Plan Configuration — Unit Tests

Tests for:
- PlanStore       : CRUD operations on cp_plans
- Plan admin API  : /admin/billing/plans/*
- Tenant portal   : /tenant/billing/usage, /tenant/billing/invoices
- Payment webhook : /webhook/payments/{provider}
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_cp_db():
    _plans: list[dict] = []
    _usage: list[dict] = []
    _invoices: list[dict] = []
    _payments: list[dict] = []
    _tenants: list[dict] = []
    _lastval = [0]

    def _query(sql: str, params=None) -> list:
        su = sql.upper().strip()

        # LASTVAL
        if "LASTVAL()" in su:
            return [{"id": _lastval[0]}]

        # cp_plans
        if "CP_PLANS" in su:
            if "WHERE NAME = %S" in su.replace("name", "NAME"):
                name = params[0] if params else None
                return [p for p in _plans if p["name"] == name and (
                    "ACTIVE" not in su or p.get("status") == "active"
                )]
            return [p for p in _plans if "ARCHIVED" in su or p.get("status") == "active"]

        # cp_usage_events aggregate
        if "CP_USAGE_EVENTS" in su and ("SUM(" in su or "MAX(" in su):
            tid = params[0] if params else None
            filtered = [r for r in _usage if str(r.get("tenant_id")) == str(tid)]
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

        # cp_invoices single
        if "CP_INVOICES" in su and "TENANT_ID" in su and "PERIOD" in su and "COUNT" not in su and "ORDER" not in su:
            if params and len(params) >= 2:
                tid, period = str(params[0]), str(params[1])
                return [i for i in _invoices if i["tenant_id"] == tid and i["period"] == period]

        # cp_invoices count
        if "CP_INVOICES" in su and "COUNT(*)" in su:
            return [{"n": len(_invoices)}]

        # cp_invoices list
        if "CP_INVOICES" in su and "ORDER" in su:
            return _invoices[:]

        return []

    def _execute(sql: str, params=None) -> None:
        su = sql.upper().strip()
        if "INSERT INTO CP_PLANS" in su:
            _plans.append({
                "name": params[0],
                "monthly_price_usd": params[1],
                "token_quota": params[2],
                "storage_gb_quota": params[3],
                "api_call_quota": params[4],
                "active_user_quota": params[5],
                "overage_token_per_1k": params[6],
                "overage_storage_gb": params[7],
                "overage_api_per_1k": params[8],
                "overage_user": params[9],
                "status": "active",
            })
        elif "UPDATE CP_PLANS" in su and "STATUS = 'ARCHIVED'" in su:
            name = params[0] if params else None
            for p in _plans:
                if p["name"] == name:
                    p["status"] = "archived"
        elif "UPDATE CP_PLANS" in su:
            name = params[-1] if params else None
            for p in _plans:
                if p["name"] == name:
                    # Apply updates (simplified)
                    pass
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
        elif "INSERT INTO CP_PAYMENTS" in su:
            _payments.append({
                "tenant_id": params[0],
                "provider": params[1],
                "provider_payment_id": params[2],
                "amount": params[3],
                "currency": params[4],
                "status": params[5],
            })
        elif "UPDATE CP_INVOICES" in su and "SET STATUS = 'PAID'" in su:
            tid, period = str(params[0]), str(params[1])
            for inv in _invoices:
                if inv["tenant_id"] == tid and inv["period"] == period:
                    inv["status"] = "paid"
        elif "UPDATE CP_INVOICES" in su and "SET STATUS = 'ISSUED'" in su:
            tid, period = str(params[0]), str(params[1])
            for inv in _invoices:
                if inv["tenant_id"] == tid and inv["period"] == period:
                    inv["status"] = "issued"

    with patch("control_plane.db.query", side_effect=_query), \
         patch("control_plane.db.execute", side_effect=_execute):
        yield {
            "plans": _plans,
            "usage": _usage,
            "invoices": _invoices,
            "payments": _payments,
        }


@pytest.fixture
def test_client(patch_cp_db):
    from control_plane.main import create_app
    with patch("control_plane.db.init_db_pool"), \
         patch("control_plane.db.init_schema"):
        app = create_app()
    return TestClient(app)


def _admin_headers():
    from jose import jwt
    from control_plane.settings import settings
    token = jwt.encode(
        {"sub": "admin", "role": "SUPER_ADMIN", "exp": int(time.time()) + 3600},
        settings.admin_jwt_secret,
        algorithm=settings.admin_jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _internal_headers():
    from control_plane.settings import settings
    return {"X-Internal-Token": settings.internal_token}


# ---------------------------------------------------------------------------
# TestPlanStore
# ---------------------------------------------------------------------------

class TestPlanStore:

    def test_get_falls_back_to_hardcoded(self, patch_cp_db):
        from control_plane.plan_store import PlanStore
        plan = PlanStore().get("starter")
        assert plan.name == "starter"
        assert plan.monthly_price_usd == Decimal("49.00")

    def test_create_plan(self, patch_cp_db):
        from control_plane.plan_store import PlanStore
        store = PlanStore()
        store.create(
            name="custom",
            monthly_price_usd=Decimal("299.00"),
            token_quota=500_000,
            storage_gb_quota=100,
            api_call_quota=200_000,
            active_user_quota=100,
            overage_token_per_1k=Decimal("0.25"),
            overage_storage_gb=Decimal("0.07"),
            overage_api_per_1k=Decimal("0.10"),
            overage_user=Decimal("1.50"),
        )
        assert len(patch_cp_db["plans"]) == 1
        assert patch_cp_db["plans"][0]["name"] == "custom"

    def test_archive_plan(self, patch_cp_db):
        from control_plane.plan_store import PlanStore
        patch_cp_db["plans"].append({
            "name": "old_plan",
            "monthly_price_usd": "99.00",
            "token_quota": 50000,
            "storage_gb_quota": 10,
            "api_call_quota": 100000,
            "active_user_quota": 50,
            "overage_token_per_1k": "0.40",
            "overage_storage_gb": "0.09",
            "overage_api_per_1k": "0.15",
            "overage_user": "1.75",
            "status": "active",
        })
        PlanStore().archive("old_plan")
        assert patch_cp_db["plans"][0]["status"] == "archived"


# ---------------------------------------------------------------------------
# TestPlanAdminAPI
# ---------------------------------------------------------------------------

class TestPlanAdminAPI:

    def test_list_plans_returns_defaults(self, test_client):
        resp = test_client.get("/admin/billing/plans", headers=_admin_headers())
        assert resp.status_code == 200
        plans = resp.json()["plans"]
        assert len(plans) >= 3
        names = {p["name"] for p in plans}
        assert {"starter", "growth", "enterprise"} <= names

    def test_create_plan(self, test_client, patch_cp_db):
        body = {
            "name": "premium",
            "monthly_price_usd": "499.00",
            "token_quota": 2000000,
            "storage_gb_quota": 200,
            "api_call_quota": 1000000,
            "active_user_quota": 500,
            "overage_token_per_1k": "0.20",
            "overage_storage_gb": "0.06",
            "overage_api_per_1k": "0.08",
            "overage_user": "1.25",
        }
        resp = test_client.post(
            "/admin/billing/plans",
            json=body,
            headers=_admin_headers(),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "premium"

    def test_create_plan_missing_fields_422(self, test_client):
        resp = test_client.post(
            "/admin/billing/plans",
            json={"name": "incomplete"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 422

    def test_archive_plan(self, test_client, patch_cp_db):
        resp = test_client.delete(
            "/admin/billing/plans/starter",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"


# ---------------------------------------------------------------------------
# TestTenantPortal
# ---------------------------------------------------------------------------

class TestTenantPortal:

    def test_get_usage(self, test_client, patch_cp_db):
        patch_cp_db["usage"].append({
            "id": 1,
            "tenant_id": "t-portal",
            "event_type": "ai_tokens",
            "quantity": "45000",
            "metadata": {},
        })
        resp = test_client.get(
            "/tenant/billing/usage",
            params={"tenant_id": "t-portal"},
            headers=_internal_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["ai_tokens"] == 45000

    def test_list_invoices(self, test_client, patch_cp_db):
        resp = test_client.get(
            "/tenant/billing/invoices",
            params={"tenant_id": "t-portal"},
            headers=_internal_headers(),
        )
        assert resp.status_code == 200
        assert "invoices" in resp.json()

    def test_get_invoice_not_found(self, test_client):
        resp = test_client.get(
            "/tenant/billing/invoices/2026-03",
            params={"tenant_id": "t-none"},
            headers=_internal_headers(),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestPaymentWebhook
# ---------------------------------------------------------------------------

class TestPaymentWebhook:

    def test_stripe_webhook_records_payment(self, test_client, patch_cp_db):
        payload = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123abc",
                    "amount_received": 4900,
                    "currency": "usd",
                    "metadata": {
                        "tenant_id": "t-stripe",
                        "period": "2026-03",
                    },
                }
            },
        }
        resp = test_client.post("/webhook/payments/stripe", json=payload)
        assert resp.status_code == 200
        assert resp.json()["payment_id"] == "pi_123abc"
        assert resp.json()["status"] == "succeeded"
        assert len(patch_cp_db["payments"]) == 1

    def test_razorpay_webhook_records_payment(self, test_client, patch_cp_db):
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_xyz789",
                        "amount": 19900,
                        "currency": "INR",
                        "notes": {
                            "tenant_id": "t-rp",
                            "period": "2026-03",
                        },
                    }
                }
            },
        }
        resp = test_client.post("/webhook/payments/razorpay", json=payload)
        assert resp.status_code == 200
        assert resp.json()["payment_id"] == "pay_xyz789"

    def test_unknown_provider_returns_400(self, test_client):
        resp = test_client.post("/webhook/payments/paypal", json={})
        assert resp.status_code == 400

    def test_missing_payment_id_returns_400(self, test_client):
        resp = test_client.post("/webhook/payments/stripe", json={"type": "unknown"})
        assert resp.status_code == 400

    def test_stripe_success_marks_invoice_paid(self, test_client, patch_cp_db):
        tid = "t-auto-pay"
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
            "status": "issued",
            "created_at": None,
            "issued_at": None,
        })
        payload = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_auto",
                    "amount_received": 4900,
                    "currency": "usd",
                    "metadata": {"tenant_id": tid, "period": "2026-02"},
                }
            },
        }
        resp = test_client.post("/webhook/payments/stripe", json=payload)
        assert resp.status_code == 200
        assert patch_cp_db["invoices"][0]["status"] == "paid"
