"""
ALIS AI Gateway API Router — E03-S01

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Orchestration (FastAPI)
ENTITY: AIGateway

Exposes the centralized AI Gateway as a REST endpoint.
This is the ONLY API surface for AI invocations in ALIS.

Endpoints:
    POST /api/v1/ai/invoke         — Invoke a module-scoped AI agent
    GET  /api/v1/ai/agents/{module} — List registered agents for a module
    GET  /api/v1/ai/health          — AI subsystem health check

Must Align With:
    - E03-S01: Single API surface, RBAC-protected, tenant-aware
    - Blueprint B: AI Agent Architecture
    - Module-Scoped AI Agent Model v1.0
    - "Agents draft, rules decide"
    - "AI is read-only with respect to state"
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from server.agents.academics.registry import AcademicsAgentRegistry

# Module-scoped agent registries — import per module
from server.agents.admissions.registry import AdmissionsAgentRegistry
from server.agents.examinations.registry import ExaminationsAgentRegistry
from server.agents.finance.registry import FinanceAgentRegistry
from server.agents.hr_admin.registry import HRAdminAgentRegistry
from server.agents.rail.registry import RailAgentRegistry
from server.agents.regulatory.registry import RegulatoryAgentRegistry
from server.agents.research.registry import ResearchAgentRegistry
from server.agents.student_services.registry import StudentServicesAgentRegistry
from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)
from server.core.ai_observability import AIObservabilityService
from server.core.rbac import Permission, Role, require_permission

logger = logging.getLogger(__name__)

from server.core.backpressure import require_ai_capacity  # noqa: E402

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai-gateway"],
    dependencies=[],  # require_ai_capacity applied per-endpoint, not globally
)


# =============================================================================
# MODULE REGISTRY LOOKUP
# =============================================================================

# Maps module identifiers to their scoped agent registries.
# Each module maintains its own registry per the Module-Scoped Agent Model.
_MODULE_REGISTRIES: dict[str, Any] = {
    "M1": AdmissionsAgentRegistry,
    "M2": AcademicsAgentRegistry,
    "M3": ExaminationsAgentRegistry,
    "M4": FinanceAgentRegistry,
    "M5": HRAdminAgentRegistry,
    "M6": StudentServicesAgentRegistry,
    "M7": RegulatoryAgentRegistry,
    "M8": ResearchAgentRegistry,
    "RAIL": RailAgentRegistry,
}


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class AIInvokeRequest(BaseModel):
    """
    Request body for AI Gateway invocation.

    All fields required for tenant-aware, RBAC-protected, module-scoped
    AI agent invocation.
    """

    # Actor context
    actor_id: str = Field(
        ..., description="ID of the actor (user or system) requesting AI"
    )
    actor_role: str = Field(
        ..., description="Role of the actor (e.g., 'ai_agent', 'faculty')"
    )

    # Tenant context
    org_id: str = Field(..., description="Tenant/Organization ID for isolation")

    # Module & Agent targeting
    module: str = Field(..., description="Target module (e.g., 'M1' for Admissions)")
    agent_name: str = Field(
        ...,
        description="Name of the agent to invoke (e.g., 'eligibility_evaluator_v1')",
    )

    # Agent input
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Input payload for the agent (module-specific)",
    )

    # Optional
    wizard: str | None = Field(
        default=None, description="Wizard context (e.g., 'Eligibility Eval')"
    )
    correlation_id: str | None = Field(
        default=None, description="Correlation ID for distributed tracing"
    )
    model_override: str | None = Field(
        default=None, description="Optional LLM model override (e.g., 'qwen2.5')"
    )


class AIInvokeResponse(BaseModel):
    """
    Standardized response from the AI Gateway.

    All AI outputs are advisory — they propose decisions but never
    mutate system state.
    """

    success: bool
    request_id: str
    module: str
    agent_name: str
    model: str = ""
    latency_ms: float = 0.0

    # Agent output (always advisory / draft)
    content: str | None = None
    error: str | None = None

    # E00-S06: Structured output (when schema-validated)
    validated_output: dict[str, Any] | None = None


class AgentListResponse(BaseModel):
    """Response listing available agents for a module."""

    module: str
    agents: list


# =============================================================================
# POST /api/v1/ai/invoke — Central AI Invocation Endpoint
# =============================================================================


@router.post(
    "/invoke",
    response_model=AIInvokeResponse,
    dependencies=[Depends(require_ai_capacity)],
)
@require_permission(Permission.AI_INVOKE)
async def invoke_ai_agent(request: Request, body: AIInvokeRequest) -> JSONResponse:
    """
    Invoke a module-scoped AI agent through the centralized gateway.

    This is the ONLY authorized entry point for AI invocations in ALIS.

    Flow:
        1. Validate module exists in registry
        2. Validate agent exists in module registry
        3. Build AIGatewayContext (tenant + RBAC context)
        4. Execute agent via module registry
        5. Return structured response

    Constraints:
        - RBAC: Requires AI_INVOKE permission
        - Tenant: org_id is mandatory for isolation
        - Module-scoped: Agent must belong to target module
        - Read-only: AI output is always advisory
    """
    # --- Step 1: Validate module ---
    registry = _MODULE_REGISTRIES.get(body.module)
    if registry is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": "ERR_AI_MODULE_NOT_FOUND",
                "message": f"Module '{body.module}' has no registered AI agents.",
                "details": {"available_modules": list(_MODULE_REGISTRIES.keys())},
            },
        )

    # --- Step 2: Validate agent exists in module registry ---
    if not registry.has_agent(body.agent_name):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": "ERR_AI_AGENT_NOT_FOUND",
                "message": (
                    f"Agent '{body.agent_name}' not found in module '{body.module}'."
                ),
                "details": {
                    "available_agents": registry.list_agents(),
                },
            },
        )

    # --- Step 3: Build Gateway Context ---
    # Map string role to Role enum (fallback to SYSTEM if unknown)
    try:
        actor_role = Role(body.actor_role)
    except ValueError:
        actor_role = Role.SYSTEM

    context = AIGatewayContext(
        actor_id=body.actor_id,
        actor_role=actor_role,
        actor_type="human"
        if actor_role not in (Role.AI_AGENT, Role.SYSTEM)
        else "system",
        org_id=body.org_id,
        module=body.module,
        wizard=body.wizard,
        correlation_id=body.correlation_id,
        metadata=body.input_data,
    )

    # --- Step 4: Execute agent ---
    result: AIInvocationResult = registry.execute(
        agent_name=body.agent_name,
        context=context,
        input_data=body.input_data,
        model_override=body.model_override,
    )

    # --- Step 5: Build response ---
    response_data = AIInvokeResponse(
        success=result.success,
        request_id=result.request_id,
        module=body.module,
        agent_name=body.agent_name,
        model=result.model,
        latency_ms=result.latency_ms,
        content=result.content,
        error=result.error,
        validated_output=(
            result.validated_output.model_dump() if result.validated_output else None
        ),
    )

    status_code = 200 if result.success else 500
    return JSONResponse(
        status_code=status_code,
        content=response_data.model_dump(),
    )


# =============================================================================
# GET /api/v1/ai/agents/{module} — List Module Agents
# =============================================================================


@router.get("/agents/{module}", response_model=AgentListResponse)
@require_permission(Permission.AI_INVOKE)
async def list_module_agents(request: Request, module: str) -> JSONResponse:
    """
    List all registered AI agents for a given module.

    Useful for discovery and admin dashboards.
    """
    registry = _MODULE_REGISTRIES.get(module)
    if registry is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "code": "ERR_AI_MODULE_NOT_FOUND",
                "message": f"Module '{module}' not found.",
                "details": {"available_modules": list(_MODULE_REGISTRIES.keys())},
            },
        )

    agents = registry.list_agents_detail()

    return JSONResponse(
        status_code=200,
        content={
            "module": module,
            "agents": agents,
        },
    )


# =============================================================================
# GET /api/v1/ai/metrics — AI Observability (E03-S10)
# =============================================================================


@router.get("/metrics")
@require_permission(Permission.AI_INVOKE)
async def get_ai_metrics(
    request: Request,
    org_id: str,
    window_hours: int = 24,
    module: str | None = None,
) -> JSONResponse:
    """
    Retrieve aggregated AI usage metrics for a tenant.

    Metrics are derived from the immutable audit ledger — no separate
    telemetry store. Tenant-scoped; callers only receive their own metrics.

    Query params:
        org_id:       Required. Tenant to scope metrics to.
        window_hours: Look-back window in hours (default 24, max 168).
        module:       Optional module filter (M1, M2, …).

    Returns:
        InvocationMetrics JSON — does NOT include tenant_id.
    """
    # Clamp window to 7 days max to prevent expensive full-table scans
    window_hours = max(1, min(window_hours, 168))

    metrics = AIObservabilityService.get_metrics(
        tenant_id=org_id,
        window_hours=window_hours,
        module=module,
    )

    return JSONResponse(
        status_code=200,
        content={
            "window_start": metrics.window_start.isoformat(),
            "window_end": metrics.window_end.isoformat(),
            "window_hours": window_hours,
            "invocations": {
                "total": metrics.total_invocations,
                "successful": metrics.successful_invocations,
                "failed": metrics.failed_invocations,
                "failure_rate": round(metrics.failure_rate, 4),
            },
            "latency_ms": {
                "avg": round(metrics.avg_latency_ms, 2),
                "p95": round(metrics.p95_latency_ms, 2),
                "max": round(metrics.max_latency_ms, 2),
            },
            "guardrails": {
                "blocks": metrics.guardrail_blocks,
                "warnings": metrics.guardrail_warnings,
            },
            "hitl": {
                "reviews": metrics.hitl_reviews,
                "escalations": metrics.hitl_escalations,
                "auto_proceeds": metrics.hitl_auto_proceeds,
            },
            "safety": {
                "injection_attempts": metrics.injection_attempts,
                "schema_rejections": metrics.schema_rejections,
            },
            "model_usage": metrics.model_usage,
            "agent_executions": metrics.agent_executions,
        },
    )


# =============================================================================
# GET /api/v1/ai/health — AI Subsystem Health
# =============================================================================


@router.get("/health")
@require_permission(Permission.AI_INVOKE)
async def ai_health_check() -> JSONResponse:
    """
    Check health of the AI subsystem.

    Verifies:
    - Gateway module loaded
    - Agent registries loaded
    - No forbidden cloud imports detected
    """
    cloud_violations = AIGateway.validate_no_cloud_imports()

    return JSONResponse(
        status_code=200 if not cloud_violations else 500,
        content={
            "status": "healthy" if not cloud_violations else "degraded",
            "gateway": "loaded",
            "registered_modules": list(_MODULE_REGISTRIES.keys()),
            "cloud_violations": cloud_violations,
        },
    )
