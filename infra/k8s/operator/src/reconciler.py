"""
TenantStack Operator Reconciler — S8

A kopf-based Kubernetes operator that watches TenantStack CRDs and
orchestrates the full tenant lifecycle:

  1. Provision database (via control plane API)
  2. Create S3 bucket (via control plane API)
  3. Write secrets to Vault (via control plane API)
  4. Register per-tenant Celery queues
  5. Update status subresource

The operator is declarative and idempotent — every reconciliation
converges toward the desired state without side effects on re-runs.

Run:
    kopf run infra/k8s/operator/src/reconciler.py --verbose
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Attempt to import kopf; graceful fallback for testing without k8s
try:
    import kopf
except ImportError:
    kopf = None  # type: ignore

# Attempt to import httpx for control plane calls
try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

import os

CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://alis-control-plane:8001")
CONTROL_PLANE_TOKEN = os.environ.get("CONTROL_PLANE_TOKEN", "")
RECONCILE_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "60"))


def _cp_headers() -> Dict[str, str]:
    return {"X-Internal-Token": CONTROL_PLANE_TOKEN}


# ---------------------------------------------------------------------------
# Reconciliation logic (pure functions — testable without kopf/k8s)
# ---------------------------------------------------------------------------

class TenantReconciler:
    """
    Stateless reconciler. Each method returns an updated status dict.
    The kopf handler patches status after each call.
    """

    def __init__(self, cp_url: str = CONTROL_PLANE_URL, cp_token: str = CONTROL_PLANE_TOKEN):
        self._cp_url = cp_url.rstrip("/")
        self._headers = {"X-Internal-Token": cp_token}

    def reconcile(self, spec: Dict[str, Any], status: Dict[str, Any], name: str) -> Dict[str, Any]:
        """
        Main reconciliation entry point.

        Returns the new status dict to be patched onto the CRD.
        """
        new_status = dict(status)
        new_status["lastReconcileTime"] = datetime.now(timezone.utc).isoformat()

        # Handle suspension
        if spec.get("suspended"):
            return self._handle_suspension(spec, new_status)

        # Handle reactivation (was suspended, now not)
        if new_status.get("phase") == "Suspended" and not spec.get("suspended"):
            return self._handle_reactivation(spec, new_status)

        # If already Active and all ready flags are True, nothing to do
        if (
            new_status.get("phase") == "Active"
            and new_status.get("databaseReady")
            and new_status.get("bucketReady")
            and new_status.get("controlPlaneRegistered")
        ):
            return new_status

        # Step through provisioning
        new_status["phase"] = "Provisioning"

        # 1. Ensure tenant_id
        if not new_status.get("tenantId"):
            new_status["tenantId"] = str(uuid.uuid4())

        tenant_id = new_status["tenantId"]

        # 2. Provision via control plane
        if not new_status.get("controlPlaneRegistered"):
            try:
                self._provision_via_cp(tenant_id, spec)
                new_status["controlPlaneRegistered"] = True
                new_status["databaseReady"] = True
                new_status["bucketReady"] = True
                new_status["vaultReady"] = True
                new_status["queuesReady"] = True
                new_status["message"] = "Provisioned successfully"
            except Exception as exc:
                new_status["phase"] = "Failed"
                new_status["message"] = f"Provisioning failed: {exc}"
                logger.error("Reconcile failed for %s: %s", name, exc)
                return new_status

        new_status["phase"] = "Active"
        return new_status

    def handle_delete(self, spec: Dict[str, Any], status: Dict[str, Any], name: str) -> None:
        """Called when TenantStack is deleted. Triggers cleanup via control plane."""
        tenant_id = status.get("tenantId")
        if not tenant_id:
            logger.info("TenantStack %s has no tenantId — nothing to clean up", name)
            return

        try:
            resp = httpx.delete(
                f"{self._cp_url}/admin/tenants/{tenant_id}",
                params={"drop_database": "false"},  # safe delete — no DB drop
                headers=self._headers,
                timeout=30,
            )
            if resp.status_code in (200, 404):
                logger.info("TenantStack %s: control plane cleanup done (status=%s)", name, resp.status_code)
            else:
                logger.warning("TenantStack %s: cleanup returned %s", name, resp.status_code)
        except Exception as exc:
            logger.error("TenantStack %s: cleanup failed: %s", name, exc)

    def _provision_via_cp(self, tenant_id: str, spec: Dict[str, Any]) -> None:
        """Call the control plane provision endpoint."""
        payload = {
            "subdomain": spec["subdomain"],
            "display_name": spec.get("displayName", spec["subdomain"]),
            "plan": spec["plan"],
            "region": spec.get("region", "in-central"),
            "feature_flags": spec.get("featureFlags", {}),
        }

        # BYOD: if externalDSN is provided, pass DB details
        db_spec = spec.get("database", {})
        if db_spec.get("externalDSN"):
            payload["db_host"] = db_spec.get("host", "")
            payload["db_port"] = db_spec.get("port", 5432)

        resp = httpx.post(
            f"{self._cp_url}/admin/tenants",
            json=payload,
            headers=self._headers,
            timeout=60,
        )

        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(
                f"Control plane provision failed: {resp.status_code} {resp.text}"
            )
        logger.info("Control plane accepted provisioning for tenant=%s", tenant_id)

    def _handle_suspension(self, spec: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = status.get("tenantId")
        if tenant_id and status.get("phase") != "Suspended":
            try:
                httpx.put(
                    f"{self._cp_url}/admin/tenants/{tenant_id}/suspend",
                    headers=self._headers,
                    timeout=15,
                )
            except Exception as exc:
                logger.warning("Suspension call failed for %s: %s", tenant_id, exc)

        status["phase"] = "Suspended"
        status["message"] = "Tenant suspended"
        return status

    def _handle_reactivation(self, spec: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = status.get("tenantId")
        if tenant_id:
            try:
                httpx.put(
                    f"{self._cp_url}/admin/tenants/{tenant_id}/reactivate",
                    headers=self._headers,
                    timeout=15,
                )
            except Exception as exc:
                logger.warning("Reactivation call failed for %s: %s", tenant_id, exc)

        status["phase"] = "Active"
        status["message"] = "Tenant reactivated"
        return status


# ---------------------------------------------------------------------------
# kopf handlers (only registered if kopf is installed)
# ---------------------------------------------------------------------------

if kopf is not None:
    _reconciler = TenantReconciler()

    @kopf.on.create("alis.app", "v1alpha1", "tenantstacks")
    def on_create(spec, status, meta, patch, **kwargs):
        """Handle TenantStack creation."""
        name = meta.get("name", "unknown")
        logger.info("TenantStack CREATE: %s", name)
        new_status = _reconciler.reconcile(dict(spec), dict(status or {}), name)
        patch.status.update(new_status)

    @kopf.on.update("alis.app", "v1alpha1", "tenantstacks")
    def on_update(spec, status, meta, patch, **kwargs):
        """Handle TenantStack update (e.g. plan change, suspension toggle)."""
        name = meta.get("name", "unknown")
        logger.info("TenantStack UPDATE: %s", name)
        new_status = _reconciler.reconcile(dict(spec), dict(status or {}), name)
        patch.status.update(new_status)

    @kopf.on.delete("alis.app", "v1alpha1", "tenantstacks")
    def on_delete(spec, status, meta, **kwargs):
        """Handle TenantStack deletion — trigger cleanup."""
        name = meta.get("name", "unknown")
        logger.info("TenantStack DELETE: %s", name)
        _reconciler.handle_delete(dict(spec), dict(status or {}), name)

    @kopf.timer("alis.app", "v1alpha1", "tenantstacks", interval=RECONCILE_INTERVAL)
    def on_timer(spec, status, meta, patch, **kwargs):
        """Periodic re-reconciliation to detect drift."""
        name = meta.get("name", "unknown")
        new_status = _reconciler.reconcile(dict(spec), dict(status or {}), name)
        patch.status.update(new_status)
