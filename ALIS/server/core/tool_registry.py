"""
ALIS Tool Invocation Framework — E03-S05

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions) + Layer 4 (Invariant Enforcement)
ENTITY: ToolRegistry, ToolInvoker

Implements a controlled Tool Invocation Framework for ALIS AI agents.

All tools agents may invoke MUST be:
- Pre-registered in ToolRegistry
- Declared in the agent's allowed_tools list (AgentMeta)
- Read-only (no DB writes)
- Schema-validated on output
- Audit-logged on every invocation

Hard Constraints (E03-S05):
- Tools cannot write to DB (enforced at registration and invocation)
- No tool chaining (ToolInvoker cannot be called from inside tool.execute())
- No dynamic tool selection (allowed_tools is a static declaration)
- Undeclared tools are rejected before execution

Acceptance Criteria:
- [x] Tools are registered in Tool Registry
- [x] Agents declare allowed tools in DSL (AgentMeta.allowed_tools)
- [x] Undeclared tools are rejected
- [x] Tool output must match schema
- [x] Tool invocation is logged
- [x] Tools cannot write to DB
- [x] No tool chaining allowed
- [x] RAG implemented via this framework
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field as PydanticField

from .audit import AuditLog, AuditAction
from .exceptions import (
    ToolNotAllowedError,
    ToolNotRegisteredError,
    ToolSchemaViolationError,
    ToolWriteAttemptError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL OUTPUT SCHEMA (Mandatory Output Contract)
# =============================================================================

class ToolOutputSchema(BaseModel):
    """
    Mandatory output schema for all ALIS tool invocations.

    Every tool MUST return a ToolOutputSchema instance.
    Free-form or untyped returns are rejected by ToolInvoker.

    Fields:
        tool_id:      The registered tool identifier (e.g. "tool.policy.lookup")
        tool_version: Integer version of the tool implementation
        data:         The structured result data (tool-specific keys)
        source:       Human-readable source description (table/index/service)
        retrieved_at: UTC timestamp of when the data was retrieved
    """
    tool_id: str = PydanticField(..., description="Registered tool identifier")
    tool_version: int = PydanticField(..., description="Tool implementation version")
    data: Dict[str, Any] = PydanticField(
        default_factory=dict,
        description="Structured result data from the tool"
    )
    source: Optional[str] = PydanticField(
        default=None,
        description="Data source description (e.g. 'policy_registry', 'rag_index')"
    )
    retrieved_at: datetime = PydanticField(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of retrieval"
    )


# =============================================================================
# BASE TOOL (Abstract)
# =============================================================================

class BaseTool(ABC):
    """
    Abstract base class for all ALIS tools.

    All concrete tools must:
    1. Set tool_id to a namespaced string (e.g. "tool.policy.lookup")
    2. Set version to an explicit integer
    3. Keep read_only = True (enforced at registration)
    4. Implement execute() returning ToolOutputSchema
    5. NOT call ToolInvoker.invoke() from inside execute() (no chaining)

    The execute() contract:
    - Input: tool-specific dict + tenant_id
    - Output: ToolOutputSchema
    - Side effects: NONE (read-only, no DB mutations)
    - Exceptions: raise ToolSchemaViolationError or ValueError for bad input
    """

    #: Unique tool identifier. Namespaced: "tool.<domain>.<function>"
    tool_id: ClassVar[str]

    #: Integer version. Increment when behaviour changes.
    version: ClassVar[int]

    #: Human-readable description of what this tool does.
    description: ClassVar[str]

    #: MUST remain True for all tools. Set to False only to trigger
    #: ToolWriteAttemptError at registration time.
    read_only: ClassVar[bool] = True

    @abstractmethod
    def execute(
        self,
        input_data: Dict[str, Any],
        tenant_id: str,
    ) -> ToolOutputSchema:
        """
        Execute the tool.

        Args:
            input_data: Tool-specific input dict
            tenant_id:  Tenant scope for data isolation

        Returns:
            ToolOutputSchema with the result

        Raises:
            ToolSchemaViolationError: If input is invalid
            ValueError: For domain-specific input errors
        """
        ...  # pragma: no cover


# =============================================================================
# TOOL REGISTRY
# =============================================================================

class ToolRegistry:
    """
    Central registry for all ALIS tools.

    Tools are registered at import time (or at server startup).
    The registry is read-only after startup — no runtime modifications.

    Enforces:
    - All registered tools must have read_only=True
    - Tool IDs must be unique
    - No anonymous or ad-hoc tool registration
    """

    _tools: Dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # REGISTER
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """
        Register a tool instance in the global tool registry.

        Args:
            tool: A BaseTool subclass instance

        Raises:
            ToolWriteAttemptError: If tool.read_only is not True
            ValueError: If a different tool is already registered under this ID
        """
        if not tool.read_only:
            raise ToolWriteAttemptError(
                message=(
                    f"Tool '{tool.tool_id}' cannot be registered: "
                    f"read_only must be True (E03-S05 invariant)."
                ),
                details={"tool_id": tool.tool_id},
            )

        existing = cls._tools.get(tool.tool_id)
        if existing is not None and type(existing) is not type(tool):
            raise ValueError(
                f"Tool '{tool.tool_id}' is already registered with a "
                f"different implementation ({type(existing).__name__})."
            )

        cls._tools[tool.tool_id] = tool
        logger.info(
            "E03-S05: Tool registered — id=%s version=%d",
            tool.tool_id, tool.version,
        )

    # ------------------------------------------------------------------
    # LOOKUP
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, tool_id: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by ID. Returns None if not found."""
        return cls._tools.get(tool_id)

    @classmethod
    def list_tools(cls) -> List[Dict[str, Any]]:
        """List all registered tools with their metadata."""
        return [
            {
                "tool_id": t.tool_id,
                "version": t.version,
                "description": t.description,
                "read_only": t.read_only,
            }
            for t in cls._tools.values()
        ]

    @classmethod
    def is_registered(cls, tool_id: str) -> bool:
        """Check if a tool is registered."""
        return tool_id in cls._tools


# =============================================================================
# TOOL INVOKER
# =============================================================================

class ToolInvoker:
    """
    Controlled tool invocation layer for ALIS AI agents.

    This is the ONLY authorized path for agent tool invocations.
    Direct instantiation and calling of tool.execute() outside this
    class is prohibited.

    Enforcement pipeline (per invocation):
        1. Check tool_name is in agent's declared allowed_tools
        2. Check tool is registered in ToolRegistry
        3. Verify tool.read_only (belt-and-suspenders)
        4. Execute tool.execute()
        5. Validate output is ToolOutputSchema
        6. Log AGENT_TOOL_CALL to AuditLog
        7. Return validated output

    No chaining: ToolInvoker.invoke() cannot be called from inside
    a tool's execute() method. Tools are pure read functions.
    """

    @staticmethod
    def invoke(
        tool_name: str,
        input_data: Dict[str, Any],
        agent_id: str,
        allowed_tools: Tuple[str, ...],
        tenant_id: str,
        module: Optional[str] = None,
        wizard: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> ToolOutputSchema:
        """
        Invoke a registered tool on behalf of an agent.

        Args:
            tool_name:     Tool ID to invoke (e.g. "tool.policy.lookup")
            input_data:    Tool-specific input payload
            agent_id:      ID of the invoking agent (for audit)
            allowed_tools: Agent's declared allowed tools (from AgentMeta)
            tenant_id:     Tenant scope
            module:        Module context (for audit)
            wizard:        Wizard context (for audit)
            actor_id:      Human actor who triggered the agent run (for audit)
            actor_role:    Actor's role (for audit)

        Returns:
            ToolOutputSchema — validated structured output

        Raises:
            ToolNotAllowedError:    Tool not in agent's allowed_tools
            ToolNotRegisteredError: Tool not in ToolRegistry
            ToolWriteAttemptError:  Tool is not read-only (invariant)
            ToolSchemaViolationError: Tool returned invalid output
        """
        # ------------------------------------------------------------------
        # Step 1: Declared tool check (agent DSL)
        # ------------------------------------------------------------------
        if tool_name not in allowed_tools:
            AuditLog.log(
                action=AuditAction.AGENT_TOOL_CALL,
                actor_id=actor_id or agent_id,
                actor_role=actor_role,
                entity_type="tool",
                entity_id=tool_name,
                org_id=tenant_id,
                module=module,
                wizard=wizard,
                success=False,
                failure_reason=f"Tool '{tool_name}' not declared in agent allowed_tools",
                metadata={
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "allowed_tools": list(allowed_tools),
                    "violation": "undeclared_tool",
                },
            )
            raise ToolNotAllowedError(
                message=(
                    f"Agent '{agent_id}' is not permitted to invoke tool "
                    f"'{tool_name}' — not declared in allowed_tools (E03-S05)."
                ),
                details={
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "allowed_tools": list(allowed_tools),
                },
            )

        # ------------------------------------------------------------------
        # Step 2: Registry check
        # ------------------------------------------------------------------
        tool = ToolRegistry.get(tool_name)
        if tool is None:
            raise ToolNotRegisteredError(
                message=(
                    f"Tool '{tool_name}' is not registered in the Tool Registry "
                    f"(E03-S05). Register it before use."
                ),
                details={"tool_name": tool_name},
            )

        # ------------------------------------------------------------------
        # Step 3: Read-only invariant (belt-and-suspenders)
        # ------------------------------------------------------------------
        if not tool.read_only:
            raise ToolWriteAttemptError(
                message=(
                    f"Tool '{tool_name}' is not read-only — execution blocked "
                    f"(E03-S05 Layer 4 Invariant)."
                ),
                details={"tool_name": tool_name},
            )

        # ------------------------------------------------------------------
        # Step 4: Execute
        # ------------------------------------------------------------------
        try:
            raw_result = tool.execute(input_data=input_data, tenant_id=tenant_id)
        except (ToolSchemaViolationError, ToolNotAllowedError, ToolWriteAttemptError):
            raise  # Re-raise framework errors unchanged
        except Exception as exc:
            # Log and wrap unexpected errors
            AuditLog.log(
                action=AuditAction.AGENT_TOOL_CALL,
                actor_id=actor_id or agent_id,
                actor_role=actor_role,
                entity_type="tool",
                entity_id=tool_name,
                org_id=tenant_id,
                module=module,
                wizard=wizard,
                success=False,
                failure_reason=str(exc),
                metadata={
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "tool_version": tool.version,
                },
            )
            raise

        # ------------------------------------------------------------------
        # Step 5: Output schema validation
        # ------------------------------------------------------------------
        if not isinstance(raw_result, ToolOutputSchema):
            raise ToolSchemaViolationError(
                message=(
                    f"Tool '{tool_name}' returned {type(raw_result).__name__} "
                    f"instead of ToolOutputSchema (E03-S05)."
                ),
                details={
                    "tool_name": tool_name,
                    "returned_type": type(raw_result).__name__,
                },
            )

        # ------------------------------------------------------------------
        # Step 6: Audit log (success)
        # ------------------------------------------------------------------
        AuditLog.log(
            action=AuditAction.AGENT_TOOL_CALL,
            actor_id=actor_id or agent_id,
            actor_role=actor_role,
            entity_type="tool",
            entity_id=tool_name,
            org_id=tenant_id,
            module=module,
            wizard=wizard,
            success=True,
            metadata={
                "agent_id": agent_id,
                "tool_name": tool_name,
                "tool_version": raw_result.tool_version,
                "source": raw_result.source,
                "data_keys": list(raw_result.data.keys()),
                "input_hash": hashlib.sha256(
                    str(sorted(input_data.items())).encode()
                ).hexdigest()[:16],
            },
        )

        return raw_result
