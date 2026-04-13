"""
Policy Evaluation Engine — E04-S11

Evaluates an applicant's data against the institution's configured policies
and produces a deterministic decision:

    AUTO_PROCEED         — meets all thresholds → pipeline continues automatically
    REVIEW_REQUIRED      — borderline (in tolerance band) → flagged for staff review
    AUTO_REJECT          — fails hard requirements → pipeline halted

Design principles:
- Pure function — no side effects (no DB writes, no state transitions)
- All thresholds come from PolicyStore (configurable per org, never hardcoded)
- Returns a structured PolicyDecision with full reasoning for audit trail
- Used by the automation pipeline (E04-S13) and the eligibility endpoint
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .policy_store import PolicyKey, PolicyStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


class PolicyOutcome(str, Enum):
    AUTO_PROCEED = "AUTO_PROCEED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    AUTO_REJECT = "AUTO_REJECT"


@dataclass
class PolicyDecision:
    outcome: PolicyOutcome
    reason: str
    flags: list[str] = field(default_factory=list)
    # Which policy key triggered the decision (for the review queue)
    trigger_key: str | None = None
    trigger_value: Any | None = None  # the configured threshold
    actual_value: Any | None = None  # the applicant's actual value

    @property
    def is_auto(self) -> bool:
        return self.outcome == PolicyOutcome.AUTO_PROCEED

    @property
    def needs_review(self) -> bool:
        return self.outcome == PolicyOutcome.REVIEW_REQUIRED

    @property
    def is_rejected(self) -> bool:
        return self.outcome == PolicyOutcome.AUTO_REJECT


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class PolicyEvaluator:
    """
    Stateless policy evaluator.

    Usage:
        decision = PolicyEvaluator.evaluate(
            org_id="abc",
            academic_percentage=54.0,
            entrance_score=65.0,
            docs_complete=True,
        )
        if decision.needs_review:
            ReviewQueue.enqueue(applicant_id, decision, org_id)
        elif decision.is_rejected:
            ApplicantService.transition_state(..., NOT_ELIGIBLE)
    """

    @classmethod
    def evaluate(
        cls,
        org_id: str,
        academic_percentage: float | None = None,
        entrance_score: float | None = None,
        docs_complete: bool | None = None,
    ) -> PolicyDecision:
        """
        Evaluate applicant eligibility criteria against org policies.

        Returns AUTO_PROCEED, REVIEW_REQUIRED, or AUTO_REJECT.
        Evaluation order: hard rejects first → borderline review → approve.
        """
        flags: list[str] = []

        # ------------------------------------------------------------------
        # Load policy thresholds for this org
        # ------------------------------------------------------------------
        min_academic = float(
            PolicyStore.get(org_id, PolicyKey.MIN_ACADEMIC_PCT) or 55.0
        )
        review_lower = float(
            PolicyStore.get(org_id, PolicyKey.REVIEW_BAND_LOWER) or 50.0
        )
        min_entrance = float(
            PolicyStore.get(org_id, PolicyKey.MIN_ENTRANCE_SCORE) or 40.0
        )
        docs_required = bool(PolicyStore.get(org_id, PolicyKey.DOCS_REQUIRED_FOR_OFFER))

        # ------------------------------------------------------------------
        # 1. Hard REJECT — below the review band entirely
        # ------------------------------------------------------------------
        if academic_percentage is not None and academic_percentage < review_lower:
            return PolicyDecision(
                outcome=PolicyOutcome.AUTO_REJECT,
                reason=f"Academic percentage {academic_percentage:.1f}% is below minimum review threshold of {review_lower:.1f}%",
                flags=["LOW_ACADEMICS"],
                trigger_key=PolicyKey.REVIEW_BAND_LOWER,
                trigger_value=review_lower,
                actual_value=academic_percentage,
            )

        if entrance_score is not None and entrance_score < (min_entrance * 0.5):
            # Below 50% of the entrance threshold → hard reject
            return PolicyDecision(
                outcome=PolicyOutcome.AUTO_REJECT,
                reason=f"Entrance score {entrance_score:.1f} is critically below minimum of {min_entrance:.1f}",
                flags=["LOW_ENTRANCE_SCORE"],
                trigger_key=PolicyKey.MIN_ENTRANCE_SCORE,
                trigger_value=min_entrance,
                actual_value=entrance_score,
            )

        # ------------------------------------------------------------------
        # 2. REVIEW band — meets reject floor but below the proceed threshold
        # ------------------------------------------------------------------
        if academic_percentage is not None and academic_percentage < min_academic:
            flags.append("BORDERLINE_ACADEMICS")
            return PolicyDecision(
                outcome=PolicyOutcome.REVIEW_REQUIRED,
                reason=(
                    f"Academic percentage {academic_percentage:.1f}% is between review band "
                    f"({review_lower:.1f}%–{min_academic:.1f}%) — requires staff review"
                ),
                flags=flags,
                trigger_key=PolicyKey.MIN_ACADEMIC_PCT,
                trigger_value=min_academic,
                actual_value=academic_percentage,
            )

        if entrance_score is not None and entrance_score < min_entrance:
            flags.append("BORDERLINE_ENTRANCE_SCORE")
            return PolicyDecision(
                outcome=PolicyOutcome.REVIEW_REQUIRED,
                reason=f"Entrance score {entrance_score:.1f} is below minimum {min_entrance:.1f} — requires staff review",
                flags=flags,
                trigger_key=PolicyKey.MIN_ENTRANCE_SCORE,
                trigger_value=min_entrance,
                actual_value=entrance_score,
            )

        # ------------------------------------------------------------------
        # 3. Document completeness gate (REVIEW if docs missing, not reject)
        # ------------------------------------------------------------------
        if docs_required and docs_complete is False:
            flags.append("DOCS_INCOMPLETE")
            return PolicyDecision(
                outcome=PolicyOutcome.REVIEW_REQUIRED,
                reason="Required documents are not yet verified — requires staff review",
                flags=flags,
                trigger_key=PolicyKey.DOCS_REQUIRED_FOR_OFFER,
                trigger_value=True,
                actual_value=False,
            )

        # ------------------------------------------------------------------
        # 4. All checks passed → AUTO_PROCEED
        # ------------------------------------------------------------------
        if academic_percentage is not None:
            flags.append(f"ACADEMICS_OK ({academic_percentage:.1f}%)")
        if entrance_score is not None:
            flags.append(f"ENTRANCE_OK ({entrance_score:.1f})")

        return PolicyDecision(
            outcome=PolicyOutcome.AUTO_PROCEED,
            reason="All eligibility criteria met",
            flags=flags,
        )
