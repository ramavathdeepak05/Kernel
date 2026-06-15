"""Unit tests for build_entitlement_store — config-driven entitlement-store wiring (WS-C)."""

from __future__ import annotations

from adapters.entitlements.postgres import PostgresEntitlementRepository
from core.entitlements import EntitlementStore
from delivery.sdk.entitlements_config import build_entitlement_store


def test_no_entitlements_section_is_in_memory() -> None:
    store = build_entitlement_store({"storage": {"dsn": "postgresql://x/y"}})
    assert isinstance(store, EntitlementStore)
    assert store._repository is None  # storage DSN alone must not implicitly persist plans


def test_entitlements_section_without_dsn_falls_back_to_storage() -> None:
    store = build_entitlement_store(
        {"entitlements": {}, "storage": {"dsn": "postgresql://host/db"}}
    )
    assert isinstance(store._repository, PostgresEntitlementRepository)


def test_entitlements_dsn_takes_precedence() -> None:
    store = build_entitlement_store(
        {
            "entitlements": {"dsn": "postgresql://ent/db"},
            "storage": {"dsn": "postgresql://storage/db"},
        }
    )
    assert isinstance(store._repository, PostgresEntitlementRepository)
    assert store._repository._dsn == "postgresql://ent/db"


def test_env_var_substitution_resolves_dsn(monkeypatch) -> None:
    monkeypatch.setenv("ENT_DSN", "postgresql://secret-host/db")
    store = build_entitlement_store({"entitlements": {"dsn": "${ENT_DSN}"}})
    assert isinstance(store._repository, PostgresEntitlementRepository)
    assert store._repository._dsn == "postgresql://secret-host/db"


def test_entitlements_section_with_empty_dsn_is_in_memory() -> None:
    # Section present but no resolvable DSN (and no [storage]) → in-memory, not a crash.
    store = build_entitlement_store({"entitlements": {"dsn": ""}})
    assert store._repository is None
