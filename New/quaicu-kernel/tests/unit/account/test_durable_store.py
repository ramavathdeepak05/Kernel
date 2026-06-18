"""Durable account store — PostgresAccountRepository (fake psycopg2) + AccountStore write-through."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from adapters.account.postgres import PostgresAccountRepository
from core.account.model import Account, AccountStatus, ApiKey
from core.account.store import AccountStore
from core.errors import AccountPersistenceError
from core.types import TenantId

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def _account(aid: str = "acct_1", tenant: str = "acme") -> Account:
    return Account(
        account_id=aid, tenant_id=TenantId(tenant), email=f"{tenant}@b.io", name=tenant,
        status=AccountStatus.ACTIVE, created_at=NOW,
    )


def _key(kid: str = "k1", tenant: str = "acme") -> ApiKey:
    return ApiKey(key_id=kid, tenant_id=TenantId(tenant), hashed_secret="deadbeef", created_at=NOW)


# ── Fake psycopg2 connection ───────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, backend: "_FakeBackend") -> None:
        self._b = backend

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql: str, params=None):
        self._b.calls.append((sql, params))
        if "SELECT account_id" in sql:
            self._b.result = self._b.account_rows
        elif "SELECT key_id" in sql:
            self._b.result = self._b.key_rows

    def fetchall(self):
        return self._b.result


class _FakeConn:
    def __init__(self, backend: "_FakeBackend") -> None:
        self._b = backend

    def cursor(self):
        return _FakeCursor(self._b)

    def commit(self):
        self._b.commits += 1

    def close(self):
        self._b.closed += 1


class _FakeBackend:
    def __init__(self) -> None:
        self.calls: list = []
        self.result: list = []
        self.account_rows: list = []
        self.key_rows: list = []
        self.commits = 0
        self.closed = 0


def _repo(backend: _FakeBackend) -> PostgresAccountRepository:
    return PostgresAccountRepository("postgresql://fake/fake", connect=lambda: _FakeConn(backend))


# ── PostgresAccountRepository ───────────────────────────────────────────────────


def test_save_account_upserts_and_commits():
    b = _FakeBackend()
    _repo(b).save_account(_account())
    sql, params = b.calls[0]
    assert "INSERT INTO quaicu_accounts" in sql and "ON CONFLICT (account_id)" in sql
    assert params[0] == "acct_1" and params[1] == "acme" and params[4] == "ACTIVE"
    assert b.commits == 1 and b.closed == 1


def test_save_api_key_serializes_scopes_as_json():
    b = _FakeBackend()
    _repo(b).save_api_key(ApiKey("k1", TenantId("acme"), "h", NOW, scopes=frozenset({"a", "b"})))
    sql, params = b.calls[0]
    assert "INSERT INTO quaicu_api_keys" in sql
    assert params[5] == '["a", "b"]'  # sorted JSON array


def test_load_all_maps_rows():
    b = _FakeBackend()
    # 9 columns: …, full_name, job_title, phone (migration 008).
    b.account_rows = [("acct_1", "acme", "a@b.io", "Acme", "ACTIVE", NOW, "Ada Lovelace", "CTO", "+1")]
    b.key_rows = [("k1", "acme", "hash", NOW, False, ["read"])]
    accounts, keys = _repo(b).load_all()
    assert accounts[0].account_id == "acct_1" and accounts[0].status is AccountStatus.ACTIVE
    assert accounts[0].full_name == "Ada Lovelace" and accounts[0].job_title == "CTO"
    assert keys[0].key_id == "k1" and keys[0].scopes == frozenset({"read"})


def test_errors_wrap_as_account_persistence_error():
    def _boom():
        raise RuntimeError("db down")

    repo = PostgresAccountRepository("postgresql://fake/fake", connect=_boom)
    with pytest.raises(AccountPersistenceError, match="save_account failed"):
        repo.save_account(_account())


# ── AccountStore write-through + hydrate ────────────────────────────────────────


class _RecordingRepo:
    def __init__(self) -> None:
        self.accounts: list[Account] = []
        self.keys: list[ApiKey] = []

    def load_all(self):
        return list(self.accounts), list(self.keys)

    def save_account(self, account):
        self.accounts.append(account)

    def save_api_key(self, key):
        self.keys.append(key)

    def replace_api_key(self, key):
        self.keys.append(key)

    def close(self):
        pass


def test_store_persists_through_on_writes():
    repo = _RecordingRepo()
    store = AccountStore(repository=repo)
    store.add_account(_account())
    store.add_api_key(_key())
    assert len(repo.accounts) == 1 and len(repo.keys) == 1
    # And the cache is updated for the hot-path read.
    assert store.get_account_by_email("acme@b.io") is not None
    assert store.get_api_key("k1") is not None


def test_store_hydrate_populates_cache():
    repo = _RecordingRepo()
    repo.accounts = [_account()]
    repo.keys = [_key()]
    store = AccountStore(repository=repo)
    assert store.get_account("acct_1") is None  # empty before hydrate
    store.hydrate()
    assert store.get_account("acct_1") is not None
    assert store.get_account_by_tenant(TenantId("acme")) is not None
    assert store.get_api_key("k1") is not None


def test_in_memory_store_unaffected_without_repo():
    store = AccountStore()  # no repository
    store.add_account(_account())
    store.hydrate()  # no-op, must not raise
    assert store.get_account("acct_1") is not None
