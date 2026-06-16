"""AI-assisted CEL policy drafting (K·01 helper).

POST /v1/policies/assist → 200 — drafts a candidate CEL policy from a plain-English rule, validated by
real compilation. Advisory only: the returned draft still goes through the normal
DRAFT→REVIEW→backtest→ACTIVATE lifecycle (`/v1/policies`). Returns 503 when no assistant is wired.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.account.scopes import POLICY_ADMIN
from delivery.api.auth import enforce_scope
from delivery.api.deps import get_request_tenant

router = APIRouter(prefix="/v1/policies", tags=["policies"])


class AssistRequest(BaseModel):
    description: str = Field(..., description="Plain-English rule to express as a CEL policy.")
    action_types: list[str] | None = Field(None, description="Known action types to target.")
    payload_fields: list[str] | None = Field(None, description="Known payload field names (unprefixed).")
    actor_roles: list[str] | None = Field(None, description="Known actor roles, e.g. 'role:analyst'.")


class AssistResponse(BaseModel):
    condition: str
    decision: str
    explanation: str
    valid: bool = Field(..., description="True if the suggested CEL compiles against the engine.")
    error: str | None = None
    warnings: list[str] = []


@router.post(
    "/assist",
    response_model=AssistResponse,
    summary="AI-assisted CEL policy drafting (advisory; review before activating)",
)
async def assist(body: AssistRequest, request: Request) -> AssistResponse:
    assistant = getattr(request.app.state, "policy_assistant", None)
    if assistant is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Policy assistant is not enabled on this deployment", "code": "ASSISTANT_DISABLED"},
        )
    enforce_scope(request, POLICY_ADMIN)  # no-op when API-key auth is disabled
    tenant = get_request_tenant(request)
    suggestion = await assistant.suggest(
        description=body.description,
        tenant=tenant,
        action_types=body.action_types,
        payload_fields=body.payload_fields,
        actor_roles=body.actor_roles,
    )
    return AssistResponse(
        condition=suggestion.condition,
        decision=suggestion.decision,
        explanation=suggestion.explanation,
        valid=suggestion.valid,
        error=suggestion.error,
        warnings=list(suggestion.warnings),
    )
