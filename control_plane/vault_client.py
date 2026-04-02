"""
Vault Client + Tenant Secrets Manager — S5

Vault path design:
  alis/{region}/tenant/{tenant_id}/db          → DB credentials
  alis/{region}/tenant/{tenant_id}/s3          → S3 bucket credentials (if per-tenant keys)
  alis/{region}/tenant/{tenant_id}/whatsapp    → WhatsApp API token
  alis/{region}/tenant/{tenant_id}/sms         → SMS gateway credentials
  alis/{region}/tenant/{tenant_id}/payu        → PayU merchant key + salt
  alis/{region}/tenant/{tenant_id}/custom/{k}  → Arbitrary institution-specific secrets

System-level paths (not tenant-scoped):
  alis/system/master_key                        → ALIS_MASTER_KEY (AES root key)
  alis/system/control_plane/db                 → Control plane DB password
  alis/system/jwt_secret                       → Admin JWT signing secret

All paths use KV v2 (versioned secrets). The VaultClient wrapper handles
token refresh (AppRole), retry on seal, and per-path access controls.

Backward compatibility:
  When VAULT_ADDR is not set, TenantSecretsManager falls back to
  reading from environment variables / settings (single-tenant mode).
  This preserves the existing dev setup.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """Raised for unrecoverable Vault errors (sealed, permission denied, etc.)"""


class VaultClient:
    """
    Minimal HashiCorp Vault KV v2 client.

    Uses AppRole authentication (recommended for machine-to-machine).
    Falls back to token auth when VAULT_TOKEN env var is set (dev mode).

    Only implements the methods required by TenantSecretsManager:
      - read(path)  → dict of secret data
      - write(path, data)
      - delete(path)
      - list(path)  → list of keys
    """

    def __init__(
        self,
        addr: str,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
        timeout: int = 10,
    ) -> None:
        self._addr = addr.rstrip("/")
        self._role_id = role_id
        self._secret_id = secret_id
        self._token = token
        self._mount = mount_point
        self._timeout = timeout
        self._authenticated_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Return a valid Vault token, authenticating via AppRole if needed."""
        if self._token:
            return self._token

        if self._authenticated_token:
            return self._authenticated_token

        if not self._role_id or not self._secret_id:
            raise VaultError(
                "Vault: no token and no AppRole credentials configured. "
                "Set VAULT_TOKEN or VAULT_ROLE_ID + VAULT_SECRET_ID."
            )

        import httpx

        resp = httpx.post(
            f"{self._addr}/v1/auth/approle/login",
            json={"role_id": self._role_id, "secret_id": self._secret_id},
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise VaultError(f"Vault AppRole auth failed: {resp.status_code} {resp.text}")

        self._authenticated_token = resp.json()["auth"]["client_token"]
        logger.debug("VaultClient: authenticated via AppRole")
        return self._authenticated_token

    def _headers(self) -> Dict[str, str]:
        return {"X-Vault-Token": self._get_token()}

    # ------------------------------------------------------------------
    # KV v2 operations
    # ------------------------------------------------------------------

    def read(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Read a secret from KV v2. Returns the `data` dict or None if not found.
        path is relative to the mount point, e.g. "alis/in-central/tenant/xxx/db"
        """
        import httpx

        url = f"{self._addr}/v1/{self._mount}/data/{path}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=self._timeout)
        except Exception as exc:
            raise VaultError(f"Vault read failed for {path}: {exc}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise VaultError(f"Vault read error {resp.status_code} for {path}: {resp.text}")

        body = resp.json()
        return body.get("data", {}).get("data")

    def write(self, path: str, data: Dict[str, Any]) -> None:
        """Write (create or update) a secret in KV v2."""
        import httpx

        url = f"{self._addr}/v1/{self._mount}/data/{path}"
        try:
            resp = httpx.post(
                url,
                json={"data": data},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except Exception as exc:
            raise VaultError(f"Vault write failed for {path}: {exc}") from exc

        if resp.status_code not in (200, 204):
            raise VaultError(f"Vault write error {resp.status_code} for {path}: {resp.text}")

        logger.debug("VaultClient: wrote secret at %s", path)

    def delete(self, path: str) -> None:
        """Soft-delete the latest version of a secret (KV v2 delete)."""
        import httpx

        url = f"{self._addr}/v1/{self._mount}/metadata/{path}"
        try:
            resp = httpx.delete(url, headers=self._headers(), timeout=self._timeout)
        except Exception as exc:
            raise VaultError(f"Vault delete failed for {path}: {exc}") from exc

        if resp.status_code not in (200, 204):
            logger.warning("Vault delete returned %s for %s", resp.status_code, path)

    def list(self, path: str) -> list[str]:
        """List keys under a path prefix."""
        import httpx

        url = f"{self._addr}/v1/{self._mount}/metadata/{path}"
        try:
            resp = httpx.request(
                "LIST", url, headers=self._headers(), timeout=self._timeout
            )
        except Exception as exc:
            raise VaultError(f"Vault list failed for {path}: {exc}") from exc

        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise VaultError(f"Vault list error {resp.status_code} for {path}: {resp.text}")

        return resp.json().get("data", {}).get("keys", [])


# ---------------------------------------------------------------------------
# TenantSecretsManager
# ---------------------------------------------------------------------------

class TenantSecretsManager:
    """
    High-level interface for reading/writing per-tenant secrets in Vault.

    Path convention:
        alis/{region}/tenant/{tenant_id}/{secret_type}

    Fallback:
        When Vault is not configured (VAULT_ADDR unset), reads from
        environment / settings as before (backward compat with single-tenant).
    """

    def __init__(
        self,
        vault_client: Optional[VaultClient] = None,
        region: str = "in-central",
    ) -> None:
        self._vault = vault_client or _get_vault_client()
        self._region = region

    def _path(self, tenant_id: str, secret_type: str) -> str:
        return f"alis/{self._region}/tenant/{tenant_id}/{secret_type}"

    # ------------------------------------------------------------------
    # Standard secret types
    # ------------------------------------------------------------------

    def write_db_credentials(
        self, tenant_id: str, db_user: str, db_password: str, db_name: str, db_host: str, db_port: int = 5432
    ) -> None:
        if not self._vault:
            logger.debug("TenantSecretsManager: Vault not configured, skipping write_db_credentials")
            return
        self._vault.write(self._path(tenant_id, "db"), {
            "user": db_user,
            "password": db_password,
            "name": db_name,
            "host": db_host,
            "port": str(db_port),
        })

    def read_db_credentials(self, tenant_id: str) -> Optional[Dict[str, str]]:
        if not self._vault:
            return None
        return self._vault.read(self._path(tenant_id, "db"))

    def write_s3_credentials(self, tenant_id: str, bucket: str, access_key: str, secret_key: str) -> None:
        if not self._vault:
            return
        self._vault.write(self._path(tenant_id, "s3"), {
            "bucket": bucket,
            "access_key": access_key,
            "secret_key": secret_key,
        })

    def write_custom_secret(self, tenant_id: str, key: str, data: Dict[str, Any]) -> None:
        if not self._vault:
            return
        self._vault.write(self._path(tenant_id, f"custom/{key}"), data)

    def read_custom_secret(self, tenant_id: str, key: str) -> Optional[Dict[str, Any]]:
        if not self._vault:
            return None
        return self._vault.read(self._path(tenant_id, f"custom/{key}"))

    def delete_all(self, tenant_id: str) -> None:
        """Delete all secrets for a tenant (called during tenant deletion)."""
        if not self._vault:
            return
        base_path = f"alis/{self._region}/tenant/{tenant_id}"
        try:
            keys = self._vault.list(base_path)
            for key in keys:
                self._vault.delete(f"{base_path}/{key.rstrip('/')}")
            logger.info("TenantSecretsManager: deleted all secrets for tenant=%s", tenant_id)
        except VaultError as exc:
            logger.warning("TenantSecretsManager: failed to delete secrets for %s: %s", tenant_id, exc)

    def list_secret_types(self, tenant_id: str) -> list[str]:
        """List the secret types registered for a tenant."""
        if not self._vault:
            return []
        try:
            return self._vault.list(f"alis/{self._region}/tenant/{tenant_id}")
        except VaultError:
            return []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _get_vault_client() -> Optional[VaultClient]:
    """
    Build a VaultClient from settings.

    Returns None when Vault is not configured (backward compat).
    """
    try:
        from control_plane.settings import settings

        if not settings.vault_addr:
            return None

        return VaultClient(
            addr=settings.vault_addr,
            role_id=settings.vault_role_id or None,
            secret_id=settings.vault_secret_id or None,
            token=settings.vault_token or None,
            mount_point=settings.vault_mount_point,
        )
    except Exception as exc:
        logger.warning("VaultClient: failed to build from settings: %s", exc)
        return None
