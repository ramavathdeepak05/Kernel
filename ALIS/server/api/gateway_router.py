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

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)
from server.core.rbac import Role, Permission, require_permission
from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import (
    PermissionDeniedError,
    PromptInjectionError,
    AISchemaViolationError,
    ALISError,
)

# Module-scoped agent registries — import per module
from server.agents.admissions.registry import AdmissionsAgentRegistry


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["ai-gateway"])


# =============================================================================
# MODULE REGISTRY LOOKUP
# =============================================================================

# Maps module identifiers to their scoped agent registries.
# Each module maintains its own registry per the Module-Scoped Agent Model.
_MODULE_REGISTRIES: Dict[str, Any] = {
    "M1": AdmissionsAgentRegistry,
    # "M2": AcademicsAgentRegistry,     # Future: E03-S02+
    # "M3": ExaminationsAgentRegistry,  # Future
    # "M4": FinanceAgentRegistry,       # Future
    # "M5": HRAdminAgentRegistry,       # Future
    # "M6": StudentServicesAgentRegistry, # Future
    # "M7": RegulatoryAgentRegistry,    # Future
    # "M8": ResearchAgentRegistry,      # Future
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
    org_id: str = Field(
        ..., description="Tenant/Organization ID for isolation"
    )

    # Module & Agent targeting
    module: str = Field(
        ..., description="Target module (e.g., 'M1' for Admissions)"
    )
    agent_name: str = Field(
        ..., description="Name of the agent to invoke (e.g., 'eligibility_evaluator_v1')"
    )

    # Agent input
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input payload for the agent (module-specific)"
    )

    # Optional
    wizard: Optional[str] = Field(
        default=None, description="Wizard context (e.g., 'Eligibility Eval')"
    )
    correlation_id: Optional[str] = Field(
        default=None, description="Correlation ID for distributed tracing"
    )
    model_override: Optional[str] = Field(
        default=None,
        description="Optional LLM model override (e.g., 'qwen2.5')"
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
    content: Optional[str] = None
    error: Optional[str] = None

    # E00-S06: Structured output (when schema-validated)
    validated_output: Optional[Dict[str, Any]] = None


class AgentListResponse(BaseModel):
    """Response listing available agents for a module."""
    module: str
    agents: list


# =============================================================================
# POST /api/v1/ai/invoke — Central AI Invocation Endpoint
# =============================================================================

@router.post("/invoke", response_model=AIInvokeResponse)
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
        actor_type="human" if actor_role not in (Role.AI_AGENT, Role.SYSTEM) else "system",
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
            result.validated_output.model_dump()
            if result.validated_output
            else None
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
# GET /api/v1/ai/health — AI Subsystem Health
# =============================================================================

@router.get("/health")
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
