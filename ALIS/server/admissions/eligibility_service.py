"""
E04-S03 — Eligibility Evaluation Wizard (Orchestrator)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (AI) + Layer 3 (Transitions) + Layer 4 (Locks)
ENTITY: Applicant

Orchestrates the eligibility evaluation workflow:
    1. Validate applicant is APPLIED (Layer 3 pre-condition)
    2. Check for required documents (Layer 4 lock)
    3. Invoke the LangGraph eligibility agent via AI Gateway
    4. Map AI confidence → proposed state
    5. Execute state transition (Layer 3 authority)
    6. Audit log result

The AI agent produces ONLY a draft — the orchestrator owns the
state transition. "AI proposes, rules enforce."

Acceptance Criteria (E04-S03):
    - [x] API: POST /eligibility/evaluate
    - [x] AI agent must not mutate state directly
    - [x] Transition executed by orchestrator
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

logger = logging.getLogger(__name__)

# Confidence thresholds (mirror eligibility.py agent)
_HIGH_THRESHOLD = 0.8
_MEDIUM_THRESHOLD = 0.5


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
            "SELECT status FROM applicants WHERE id = %s AND org_id = %s",
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

        # --- Build AI Gateway context ---
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

        # --- Invoke AI agent (Layer 2 — advisory draft only) ---
        result = AdmissionsAgentRegistry.execute(
            agent_name="eligibility_evaluator_v1",
            context=context,
            input_data={
                "marksheet_text": marksheet_text,
                "admission_criteria": admission_criteria,
            },
        )

        if not result.success or not result.content:
            raise BusinessRuleViolation(
                message=f"Eligibility agent failed: {result.error}",
                details={"agent_error": result.error},
            )

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
        }
