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

import os
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from core.entitlements import FeatureTier
from delivery.api.app import create_app
from delivery.sdk.account_config import build_account_engine, require_api_key
from delivery.sdk.billing_config import build_billing
from delivery.sdk.email_config import build_email_sender
from delivery.sdk.erasure_config import build_erasure
from delivery.sdk.entitlements_config import build_entitlement_store
from delivery.sdk.coupon_config import build_coupon_book
from delivery.sdk.signup_payment_config import build_signup_payment
from delivery.sdk.metering_config import build_usage_meter
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
        account_engine=build_account_engine(config, store),  # self-serve signup ([account].enabled)
        require_api_key=require_api_key(config),
        billing_adapters=billing_adapters,
        billing_engine=billing_engine,
        email_sender=build_email_sender(config),  # Resend when RESEND_API_KEY set, else log-only
        signup_payment=build_signup_payment(config),  # ₹2 fee gate when [signup_fee].enabled
        consultation=dict(config.get("consultation", {})),  # Business/Enterprise consultation config
        coupon_book=build_coupon_book(config),  # discount codes for the fee / consultation
        erasure_engine=build_erasure(config),  # crypto-shred erasure when [erasure].enabled (W6-4)
        cors_origins=_cors_origins(config),
    )


def _cors_origins(config: Mapping[str, Any]) -> list[str] | None:
    """Browser origins allowed to call the API (the deployed console runs on a separate origin).

    Resolution order: the ``CORS_ORIGINS`` env var (comma-separated — convenient for Cloud Run /
    container envs) → a ``[cors] origins = [...]`` config list → ``None`` (which falls back to
    ``create_app``'s localhost-dev default). A production deploy MUST set one of the first two to the
    console's origin, else its cross-origin requests are blocked by CORS.
    """
    env = os.getenv("CORS_ORIGINS", "")
    if env.strip():
        return [o.strip() for o in env.split(",") if o.strip()]
    section = config.get("cors")
    if isinstance(section, Mapping) and section.get("origins"):
        return [str(o) for o in section["origins"]]
    return None
