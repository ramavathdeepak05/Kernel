"""
ALIS Admissions Module — Agent Registry (E03-S01)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (Agentic Decisions)
ENTITY: AdmissionsAgentRegistry

Per the ALIS Module-Scoped AI Agent Model v1.0:
- Each module owns its AI agents.
- Agents may NOT be shared across modules.
- Each module maintains its own AgentRegistry, prompt versions,
  invocation rules, and confidence thresholds.

This registry maps agent names to their execution functions.
It is consumed exclusively by the AI Gateway router.

Registered Agents:
    - eligibility_evaluator_v1  — Eligibility Eval Wizard (M1-W3)
"""

from typing import Dict, Any, List, Callable, Optional, Tuple
from dataclasses import dataclass, field

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)
from server.core.audit import AuditLog, AuditAction


# =============================================================================
# AGENT METADATA
# =============================================================================

@dataclass(frozen=True)
class AgentMeta:
    """
    Metadata for a module-scoped AI agent.

    Per Module-Scoped AI Agent Model v1.0 Sec. 5 — Versioning.
    Per E03-S04: Agents are constrained, named actors with explicit scopes.

    Fields:
        allowed_tools: Exhaustive list of read-only tool names this agent
                       may invoke. DB write tools are structurally absent —
                       agents interact with data only through the AI Gateway
                       and declared read-only tools.
    """
    agent_id: str
    module: str
    model_version: str
    prompt_version: str
    invocation_class: str       # EVALUATIVE, GENERATIVE, ANALYTICAL
    authorization_policy: str
    allowed_tools: Tuple[str, ...] = ()   # E03-S04: declared tool scope
    description: str = ""


# =============================================================================
# ADMISSIONS AGENT REGISTRY
# =============================================================================

class AdmissionsAgentRegistry:
    """
    Module-scoped agent registry for M1 — Admissions & Marketing.

    Maintains:
    - Agent metadata (versioned)
    - Agent execution functions
    - Invocation rules

    No agent in this registry may be invoked by any other module.
    Cross-module interaction MUST go through events (Wizard → Core → Event Bus).
    """

    # --- Agent metadata store ---
    _agents: Dict[str, AgentMeta] = {
        "eligibility_evaluator_v1": AgentMeta(
            agent_id="eligibility_evaluator_v1",
            module="M1",
            model_version="llama3_8b_v1",
            prompt_version="v1",
            invocation_class="EVALUATIVE",
            authorization_policy="admissions_officer_or_system",
            allowed_tools=(
                "tool.rag.retriever",    # Semantic search over institutional docs
                "tool.policy.lookup",    # Fetch admission criteria from policy store
                "tool.scoring.structured",  # Compute weighted eligibility score
            ),
            description=(
                "Evaluates applicant eligibility by analyzing uploaded "
                "marksheets via OCR + LLM grading against admission criteria."
            ),
        ),
    }

    # --- Agent execution function map ---
    # Populated at import time by importing the agent modules.
    _executors: Dict[str, Callable] = {}

    @classmethod
    def _ensure_executors_loaded(cls):
        """Lazy-load agent executors to avoid circular imports."""
        if not cls._executors:
            from server.agents.admissions.eligibility import execute_eligibility_eval
            cls._executors["eligibility_evaluator_v1"] = execute_eligibility_eval

    @classmethod
    def has_agent(cls, agent_name: str) -> bool:
        """Check if an agent is registered."""
        return agent_name in cls._agents

    @classmethod
    def list_agents(cls) -> List[str]:
        """List all registered agent names."""
        return list(cls._agents.keys())

    @classmethod
    def list_agents_detail(cls) -> List[Dict[str, Any]]:
        """List all agents with their metadata."""
        return [
            {
                "agent_id": meta.agent_id,
                "module": meta.module,
                "model_version": meta.model_version,
                "prompt_version": meta.prompt_version,
                "invocation_class": meta.invocation_class,
                "authorization_policy": meta.authorization_policy,
                "allowed_tools": list(meta.allowed_tools),
                "description": meta.description,
            }
            for meta in cls._agents.values()
        ]

    @classmethod
    def execute(
        cls,
        agent_name: str,
        context: AIGatewayContext,
        input_data: Dict[str, Any],
        model_override: Optional[str] = None,
    ) -> AIInvocationResult:
        """
        Execute a registered agent.

        Args:
            agent_name: Registered agent identifier
            context: AIGatewayContext (tenant + RBAC)
            input_data: Agent-specific input payload
            model_override: Optional LLM model override

        Returns:
            AIInvocationResult from the agent execution

        Raises:
            ValueError: If agent_name is not registered
        """
        if agent_name not in cls._agents:
            raise ValueError(
                f"Agent '{agent_name}' not registered in M1 (Admissions)."
            )

        cls._ensure_executors_loaded()

        executor = cls._executors.get(agent_name)
        if executor is None:
            raise ValueError(
                f"Agent '{agent_name}' is registered but has no executor."
            )

        meta = cls._agents[agent_name]

        # E03-S04: Log agent execution start
        AuditLog.log(
            action=AuditAction.AGENT_EXECUTION,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            actor_role=context.actor_role.value if context.actor_role else None,
            entity_type="ai_agent",
            entity_id=meta.agent_id,
            org_id=context.org_id,
            module=context.module,
            wizard=context.wizard,
            metadata={
                "phase": "start",
                "invocation_class": meta.invocation_class,
                "allowed_tools": list(meta.allowed_tools),
                "model_version": meta.model_version,
                "prompt_version": meta.prompt_version,
                "request_id": context.request_id,
            },
        )

        result = executor(
            context=context,
            input_data=input_data,
            model_override=model_override,
        )

        # E03-S04: Log agent execution completion
        AuditLog.log(
            action=AuditAction.AGENT_EXECUTION,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            actor_role=context.actor_role.value if context.actor_role else None,
            entity_type="ai_agent",
            entity_id=meta.agent_id,
            org_id=context.org_id,
            module=context.module,
            wizard=context.wizard,
            success=result.success,
            failure_reason=result.error,
            metadata={
                "phase": "complete",
                "request_id": context.request_id,
                "latency_ms": result.latency_ms,
                "model": result.model,
            },
        )

        return result
