"""
ALIS HR Admin — Workload Analyzer Agent v1

MODULE: M5 — HR Admin
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "Is this faculty member's workload within policy limits?"

AI Role: Analytical — detect overload or underutilisation from teaching + admin signals.

Confidence Rules (thresholds configurable via tenant policy):
    Score >= ai.hr.workload_overloaded_threshold (default 75%) → OVERLOADED
    Score >= 0.45 → REVIEW_NEEDED   (flag for next workload review cycle)
    Score <  0.45 → BALANCED        (within policy norms)

Special case: underutilisation detected when teaching_hours_per_week < threshold
    and score < 0.45 → UNDERUTILISED tier with utilisation flag.

Hard Constraints:
    - Read-only. Never mutates state.
    - Workload tier is a Draft — HOD confirms before any reassignment.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)
from server.core.policy_store import PolicyStore

logger = logging.getLogger(__name__)

_HIGH_TIER_DEFAULT = 3 / 4


def execute_workload_analyzer(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Execute the Workload Analyzer.

    Expected input_data keys:
        faculty_id              : str   — UUID of the faculty member
        faculty_name            : str   — (optional) display name
        teaching_hours_per_week : float — actual teaching contact hours
        courses_assigned        : int   — number of courses this semester
        exam_duties             : int   — number of exam/invigilation duties
        admin_roles             : int   — number of committee/admin roles held
        policy_max_hours        : float — institution's policy maximum (default 18)
        policy_min_hours        : float — institution's policy minimum (default 10)
        department              : str   — (optional) department name

    Returns AIInvocationResult with content JSON:
        {
          "workload_tier":      "OVERLOADED" | "REVIEW_NEEDED" | "BALANCED" | "UNDERUTILISED",
          "severity_score":     0.0–1.0,
          "findings":           str,
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="hr.workload_analysis",
            prompt_version=1,
            variables={
                "faculty_id": input_data.get("faculty_id", "unknown"),
                "faculty_name": input_data.get("faculty_name", ""),
                "teaching_hours_per_week": input_data.get("teaching_hours_per_week", 0),
                "courses_assigned": input_data.get("courses_assigned", 0),
                "exam_duties": input_data.get("exam_duties", 0),
                "admin_roles": input_data.get("admin_roles", 0),
                "policy_max_hours": input_data.get("policy_max_hours", 18),
                "policy_min_hours": input_data.get("policy_min_hours", 10),
                "department": input_data.get("department", ""),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score
            teaching_hrs = input_data.get("teaching_hours_per_week", 0)
            policy_min = input_data.get("policy_min_hours", 10)

            high_threshold = float(
                PolicyStore.get(
                    context.org_id or "", "ai.hr.workload_overloaded_threshold"
                )
                or _HIGH_TIER_DEFAULT
            )
            if score >= high_threshold:
                tier = "OVERLOADED"
                action = "Immediate HOD review. Reassign at least one course or reduce admin duties."
            elif score >= 0.45:
                tier = "REVIEW_NEEDED"
                action = "Flag for next workload review cycle. HOD to assess rebalancing options."
            elif teaching_hrs < policy_min:
                tier = "UNDERUTILISED"
                action = "Consider additional course assignment or project supervision for utilisation."
            else:
                tier = "BALANCED"
                action = "No action required. Workload within policy norms."

            return AIInvocationResult(
                success=True,
                content=json.dumps(
                    {
                        "workload_tier": tier,
                        "severity_score": round(score, 3),
                        "findings": vo.reasoning or result.content or "",
                        "recommended_action": action,
                    }
                ),
                request_id=context.request_id,
                model=model_override or result.model or "qwen2.5",
            )

        return AIInvocationResult(
            success=True,
            content=result.content
            or json.dumps(
                {
                    "workload_tier": "BALANCED",
                    "severity_score": 0.0,
                    "findings": "Insufficient data for workload analysis.",
                    "recommended_action": "Provide complete workload data before re-running.",
                }
            ),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("workload_analyzer_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
