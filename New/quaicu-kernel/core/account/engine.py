"""Account & API-key — the engine (ADR-0010).

`AccountEngine` owns self-serve provisioning: a signup creates an `Account`, mints a tenant id,
provisions a **default STARTER plan** in the entitlement store (so the new tenant can immediately make
governed calls on the shared plane), and issues one API key. The plaintext key is returned exactly
once; only its SHA-256 hash is persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timezone

from core.account.model import Account, AccountStatus, ApiKey
from core.account.store import AccountStore
from core.entitlements import CustomerPlan, EntitlementStore, FeatureTier, PlanStatus
from core.errors import AccountExistsError, ApiKeyInvalidError
from core.types import TenantId

log = logging.getLogger("quaicu.account")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:32] or "tenant"


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class AccountEngine:
    """Self-serve account provisioning and API-key authentication."""

    def __init__(self, accounts: AccountStore, entitlements: EntitlementStore) -> None:
        self._accounts = accounts
        self._entitlements = entitlements

    # ── Signup ───────────────────────────────────────────────────────────────────

    def signup(self, *, email: str, name: str) -> tuple[Account, str]:
        """Provision a new account on the STARTER tier. Returns (account, plaintext_api_key).

        Raises `AccountExistsError` if the email already owns an account. The plaintext key is the
        only time the full credential is available — the store keeps only its hash.
        """
        if self._accounts.get_account_by_email(email) is not None:
            raise AccountExistsError(
                f"An account already exists for {email!r}.",
                detail={"email": email},
            )

        now = datetime.now(timezone.utc)
        tenant = TenantId(f"{_slugify(name)}-{secrets.token_hex(3)}")
        account = Account(
            account_id=f"acct_{secrets.token_hex(8)}",
            tenant_id=tenant,
            email=email,
            name=name,
            status=AccountStatus.ACTIVE,
            created_at=now,
        )
        self._accounts.add_account(account)

        # Default plan: STARTER, ACTIVE — the new tenant is immediately routable on the shared plane.
        self._entitlements.upsert(
            CustomerPlan(
                tenant_id=tenant,
                tier=FeatureTier.STARTER,
                status=PlanStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )

        _, plaintext = self.issue_api_key(tenant)
        log.info("signup complete: tenant=%s tier=STARTER", tenant)
        return account, plaintext

    # ── API keys ─────────────────────────────────────────────────────────────────

    def issue_api_key(self, tenant: TenantId) -> tuple[ApiKey, str]:
        """Mint a new API key for ``tenant``. Returns (record, plaintext). Plaintext shown once."""
        key_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        record = ApiKey(
            key_id=key_id,
            tenant_id=tenant,
            hashed_secret=_hash_secret(secret),
            created_at=datetime.now(timezone.utc),
        )
        self._accounts.add_api_key(record)
        return record, f"qk_{key_id}_{secret}"

    def revoke_api_key(self, key_id: str) -> None:
        """Revoke a key so it can no longer authenticate. Idempotent."""
        import dataclasses

        existing = self._accounts.get_api_key(key_id)
        if existing is None:
            raise ApiKeyInvalidError(
                f"No API key {key_id!r} to revoke.", detail={"key_id": key_id}
            )
        self._accounts.replace_api_key(dataclasses.replace(existing, revoked=True))

    def verify_api_key(self, presented: str) -> Account:
        """Resolve the owning `Account` for a presented ``qk_<key_id>_<secret>`` key. Fail-closed.

        Raises `ApiKeyInvalidError` if the key is malformed, unknown, revoked, or the secret does not
        match. The comparison is constant-time.
        """
        parts = (presented or "").split("_", 2)
        if len(parts) != 3 or parts[0] != "qk":
            raise ApiKeyInvalidError("Malformed API key (expected 'qk_<id>_<secret>').")

        _, key_id, secret = parts
        record = self._accounts.get_api_key(key_id)
        if record is None or record.revoked:
            raise ApiKeyInvalidError(
                "API key is unknown or revoked.", detail={"key_id": key_id}
            )
        if not hmac.compare_digest(record.hashed_secret, _hash_secret(secret)):
            raise ApiKeyInvalidError("API key secret does not match.", detail={"key_id": key_id})

        account = self._accounts.get_account_by_tenant(record.tenant_id)
        if account is None:
            raise ApiKeyInvalidError(
                "API key has no owning account.", detail={"key_id": key_id}
            )
        return account
