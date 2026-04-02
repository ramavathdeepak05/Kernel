"""
S5 Infrastructure Isolation — Unit Tests

Tests for:
- TenantTaskRouter  : per-tenant queue routing, system task pass-through, high-priority
- apply_tenant_task : delegates to celery_app.send_task with correct queue
- BucketProvisioner : create, public-block, versioning, encryption, destroy
- VaultClient       : read, write, delete, list; auth fallback
- TenantSecretsManager : path construction, write/read/delete helpers
"""
from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

# Add ALIS data plane to path so server.core.* imports resolve
_ALIS_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "../..", "ALIS"))
if _ALIS_PATH not in sys.path:
    sys.path.insert(0, _ALIS_PATH)


# ---------------------------------------------------------------------------
# TestTenantTaskRouter
# ---------------------------------------------------------------------------

class TestTenantTaskRouter:

    def _router(self):
        from server.core.tenant_tasks import TenantTaskRouter
        return TenantTaskRouter()

    def test_routes_to_tenant_default_queue(self):
        router = self._router()
        tid = str(uuid.uuid4())
        result = router.route_for_task(
            "server.tasks.ai_tasks.verify_document_async",
            kwargs={"tenant_id": tid},
        )
        assert result == {"queue": f"default:{tid}"}

    def test_routes_to_high_queue_for_notifications(self):
        router = self._router()
        tid = str(uuid.uuid4())
        result = router.route_for_task(
            "server.tasks.notifications.send_email",
            kwargs={"tenant_id": tid},
        )
        assert result == {"queue": f"high:{tid}"}

    def test_system_task_returns_none(self):
        router = self._router()
        # Calendar tasks are system-level — no tenant context
        result = router.route_for_task("server.tasks.calendar.trigger_all")
        assert result is None

    def test_no_tenant_id_returns_none(self):
        router = self._router()
        result = router.route_for_task("server.tasks.ai_tasks.some_task", kwargs={})
        assert result is None

    def test_org_id_kwarg_used_as_fallback(self):
        router = self._router()
        tid = str(uuid.uuid4())
        result = router.route_for_task(
            "server.tasks.ai_tasks.verify_document_async",
            kwargs={"org_id": tid},
        )
        assert result == {"queue": f"default:{tid}"}

    def test_shadow_divergence_always_system_queue(self):
        router = self._router()
        tid = str(uuid.uuid4())
        result = router.route_for_task(
            "server.tasks.shadow_divergence.run",
            kwargs={"tenant_id": tid},
        )
        assert result is None


# ---------------------------------------------------------------------------
# TestQueueNaming
# ---------------------------------------------------------------------------

class TestQueueNaming:

    def test_default_queue_name(self):
        from server.core.tenant_tasks import tenant_queue
        tid = "abc-123"
        assert tenant_queue(tid) == "default:abc-123"

    def test_high_queue_name(self):
        from server.core.tenant_tasks import tenant_queue
        tid = "abc-123"
        assert tenant_queue(tid, "high") == "high:abc-123"

    def test_parse_tenant_from_queue(self):
        from server.core.tenant_tasks import parse_tenant_from_queue
        assert parse_tenant_from_queue("default:tid-001") == "tid-001"
        assert parse_tenant_from_queue("high:tid-002") == "tid-002"
        assert parse_tenant_from_queue("dead_letter") is None
        assert parse_tenant_from_queue("default") is None

    def test_ensure_tenant_queues_returns_two_queues(self):
        from server.core.tenant_tasks import ensure_tenant_queues
        tid = str(uuid.uuid4())
        queues = ensure_tenant_queues(tid)
        assert len(queues) == 2
        assert f"default:{tid}" in queues
        assert f"high:{tid}" in queues


# ---------------------------------------------------------------------------
# TestApplyTenantTask
# ---------------------------------------------------------------------------

class TestApplyTenantTask:

    def test_dispatches_to_correct_queue(self):
        from server.core.tenant_tasks import apply_tenant_task

        mock_result = MagicMock()
        tid = str(uuid.uuid4())

        with patch("server.worker.celery_app") as mock_app:
            mock_app.send_task.return_value = mock_result
            result = apply_tenant_task(
                "server.tasks.ai_tasks.verify_document_async",
                tenant_id=tid,
                args=[tid, "app-001", "doc-001"],
            )

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs[1]["queue"] == f"default:{tid}"

    def test_high_priority_uses_high_queue(self):
        from server.core.tenant_tasks import apply_tenant_task

        tid = str(uuid.uuid4())

        with patch("server.worker.celery_app") as mock_app:
            mock_app.send_task.return_value = MagicMock()
            apply_tenant_task(
                "server.tasks.notifications.send_sms",
                tenant_id=tid,
                priority="high",
            )

        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs[1]["queue"] == f"high:{tid}"

    def test_tenant_id_injected_into_kwargs(self):
        from server.core.tenant_tasks import apply_tenant_task

        tid = str(uuid.uuid4())

        with patch("server.worker.celery_app") as mock_app:
            mock_app.send_task.return_value = MagicMock()
            apply_tenant_task(
                "server.tasks.ai_tasks.something",
                tenant_id=tid,
                kwargs={"foo": "bar"},
            )

        sent_kwargs = mock_app.send_task.call_args[1]["kwargs"]
        assert sent_kwargs["tenant_id"] == tid
        assert sent_kwargs["foo"] == "bar"


# ---------------------------------------------------------------------------
# TestBucketProvisioner
# ---------------------------------------------------------------------------

class TestBucketProvisioner:
    """Uses a mock boto3 S3 client — no real MinIO needed."""

    def _make_provisioner(self, mock_s3):
        from control_plane.bucket_provisioner import BucketProvisioner

        provisioner = BucketProvisioner(
            endpoint_url="http://localhost:9000",
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        provisioner._client = lambda: mock_s3
        return provisioner

    def _mock_s3(self):
        m = MagicMock()
        # simulate BucketAlreadyOwnedByYou as an attribute exception class
        m.exceptions.BucketAlreadyOwnedByYou = type("BucketAlreadyOwnedByYou", (Exception,), {})
        m.exceptions.BucketAlreadyExists = type("BucketAlreadyExists", (Exception,), {})
        return m

    def test_provision_creates_bucket(self):
        s3 = self._mock_s3()
        p = self._make_provisioner(s3)
        name = p.provision("tenant-abc")
        assert name == "alis-tenant-tenant-abc"
        s3.create_bucket.assert_called_once_with(Bucket="alis-tenant-tenant-abc")

    def test_provision_blocks_public_access(self):
        s3 = self._mock_s3()
        p = self._make_provisioner(s3)
        p.provision("t1")
        s3.put_public_access_block.assert_called_once()
        config = s3.put_public_access_block.call_args[1]["PublicAccessBlockConfiguration"]
        assert config["BlockPublicAcls"] is True
        assert config["BlockPublicPolicy"] is True

    def test_provision_enables_versioning(self):
        s3 = self._mock_s3()
        p = self._make_provisioner(s3)
        p.provision("t2")
        s3.put_bucket_versioning.assert_called_once()
        cfg = s3.put_bucket_versioning.call_args[1]["VersioningConfiguration"]
        assert cfg["Status"] == "Enabled"

    def test_provision_enables_encryption(self):
        s3 = self._mock_s3()
        p = self._make_provisioner(s3)
        p.provision("t3")
        s3.put_bucket_encryption.assert_called_once()
        rules = s3.put_bucket_encryption.call_args[1]["ServerSideEncryptionConfiguration"]["Rules"]
        assert rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"

    def test_provision_idempotent_when_bucket_exists(self):
        s3 = self._mock_s3()
        # Simulate "already owned by you" on create
        s3.create_bucket.side_effect = s3.exceptions.BucketAlreadyOwnedByYou()
        p = self._make_provisioner(s3)
        name = p.provision("t-exists")
        # Should not raise; still calls put_public_access_block etc.
        assert name == "alis-tenant-t-exists"
        s3.put_public_access_block.assert_called_once()

    def test_bucket_name_convention(self):
        from control_plane.bucket_provisioner import BucketProvisioner
        bp = BucketProvisioner.__new__(BucketProvisioner)
        assert bp.bucket_name("3fa85f64-5717") == "alis-tenant-3fa85f64-5717"

    def test_destroy_returns_false_when_bucket_missing(self):
        s3 = self._mock_s3()
        # head_bucket raises → bucket does not exist
        s3.head_bucket.side_effect = Exception("NoSuchBucket")
        p = self._make_provisioner(s3)
        result = p.destroy("t-gone", archive_first=False)
        assert result is False


# ---------------------------------------------------------------------------
# TestVaultClient
# ---------------------------------------------------------------------------

class TestVaultClient:

    def _client(self, token="dev-token"):
        from control_plane.vault_client import VaultClient
        return VaultClient(addr="http://vault:8200", token=token)

    def test_read_returns_secret_data(self):
        client = self._client()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"data": {"user": "alis_t1", "password": "s3cr3t"}}
        }

        with patch("httpx.get", return_value=mock_resp) as mock_get:
            result = client.read("alis/in-central/tenant/t1/db")

        assert result == {"user": "alis_t1", "password": "s3cr3t"}

    def test_read_returns_none_on_404(self):
        client = self._client()

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.get", return_value=mock_resp):
            result = client.read("alis/in-central/tenant/missing/db")

        assert result is None

    def test_write_sends_post(self):
        client = self._client()

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            client.write("alis/in-central/tenant/t1/db", {"user": "u", "password": "p"})

        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "t1/db" in url
        assert mock_post.call_args[1]["json"] == {"data": {"user": "u", "password": "p"}}

    def test_list_returns_keys(self):
        client = self._client()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"keys": ["db", "s3", "custom/"]}}

        with patch("httpx.request", return_value=mock_resp):
            result = client.list("alis/in-central/tenant/t1")

        assert "db" in result
        assert "s3" in result

    def test_list_returns_empty_on_404(self):
        client = self._client()

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.request", return_value=mock_resp):
            result = client.list("alis/in-central/tenant/missing")

        assert result == []

    def test_approle_auth_called_when_no_token(self):
        from control_plane.vault_client import VaultClient

        client = VaultClient(
            addr="http://vault:8200",
            role_id="role-001",
            secret_id="secret-001",
        )

        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 200
        mock_auth_resp.json.return_value = {"auth": {"client_token": "tok-123"}}

        mock_read_resp = MagicMock()
        mock_read_resp.status_code = 200
        mock_read_resp.json.return_value = {"data": {"data": {"key": "val"}}}

        with patch("httpx.post", return_value=mock_auth_resp):
            with patch("httpx.get", return_value=mock_read_resp):
                result = client.read("some/path")

        assert result == {"key": "val"}
        assert client._authenticated_token == "tok-123"


# ---------------------------------------------------------------------------
# TestTenantSecretsManager
# ---------------------------------------------------------------------------

class TestTenantSecretsManager:

    def _manager(self, mock_vault=None):
        from control_plane.vault_client import TenantSecretsManager, VaultClient

        if mock_vault is None:
            mock_vault = MagicMock(spec=VaultClient)
        return TenantSecretsManager(vault_client=mock_vault, region="in-central")

    def test_path_construction(self):
        mgr = self._manager()
        # Access internal path method
        assert mgr._path("t1", "db") == "alis/in-central/tenant/t1/db"

    def test_write_db_credentials_calls_vault_write(self):
        mock_vault = MagicMock()
        mgr = self._manager(mock_vault)
        mgr.write_db_credentials(
            tenant_id="t1",
            db_user="alis_t1",
            db_password="pw",
            db_name="alis_t1",
            db_host="localhost",
            db_port=5432,
        )
        mock_vault.write.assert_called_once()
        path = mock_vault.write.call_args[0][0]
        assert path == "alis/in-central/tenant/t1/db"
        data = mock_vault.write.call_args[0][1]
        assert data["user"] == "alis_t1"
        assert data["password"] == "pw"

    def test_read_db_credentials_calls_vault_read(self):
        mock_vault = MagicMock()
        mock_vault.read.return_value = {"user": "u", "password": "p"}
        mgr = self._manager(mock_vault)
        result = mgr.read_db_credentials("t1")
        mock_vault.read.assert_called_once_with("alis/in-central/tenant/t1/db")
        assert result["user"] == "u"

    def test_no_vault_configured_write_is_noop(self):
        from control_plane.vault_client import TenantSecretsManager
        # Patch _get_vault_client to return None (simulates Vault not configured)
        with patch("control_plane.vault_client._get_vault_client", return_value=None):
            mgr = TenantSecretsManager(vault_client=None, region="in-central")
        # Should not raise when vault is None
        mgr.write_db_credentials("t1", "u", "p", "db", "localhost")

    def test_delete_all_calls_list_and_delete(self):
        mock_vault = MagicMock()
        mock_vault.list.return_value = ["db", "s3"]
        mgr = self._manager(mock_vault)
        mgr.delete_all("t1")
        mock_vault.list.assert_called_once()
        assert mock_vault.delete.call_count == 2

    def test_write_custom_secret(self):
        mock_vault = MagicMock()
        mgr = self._manager(mock_vault)
        mgr.write_custom_secret("t1", "payu", {"key": "k", "salt": "s"})
        path = mock_vault.write.call_args[0][0]
        assert "custom/payu" in path
