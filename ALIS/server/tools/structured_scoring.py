"""
StructuredScoringTool — E03-S05

Computes a normalized aggregate score from a set of component scores,
applying weights declared in a rubric. Returns a structured scoring
report suitable for AI agent consumption and downstream rule evaluation.

Read-only. No DB writes. No chaining.

Input schema:
    {
        "scores": [
            {
                "component": str,   # Must match a rubric component name
                "raw_score": float, # Achieved score
                "max_score": float  # Maximum possible score for this component
            },
            ...
        ],
        "rubric": {
            "components": [
                {
                    "name": str,
                    "weight": float  # Weight as percentage (must sum to 100)
                },
                ...
            ]
        }
    }

Output data keys:
    {
        "aggregate_score": float,       # 0.0 - 100.0 weighted aggregate
        "aggregate_percentage": float,  # Same as aggregate_score (0-100)
        "component_scores": [
            {
                "component": str,
                "raw_score": float,
                "max_score": float,
                "percentage": float,
                "weight": float,
                "weighted_contribution": float
            }
        ],
        "missing_components": [str, ...],  # Components in rubric but not in scores
        "scoring_complete": bool
    }
"""

from typing import Any, ClassVar, Dict, List

from server.core.tool_registry import BaseTool, ToolOutputSchema
from server.core.exceptions import ToolSchemaViolationError


class StructuredScoringTool(BaseTool):
    """
    Computes a weighted aggregate score from component scores and a rubric.

    Used by evaluation agents to produce a normalized final score
    before passing to the rule engine for eligibility decisions.
    """

    tool_id: ClassVar[str] = "tool.scoring.structured"
    version: ClassVar[int] = 1
    description: ClassVar[str] = (
        "Computes a weighted aggregate score from component scores and a rubric. "
        "Returns normalized percentage and per-component breakdown."
    )
    read_only: ClassVar[bool] = True

    def execute(
        self,
        input_data: Dict[str, Any],
        tenant_id: str,
    ) -> ToolOutputSchema:
        """
        Compute weighted aggregate score.

        Args:
            input_data: Must contain "scores" (list) and "rubric" (dict).
            tenant_id:  Tenant scope.

        Returns:
            ToolOutputSchema with scoring report in data.

        Raises:
            ToolSchemaViolationError: If input structure is invalid.
        """
        scores = input_data.get("scores")
        if not isinstance(scores, list):
            raise ToolSchemaViolationError(
                message="StructuredScoringTool requires 'scores' (list) in input_data.",
                details={"received_keys": list(input_data.keys())},
            )

        rubric = input_data.get("rubric")
        if not isinstance(rubric, dict):
            raise ToolSchemaViolationError(
                message="StructuredScoringTool requires 'rubric' (dict) in input_data.",
                details={"received_keys": list(input_data.keys())},
            )

        components = rubric.get("components", [])
        if not isinstance(components, list) or not components:
            raise ToolSchemaViolationError(
                message="StructuredScoringTool: rubric.components must be a non-empty list.",
            )

        # Build weight lookup from rubric
        weight_map: Dict[str, float] = {}
        for comp in components:
            name = comp.get("name")
            weight = comp.get("weight")
            if name and isinstance(weight, (int, float)):
                weight_map[str(name)] = float(weight)

        # Build score lookup from input
        score_map: Dict[str, Dict[str, float]] = {}
        for entry in scores:
            if not isinstance(entry, dict):
                continue
            comp_name = entry.get("component")
            raw = entry.get("raw_score")
            max_s = entry.get("max_score")
            if comp_name and isinstance(raw, (int, float)) and isinstance(max_s, (int, float)) and max_s > 0:
                score_map[str(comp_name)] = {
                    "raw_score": float(raw),
                    "max_score": float(max_s),
                }

        # Compute weighted contributions
        component_scores = []
        aggregate = 0.0
        missing: List[str] = []

        for comp_name, weight in weight_map.items():
            if comp_name not in score_map:
                missing.append(comp_name)
                continue

            raw_score = score_map[comp_name]["raw_score"]
            max_score = score_map[comp_name]["max_score"]
            percentage = (raw_score / max_score) * 100.0
            weighted_contribution = (percentage * weight) / 100.0

            aggregate += weighted_contribution
            component_scores.append({
                "component": comp_name,
                "raw_score": raw_score,
                "max_score": max_score,
                "percentage": round(percentage, 4),
                "weight": weight,
                "weighted_contribution": round(weighted_contribution, 4),
            })

        return ToolOutputSchema(
            tool_id=self.tool_id,
            tool_version=self.version,
            data={
                "aggregate_score": round(aggregate, 4),
                "aggregate_percentage": round(aggregate, 4),
                "component_scores": component_scores,
                "missing_components": missing,
                "scoring_complete": len(missing) == 0,
            },
            source="structured_scoring",
        )
