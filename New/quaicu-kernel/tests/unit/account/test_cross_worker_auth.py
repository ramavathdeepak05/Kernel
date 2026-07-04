"""Cross-worker auth consistency (D4-1): find_api_key / find_account_by_tenant fallbacks + TTL.

A key or account created on another worker/instance lives in the durable store but not this
process's cache; the authoritative lookups must fall back and cache the result. Revocations
flipped elsewhere must propagate within the TTL.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.account.model import Account, AccountStatus, ApiKey
from core.account.store import AccountStore
from core.types import TenantId

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _account(aid: str = "acct_1", tenant: str = "acme") -> Account:
    return Account(
        account_id=aid, tenant_id=TenantId(tenant), email=f"{tenant}@b.io", name=tenant,
        status=AccountStatus.ACTIVE, created_at=NOW,
    )


def _key(kid: str = "k1", tenant: str = "acme", revoked: bool = False) -> ApiKey:
    return ApiKey(
        key_id=kid, tenant_id=TenantId(tenant), hashed_secret="deadbeef",
        created_at=NOW, revoked=revoked,
    )


class _FakeRepo:
    """Durable store shared by 'workers': dicts standing in for Postgres."""

    def __init__(self) -> None:
        self.keys: dict[str, ApiKey] = {}
        self.accounts_by_tenant: dict[str, Account] = {}
        self.key_reads = 0

    # Only the getters the fallbacks use are needed (getattr-based lookup).
    def get_api_key(self, key_id: str) -> ApiKey | None:
        self.key_reads += 1
        return self.keys.get(key_id)

    def get_account_by_tenant(self, tenant: TenantId) -> Account | None:
        return self.accounts_by_tenant.get(str(tenant))


def test_find_api_key_falls_back_to_repository_and_caches() -> None:
    repo = _FakeRepo()
    repo.keys["k1"] = _key()
    store = AccountStore(repository=repo)  # cold cache — "the other worker"

    assert store.get_api_key("k1") is None  # plain cache lookup misses
    found = store.find_api_key("k1")
    assert found is not None and found.key_id == "k1"
    # Cached now: a second find within the TTL doesn't re-read the repo.
    reads = repo.key_reads
    assert store.find_api_key("k1") is not None
    assert repo.key_reads == reads


def test_find_api_key_miss_returns_none() -> None:
    store = AccountStore(repository=_FakeRepo())
    assert store.find_api_key("ghost") is None


def test_find_api_key_ttl_refresh_sees_remote_revocation(monkeypatch) -> None:
    import core.account.store as store_mod

    repo = _FakeRepo()
    repo.keys["k1"] = _key()
    store = AccountStore(repository=repo)
    assert store.find_api_key("k1").revoked is False  # cached fresh

    # Another worker revokes the key in the durable store; our cache is now stale.
    repo.keys["k1"] = _key(revoked=True)
    # Force the TTL window shut: everything cached is instantly stale.
    monkeypatch.setattr(store_mod, "_API_KEY_TTL_SECONDS", 0.0000001)
    refreshed = store.find_api_key("k1")
    assert refreshed is not None and refreshed.revoked is True


def test_find_api_key_serves_cache_when_refresh_faults(monkeypatch) -> None:
    import core.account.store as store_mod

    repo = _FakeRepo()
    repo.keys["k1"] = _key()
    store = AccountStore(repository=repo)
    assert store.find_api_key("k1") is not None

    def _boom(key_id: str):
        raise RuntimeError("db down")

    repo.get_api_key = _boom  # type: ignore[method-assign]
    monkeypatch.setattr(store_mod, "_API_KEY_TTL_SECONDS", 0.0000001)
    # Availability: the cached copy is served rather than failing auth outright.
    assert store.find_api_key("k1") is not None


def test_find_account_by_tenant_falls_back_and_caches() -> None:
    repo = _FakeRepo()
    repo.accounts_by_tenant["acme"] = _account()
    store = AccountStore(repository=repo)

    assert store.get_account_by_tenant(TenantId("acme")) is None
    found = store.find_account_by_tenant(TenantId("acme"))
    assert found is not None and found.account_id == "acct_1"
    # Indexed into the cache (email + tenant indexes populated).
    assert store.get_account_by_tenant(TenantId("acme")) is not None
    assert store.get_account_by_email("acme@b.io") is not None


def test_find_api_key_without_repository_is_cache_only() -> None:
    store = AccountStore()
    assert store.find_api_key("k1") is None
    store.add_api_key(_key())
    assert store.find_api_key("k1") is not None
