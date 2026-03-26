"""
PolicyLookupTool — E03-S05

Retrieves the active policy value for a given policy_key and tenant.
Read-only. No DB writes. No chaining.

Input schema:
    {
        "policy_key": str,          # e.g. "attendance.minimum_percentage"
        "as_of": str | None         # ISO datetime string, optional
    }

Output data keys:
    {
        "policy_key": str,
        "value": Any,
        "effective_from": str,
        "version": int
    }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Optional

from server.core.tool_registry import BaseTool, ToolOutputSchema
from server.core.exceptions import ToolSchemaViolationError


class PolicyLookupTool(BaseTool):
    """
    Looks up the current active policy value for a given key and tenant.

    Uses the ConfigRegistry (in-memory) as the policy store.
    For DB-backed policy lookups, the backing store can be swapped
    without changing this interface.

    Allowed inputs:
        policy_key (required): The config key to look up
        as_of (optional):      ISO datetime string for point-in-time lookup
    """

    tool_id: ClassVar[str] = "tool.policy.lookup"
    version: ClassVar[int] = 1
    description: ClassVar[str] = (
        "Retrieves the active policy value for a given policy key. "
        "Read-only. Used by agents to fetch institutional rules."
    )
    read_only: ClassVar[bool] = True

    def execute(
        self,
        input_data: Dict[str, Any],
        tenant_id: str,
    ) -> ToolOutputSchema:
        """
        Look up a policy value.

        Args:
            input_data: Must contain "policy_key" (str). Optionally "as_of" (ISO str).
            tenant_id:  Tenant scope (used for audit; ConfigRegistry is global)

        Returns:
            ToolOutputSchema with the policy value in data.

        Raises:
            ToolSchemaViolationError: If policy_key is missing or invalid.
        """
        policy_key = input_data.get("policy_key")
        if not policy_key or not isinstance(policy_key, str):
            raise ToolSchemaViolationError(
                message=(
                    "PolicyLookupTool requires 'policy_key' (str) in input_data."
                ),
                details={"received_keys": list(input_data.keys())},
            )

        as_of_str: Optional[str] = input_data.get("as_of")
        as_of: Optional[datetime] = None
        if as_of_str:
            try:
                as_of = datetime.fromisoformat(as_of_str)
            except ValueError:
                raise ToolSchemaViolationError(
                    message=f"PolicyLookupTool: 'as_of' is not a valid ISO datetime: {as_of_str!r}",
                    details={"as_of": as_of_str},
                )

        from server.core.config import ConfigRegistry

        entry = ConfigRegistry.get_entry(policy_key)
        if entry is None:
            # Return empty data — agents must handle missing policy
            return ToolOutputSchema(
                tool_id=self.tool_id,
                tool_version=self.version,
                data={
                    "policy_key": policy_key,
                    "value": None,
                    "found": False,
                },
                source="config_registry",
            )

        value = entry.get_value(as_of=as_of)
        version = entry.current_version

        return ToolOutputSchema(
            tool_id=self.tool_id,
            tool_version=self.version,
            data={
                "policy_key": policy_key,
                "value": value,
                "found": True,
                "version": version,
                "effective_from": (
                    entry.versions[-1].effective_from.isoformat()
                    if entry.versions
                    else None
                ),
            },
            source="config_registry",
        )
