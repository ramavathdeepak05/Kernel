"""
RubricValidatorTool — E03-S05

Validates a grading rubric configuration against institutional rules.
Returns whether the rubric is valid and lists any violations.

Read-only. No DB writes. No chaining.

Input schema:
    {
        "rubric": {                  # Rubric to validate
            "components": [
                {
                    "name": str,     # Component name (e.g. "Internal Assessment")
                    "weight": float, # Weight as percentage (0-100)
                    "min_pass": float
                },
                ...
            ]
        },
        "total_marks": int           # Total marks the rubric is out of
    }

Output data keys:
    {
        "valid": bool,
        "violations": [str, ...],
        "total_weight": float,
        "component_count": int
    }
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from server.core.tool_registry import BaseTool, ToolOutputSchema
from server.core.exceptions import ToolSchemaViolationError


class RubricValidatorTool(BaseTool):
    """
    Validates a grading rubric against ALIS institutional rules.

    Rules enforced:
    - Component weights must sum to 100
    - Each component weight must be > 0
    - min_pass per component must be in [0, 100]
    - At least one component must exist
    - total_marks must be a positive integer
    """

    tool_id: ClassVar[str] = "tool.rubric.validator"
    version: ClassVar[int] = 1
    description: ClassVar[str] = (
        "Validates a grading rubric configuration against institutional rules. "
        "Returns validity flag and a list of violations."
    )
    read_only: ClassVar[bool] = True

    def execute(
        self,
        input_data: Dict[str, Any],
        tenant_id: str,
    ) -> ToolOutputSchema:
        """
        Validate a rubric.

        Args:
            input_data: Must contain "rubric" (dict with "components" list)
                        and "total_marks" (int).
            tenant_id:  Tenant scope (used for contextual rule lookup if extended).

        Returns:
            ToolOutputSchema with validation result in data.

        Raises:
            ToolSchemaViolationError: If input structure is invalid.
        """
        rubric = input_data.get("rubric")
        if not isinstance(rubric, dict):
            raise ToolSchemaViolationError(
                message="RubricValidatorTool requires 'rubric' (dict) in input_data.",
                details={"received_keys": list(input_data.keys())},
            )

        components = rubric.get("components")
        if not isinstance(components, list):
            raise ToolSchemaViolationError(
                message="RubricValidatorTool: rubric.components must be a list.",
                details={"rubric_keys": list(rubric.keys())},
            )

        total_marks = input_data.get("total_marks")
        if total_marks is None or not isinstance(total_marks, (int, float)) or total_marks <= 0:
            raise ToolSchemaViolationError(
                message="RubricValidatorTool requires 'total_marks' (positive number).",
                details={"total_marks": total_marks},
            )

        violations: List[str] = []

        if len(components) == 0:
            violations.append("Rubric must have at least one component.")

        total_weight = 0.0
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                violations.append(f"Component {i} is not a dict.")
                continue

            name = comp.get("name", f"component_{i}")
            weight = comp.get("weight")
            min_pass = comp.get("min_pass", 0)

            if weight is None or not isinstance(weight, (int, float)):
                violations.append(f"Component '{name}': missing or invalid 'weight'.")
            elif weight <= 0:
                violations.append(f"Component '{name}': weight must be > 0.")
            else:
                total_weight += float(weight)

            if not isinstance(min_pass, (int, float)) or not (0 <= min_pass <= 100):
                violations.append(
                    f"Component '{name}': min_pass must be in [0, 100], got {min_pass!r}."
                )

        if components and abs(total_weight - 100.0) > 0.01:
            violations.append(
                f"Component weights must sum to 100, got {total_weight:.2f}."
            )

        return ToolOutputSchema(
            tool_id=self.tool_id,
            tool_version=self.version,
            data={
                "valid": len(violations) == 0,
                "violations": violations,
                "total_weight": round(total_weight, 4),
                "component_count": len(components),
            },
            source="rubric_validator",
        )
