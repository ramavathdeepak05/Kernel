"""
Tests for ALIS Immutable Audit Ledger API (E00-S02)

Verifies the FastAPI endpoints for hash-chain integrity checking
and ledger export.

Run:  PYTHONPATH=. pytest tests/test_audit_api.py -v
"""

import sys
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


# ============================================================================
# APP SETUP & MOCKS
# ============================================================================

# 1. We mock out the core dependencies before loading the router
#    to avoid DB connection attempts during routing setup.

mock_security = MagicMock()
mock_security.get_current_tenant_id.return_value = "tenant_123"
sys.modules["server.core.security"] = mock_security

mock_rbac = MagicMock()
mock_rbac.Permission.AUDIT_LOG_READ = "audit_log:read"

# Our require_permission decorator mock just returns the function
# (bypassing actual RBAC logic so we can test the controller logic directly)
def mock_require_permission(perm):
    def decorator(func):
        return func
    return decorator

mock_rbac.require_permission = mock_require_permission
sys.modules["server.core.rbac"] = mock_rbac

# Mock AuditLedger
mock_audit = MagicMock()
mock_ledger_class = MagicMock()
mock_audit.AuditLedger = mock_ledger_class
sys.modules["server.core.audit"] = mock_audit

# 2. Now import the router safely
from server.api.audit_router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ============================================================================
# TESTS
# ============================================================================

class TestAuditAPI:

    def test_verify_chain_success(self):
        """When chain is unbroken, returns 200 with valid=true."""
        mock_ledger_class.verify_chain_integrity.return_value = {
            "valid": True,
            "total_entries": 42,
            "first_invalid_id": None,
            "message": "All 42 entries verified successfully."
        }
        
        response = client.get("/api/v1/audit/verify")
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True
        assert data["total_entries"] == 42
        
        # Verify tenant logic was applied
        mock_ledger_class.verify_chain_integrity.assert_called_once_with("tenant_123")

    def test_verify_chain_tampered(self):
        """When chain is broken, returns 409 Conflict with valid=false."""
        mock_ledger_class.verify_chain_integrity.return_value = {
            "valid": False,
            "total_entries": 5,
            "first_invalid_id": 3,
            "message": "Hash mismatch at entry 3"
        }
        
        response = client.get("/api/v1/audit/verify")
        assert response.status_code == 409  # 409 Conflict
        
        data = response.json()
        assert data["valid"] is False
        assert data["first_invalid_id"] == 3

    def test_export_ledger_json(self):
        """Export defaults to JSON and sets Content-Disposition header."""
        mock_ledger_class.export_ledger.return_value = '[{"id":1}]'
        
        response = client.get("/api/v1/audit/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment; filename=audit_ledger_tenant_123.json" in response.headers["content-disposition"]
        assert response.json() == [{"id": 1}]
        
        # Ensure it passed kwargs correctly
        mock_ledger_class.export_ledger.assert_called_with(
            tenant_id="tenant_123",
            fmt="json",
            start_time=None,
            end_time=None
        )

    def test_export_ledger_csv(self):
        """Export handles CSV format."""
        mock_ledger_class.export_ledger.return_value = "id,tenant_id,actor_id\n1,tenant_123,admin_user"
        
        response = client.get("/api/v1/audit/export?fmt=csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment; filename=audit_ledger_tenant_123.csv" in response.headers["content-disposition"]
        assert "admin_user" in response.text

    def test_export_ledger_filters(self):
        """Export handles datetime filtering."""
        mock_ledger_class.export_ledger.return_value = "[]"
        
        start_dt = "2025-01-01T00:00:00Z"
        end_dt = "2025-12-31T23:59:59Z"
        
        response = client.get(f"/api/v1/audit/export?start_time={start_dt}&end_time={end_dt}")
        assert response.status_code == 200
        
        # Verify it converted strings to datetimes
        call_args = mock_ledger_class.export_ledger.call_args[1]
        assert call_args["start_time"].isoformat() == "+00:00".join(start_dt.split("Z"))
        assert call_args["end_time"].isoformat() == "+00:00".join(end_dt.split("Z"))
