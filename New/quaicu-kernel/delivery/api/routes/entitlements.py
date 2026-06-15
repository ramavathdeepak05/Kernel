"""Caller entitlements — the console's per-tier UI gating source (WS-D).

``GET /v1/me/entitlements`` returns the bearer's tenant tier plus a feature-flag + quota map derived
from ``TIER_MATRIX`` (the single source of truth). The operator console reads this to show/hide
tier-gated UI; it never hard-codes the tier→feature mapping (which would drift from the matrix).

Entitlement-source resolution mirrors the rate-limit middleware: the provider's engine in shared-plane
mode, a wired entitlement store in single-kernel mode, else ``None``. With no entitlement source (a
dedicated single-kernel deploy) the response reports ``tier=None`` with every feature enabled — that
deployment is not tier-limited. With a source present but the tenant unprovisioned/inactive, it
fails closed (``NO_ACTIVE_PLAN``, every feature off).

This route reads (does not mint) identity: a bearer token must be present (401 otherwise), and the
tenant is the routing tenant. It exposes only commercial-tier metadata, so it does not run as a
governed action.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from core.entitlements import EntitlementEngine, TierSpec
from core.errors import EntitlementError
from delivery.api.deps import get_request_tenant
from delivery.api.routes.actions import _bearer_token
from delivery.api.schemas import EntitlementsResponse

router = APIRouter(prefix="/v1/me", tags=["entitlements"])

# The console's feature switches, each mapped to the tier grant that enables it. Keep these keys in
# sync with the console's `useFeature` calls.
_ALL_FEATURES: dict[str, bool] = {
    "policies": True,
    "policy_simulate": True,
    "inference": True,
    "approvals": True,
    "dashboard": True,
    "audit": True,
}


def _engine(request: Request) -> EntitlementEngine | None:
    """The entitlement engine: the provider's, else a wired store's, else None (not tier-limited)."""
    provider = getattr(request.app.state, "provider", None)
    if provider is not None:
        return provider.entitlements
    store = getattr(request.app.state, "entitlement_store", None)
    return EntitlementEngine(store) if store is not None else None


def _features(spec: TierSpec) -> dict[str, bool]:
    """Map a tier's grants onto the console feature switches."""
    return {
        # STARTER permits 0 policies → hide the policy-admin surface entirely.
        "policies": spec.max_policies != 0,
        # Backtest/simulate needs the CEL engine.
        "policy_simulate": "cel_policy" in spec.allowed_adapters,
        # The AI gateway surface needs an inference adapter.
        "inference": "openai_compat" in spec.allowed_adapters,
        # HITL approvals are meaningful only when the tier can run a gating profile.
        "approvals": bool(spec.allowed_profiles - {"audit_only", "monitor"}),
        # Read-only surfaces are available on every tier.
        "dashboard": True,
        "audit": True,
    }


def _quotas(spec: TierSpec) -> dict[str, int]:
    return {
        "max_policies": spec.max_policies,
        "max_actions_per_day": spec.max_actions_per_day,
        "rate_limit_per_min": spec.rate_limit_per_min,
    }


@router.get(
    "/entitlements",
    response_model=EntitlementsResponse,
    summary="The caller's tier, feature flags, and quotas",
)
async def entitlements(request: Request) -> EntitlementsResponse:
    _bearer_token(request)  # 401 if absent
    tenant = get_request_tenant(request)
    engine = _engine(request)

    if engine is None:
        # Dedicated single-kernel deploy: not tier-limited — surface everything.
        return EntitlementsResponse(
            tenant=str(tenant),
            tier=None,
            status=None,
            features=dict(_ALL_FEATURES),
            quotas={},
        )

    try:
        plan = engine.resolve_plan(tenant)
    except EntitlementError:
        # Unprovisioned / suspended / cancelled: fail closed — nothing tier-gated is shown.
        return EntitlementsResponse(
            tenant=str(tenant),
            tier=None,
            status="NO_ACTIVE_PLAN",
            features={k: False for k in _ALL_FEATURES},
            quotas={},
        )

    spec = plan.spec
    return EntitlementsResponse(
        tenant=str(tenant),
        tier=plan.tier.value,
        status=plan.status.value,
        features=_features(spec),
        quotas=_quotas(spec),
    )
