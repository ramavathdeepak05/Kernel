"""
ALIS Research — Plagiarism Advisor Agent v1

MODULE: M8 — Research
LAYER: Layer 2 (Agentic Decisions)

Decision:
    "How should this PhD scholar remediate their plagiarism findings?"

AI Role: Evaluative — interpret similarity report and generate a structured remediation plan
         within institutional policy thresholds.

Severity Assessment (based on similarity_pct):
    >= 40% → CRITICAL  (exceeds UGC Regulations 2018 threshold — submission blocked)
    >= 25% → HIGH      (significant revision required before re-submission)
    >= 10% → MODERATE  (targeted paraphrasing and citation improvement needed)
    <  10% → ACCEPTABLE (within threshold — minor citation clean-up only)

Hard Constraints:
    - Read-only. Never modifies thesis documents.
    - Advice is a Draft — Supervisor must review and confirm the remediation plan.
    - Does not make conclusions about academic misconduct — that is a human decision.
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


def execute_plagiarism_advisor(
    context: AIGatewayContext,
    input_data: Dict[str, Any],
    model_override: Optional[str] = None,
) -> AIInvocationResult:
    """
    Execute the Plagiarism Advisor.

    Expected input_data keys:
        thesis_id           : str   — UUID of the thesis record
        scholar_name        : str   — (optional) display name
        similarity_pct      : float — overall similarity percentage from detection tool
        self_citation_pct   : float — percentage attributed to self-citation
        internet_match_pct  : float — percentage matched from internet sources
        publication_match_pct: float — percentage matched from academic publications
        top_matched_sections: list  — (optional) list of section names with high similarity
        chapter_count       : int   — total chapters in thesis
        detector_tool       : str   — (optional) "iThenticate" | "Turnitin" | "other"

    Returns AIInvocationResult with content JSON:
        {
          "severity":           "CRITICAL" | "HIGH" | "MODERATE" | "ACCEPTABLE",
          "similarity_pct":     float,
          "submission_blocked": bool,
          "remediation_plan":   str,
          "section_advice":     [{"section": str, "action": str}],
          "estimated_effort":   str,
          "recommended_action": str
        }
    """
    llm = AIGateway.get_llm(context)
    similarity_pct = float(input_data.get("similarity_pct", 0))

    # Hard-block determination before LLM (policy-based, not AI-based)
    submission_blocked = similarity_pct >= 40

    try:
        result = llm.invoke_with_prompt(
            prompt_name="research.plagiarism_advice",
            prompt_version=1,
            variables={
                "thesis_id":              input_data.get("thesis_id", "unknown"),
                "scholar_name":           input_data.get("scholar_name", ""),
                "similarity_pct":         similarity_pct,
                "self_citation_pct":      input_data.get("self_citation_pct", 0),
                "internet_match_pct":     input_data.get("internet_match_pct", 0),
                "publication_match_pct":  input_data.get("publication_match_pct", 0),
                "top_matched_sections":   json.dumps(input_data.get("top_matched_sections", [])),
                "chapter_count":          input_data.get("chapter_count", 0),
                "detector_tool":          input_data.get("detector_tool", "unknown"),
            },
            validate_schema=True,
        )

        if similarity_pct >= 40:
            severity = "CRITICAL"
            action = "Submission blocked. Scholar must revise and resubmit for plagiarism check."
        elif similarity_pct >= 25:
            severity = "HIGH"
            action = "Significant revision required. Re-submit for plagiarism check after corrections."
        elif similarity_pct >= 10:
            severity = "MODERATE"
            action = "Targeted paraphrasing and citation improvements required."
        else:
            severity = "ACCEPTABLE"
            action = "Within threshold. Minor citation clean-up recommended before final submission."

        if result.validated_output:
            vo = result.validated_output
            remediation_plan = vo.reasoning or result.content or ""
        else:
            remediation_plan = result.content or "Review each matched section and either paraphrase or add proper citations."

        return AIInvocationResult(
            success=True,
            content=json.dumps({
                "severity": severity,
                "similarity_pct": round(similarity_pct, 2),
                "submission_blocked": submission_blocked,
                "remediation_plan": remediation_plan,
                "section_advice": [],
                "estimated_effort": "2–4 weeks" if severity in ("CRITICAL", "HIGH") else "3–5 days",
                "recommended_action": action,
            }),
            request_id=context.request_id,
            model=model_override or (result.model if result.validated_output else "qwen2.5"),
        )

    except Exception as exc:
        logger.exception("plagiarism_advisor_v1 failed: %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "qwen2.5",
        )
