"""
ALIS Examinations — Result Analyzer Agent v1

MODULE: M3 — Examinations
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "Does this grade distribution indicate a paper moderation issue?"

AI Role: Analytical — detect unusual clustering, bimodal distributions, or outlier
         scores from raw grade data.

Confidence Rules (thresholds configurable via tenant policy):
    Score >= ai.examinations.anomaly_high_threshold (default 75%) → HIGH anomaly
    Score >= 0.45 → MEDIUM anomaly (HOD review recommended)
    Score <  0.45 → NORMAL         (distribution within expected parameters)

Hard Constraints:
    - Read-only. Never mutates state.
    - Anomaly report is a Draft — COE confirms before any moderation action.
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


def execute_result_analyzer(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Execute the Result Analyzer.

    Expected input_data keys:
        exam_id         : str   — UUID of the examination
        course_name     : str   — human-readable course label
        total_students  : int   — number of students who appeared
        mean_score      : float — mean marks (0–100)
        std_dev         : float — standard deviation of scores
        pass_pct        : float — percentage who passed
        distinction_pct : float — percentage who scored >= 75
        below_40_pct    : float — percentage who scored < 40
        score_buckets   : dict  — optional histogram {bucket_label: count}

    Returns AIInvocationResult with content JSON:
        {
          "anomaly_level":  "HIGH" | "MEDIUM" | "NORMAL",
          "anomaly_score":  0.0–1.0,
          "findings":       str,
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="examinations.result_analysis",
            prompt_version=1,
            variables={
                "exam_id": input_data.get("exam_id", "unknown"),
                "course_name": input_data.get("course_name", ""),
                "total_students": input_data.get("total_students", 0),
                "mean_score": input_data.get("mean_score", 0),
                "std_dev": input_data.get("std_dev", 0),
                "pass_pct": input_data.get("pass_pct", 0),
                "distinction_pct": input_data.get("distinction_pct", 0),
                "below_40_pct": input_data.get("below_40_pct", 0),
                "score_buckets": json.dumps(input_data.get("score_buckets", {})),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score
            high_threshold = float(
                PolicyStore.get(
                    context.org_id or "", "ai.examinations.anomaly_high_threshold"
                )
                or _HIGH_TIER_DEFAULT
            )
            if score >= high_threshold:
                level = "HIGH"
                action = "Refer to Moderation Committee. COE must review before results are published."
            elif score >= 0.45:
                level = "MEDIUM"
                action = "HOD to review grade distribution within 3 working days."
            else:
                level = "NORMAL"
                action = "No action required. Distribution within expected parameters."

            return AIInvocationResult(
                success=True,
                content=json.dumps(
                    {
                        "anomaly_level": level,
                        "anomaly_score": round(score, 3),
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
                    "anomaly_level": "NORMAL",
                    "anomaly_score": 0.0,
                    "findings": "Insufficient data for analysis.",
                    "recommended_action": "Collect complete score data before re-running.",
                }
            ),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("result_analyzer_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
