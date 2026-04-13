"""
ALIS HR Admin Module — Agent Registry

MODULE: M5 — HR Admin
LAYER: Layer 2 (Agentic Decisions)

Registered Agents:
    workload_analyzer_v1 — Faculty workload gap analysis
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from server.core.ai_gateway import AIGatewayContext, AIInvocationResult
from server.core.audit import AuditAction, AuditLog


@dataclass(frozen=True)
class AgentMeta:
    agent_id: str
    module: str
    model_version: str
    prompt_version: str
    invocation_class: str
    authorization_policy: str
    allowed_tools: tuple[str, ...] = ()
    description: str = ""
    status: Literal["ACTIVE", "SHADOW", "DEPRECATED"] = "ACTIVE"


class HRAdminAgentRegistry:
    """Module-scoped agent registry for M5 — HR Admin."""

    _agents: dict[str, AgentMeta] = {
        "workload_analyzer_v1": AgentMeta(
            agent_id="workload_analyzer_v1",
            module="M5",
            model_version="qwen2.5:1.5b-instruct-q8_0",
            prompt_version="v1",
            invocation_class="ANALYTICAL",
            authorization_policy="hod_or_hr_admin_or_system",
            allowed_tools=(
                "tool.rag.retriever",
                "tool.policy.lookup",
            ),
            description=(
                "Analyses faculty workload across teaching hours, course assignments, exam duties, "
                "and administrative responsibilities to detect overload or underutilisation gaps. "
                "Returns a workload tier (OVERLOADED / BALANCED / UNDERUTILISED) with rebalancing "
                "recommendations for the HOD."
            ),
        ),
    }

    _executors: dict[str, Callable] = {}

    @classmethod
    def _ensure_executors_loaded(cls):
        if not cls._executors:
            from server.agents.hr_admin.workload_analyzer_v1 import (
                execute_workload_analyzer,
            )

            cls._executors["workload_analyzer_v1"] = execute_workload_analyzer

    @classmethod
    def has_agent(cls, agent_name: str) -> bool:
        return agent_name in cls._agents

    @classmethod
    def list_agents(cls) -> list[str]:
        return list(cls._agents.keys())

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
            raise ValueError(f"Agent '{agent_name}' not registered in M5 (HR Admin).")
        cls._ensure_executors_loaded()
        executor = cls._executors.get(agent_name)
        if executor is None:
            raise ValueError(f"Agent '{agent_name}' has no executor.")
        meta = cls._agents[agent_name]
        AuditLog.log(
            action=AuditAction.AGENT_EXECUTION,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            actor_role=context.actor_role.value if context.actor_role else None,
            entity_type="ai_agent",
            entity_id=meta.agent_id,
            tenant_id=context.org_id,
            metadata={
                "phase": "start",
                "module": "M5",
                "request_id": context.request_id,
            },
        )
        result = executor(
            context=context, input_data=input_data, model_override=model_override
        )
        AuditLog.log(
            action=AuditAction.AGENT_EXECUTION,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            actor_role=context.actor_role.value if context.actor_role else None,
            entity_type="ai_agent",
            entity_id=meta.agent_id,
            tenant_id=context.org_id,
            success=result.success,
            failure_reason=result.error,
            metadata={
                "phase": "complete",
                "request_id": context.request_id,
                "latency_ms": result.latency_ms,
            },
        )
        return result
