"""Unit tests for the shared SaaS-plane app builder (delivery/sdk/saas_app).

Uses in-memory tier configs written to tmp_path, so no external services are required. Covers the
plane → provider wiring and the fail-closed [plane] validation.
"""

from __future__ import annotations

import pytest

from core.entitlements import FeatureTier
from delivery.sdk.saas_app import build_saas_app, tier_config_paths

# A minimal in-memory kernel config (no external deps) for a single plane tier.
_MEMORY_TIER = """
[tenant]
id = "{id}"

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


def _write_tier(tmp_path, name: str, tenant_id: str) -> str:
    p = tmp_path / f"{name}.toml"
    p.write_text(_MEMORY_TIER.format(id=tenant_id))
    return str(p)


def test_build_saas_app_serves_starter_and_business(tmp_path) -> None:
    config = {
        "plane": {
            "starter": _write_tier(tmp_path, "starter", "saas-starter"),
            "business": _write_tier(tmp_path, "business", "saas-business"),
        }
    }
    app = build_saas_app(config)
    served = sorted(t.value for t in app.state.provider.served_tiers())
    assert served == ["BUSINESS", "STARTER"]
    # The shared entitlement store is wired through to the control plane (billing webhook + reads).
    assert app.state.entitlement_store is not None
    assert app.state.kernel is None  # provider mode, not single-kernel


def test_build_saas_app_single_tier(tmp_path) -> None:
    config = {"plane": {"starter": _write_tier(tmp_path, "starter", "saas-starter")}}
    app = build_saas_app(config)
    assert [t.value for t in app.state.provider.served_tiers()] == ["STARTER"]


def test_admin_token_closed_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("QUAICU_ADMIN_TOKEN", raising=False)
    config = {"plane": {"starter": _write_tier(tmp_path, "starter", "saas-starter")}}
    app = build_saas_app(config)
    assert app.state.admin_token is None  # /v1/admin/* stays closed (503) — safe default


def test_admin_token_wired_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUAICU_ADMIN_TOKEN", "s3cret-admin")
    config = {"plane": {"starter": _write_tier(tmp_path, "starter", "saas-starter")}}
    app = build_saas_app(config)
    assert app.state.admin_token == "s3cret-admin"  # enables manual tier changes via /v1/admin/*


# ── tier_config_paths validation (fail-closed) ────────────────────────────────


def test_tier_config_paths_rejects_enterprise() -> None:
    with pytest.raises(ValueError, match="ENTERPRISE"):
        tier_config_paths({"plane": {"starter": "a.toml", "enterprise": "e.toml"}})


def test_tier_config_paths_requires_plane_section() -> None:
    with pytest.raises(ValueError, match=r"\[plane\]"):
        tier_config_paths({})


def test_tier_config_paths_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown tier key"):
        tier_config_paths({"plane": {"gold": "g.toml"}})


def test_tier_config_paths_maps_known_tiers() -> None:
    paths = tier_config_paths({"plane": {"starter": "s.toml", "business": "b.toml"}})
    assert paths == {FeatureTier.STARTER: "s.toml", FeatureTier.BUSINESS: "b.toml"}
