"""
S10 DNS Routing — Unit Tests

Tests for:
- DNSRecord         : data structure
- CloudflareDNS     : create, delete, get, idempotent handling
- Route53DNS        : create (UPSERT), delete, get
- TenantDNSManager  : provision/deprovision orchestration, provider fallback
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from control_plane.dns_manager import (
    AzureDNS,
    BaseDNSProvider,
    CloudflareDNS,
    DNSRecord,
    Route53DNS,
    TenantDNSManager,
)


# ---------------------------------------------------------------------------
# TestDNSRecord
# ---------------------------------------------------------------------------

class TestDNSRecord:

    def test_create_record(self):
        r = DNSRecord(name="iitb.alis.app", record_type="CNAME", value="lb.alis.app")
        assert r.name == "iitb.alis.app"
        assert r.record_type == "CNAME"
        assert r.value == "lb.alis.app"
        assert r.ttl == 300
        assert r.proxied is True

    def test_non_proxied_record(self):
        r = DNSRecord(name="test.alis.app", record_type="A", value="1.2.3.4", proxied=False)
        assert r.proxied is False


# ---------------------------------------------------------------------------
# TestCloudflareDNS
# ---------------------------------------------------------------------------

class TestCloudflareDNS:

    def _provider(self):
        return CloudflareDNS(api_token="cf-token", zone_id="zone-123")

    def test_create_record_success(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "result": {"id": "rec-abc"},
        }
        with patch("httpx.post", return_value=mock_resp):
            record_id = prov.create_record(
                DNSRecord("iitb.alis.app", "CNAME", "lb.alis.app")
            )
        assert record_id == "rec-abc"

    def test_create_record_already_exists_returns_existing_id(self):
        prov = self._provider()

        create_resp = MagicMock()
        create_resp.json.return_value = {
            "success": False,
            "errors": [{"message": "Record already exists"}],
        }

        get_resp = MagicMock()
        get_resp.json.return_value = {
            "result": [{"id": "existing-rec"}],
        }

        with patch("httpx.post", return_value=create_resp), \
             patch("httpx.get", return_value=get_resp):
            record_id = prov.create_record(
                DNSRecord("iitb.alis.app", "CNAME", "lb.alis.app")
            )
        assert record_id == "existing-rec"

    def test_delete_record_success(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True}

        with patch("httpx.delete", return_value=mock_resp):
            result = prov.delete_record("rec-abc")
        assert result is True

    def test_delete_record_failure_returns_false(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": False, "errors": ["not found"]}

        with patch("httpx.delete", return_value=mock_resp):
            result = prov.delete_record("rec-missing")
        assert result is False

    def test_get_record_found(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": [{"id": "rec-found"}],
        }
        with patch("httpx.get", return_value=mock_resp):
            rid = prov.get_record("iitb.alis.app")
        assert rid == "rec-found"

    def test_get_record_not_found(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": []}
        with patch("httpx.get", return_value=mock_resp):
            rid = prov.get_record("missing.alis.app")
        assert rid is None

    def test_create_sends_proxied_true(self):
        prov = self._provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "result": {"id": "r"}}

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            prov.create_record(DNSRecord("x.alis.app", "CNAME", "lb.alis.app", proxied=True))

        payload = mock_post.call_args[1]["json"]
        assert payload["proxied"] is True
        assert payload["ttl"] == 1  # auto for proxied


# ---------------------------------------------------------------------------
# TestRoute53DNS
# ---------------------------------------------------------------------------

class TestRoute53DNS:

    def test_create_record_upsert(self):
        prov = Route53DNS(hosted_zone_id="Z123")
        mock_client = MagicMock()

        with patch.object(prov, "_client", return_value=mock_client):
            rid = prov.create_record(DNSRecord("test.alis.app", "CNAME", "lb.alis.app"))

        mock_client.change_resource_record_sets.assert_called_once()
        batch = mock_client.change_resource_record_sets.call_args[1]["ChangeBatch"]
        assert batch["Changes"][0]["Action"] == "UPSERT"
        assert rid == "test.alis.app:CNAME"

    def test_get_record_found(self):
        prov = Route53DNS(hosted_zone_id="Z123")
        mock_client = MagicMock()
        mock_client.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {"Name": "test.alis.app.", "Type": "CNAME", "TTL": 300, "ResourceRecords": [{"Value": "lb"}]}
            ]
        }

        with patch.object(prov, "_client", return_value=mock_client):
            rid = prov.get_record("test.alis.app")
        assert rid == "test.alis.app:CNAME"

    def test_get_record_not_found(self):
        prov = Route53DNS(hosted_zone_id="Z123")
        mock_client = MagicMock()
        mock_client.list_resource_record_sets.return_value = {
            "ResourceRecordSets": []
        }
        with patch.object(prov, "_client", return_value=mock_client):
            rid = prov.get_record("missing.alis.app")
        assert rid is None


# ---------------------------------------------------------------------------
# TestTenantDNSManager
# ---------------------------------------------------------------------------

class TestTenantDNSManager:

    def test_provision_dns_creates_cname(self):
        mock_prov = MagicMock(spec=BaseDNSProvider)
        mock_prov.create_record.return_value = "rec-new"

        mgr = TenantDNSManager(provider=mock_prov)
        rid = mgr.provision_dns("iitb", "lb.alis.app")

        assert rid == "rec-new"
        mock_prov.create_record.assert_called_once()
        record = mock_prov.create_record.call_args[0][0]
        assert record.name == "iitb.alis.app"
        assert record.record_type == "CNAME"
        assert record.value == "lb.alis.app"

    def test_provision_dns_returns_none_when_no_provider(self):
        mgr = TenantDNSManager(provider=None)
        rid = mgr.provision_dns("iitb", "lb.alis.app")
        assert rid is None

    def test_deprovision_dns_deletes_record(self):
        mock_prov = MagicMock(spec=BaseDNSProvider)
        mock_prov.get_record.return_value = "rec-existing"
        mock_prov.delete_record.return_value = True

        mgr = TenantDNSManager(provider=mock_prov)
        result = mgr.deprovision_dns("iitb")

        assert result is True
        mock_prov.delete_record.assert_called_once_with("rec-existing")

    def test_deprovision_dns_noop_when_no_record(self):
        mock_prov = MagicMock(spec=BaseDNSProvider)
        mock_prov.get_record.return_value = None

        mgr = TenantDNSManager(provider=mock_prov)
        result = mgr.deprovision_dns("gone")

        assert result is True
        mock_prov.delete_record.assert_not_called()

    def test_deprovision_dns_returns_true_when_no_provider(self):
        mgr = TenantDNSManager(provider=None)
        assert mgr.deprovision_dns("iitb") is True

    def test_provision_handles_provider_error(self):
        mock_prov = MagicMock(spec=BaseDNSProvider)
        mock_prov.create_record.side_effect = RuntimeError("API down")

        mgr = TenantDNSManager(provider=mock_prov)
        rid = mgr.provision_dns("iitb", "lb.alis.app")

        assert rid is None  # graceful failure

    def test_cloudflare_provider_uses_proxied_true(self):
        cf = CloudflareDNS(api_token="tok", zone_id="z")
        mgr = TenantDNSManager(provider=cf)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "result": {"id": "r"}}

        with patch("httpx.post", return_value=mock_resp):
            mgr.provision_dns("iitb", "lb.alis.app")
