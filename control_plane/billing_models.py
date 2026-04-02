"""
Billing Models — S4

Pydantic schemas + plan configuration for the ALIS billing engine.

Plans define:
  - Monthly base price (USD)
  - Included token quota (from AI service budget)
  - Included storage (GB, for MinIO tenant bucket)
  - Included API call quota (requests/month)
  - Per-unit overage prices

Usage events are write-once records emitted by the data plane and AI service.
Invoices are generated monthly by the BillingEngine Beat task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Plan definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanConfig:
    name: str
    monthly_price_usd: Decimal          # base subscription fee
    token_quota: int                     # included AI tokens/month
    storage_gb_quota: int               # included object storage (GB)
    api_call_quota: int                 # included API calls/month
    active_user_quota: int              # included monthly active users
    # Overage — cost per additional unit beyond quota
    overage_token_per_1k: Decimal       # $/1K tokens
    overage_storage_gb: Decimal         # $/GB/month
    overage_api_per_1k: Decimal         # $/1K calls
    overage_user: Decimal               # $/extra user/month


PLAN_CONFIGS: Dict[str, PlanConfig] = {
    "starter": PlanConfig(
        name="starter",
        monthly_price_usd=Decimal("49.00"),
        token_quota=100_000,
        storage_gb_quota=5,
        api_call_quota=50_000,
        active_user_quota=25,
        overage_token_per_1k=Decimal("0.50"),
        overage_storage_gb=Decimal("0.10"),
        overage_api_per_1k=Decimal("0.20"),
        overage_user=Decimal("2.00"),
    ),
    "growth": PlanConfig(
        name="growth",
        monthly_price_usd=Decimal("199.00"),
        token_quota=1_000_000,
        storage_gb_quota=50,
        api_call_quota=500_000,
        active_user_quota=250,
        overage_token_per_1k=Decimal("0.30"),
        overage_storage_gb=Decimal("0.08"),
        overage_api_per_1k=Decimal("0.15"),
        overage_user=Decimal("1.50"),
    ),
    "enterprise": PlanConfig(
        name="enterprise",
        monthly_price_usd=Decimal("999.00"),
        token_quota=10_000_000,
        storage_gb_quota=500,
        api_call_quota=5_000_000,
        active_user_quota=2500,
        overage_token_per_1k=Decimal("0.10"),
        overage_storage_gb=Decimal("0.05"),
        overage_api_per_1k=Decimal("0.05"),
        overage_user=Decimal("1.00"),
    ),
}


# ---------------------------------------------------------------------------
# Usage event types
# ---------------------------------------------------------------------------

class UsageEventType(str, Enum):
    AI_TOKENS    = "ai_tokens"       # tokens consumed (unit: tokens)
    API_CALLS    = "api_calls"       # HTTP requests (unit: requests)
    STORAGE_GB   = "storage_gb"      # object storage snapshot (unit: GB·hours → normalised to GB/month)
    ACTIVE_USERS = "active_users"    # monthly active user count snapshot (unit: users)


# ---------------------------------------------------------------------------
# Pydantic I/O models
# ---------------------------------------------------------------------------

class UsageEventIn(BaseModel):
    """Emitted by data plane or AI service via POST /billing/usage."""
    tenant_id: str
    event_type: UsageEventType
    quantity: Decimal = Field(ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UsageEventRecord(BaseModel):
    """Stored usage event (DB row)."""
    id: int
    tenant_id: str
    event_type: str
    quantity: Decimal
    metadata: Dict[str, Any]
    recorded_at: datetime


class UsageSummary(BaseModel):
    """Aggregated usage for a tenant in a billing period."""
    tenant_id: str
    period: str                   # "YYYY-MM"
    ai_tokens: int = 0
    api_calls: int = 0
    storage_gb: Decimal = Decimal("0")
    active_users: int = 0


class InvoiceLineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class Invoice(BaseModel):
    id: Optional[int] = None
    tenant_id: str
    period: str                   # "YYYY-MM"
    period_start: date
    period_end: date
    plan: str
    line_items: List[InvoiceLineItem]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    currency: str = "USD"
    status: str = "draft"         # draft | issued | paid | void
    created_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None


class BillingUsageRequest(BaseModel):
    """Request body for POST /billing/usage."""
    tenant_id: str
    event_type: UsageEventType
    quantity: Decimal = Field(ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvoiceListResponse(BaseModel):
    invoices: List[Invoice]
    total: int
