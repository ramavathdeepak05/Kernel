"""Governed MCP proxy (D2-1) — front a downstream MCP server, govern + forward.

`GovernedMCPProxy` sits between the agent and a DOWNSTREAM MCP server (the real tools). It mirrors the
downstream's tool list and governs every call before forwarding it — so the agent AND the downstream
tools need no code change; you just point the agent at the proxy. ALLOW forwards to the downstream;
DENY/HALT/PENDING block the call (fail-closed).

`downstream` is any object exposing ``async list_tools()`` and ``async call_tool(name, arguments)`` (an
``mcp`` ClientSession, or a stub in tests) — so the governance is unit-testable without a live server.
The ``mcp`` server-facing transport is wired lazily.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from core.types import Actor
from delivery.mcp.governance import ToolOutcome, ToolStatus, govern_tool_call
from delivery.mcp.render import to_call_result
from delivery.sdk.kernel import Kernel

log = logging.getLogger("quaicu.mcp.proxy")


class Downstream(Protocol):
    async def list_tools(self) -> Any: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class GovernedMCPProxy:
    """Govern every tool call, then forward allowed ones to a downstream MCP server."""

    def __init__(
        self,
        kernel: Kernel,
        *,
        actor: Actor,
        downstream: Downstream,
        name: str = "quaicu-governed-proxy",
        default_policy: str = "mcp.tool",
        policy_for: Callable[[str], str] | None = None,
    ) -> None:
        self._kernel = kernel
        self._actor = actor
        self._downstream = downstream
        self._name = name
        self._policy_for = policy_for or (lambda _name: default_policy)

    async def _govern(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        async def execute(args: dict[str, Any]) -> Any:
            return await self._downstream.call_tool(name, args)

        return await govern_tool_call(
            self._kernel,
            actor=self._actor,
            tool_name=name,
            arguments=arguments,
            policy=self._policy_for(name),
            execute=execute,
        )

    async def handle_call(self, name: str, arguments: dict[str, Any] | None):
        """Govern a call and build the `CallToolResult` (forwarding to the downstream only on ALLOW)."""
        return to_call_result(await self._govern(name, dict(arguments or {})))

    # ── MCP transport wiring (lazy import) ───────────────────────────────────────

    def build_mcp_server(self):
        """Wire a low-level ``mcp`` Server that mirrors the downstream tools, governed."""
        import mcp.types as types
        from mcp.server import Server

        server = Server(self._name)

        @server.list_tools()
        async def _list() -> list:
            listed = await self._downstream.list_tools()
            # An mcp ListToolsResult has `.tools`; a plain list is returned as-is.
            return list(getattr(listed, "tools", listed))

        @server.call_tool()
        async def _call(name: str, arguments: dict[str, Any] | None):
            outcome = await self._govern(name, dict(arguments or {}))
            if outcome.status is ToolStatus.ALLOWED:
                r = outcome.result
                # Forward the downstream's own content when it returned an mcp result.
                content = getattr(r, "content", None)
                if content is not None:
                    return content
                return r if isinstance(r, dict) else [types.TextContent(type="text", text=str(r))]
            text = f"{outcome.status.value.lower()} by governance"
            if outcome.status is ToolStatus.PENDING and outcome.handle_id:
                text = f"pending approval: approve handle {outcome.handle_id} via /v1/approvals"
            raise PermissionError(text)

        return server
