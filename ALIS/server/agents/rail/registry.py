"""
ALIS Agent Rail — Agent Registry (RAIL)

MODULE: RAIL — Agent Rail Intelligence
LAYER: Layer 2 (Agentic Decisions)

Registered agents:
    context_advisor_v1 — Context-aware proactive briefing for the agent rail.

AgentMeta.status values:
    ACTIVE     — live, returned to callers
    SHADOW     — runs alongside ACTIVE, output logged to audit_ledger only,
                 never returned to caller. Used for A/B testing new prompt
                 versions. Both outputs tagged with agent_id + prompt_version
                 in audit_ledger for comparison. Promotion gate is manual
                 review until an automated divergence criterion is defined.
    DEPRECATED — no longer invoked; kept for audit history only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from server.core.ai_gateway import AIGatewayContext, AIInvocationResult
from server.core.audit import AuditAction, AuditLog

# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentMeta:
    agent_id: str
    module: str
    model_version: str
    prompt_version: str
    invocation_class: str  # EVALUATIVE | GENERATIVE | ANALYTICAL
    authorization_policy: str
    allowed_tools: tuple[str, ...] = ()
    description: str = ""
    status: Literal["ACTIVE", "SHADOW", "DEPRECATED"] = "ACTIVE"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class RailAgentRegistry:
    """Module-scoped registry for RAIL agents."""

    _agents: dict[str, AgentMeta] = {
        "context_advisor_v1": AgentMeta(
            agent_id="context_advisor_v1",
            module="RAIL",
            model_version="programmatic+copilot",
            prompt_version="v2-copilot",
            invocation_class="ANALYTICAL",
            authorization_policy="any_authenticated_role",
            allowed_tools=("tool.db.workflow_tasks.count",),
            description=(
                "Context-aware copilot for the ALIS agent rail. "
                "Three modes: (1) view_change — programmatic proactive briefing, "
                "(2) chip action — pre-configured quick queries, "
                "(3) copilot — structured LLM conversation with role-aware "
                "intent parsing, EXECUTE_MODULE draft actions (all modules + "
                "policy + settings), batch actions, and tenant-configurable personality. "
                "Silence threshold is institution-configurable via agent_rail_silence policy."
            ),
            status="ACTIVE",
        ),
    }

    _executors: dict[str, Callable] = {}

    @classmethod
    def _ensure_executors_loaded(cls) -> None:
        if not cls._executors:
            from server.agents.rail.context_advisor import execute_context_advisor

            cls._executors["context_advisor_v1"] = execute_context_advisor

    @classmethod
    def has_agent(cls, agent_name: str) -> bool:
        return agent_name in cls._agents

    @classmethod
    def list_agents(cls) -> list[str]:
        return [n for n, m in cls._agents.items() if m.status != "DEPRECATED"]

    @classmethod
    def list_agents_detail(cls) -> list[dict[str, Any]]:
        return [
            {
                "agent_id": m.agent_id,
                "module": m.module,
                "model_version": m.model_version,
                "prompt_version": m.prompt_version,
                "invocation_class": m.invocation_class,
                "authorization_policy": m.authorization_policy,
                "allowed_tools": list(m.allowed_tools),
                "description": m.description,
                "status": m.status,
            }
            for m in cls._agents.values()
        ]

    @classmethod
    def execute(
        cls,
        agent_name: str,
        context: AIGatewayContext,
        input_data: dict[str, Any],
        model_override: str | None = None,
    ) -> AIInvocationResult:
        if agent_name not in cls._agents:
            raise ValueError(f"Agent '{agent_name}' not registered in RAIL module.")

        meta = cls._agents[agent_name]

        if meta.status == "DEPRECATED":
            raise ValueError(
                f"Agent '{agent_name}' is deprecated and cannot be invoked."
            )

        cls._ensure_executors_loaded()
        executor = cls._executors.get(agent_name)
        if executor is None:
            raise ValueError(f"Agent '{agent_name}' has no executor.")

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
                "status": meta.status,
                "invocation_class": meta.invocation_class,
                "prompt_version": meta.prompt_version,
                "request_id": context.request_id,
                "view": input_data.get("view"),
                "trigger": input_data.get("message", "")[:80],
            },
        )

        result = executor(
            context=context,
            input_data=input_data,
            model_override=model_override,
        )

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
                "status": meta.status,
                "request_id": context.request_id,
                "latency_ms": result.latency_ms,
                # SHADOW agents log their output here for comparison against ACTIVE
                "shadow_content": result.content if meta.status == "SHADOW" else None,
            },
        )

        # SHADOW agents: run for logging only, return empty success to gateway
        if meta.status == "SHADOW":
            return AIInvocationResult(
                success=True,
                content=None,
                request_id=context.request_id,
                model=result.model,
                latency_ms=result.latency_ms,
            )

        return result
