"""
ALIS Human-in-the-Loop Enforcement — E03-S09

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions) + Layer 3 (State Machines)
ENTITY: HITLEnforcer

Ensures that AI outputs are never auto-committed to institutional state.
All AI decisions must pass through one of three dispositions:

    AUTO_PROCEED   — High confidence, low-risk: logged but no human gate
    REVIEW_REQUIRED — Medium confidence or high-risk: routed to approval queue
    ESCALATE       — Low confidence or critical domain: requires senior authority

Acceptance Criteria (E03-S09):
    - [x] AI outputs never auto-commit
    - [x] Explicit approval states
    - [x] Clear handoff points
    - [x] Audit trail preserved
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from .audit import AuditLog, AuditAction
from .exceptions import HITLRequiredError

logger = logging.getLogger(__name__)


# =============================================================================
# HITL CONFIGURATION
# =============================================================================

# Confidence thresholds for gate routing.
# These align with ConfidenceTier boundaries in ai_gateway.py.
_THRESHOLD_AUTO_PROCEED: float = 0.85    # HIGH-confidence auto-proceed floor
_THRESHOLD_ESCALATE: float = 0.40        # Below this → mandatory escalation

# Domains that always require REVIEW regardless of confidence.
# These are institutional-critical domains where any AI output must be seen
# by a human before it influences state.
_ALWAYS_REVIEW_DOMAINS: Set[str] = {
    "scholarship",       # Scholarship approval
    "disciplinary",      # Disciplinary summaries
    "revaluation",       # Revaluation grading
    "fee_waiver",        # Financial waivers
    "grade_override",    # Grade amendments
    "admission_final",   # Final admission decisions
    "transcript",        # Official transcripts
}

# Domains that require ESCALATION (senior authority) even on high confidence.
_ALWAYS_ESCALATE_DOMAINS: Set[str] = {
    "disciplinary",      # Disciplinary actions require senior authority
    "grade_override",    # Grade overrides require academic authority
}


# =============================================================================
# HITL DISPOSITION
# =============================================================================

class HITLDisposition(str, Enum):
    """
    Outcome of the HITL gate evaluation.

    AUTO_PROCEED    — AI output may proceed without human review.
                      Logged but no approval queue entry created.
    REVIEW_REQUIRED — AI output must enter the approval queue.
                      HITLRequiredError is raised to signal the handoff.
    ESCALATE        — AI output requires senior authority review.
                      HITLRequiredError with escalation flag is raised.
    """
    AUTO_PROCEED = "auto_proceed"
    REVIEW_REQUIRED = "review_required"
    ESCALATE = "escalate"


# =============================================================================
# HITL RESULT
# =============================================================================

@dataclass
class HITLResult:
    """
    Result of a HITL gate evaluation.

    Attributes:
        disposition:     The routing decision for this AI output.
        confidence_score: The AI confidence score that drove the decision.
        domain:          The institutional domain context.
        reasons:         Human-readable list of reasons for the disposition.
        review_id:       Unique ID for the pending review (if applicable).
        metadata:        Additional context for the approval workflow.
    """
    disposition: HITLDisposition
    confidence_score: float
    domain: str
    reasons: List[str] = field(default_factory=list)
    review_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# HITL ENFORCER
# =============================================================================

class HITLEnforcer:
    """
    Enforces Human-in-the-Loop approval routing for all AI outputs.

    Called by agents after InstrumentedLLM.invoke() returns a validated
    AIResponseSchema. The enforcer decides whether the output can proceed
    automatically or must be queued for human review.

    Design Invariants:
    - AI outputs NEVER auto-commit to state (E03-S09)
    - Approval states are always explicit and logged
    - Confidence score + domain together determine disposition
    - Critical domains always require human review regardless of confidence

    Usage:
        result = HITLEnforcer.evaluate(
            confidence_score=validated_output.confidence_score,
            domain="scholarship",
            actor_id=context.actor_id,
            org_id=context.org_id,
            ai_output=validated_output.model_dump(),
            request_id=llm_result.request_id,
        )
        # If domain requires review, HITLRequiredError is raised above
        # If AUTO_PROCEED, the result is returned and caller may continue
    """

    @classmethod
    def evaluate(
        cls,
        confidence_score: float,
        domain: str,
        actor_id: str,
        org_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        module: Optional[str] = None,
        wizard: Optional[str] = None,
        request_id: Optional[str] = None,
        ai_output: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HITLResult:
        """
        Evaluate AI output against HITL policy and route appropriately.

        Args:
            confidence_score: AI confidence score (0.0 – 1.0)
            domain:           Institutional domain (e.g., "scholarship")
            actor_id:         AI agent or system actor ID
            org_id:           Tenant scope
            actor_role:       Actor role string for audit
            module:           Module context (M1, M2, …)
            wizard:           Wizard context
            request_id:       Originating gateway request ID
            ai_output:        The AI output payload (for audit/handoff)
            metadata:         Additional context to include in review record

        Returns:
            HITLResult with disposition == AUTO_PROCEED if gate is passed.

        Raises:
            HITLRequiredError: If disposition is REVIEW_REQUIRED or ESCALATE.
                               Callers MUST catch this and route to the
                               approval workflow — they must NOT suppress it.
        """
        reasons: List[str] = []
        domain_lower = domain.lower()

        # --- Gate 1: Always-escalate domains ---
        if domain_lower in _ALWAYS_ESCALATE_DOMAINS:
            reasons.append(
                f"Domain '{domain}' unconditionally requires senior authority escalation"
            )
            disposition = HITLDisposition.ESCALATE

        # --- Gate 2: Always-review domains ---
        elif domain_lower in _ALWAYS_REVIEW_DOMAINS:
            reasons.append(
                f"Domain '{domain}' unconditionally requires human review"
            )
            disposition = HITLDisposition.REVIEW_REQUIRED

        # --- Gate 3: Low confidence → escalate ---
        elif confidence_score < _THRESHOLD_ESCALATE:
            reasons.append(
                f"Confidence score {confidence_score:.2f} is below escalation "
                f"threshold {_THRESHOLD_ESCALATE:.2f}"
            )
            disposition = HITLDisposition.ESCALATE

        # --- Gate 4: Medium confidence → review ---
        elif confidence_score < _THRESHOLD_AUTO_PROCEED:
            reasons.append(
                f"Confidence score {confidence_score:.2f} is below auto-proceed "
                f"threshold {_THRESHOLD_AUTO_PROCEED:.2f} — human review required"
            )
            disposition = HITLDisposition.REVIEW_REQUIRED

        # --- Gate 5: High confidence, non-critical domain → auto-proceed ---
        else:
            reasons.append(
                f"Confidence score {confidence_score:.2f} meets auto-proceed "
                f"threshold {_THRESHOLD_AUTO_PROCEED:.2f}"
            )
            disposition = HITLDisposition.AUTO_PROCEED

        result = HITLResult(
            disposition=disposition,
            confidence_score=confidence_score,
            domain=domain,
            reasons=reasons,
            metadata={
                **(metadata or {}),
                "request_id": request_id,
                "ai_output_summary": _summarise_output(ai_output),
            },
        )

        # --- Audit: log every HITL decision ---
        cls._audit(result, actor_id, actor_role, org_id, module, wizard)

        # --- Route non-auto decisions ---
        if disposition == HITLDisposition.AUTO_PROCEED:
            logger.info(
                "E03-S09: HITL AUTO_PROCEED [domain=%s, score=%.2f, review_id=%s]",
                domain, confidence_score, result.review_id,
            )
            return result

        # REVIEW_REQUIRED or ESCALATE — raise handoff signal
        hitl_decision = disposition.value
        logger.warning(
            "E03-S09: HITL %s [domain=%s, score=%.2f, review_id=%s]",
            hitl_decision.upper(), domain, confidence_score, result.review_id,
        )
        raise HITLRequiredError(
            message=(
                f"AI output requires human review before proceeding "
                f"(domain={domain}, disposition={hitl_decision})"
            ),
            hitl_decision=hitl_decision,
            details={
                "review_id": result.review_id,
                "disposition": hitl_decision,
                "domain": domain,
                "confidence_score": confidence_score,
                "reasons": reasons,
                "metadata": result.metadata,
            },
        )

    @classmethod
    def _audit(
        cls,
        result: HITLResult,
        actor_id: str,
        actor_role: Optional[str],
        org_id: Optional[str],
        module: Optional[str],
        wizard: Optional[str],
    ) -> None:
        """Log the HITL disposition to the immutable audit ledger."""
        if result.disposition == HITLDisposition.AUTO_PROCEED:
            action = AuditAction.HITL_AUTO_PROCEED
        elif result.disposition == HITLDisposition.ESCALATE:
            action = AuditAction.HITL_ESCALATED
        else:
            action = AuditAction.HITL_REVIEW_REQUIRED

        AuditLog.log(
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="ai_hitl",
            entity_id=result.review_id,
            org_id=org_id,
            module=module,
            wizard=wizard,
            success=True,
            metadata={
                "disposition": result.disposition.value,
                "confidence_score": result.confidence_score,
                "domain": result.domain,
                "reasons": result.reasons,
                **result.metadata,
            },
        )


# =============================================================================
# HELPERS
# =============================================================================

def _summarise_output(ai_output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract a minimal summary of AI output for audit/handoff metadata.

    We include only non-sensitive fields — the full output is stored
    separately in the AI_INVOCATION audit entry.
    """
    if not ai_output:
        return {}
    return {
        "decision": str(ai_output.get("decision", ""))[:200],
        "confidence_score": ai_output.get("confidence_score"),
        "confidence_tier": ai_output.get("confidence_tier"),
        "state_impact": ai_output.get("state_impact"),
    }
