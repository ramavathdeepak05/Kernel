"""Pydantic request/response schemas for the QUAICU Kernel REST API.

All schemas are versioned under /v1. Breaking changes require a new major version.
Pydantic v2 is required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from core.types import Decision


# ── Request schemas ───────────────────────────────────────────────────────────────


class ProposeRequest(BaseModel):
    """Body for POST /v1/actions/propose.

    The actor is NEVER supplied by the caller: identity is resolved from the bearer token by the
    configured IdentityPort. There is intentionally no actor_id / actor_roles field.
    """

    type: str = Field(..., description="Action type (e.g. 'ciro.ifrs9.stage_transition')")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action payload")
    idempotency_key: str = Field(..., description="Caller-supplied idempotency key (UUID recommended)")


class ApproveRequest(BaseModel):
    """Body for POST /v1/actions/{action_id}/approve."""

    approver_ref: str = Field(..., description="Approver reference, e.g. 'user:alice' or 'role:risk_head'")
    decision: str = Field("approved", description="'approved' or 'rejected'")


class InferenceRequest(BaseModel):
    """Body for POST /v1/inference — a governed model call."""

    model_id: str = Field(..., description="Model id, e.g. 'gpt-4' or 'llama3'")
    model_version: str = Field("", description="Optional model version")
    prompt_text: str = Field(..., description="Raw prompt; PII is masked by the gateway before transmission")
    payload: dict[str, Any] = Field(default_factory=dict, description="Optional structured payload (sensitive fields masked)")
    idempotency_key: str = Field(..., description="Caller-supplied idempotency key (UUID recommended)")


# ── Response schemas ──────────────────────────────────────────────────────────────


class ActionResponse(BaseModel):
    """Response for propose and action status endpoints."""

    action_id: str
    state: str
    type: str
    tenant: str
    actor_id: str


class InferenceResponse(BaseModel):
    """Response for POST /v1/inference."""

    content: str
    model_id: str
    prompt_hash: str
    response_hash: str
    action_id: str
    state: str


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


class AuthorizeRequest(BaseModel):
    """Body for POST /v1/authorize — a pure policy-decision query.

    The actor is NEVER supplied by the caller; it is resolved from the bearer token. ``record``
    overrides the profile's ``seal_to_ledger`` flag: None = follow the profile (default all() seals
    every decision), True = always seal, False = never seal.
    """

    type: str = Field(..., description="Action type to authorize (e.g. 'payments.wire')")
    payload: dict[str, Any] = Field(default_factory=dict, description="Optional action payload")
    idempotency_key: str | None = Field(None, description="Optional caller-supplied key")
    record: bool | None = Field(None, description="Override whether to seal this decision to the ledger")


class AuthorizeResponse(BaseModel):
    """Response for POST /v1/authorize.

    Always returns 200 — the HTTP status never encodes the verdict. Check ``allowed`` or
    ``decision`` in the body. The caller is the enforcement point.
    """

    decision: str
    allowed: bool
    actor_id: str
    reason: str | None = None
    policy_versions: list[str] = Field(default_factory=list)
    approvers: list[str] = Field(default_factory=list)
    enforced_layers: list[str] = Field(default_factory=list)
    sealed: bool = False
    ledger_seq: int | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)


# ── Policy management (K·01 authoring API) ─────────────────────────────────────────

_VALID_DECISIONS = {d.value for d in Decision}


class PolicyRegisterRequest(BaseModel):
    """Body for POST /v1/policies — register a new policy version.

    The server always registers as DRAFT; there is intentionally no ``lifecycle`` field. Lifecycle
    advances only via the explicit submit / activate / deprecate endpoints.
    """

    id: str = Field(..., description="Policy id, dot-namespaced (e.g. 'ciro.ifrs9.stage_transition')")
    version: int = Field(..., ge=1, description="Monotonic version number (>= 1)")
    governs: str = Field(..., description="Action type this policy governs; '*' is a wildcard")
    scope: dict[str, str] = Field(..., description="e.g. {'tenant': '*'} or {'tenant': 'ciro-bank'}")
    condition: str = Field(..., description="CEL expression; compiled at registration")
    decision: str = Field(..., description="One of: allow | deny | require_approval")
    approvers: list[str] = Field(default_factory=list, description="Required only for require_approval")
    regulatory_refs: list[str] = Field(default_factory=list, description="K·14 regulation references")

    @field_validator("decision")
    @classmethod
    def _decision_is_valid(cls, v: str) -> str:
        normalized = v.lower()
        if normalized not in _VALID_DECISIONS:
            raise ValueError(f"decision must be one of {sorted(_VALID_DECISIONS)}, got {v!r}")
        return normalized

    @model_validator(mode="after")
    def _approvers_required_for_approval(self) -> "PolicyRegisterRequest":
        if self.decision == Decision.REQUIRE_APPROVAL.value and not self.approvers:
            raise ValueError("decision 'require_approval' requires a non-empty approvers list")
        return self


class ImpactReportRequest(BaseModel):
    """Body for PUT /v1/policies/{id}/versions/{v}/impact-report (and the inline activate report).

    ``policy_id`` / ``policy_version`` are taken from the URL path, not the body — this eliminates
    the mismatch class of F-10 errors entirely.
    """

    reviewed_by: str = Field(..., description="Reviewer identity (e.g. 'user:compliance_officer')")
    reviewed_at: datetime = Field(..., description="Review timestamp (ISO 8601)")
    decision_distribution: dict[str, float] = Field(default_factory=dict)
    flip_count: int = Field(0, ge=0)
    fairness_delta: float = 0.0
    acknowledged: bool = Field(..., description="Must be True to pass the F-10 activation gate")


class ActivateRequest(BaseModel):
    """Body for POST /v1/policies/{id}/versions/{v}/activate.

    Provide ``impact_report`` inline, or omit it to use a report previously uploaded via PUT.
    """

    impact_report: ImpactReportRequest | None = None


class PolicyResponse(BaseModel):
    """A policy envelope, sans the non-serialisable compiled condition."""

    id: str
    version: int
    governs: str
    scope: dict[str, str]
    condition: str
    decision: str
    approvers: list[str]
    regulatory_refs: list[str]
    lifecycle: str


class PolicyListResponse(BaseModel):
    """Response for the policy list / versions endpoints."""

    policies: list[PolicyResponse]
    count: int


class ImpactReportResponse(BaseModel):
    """An echo of a stored impact report."""

    policy_id: str
    policy_version: int
    reviewed_by: str
    reviewed_at: str  # ISO 8601
    decision_distribution: dict[str, float]
    flip_count: int
    fairness_delta: float
    acknowledged: bool
