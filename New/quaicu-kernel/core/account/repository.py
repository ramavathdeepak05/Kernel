"""Account & API-key — durable repository protocol (ADR-0010).

The `AccountStore` is the in-process registry the auth hot path reads. A durable backend implementing
`AccountRepository` persists accounts + API keys so a restarted (or scaled-out) kernel still
authenticates self-serve keys and recognises existing signups. Mirrors
`core/entitlements/repository.py`.

These methods are **synchronous** — accounts are written only on the (infrequent) signup / key-issue
path, and the auth hot path reads the hydrated in-memory cache, never the DB. A sync (psycopg2) adapter
keeps `AccountEngine.signup` / `issue_api_key` synchronous (no async refactor of the auth surface).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.account.model import Account, ApiKey


@runtime_checkable
class AccountRepository(Protocol):
    """Durable backend for accounts + API keys. Synchronous (off the hot path)."""

    def load_all(self) -> tuple[list[Account], list[ApiKey]]:
        """Return (accounts, api_keys). Called once at startup to hydrate the cache."""
        ...

    def get_account_by_email(self, email: str) -> Account | None:
        """Durable lookup by email (case-insensitive). Used to make the signup duplicate check
        authoritative across instances — a brand-new account created on another instance isn't yet in
        this instance's cache, so the cache alone could let a duplicate signup through. Returns None
        when no account owns ``email``."""
        ...

    def save_account(self, account: Account) -> None:
        """Upsert an account keyed by ``account_id`` (idempotent)."""
        ...

    def save_api_key(self, key: ApiKey) -> None:
        """Upsert an API-key record keyed by ``key_id`` (idempotent)."""
        ...

    def replace_api_key(self, key: ApiKey) -> None:
        """Persist a mutated API-key record (e.g. revoked=True)."""
        ...

    def close(self) -> None:
        """Release any backend resources."""
        ...
