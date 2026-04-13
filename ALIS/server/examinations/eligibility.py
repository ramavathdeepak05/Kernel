"""
Exam Eligibility Service — E06 Stage 1

Checks whether a student is eligible to sit for an exam:
1. Attendance ≥ 75% (or condonation approved)
2. Internal assessment marks submitted
3. Student dues cleared (re-queried at eligibility check time, not cached)
4. No active disciplinary hold

Condonation:
- Students below 75% but above 65% may apply for attendance condonation
- Requires HOD recommendation + Registrar/CoE approval
- Stored in `exam_condonations` table

Roles:
- Registrar/CoE: approve eligibility lists, approve condonations
- Faculty: submit attendance, request condonation for students
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    CONDONATION_PENDING = "CONDONATION_PENDING"
    CONDONATION_APPROVED = "CONDONATION_APPROVED"
    CONDONATION_REJECTED = "CONDONATION_REJECTED"


class CondonationStatus(str, Enum):
    PENDING = "PENDING"
    HOD_RECOMMENDED = "HOD_RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ExamEligibilityService:
    """
    Determines exam eligibility per student per course.

    Checks (in order):
    1. Disciplinary hold — auto-fail if active hold exists
    2. Attendance ≥ threshold (default 75%, from policy engine)
    3. If attendance < threshold but ≥ condonation floor (65%):
       check for approved condonation
    4. Internal marks submitted
    5. Dues cleared — ALWAYS re-queried from finance.dues_status (never cached)
    """

    @classmethod
    def check_eligibility(
        cls,
        org_id: str,
        student_id: str,
        exam_id: str,
        course_id: str,
    ) -> dict[str, Any]:
        """Run all eligibility checks for a student-course-exam combination."""
        checks = {}
        eligible = True

        # 1. Disciplinary hold
        holds = execute_query(
            "SELECT id FROM disciplinary_holds WHERE student_id = %s AND org_id = %s "
            "AND is_active = TRUE AND (expires_at IS NULL OR expires_at > NOW())",
            (student_id, org_id),
            tenant_id=org_id,
        )
        checks["disciplinary_hold"] = {"passed": len(holds) == 0, "holds": len(holds)}
        if holds:
            eligible = False

        # 2. Attendance gate
        attendance_threshold = float(
            policy_engine.get_value("examinations.attendance_threshold", org_id, 75.0)
        )
        condonation_floor = float(
            policy_engine.get_value("examinations.condonation_floor", org_id, 65.0)
        )

        attendance_rows = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('PRESENT', 'EXCUSED_LATE_JOINER', 'EXCUSED_DISRUPTION')) AS present,
                COUNT(*) AS total
            FROM attendance_records
            WHERE student_id = %s AND course_id = %s AND org_id = %s
            """,
            (student_id, course_id, org_id),
            tenant_id=org_id,
        )
        if attendance_rows and attendance_rows[0]["total"] > 0:
            att_pct = (
                attendance_rows[0]["present"] / attendance_rows[0]["total"]
            ) * 100
        else:
            att_pct = 0.0

        if att_pct >= attendance_threshold:
            checks["attendance"] = {
                "passed": True,
                "percentage": round(att_pct, 1),
                "threshold": attendance_threshold,
            }
        elif att_pct >= condonation_floor:
            # Check for approved condonation
            condonation = execute_query(
                "SELECT status FROM exam_condonations "
                "WHERE student_id = %s AND course_id = %s AND exam_id = %s AND org_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (student_id, course_id, exam_id, org_id),
                tenant_id=org_id,
            )
            if (
                condonation
                and condonation[0]["status"] == CondonationStatus.APPROVED.value
            ):
                checks["attendance"] = {
                    "passed": True,
                    "percentage": round(att_pct, 1),
                    "condonation": "APPROVED",
                }
            else:
                checks["attendance"] = {
                    "passed": False,
                    "percentage": round(att_pct, 1),
                    "condonation": condonation[0]["status"]
                    if condonation
                    else "NOT_APPLIED",
                    "reason": f"Attendance {att_pct:.1f}% below {attendance_threshold}% (condonation possible)",
                }
                eligible = False
        else:
            checks["attendance"] = {
                "passed": False,
                "percentage": round(att_pct, 1),
                "reason": f"Attendance {att_pct:.1f}% below condonation floor {condonation_floor}%",
            }
            eligible = False

        # 3. Internal marks submitted
        marks = execute_query(
            "SELECT COUNT(*) AS cnt FROM internal_marks "
            "WHERE student_id = %s AND course_id = %s AND org_id = %s AND marks IS NOT NULL",
            (student_id, course_id, org_id),
            tenant_id=org_id,
        )
        marks_submitted = marks[0]["cnt"] > 0 if marks else False
        checks["internal_marks"] = {"passed": marks_submitted}
        if not marks_submitted:
            eligible = False

        # 4. Dues cleared — ALWAYS re-query (never cached)
        dues = execute_query(
            "SELECT total_due FROM student_dues_status "
            "WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        dues_clear = (not dues) or (float(dues[0].get("total_due", 0)) <= 0)
        checks["dues_cleared"] = {
            "passed": dues_clear,
            "total_due": float(dues[0]["total_due"]) if dues else 0,
        }
        if not dues_clear:
            eligible = False

        return {
            "student_id": student_id,
            "exam_id": exam_id,
            "course_id": course_id,
            "eligible": eligible,
            "status": EligibilityStatus.ELIGIBLE.value
            if eligible
            else EligibilityStatus.NOT_ELIGIBLE.value,
            "checks": checks,
        }

    @classmethod
    def request_condonation(
        cls,
        org_id: str,
        student_id: str,
        exam_id: str,
        course_id: str,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Student or faculty requests attendance condonation."""
        condonation_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO exam_condonations
                    (id, org_id, student_id, exam_id, course_id, reason, status,
                     requested_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        condonation_id,
                        org_id,
                        student_id,
                        exam_id,
                        course_id,
                        reason,
                        CondonationStatus.PENDING.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        return {"id": condonation_id, "status": CondonationStatus.PENDING.value}

    @classmethod
    def decide_condonation(
        cls,
        org_id: str,
        condonation_id: str,
        decision: str,
        actor_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        """HOD recommends or Registrar/CoE approves/rejects condonation."""
        valid_decisions = {
            "HOD": {
                CondonationStatus.HOD_RECOMMENDED.value,
                CondonationStatus.REJECTED.value,
            },
            "REGISTRAR": {
                CondonationStatus.APPROVED.value,
                CondonationStatus.REJECTED.value,
            },
            "COE": {CondonationStatus.APPROVED.value, CondonationStatus.REJECTED.value},
        }

        allowed = valid_decisions.get(actor_role, set())
        if decision not in allowed:
            raise ValueError(f"Role {actor_role} cannot set decision to {decision}")

        execute_transaction(
            [
                (
                    "UPDATE exam_condonations SET status = %s, decided_by = %s, decided_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (decision, actor_id, condonation_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="exam_condonation",
            entity_id=condonation_id,
            tenant_id=org_id,
            metadata={"decision": decision},
        )

        return {"id": condonation_id, "status": decision}
