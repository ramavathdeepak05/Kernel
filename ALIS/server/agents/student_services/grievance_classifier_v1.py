"""
ALIS Student Services — Grievance Classifier Agent v1

MODULE: M6 — Student Services
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "How urgent is this grievance and who should resolve it?"

AI Role: Evaluative — classify urgency and route to the correct authority.

Urgency Tiers:
    CRITICAL — safety, harassment, mental health crisis → immediate Dean + Welfare Officer alert
    HIGH     — academic integrity, discrimination, housing emergency → 24-hour response SLA
    MEDIUM   — administrative delays, fee disputes, facility issues → 3-day response SLA
    LOW      — general complaints, suggestions → 7-day response SLA

Hard Constraints:
    - Read-only. Never mutates state.
    - Classification is a Draft — Student Welfare Officer reviews before assignment.
    - CRITICAL tier automatically triggers an escalation notification regardless of human review.
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

logger = logging.getLogger(__name__)

_ROUTING_MAP = {
    "CRITICAL": "Dean of Students + Student Welfare Officer (immediate)",
    "HIGH": "Registrar or HOD (24-hour SLA)",
    "MEDIUM": "Student Welfare Officer or relevant Department Head (3-day SLA)",
    "LOW": "Student Services Helpdesk (7-day SLA)",
}


def execute_grievance_classifier(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Execute the Grievance Classifier.

    Expected input_data keys:
        grievance_id    : str  — UUID of the grievance record
        subject         : str  — one-line subject provided by student
        description     : str  — full grievance text
        category        : str  — (optional) student-selected category hint
        student_id      : str  — UUID of the submitting student
        prior_grievances: int  — number of prior grievances by this student

    Returns AIInvocationResult with content JSON:
        {
          "urgency":            "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
          "confidence_score":   0.0–1.0,
          "routing":            str,
          "summary":            str,
          "recommended_action": str,
          "safety_flag":        bool
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="student_services.grievance_classification",
            prompt_version=1,
            variables={
                "grievance_id": input_data.get("grievance_id", "unknown"),
                "subject": input_data.get("subject", ""),
                "description": input_data.get("description", ""),
                "category": input_data.get("category", ""),
                "student_id": input_data.get("student_id", "unknown"),
                "prior_grievances": input_data.get("prior_grievances", 0),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score

            # Determine urgency tier from confidence score
            # (higher score = more severe / urgent)
            if score >= 0.85:
                urgency = "CRITICAL"
                safety_flag = True
            elif score >= 0.65:
                urgency = "HIGH"
                safety_flag = False
            elif score >= 0.40:
                urgency = "MEDIUM"
                safety_flag = False
            else:
                urgency = "LOW"
                safety_flag = False

            routing = _ROUTING_MAP[urgency]

            return AIInvocationResult(
                success=True,
                content=json.dumps(
                    {
                        "urgency": urgency,
                        "confidence_score": round(score, 3),
                        "routing": routing,
                        "summary": vo.reasoning or "",
                        "recommended_action": routing,
                        "safety_flag": safety_flag,
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
                    "urgency": "MEDIUM",
                    "confidence_score": 0.0,
                    "routing": _ROUTING_MAP["MEDIUM"],
                    "summary": "Insufficient data — defaulting to MEDIUM urgency.",
                    "recommended_action": _ROUTING_MAP["MEDIUM"],
                    "safety_flag": False,
                }
            ),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("grievance_classifier_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
