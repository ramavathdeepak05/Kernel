"""Config-driven hosted-MCP selection: [mcp] enabled → a GovernedMCPProxy, else None."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from delivery.mcp.proxy import GovernedMCPProxy  # noqa: E402
from delivery.sdk.mcp_config import build_mcp_gateway  # noqa: E402


def test_disabled_or_absent_returns_none():
    assert build_mcp_gateway({}) is None
    assert build_mcp_gateway({"mcp": {}}) is None
    assert build_mcp_gateway({"mcp": {"enabled": False}}) is None


def test_enabled_builds_proxy():
    proxy = build_mcp_gateway({"mcp": {"enabled": True}})
    assert isinstance(proxy, GovernedMCPProxy)
    # No shared action type → each tool defaults to its own mcp.<tool_name>.
    assert proxy._policy_for("search") is None


def test_default_policy_groups_tools_under_one_action_type():
    proxy = build_mcp_gateway({"mcp": {"enabled": True, "default_policy": "mcp.tool"}})
    assert isinstance(proxy, GovernedMCPProxy)
    assert proxy._policy_for("search") == "mcp.tool"
    assert proxy._policy_for("wire_transfer") == "mcp.tool"
