"""
ALIS Audit Ledger API Router — E00-S02

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Orchestration (FastAPI)
ENTITY: AuditLedger

Exposes the Immutable Audit Ledger's verification and export
capabilities as REST endpoints.

Endpoints:
    GET /api/v1/audit/verify   — Hash chain verification
    GET /api/v1/audit/export   — Admin ledger export (JSON / CSV)

Must Align With:
    - E00-S02 Acceptance Criteria: Hash chain verification endpoint,
      Admin export capability
    - Layer 5: Only ADMIN / SUPER_ADMIN may access these endpoints
      (enforced via RBAC+ Permission.AUDIT_LOG_READ)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from server.core.audit import AuditLedger
from server.core.rbac import Permission, require_permission
from server.core.schema import TimelineEvent
from server.core.security import get_current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ============================================================================
# GET /api/v1/audit/verify  —  Hash Chain Verification
# ============================================================================


@router.get("/verify")
@require_permission(Permission.AUDIT_LOG_READ)
async def verify_audit_chain(request: Request) -> JSONResponse:
    """
    Walk the entire hash chain for the current tenant and verify
    every link.

    Returns:
        200: { "valid": bool, "total_entries": int,
               "first_invalid_id": int | null, "message": str }

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()
    result = AuditLedger.verify_chain_integrity(tenant_id)

    status_code = 200 if result["valid"] else 409  # 409 Conflict on tamper
    return JSONResponse(content=result, status_code=status_code)


# ============================================================================
# GET /api/v1/audit/export  —  Admin Ledger Export
# ============================================================================


@router.get("/export")
@require_permission(Permission.AUDIT_LOG_READ)
async def export_audit_ledger(
    request: Request,
    fmt: str = Query(
        default="json",
        description="Export format: 'json' or 'csv'.",
        pattern="^(json|csv)$",
    ),
    start_time: str | None = Query(
        default=None,
        description="ISO-8601 lower-bound filter (e.g. 2025-01-01T00:00:00Z).",
    ),
    end_time: str | None = Query(
        default=None,
        description="ISO-8601 upper-bound filter.",
    ),
) -> Response:
    """
    Export the audit ledger for the current tenant.

    Returns:
        200: Full ledger export as JSON or CSV.

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()

    # Parse optional datetime filters
    parsed_start = _parse_iso(start_time) if start_time else None
    parsed_end = _parse_iso(end_time) if end_time else None

    export_str = AuditLedger.export_ledger(
        tenant_id=tenant_id,
        fmt=fmt,
        start_time=parsed_start,
        end_time=parsed_end,
    )

    if fmt == "csv":
        return Response(
            content=export_str,
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=audit_ledger_{tenant_id}.csv"
                )
            },
        )

    # Default: JSON
    return Response(
        content=export_str,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=audit_ledger_{tenant_id}.json"
            )
        },
    )


# ============================================================================
# GET /api/v1/audit/logs  —  Audit Ledger Query
# ============================================================================


@router.get("/logs")
@require_permission(Permission.AUDIT_LOG_READ)
async def get_audit_logs(
    request: Request,
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    entity_id: str | None = Query(None, description="Filter by entity ID"),
    action: str | None = Query(
        None, description="Filter by action (e.g. login, create)"
    ),
    limit: int = Query(50, le=500, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> JSONResponse:
    """
    Query the audit ledger for the current tenant.

    Returns:
        200: List of audit entries (JSON).

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()

    logs = AuditLedger.query(
        tenant_id=tenant_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        limit=limit,
        offset=offset,
    )

    # Convert AuditEntry objects to dicts for JSON serialization
    serialized = []
    for entry in logs:
        serialized.append(
            {
                "id": entry.id,
                "tenant_id": entry.tenant_id,
                "actor_id": entry.actor_id,
                "actor_role": entry.actor_role,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "metadata": entry.metadata,
                "timestamp": entry.timestamp.isoformat(),
                "previous_hash": entry.previous_hash,
                "hash": entry.hash,
            }
        )

    return JSONResponse(content=serialized)


# ============================================================================
# GET /api/v1/audit/timeline/{entity_type}/{entity_id}  —  Entity Timeline
# ============================================================================

# Map AuditAction values → (human label, color, icon)
_ACTION_STYLE: dict = {
    # Auth
    "login": ("Logged In", "blue", "user"),
    "logout": ("Logged Out", "muted", "user"),
    "access_denied": ("Access Denied", "red", "lock"),
    # CRUD
    "create": ("Record Created", "green", "check"),
    "update": ("Record Updated", "blue", "edit"),
    "delete": ("Record Deleted", "red", "trash"),
    # State & Events
    "state_transition": ("Status Changed", "blue", "arrow"),
    "event_published": ("Event Published", "muted", "broadcast"),
    # AI
    "ai_invocation": ("AI Analysis Run", "blue", "ai"),
    "agent_execution": ("Agent Executed", "blue", "ai"),
    "agent_decision": ("Agent Decision Made", "blue", "ai"),
    "ai_prompt_injection": ("Injection Attempt Blocked", "red", "shield"),
    "ai_schema_rejected": ("AI Output Rejected", "amber", "alert"),
    "guardrail_blocked": ("Guardrail Blocked Output", "red", "shield"),
    "guardrail_warning": ("Guardrail Warning", "amber", "alert"),
    "hitl_review_required": ("Sent for Human Review", "amber", "clock"),
    "hitl_auto_proceed": ("Auto-Proceeded (HITL Waived)", "green", "check"),
    # Policy Engine (Phase A)
    "policy_evaluated": ("Policy Evaluated", "blue", "balance"),
    "policy_drafted": ("Policy Drafted", "muted", "edit"),
    "policy_submitted": ("Policy Submitted for Approval", "amber", "clock"),
    "policy_approved": ("Policy Approved", "green", "check"),
    "policy_activated": ("Policy Activated", "green", "check"),
    # Approvals
    "override_requested": ("Override Requested", "amber", "alert"),
    "override_approved": ("Override Approved", "amber", "alert"),
    "override_rejected": ("Override Rejected", "red", "alert"),
    "override_executed": ("Override Executed", "amber", "alert"),
    # Escalation
    "escalation_requested": ("Escalation Requested", "amber", "arrow"),
    "escalation_granted": ("Escalation Granted", "amber", "arrow"),
    "escalation_denied": ("Escalation Denied", "red", "lock"),
    # Lockdown
    "lockdown_activated": ("System Lockdown Activated", "red", "lock"),
    "lockdown_deactivated": ("Lockdown Lifted", "green", "check"),
    # Selective auto-execution (Phase D)
    "auto_executed": ("Auto-Executed by Policy", "green", "zap"),
    # Prompts
    "prompt_created": ("Prompt Created", "muted", "edit"),
    "prompt_activated": ("Prompt Activated", "green", "check"),
    # Data
    "field_change": ("Field Changed", "muted", "edit"),
    "archive": ("Record Archived", "muted", "trash"),
    "sensitive_access": ("Sensitive Data Accessed", "amber", "shield"),
}

_DEFAULT_STYLE = ("Activity Recorded", "muted", "clock")


def _format_label(entry) -> str:
    """Build a detailed label from the raw action + metadata."""
    base_label, _, _ = _ACTION_STYLE.get(entry.action, _DEFAULT_STYLE)
    meta = entry.metadata or {}

    # Enrich label with policy context when available
    if entry.action == "policy_evaluated":
        pid = meta.get("policy_id", "")
        ver = meta.get("policy_version")
        verdict = meta.get("verdict", "")
        rule = meta.get("rule_id")
        parts = [f"Policy Evaluated: {pid}"]
        if verdict:
            parts[0] += f" → {verdict}"
        if ver:
            detail = f"v{ver}"
            if rule:
                detail += f", Rule {rule}"
            parts.append(f"({detail})")
        return " ".join(parts)

    if entry.action == "state_transition":
        from_s = meta.get("from_state", "")
        to_s = meta.get("to_state", "")
        if from_s and to_s:
            return f"Status: {from_s} → {to_s}"

    if entry.action in ("auto_executed",):
        policy_id = meta.get("policy_id", "")
        return f"Auto-Executed by Policy ({policy_id})" if policy_id else base_label

    return base_label


@router.get("/timeline/{entity_type}/{entity_id}")
@require_permission(Permission.AUDIT_LOG_READ)
async def get_entity_timeline(
    entity_type: str,
    entity_id: str,
    request: Request,
    limit: int = Query(200, le=500, description="Max timeline entries"),
) -> JSONResponse:
    """
    Return the full activity timeline for a single entity.

    Maps every AuditLedger entry for (entity_type, entity_id) to a
    human-readable TimelineEvent with pre-computed label, color, and icon.
    Sorted chronologically (oldest first) for display.

    Example:
        GET /api/v1/audit/timeline/application/APP-2026-000001
        GET /api/v1/audit/timeline/policy/attendance_eligibility

    Access:
        Requires ``audit_log:read`` permission (ADMIN, SUPER_ADMIN).
    """
    tenant_id = get_current_tenant_id()

    entries = AuditLedger.query(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )

    # Sort oldest-first for timeline display
    entries_sorted = sorted(entries, key=lambda e: e.timestamp)

    events = []
    for entry in entries_sorted:
        _, color, icon = _ACTION_STYLE.get(entry.action, _DEFAULT_STYLE)
        meta = entry.metadata or {}
        events.append(
            TimelineEvent(
                id=entry.id,
                timestamp=entry.timestamp.isoformat(),
                action=entry.action,
                label=_format_label(entry),
                actor_id=entry.actor_id,
                actor_role=entry.actor_role,
                color=color,
                icon=icon,
                metadata=meta,
                formatted_detail=meta.get("formatted"),
            ).model_dump()
        )

    return JSONResponse(content=events)


# ============================================================================
# HELPERS
# ============================================================================


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
