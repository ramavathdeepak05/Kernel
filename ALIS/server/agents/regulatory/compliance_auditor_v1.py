"""
ALIS Regulatory — Compliance Auditor Agent v1

MODULE: M7 — Regulatory
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "Where are we non-compliant or at risk for NAAC / NIRF accreditation?"

AI Role: Analytical — cross-reference institutional metrics against regulatory benchmarks
         to surface gaps before formal assessment.

Gap Severity:
    CRITICAL — likely to cause grade/rank loss in formal audit → immediate IQAC action
    MAJOR    — significant deviation from benchmark → corrective plan required
    MINOR    — minor shortfall → monitor and improve
    COMPLIANT — meets or exceeds benchmark

Hard Constraints:
    - Read-only. Never mutates state.
    - Gap report is a Draft — IQAC Coordinator reviews before submission.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, Optional

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
)

logger = logging.getLogger(__name__)


def execute_compliance_auditor(
    context: AIGatewayContext,
    input_data: Dict[str, Any],
    model_override: Optional[str] = None,
) -> AIInvocationResult:
    """
    Execute the Compliance Auditor.

    Expected input_data keys:
        framework           : str   — "NAAC" | "NIRF" | "BOTH"
        avg_attendance_pct  : float — institution-wide average attendance
        pass_rate_pct       : float — overall pass rate last academic year
        phd_faculty_pct     : float — % of faculty with PhD
        research_papers_py  : int   — refereed research papers published last year
        student_faculty_ratio: float — students per faculty (lower is better)
        infrastructure_score: float — 0–10 self-assessed infra score
        placement_rate_pct  : float — % of eligible students placed
        accreditation_cycle : str   — (optional) "NAAC_CYCLE4" / "NIRF_2025" etc.

    Returns AIInvocationResult with content JSON:
        {
          "overall_risk":   "CRITICAL" | "MAJOR" | "MINOR" | "COMPLIANT",
          "risk_score":     0.0–1.0,
          "gap_summary":    str,
          "criterion_gaps": [{"criterion": str, "severity": str, "detail": str}],
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)

    try:
        result = llm.invoke_with_prompt(
            prompt_name="regulatory.compliance_audit",
            prompt_version=1,
            variables={
                "framework":             input_data.get("framework", "NAAC"),
                "avg_attendance_pct":    input_data.get("avg_attendance_pct", 0),
                "pass_rate_pct":         input_data.get("pass_rate_pct", 0),
                "phd_faculty_pct":       input_data.get("phd_faculty_pct", 0),
                "research_papers_py":    input_data.get("research_papers_py", 0),
                "student_faculty_ratio": input_data.get("student_faculty_ratio", 0),
                "infrastructure_score":  input_data.get("infrastructure_score", 0),
                "placement_rate_pct":    input_data.get("placement_rate_pct", 0),
                "accreditation_cycle":   input_data.get("accreditation_cycle", ""),
            },
            validate_schema=True,
        )

        if result.validated_output:
            vo = result.validated_output
            score = vo.confidence_score
            if score >= 0.75:
                risk = "CRITICAL"
                action = "Immediate IQAC action plan required. Present to Management Committee."
            elif score >= 0.50:
                risk = "MAJOR"
                action = "Develop corrective action plan within 30 days. IQAC to assign owners per criterion."
            elif score >= 0.25:
                risk = "MINOR"
                action = "Include in next IQAC quarterly review. Monitor improvement trajectory."
            else:
                risk = "COMPLIANT"
                action = "Institution meets benchmarks. Document evidence for SSR submission."

            return AIInvocationResult(
                success=True,
                content=json.dumps({
                    "overall_risk": risk,
                    "risk_score": round(score, 3),
                    "gap_summary": vo.reasoning or result.content or "",
                    "criterion_gaps": [],
                    "recommended_action": action,
                }),
                request_id=context.request_id,
                model=model_override or result.model or "qwen2.5",
            )

        return AIInvocationResult(
            success=True,
            content=result.content or json.dumps({
                "overall_risk": "MINOR",
                "risk_score": 0.0,
                "gap_summary": "Insufficient institutional data for full audit.",
                "criterion_gaps": [],
                "recommended_action": "Provide complete metrics before re-running the compliance audit.",
            }),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )

    except Exception as exc:
        logger.exception("compliance_auditor_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
