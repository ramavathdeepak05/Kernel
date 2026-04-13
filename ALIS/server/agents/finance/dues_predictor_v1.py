"""
ALIS Finance — Dues Predictor Agent v1

MODULE: M4 — Finance
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "Is this student at risk of fee default?"

AI Role: Evaluative — assess default probability from payment behaviour signals.

Confidence Rules (thresholds configurable via tenant policy):
    Score >= ai.finance.dues_high_risk_threshold (default 75%) → HIGH risk
    Score >= 0.45 → MEDIUM risk (early reminder + soft follow-up)
    Score <  0.45 → LOW risk    (standard dunning schedule)

Hard Constraints:
    - Read-only. Never mutates state.
    - Risk tier is a Draft — Finance Officer confirms before intervention.
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


def execute_dues_predictor(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Execute the Dues Predictor.

    Expected input_data keys:
        student_id          : str   — UUID of the student
        total_dues          : float — total outstanding fee (INR)
        overdue_days        : int   — days since last due date
        missed_instalments  : int   — number of missed scheduled instalments
        prior_defaults      : int   — number of prior default incidents
        scholarship_active  : bool  — whether student holds an active scholarship
        waiver_applied      : bool  — whether a fee waiver is pending
        course_name         : str   — (optional) context label

    Returns AIInvocationResult with content JSON:
        {
          "risk_tier":          "HIGH" | "MEDIUM" | "LOW",
          "risk_score":         0.0–1.0,
          "rationale":          str,
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="finance.dues_prediction",
            prompt_version=1,
            variables={
                "student_id": input_data.get("student_id", "unknown"),
                "total_dues": input_data.get("total_dues", 0),
                "overdue_days": input_data.get("overdue_days", 0),
                "missed_instalments": input_data.get("missed_instalments", 0),
                "prior_defaults": input_data.get("prior_defaults", 0),
                "scholarship_active": input_data.get("scholarship_active", False),
                "waiver_applied": input_data.get("waiver_applied", False),
                "course_name": input_data.get("course_name", ""),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score
            high_threshold = float(
                PolicyStore.get(
                    context.org_id or "", "ai.finance.dues_high_risk_threshold"
                )
                or _HIGH_TIER_DEFAULT
            )
            if score >= high_threshold:
                tier = "HIGH"
                action = "Initiate payment plan discussion or refer to Finance Officer for waiver assessment."
            elif score >= 0.45:
                tier = "MEDIUM"
                action = "Send early payment reminder and schedule soft follow-up within 7 days."
            else:
                tier = "LOW"
                action = "Continue standard dunning schedule."

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
                    "rationale": "Insufficient payment data.",
                    "recommended_action": "Monitor.",
                }
            ),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("dues_predictor_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
