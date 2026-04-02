"""
S8 TenantStack Operator — Unit Tests

Tests the reconciler logic without requiring a live Kubernetes cluster.
The TenantReconciler class is pure-function based: takes spec + status dicts,
returns new status dict. kopf handlers are thin wrappers.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
import sys
import os

# Add operator src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.reconciler import TenantReconciler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reconciler():
    """TenantReconciler with mocked control plane calls."""
    return TenantReconciler(cp_url="http://localhost:8001", cp_token="test-token")


def _base_spec(**overrides):
    spec = {
        "subdomain": "iitb",
        "displayName": "IIT Bombay",
        "plan": "enterprise",
        "region": "in-central",
        "featureFlags": {},
        "suspended": False,
    }
    spec.update(overrides)
    return spec


# ---------------------------------------------------------------------------
# TestReconcile — Create path
# ---------------------------------------------------------------------------

class TestReconcileCreate:

    def test_new_tenant_gets_uuid(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.post", return_value=mock_resp):
            status = reconciler.reconcile(_base_spec(), {}, "iitb")

        assert status["tenantId"] is not None
        assert len(status["tenantId"]) == 36  # UUID format

    def test_new_tenant_becomes_active(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.post", return_value=mock_resp):
            status = reconciler.reconcile(_base_spec(), {}, "iitb")

        assert status["phase"] == "Active"
        assert status["controlPlaneRegistered"] is True
        assert status["databaseReady"] is True
        assert status["bucketReady"] is True

    def test_provision_failure_sets_failed_phase(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("httpx.post", return_value=mock_resp):
            status = reconciler.reconcile(_base_spec(), {}, "iitb")

        assert status["phase"] == "Failed"
        assert "Provisioning failed" in status["message"]

    def test_network_error_sets_failed_phase(self, reconciler):
        with patch("httpx.post", side_effect=Exception("connection refused")):
            status = reconciler.reconcile(_base_spec(), {}, "iitb")

        assert status["phase"] == "Failed"

    def test_already_active_tenant_is_noop(self, reconciler):
        existing_status = {
            "phase": "Active",
            "tenantId": str(uuid.uuid4()),
            "controlPlaneRegistered": True,
            "databaseReady": True,
            "bucketReady": True,
        }

        # Should NOT call control plane at all
        with patch("httpx.post") as mock_post:
            status = reconciler.reconcile(_base_spec(), existing_status, "iitb")
            mock_post.assert_not_called()

        assert status["phase"] == "Active"

    def test_reconcile_sets_last_reconcile_time(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.post", return_value=mock_resp):
            status = reconciler.reconcile(_base_spec(), {}, "iitb")

        assert "lastReconcileTime" in status

    def test_provision_sends_correct_payload(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            reconciler.reconcile(
                _base_spec(subdomain="woxsen", plan="growth"),
                {},
                "woxsen",
            )

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["subdomain"] == "woxsen"
        assert payload["plan"] == "growth"


# ---------------------------------------------------------------------------
# TestReconcile — Suspension / Reactivation
# ---------------------------------------------------------------------------

class TestReconcileSuspension:

    def test_suspend_tenant(self, reconciler):
        existing_status = {
            "phase": "Active",
            "tenantId": str(uuid.uuid4()),
            "controlPlaneRegistered": True,
            "databaseReady": True,
            "bucketReady": True,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.put", return_value=mock_resp):
            status = reconciler.reconcile(
                _base_spec(suspended=True),
                existing_status,
                "iitb",
            )

        assert status["phase"] == "Suspended"
        assert "suspended" in status["message"].lower()

    def test_reactivate_tenant(self, reconciler):
        existing_status = {
            "phase": "Suspended",
            "tenantId": str(uuid.uuid4()),
            "controlPlaneRegistered": True,
            "databaseReady": True,
            "bucketReady": True,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.put", return_value=mock_resp):
            status = reconciler.reconcile(
                _base_spec(suspended=False),
                existing_status,
                "iitb",
            )

        assert status["phase"] == "Active"
        assert "reactivated" in status["message"].lower()

    def test_suspend_calls_control_plane(self, reconciler):
        tid = str(uuid.uuid4())
        existing_status = {
            "phase": "Active",
            "tenantId": tid,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.put", return_value=mock_resp) as mock_put:
            reconciler.reconcile(_base_spec(suspended=True), existing_status, "iitb")

        mock_put.assert_called_once()
        url = mock_put.call_args[0][0]
        assert f"/admin/tenants/{tid}/suspend" in url


# ---------------------------------------------------------------------------
# TestReconcile — Delete
# ---------------------------------------------------------------------------

class TestReconcileDelete:

    def test_delete_calls_control_plane(self, reconciler):
        tid = str(uuid.uuid4())
        status = {"tenantId": tid}

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.delete", return_value=mock_resp) as mock_del:
            reconciler.handle_delete(_base_spec(), status, "iitb")

        mock_del.assert_called_once()
        url = mock_del.call_args[0][0]
        assert f"/admin/tenants/{tid}" in url

    def test_delete_without_tenant_id_is_noop(self, reconciler):
        with patch("httpx.delete") as mock_del:
            reconciler.handle_delete(_base_spec(), {}, "iitb")
            mock_del.assert_not_called()

    def test_delete_handles_404_gracefully(self, reconciler):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.delete", return_value=mock_resp):
            # Should not raise
            reconciler.handle_delete(
                _base_spec(),
                {"tenantId": str(uuid.uuid4())},
                "iitb",
            )

    def test_delete_handles_network_error(self, reconciler):
        with patch("httpx.delete", side_effect=Exception("timeout")):
            # Should not raise — just log
            reconciler.handle_delete(
                _base_spec(),
                {"tenantId": str(uuid.uuid4())},
                "iitb",
            )


# ---------------------------------------------------------------------------
# TestCRDSchema — structural checks on the CRD YAML
# ---------------------------------------------------------------------------

class TestCRDSchema:

    @pytest.fixture(autouse=True)
    def load_crd(self):
        import yaml
        crd_path = os.path.join(os.path.dirname(__file__), "..", "crds", "tenantstack.yaml")
        with open(crd_path) as f:
            self.crd = yaml.safe_load(f)

    def test_crd_group_is_alis_app(self):
        assert self.crd["spec"]["group"] == "alis.app"

    def test_crd_kind_is_tenant_stack(self):
        assert self.crd["spec"]["names"]["kind"] == "TenantStack"

    def test_crd_has_status_subresource(self):
        v = self.crd["spec"]["versions"][0]
        assert "status" in v["subresources"]

    def test_crd_spec_requires_subdomain_and_plan(self):
        v = self.crd["spec"]["versions"][0]
        required = v["schema"]["openAPIV3Schema"]["properties"]["spec"]["required"]
        assert "subdomain" in required
        assert "plan" in required

    def test_plan_enum_has_three_tiers(self):
        v = self.crd["spec"]["versions"][0]
        plan_enum = v["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]["plan"]["enum"]
        assert set(plan_enum) == {"starter", "growth", "enterprise"}

    def test_status_phase_enum_complete(self):
        v = self.crd["spec"]["versions"][0]
        phases = v["schema"]["openAPIV3Schema"]["properties"]["status"]["properties"]["phase"]["enum"]
        assert "Active" in phases
        assert "Suspended" in phases
        assert "Failed" in phases
        assert "Provisioning" in phases

    def test_printer_columns_include_subdomain_and_phase(self):
        v = self.crd["spec"]["versions"][0]
        col_names = [c["name"] for c in v["additionalPrinterColumns"]]
        assert "Subdomain" in col_names
        assert "Phase" in col_names
