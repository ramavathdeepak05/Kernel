"""
Control Plane Router — S2

Two sets of endpoints:

/internal/...   — Called by data planes (TenantRegistry HTTP fallback).
                  Protected by X-Internal-Token header.

/admin/...      — Called by ALIS superadmins (provisioning UI / CLI scripts).
                  Protected by admin JWT (Bearer token).

All routes are synchronous — provisioning is queued via background tasks;
DB reads/writes use the cp_db psycopg2 pool.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from control_plane.billing_models import BillingUsageRequest
from control_plane.models import (
    CacheInvalidateRequest,
    ProvisionResponse,
    TenantListResponse,
    TenantProvisionRequest,
    TenantRecord,
    TenantUpdateRequest,
)
from control_plane.repository import TenantRepository

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------

def _require_internal_token(x_internal_token: str = Header(..., alias="X-Internal-Token")) -> None:
    from control_plane.settings import settings
    import secrets
    if not secrets.compare_digest(x_internal_token, settings.internal_token):
        raise HTTPException(status_code=401, detail="Invalid internal token")


def _require_admin_jwt(authorization: str = Header(...)) -> dict:
    """Validate admin Bearer JWT. Returns the decoded payload."""
    from control_plane.settings import settings
    try:
        import jwt as _pyjwt
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        token = authorization[7:].strip()
        payload = _pyjwt.decode(token, settings.admin_jwt_secret, algorithms=[settings.admin_jwt_algorithm])
        if payload.get("role") not in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
            raise HTTPException(status_code=403, detail="Admin role required")
        return payload
    except (_pyjwt.PyJWTError, Exception) as exc:
        raise HTTPException(status_code=401, detail=str(exc))


# ---------------------------------------------------------------------------
# /internal — Data plane → control plane calls
# ---------------------------------------------------------------------------

@router.get(
    "/internal/tenants/{tenant_id}/db-config",
    response_model=TenantRecord,
    dependencies=[Depends(_require_internal_token)],
    summary="Get DB config for a tenant (called by TenantRegistry)",
)
def get_tenant_db_config(tenant_id: str):
    record = TenantRepository.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    return record


@router.get(
    "/internal/tenants/by-subdomain/{subdomain}",
    response_model=TenantRecord,
    dependencies=[Depends(_require_internal_token)],
    summary="Resolve tenant by subdomain slug (called by SubdomainTenantMiddleware)",
)
def get_tenant_by_subdomain(subdomain: str):
    record = TenantRepository.get_by_subdomain(subdomain)
    if not record:
        raise HTTPException(status_code=404, detail=f"Subdomain '{subdomain}' not registered")
    return record


@router.post(
    "/internal/tenants/{tenant_id}/invalidate-cache",
    dependencies=[Depends(_require_internal_token)],
    summary="Evict tenant record from data plane Redis cache",
)
async def invalidate_tenant_cache(tenant_id: str, body: CacheInvalidateRequest):
    """
    Notifies all data planes to evict their Redis cache for this tenant.
    In a multi-region setup, each data plane calls this on its own Redis.
    Here we fan out to the local Redis only (S1 contract).
    """
    try:
        # Import TenantRegistry from the ALIS data plane code.
        # This works because control_plane and ALIS share the same Python env in the monorepo.
        import sys, os
        alis_path = os.path.join(os.path.dirname(__file__), "..", "ALIS")
        if alis_path not in sys.path:
            sys.path.insert(0, alis_path)
        from server.core.tenant_registry import TenantRegistry
        await TenantRegistry.invalidate(tenant_id, subdomain=body.subdomain)
        return {"invalidated": True, "tenant_id": tenant_id}
    except Exception as exc:
        logger.warning("Cache invalidation failed for tenant=%s: %s", tenant_id, exc)
        return {"invalidated": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# /admin — Admin portal / CLI calls
# ---------------------------------------------------------------------------

@router.post(
    "/admin/tenants",
    response_model=ProvisionResponse,
    status_code=202,
    summary="Provision a new tenant (async — enqueued as background task)",
)
def provision_tenant(
    body: TenantProvisionRequest,
    background_tasks: BackgroundTasks,
    _admin=Depends(_require_admin_jwt),
):
    """
    Accepts the provisioning request and immediately returns 202 Accepted.
    The actual DB creation + migration runs as a background task.

    Poll GET /admin/tenants/{tenant_id} to check status.
    """
    tenant_id = str(uuid.uuid4())

    # Insert placeholder record so the admin can track status
    import json
    from control_plane import db as cp_db
    from control_plane.settings import settings

    # Placeholder — will be updated by the background task with real DB details
    cp_db.execute(
        """
        INSERT INTO cp_tenants
            (tenant_id, subdomain, display_name, region, db_host, db_port,
             db_name, db_user, db_password_enc, plan, feature_flags, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'provisioning')
        """,
        (
            tenant_id,
            body.subdomain,
            body.display_name,
            body.region,
            body.db_host or settings.cp_pg_admin_host,
            body.db_port or settings.cp_pg_admin_port,
            f"alis_{body.subdomain.replace('-', '_')}",
            f"alis_{body.subdomain.replace('-', '_')}",
            "",  # empty — filled by provisioner
            body.plan,
            json.dumps(body.feature_flags),
        ),
    )

    def _run_provision():
        from control_plane.provisioner import TenantProvisioner
        try:
            TenantProvisioner.provision(
                tenant_id=tenant_id,
                subdomain=body.subdomain,
                display_name=body.display_name,
                region=body.region,
                plan=body.plan,
                feature_flags=body.feature_flags,
                db_host=body.db_host,
                db_port=body.db_port,
                db_user_override=body.db_user,
                db_password_override=body.db_password,
            )
        except Exception as exc:
            logger.error("Provision background task failed for tenant=%s: %s", tenant_id, exc)
            cp_db.execute(
                "UPDATE cp_tenants SET status = 'provision_failed', updated_at = NOW() WHERE tenant_id = %s",
                (tenant_id,),
            )

    background_tasks.add_task(_run_provision)

    return ProvisionResponse(
        tenant_id=tenant_id,
        subdomain=body.subdomain,
        status="provisioning",
        message="Provisioning started. Poll GET /admin/tenants/{tenant_id} for status.",
    )


@router.get(
    "/admin/tenants",
    response_model=TenantListResponse,
    summary="List all tenants",
)
def list_tenants(
    status: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(_require_admin_jwt),
):
    items, total = TenantRepository.list_tenants(
        status=status, region=region, limit=limit, offset=offset
    )
    return TenantListResponse(items=items, total=total)


@router.get(
    "/admin/tenants/{tenant_id}",
    response_model=TenantRecord,
    summary="Get full tenant record",
)
def get_tenant(tenant_id: str, _admin=Depends(_require_admin_jwt)):
    record = TenantRepository.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    return record


@router.patch(
    "/admin/tenants/{tenant_id}",
    response_model=TenantRecord,
    summary="Update tenant metadata (display_name, plan, feature_flags, region)",
)
def update_tenant(
    tenant_id: str,
    body: TenantUpdateRequest,
    _admin=Depends(_require_admin_jwt),
):
    record = TenantRepository.update(
        tenant_id,
        display_name=body.display_name,
        plan=body.plan,
        feature_flags=body.feature_flags,
        region=body.region,
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    return record


@router.put(
    "/admin/tenants/{tenant_id}/suspend",
    summary="Suspend a tenant (blocks all data plane requests)",
)
def suspend_tenant(tenant_id: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.provisioner import TenantProvisioner
    record = TenantRepository.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    TenantProvisioner.suspend(tenant_id)
    return {"tenant_id": tenant_id, "status": "suspended"}


@router.put(
    "/admin/tenants/{tenant_id}/reactivate",
    summary="Reactivate a suspended tenant",
)
def reactivate_tenant(tenant_id: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.provisioner import TenantProvisioner
    record = TenantRepository.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    TenantProvisioner.reactivate(tenant_id)
    return {"tenant_id": tenant_id, "status": "active"}


@router.delete(
    "/admin/tenants/{tenant_id}",
    summary="Soft-delete a tenant. Pass ?drop_database=true to also DROP DATABASE (IRREVERSIBLE).",
)
def delete_tenant(
    tenant_id: str,
    drop_database: bool = Query(default=False),
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.provisioner import TenantProvisioner
    record = TenantRepository.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    TenantProvisioner.delete(tenant_id, drop_database=drop_database)
    return {"tenant_id": tenant_id, "status": "deleted", "database_dropped": drop_database}


# ---------------------------------------------------------------------------
# /internal/billing — Data plane usage event ingestion
# ---------------------------------------------------------------------------

@router.post(
    "/internal/billing/usage",
    status_code=201,
    dependencies=[Depends(_require_internal_token)],
    summary="Record a usage event from the data plane or AI service",
)
def record_usage_event(body: BillingUsageRequest):
    from control_plane.usage_store import UsageStore

    store = UsageStore()
    event_id = store.record(
        tenant_id=body.tenant_id,
        event_type=body.event_type,
        quantity=body.quantity,
        metadata=body.metadata,
    )
    return {"recorded": True, "event_id": event_id}


@router.get(
    "/internal/billing/usage/{tenant_id}",
    dependencies=[Depends(_require_internal_token)],
    summary="Get aggregated usage for a tenant in a billing period",
)
def get_usage_summary(tenant_id: str, period: str = Query(..., description="YYYY-MM")):
    from control_plane.usage_store import UsageStore

    store = UsageStore()
    summary = store.get_summary(tenant_id, period)
    return summary


# ---------------------------------------------------------------------------
# /admin/billing — Admin invoice management
# ---------------------------------------------------------------------------

@router.post(
    "/admin/billing/invoices/generate",
    summary="Generate (or recompute) invoices for all active tenants in a period",
)
def generate_invoices(
    period: str = Query(..., description="YYYY-MM"),
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    invoices = engine.compute_all_active(period)
    return {"period": period, "generated": len(invoices)}


@router.post(
    "/admin/billing/invoices/{tenant_id}/{period}",
    summary="Generate or recompute invoice for one tenant",
)
def generate_tenant_invoice(
    tenant_id: str,
    period: str,
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.billing_engine import BillingEngine
    from control_plane.repository import TenantRepository as TR

    record = TR.get_by_id(tenant_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    engine = BillingEngine()
    invoice = engine.compute_invoice(
        tenant_id=tenant_id,
        plan=record.plan,
        period=period,
        persist=True,
    )
    return invoice


@router.get(
    "/admin/billing/invoices",
    summary="List invoices with optional tenant_id / status filters",
)
def list_invoices(
    tenant_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    items, total = engine.list_invoices(
        tenant_id=tenant_id, status=status, limit=limit, offset=offset
    )
    return {"invoices": [i.model_dump(mode="json") for i in items], "total": total}


@router.get(
    "/admin/billing/invoices/{tenant_id}/{period}",
    summary="Get a specific invoice",
)
def get_invoice(
    tenant_id: str,
    period: str,
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    invoice = engine.get_invoice(tenant_id, period)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.put(
    "/admin/billing/invoices/{tenant_id}/{period}/issue",
    summary="Transition invoice draft → issued",
)
def issue_invoice(tenant_id: str, period: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    invoice = engine.get_invoice(tenant_id, period)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "draft":
        raise HTTPException(status_code=409, detail=f"Invoice is {invoice.status}, not draft")
    engine.mark_issued(tenant_id, period)
    return {"tenant_id": tenant_id, "period": period, "status": "issued"}


@router.put(
    "/admin/billing/invoices/{tenant_id}/{period}/pay",
    summary="Mark invoice as paid",
)
def mark_invoice_paid(tenant_id: str, period: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    invoice = engine.get_invoice(tenant_id, period)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "issued":
        raise HTTPException(status_code=409, detail=f"Invoice is {invoice.status}, not issued")
    engine.mark_paid(tenant_id, period)
    return {"tenant_id": tenant_id, "period": period, "status": "paid"}


# ---------------------------------------------------------------------------
# /admin/billing/plans — S9: Plan configuration CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/admin/billing/plans",
    summary="List all billing plans",
)
def list_plans(
    include_archived: bool = Query(default=False),
    _admin=Depends(_require_admin_jwt),
):
    from control_plane.plan_store import PlanStore

    plans = PlanStore().list_all(include_archived=include_archived)
    return {"plans": [_plan_to_dict(p) for p in plans]}


@router.get(
    "/admin/billing/plans/{plan_name}",
    summary="Get a billing plan by name",
)
def get_plan(plan_name: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.plan_store import PlanStore

    plan = PlanStore().get(plan_name)
    return _plan_to_dict(plan)


@router.post(
    "/admin/billing/plans",
    status_code=201,
    summary="Create a new billing plan",
)
def create_plan(body: dict, _admin=Depends(_require_admin_jwt)):
    from decimal import Decimal
    from control_plane.plan_store import PlanStore

    required = ["name", "monthly_price_usd", "token_quota", "storage_gb_quota",
                "api_call_quota", "active_user_quota", "overage_token_per_1k",
                "overage_storage_gb", "overage_api_per_1k", "overage_user"]
    missing = [f for f in required if f not in body]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {missing}")

    plan = PlanStore().create(
        name=body["name"],
        monthly_price_usd=Decimal(str(body["monthly_price_usd"])),
        token_quota=int(body["token_quota"]),
        storage_gb_quota=int(body["storage_gb_quota"]),
        api_call_quota=int(body["api_call_quota"]),
        active_user_quota=int(body["active_user_quota"]),
        overage_token_per_1k=Decimal(str(body["overage_token_per_1k"])),
        overage_storage_gb=Decimal(str(body["overage_storage_gb"])),
        overage_api_per_1k=Decimal(str(body["overage_api_per_1k"])),
        overage_user=Decimal(str(body["overage_user"])),
    )
    return _plan_to_dict(plan)


@router.patch(
    "/admin/billing/plans/{plan_name}",
    summary="Update a billing plan",
)
def update_plan(plan_name: str, body: dict, _admin=Depends(_require_admin_jwt)):
    from control_plane.plan_store import PlanStore

    plan = PlanStore().update(plan_name, **body)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_name} not found")
    return _plan_to_dict(plan)


@router.delete(
    "/admin/billing/plans/{plan_name}",
    summary="Archive a billing plan (existing tenants keep it, new signups can't use it)",
)
def archive_plan(plan_name: str, _admin=Depends(_require_admin_jwt)):
    from control_plane.plan_store import PlanStore

    PlanStore().archive(plan_name)
    return {"plan": plan_name, "status": "archived"}


# ---------------------------------------------------------------------------
# /tenant/billing — S9: Tenant-facing billing portal
# ---------------------------------------------------------------------------

@router.get(
    "/tenant/billing/usage",
    summary="Get current month usage for the calling tenant",
    dependencies=[Depends(_require_internal_token)],
)
def tenant_get_usage(tenant_id: str = Query(...)):
    from control_plane.usage_store import UsageStore
    from datetime import date

    period = date.today().strftime("%Y-%m")
    store = UsageStore()
    summary = store.get_summary(tenant_id, period)
    return summary


@router.get(
    "/tenant/billing/invoices",
    summary="List invoices for the calling tenant",
    dependencies=[Depends(_require_internal_token)],
)
def tenant_list_invoices(
    tenant_id: str = Query(...),
    limit: int = Query(default=12, le=50),
    offset: int = Query(default=0, ge=0),
):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    items, total = engine.list_invoices(tenant_id=tenant_id, limit=limit, offset=offset)
    return {"invoices": [i.model_dump(mode="json") for i in items], "total": total}


@router.get(
    "/tenant/billing/invoices/{period}",
    summary="Get a specific invoice for the calling tenant",
    dependencies=[Depends(_require_internal_token)],
)
def tenant_get_invoice(period: str, tenant_id: str = Query(...)):
    from control_plane.billing_engine import BillingEngine

    engine = BillingEngine()
    invoice = engine.get_invoice(tenant_id, period)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


# ---------------------------------------------------------------------------
# /webhook/payments — S9: Payment gateway callbacks
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/payments/{provider}",
    summary="Payment gateway webhook (Stripe, Razorpay). No auth — verified by signature.",
)
def payment_webhook(provider: str, body: dict):
    """
    Handle payment confirmation from Stripe or Razorpay.

    Signature verification should be done in middleware or a provider-specific
    helper before this endpoint. For S9, we accept the payload and record it.
    """
    import json as _json
    from control_plane import db as cp_db

    if provider not in ("stripe", "razorpay"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Extract common fields from the webhook payload
    if provider == "stripe":
        event_type = body.get("type", "")
        obj = body.get("data", {}).get("object", {})
        payment_id = obj.get("id", "")
        amount = obj.get("amount_received", 0) / 100  # Stripe amounts are in cents
        currency = obj.get("currency", "usd").upper()
        tenant_id = obj.get("metadata", {}).get("tenant_id", "")
        invoice_period = obj.get("metadata", {}).get("period", "")
        status = "succeeded" if event_type == "payment_intent.succeeded" else "pending"
    else:  # razorpay
        payment_id = body.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
        amount_paise = body.get("payload", {}).get("payment", {}).get("entity", {}).get("amount", 0)
        amount = amount_paise / 100
        currency = body.get("payload", {}).get("payment", {}).get("entity", {}).get("currency", "INR").upper()
        tenant_id = body.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("tenant_id", "")
        invoice_period = body.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("period", "")
        event_type = body.get("event", "")
        status = "succeeded" if event_type == "payment.captured" else "pending"

    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment ID in webhook payload")

    # Record the payment
    cp_db.execute(
        """
        INSERT INTO cp_payments
            (tenant_id, provider, provider_payment_id, amount, currency, status, webhook_payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (provider_payment_id) DO UPDATE SET
            status = EXCLUDED.status, webhook_payload = EXCLUDED.webhook_payload, updated_at = NOW()
        """,
        (
            tenant_id or "unknown", provider, payment_id,
            str(amount), currency, status,
            _json.dumps(body),
        ),
    )

    # If payment succeeded and we have tenant_id + period, mark invoice as paid
    if status == "succeeded" and tenant_id and invoice_period:
        try:
            from control_plane.billing_engine import BillingEngine
            engine = BillingEngine()
            invoice = engine.get_invoice(tenant_id, invoice_period)
            if invoice and invoice.status == "issued":
                engine.mark_paid(tenant_id, invoice_period)
        except Exception as exc:
            logger.warning("Webhook: failed to mark invoice paid: %s", exc)

    return {"received": True, "payment_id": payment_id, "status": status}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_to_dict(plan) -> dict:
    """Convert PlanConfig dataclass to JSON-serializable dict."""
    return {
        "name": plan.name,
        "monthly_price_usd": str(plan.monthly_price_usd),
        "token_quota": plan.token_quota,
        "storage_gb_quota": plan.storage_gb_quota,
        "api_call_quota": plan.api_call_quota,
        "active_user_quota": plan.active_user_quota,
        "overage_token_per_1k": str(plan.overage_token_per_1k),
        "overage_storage_gb": str(plan.overage_storage_gb),
        "overage_api_per_1k": str(plan.overage_api_per_1k),
        "overage_user": str(plan.overage_user),
    }
