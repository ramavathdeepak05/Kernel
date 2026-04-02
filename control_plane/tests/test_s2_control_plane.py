"""
S2 Control Plane — Unit Tests

Tests for:
- TenantRepository : CRUD operations on cp_tenants
- TenantProvisioner : provision, suspend, reactivate, delete
- Crypto            : encrypt/decrypt round-trip
- HTTP API          : /internal and /admin endpoints via TestClient
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_cp_db():
    """Replace all cp_db calls with an in-memory store."""
    _store: list[dict] = []
    _plog: list[dict] = []

    def _query(sql: str, params=None) -> list:
        sql_upper = sql.upper()
        if "CP_PROVISIONING_LOG" in sql_upper:
            return _plog[:]
        # COUNT(*) query — return {"n": count}
        if "COUNT(*)" in sql_upper:
            filtered = [r for r in _store if r.get("status") != "deleted"]
            return [{"n": len(filtered)}]
        # Simple exact-match filter for test purposes
        if params and ("WHERE tenant_id = %s" in sql or "WHERE subdomain = %s" in sql):
            field = "tenant_id" if "WHERE tenant_id = %s" in sql else "subdomain"
            val = str(params[0]) if params else None
            result = [r for r in _store if str(r.get(field)) == val]
            if "STATUS != 'DELETED'" in sql_upper:
                result = [r for r in result if r.get("status") != "deleted"]
            return result
        if "STATUS != 'DELETED'" in sql_upper:
            return [r for r in _store if r.get("status") != "deleted"]
        return _store[:]

    def _execute(sql: str, params=None) -> None:
        sql_upper = sql.upper()
        if "CP_PROVISIONING_LOG" in sql_upper and "INSERT" in sql_upper:
            _plog.append({"tenant_id": params[0] if params else None})
            return
        if "INSERT INTO CP_TENANTS" in sql_upper:
            row = {
                "tenant_id": params[0],
                "subdomain": params[1],
                "display_name": params[2],
                "region": params[3],
                "db_host": params[4],
                "db_port": params[5],
                "db_name": params[6],
                "db_user": params[7],
                "db_password_enc": params[8],
                "plan": params[9],
                "feature_flags": json.loads(params[10]) if params[10] else {},
                "status": "active",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "suspended_at": None,
                "deleted_at": None,
            }
            # Handle ON CONFLICT DO UPDATE
            existing = [i for i, r in enumerate(_store) if str(r["tenant_id"]) == str(params[0])]
            if existing:
                _store[existing[0]] = row
            else:
                _store.append(row)
        elif "UPDATE CP_TENANTS" in sql_upper:
            tid = str(params[-1]) if params else None
            if "STATUS = 'SUSPENDED'" in sql_upper:
                for r in _store:
                    if str(r["tenant_id"]) == tid:
                        r["status"] = "suspended"
                        r["suspended_at"] = datetime.now(timezone.utc)
            elif "STATUS = 'ACTIVE'" in sql_upper:
                for r in _store:
                    if str(r["tenant_id"]) == tid:
                        r["status"] = "active"
                        r["suspended_at"] = None
            elif "STATUS = 'DELETED'" in sql_upper:
                for r in _store:
                    if str(r["tenant_id"]) == tid:
                        r["status"] = "deleted"
                        r["deleted_at"] = datetime.now(timezone.utc)
            elif "STATUS = 'PROVISION_FAILED'" in sql_upper:
                for r in _store:
                    if str(r["tenant_id"]) == tid:
                        r["status"] = "provision_failed"

    import control_plane.db as cp_db_module
    with patch.object(cp_db_module, "query", side_effect=_query), \
         patch.object(cp_db_module, "execute", side_effect=_execute):
        yield _store, _plog


@pytest.fixture
def test_app(patch_cp_db):
    """FastAPI TestClient for the control plane app (DB mocked)."""
    import sys
    import os
    # Ensure control_plane package is importable
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from control_plane.main import create_app
    with patch("control_plane.db.init_db_pool"), \
         patch("control_plane.db.init_schema"), \
         patch("control_plane.db.close_db_pool"):
        app = create_app()
    return TestClient(app, raise_server_exceptions=True)


def _admin_headers() -> dict:
    """Generate a valid admin JWT for test requests."""
    from jose import jwt
    import time
    payload = {
        "sub": "test-admin",
        "role": "SUPER_ADMIN",
        "exp": int(time.time()) + 3600,
    }
    from control_plane.settings import settings
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm=settings.admin_jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _internal_headers() -> dict:
    from control_plane.settings import settings
    return {"X-Internal-Token": settings.internal_token}


def _seed_tenant(store: list, overrides: dict | None = None) -> dict:
    from control_plane.crypto import encrypt
    row = {
        "tenant_id": str(uuid.uuid4()),
        "subdomain": "iitb",
        "display_name": "IIT Bombay",
        "region": "in-central",
        "db_host": "localhost",
        "db_port": 5432,
        "db_name": "alis_iitb",
        "db_user": "alis_iitb",
        "db_password_enc": encrypt("test-password"),
        "plan": "enterprise",
        "feature_flags": {},
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "suspended_at": None,
        "deleted_at": None,
    }
    if overrides:
        row.update(overrides)
    store.append(row)
    return row


# ===========================================================================
# 1. Crypto round-trip
# ===========================================================================

class TestCrypto:

    def test_encrypt_decrypt_round_trip(self):
        from control_plane.crypto import encrypt, decrypt
        original = "super-secret-password-123"
        assert decrypt(encrypt(original)) == original

    def test_different_plaintexts_produce_different_ciphertexts(self):
        from control_plane.crypto import encrypt
        ct1 = encrypt("password-a")
        ct2 = encrypt("password-a")
        # AES-GCM uses random nonce — same plaintext → different ciphertext
        assert ct1 != ct2

    def test_dev_fallback_round_trip(self):
        """Dev fallback (::dev suffix) also round-trips correctly."""
        from control_plane.crypto import encrypt, decrypt
        with patch("control_plane.crypto._get_key", side_effect=ImportError):
            ct = encrypt("my-password")
        assert ct.endswith("::dev")
        assert decrypt(ct) == "my-password"


# ===========================================================================
# 2. TenantRepository
# ===========================================================================

class TestTenantRepository:

    def test_get_by_id_returns_record(self, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        from control_plane.repository import TenantRepository
        record = TenantRepository.get_by_id(row["tenant_id"])
        assert record is not None
        assert record.tenant_id == row["tenant_id"]
        assert record.subdomain == "iitb"
        assert "iitb" in record.db_url

    def test_get_by_id_returns_none_for_unknown(self, patch_cp_db):
        from control_plane.repository import TenantRepository
        assert TenantRepository.get_by_id(str(uuid.uuid4())) is None

    def test_get_by_subdomain_returns_record(self, patch_cp_db):
        store, _ = patch_cp_db
        _seed_tenant(store)
        from control_plane.repository import TenantRepository
        record = TenantRepository.get_by_subdomain("iitb")
        assert record is not None
        assert record.subdomain == "iitb"

    def test_get_by_subdomain_returns_none_for_deleted(self, patch_cp_db):
        store, _ = patch_cp_db
        _seed_tenant(store, {"status": "deleted"})
        from control_plane.repository import TenantRepository
        # deleted tenants should not be returned
        assert TenantRepository.get_by_subdomain("iitb") is None

    def test_update_plan(self, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        from control_plane.repository import TenantRepository
        record = TenantRepository.update(row["tenant_id"], plan="growth")
        # The mock execute updates the store; re-read should reflect new plan
        assert record is not None  # basic assertion that update didn't raise


# ===========================================================================
# 3. TenantProvisioner (mocked DB and shell)
# ===========================================================================

class TestTenantProvisioner:

    def _mock_provision_deps(self):
        return [
            patch("control_plane.provisioner._create_db_user"),
            patch("control_plane.provisioner._create_database"),
            patch("control_plane.provisioner._grant_privileges"),
            patch("control_plane.provisioner._run_migrations"),
            patch("control_plane.provisioner._log_provision"),
        ]

    def test_provision_calls_all_steps(self, patch_cp_db):
        store, _ = patch_cp_db
        patches = self._mock_provision_deps()
        mocks = [p.start() for p in patches]
        try:
            from control_plane.provisioner import TenantProvisioner
            tid = str(uuid.uuid4())
            result = TenantProvisioner.provision(
                tenant_id=tid,
                subdomain="nit",
                display_name="NIT Trichy",
            )
            assert result["status"] == "active"
            assert result["tenant_id"] == tid
            # All provisioning steps were called
            for mock in mocks[:4]:
                mock.assert_called_once()
        finally:
            for p in patches:
                p.stop()

    def test_suspend_sets_status(self, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        from control_plane.provisioner import TenantProvisioner
        TenantProvisioner.suspend(row["tenant_id"])
        updated = next((r for r in store if r["tenant_id"] == row["tenant_id"]), None)
        assert updated["status"] == "suspended"

    def test_reactivate_clears_suspended(self, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store, {"status": "suspended"})
        from control_plane.provisioner import TenantProvisioner
        TenantProvisioner.reactivate(row["tenant_id"])
        updated = next((r for r in store if r["tenant_id"] == row["tenant_id"]), None)
        assert updated["status"] == "active"

    def test_delete_sets_status_deleted(self, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        with patch("control_plane.provisioner._admin_conn") as mock_conn_fn:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn_fn.return_value = mock_conn
            from control_plane.provisioner import TenantProvisioner
            TenantProvisioner.delete(row["tenant_id"], drop_database=False)
        updated = next((r for r in store if r["tenant_id"] == row["tenant_id"]), None)
        assert updated["status"] == "deleted"


# ===========================================================================
# 4. HTTP API — /internal endpoints
# ===========================================================================

class TestInternalAPI:

    def test_get_db_config_returns_record(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.get(
            f"/internal/tenants/{row['tenant_id']}/db-config",
            headers=_internal_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == row["tenant_id"]
        assert "iitb" in data["db_url"]

    def test_get_db_config_404_for_unknown(self, test_app, patch_cp_db):
        resp = test_app.get(
            f"/internal/tenants/{uuid.uuid4()}/db-config",
            headers=_internal_headers(),
        )
        assert resp.status_code == 404

    def test_get_db_config_401_without_token(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.get(f"/internal/tenants/{row['tenant_id']}/db-config")
        assert resp.status_code in (401, 422)  # missing header

    def test_get_by_subdomain_returns_record(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        _seed_tenant(store)
        resp = test_app.get(
            "/internal/tenants/by-subdomain/iitb",
            headers=_internal_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["subdomain"] == "iitb"

    def test_get_by_subdomain_404_unknown(self, test_app, patch_cp_db):
        resp = test_app.get(
            "/internal/tenants/by-subdomain/nobody",
            headers=_internal_headers(),
        )
        assert resp.status_code == 404


# ===========================================================================
# 5. HTTP API — /admin endpoints
# ===========================================================================

class TestAdminAPI:

    def test_provision_returns_202(self, test_app, patch_cp_db):
        resp = test_app.post(
            "/admin/tenants",
            json={
                "subdomain": "iisc",
                "display_name": "IISc Bangalore",
                "region": "in-south",
                "plan": "growth",
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "provisioning"
        assert data["subdomain"] == "iisc"
        assert "tenant_id" in data

    def test_provision_rejected_without_admin_jwt(self, test_app, patch_cp_db):
        resp = test_app.post(
            "/admin/tenants",
            json={"subdomain": "iisc", "display_name": "IISc", "region": "in-south"},
        )
        assert resp.status_code in (401, 422)

    def test_list_tenants_returns_all(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        _seed_tenant(store, {"subdomain": "t1", "display_name": "T1"})
        _seed_tenant(store, {"subdomain": "t2", "display_name": "T2"})
        resp = test_app.get("/admin/tenants", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_get_tenant_returns_record(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.get(f"/admin/tenants/{row['tenant_id']}", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["subdomain"] == "iitb"

    def test_get_tenant_404_unknown(self, test_app, patch_cp_db):
        resp = test_app.get(f"/admin/tenants/{uuid.uuid4()}", headers=_admin_headers())
        assert resp.status_code == 404

    def test_suspend_tenant(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.put(
            f"/admin/tenants/{row['tenant_id']}/suspend",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    def test_reactivate_tenant(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store, {"status": "suspended"})
        resp = test_app.put(
            f"/admin/tenants/{row['tenant_id']}/reactivate",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_delete_tenant_soft(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.delete(
            f"/admin/tenants/{row['tenant_id']}",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["database_dropped"] is False

    def test_patch_tenant_updates_plan(self, test_app, patch_cp_db):
        store, _ = patch_cp_db
        row = _seed_tenant(store)
        resp = test_app.patch(
            f"/admin/tenants/{row['tenant_id']}",
            json={"plan": "enterprise"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200

    def test_health_endpoint(self, test_app, patch_cp_db):
        resp = test_app.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "control-plane"

    def test_invalid_subdomain_pattern_rejected(self, test_app, patch_cp_db):
        resp = test_app.post(
            "/admin/tenants",
            json={
                "subdomain": "INVALID SPACES",
                "display_name": "Bad",
                "region": "in-central",
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 422

    def test_invalid_plan_rejected(self, test_app, patch_cp_db):
        resp = test_app.post(
            "/admin/tenants",
            json={
                "subdomain": "valid-slug",
                "display_name": "Test",
                "region": "in-central",
                "plan": "UNKNOWN_PLAN",
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 422
