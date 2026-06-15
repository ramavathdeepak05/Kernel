"""Config-driven billing wiring (WS-C).

Turns a ``[billing]`` TOML section into the live `billing_adapters` + `BillingEngine` that
`create_app` consumes — so a production deploy enables Stripe/Razorpay from config + environment
instead of constructing adapters in code. Without a ``[billing]`` section this is a no-op and billing
stays disabled (the routes 503), preserving the behavior of a non-billing deploy.

Secrets are referenced as ``${ENV_VAR}`` in the TOML and resolved from the environment at load
(`os.path.expandvars`), so live payment keys never live in the committed config file.

Config shape::

    [billing.stripe]
    webhook_secret = "${STRIPE_WEBHOOK_SECRET}"
    api_key        = "${STRIPE_API_KEY}"        # omit for webhook-only (no checkout)
    [billing.stripe.price_to_tier]
    "price_business"   = "BUSINESS"
    "price_enterprise" = "ENTERPRISE"

    [billing.razorpay]
    webhook_secret = "${RAZORPAY_WEBHOOK_SECRET}"
    key_id         = "${RAZORPAY_KEY_ID}"
    key_secret     = "${RAZORPAY_KEY_SECRET}"
    [billing.razorpay.plan_to_tier]
    "plan_business" = "BUSINESS"
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from adapters.billing import RazorpayBillingAdapter, StripeBillingAdapter
from core.billing import BillingEngine
from core.entitlements import EntitlementStore, FeatureTier


def _expand_env(node: Any) -> Any:
    """Recursively resolve ``${ENV_VAR}`` references in string values (dicts/lists/strings)."""
    if isinstance(node, str):
        return os.path.expandvars(node)
    if isinstance(node, Mapping):
        return {k: _expand_env(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    return node


def _tier_map(raw: Mapping[str, str], *, what: str) -> dict[str, FeatureTier]:
    """Parse a ``{ "<provider id>": "TIER" }`` table into id → FeatureTier (fail-closed on bad tier)."""
    out: dict[str, FeatureTier] = {}
    for ref, tier_name in raw.items():
        try:
            out[ref] = FeatureTier(str(tier_name).upper())
        except ValueError as exc:
            raise ValueError(
                f"{what}: {ref!r} maps to unknown tier {tier_name!r} "
                f"(expected one of {[t.value for t in FeatureTier]})."
            ) from exc
    return out


def _require(section: Mapping[str, Any], key: str, *, provider: str) -> str:
    value = section.get(key)
    if not value:
        raise ValueError(f"[billing.{provider}] is missing required {key!r}.")
    return str(value)


def _build_stripe(section: Mapping[str, Any]) -> StripeBillingAdapter:
    return StripeBillingAdapter(
        webhook_secret=_require(section, "webhook_secret", provider="stripe"),
        price_to_tier=_tier_map(section.get("price_to_tier", {}), what="[billing.stripe.price_to_tier]"),
        api_key=section.get("api_key") or None,
        api_base=section.get("api_base", "https://api.stripe.com"),
        tolerance_seconds=int(section.get("tolerance_seconds", 300)),
    )


def _build_razorpay(section: Mapping[str, Any]) -> RazorpayBillingAdapter:
    return RazorpayBillingAdapter(
        webhook_secret=_require(section, "webhook_secret", provider="razorpay"),
        plan_to_tier=_tier_map(section.get("plan_to_tier", {}), what="[billing.razorpay.plan_to_tier]"),
        key_id=section.get("key_id") or None,
        key_secret=section.get("key_secret") or None,
        api_base=section.get("api_base", "https://api.razorpay.com"),
        subscription_total_count=int(section.get("subscription_total_count", 12)),
    )


_BUILDERS = {"stripe": _build_stripe, "razorpay": _build_razorpay}


def build_billing(
    config: Mapping[str, Any],
    entitlements: EntitlementStore,
) -> tuple[dict[str, object], BillingEngine | None]:
    """Construct billing adapters + engine from a ``[billing]`` config section.

    Returns ``({}, None)`` when no ``[billing]`` section is present (billing disabled). Otherwise
    returns ``(adapters_by_provider, BillingEngine(entitlements))`` so a verified webhook flips the
    tenant's plan in the same ``EntitlementStore`` the entitlements/rate-limit reads use.
    """
    billing = config.get("billing")
    if not billing:
        return {}, None

    adapters: dict[str, object] = {}
    for provider, builder in _BUILDERS.items():
        section = billing.get(provider)
        if not section:
            continue
        adapters[provider] = builder(_expand_env(section))

    if not adapters:
        return {}, None
    return adapters, BillingEngine(entitlements)
