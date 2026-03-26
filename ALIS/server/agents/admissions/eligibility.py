"""
ALIS Admissions Eligibility Evaluator Agent — E03-S01

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (Agentic Decisions)
ENTITY: Eligibility Eval Wizard (M1-W3)

Implements Blueprint B: AI Agent (Reasoning) using LangGraph StateGraph.

Per ALIS Master Developer Spec (M1 Wizard Table, Row 3):
    Name:     Eligibility Eval
    Type:     AI Agent
    Input:    PDF Marksheet (Stream)
    Process:  LangGraph: OCR (Tesseract) → Llama 3 ("Extract Grades")
              → Llama 3 ("Compare vs Criteria")
    Output:   score: 0-100, json_data

Decision Declaration (Layer 2 — Mandatory Format):
    Decision Made:
        "Is this applicant eligible for admission based on academic merit?"

    AI Role:
        Score + Infer

    Confidence Rules:
        High (>=0.8)   → Auto-eligible (ELIGIBLE)
        Medium (0.5-0.8) → Provisionally eligible (PROVISIONALLY_ELIGIBLE)
        Low (<0.5)     → Manual review required

    Human Authority:
        Approve only if provisional or low confidence

    Output:
        Eligibility score + Proposed next state

Hard Constraints:
    - Agent is READ-ONLY. It produces a "Draft" — never mutates state.
    - Uses AIGateway.get_llm() exclusively for inference.
    - Output conforms to AIResponseSchema (E00-S06).
"""
from __future__ import annotations

from typing import TypedDict, Dict, Any, Optional
import json
import logging

from langgraph.graph import StateGraph, END

from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
    AIResponseSchema,
    ConfidenceTier,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AGENT STATE (LangGraph TypedDict)
# =============================================================================

class EligibilityState(TypedDict):
    """
    State for the Eligibility Evaluator LangGraph workflow.

    Per Blueprint B: State flows through nodes, each adding to / reading
    from this shared state dict.
    """
    # Input
    marksheet_text: str          # OCR-extracted text from marksheet PDF
    admission_criteria: str      # Institutional criteria to compare against
    rbac_context: Dict[str, Any] # RBAC+ context (passed from gateway)

    # Intermediate
    extracted_grades: str        # Grades extracted by LLM

    # Output
    draft_verdict: str           # Raw LLM response (structured JSON)
    eligibility_score: float     # 0.0–1.0
    confidence_tier: str         # HIGH / MEDIUM / LOW
    proposed_state: str          # ELIGIBLE / PROVISIONALLY_ELIGIBLE / MANUAL_REVIEW


# =============================================================================
# GRAPH NODES
# =============================================================================

def extract_grades_node(state: EligibilityState) -> dict:
    """
    Node 1: Extract grades from marksheet text.

    Uses the AI Gateway to invoke the LLM for grade extraction.
    The LLM is instructed to return structured JSON with subjects and marks.

    Constraint: This node is read-only. It only analyzes text.
    """
    context = AIGatewayContext(
        actor_id="eligibility_evaluator_v1",
        actor_role=state["rbac_context"].get("actor_role"),
        actor_type="ai_agent",
        org_id=state["rbac_context"].get("org_id"),
        module="M1",
        wizard="Eligibility Eval",
    )

    llm = AIGateway.get_llm(context)

    # E03-S03: Fetch prompt from registry instead of inline string.
    # Template variables are rendered by the AI Gateway via Jinja2.
    result = llm.invoke_with_prompt(
        prompt_name="eligibility.extract_grades",
        prompt_version=1,
        variables={"marksheet_text": state["marksheet_text"]},
        validate_schema=False,
    )

    return {"extracted_grades": result.content or "{}"}


def evaluate_eligibility_node(state: EligibilityState) -> dict:
    """
    Node 2: Compare extracted grades against admission criteria.

    Uses the AI Gateway to invoke the LLM for eligibility evaluation.
    The LLM MUST return output conforming to AIResponseSchema:
    - decision, confidence_score, confidence_tier, state_impact, reasoning

    Constraint: Output must have state_impact = "Draft" or "ProvisionalOnly".
    """
    from server.core.rbac import Role

    context = AIGatewayContext(
        actor_id="eligibility_evaluator_v1",
        actor_role=state["rbac_context"].get("actor_role"),
        actor_type="ai_agent",
        org_id=state["rbac_context"].get("org_id"),
        module="M1",
        wizard="Eligibility Eval",
    )

    llm = AIGateway.get_llm(context)

    # E03-S03: Fetch prompt from registry instead of inline string.
    # Template variables are rendered by the AI Gateway via Jinja2.
    result = llm.invoke_with_prompt(
        prompt_name="eligibility.evaluate",
        prompt_version=1,
        variables={
            "extracted_grades": state["extracted_grades"],
            "admission_criteria": state["admission_criteria"],
        },
        validate_schema=True,
    )

    # Extract structured fields from validated output
    if result.validated_output:
        vo = result.validated_output
        score = vo.confidence_score
        tier = vo.confidence_tier.value

        # Confidence thresholds from policy_engine — never hardcoded (§12.4 R02)
        org_id = state["rbac_context"].get("org_id", "")
        from server.core.policy_store import PolicyStore
        high_conf = float(PolicyStore.get(org_id, "ai.eligibility.high_confidence_threshold") or 0.8)
        low_conf = float(PolicyStore.get(org_id, "ai.eligibility.low_confidence_threshold") or 0.5)

        # Map confidence to proposed state
        if score >= high_conf:
            proposed = "ELIGIBLE"
        elif score >= low_conf:
            proposed = "PROVISIONALLY_ELIGIBLE"
        else:
            proposed = "MANUAL_REVIEW"

        return {
            "draft_verdict": result.content,
            "eligibility_score": score,
            "confidence_tier": tier,
            "proposed_state": proposed,
        }

    # Fallback if validation was bypassed (should not happen)
    return {
        "draft_verdict": result.content or "",
        "eligibility_score": 0.0,
        "confidence_tier": "LOW",
        "proposed_state": "MANUAL_REVIEW",
    }


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================

def build_eligibility_graph() -> StateGraph:
    """
    Build the LangGraph StateGraph for eligibility evaluation.

    Graph topology:
        extract_grades → evaluate_eligibility → END
    """
    graph = StateGraph(EligibilityState)

    graph.add_node("extract_grades", extract_grades_node)
    graph.add_node("evaluate_eligibility", evaluate_eligibility_node)

    graph.set_entry_point("extract_grades")
    graph.add_edge("extract_grades", "evaluate_eligibility")
    graph.add_edge("evaluate_eligibility", END)

    return graph


# =============================================================================
# EXECUTOR (Called by AdmissionsAgentRegistry)
# =============================================================================

def execute_eligibility_eval(
    context: AIGatewayContext,
    input_data: Dict[str, Any],
    model_override: Optional[str] = None,
) -> AIInvocationResult:
    """
    Execute the Eligibility Evaluator agent.

    This is the entry point called by AdmissionsAgentRegistry.execute().

    Args:
        context: AIGatewayContext (tenant + RBAC context)
        input_data: Must contain:
            - marksheet_text: str — OCR text from the marksheet
            - admission_criteria: str — criteria to evaluate against
        model_override: Optional LLM model name override

    Returns:
        AIInvocationResult with the eligibility evaluation
    """
    from server.core.rbac import Role

    # Build initial state
    initial_state: EligibilityState = {
        "marksheet_text": input_data.get("marksheet_text", ""),
        "admission_criteria": input_data.get(
            "admission_criteria",
            "Minimum 50% aggregate in qualifying examination"
        ),
        "rbac_context": {
            "actor_role": context.actor_role,
            "org_id": context.org_id,
        },
        "extracted_grades": "",
        "draft_verdict": "",
        "eligibility_score": 0.0,
        "confidence_tier": "LOW",
        "proposed_state": "MANUAL_REVIEW",
    }

    # Build and compile graph
    graph = build_eligibility_graph()
    compiled = graph.compile()

    # Execute the graph
    try:
        final_state = compiled.invoke(initial_state)

        # Build result from final state
        return AIInvocationResult(
            success=True,
            content=json.dumps({
                "eligibility_score": final_state.get("eligibility_score", 0.0),
                "confidence_tier": final_state.get("confidence_tier", "LOW"),
                "proposed_state": final_state.get("proposed_state", "MANUAL_REVIEW"),
                "draft_verdict": final_state.get("draft_verdict", ""),
            }),
            request_id=context.request_id,
            model=model_override or "llama3",
        )

    except Exception as e:
        logger.exception(f"Eligibility evaluation failed: {e}")
        return AIInvocationResult(
            success=False,
            error=str(e),
            request_id=context.request_id,
            model=model_override or "llama3",
        )
