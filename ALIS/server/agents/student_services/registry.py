"""
ALIS Student Services Module — Agent Registry

MODULE: M6 — Student Services
LAYER: Layer 2 (Agentic Decisions)

Registered Agents:
    grievance_classifier_v1 — Grievance urgency classification and routing
"""
from __future__ import annotations

from typing import Dict, Any, List, Callable, Literal, Optional, Tuple
from dataclasses import dataclass

from server.core.ai_gateway import AIGatewayContext, AIInvocationResult
from server.core.audit import AuditLog, AuditAction


@dataclass(frozen=True)
class AgentMeta:
    agent_id: str
    module: str
    model_version: str
    prompt_version: str
    invocation_class: str
    authorization_policy: str
    allowed_tools: Tuple[str, ...] = ()
    description: str = ""
    status: Literal["ACTIVE", "SHADOW", "DEPRECATED"] = "ACTIVE"


class StudentServicesAgentRegistry:
    """Module-scoped agent registry for M6 — Student Services."""

    _agents: Dict[str, AgentMeta] = {
        "grievance_classifier_v1": AgentMeta(
            agent_id="grievance_classifier_v1",
            module="M6",
            model_version="qwen2.5:1.5b-instruct-q8_0",
            prompt_version="v1",
            invocation_class="EVALUATIVE",
            authorization_policy="student_welfare_officer_or_registrar_or_system",
            allowed_tools=(
                "tool.rag.retriever",
                "tool.policy.lookup",
            ),
            description=(
                "Classifies an incoming student grievance by urgency (CRITICAL / HIGH / MEDIUM / LOW) "
                "and routes it to the appropriate resolving authority (Dean, Registrar, HOD, Warden, "
                "or Counsellor). Detects safety-critical or harassment signals that require immediate "
                "escalation. Returns a routing recommendation as a Draft."
            ),
        ),
    }

    _executors: Dict[str, Callable] = {}

    @classmethod
    def _ensure_executors_loaded(cls):
        if not cls._executors:
            from server.agents.student_services.grievance_classifier_v1 import execute_grievance_classifier
            cls._executors["grievance_classifier_v1"] = execute_grievance_classifier

    @classmethod
    def has_agent(cls, agent_name: str) -> bool:
        return agent_name in cls._agents

    @classmethod
    def list_agents(cls) -> List[str]:
        return list(cls._agents.keys())

    @classmethod
    def list_agents_detail(cls) -> List[Dict[str, Any]]:
        return [
            {"agent_id": m.agent_id, "module": m.module, "model_version": m.model_version,
             "prompt_version": m.prompt_version, "invocation_class": m.invocation_class,
             "authorization_policy": m.authorization_policy, "allowed_tools": list(m.allowed_tools),
             "description": m.description}
            for m in cls._agents.values()
        ]

    @classmethod
    def execute(cls, agent_name: str, context: AIGatewayContext,
                input_data: Dict[str, Any], model_override: Optional[str] = None) -> AIInvocationResult:
        if agent_name not in cls._agents:
            raise ValueError(f"Agent '{agent_name}' not registered in M6 (Student Services).")
        cls._ensure_executors_loaded()
        executor = cls._executors.get(agent_name)
        if executor is None:
            raise ValueError(f"Agent '{agent_name}' has no executor.")
        meta = cls._agents[agent_name]
        AuditLog.log(action=AuditAction.AGENT_EXECUTION, actor_id=context.actor_id,
                     actor_type=context.actor_type, actor_role=context.actor_role.value if context.actor_role else None,
                     entity_type="ai_agent", entity_id=meta.agent_id, tenant_id=context.org_id,
                     metadata={"phase": "start", "module": "M6", "request_id": context.request_id})
        result = executor(context=context, input_data=input_data, model_override=model_override)
        AuditLog.log(action=AuditAction.AGENT_EXECUTION, actor_id=context.actor_id,
                     actor_type=context.actor_type, actor_role=context.actor_role.value if context.actor_role else None,
                     entity_type="ai_agent", entity_id=meta.agent_id, tenant_id=context.org_id,
                     success=result.success, failure_reason=result.error,
                     metadata={"phase": "complete", "request_id": context.request_id, "latency_ms": result.latency_ms})
        return result
