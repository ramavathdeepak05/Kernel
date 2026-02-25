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


@pytest.fixture(scope="module")
def audit_app():
    """ Setup mocks and return a TestClient for the audit API. """
    # 1. Save original modules to avoid poisoning the test suite
    _orig_modules = sys.modules.copy()
    
    try:
        # 2. Mock out core dependencies before loading the router
        mock_security = MagicMock()
        mock_security.get_current_tenant_id.return_value = "tenant_123"
        sys.modules["server.core.security"] = mock_security

        mock_rbac = MagicMock()
        mock_rbac.Permission.AUDIT_LOG_READ = "audit_log:read"
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

        # 3. Lazy import the router and create the app
        from server.api.audit_router import router
        app = FastAPI()
        app.include_router(router)
        
        # Store mock_ledger_class on the client so tests can access it
        client = TestClient(app)
        client.mock_ledger = mock_ledger_class
        
        yield client

    finally:
        # 4. Restore original modules
        for mod_name in list(sys.modules.keys()):
            if mod_name not in _orig_modules:
                del sys.modules[mod_name]
            else:
                sys.modules[mod_name] = _orig_modules[mod_name]


# ============================================================================
# TESTS
# ============================================================================

class TestAuditAPI:

    def test_verify_chain_success(self, audit_app):
        """When chain is unbroken, returns 200 with valid=true."""
        audit_app.mock_ledger.verify_chain_integrity.return_value = {
            "valid": True,
            "total_entries": 42,
            "first_invalid_id": None,
            "message": "All 42 entries verified successfully."
        }
        
        response = audit_app.get("/api/v1/audit/verify")
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True
        assert data["total_entries"] == 42
        
        # Verify tenant logic was applied
        audit_app.mock_ledger.verify_chain_integrity.assert_called_once_with("tenant_123")

    def test_verify_chain_tampered(self, audit_app):
        """When chain is broken, returns 409 Conflict with valid=false."""
        audit_app.mock_ledger.verify_chain_integrity.return_value = {
            "valid": False,
            "total_entries": 5,
            "first_invalid_id": 3,
            "message": "Hash mismatch at entry 3"
        }
        
        response = audit_app.get("/api/v1/audit/verify")
        assert response.status_code == 409  # 409 Conflict
        
        data = response.json()
        assert data["valid"] is False
        assert data["first_invalid_id"] == 3

    def test_export_ledger_json(self, audit_app):
        """Export defaults to JSON and sets Content-Disposition header."""
        audit_app.mock_ledger.export_ledger.return_value = '[{"id":1}]'
        
        response = audit_app.get("/api/v1/audit/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment; filename=audit_ledger_tenant_123.json" in response.headers["content-disposition"]
        assert response.json() == [{"id": 1}]
        
        # Ensure it passed kwargs correctly
        audit_app.mock_ledger.export_ledger.assert_called_with(
            tenant_id="tenant_123",
            fmt="json",
            start_time=None,
            end_time=None
        )

    def test_export_ledger_csv(self, audit_app):
        """Export handles CSV format."""
        audit_app.mock_ledger.export_ledger.return_value = "id,tenant_id,actor_id\n1,tenant_123,admin_user"
        
        response = audit_app.get("/api/v1/audit/export?fmt=csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment; filename=audit_ledger_tenant_123.csv" in response.headers["content-disposition"]
        assert "admin_user" in response.text

    def test_export_ledger_filters(self, audit_app):
        """Export handles datetime filtering."""
        audit_app.mock_ledger.export_ledger.return_value = "[]"
        
        start_dt = "2025-01-01T00:00:00Z"
        end_dt = "2025-12-31T23:59:59Z"
        
        response = audit_app.get(f"/api/v1/audit/export?start_time={start_dt}&end_time={end_dt}")
        assert response.status_code == 200
        
        # Verify it converted strings to datetimes
        call_args = audit_app.mock_ledger.export_ledger.call_args[1]
        assert call_args["start_time"].isoformat() == "+00:00".join(start_dt.split("Z"))
        assert call_args["end_time"].isoformat() == "+00:00".join(end_dt.split("Z"))
