"""Account & API-key — in-memory store (ADR-0010).

Holds accounts (by id, indexed by email and tenant) and API keys (by key_id). Thread-safe. A durable
`AccountRepository` write-through can back it later; the in-memory store is the Wave-1 implementation.
"""

from __future__ import annotations

import logging
import threading

from core.account.model import Account, ApiKey
from core.types import TenantId

log = logging.getLogger("quaicu.account")


class AccountStore:
    """In-process registry of accounts and API keys."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}            # account_id -> Account
        self._email_index: dict[str, str] = {}             # lower(email) -> account_id
        self._tenant_index: dict[str, str] = {}            # tenant_id -> account_id
        self._api_keys: dict[str, ApiKey] = {}             # key_id -> ApiKey
        self._lock = threading.Lock()

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

    def add_account(self, account: Account) -> Account:
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
        with self._lock:
            self._api_keys[key.key_id] = key
        log.info("api key issued: key_id=%s tenant=%s", key.key_id, key.tenant_id)
        return key

    def get_api_key(self, key_id: str) -> ApiKey | None:
        with self._lock:
            return self._api_keys.get(key_id)

    def replace_api_key(self, key: ApiKey) -> None:
        with self._lock:
            self._api_keys[key.key_id] = key

    def list_api_keys(self, tenant: TenantId) -> list[ApiKey]:
        with self._lock:
            return [k for k in self._api_keys.values() if str(k.tenant_id) == str(tenant)]
