"""Shared SaaS-plane app builder (ADR-0009).

Turns a *plane-descriptor* config into a FastAPI app backed by a `TieredKernelProvider` that routes
each request to the kernel its tenant's tier is served by. Pure (no import-time side effects) so it is
unit-testable; `delivery/entrypoint_saas.py` is the thin uvicorn wrapper that loads the TOML and builds
the module-level ``app``.

Plane-descriptor config shape::

    [plane]                       # one kernel config path per served tier (ENTERPRISE excluded)
    starter  = "/etc/quaicu/kernel.starter.toml"
    business = "/etc/quaicu/kernel.business.toml"

    [entitlements]                # optional — durable plan store (see entitlements_config)
    dsn = "${ENTITLEMENTS_DSN}"

    [billing.stripe]              # optional — self-serve checkout + webhook tier flips (WS-C)
    ...

ENTERPRISE is intentionally not a plane tier: it ships as a dedicated single-kernel deployment
(`delivery/entrypoint.py` + `TieredKernelProvider.for_enterprise`), license-gated.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from core.entitlements import FeatureTier
from delivery.api.app import create_app
from delivery.sdk.billing_config import build_billing
from delivery.sdk.entitlements_config import build_entitlement_store
from delivery.sdk.metering_config import build_usage_meter
from delivery.sdk.policy_assistant_config import build_policy_assistant
from delivery.sdk.provider import TieredKernelProvider

# Plane keys → tier. STARTER + BUSINESS are the self-serve shared-plane tiers.
_TIER_KEYS: dict[str, FeatureTier] = {
    "starter": FeatureTier.STARTER,
    "business": FeatureTier.BUSINESS,
}


def tier_config_paths(config: Mapping[str, Any]) -> dict[FeatureTier, str]:
    """Resolve the ``[plane]`` section into a ``{FeatureTier: config_path}`` map (fail-closed)."""
    plane = config.get("plane")
    if not isinstance(plane, Mapping) or not plane:
        raise ValueError(
            "SaaS config needs a [plane] section mapping tier → kernel config path "
            "(e.g. starter = '…toml', business = '…toml')."
        )
    if "enterprise" in plane:
        raise ValueError(
            "ENTERPRISE is a dedicated deployment; use the single-kernel entrypoint with "
            "for_enterprise(), not the SaaS plane."
        )
    unknown = set(plane) - set(_TIER_KEYS)
    if unknown:
        raise ValueError(
            f"[plane] has unknown tier key(s) {sorted(unknown)}; expected a subset of "
            f"{sorted(_TIER_KEYS)}."
        )
    paths = {tier: str(plane[key]) for key, tier in _TIER_KEYS.items() if plane.get(key)}
    if not paths:
        raise ValueError("[plane] must declare at least one of: starter, business.")
    return paths


def build_saas_app(config: Mapping[str, Any]) -> FastAPI:
    """Build the shared-plane FastAPI app from a plane-descriptor config.

    Wires one shared `EntitlementStore` (durable when a DSN is configured) through both the provider's
    routing engine and the billing webhook — one source of truth for plans — and hydrates it at
    startup via create_app's lifespan.
    """
    store = build_entitlement_store(config)
    provider = TieredKernelProvider.for_saas(
        tier_config_paths=tier_config_paths(config),
        entitlement_store=store,
    )
    billing_adapters, billing_engine = build_billing(config, store)
    return create_app(
        provider=provider,
        entitlement_store=store,
        usage_meter=build_usage_meter(config),  # per-tenant daily-quota + usage; shared Redis if configured
        policy_assistant=build_policy_assistant(config),  # AI CEL drafting (vendor model; free-tier ok)
        billing_adapters=billing_adapters,
        billing_engine=billing_engine,
    )
