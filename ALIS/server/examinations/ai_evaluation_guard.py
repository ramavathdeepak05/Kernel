"""EC-EXM-05 — AI Hallucination Guard on Descriptive Evaluation

All LLM-generated scores stored as ai_draft_score (never final directly).
Faculty must confirm or override before scores become final.

Thresholds — all from policy_engine (R1, never literals):
  examinations.ai_confidence_threshold       default 0.6
  examinations.ai_deviation_threshold        default 20.0 (%)
  examinations.rubber_stamp_threshold        default 95.0 (%) — anomaly if >95% accepted
  examinations.ai_batch_rubber_stamp_alert   default 10   (min samples to trigger rubber stamp check)

If confidence < threshold → route to faculty review WITHOUT showing AI score
(prevents anchoring bias).

If faculty final_score deviates > deviation threshold from AI draft → require
override_reason. Store policy_version_id on every AnswerEvaluationRecord (R12).
"""

import logging
import uuid
from typing import Optional

from pydantic import BaseModel

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class AnswerEvaluationRecord(BaseModel):
    id: str
    org_id: str
    answer_script_id: str
    question_id: str
    max_marks: float
    ai_draft_score: Optional[float]
    ai_confidence: Optional[float]
    faculty_final_score: Optional[float]
    override_reason: Optional[str]
    policy_version_id: Optional[str]
    status: str  # AI_PENDING | FACULTY_REVIEW | CONFIRMED | OVERRIDE_CONFIRMED


class AIEvaluationGuardService:

    # ------------------------------------------------------------------
    # Record AI draft
    # ------------------------------------------------------------------

    @classmethod
    def submit_ai_draft(
        cls,
        org_id: str,
        answer_script_id: str,
        question_id: str,
        max_marks: float,
        ai_draft_score: float,
        ai_confidence: float,
        actor_id: str,
    ) -> dict:
        """Save AI draft score and route appropriately.

        Below-threshold confidence: route to FACULTY_REVIEW without showing score.
        Above-threshold: save as AI_PENDING (faculty confirms or overrides).
        """
        # R1 — all thresholds from policy engine
        confidence_threshold = float(policy_engine.get_value(
            "examinations.ai_confidence_threshold", org_id, 0.6
        ))
        policy_version = policy_engine.get_version(
            "examinations.ai_confidence_threshold", org_id
        )

        record_id = str(uuid.uuid4())

        if ai_confidence < confidence_threshold:
            # Low confidence: route to faculty WITHOUT showing AI score
            status = "FACULTY_REVIEW"
            # Do NOT store ai_draft_score in the returned payload — prevents anchoring
            store_score = None
        else:
            status = "AI_PENDING"
            store_score = ai_draft_score

        execute_transaction([("""
            INSERT INTO answer_evaluation_records
                (id, org_id, answer_script_id, question_id, max_marks,
                 ai_draft_score, ai_confidence, status, policy_version_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (answer_script_id, question_id) DO UPDATE SET
                ai_draft_score    = EXCLUDED.ai_draft_score,
                ai_confidence     = EXCLUDED.ai_confidence,
                status            = EXCLUDED.status,
                policy_version_id = EXCLUDED.policy_version_id
        """, (
            record_id, org_id, answer_script_id, question_id, max_marks,
            store_score, ai_confidence, status, policy_version,
        ))])

        if status == "FACULTY_REVIEW":
            DomainEventBus.publish(DomainEvent(
                event_type="examinations.low_confidence_answer_flagged",
                org_id=org_id,
                payload={
                    "record_id": record_id,
                    "answer_script_id": answer_script_id,
                    "question_id": question_id,
                    "reason": "ai_confidence_below_threshold",
                    # NOTE: ai_draft_score intentionally omitted from event payload
                },
            ))

        return {
            "record_id": record_id,
            "status": status,
            "requires_faculty_review": status == "FACULTY_REVIEW",
            # Only include score if above threshold
            "ai_draft_score": store_score if status != "FACULTY_REVIEW" else None,
        }

    # ------------------------------------------------------------------
    # Faculty confirmation / override
    # ------------------------------------------------------------------

    @classmethod
    def confirm_score(
        cls,
        org_id: str,
        record_id: str,
        faculty_final_score: float,
        override_reason: Optional[str],
        actor_id: str,
    ) -> dict:
        """Faculty confirms or overrides the AI draft score.

        If deviation > deviation_threshold, override_reason is mandatory (R1).
        """
        rows = execute_query(
            """
            SELECT id, ai_draft_score, max_marks, status, policy_version_id
            FROM answer_evaluation_records
            WHERE id = %s AND org_id = %s
            """,
            (record_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Evaluation record {record_id} not found")

        rec = rows[0]
        if rec["status"] not in ("AI_PENDING", "FACULTY_REVIEW"):
            raise BusinessRuleViolation(
                f"Score already confirmed (status: {rec['status']})"
            )

        if faculty_final_score < 0 or faculty_final_score > float(rec.get("max_marks", 100)):
            raise BusinessRuleViolation(
                f"faculty_final_score must be between 0 and {rec['max_marks']}"
            )

        deviation_threshold = float(policy_engine.get_value(
            "examinations.ai_deviation_threshold", org_id, 20.0
        ))

        # Check deviation only when AI draft was actually stored (not suppressed)
        ai_draft = rec["ai_draft_score"]
        if ai_draft is not None:
            max_marks = float(rec.get("max_marks") or 100)
            if max_marks > 0:
                deviation_pct = abs(faculty_final_score - float(ai_draft)) / max_marks * 100
            else:
                deviation_pct = 0.0

            if deviation_pct > deviation_threshold and not override_reason:
                raise BusinessRuleViolation(
                    f"Deviation {deviation_pct:.1f}% exceeds threshold "
                    f"{deviation_threshold}% — override_reason is required"
                )

        final_status = "OVERRIDE_CONFIRMED" if (ai_draft is not None and override_reason) else "CONFIRMED"

        execute_transaction([("""
            UPDATE answer_evaluation_records
            SET faculty_final_score = %s,
                override_reason     = %s,
                status              = %s,
                confirmed_by        = %s,
                confirmed_at        = NOW()
            WHERE id = %s AND org_id = %s
        """, (
            faculty_final_score, override_reason, final_status,
            actor_id, record_id, org_id,
        ))])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="answer_evaluation",
            resource_id=record_id,
            detail={
                "faculty_final_score": faculty_final_score,
                "override_reason": override_reason,
                "status": final_status,
                "policy_version_id": str(rec.get("policy_version_id") or ""),
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="examinations.answer_score_confirmed",
            org_id=org_id,
            payload={
                "record_id": record_id,
                "faculty_final_score": faculty_final_score,
                "status": final_status,
            },
        ))

        return {
            "record_id": record_id,
            "faculty_final_score": faculty_final_score,
            "status": final_status,
        }

    # ------------------------------------------------------------------
    # Rubber stamp anomaly check
    # ------------------------------------------------------------------

    @classmethod
    def check_rubber_stamp_anomaly(cls, org_id: str, batch_id: str) -> dict:
        """Check if faculty are rubber-stamping AI scores without real review.

        Triggers alert if acceptance rate > rubber_stamp_threshold (R1).
        """
        rubber_stamp_threshold = float(policy_engine.get_value(
            "examinations.rubber_stamp_threshold", org_id, 95.0
        ))
        min_samples = int(policy_engine.get_value(
            "examinations.ai_batch_rubber_stamp_alert", org_id, 10
        ))

        rows = execute_query("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'CONFIRMED' AND override_reason IS NULL) AS rubber_stamped,
                COUNT(*) FILTER (WHERE status = 'OVERRIDE_CONFIRMED') AS overridden
            FROM answer_evaluation_records
            WHERE org_id = %s
              AND answer_script_id IN (
                  SELECT id FROM answer_scripts WHERE batch_id = %s
              )
              AND status IN ('CONFIRMED', 'OVERRIDE_CONFIRMED')
        """, (org_id, batch_id))

        if not rows or int(rows[0]["total"] or 0) < min_samples:
            return {"anomaly": False, "reason": "insufficient_samples"}

        total = int(rows[0]["total"])
        stamped = int(rows[0]["rubber_stamped"] or 0)
        acceptance_rate = stamped / total * 100 if total > 0 else 0

        anomaly = acceptance_rate > rubber_stamp_threshold

        if anomaly:
            DomainEventBus.publish(DomainEvent(
                event_type="examinations.rubber_stamp_anomaly",
                org_id=org_id,
                payload={
                    "batch_id": batch_id,
                    "acceptance_rate_pct": round(acceptance_rate, 1),
                    "threshold_pct": rubber_stamp_threshold,
                    "total_records": total,
                    "rubber_stamped": stamped,
                },
            ))

        return {
            "anomaly": anomaly,
            "acceptance_rate_pct": round(acceptance_rate, 1),
            "threshold_pct": rubber_stamp_threshold,
            "total_records": total,
            "rubber_stamped": stamped,
        }

    # ------------------------------------------------------------------
    # Faculty review queue
    # ------------------------------------------------------------------

    @classmethod
    def get_faculty_review_queue(cls, org_id: str, faculty_id: str) -> list:
        """Return pending evaluation records for faculty to confirm."""
        return execute_query("""
            SELECT r.id, r.answer_script_id, r.question_id, r.max_marks,
                   r.ai_confidence, r.status,
                   -- Only show AI score if status = AI_PENDING (not FACULTY_REVIEW)
                   CASE WHEN r.status = 'AI_PENDING' THEN r.ai_draft_score ELSE NULL END AS ai_draft_score
            FROM answer_evaluation_records r
            JOIN answer_scripts s ON s.id = r.answer_script_id
            WHERE r.org_id = %s
              AND s.assigned_evaluator = %s
              AND r.status IN ('AI_PENDING', 'FACULTY_REVIEW')
            ORDER BY r.created_at ASC
        """, (org_id, faculty_id))
