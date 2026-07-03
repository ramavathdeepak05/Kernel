"""Config-driven hosted-MCP endpoint selection.

Turns a ``[mcp]`` config section into a `GovernedMCPProxy` served at ``/mcp`` on the shared plane —
the BYO-downstream hosted MCP endpoint (each tenant registers their own downstream MCP server, whose
tools are governed + forwarded per tenant). Off by default; the operator opts in.

Config shape::

    [mcp]
    enabled        = true            # omit / false → /mcp is not mounted
    name           = "quaicu-hosted" # optional display name
    default_policy = "mcp.tool"      # optional: govern all tools under one action type (else each
                                     #   tool defaults to its own mcp.<tool_name> action type)

Registered-tools mode (a fixed operator tool set) can't come from TOML — it needs code handlers, so
it stays the programmatic ``build_saas_app(..., mcp_server=...)`` param.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_mcp_gateway(config: Mapping[str, Any]) -> Any | None:
    """Build the hosted MCP proxy from a ``[mcp]`` section, or ``None`` when disabled/absent.

    Fail-fast: if ``enabled`` is set but the optional ``mcp`` SDK isn't installed, raise (a misconfig
    should surface, not silently leave ``/mcp`` unmounted).
    """
    section = config.get("mcp", {}) or {}
    if not section.get("enabled"):
        return None
    try:
        from delivery.mcp.proxy import GovernedMCPProxy
    except ImportError as exc:  # pragma: no cover - exercised only without the [mcp] extra
        raise ValueError(
            "[mcp] enabled=true but the MCP SDK is not installed — build the image with the "
            "'mcp' extra (pip install quaicu-kernel[mcp])."
        ) from exc

    default_policy = str(section.get("default_policy", "") or "") or None
    return GovernedMCPProxy(
        name=str(section.get("name", "") or "quaicu-hosted"),
        default_policy=default_policy,
    )
