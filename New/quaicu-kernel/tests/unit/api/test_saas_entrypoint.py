"""Unit tests for the shared SaaS-plane app builder (delivery/sdk/saas_app).

Uses an in-memory kernel config written to tmp_path, so no external services are required. Covers the
single-durable-kernel plane → provider wiring and the fail-closed [plane] validation. STARTER and
BUSINESS are served by the SAME kernel (the tier is a feature gate, not a separate data store), so a
STARTER→BUSINESS upgrade is a feature unlock, not a data migration.
"""

from __future__ import annotations

import pytest

from delivery.sdk.saas_app import build_saas_app, plane_config_path

# A minimal in-memory kernel config (no external deps) for the shared plane.
_MEMORY_SHARED = """
[tenant]
id = "saas-shared"

[adapters]
policy = "always_allow"
hitl   = "webhook"
ledger = "memory_ledger"
events = "memory_events"

[hitl]
dispatch_url = "http://localhost:9000/dispatch"
poll_url     = "http://localhost:9000/status"
timeout      = 10
"""


def _write_shared(tmp_path) -> str:
    p = tmp_path / "kernel.shared.toml"
    p.write_text(_MEMORY_SHARED)
    return str(p)


def test_build_saas_app_serves_starter_and_business(tmp_path) -> None:
    config = {"plane": {"config": _write_shared(tmp_path)}}
    app = build_saas_app(config)
    # One durable kernel serves both self-serve tiers.
    served = sorted(t.value for t in app.state.provider.served_tiers())
    assert served == ["BUSINESS", "STARTER"]
    # STARTER and BUSINESS resolve to the SAME kernel instance (feature unlock, not migration).
    from core.entitlements import FeatureTier

    provider = app.state.provider
    assert provider._kernels[FeatureTier.STARTER] is provider._kernels[FeatureTier.BUSINESS]
    # The shared entitlement store is wired through to the control plane (billing webhook + reads).
    assert app.state.entitlement_store is not None
    assert app.state.kernel is None  # provider mode, not single-kernel


def test_admin_token_closed_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("QUAICU_ADMIN_TOKEN", raising=False)
    config = {"plane": {"config": _write_shared(tmp_path)}}
    app = build_saas_app(config)
    assert app.state.admin_token is None  # /v1/admin/* stays closed (503) — safe default


def test_admin_token_wired_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUAICU_ADMIN_TOKEN", "s3cret-admin")
    config = {"plane": {"config": _write_shared(tmp_path)}}
    app = build_saas_app(config)
    assert app.state.admin_token == "s3cret-admin"  # enables manual tier changes via /v1/admin/*


# ── plane_config_path validation (fail-closed) ────────────────────────────────


def test_plane_config_path_rejects_enterprise() -> None:
    with pytest.raises(ValueError, match="ENTERPRISE"):
        plane_config_path({"plane": {"config": "s.toml", "enterprise": "e.toml"}})


def test_plane_config_path_requires_plane_section() -> None:
    with pytest.raises(ValueError, match=r"\[plane\]"):
        plane_config_path({})


def test_plane_config_path_rejects_legacy_per_tier_shape() -> None:
    # The old two-kernel shape is rejected with a migration hint to the single shared kernel.
    with pytest.raises(ValueError, match="single durable kernel"):
        plane_config_path({"plane": {"starter": "s.toml", "business": "b.toml"}})


def test_plane_config_path_requires_config_key() -> None:
    with pytest.raises(ValueError, match="config"):
        plane_config_path({"plane": {"region": "eu"}})


def test_plane_config_path_returns_single_config() -> None:
    assert plane_config_path({"plane": {"config": "/etc/quaicu/kernel.shared.toml"}}) == (
        "/etc/quaicu/kernel.shared.toml"
    )
