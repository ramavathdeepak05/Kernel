"""Control-plane admin routes (ADR-0010).

Cross-tenant operations the operator (not a tenant) performs: list provisioned tenants and change a
tenant's tier. These are guarded by a deployment **admin token** (``app.state.admin_token``) presented
as a bearer token or ``X-Admin-Token`` header — a pragmatic control-plane guard; fuller operator RBAC
is WS-D. If no admin token is configured, the routes return 503 (closed by default).

  GET  /v1/admin/tenants                  → list customer plans
  POST /v1/admin/tenants/{tenant}/tier    → change a tenant's tier (e.g. manual upgrade)
  GET  /v1/admin/tenants/{tenant}/usage   → the tenant's metered usage for the current UTC day
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.entitlements import EntitlementEngine, FeatureTier
from core.errors import EntitlementError
from core.types import TenantId

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _require_admin(request: Request) -> None:
    """Fail-closed admin guard. 503 if no admin token configured; 401/403 otherwise."""
    expected = getattr(request.app.state, "admin_token", None)
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={"error": "Admin API not enabled", "code": "ADMIN_DISABLED"},
        )
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    presented = token.strip() if scheme.lower() == "bearer" else request.headers.get("x-admin-token", "")
    if not presented:
        raise HTTPException(status_code=401, detail={"error": "Missing admin token", "code": "UNAUTHENTICATED"})
    if not hmac.compare_digest(str(presented), str(expected)):
        raise HTTPException(status_code=403, detail={"error": "Invalid admin token", "code": "FORBIDDEN"})


def _store(request: Request):
    store = getattr(request.app.state, "entitlement_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Entitlement store not configured", "code": "ENTITLEMENTS_DISABLED"},
        )
    return store


class TenantPlanResponse(BaseModel):
    tenant_id: str
    tier: str
    status: str


class SetTierRequest(BaseModel):
    tier: str = Field(..., description="Target tier: STARTER | BUSINESS | ENTERPRISE")


@router.get("/tenants", response_model=list[TenantPlanResponse], summary="List provisioned tenants")
async def list_tenants(request: Request) -> list[TenantPlanResponse]:
    _require_admin(request)
    store = _store(request)
    return [
        TenantPlanResponse(tenant_id=str(p.tenant_id), tier=p.tier.value, status=p.status.value)
        for p in store.list_plans()
    ]


@router.post(
    "/tenants/{tenant}/tier",
    response_model=TenantPlanResponse,
    summary="Change a tenant's tier",
)
async def set_tier(tenant: str, body: SetTierRequest, request: Request) -> TenantPlanResponse:
    _require_admin(request)
    store = _store(request)
    try:
        target = FeatureTier(body.tier)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Unknown tier {body.tier!r}", "code": "BAD_TIER"},
        )
    try:
        plan = await store.set_tier_persisted(TenantId(tenant), target)
    except EntitlementError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
    return TenantPlanResponse(tenant_id=str(plan.tenant_id), tier=plan.tier.value, status=plan.status.value)


class UsageResponse(BaseModel):
    tenant_id: str
    day: str
    actions_today: int
    tier: str
    limit_per_day: int


@router.get(
    "/tenants/{tenant}/usage",
    response_model=UsageResponse,
    summary="A tenant's metered usage for the current UTC day",
)
async def tenant_usage(tenant: str, request: Request) -> UsageResponse:
    _require_admin(request)
    store = _store(request)
    meter = getattr(request.app.state, "usage_meter", None)
    if meter is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Usage metering not enabled", "code": "METERING_DISABLED"},
        )
    snap = meter.snapshot(TenantId(tenant))
    try:
        plan = EntitlementEngine(store).resolve_plan(TenantId(tenant))
        tier, limit = plan.tier.value, EntitlementEngine(store)._quota(plan, "max_actions_per_day")
    except EntitlementError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc), "code": exc.code})
    return UsageResponse(
        tenant_id=snap.tenant_id,
        day=snap.day,
        actions_today=snap.actions_today,
        tier=tier,
        limit_per_day=limit,
    )
