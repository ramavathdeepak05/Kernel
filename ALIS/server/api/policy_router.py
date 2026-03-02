"""
ALIS Policy Governance API Router — E00-S09

Exposes the Policy Governance Service via RESTful endpoints.

Endpoints:
    POST /policy/draft     — Create a new policy draft
    POST /policy/submit    — Submit a draft for approval
    POST /policy/approve   — Approve a submitted policy
    GET  /policy/{id}      — Retrieve a policy (with optional temporal query)
    GET  /policy/          — List policies (with optional filters)
    GET  /policy/type/{t}  — Get active policy by type (Rule Engine API)
    GET  /policy/history/{t} — Version history for diff viewer

All endpoints enforce RBAC via the standard middleware pattern.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.core.policy_service import PolicyService, PolicyStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/policy", tags=["Policy Governance (E00-S09)"])


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class PolicyDraftRequest(BaseModel):
    """Request body for creating a policy draft."""
    policy_type: str = Field(..., min_length=1, max_length=100,
                             description="Category (e.g., 'attendance_threshold')")
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    parameters: Dict[str, Any] = Field(..., description="Structured JSON parameters")
    effective_from: datetime = Field(..., description="When the policy becomes applicable")
    effective_to: Optional[datetime] = Field(None, description="When the policy expires")
    module: Optional[str] = Field(None, description="Owning module (e.g., 'm1', 'm4')")


class PolicyActionRequest(BaseModel):
    """Request body for submit / approve actions."""
    policy_id: str = Field(..., description="ID of the policy to act on")


class PolicyResponse(BaseModel):
    """Standard response for policy mutations."""
    id: str
    status: str
    policy_type: Optional[str] = None
    version: Optional[int] = None
    name: Optional[str] = None
    content_hash: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/draft", response_model=PolicyResponse)
async def create_draft(body: PolicyDraftRequest):
    """
    POST /policy/draft

    Create a new policy draft. Requires POLICY_DRAFT permission.

    The caller must provide structured parameters, effective dates,
    and a policy type.  A version number is auto-assigned.
    """
    try:
        # TODO: Extract actor_id, actor_role, tenant_id from request.state
        # once auth middleware is connected.  Using placeholders for now.
        result = PolicyService.create_draft(
            policy_type=body.policy_type,
            name=body.name,
            description=body.description,
            parameters=body.parameters,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
            created_by="actor_placeholder",
            actor_role="admin",
            tenant_id="default_tenant",
            module=body.module,
        )
        return PolicyResponse(**result)
    except Exception as e:
        logger.error(f"Failed to create policy draft: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/submit", response_model=PolicyResponse)
async def submit_for_approval(body: PolicyActionRequest):
    """
    POST /policy/submit

    Submit a DRAFT policy for approval. Requires POLICY_SUBMIT permission.
    The policy is locked from further edits after submission.
    """
    try:
        result = PolicyService.submit_for_approval(
            policy_id=body.policy_id,
            submitted_by="actor_placeholder",
            actor_role="admin",
            tenant_id="default_tenant",
        )
        return PolicyResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve", response_model=PolicyResponse)
async def approve_policy(body: PolicyActionRequest):
    """
    POST /policy/approve

    Approve a SUBMITTED policy. Requires POLICY_APPROVE permission
    (ADMIN / SUPER_ADMIN only).

    If effective_from <= now, the policy is auto-activated and a
    PolicyActivated event is emitted.
    """
    try:
        result = PolicyService.approve_policy(
            policy_id=body.policy_id,
            approved_by="actor_placeholder",
            actor_role="admin",
            tenant_id="default_tenant",
        )
        return PolicyResponse(**result)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{policy_id}")
async def get_policy(
    policy_id: str,
    date: Optional[datetime] = Query(None, description="Temporal query — returns the version active on this date"),
):
    """
    GET /policy/{policy_id}?date=

    Retrieve a policy by ID.  If `date` is provided, returns the
    version of the same policy_type that was active on that date.

    This is the READ-ONLY API consumed by the Rule Engine.
    """
    try:
        result = PolicyService.get_policy(
            policy_id=policy_id,
            tenant_id="default_tenant",
            as_of_date=date,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/type/{policy_type}")
async def get_active_by_type(
    policy_type: str,
    date: Optional[datetime] = Query(None, description="Point-in-time resolution"),
):
    """
    GET /policy/type/{policy_type}?date=

    Rule Engine convenience endpoint.  Returns the currently active
    policy for the given type.
    """
    try:
        result = PolicyService.get_active_policy_by_type(
            policy_type=policy_type,
            tenant_id="default_tenant",
            as_of_date=date,
        )
        if not result:
            raise HTTPException(status_code=404, detail="No active policy found for this type.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve active policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_policies(
    policy_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    GET /policy/

    List policies with optional filters. Requires POLICY_READ permission.
    """
    try:
        status_enum = PolicyStatus(status) if status else None
        results = PolicyService.list_policies(
            tenant_id="default_tenant",
            policy_type=policy_type,
            status=status_enum,
            limit=limit,
            offset=offset,
        )
        return {"policies": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Failed to list policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{policy_type}")
async def get_version_history(policy_type: str):
    """
    GET /policy/history/{policy_type}

    Return all versions of a policy type for the admin UI diff viewer.
    """
    try:
        results = PolicyService.get_version_history(
            policy_type=policy_type,
            tenant_id="default_tenant",
        )
        return {"versions": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Failed to retrieve version history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
