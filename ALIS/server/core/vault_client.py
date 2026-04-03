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
    vault = get_vault_client()

    # Encrypt an exam paper (CoE produces it, no one else can read the plaintext)
    ciphertext = vault.encrypt_exam_paper(tenant_id, paper_id, plaintext_bytes)

    # Decrypt — CoE role only (RBAC checked at caller, Vault policy at transit engine)
    plaintext = vault.decrypt_exam_paper(tenant_id, paper_id, ciphertext)

    # KV read (cached, with graceful degradation)
    secret = vault.get_secret("alis/payment_gateway_key")

Hard Constraints:
- All Transit operations logged to audit_ledger (immutable, append-only)
- Transit key per tenant — no cross-tenant key reuse
- Root token only used for initial setup; service token rotated daily via AppRole

Resilience Model (Vault Downtime):
- CRITICAL secrets (exam keys, MFA, tenant encryption keys): FAIL-CLOSED. No fallback.
- NON-CRITICAL secrets (webhooks, API keys): served from 5-min TTL cache.
  On cache miss + Vault down: fallback to env var, then fail-closed.
"""
from __future__ import annotations

import base64
import logging
import os
import threading
import time
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Degradation Tiers — defines behavior when Vault is unreachable
# ---------------------------------------------------------------------------

# CRITICAL: Vault down = fail-closed. Zero fallback allowed.
_CRITICAL_SECRET_PREFIXES = (
    "alis/exam",       # Exam paper keys — CoE-only
    "alis/mfa",        # MFA secrets — never fallback
    "alis/tenant_key", # Per-tenant data-at-rest keys
)

# NON-CRITICAL: can fall back to env var if Vault is unreachable.
_NON_CRITICAL_FALLBACK_ENV: dict[str, str] = {
    "alis/razorpay_webhook": "RAZORPAY_WEBHOOK_SECRET",
    "alis/msg91_key":        "MSG91_API_KEY",
    "alis/smtp_password":    "SMTP_PASSWORD",
}


def _is_critical(path: str) -> bool:
    return any(path.startswith(p) for p in _CRITICAL_SECRET_PREFIXES)


# ---------------------------------------------------------------------------
# TTL-Based Secret Cache — prevents Vault from being a per-request bottleneck
# ---------------------------------------------------------------------------

class _SecretCache:
    """
    Thread-safe, TTL-based in-memory cache for non-sensitive KV secrets.

    SECURITY NOTE: NEVER cache critical secrets (exam Transit keys).
    Only cache non-rotating operational keys (webhooks, API keys).
    Structure: { path: (value, expires_at_monotonic) }
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._store: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, path: str) -> Optional[dict]:
        with self._lock:
            if path in self._store:
                value, expires_at = self._store[path]
                if time.monotonic() < expires_at:
                    return value
                del self._store[path]
        return None

    def set(self, path: str, value: dict) -> None:
        if _is_critical(path):
            return  # Never cache critical secrets
        with self._lock:
            self._store[path] = (value, time.monotonic() + self._ttl)

    def invalidate(self, path: str) -> None:
        with self._lock:
            self._store.pop(path, None)


# Module-level singleton — 5-min TTL for non-critical secrets
_secret_cache = _SecretCache(ttl_seconds=300)


class VaultUnavailableError(RuntimeError):
    """
    Raised when Vault is unreachable for a secret that has no valid fallback.

    For critical secrets (exam keys, MFA), map to HTTP 503.
    Alert on-call when this is raised in production.
    """


class VaultClient:
    """
    Thin wrapper around the HashiCorp Vault HTTP API.

    Uses the `hvac` Python library if installed; falls back to
    raw urllib.request to avoid hard dependency at startup.

    RESILIENCE:
    - Non-critical KV secrets are cached in-memory (5-min TTL).
      Vault downtime does not affect cached secrets within the TTL window.
    - Critical Transit keys (exam papers) are never cached.
      They fail-closed if Vault is unreachable.
    """

    def __init__(
        self,
        addr: Optional[str] = None,
        token: Optional[str] = None,
        transit_mount: str = "transit",
        kv_mount: str = "secret",
    ) -> None:
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
        except Exception as exc:
            logger.error(
                "Vault client failed to authenticate at %s: %s. Running in DEGRADED mode.",
                self._addr, exc,
            )
            return None

    def _is_available(self) -> bool:
        """Lightweight availability check — called before critical operations."""
        try:
            if self._client:
                return self._client.is_authenticated()
            import urllib.request
            req = urllib.request.Request(
                self._addr.rstrip("/") + "/v1/sys/health",
                headers={"X-Vault-Token": self._token},
            )
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Transit: exam paper encryption (AES-256-GCM) — Critical, never cached
    # -------------------------------------------------------------------------

    def _transit_key_name(self, tenant_id: str) -> str:
        """Deterministic per-tenant Transit key: alis-exam-{tenant_id}."""
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
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    logger.error("Failed to create transit key '%s': %s", key_name, exc)
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
        Encrypt exam paper content via per-tenant Transit key.

        FAIL-CLOSED: Raises VaultUnavailableError if Vault is unreachable.
        Exam paper encryption is Critical — no cache, no fallback.

        Args:
            tenant_id: Tenant scoping the Transit key.
            paper_id: Exam paper UUID — logged for audit traceability.
            plaintext: Raw bytes to encrypt.

        Returns:
            Vault ciphertext string (vault:v1:...).
        """
        if not self._is_available():
            raise VaultUnavailableError(
                "Vault is unreachable. Exam paper encryption requires a live Vault connection."
            )
        self.ensure_transit_key(tenant_id)
        b64 = base64.b64encode(plaintext).decode()
        key_name = self._transit_key_name(tenant_id)

        if self._client:
            resp = self._client.secrets.transit.encrypt_data(
                name=key_name, plaintext=b64, mount_point=self._transit_mount,
            )
            ciphertext: str = resp["data"]["ciphertext"]
        else:
            resp = self._urllib_request(
                "POST", f"/v1/{self._transit_mount}/encrypt/{key_name}", {"plaintext": b64},
            )
            ciphertext = resp["data"]["ciphertext"]

        self._audit("EXAM_PAPER_ENCRYPTED", tenant_id, paper_id)
        return ciphertext

    def decrypt_exam_paper(
        self, tenant_id: str, paper_id: str, ciphertext: str
    ) -> bytes:
        """
        Decrypt exam paper.

        FAIL-CLOSED: Raises VaultUnavailableError if Vault is unreachable.
        Caller MUST enforce CoE-only RBAC before calling this method.

        Args:
            tenant_id: Must match the tenant that produced the ciphertext.
            paper_id: Logged for audit trail.
            ciphertext: Vault ciphertext string (vault:v1:...).

        Returns:
            Original plaintext bytes.
        """
        if not self._is_available():
            raise VaultUnavailableError(
                "Vault is unreachable. Exam paper decryption requires a live Vault connection. "
                "Contact the system administrator immediately."
            )
        key_name = self._transit_key_name(tenant_id)

        if self._client:
            resp = self._client.secrets.transit.decrypt_data(
                name=key_name, ciphertext=ciphertext, mount_point=self._transit_mount,
            )
            plaintext_b64: str = resp["data"]["plaintext"]
        else:
            resp = self._urllib_request(
                "POST", f"/v1/{self._transit_mount}/decrypt/{key_name}", {"ciphertext": ciphertext},
            )
            plaintext_b64 = resp["data"]["plaintext"]

        self._audit("EXAM_PAPER_DECRYPTED", tenant_id, paper_id)
        return base64.b64decode(plaintext_b64)

    # -------------------------------------------------------------------------
    # KV v2: service secrets (with TTL cache + graceful degradation)
    # -------------------------------------------------------------------------

    def get_secret(self, path: str) -> dict:
        """
        Read a KV v2 secret.

        RESILIENCE STRATEGY:
        1. Serve from TTL cache if available (non-critical only).
        2. Fetch from Vault on cache miss.
        3. On Vault failure:
           - CRITICAL path: raise VaultUnavailableError.
           - NON-CRITICAL with env fallback: return env var.
           - Otherwise: raise VaultUnavailableError.

        Args:
            path: Secret path relative to KV mount (e.g. "alis/payment_key").

        Returns:
            Dict of secret key-value pairs.

        Raises:
            VaultUnavailableError: Critical path or no fallback is available.
        """
        # TTL cache check (critical secrets bypassed by _secret_cache.set)
        cached = _secret_cache.get(path)
        if cached is not None:
            return cached

        try:
            if self._client:
                resp = self._client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point=self._kv_mount
                )
                data = resp["data"]["data"]
            else:
                resp = self._urllib_request("GET", f"/v1/{self._kv_mount}/data/{path}")
                data = resp["data"]["data"]

            _secret_cache.set(path, data)
            return data

        except Exception as exc:
            if _is_critical(path):
                logger.critical(
                    "VAULT DOWN — critical secret '%s' unreachable: %s", path, exc
                )
                raise VaultUnavailableError(
                    f"Vault is unreachable and '{path}' is a critical secret. "
                    "System cannot proceed."
                ) from exc

            # Non-critical: try env var fallback
            fallback_env = _NON_CRITICAL_FALLBACK_ENV.get(path)
            if fallback_env:
                val = os.getenv(fallback_env)
                if val:
                    logger.warning(
                        "Vault unavailable — using env fallback for '%s' via %s.",
                        path, fallback_env,
                    )
                    return {"value": val}

            logger.error("Vault unavailable and no fallback for '%s': %s", path, exc)
            raise VaultUnavailableError(
                f"Vault is unreachable and '{path}' has no fallback configured."
            ) from exc

    def put_secret(self, path: str, data: dict) -> None:
        """Write / update a KV v2 secret and invalidate its cache entry."""
        if self._client:
            self._client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=data, mount_point=self._kv_mount
            )
        else:
            self._urllib_request(
                "POST", f"/v1/{self._kv_mount}/data/{path}", {"data": data}
            )
        _secret_cache.invalidate(path)

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
            url, data=data, method=method,
            headers={
                "X-Vault-Token": self._token,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _audit(self, action: str, tenant_id: str, entity_id: str) -> None:
        """Append an audit ledger entry for every Vault encrypt/decrypt operation."""
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
        except Exception as exc:
            # Audit failure must NEVER block the encrypt/decrypt operation
            logger.error(
                "Vault audit log failed (action=%s, entity=%s): %s", action, entity_id, exc
            )


@lru_cache(maxsize=1)
def get_vault_client() -> VaultClient:
    """Return the singleton VaultClient (created lazily at first call)."""
    return VaultClient()
