"""
DNS Manager — S10

Automates wildcard DNS record management for tenant subdomains.

Supported providers:
  - Cloudflare (primary — handles CDN + DNS + SSL in one)
  - AWS Route53 (for AWS-hosted regions)
  - Azure DNS (for Azure-hosted regions)

Each tenant gets a CNAME record:
    {subdomain}.alis.app → data-plane-lb.alis.app

The wildcard cert (*.alis.app) is managed by cert-manager in k8s
or by Cloudflare's Universal SSL. Individual tenant records are
created for analytics/audit tracking, even though the wildcard
would match without them.

Auto-provisioning:
  - On tenant create: create CNAME record
  - On tenant suspend: add TXT record "alis-suspended=true" (optional, for WAF rules)
  - On tenant delete: remove CNAME record
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DNSRecord:
    """Represents a DNS record to be created/updated/deleted."""

    def __init__(
        self,
        name: str,          # e.g. "iitb.alis.app"
        record_type: str,   # CNAME | A | TXT
        value: str,          # e.g. "data-plane.alis.app"
        ttl: int = 300,
        proxied: bool = True,  # Cloudflare-specific: proxy through CDN
    ):
        self.name = name
        self.record_type = record_type
        self.value = value
        self.ttl = ttl
        self.proxied = proxied


class BaseDNSProvider:
    """Interface for DNS providers."""

    def create_record(self, record: DNSRecord) -> str:
        """Create a DNS record. Returns the record ID."""
        raise NotImplementedError

    def delete_record(self, record_id: str) -> bool:
        """Delete a DNS record by ID. Returns True on success."""
        raise NotImplementedError

    def get_record(self, name: str, record_type: str = "CNAME") -> Optional[str]:
        """Get a record ID by name. Returns None if not found."""
        raise NotImplementedError

    def update_record(self, record_id: str, record: DNSRecord) -> bool:
        """Update an existing record. Returns True on success."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------

class CloudflareDNS(BaseDNSProvider):
    """
    Cloudflare DNS API.

    Requires:
      - CLOUDFLARE_API_TOKEN (scoped to Zone:DNS:Edit)
      - CLOUDFLARE_ZONE_ID (zone ID for alis.app)
    """

    API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, api_token: str, zone_id: str) -> None:
        self._token = api_token
        self._zone_id = zone_id

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def create_record(self, record: DNSRecord) -> str:
        import httpx

        resp = httpx.post(
            f"{self.API_BASE}/zones/{self._zone_id}/dns_records",
            json={
                "type": record.record_type,
                "name": record.name,
                "content": record.value,
                "ttl": 1 if record.proxied else record.ttl,  # 1 = auto for proxied
                "proxied": record.proxied,
            },
            headers=self._headers(),
            timeout=15,
        )
        data = resp.json()
        if not data.get("success"):
            errors = data.get("errors", [])
            # Idempotent: if record already exists, fetch its ID
            if any("already exists" in str(e).lower() for e in errors):
                existing = self.get_record(record.name, record.record_type)
                if existing:
                    return existing
            raise RuntimeError(f"Cloudflare DNS create failed: {errors}")

        record_id = data["result"]["id"]
        logger.info("CloudflareDNS: created %s → %s (id=%s)", record.name, record.value, record_id)
        return record_id

    def delete_record(self, record_id: str) -> bool:
        import httpx

        resp = httpx.delete(
            f"{self.API_BASE}/zones/{self._zone_id}/dns_records/{record_id}",
            headers=self._headers(),
            timeout=15,
        )
        data = resp.json()
        if data.get("success"):
            logger.info("CloudflareDNS: deleted record %s", record_id)
            return True
        logger.warning("CloudflareDNS: delete failed for %s: %s", record_id, data.get("errors"))
        return False

    def get_record(self, name: str, record_type: str = "CNAME") -> Optional[str]:
        import httpx

        resp = httpx.get(
            f"{self.API_BASE}/zones/{self._zone_id}/dns_records",
            params={"name": name, "type": record_type},
            headers=self._headers(),
            timeout=15,
        )
        data = resp.json()
        results = data.get("result", [])
        return results[0]["id"] if results else None

    def update_record(self, record_id: str, record: DNSRecord) -> bool:
        import httpx

        resp = httpx.put(
            f"{self.API_BASE}/zones/{self._zone_id}/dns_records/{record_id}",
            json={
                "type": record.record_type,
                "name": record.name,
                "content": record.value,
                "ttl": 1 if record.proxied else record.ttl,
                "proxied": record.proxied,
            },
            headers=self._headers(),
            timeout=15,
        )
        return resp.json().get("success", False)


# ---------------------------------------------------------------------------
# AWS Route53
# ---------------------------------------------------------------------------

class Route53DNS(BaseDNSProvider):
    """AWS Route53 DNS. Requires hosted_zone_id and boto3 credentials."""

    def __init__(self, hosted_zone_id: str) -> None:
        self._zone_id = hosted_zone_id

    def _client(self):
        import boto3
        return boto3.client("route53")

    def create_record(self, record: DNSRecord) -> str:
        client = self._client()
        client.change_resource_record_sets(
            HostedZoneId=self._zone_id,
            ChangeBatch={
                "Changes": [{
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": record.name,
                        "Type": record.record_type,
                        "TTL": record.ttl,
                        "ResourceRecords": [{"Value": record.value}],
                    },
                }]
            },
        )
        logger.info("Route53DNS: upserted %s → %s", record.name, record.value)
        return f"{record.name}:{record.record_type}"

    def delete_record(self, record_id: str) -> bool:
        # record_id is "name:type" from create_record
        name, rtype = record_id.rsplit(":", 1)
        client = self._client()
        try:
            # Need to fetch current value first
            response = client.list_resource_record_sets(
                HostedZoneId=self._zone_id,
                StartRecordName=name,
                StartRecordType=rtype,
                MaxItems="1",
            )
            for rrs in response.get("ResourceRecordSets", []):
                if rrs["Name"].rstrip(".") == name.rstrip(".") and rrs["Type"] == rtype:
                    client.change_resource_record_sets(
                        HostedZoneId=self._zone_id,
                        ChangeBatch={
                            "Changes": [{
                                "Action": "DELETE",
                                "ResourceRecordSet": rrs,
                            }]
                        },
                    )
                    logger.info("Route53DNS: deleted %s", name)
                    return True
        except Exception as exc:
            logger.warning("Route53DNS: delete failed for %s: %s", record_id, exc)
        return False

    def get_record(self, name: str, record_type: str = "CNAME") -> Optional[str]:
        client = self._client()
        response = client.list_resource_record_sets(
            HostedZoneId=self._zone_id,
            StartRecordName=name,
            StartRecordType=record_type,
            MaxItems="1",
        )
        for rrs in response.get("ResourceRecordSets", []):
            if rrs["Name"].rstrip(".") == name.rstrip("."):
                return f"{name}:{record_type}"
        return None

    def update_record(self, record_id: str, record: DNSRecord) -> bool:
        self.create_record(record)  # UPSERT semantics
        return True


# ---------------------------------------------------------------------------
# Azure DNS
# ---------------------------------------------------------------------------

class AzureDNS(BaseDNSProvider):
    """Azure DNS Zone management."""

    def __init__(self, resource_group: str, zone_name: str) -> None:
        self._rg = resource_group
        self._zone = zone_name

    def _client(self):
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.dns import DnsManagementClient
        credential = DefaultAzureCredential()
        # subscription_id from env or settings
        import os
        sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
        return DnsManagementClient(credential, sub_id)

    def create_record(self, record: DNSRecord) -> str:
        client = self._client()
        relative_name = record.name.replace(f".{self._zone}", "")
        client.record_sets.create_or_update(
            self._rg, self._zone, relative_name,
            record.record_type,
            {
                "ttl": record.ttl,
                "cname_record": {"cname": record.value} if record.record_type == "CNAME" else None,
                "arecords": [{"ipv4_address": record.value}] if record.record_type == "A" else None,
            },
        )
        logger.info("AzureDNS: upserted %s → %s", record.name, record.value)
        return f"{relative_name}:{record.record_type}"

    def delete_record(self, record_id: str) -> bool:
        name, rtype = record_id.rsplit(":", 1)
        try:
            client = self._client()
            client.record_sets.delete(self._rg, self._zone, name, rtype)
            return True
        except Exception as exc:
            logger.warning("AzureDNS: delete failed: %s", exc)
            return False

    def get_record(self, name: str, record_type: str = "CNAME") -> Optional[str]:
        relative_name = name.replace(f".{self._zone}", "")
        try:
            client = self._client()
            client.record_sets.get(self._rg, self._zone, relative_name, record_type)
            return f"{relative_name}:{record_type}"
        except Exception:
            return None

    def update_record(self, record_id: str, record: DNSRecord) -> bool:
        self.create_record(record)
        return True


# ---------------------------------------------------------------------------
# TenantDNSManager — orchestrates DNS for tenant lifecycle
# ---------------------------------------------------------------------------

class TenantDNSManager:
    """
    High-level DNS orchestrator called during tenant provisioning.

    Selects the provider based on settings and manages the tenant's
    CNAME record lifecycle.
    """

    def __init__(self, provider: Optional[BaseDNSProvider] = None):
        self._provider = provider or _get_dns_provider()

    def provision_dns(self, subdomain: str, target: str, domain: str = "alis.app") -> Optional[str]:
        """
        Create CNAME record for {subdomain}.{domain} → {target}.

        Returns the DNS record ID or None if DNS is not configured.
        """
        if not self._provider:
            logger.debug("TenantDNSManager: no DNS provider configured, skipping")
            return None

        record = DNSRecord(
            name=f"{subdomain}.{domain}",
            record_type="CNAME",
            value=target,
            ttl=300,
            proxied=isinstance(self._provider, CloudflareDNS),
        )

        try:
            record_id = self._provider.create_record(record)
            logger.info("TenantDNSManager: DNS provisioned for %s.%s", subdomain, domain)
            return record_id
        except Exception as exc:
            logger.error("TenantDNSManager: DNS provisioning failed for %s: %s", subdomain, exc)
            return None

    def deprovision_dns(self, subdomain: str, domain: str = "alis.app") -> bool:
        """Remove the CNAME record for a tenant."""
        if not self._provider:
            return True

        try:
            record_id = self._provider.get_record(f"{subdomain}.{domain}", "CNAME")
            if record_id:
                return self._provider.delete_record(record_id)
            return True  # nothing to delete
        except Exception as exc:
            logger.error("TenantDNSManager: DNS deprovisioning failed for %s: %s", subdomain, exc)
            return False


def _get_dns_provider() -> Optional[BaseDNSProvider]:
    """Build DNS provider from control plane settings."""
    try:
        from control_plane.settings import settings

        cf_token = getattr(settings, "cloudflare_api_token", "")
        cf_zone = getattr(settings, "cloudflare_zone_id", "")
        if cf_token and cf_zone:
            return CloudflareDNS(api_token=cf_token, zone_id=cf_zone)

        r53_zone = getattr(settings, "route53_hosted_zone_id", "")
        if r53_zone:
            return Route53DNS(hosted_zone_id=r53_zone)

        az_rg = getattr(settings, "azure_dns_resource_group", "")
        az_zone = getattr(settings, "azure_dns_zone_name", "")
        if az_rg and az_zone:
            return AzureDNS(resource_group=az_rg, zone_name=az_zone)

    except Exception as exc:
        logger.debug("DNS provider init failed: %s", exc)

    return None
