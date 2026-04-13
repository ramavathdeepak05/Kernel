"""EC-ADM-02 — State Counselling Late Joiners: CatchUp Cohort Workflow

Handles students who join mid-semester via state counselling.
- All sessions before joining_date marked EXCUSED_LATE_JOINER
- Compressed assignment deadlines (past-due → single 2-week deadline)
- Standard penalty rules suppressed for excused period
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class CatchUpCohortWorkflow:
    @classmethod
    def trigger(
        cls,
        student_id: str,
        joining_date: str,  # ISO date string
        org_id: str,
        actor_id: str = "system",
    ) -> dict:
        """
        1. Pre-mark all sessions before joining_date as EXCUSED_LATE_JOINER.
        2. Compute elapsed weeks since semester start.
        3. Consolidate all past-due assignments into one deadline (2 weeks from joining).
        4. Suppress late penalties for the excused period.

        Returns summary of actions taken.
        """
        # 1. Mark pre-joining sessions as EXCUSED_LATE_JOINER
        sessions = execute_query(
            """
            SELECT s.id
            FROM attendance_sessions s
            JOIN course_enrollments ce ON ce.course_id = s.course_id
            WHERE ce.student_id = %s
              AND ce.org_id = %s
              AND s.session_date < %s
        """,
            (student_id, org_id, joining_date),
        )

        session_ids = [str(r["id"]) for r in sessions]
        ops = []

        if session_ids:
            # Insert or update attendance_records for these sessions
            for sid in session_ids:
                ops.append(
                    (
                        """
                    INSERT INTO attendance_records
                        (id, org_id, student_id, session_id, status, created_at)
                    VALUES (%s, %s, %s, %s, 'EXCUSED_LATE_JOINER', NOW())
                    ON CONFLICT (student_id, session_id) DO UPDATE
                       SET status = 'EXCUSED_LATE_JOINER'
                """,
                        (str(uuid.uuid4()), org_id, student_id, sid),
                    )
                )

        # 2. Determine elapsed weeks from semester start
        # Find semester start date for this student's current enrollment
        enroll_rows = execute_query(
            """
            SELECT se.start_date
            FROM semester_enrollments se
            WHERE se.student_id = %s AND se.org_id = %s
              AND se.status = 'ACTIVE'
            LIMIT 1
        """,
            (student_id, org_id),
        )

        elapsed_weeks = 0
        if enroll_rows and enroll_rows[0].get("start_date"):
            sem_start = enroll_rows[0]["start_date"]
            if isinstance(sem_start, str):
                sem_start = datetime.fromisoformat(sem_start).date()
            joining_dt = datetime.fromisoformat(joining_date).date()
            elapsed_weeks = max(0, (joining_dt - sem_start).days // 7)

        # 3. Consolidate past-due assignments → single deadline 2 weeks from joining
        compressed_weeks = int(
            policy_engine.get_value("academics.late_joiner_catchup_weeks", org_id, 2)
        )
        new_deadline = datetime.fromisoformat(joining_date) + timedelta(
            weeks=compressed_weeks
        )

        past_due_assessments = execute_query(
            """
            SELECT a.id
            FROM assessments a
            JOIN course_enrollments ce ON ce.course_id = a.course_id
            WHERE ce.student_id = %s
              AND ce.org_id = %s
              AND a.due_date < %s
              AND a.status = 'PENDING'
        """,
            (student_id, org_id, joining_date),
        )

        for assessment in past_due_assessments:
            ops.append(
                (
                    """
                UPDATE student_assessment_submissions
                SET extended_due_date = %s,
                    late_penalty_suppressed = TRUE,
                    suppression_reason = 'LATE_JOINER'
                WHERE student_id = %s AND assessment_id = %s AND org_id = %s
            """,
                    (new_deadline, student_id, str(assessment["id"]), org_id),
                )
            )

        if ops:
            execute_transaction(ops)

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="student_catchup_cohort",
            resource_id=student_id,
            detail={
                "joining_date": joining_date,
                "excused_sessions": len(session_ids),
                "elapsed_weeks": elapsed_weeks,
                "compressed_deadline": new_deadline.isoformat(),
                "past_due_compressed": len(past_due_assessments),
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="academics.catchup_cohort_enrolled",
                org_id=org_id,
                payload={
                    "student_id": student_id,
                    "joining_date": joining_date,
                    "excused_sessions": len(session_ids),
                    "compressed_deadline": new_deadline.isoformat(),
                },
            )
        )

        logger.info(
            "CatchUp cohort enrolled: student=%s joining=%s excused=%d sessions",
            student_id,
            joining_date,
            len(session_ids),
        )

        return {
            "student_id": student_id,
            "joining_date": joining_date,
            "excused_sessions": len(session_ids),
            "elapsed_weeks": elapsed_weeks,
            "compressed_assignment_deadline": new_deadline.isoformat(),
            "past_due_assessments_compressed": len(past_due_assessments),
        }
