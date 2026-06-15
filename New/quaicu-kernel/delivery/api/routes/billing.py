"""Billing routes (WS-C) — inbound webhooks + outbound checkout.

  POST /v1/billing/webhook/{provider}   → verify a payment-provider webhook, flip the tenant's tier
  POST /v1/billing/checkout             → start a checkout/subscription for the caller's own tenant

The **webhook** is authenticated by the **provider's signature** (verified inside the adapter), not by
a kernel API key — so only ``/v1/billing/webhook`` is exempt from `ApiKeyAuthMiddleware`. The raw body
is read before any parsing because signature verification is computed over the exact bytes sent.

The **checkout** route is the opposite: it is a normal authenticated, tenant-isolated, scoped
(`billing:write`) call — a tenant initiating its own upgrade. It stamps the authenticated tenant into
the provider's metadata/notes so the eventual webhook attributes the subscription back to it.

Wiring: `create_app(billing_adapters={"stripe": ..., "razorpay": ...}, billing_engine=...)`. Absent
the adapter/engine, the routes return 503. Webhook: verification failure → 400 (fail-closed); an
unmappable but verified event → 422. Checkout: provider call failure → 502; bad tier → 422.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.account.scopes import BILLING_WRITE
from core.billing.port import CheckoutPort
from core.entitlements.model import FeatureTier
from core.errors import BillingEventError, CheckoutError, WebhookVerificationError
from delivery.api.auth import enforce_scope
from delivery.api.deps import get_request_tenant
from delivery.api.routes.actions import _bearer_token

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class WebhookResult(BaseModel):
    ok: bool
    provider: str
    event_type: str
    tenant: str | None = None
    tier: str | None = None
    status: str | None = None


class CheckoutRequest(BaseModel):
    provider: str
    tier: str                       # "BUSINESS" | "ENTERPRISE" (STARTER is free — nothing to buy)
    success_url: str | None = None  # required by Stripe; ignored by Razorpay (hosted page)
    cancel_url: str | None = None
    customer_email: str | None = None


class CheckoutResponse(BaseModel):
    provider: str
    tenant: str
    tier: str
    url: str                        # redirect the end user here to pay
    reference: str | None = None    # provider session/subscription id


@router.post("/webhook/{provider}", response_model=WebhookResult, summary="Payment-provider webhook")
async def billing_webhook(provider: str, request: Request) -> WebhookResult:
    adapters = getattr(request.app.state, "billing_adapters", None) or {}
    engine = getattr(request.app.state, "billing_engine", None)
    adapter = adapters.get(provider)
    if adapter is None or engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": f"Billing not enabled for provider {provider!r}", "code": "BILLING_DISABLED"},
        )

    raw = await request.body()  # exact bytes — signature is computed over these
    try:
        event = adapter.verify_and_parse(payload=raw, headers=request.headers)
    except WebhookVerificationError as exc:
        # Fail-closed: an unverifiable webhook never mutates a plan.
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    except BillingEventError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc), "code": exc.code})

    try:
        plan = await engine.apply(event)
    except BillingEventError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc), "code": exc.code})

    return WebhookResult(
        ok=True,
        provider=provider,
        event_type=event.event_type.value,
        tenant=str(plan.tenant_id) if plan else (str(event.tenant_id) if event.tenant_id else None),
        tier=plan.tier.value if plan else None,
        status=plan.status.value if plan else None,
    )


@router.post("/checkout", response_model=CheckoutResponse, summary="Start a checkout / upgrade")
async def create_checkout(req: CheckoutRequest, request: Request) -> CheckoutResponse:
    _bearer_token(request)  # 401 if absent
    enforce_scope(request, BILLING_WRITE)
    # The checkout is always for the *authenticated* tenant — a tenant can only upgrade itself.
    tenant = get_request_tenant(request)

    try:
        tier = FeatureTier(req.tier)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Unknown tier {req.tier!r}", "code": "UNKNOWN_TIER"},
        )
    if tier is FeatureTier.STARTER:
        raise HTTPException(
            status_code=422,
            detail={"error": "STARTER is the free tier — nothing to purchase.", "code": "UNKNOWN_TIER"},
        )

    adapters = getattr(request.app.state, "billing_adapters", None) or {}
    adapter = adapters.get(req.provider)
    if adapter is None or not isinstance(adapter, CheckoutPort):
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"Checkout not enabled for provider {req.provider!r}",
                "code": "BILLING_DISABLED",
            },
        )

    try:
        session = await adapter.create_checkout(
            tenant=tenant,
            tier=tier,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
            customer_email=req.customer_email,
        )
    except CheckoutError as exc:
        # The kernel reached out to the provider and the step failed (misconfig / provider reject).
        raise HTTPException(status_code=502, detail={"error": str(exc), "code": exc.code})

    return CheckoutResponse(
        provider=session.provider,
        tenant=str(session.tenant_id),
        tier=session.tier.value,
        url=session.url,
        reference=session.reference,
    )
