"""
HashiCorp Vault Client — P0-2

MODULE: Platform Core (Security)
LAYER: Infrastructure (below Layer 1)
ENTITY: Secrets Management

Provides:
  - AES-256 encryption / decryption via Vault Transit engine
    (exam paper content — CoE-only decrypt)
  - KV v2 secret store access (API keys, service passwords)
  - Audit log every encrypt/decrypt operation via AuditLedger

Usage:
    vault = VaultClient()

    # Encrypt an exam paper (CoE produces it, no one else can read the plaintext)
    ciphertext = vault.encrypt_exam_paper(tenant_id, paper_id, plaintext_bytes)

    # Decrypt — CoE role only (RBAC checked at caller, Vault policy at transit engine)
    plaintext = vault.decrypt_exam_paper(tenant_id, paper_id, ciphertext)

    # KV read
    secret = vault.get_secret("alis/payment_gateway_key")

Hard Constraints:
- All operations logged to audit_ledger (immutable, append-only)
- Transit key per tenant — no cross-tenant key reuse
- Root token only used for initial setup; service token rotated daily via AppRole
"""
from __future__ import annotations

import base64
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


class VaultClient:
    """
    Thin wrapper around the HashiCorp Vault HTTP API.

    Uses the `hvac` Python library if available; falls back to
    raw urllib.request so the service can start without hvac installed.
    """

    def __init__(
        self,
        addr: Optional[str] = None,
        token: Optional[str] = None,
        transit_mount: str = "transit",
        kv_mount: str = "secret",
    ):
        from server.core.settings import settings
        self._addr = addr or settings.vault_addr
        self._token = token or settings.vault_token
        self._transit_mount = transit_mount
        self._kv_mount = kv_mount
        self._client = self._build_client()

    def _build_client(self):
        try:
            import hvac
            client = hvac.Client(url=self._addr, token=self._token)
            if not client.is_authenticated():
                raise RuntimeError("Vault token invalid or expired.")
            logger.info("Vault hvac client authenticated at %s", self._addr)
            return client
        except ImportError:
            logger.warning(
                "hvac not installed — Vault calls will use urllib fallback. "
                "Install with: pip install hvac"
            )
            return None

    # -------------------------------------------------------------------------
    # Transit: exam paper encryption (AES-256-GCM)
    # -------------------------------------------------------------------------

    def _transit_key_name(self, tenant_id: str) -> str:
        """Deterministic per-tenant transit key name."""
        return f"alis-exam-{tenant_id}"

    def ensure_transit_key(self, tenant_id: str) -> None:
        """
        Create the per-tenant transit key if it doesn't exist.
        Idempotent — safe to call on every tenant onboard.
        """
        key_name = self._transit_key_name(tenant_id)
        if self._client:
            try:
                self._client.secrets.transit.create_key(
                    name=key_name,
                    key_type="aes256-gcm96",
                    mount_point=self._transit_mount,
                )
                logger.info("Vault transit key '%s' ensured.", key_name)
            except Exception as e:
                # Key may already exist — Vault returns 400 for duplicate create
                if "already exists" not in str(e).lower():
                    logger.error("Failed to create transit key '%s': %s", key_name, e)
        else:
            self._urllib_request(
                "POST",
                f"/v1/{self._transit_mount}/keys/{key_name}",
                {"type": "aes256-gcm96"},
            )

    def encrypt_exam_paper(
        self, tenant_id: str, paper_id: str, plaintext: bytes
    ) -> str:
        """
        Encrypt exam paper content using the per-tenant transit key.

        Returns the Vault ciphertext string (vault:v1:...).
        Logs the operation to audit_ledger.

        Args:
            tenant_id: Tenant scoping the key.
            paper_id: Exam paper UUID — logged for traceability.
            plaintext: Raw bytes to encrypt.

        Returns:
            Vault ciphertext string.
        """
        self.ensure_transit_key(tenant_id)
        b64 = base64.b64encode(plaintext).decode()
        key_name = self._transit_key_name(tenant_id)

        if self._client:
            resp = self._client.secrets.transit.encrypt_data(
                name=key_name,
                plaintext=b64,
                mount_point=self._transit_mount,
            )
            ciphertext: str = resp["data"]["ciphertext"]
        else:
            resp = self._urllib_request(
                "POST",
                f"/v1/{self._transit_mount}/encrypt/{key_name}",
                {"plaintext": b64},
            )
            ciphertext = resp["data"]["ciphertext"]

        self._audit("EXAM_PAPER_ENCRYPTED", tenant_id, paper_id)
        return ciphertext

    def decrypt_exam_paper(
        self, tenant_id: str, paper_id: str, ciphertext: str
    ) -> bytes:
        """
        Decrypt exam paper — CALLER must enforce CoE-only RBAC check.

        Args:
            tenant_id: Must match the tenant that encrypted.
            paper_id: Logged for audit trail.
            ciphertext: Vault ciphertext string (vault:v1:...).

        Returns:
            Original plaintext bytes.
        """
        key_name = self._transit_key_name(tenant_id)

        if self._client:
            resp = self._client.secrets.transit.decrypt_data(
                name=key_name,
                ciphertext=ciphertext,
                mount_point=self._transit_mount,
            )
            plaintext_b64: str = resp["data"]["plaintext"]
        else:
            resp = self._urllib_request(
                "POST",
                f"/v1/{self._transit_mount}/decrypt/{key_name}",
                {"ciphertext": ciphertext},
            )
            plaintext_b64 = resp["data"]["plaintext"]

        self._audit("EXAM_PAPER_DECRYPTED", tenant_id, paper_id)
        return base64.b64decode(plaintext_b64)

    # -------------------------------------------------------------------------
    # KV v2: service secrets
    # -------------------------------------------------------------------------

    def get_secret(self, path: str) -> dict:
        """
        Read a KV v2 secret.

        Args:
            path: Secret path relative to KV mount (e.g. "alis/payment_key").

        Returns:
            Dict of secret key-value pairs.

        Raises:
            KeyError: If the secret path does not exist.
        """
        if self._client:
            resp = self._client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self._kv_mount
            )
            return resp["data"]["data"]
        else:
            resp = self._urllib_request("GET", f"/v1/{self._kv_mount}/data/{path}")
            return resp["data"]["data"]

    def put_secret(self, path: str, data: dict) -> None:
        """Write / update a KV v2 secret."""
        if self._client:
            self._client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=data, mount_point=self._kv_mount
            )
        else:
            self._urllib_request(
                "POST", f"/v1/{self._kv_mount}/data/{path}", {"data": data}
            )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _urllib_request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Fallback HTTP client when hvac is not installed."""
        import json
        import urllib.request

        url = self._addr.rstrip("/") + path
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-Vault-Token": self._token,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _audit(self, action: str, tenant_id: str, entity_id: str) -> None:
        """Append an audit ledger entry for every Vault encrypt/decrypt."""
        try:
            from server.core.audit import AuditService
            AuditService.log(
                tenant_id=tenant_id,
                actor_id="system:vault",
                actor_role="SYSTEM",
                action=action,
                entity_type="exam_paper",
                entity_id=entity_id,
                metadata={"vault_addr": self._addr},
            )
        except Exception as e:
            # Audit failure must never block the encrypt/decrypt operation
            logger.error("Vault audit log failed (action=%s, entity=%s): %s", action, entity_id, e)


@lru_cache(maxsize=1)
def get_vault_client() -> VaultClient:
    """Return the singleton VaultClient (cached after first call)."""
    return VaultClient()
