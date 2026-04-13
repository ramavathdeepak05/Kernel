"""
M1 Automation Pipeline — E04-S13

Orchestrates the full admissions lifecycle automatically:

    intake → dedup → eligibility eval → policy decision
    → (if REVIEW: enqueue + wait)
    → counsellor assign → offer letter
    → (payment wait)
    → confirm → enroll → StudentEnrolled event

Each step is idempotent — re-running the pipeline from any point is safe.
The pipeline is driven by Celery tasks in server/tasks/admissions.py.
This module contains the pure orchestration logic (no Celery coupling).
"""

from __future__ import annotations

import logging

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation
from server.core.state_registry import StudentState
from server.db_service import execute_query

from .policy_engine import PolicyEvaluator, PolicyOutcome
from .review_queue import ReviewQueue, ReviewStatus

logger = logging.getLogger(__name__)


class PipelineResult:
    """Outcome of one pipeline step."""

    def __init__(self, status: str, next_step: str | None = None, message: str = ""):
        self.status = status  # "advanced" | "blocked" | "completed" | "rejected"
        self.next_step = next_step
        self.message = message

    def __repr__(self) -> str:
        return f"PipelineResult(status={self.status}, next={self.next_step})"


class AdmissionsPipeline:
    """
    Stateless orchestrator for the M1 admissions lifecycle.

    Each `run_*` method handles one pipeline step.
    The Celery task calls `advance()` which routes to the right step
    based on the applicant's current status.
    """

    @classmethod
    def advance(
        cls, applicant_id: str, org_id: str, actor_id: str = "system"
    ) -> PipelineResult:
        """
        Route to the correct pipeline step based on current applicant status.
        Entry point for the Celery task.
        """
        rows = execute_query(
            "SELECT status, metadata FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Applicant {applicant_id} not found")

        status = rows[0]["status"]
        metadata = rows[0].get("metadata") or {}

        logger.info("Pipeline.advance: applicant=%s status=%s", applicant_id, status)

        step_map = {
            StudentState.APPLIED.value: cls._step_evaluate_eligibility,
            StudentState.ELIGIBLE.value: cls._step_assign_counsellor,
            StudentState.PROVISIONALLY_ELIGIBLE.value: cls._step_check_review_outcome,
            StudentState.ADMITTED.value: cls._step_enroll,
        }

        handler = step_map.get(status)
        if not handler:
            return PipelineResult(
                status="blocked",
                message=f"No pipeline step defined for status={status}",
            )

        return handler(applicant_id, org_id, actor_id, metadata)

    # ------------------------------------------------------------------
    # Step 1: Evaluate eligibility → policy decision
    # ------------------------------------------------------------------

    @classmethod
    def _step_evaluate_eligibility(
        cls, applicant_id: str, org_id: str, actor_id: str, metadata: dict
    ) -> PipelineResult:
        """Run policy evaluation; transition applicant to ELIGIBLE or flag for review."""
        from .service import ApplicantService

        academic_pct = metadata.get("academic_percentage")
        entrance_score = metadata.get("entrance_score")

        # Check doc completeness
        docs = execute_query(
            "SELECT COUNT(*) AS n FROM application_documents WHERE applicant_id = %s AND org_id = %s AND is_verified = TRUE",
            (applicant_id, org_id),
        )
        docs_complete = (docs[0]["n"] > 0) if docs else False

        decision = PolicyEvaluator.evaluate(
            org_id=org_id,
            academic_percentage=float(academic_pct)
            if academic_pct is not None
            else None,
            entrance_score=float(entrance_score)
            if entrance_score is not None
            else None,
            docs_complete=docs_complete,
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="applicant",
            entity_id=applicant_id,
            org_id=org_id,
            module="E04-S13",
            metadata={
                "pipeline_step": "eligibility_eval",
                "outcome": decision.outcome.value,
                "reason": decision.reason,
                "flags": decision.flags,
            },
        )

        if decision.outcome == PolicyOutcome.AUTO_REJECT:
            ApplicantService.transition_state(
                applicant_id, StudentState.NOT_ELIGIBLE.value, org_id, actor_id
            )
            cls._publish(
                org_id, "ApplicantRejected", applicant_id, {"reason": decision.reason}
            )
            return PipelineResult(status="rejected", message=decision.reason)

        if decision.outcome == PolicyOutcome.REVIEW_REQUIRED:
            ApplicantService.transition_state(
                applicant_id,
                StudentState.PROVISIONALLY_ELIGIBLE.value,
                org_id,
                actor_id,
            )
            ReviewQueue.enqueue(
                org_id=org_id,
                entity_type="applicant",
                entity_id=applicant_id,
                decision=decision,
                actor_id=actor_id,
            )
            cls._publish(
                org_id,
                "ApplicantFlaggedForReview",
                applicant_id,
                {"reason": decision.reason, "flags": decision.flags},
            )
            return PipelineResult(
                status="blocked",
                message="Flagged for staff review",
                next_step="await_review",
            )

        # AUTO_PROCEED
        ApplicantService.transition_state(
            applicant_id, StudentState.ELIGIBLE.value, org_id, actor_id
        )
        cls._publish(
            org_id, "ApplicantEligible", applicant_id, {"flags": decision.flags}
        )
        return PipelineResult(status="advanced", next_step="assign_counsellor")

    # ------------------------------------------------------------------
    # Step 2: Check review outcome (for PROVISIONALLY_ELIGIBLE applicants)
    # ------------------------------------------------------------------

    @classmethod
    def _step_check_review_outcome(
        cls, applicant_id: str, org_id: str, actor_id: str, metadata: dict
    ) -> PipelineResult:
        """Resume pipeline after staff has decided on a review item."""
        from .service import ApplicantService

        rows = execute_query(
            "SELECT status, decision FROM review_items WHERE entity_id = %s AND org_id = %s ORDER BY created_at DESC LIMIT 1",
            (applicant_id, org_id),
        )
        if not rows:
            return PipelineResult(
                status="blocked", message="No review item found — awaiting staff"
            )

        review_status = rows[0]["status"]
        if review_status == ReviewStatus.PENDING:
            return PipelineResult(
                status="blocked", message="Awaiting staff review decision"
            )

        if review_status == ReviewStatus.REJECTED:
            ApplicantService.transition_state(
                applicant_id, StudentState.NOT_ELIGIBLE.value, org_id, actor_id
            )
            cls._publish(
                org_id,
                "ApplicantRejected",
                applicant_id,
                {"reason": "Staff review rejected"},
            )
            return PipelineResult(status="rejected", message="Rejected by staff review")

        # APPROVED → move to ELIGIBLE and continue
        ApplicantService.transition_state(
            applicant_id, StudentState.ELIGIBLE.value, org_id, actor_id
        )
        cls._publish(
            org_id, "ApplicantEligible", applicant_id, {"via": "staff_review_approved"}
        )
        return PipelineResult(status="advanced", next_step="assign_counsellor")

    # ------------------------------------------------------------------
    # Step 3: Assign counsellor + generate offer letter
    # ------------------------------------------------------------------

    @classmethod
    def _step_assign_counsellor(
        cls, applicant_id: str, org_id: str, actor_id: str, metadata: dict
    ) -> PipelineResult:
        """Auto-assign counsellor and generate offer letter for eligible applicants."""
        from server.db_service import execute_query as eq

        from .counsellor_allocation import CounsellorAllocationService
        from .models import CounsellorAssignRequest, OfferLetterGenerateRequest
        from .offer_letter import OfferLetterService

        # Skip if already assigned
        existing_assign = eq(
            "SELECT id FROM counsellor_assignments WHERE applicant_id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not existing_assign:
            try:
                CounsellorAllocationService.assign(
                    request=CounsellorAssignRequest(applicant_id=applicant_id),
                    org_id=org_id,
                    actor_id=actor_id,
                    actor_role="SYSTEM",
                )
            except Exception as exc:
                logger.warning(
                    "Pipeline: counsellor assign failed (non-fatal): %s", exc
                )

        # Skip if offer already generated
        existing_offer = eq(
            "SELECT id FROM offer_letters WHERE applicant_id = %s AND org_id = %s AND is_valid = TRUE",
            (applicant_id, org_id),
        )
        if not existing_offer:
            applicant = eq("SELECT * FROM applicants WHERE id = %s", (applicant_id,))
            if applicant:
                from datetime import date

                year = date.today().year
                academic_year = f"{year}-{year + 1}"
                try:
                    OfferLetterService.generate(
                        request=OfferLetterGenerateRequest(
                            applicant_id=applicant_id,
                            program_name=applicant[0].get(
                                "intended_program", "General"
                            ),
                            academic_year=academic_year,
                        ),
                        org_id=org_id,
                        actor_id=actor_id,
                    )
                except Exception as exc:
                    logger.warning("Pipeline: offer letter failed (non-fatal): %s", exc)

        cls._publish(org_id, "OfferLetterIssued", applicant_id, {})
        return PipelineResult(
            status="blocked",
            next_step="await_payment",
            message="Offer letter issued — awaiting fee payment",
        )

    # ------------------------------------------------------------------
    # Step 4: Enroll (called after payment confirmation)
    # ------------------------------------------------------------------

    @classmethod
    def _step_enroll(
        cls, applicant_id: str, org_id: str, actor_id: str, metadata: dict
    ) -> PipelineResult:
        """Trigger enrollment handover for an ADMITTED applicant."""
        from .enrollment_handover import EnrollmentHandoverService
        from .models import EnrollmentHandoverRequest

        try:
            student = EnrollmentHandoverService.enroll(
                request=EnrollmentHandoverRequest(applicant_id=applicant_id),
                org_id=org_id,
                actor_id=actor_id,
            )
            cls._publish(
                org_id,
                "StudentEnrolled",
                applicant_id,
                {
                    "student_id": student.id,
                    "roll_number": student.roll_number,
                    "program": student.program,
                },
            )
            return PipelineResult(
                status="completed", message=f"Student enrolled: {student.roll_number}"
            )
        except Exception as exc:
            logger.error("Pipeline: enrollment failed for %s: %s", applicant_id, exc)
            return PipelineResult(status="blocked", message=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _publish(
        cls, org_id: str, event_type: str, applicant_id: str, payload: dict
    ) -> None:
        try:
            DomainEventBus.publish(
                DomainEvent(
                    event_type=event_type,
                    entity_type="applicant",
                    entity_id=applicant_id,
                    org_id=org_id,
                    payload=payload,
                    actor_id="system",
                )
            )
        except Exception as exc:
            logger.warning("Pipeline: event publish failed (non-fatal): %s", exc)
