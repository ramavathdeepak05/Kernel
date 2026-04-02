"""
Control Plane Pydantic Models — S2

Request/response schemas for the control plane HTTP API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Tenant lifecycle
# ---------------------------------------------------------------------------

class TenantProvisionRequest(BaseModel):
    """Body for POST /admin/tenants — provision a new tenant."""

    subdomain: str = Field(
        ...,
        min_length=3,
        max_length=63,
        description="Subdomain slug (e.g. 'iitb'). Becomes iitb.alis.app. Must be lowercase alphanumeric + hyphens.",
        pattern=r"^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$",
    )
    display_name: str = Field(..., min_length=2, max_length=255)
    region: str = Field(default="in-central")
    plan: str = Field(default="starter")
    feature_flags: Dict[str, Any] = Field(default_factory=dict)

    # Optional: override DB location (enterprise Tier 2 brings own DB)
    db_host: Optional[str] = Field(default=None)
    db_port: Optional[int] = Field(default=None)
    db_user: Optional[str] = Field(default=None)
    db_password: Optional[str] = Field(default=None)

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        allowed = {"starter", "growth", "enterprise"}
        if v not in allowed:
            raise ValueError(f"plan must be one of {allowed}")
        return v

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        allowed = {"in-central", "in-south", "uae-north", "eu-west", "us-east"}
        if v not in allowed:
            raise ValueError(f"region must be one of {allowed}")
        return v


class TenantUpdateRequest(BaseModel):
    """Body for PATCH /admin/tenants/{tenant_id}."""

    display_name: Optional[str] = None
    plan: Optional[str] = None
    feature_flags: Optional[Dict[str, Any]] = None
    region: Optional[str] = None


class TenantRecord(BaseModel):
    """Full tenant record returned by /internal and /admin endpoints."""

    tenant_id: str
    subdomain: str
    display_name: str
    region: str
    db_url: str           # full DSN (asyncpg — used by TenantRegistry)
    db_url_sync: str      # full DSN (psycopg2 — used by Celery)
    plan: str
    feature_flags: Dict[str, Any]
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None


class TenantSummary(BaseModel):
    """Lightweight record for list endpoints."""

    tenant_id: str
    subdomain: str
    display_name: str
    region: str
    plan: str
    status: str
    created_at: Optional[datetime] = None


class TenantListResponse(BaseModel):
    items: List[TenantSummary]
    total: int


class ProvisionResponse(BaseModel):
    tenant_id: str
    subdomain: str
    status: str
    message: str


class CacheInvalidateRequest(BaseModel):
    """Body for POST /internal/tenants/{tenant_id}/invalidate-cache."""
    subdomain: Optional[str] = None
