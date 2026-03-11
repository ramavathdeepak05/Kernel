"""
E04-S03 + P6 — Eligibility Evaluation Wizard (Orchestrator)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (AI) + Layer 3 (Transitions) + Layer 4 (Locks)
ENTITY: Applicant

Orchestrates the eligibility evaluation workflow (P6-enhanced):
    1. Validate applicant is APPLIED/SUBMITTED (Layer 3 pre-condition)
    2. Run deterministic rule engine (P6) — subject, board, % threshold, category relaxation
    3. If clear PASS/FAIL → execute transition immediately (no AI needed)
    4. If PROVISIONAL/BORDERLINE → invoke the LangGraph eligibility agent via AI Gateway
    5. Map AI confidence → proposed state
    6. Execute state transition (Layer 3 authority)
    7. Audit log result

The AI agent produces ONLY a draft — the orchestrator owns the
state transition. "AI proposes, rules enforce."

P6 Enhancement:
    - Deterministic rule check before AI (performance + cost saving)
    - Category relaxations applied (SC/ST get 5%, OBC 3%, EWS 3%, PWD 5%)
    - Required subject validation (e.g., PCM for B.Tech)
    - Board whitelist enforcement
    - Entrance score threshold check
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, IllegalStateTransitionError
from server.core.state_registry import StudentState
from server.db_service import execute_query

from .service import ApplicantService
from .eligibility_criteria import EligibilityCriteriaService, EligibilityRuleEngine

logger = logging.getLogger(__name__)

# Confidence thresholds (mirror eligibility.py agent)
_HIGH_THRESHOLD = 0.8
_MEDIUM_THRESHOLD = 0.5


def _verdict_to_score(verdict: Any) -> float:
    """Convert a rule engine EligibilityVerdictDetail to a numeric 0–1 score."""
    mapping = {
        "ELIGIBLE": 1.0,
        "PROVISIONALLY_ELIGIBLE": 0.6,
        "NOT_ELIGIBLE": 0.0,
        "NEEDS_AI_REVIEW": 0.5,
    }
    v = getattr(verdict, "verdict", "NEEDS_AI_REVIEW")
    return mapping.get(v, 0.5)


class EligibilityService:
    """
    Orchestrates eligibility evaluation for E04-S03.

    The LangGraph agent (in agents/admissions/eligibility.py) runs inside
    the AI Gateway and produces a Draft verdict. This service validates
    pre-conditions, runs the agent, then executes the authorised transition.
    """

    @classmethod
    def evaluate(
        cls,
        applicant_id: str,
        org_id: str,
        marksheet_text: str,
        admission_criteria: str,
        actor_id: str,
        actor_role: Any = None,
    ) -> Dict[str, Any]:
        """
        Run eligibility evaluation for an applicant.

        Args:
            applicant_id:      Applicant to evaluate
            org_id:            Tenant scope
            marksheet_text:    OCR-extracted text from uploaded marksheet
            admission_criteria: Institutional eligibility criteria
            actor_id:          Human or system actor triggering the evaluation
            actor_role:        Role enum for AI Gateway context

        Returns:
            Dict with eligibility_score, confidence_tier, proposed_state,
            and new_status (state after transition execution).

        Raises:
            BusinessRuleViolation: If applicant is not in APPLIED state.
            IllegalStateTransitionError: If transition cannot be executed.
        """
        from server.core.ai_gateway import AIGatewayContext
        from server.core.rbac import Role
        from server.agents.admissions.registry import AdmissionsAgentRegistry

        # --- Pre-condition: Applicant must be APPLIED ---
        rows = execute_query(
            "SELECT status, intended_program, intake_batch FROM applicants "
            "WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{applicant_id}' not found.",
            )
        current_status = rows[0]["status"]
        if current_status not in (StudentState.APPLIED.value, "APPLIED", "SUBMITTED"):
            raise BusinessRuleViolation(
                message=(
                    f"Eligibility evaluation requires APPLIED status — "
                    f"current status is '{current_status}'."
                ),
                details={"applicant_id": applicant_id, "status": current_status},
            )

        program_name = rows[0].get("intended_program", "")
        intake_batch = rows[0].get("intake_batch")

        # --- P6: Load criteria + run deterministic rule engine first ---
        criteria = EligibilityCriteriaService.get_criteria(org_id, program_name, intake_batch)
        rule_verdict = EligibilityRuleEngine.evaluate(applicant_id, org_id, criteria)

        # --- Short-circuit for clear PASS or FAIL (no AI needed) ---
        _direct_map = {
            "ELIGIBLE": StudentState.ELIGIBLE,
            "NOT_ELIGIBLE": StudentState.NOT_ELIGIBLE,
        }
        if rule_verdict.verdict in _direct_map:
            target_state = _direct_map[rule_verdict.verdict]
            updated = ApplicantService.transition_state(
                applicant_id=applicant_id,
                org_id=org_id,
                to_state=target_state,
                actor_id=actor_id,
                reason=(
                    f"Deterministic rule engine: {rule_verdict.verdict} "
                    f"(pct={rule_verdict.applicant_percentage}, "
                    f"eff_min={rule_verdict.effective_min_percentage})"
                ),
                metadata={
                    "engine": "deterministic",
                    "rule_verdict": rule_verdict.verdict,
                    "pass_reasons": rule_verdict.pass_reasons,
                    "fail_reasons": rule_verdict.fail_reasons,
                    "warnings": rule_verdict.warnings,
                    "criteria_applied": rule_verdict.criteria_applied,
                },
            )
            logger.info(
                "E04-S03 P6: Rule engine short-circuit [applicant=%s, verdict=%s, new_status=%s]",
                applicant_id, rule_verdict.verdict, updated.status,
            )
            return {
                "applicant_id": applicant_id,
                "eligibility_score": _verdict_to_score(rule_verdict),
                "confidence_tier": "HIGH",
                "proposed_state": rule_verdict.verdict,
                "new_status": updated.status,
                "agent_request_id": None,
                "rule_engine": {
                    "verdict": rule_verdict.verdict,
                    "pass_reasons": rule_verdict.pass_reasons,
                    "fail_reasons": rule_verdict.fail_reasons,
                    "warnings": rule_verdict.warnings,
                },
            }

        # --- PROVISIONALLY_ELIGIBLE → escalate to AI agent ---
        # Build AI Gateway context
        try:
            role = Role(actor_role) if actor_role else Role.SYSTEM
        except (ValueError, TypeError):
            role = Role.SYSTEM

        context = AIGatewayContext(
            actor_id=actor_id,
            actor_role=role,
            actor_type="human" if role not in (Role.AI_AGENT, Role.SYSTEM) else "system",
            org_id=org_id,
            module="M1",
            wizard="Eligibility Eval",
        )

        # Enrich input with rule engine context so AI has deterministic context
        result = AdmissionsAgentRegistry.execute(
            agent_name="eligibility_evaluator_v1",
            context=context,
            input_data={
                "marksheet_text": marksheet_text,
                "admission_criteria": admission_criteria,
                "rule_engine_context": {
                    "verdict": rule_verdict.verdict,
                    "category": rule_verdict.category,
                    "effective_min_percentage": rule_verdict.effective_min_percentage,
                    "applicant_percentage": rule_verdict.applicant_percentage,
                    "pass_reasons": rule_verdict.pass_reasons,
                    "warnings": rule_verdict.warnings,
                },
            },
        )

        if not result.success or not result.content:
            # AI failed — fall back to PROVISIONALLY_ELIGIBLE rule verdict
            logger.warning(
                "E04-S03: AI agent failed (err=%s); applying rule engine verdict=%s",
                result.error, rule_verdict.verdict,
            )
            updated = ApplicantService.transition_state(
                applicant_id=applicant_id,
                org_id=org_id,
                to_state=StudentState.PROVISIONALLY_ELIGIBLE,
                actor_id=actor_id,
                reason="AI agent unavailable — rule engine borderline → PROVISIONALLY_ELIGIBLE",
                metadata={
                    "engine": "deterministic_fallback",
                    "rule_verdict": rule_verdict.verdict,
                    "ai_error": result.error,
                },
            )
            return {
                "applicant_id": applicant_id,
                "eligibility_score": _verdict_to_score(rule_verdict),
                "confidence_tier": "LOW",
                "proposed_state": "PROVISIONALLY_ELIGIBLE",
                "new_status": updated.status,
                "agent_request_id": None,
                "rule_engine": {
                    "verdict": rule_verdict.verdict,
                    "warnings": rule_verdict.warnings,
                },
            }

        # --- Parse agent output ---
        try:
            agent_output = json.loads(result.content)
        except (json.JSONDecodeError, TypeError):
            agent_output = {}

        eligibility_score = float(agent_output.get("eligibility_score", 0.0))
        confidence_tier = agent_output.get("confidence_tier", "LOW")
        proposed_state_str = agent_output.get("proposed_state", "MANUAL_REVIEW")

        # --- Map proposed state to StudentState ---
        state_map = {
            "ELIGIBLE": StudentState.ELIGIBLE,
            "PROVISIONALLY_ELIGIBLE": StudentState.PROVISIONALLY_ELIGIBLE,
            "NOT_ELIGIBLE": StudentState.NOT_ELIGIBLE,
            "MANUAL_REVIEW": None,  # No auto-transition for manual review
        }
        target_state = state_map.get(proposed_state_str)

        # --- Execute transition (orchestrator authority) ---
        new_status = current_status
        if target_state is not None:
            updated = ApplicantService.transition_state(
                applicant_id=applicant_id,
                org_id=org_id,
                to_state=target_state,
                actor_id=actor_id,
                reason=f"AI eligibility evaluation (score={eligibility_score:.2f})",
                metadata={
                    "eligibility_score": eligibility_score,
                    "confidence_tier": confidence_tier,
                    "agent_request_id": result.request_id,
                    "rule_engine_verdict": rule_verdict.verdict,
                },
            )
            new_status = updated.status
        else:
            # MANUAL_REVIEW: log without transitioning
            AuditLog.log(
                action=AuditAction.AGENT_DECISION,
                actor_id=actor_id,
                entity_type="applicant",
                entity_id=applicant_id,
                org_id=org_id,
                module="M1",
                wizard="Eligibility Eval",
                success=True,
                metadata={
                    "decision": "manual_review_required",
                    "eligibility_score": eligibility_score,
                    "confidence_tier": confidence_tier,
                    "rule_engine_verdict": rule_verdict.verdict,
                    "note": "Low confidence — no auto-transition. Human review required.",
                },
            )

        logger.info(
            "E04-S03: Eligibility evaluated [applicant=%s, score=%.2f, "
            "proposed=%s, new_status=%s]",
            applicant_id, eligibility_score, proposed_state_str, new_status,
        )

        return {
            "applicant_id": applicant_id,
            "eligibility_score": eligibility_score,
            "confidence_tier": confidence_tier,
            "proposed_state": proposed_state_str,
            "new_status": new_status,
            "agent_request_id": result.request_id,
            "rule_engine": {
                "verdict": rule_verdict.verdict,
                "warnings": rule_verdict.warnings,
            },
        }
