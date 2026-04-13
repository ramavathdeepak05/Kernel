"""
ALIS Academics — Student Risk Detector Agent v1

MODULE: M2 — Academics
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "Is this student at risk of academic failure or dropout?"

AI Role: Analytical — synthesise multiple weak signals into a risk tier.

Confidence Rules (thresholds configurable via tenant policy):
    Score >= ai.academics.risk_high_threshold (default 75%) → HIGH risk
    Score >= 0.45 → MEDIUM risk (schedule check-in)
    Score <  0.45 → LOW risk    (routine monitoring)

Hard Constraints:
    - Read-only. Never mutates state.
    - Risk tier is a Draft — academic counsellor confirms before action.
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

# Default high-risk threshold — overridden per-tenant via ai.academics.risk_high_threshold
_HIGH_TIER_DEFAULT = 3 / 4


def execute_risk_detector(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Execute the Student Risk Detector.

    Expected input_data keys:
        student_id      : str — UUID of the student
        attendance_pct  : float — current attendance percentage
        internal_avg    : float — average internal exam score (0–100)
        lms_logins_30d  : int   — LMS logins in last 30 days
        counselling_flags: int  — number of prior counselling referrals
        course_name     : str   — (optional) context label

    Returns AIInvocationResult with content JSON:
        {
          "risk_tier":    "HIGH" | "MEDIUM" | "LOW",
          "risk_score":   0.0–1.0,
          "rationale":    str,
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="academics.risk_detection",
            prompt_version=1,
            variables={
                "student_id": input_data.get("student_id", "unknown"),
                "attendance_pct": input_data.get("attendance_pct", 0),
                "internal_avg": input_data.get("internal_avg", 0),
                "lms_logins_30d": input_data.get("lms_logins_30d", 0),
                "counselling_flags": input_data.get("counselling_flags", 0),
                "course_name": input_data.get("course_name", ""),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score
            high_threshold = float(
                PolicyStore.get(
                    context.org_id or "", "ai.academics.risk_high_threshold"
                )
                or _HIGH_TIER_DEFAULT
            )
            if score >= high_threshold:
                tier = "HIGH"
                action = "Immediate counsellor referral and faculty alert."
            elif score >= 0.45:
                tier = "MEDIUM"
                action = "Schedule a check-in within 5 working days."
            else:
                tier = "LOW"
                action = "Continue routine monitoring."

            return AIInvocationResult(
                success=True,
                content=json.dumps(
                    {
                        "risk_tier": tier,
                        "risk_score": round(score, 3),
                        "rationale": vo.reasoning or result.content or "",
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
                    "risk_tier": "LOW",
                    "risk_score": 0.0,
                    "rationale": "Insufficient data.",
                    "recommended_action": "Monitor.",
                }
            ),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("risk_detector_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
