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

from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)


# =============================================================================
# AGENT METADATA
# =============================================================================

@dataclass(frozen=True)
class AgentMeta:
    """
    Metadata for a module-scoped AI agent.

    Per Module-Scoped AI Agent Model v1.0 Sec. 5 — Versioning.
    """
    agent_id: str
    module: str
    model_version: str
    prompt_version: str
    invocation_class: str  # EVALUATIVE, GENERATIVE, ANALYTICAL
    authorization_policy: str
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

        return executor(
            context=context,
            input_data=input_data,
            model_override=model_override,
        )
