"""Account & API-key — in-process registry, optionally backed by a durable store (ADR-0010).

Holds accounts (by id, indexed by email and tenant) and API keys (by key_id). Thread-safe. The auth
hot path reads this cache only. When a durable `AccountRepository` is wired, writes persist-through
(DB first, then cache) and `hydrate()` repopulates the cache at startup so signups survive a restart /
scale-out. Persistence is synchronous — it runs only on the infrequent signup / key-issue path.
"""

from __future__ import annotations

import logging
import threading

from core.account.model import Account, ApiKey
from core.account.repository import AccountRepository
from core.types import TenantId

log = logging.getLogger("quaicu.account")


class AccountStore:
    """In-process registry of accounts and API keys, with optional durable write-through."""

    def __init__(self, repository: AccountRepository | None = None) -> None:
        self._accounts: dict[str, Account] = {}            # account_id -> Account
        self._email_index: dict[str, str] = {}             # lower(email) -> account_id
        self._tenant_index: dict[str, str] = {}            # tenant_id -> account_id
        self._api_keys: dict[str, ApiKey] = {}             # key_id -> ApiKey
        self._lock = threading.Lock()
        self._repository = repository

    def hydrate(self) -> None:
        """Repopulate the cache from the durable repository. No-op when none is wired."""
        if self._repository is None:
            return
        accounts, keys = self._repository.load_all()
        with self._lock:
            for account in accounts:
                self._accounts[account.account_id] = account
                self._email_index[account.email.lower()] = account.account_id
                self._tenant_index[str(account.tenant_id)] = account.account_id
            for key in keys:
                self._api_keys[key.key_id] = key
        log.info("account store hydrated: %d account(s), %d key(s)", len(accounts), len(keys))

    # ── Accounts ─────────────────────────────────────────────────────────────────

    def get_account(self, account_id: str) -> Account | None:
        with self._lock:
            return self._accounts.get(account_id)

    def get_account_by_email(self, email: str) -> Account | None:
        with self._lock:
            aid = self._email_index.get(email.lower())
            return self._accounts.get(aid) if aid else None

    def get_account_by_tenant(self, tenant: TenantId) -> Account | None:
        with self._lock:
            aid = self._tenant_index.get(str(tenant))
            return self._accounts.get(aid) if aid else None

    def email_exists(self, email: str) -> bool:
        """Authoritative 'does this email already own an account?' check, used by signup.

        Fast path: the in-memory cache. Fallback: the durable repository — a brand-new account
        created on another instance isn't in this instance's cache yet, so the cache alone could let a
        duplicate signup through (and send a needless OTP). Only invoked on the infrequent signup path.
        """
        if self.get_account_by_email(email) is not None:
            return True
        getter = getattr(self._repository, "get_account_by_email", None)
        if getter is not None:
            return getter(email) is not None
        return False

    def add_account(self, account: Account) -> Account:
        if self._repository is not None:  # persist-first: a DB failure fails closed (no cache update)
            self._repository.save_account(account)
        with self._lock:
            self._accounts[account.account_id] = account
            self._email_index[account.email.lower()] = account.account_id
            self._tenant_index[str(account.tenant_id)] = account.account_id
        log.info("account created: id=%s tenant=%s", account.account_id, account.tenant_id)
        return account

    def list_accounts(self) -> list[Account]:
        with self._lock:
            return sorted(self._accounts.values(), key=lambda a: a.created_at)

    # ── API keys ─────────────────────────────────────────────────────────────────

    def add_api_key(self, key: ApiKey) -> ApiKey:
        if self._repository is not None:
            self._repository.save_api_key(key)
        with self._lock:
            self._api_keys[key.key_id] = key
        log.info("api key issued: key_id=%s tenant=%s", key.key_id, key.tenant_id)
        return key

    def get_api_key(self, key_id: str) -> ApiKey | None:
        with self._lock:
            return self._api_keys.get(key_id)

    def replace_api_key(self, key: ApiKey) -> None:
        if self._repository is not None:
            self._repository.replace_api_key(key)
        with self._lock:
            self._api_keys[key.key_id] = key

    def list_api_keys(self, tenant: TenantId) -> list[ApiKey]:
        with self._lock:
            return [k for k in self._api_keys.values() if str(k.tenant_id) == str(tenant)]
