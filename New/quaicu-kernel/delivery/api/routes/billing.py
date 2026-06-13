"""Billing webhook route (WS-C).

  POST /v1/billing/webhook/{provider}   → verify a payment-provider webhook, flip the tenant's tier

The webhook is authenticated by the **provider's signature** (verified inside the adapter), not by a
kernel API key — so this path is exempt from `ApiKeyAuthMiddleware`. The raw request body is read
before any parsing because signature verification is computed over the exact bytes the provider sent.

Wiring: `create_app(billing_adapters={"stripe": ..., "razorpay": ...}, billing_engine=...)`. Absent
either, the route returns 503 (billing not enabled). Verification failure → 400 (fail-closed: no plan
change); an unmappable but verified event → 422.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.errors import BillingEventError, WebhookVerificationError

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class WebhookResult(BaseModel):
    ok: bool
    provider: str
    event_type: str
    tenant: str | None = None
    tier: str | None = None
    status: str | None = None


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
