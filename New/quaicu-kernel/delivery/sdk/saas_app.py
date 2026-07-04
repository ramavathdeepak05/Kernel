"""Shared SaaS-plane app builder (ADR-0009).

Turns a *plane-descriptor* config into a FastAPI app backed by a `TieredKernelProvider` that routes
each request to the kernel its tenant's tier is served by. Pure (no import-time side effects) so it is
unit-testable; `delivery/entrypoint_saas.py` is the thin uvicorn wrapper that loads the TOML and builds
the module-level ``app``.

Plane-descriptor config shape::

    [plane]                       # ONE durable kernel config serving all self-serve tiers
    config = "/etc/quaicu/kernel.shared.toml"

    [entitlements]                # optional — durable plan store (see entitlements_config)
    dsn = "${ENTITLEMENTS_DSN}"

    [billing.stripe]              # optional — self-serve checkout + webhook tier flips (WS-C)
    ...

STARTER and BUSINESS are served by the **same** durable kernel; the commercial tier is a pure feature
gate enforced at the API edge by the EntitlementEngine, so a STARTER→BUSINESS upgrade is a feature
unlock, not a data migration. (The former per-tier ``starter = … / business = …`` shape — two separate
kernels — is no longer supported; see ``plane_config_path``.)

ENTERPRISE is intentionally not a plane tier: it ships as a dedicated single-kernel deployment
(`delivery/entrypoint.py` + `TieredKernelProvider.for_enterprise`), license-gated.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from delivery.api.app import create_app
from delivery.sdk.account_config import build_account_engine, require_api_key
from delivery.sdk.billing_config import build_billing
from delivery.sdk.email_config import build_email_sender
from delivery.sdk.erasure_config import build_erasure
from delivery.sdk.entitlements_config import build_entitlement_store
from delivery.sdk.coupon_config import build_coupon_book
from delivery.sdk.signup_payment_config import build_signup_payment
from delivery.sdk.mcp_config import build_mcp_gateway
from delivery.sdk.metering_config import build_usage_meter
from delivery.sdk.provider import TieredKernelProvider

def plane_config_path(config: Mapping[str, Any]) -> str:
    """Resolve the ``[plane]`` section to the single shared-kernel config path (fail-closed).

    The shared self-serve plane is ONE durable kernel serving STARTER + BUSINESS (the tier is a feature
    gate, not a separate data store). Accepts ``[plane] config = "…"``. The former per-tier shape
    (``starter = … / business = …`` — two kernels) is rejected with a migration hint.
    """
    plane = config.get("plane")
    if not isinstance(plane, Mapping) or not plane:
        raise ValueError(
            "SaaS config needs a [plane] section with a single durable kernel config "
            '(e.g. config = "/etc/quaicu/kernel.shared.toml").'
        )
    if "enterprise" in plane:
        raise ValueError(
            "ENTERPRISE is a dedicated deployment; use the single-kernel entrypoint with "
            "for_enterprise(), not the SaaS plane."
        )
    if "starter" in plane or "business" in plane:
        raise ValueError(
            "[plane] now uses a single durable kernel: set `config = \"…/kernel.shared.toml\"` "
            "instead of the old per-tier `starter = … / business = …`. STARTER and BUSINESS share "
            "one durable kernel; the tier is a feature gate (upgrade = feature unlock, not migration)."
        )
    path = plane.get("config")
    if not path:
        raise ValueError('[plane] must declare `config = "…/kernel.shared.toml"`.')
    return str(path)


def build_saas_app(
    config: Mapping[str, Any], *, mcp_server: Any | None = None, mcp_proxy: Any | None = None
) -> FastAPI:
    """Build the shared-plane FastAPI app from a plane-descriptor config.

    Wires one shared `EntitlementStore` (durable when a DSN is configured) through both the provider's
    routing engine and the billing webhook — one source of truth for plans — and hydrates it at
    startup via create_app's lifespan.

    ``mcp_server`` / ``mcp_proxy`` (pass at most one): the hosted, authenticated, per-tenant MCP
    endpoint served at ``/mcp`` — each call governed by the caller's tenant policies and sealed to
    that tenant's ledger. ``mcp_server`` is an operator-built, tools-only `GovernedMCPServer` (register
    handlers in code — they can't come from TOML). ``mcp_proxy`` is a `GovernedMCPProxy` in
    **BYO-downstream** mode: each tenant registers their own downstream MCP server at
    ``PUT /v1/mcp/connection`` and the endpoint mirrors + governs + forwards their tools.
    """
    store = build_entitlement_store(config)
    provider = TieredKernelProvider.for_shared_saas(
        config_path=plane_config_path(config),
        entitlement_store=store,
    )
    billing_adapters, billing_engine = build_billing(config, store)
    # Hosted MCP endpoint: an explicit param wins; otherwise build from the [mcp] config section
    # (BYO-downstream proxy). None → /mcp is not mounted.
    mcp_proxy = mcp_proxy or build_mcp_gateway(config)
    # Periodic ledger anchoring (D3-2): [anchor] interval_seconds → cosign each STH on a cadence.
    anchor_interval = float(config.get("anchor", {}).get("interval_seconds", 0) or 0) or None
    return create_app(
        provider=provider,
        mcp_server=mcp_server,
        mcp_proxy=mcp_proxy,
        anchor_interval=anchor_interval,
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
        # Control-plane admin guard (ADR-0010): enables /v1/admin/* (e.g. manual tier changes) when a
        # token is provisioned. Read from the environment so the secret stays out of the config file;
        # unset → the admin routes stay closed (503), the safe default.
        admin_token=os.getenv("QUAICU_ADMIN_TOKEN") or None,
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
