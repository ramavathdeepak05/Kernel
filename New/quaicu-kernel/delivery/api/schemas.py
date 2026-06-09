"""Pydantic request/response schemas for the QUAICU Kernel REST API.

All schemas are versioned under /v1. Breaking changes require a new major version.
Pydantic v2 is required.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────────


class ProposeRequest(BaseModel):
    """Body for POST /v1/actions/propose."""

    type: str = Field(..., description="Action type (e.g. 'ciro.ifrs9.stage_transition')")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action payload")
    idempotency_key: str = Field(..., description="Caller-supplied idempotency key (UUID recommended)")
    actor_id: str = Field(..., description="Actor identity (sub claim or user id)")
    actor_roles: list[str] = Field(default_factory=list, description="Actor roles")


class ApproveRequest(BaseModel):
    """Body for POST /v1/actions/{action_id}/approve."""

    approver_ref: str = Field(..., description="Approver reference, e.g. 'user:alice' or 'role:risk_head'")
    decision: str = Field("approved", description="'approved' or 'rejected'")


# ── Response schemas ──────────────────────────────────────────────────────────────


class ActionResponse(BaseModel):
    """Response for propose and action status endpoints."""

    action_id: str
    state: str
    type: str
    tenant: str
    actor_id: str


class LedgerEntryResponse(BaseModel):
    """One sealed ledger entry."""

    ledger_seq: int
    action_id: str
    action_type: str
    actor_id: str
    decision: str
    policy_versions: list[str]
    sealed_at: str  # ISO 8601
    approver: str | None = None


class LedgerTrailResponse(BaseModel):
    """Response for GET /v1/ledger/{tenant}/trail."""

    tenant: str
    entries: list[LedgerEntryResponse]
    count: int


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)
