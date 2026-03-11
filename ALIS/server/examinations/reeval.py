"""E06-S07 — Re-evaluation Workflow

Students may request re-evaluation of a published grade.
The request routes through the E02 Approval/Quorum engine:
  - Single reviewer (faculty/exam_controller) required
  - On APPROVED: revised marks are applied and GPA recomputed
  - On REJECTED: request closed with review note
"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .grades import GradeService
from .models import ReEvalDecision, ReEvalRequest

logger = logging.getLogger(__name__)


class ReEvalService:

    # ------------------------------------------------------------------
    # S07a — Submit request
    # ------------------------------------------------------------------

    @classmethod
    def submit_request(cls, org_id: str, student_id: str,
                       req: ReEvalRequest, actor_id: str) -> dict:
        # Grade must exist, be published, and belong to this student
        grade_rows = execute_query(
            "SELECT * FROM grades WHERE id = %s AND student_id = %s AND org_id = %s",
            (req.grade_id, student_id, org_id),
        )
        if not grade_rows:
            raise NotFoundError(f"Grade {req.grade_id} not found")
        grade = dict(grade_rows[0])

        if not grade.get("is_published"):
            raise BusinessRuleViolation(message="Cannot request re-evaluation before results are published")

        # Idempotency — one pending/under-review request per grade
        pending = execute_query(
            "SELECT id FROM reeval_requests WHERE grade_id = %s AND status IN ('PENDING','UNDER_REVIEW') AND org_id = %s",
            (req.grade_id, org_id),
        )
        if pending:
            raise BusinessRuleViolation(message="A re-evaluation request is already pending for this grade")

        rid = str(uuid.uuid4())
        execute_transaction([
            (
                """
                INSERT INTO reeval_requests
                    (id, org_id, student_id, grade_id, reason, original_marks, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
                """,
                (rid, org_id, student_id, req.grade_id,
                 req.reason, grade.get("marks_obtained")),
            )
        ])

        # Route through E02 approval engine (single reviewer)
        try:
            from server.approvals.service import ApprovalService
            ApprovalService.create_request(
                org_id=org_id,
                entity_type="reeval_request",
                entity_id=rid,
                requested_by=actor_id,
                metadata={
                    "grade_id": req.grade_id,
                    "student_id": student_id,
                    "original_marks": float(grade.get("marks_obtained") or 0),
                    "reason": req.reason,
                },
            )
        except Exception as exc:
            logger.warning("ReEval: approval routing failed (non-fatal): %s", exc)

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="reeval_request", entity_id=rid, org_id=org_id,
            module="E06-S07",
            metadata={"grade_id": req.grade_id, "reason": req.reason},
        )

        logger.info("ReEval request submitted: %s by student %s", rid, student_id)
        return cls.get(org_id, rid)

    # ------------------------------------------------------------------
    # S07b — Faculty / exam controller decision
    # ------------------------------------------------------------------

    @classmethod
    def decide(cls, org_id: str, reeval_id: str,
               decision: ReEvalDecision, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM reeval_requests WHERE id = %s AND org_id = %s",
            (reeval_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Re-evaluation request {reeval_id} not found")
        reeval = dict(rows[0])

        if reeval["status"] not in ("PENDING", "UNDER_REVIEW"):
            raise BusinessRuleViolation(message=f"Request is already {reeval['status']}")

        if decision.decision not in ("REVISED", "REJECTED"):
            raise BusinessRuleViolation(message="decision must be 'REVISED' or 'REJECTED'")

        if decision.decision == "REVISED" and decision.revised_marks is None:
            raise BusinessRuleViolation(message="revised_marks required when decision is REVISED")

        execute_transaction([
            (
                """
                UPDATE reeval_requests
                SET status = %s, revised_marks = %s, review_note = %s,
                    reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s AND org_id = %s
                """,
                (
                    decision.decision,
                    decision.revised_marks,
                    decision.review_note,
                    actor_id,
                    reeval_id,
                    org_id,
                ),
            )
        ])

        if decision.decision == "REVISED":
            cls._apply_revision(
                org_id=org_id,
                grade_id=reeval["grade_id"],
                student_id=str(reeval["student_id"]),
                revised_marks=float(decision.revised_marks),
                actor_id=actor_id,
            )

        DomainEventBus.publish(DomainEvent(
            event_type="ReEvalDecided",
            entity_type="reeval_request",
            entity_id=reeval_id,
            org_id=org_id,
            payload={
                "decision": decision.decision,
                "student_id": str(reeval["student_id"]),
                "grade_id": str(reeval["grade_id"]),
                "revised_marks": decision.revised_marks,
            },
            actor_id=actor_id,
        ))

        AuditLog.log(
            action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
            entity_type="reeval_request", entity_id=reeval_id, org_id=org_id,
            module="E06-S07",
            metadata={"decision": decision.decision, "revised_marks": decision.revised_marks},
        )

        return cls.get(org_id, reeval_id)

    @classmethod
    def _apply_revision(cls, org_id: str, grade_id: str, student_id: str,
                        revised_marks: float, actor_id: str) -> None:
        """Re-run grade computation with revised marks and recompute SGPA/CGPA."""
        grade_rows = execute_query(
            "SELECT * FROM grades WHERE id = %s AND org_id = %s",
            (grade_id, org_id),
        )
        if not grade_rows:
            return
        grade = dict(grade_rows[0])

        max_marks  = int(grade["max_marks"])
        pass_marks_rows = execute_query(
            "SELECT pass_marks FROM exam_schedules WHERE id = %s",
            (grade["exam_schedule_id"],),
        )
        pass_marks = int(pass_marks_rows[0]["pass_marks"]) if pass_marks_rows else 40

        from .grades import _compute_grade, GradeService
        grade_table = GradeService._load_grade_table(org_id)
        new_grade, new_pts, new_is_pass = _compute_grade(
            revised_marks, max_marks, pass_marks, grade_table
        )

        execute_transaction([
            (
                """
                UPDATE grades
                SET marks_obtained = %s, grade = %s, grade_points = %s,
                    is_pass = %s, entered_by = %s, entered_at = NOW()
                WHERE id = %s AND org_id = %s
                """,
                (revised_marks, new_grade, new_pts, new_is_pass, actor_id, grade_id, org_id),
            )
        ])

        # Recompute semester result
        try:
            GradeService.compute_semester_result(
                org_id=org_id,
                student_id=student_id,
                academic_year=str(grade["academic_year"]),
                semester=int(grade["semester"]),
                actor_id=actor_id,
            )
        except Exception as exc:
            logger.warning("ReEval: GPA recompute failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, org_id: str, reeval_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM reeval_requests WHERE id = %s AND org_id = %s",
            (reeval_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Re-evaluation request {reeval_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM reeval_requests WHERE student_id = %s AND org_id = %s ORDER BY created_at DESC",
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_pending(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM reeval_requests WHERE org_id = %s AND status IN ('PENDING','UNDER_REVIEW') ORDER BY created_at",
            (org_id,),
        )
        return [dict(r) for r in rows]
