"""E05-S06 — Attendance Tracking"""

import logging
import uuid
from typing import Optional

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import AttendanceMarkRequest, AttendanceStatus

logger = logging.getLogger(__name__)


class AttendanceService:

    # ------------------------------------------------------------------
    # Mark attendance for a session
    # ------------------------------------------------------------------

    @classmethod
    def mark_session(cls, org_id: str, req: AttendanceMarkRequest,
                     faculty_id: str, actor_id: str) -> dict:
        """
        Create (or update) an attendance session and mark each student.
        Idempotent — re-marking a session updates existing records.
        """
        # Get or create session
        existing_session = execute_query(
            "SELECT id, is_finalized FROM attendance_sessions WHERE course_id = %s AND session_date = %s AND slot_type = %s AND org_id = %s",
            (req.course_id, req.session_date, req.slot_type, org_id),
        )

        if existing_session:
            if existing_session[0]["is_finalized"]:
                raise BusinessRuleViolation(
                    message=f"Attendance for {req.session_date} is already finalized and cannot be edited"
                )
            session_id = str(existing_session[0]["id"])
        else:
            session_id = str(uuid.uuid4())
            execute_transaction([(
                """
                INSERT INTO attendance_sessions
                    (id, org_id, course_id, faculty_id, academic_year, session_date, slot_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, org_id, req.course_id, faculty_id,
                 req.academic_year, req.session_date, req.slot_type),
            )])

        # Upsert each student's record
        ops = []
        for entry in req.records:
            student_id = entry["student_id"]
            status = entry.get("status", AttendanceStatus.ABSENT.value).upper()
            if status not in [s.value for s in AttendanceStatus]:
                status = AttendanceStatus.ABSENT.value

            ops.append((
                """
                INSERT INTO attendance_records (id, org_id, session_id, student_id, status, marked_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, student_id)
                DO UPDATE SET status = EXCLUDED.status, marked_by = EXCLUDED.marked_by, marked_at = NOW()
                """,
                (str(uuid.uuid4()), org_id, session_id, student_id, status, actor_id),
            ))

        if ops:
            execute_transaction(ops)

        present = sum(1 for r in req.records if r.get("status", "").upper() == "PRESENT")
        total = len(req.records)

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="attendance_session", entity_id=session_id, org_id=org_id,
                     module="E05-S06",
                     metadata={"course_id": req.course_id, "date": req.session_date,
                               "present": present, "total": total})

        return {
            "session_id": session_id,
            "course_id": req.course_id,
            "session_date": req.session_date,
            "total": total,
            "present": present,
            "absent": total - present,
        }

    # ------------------------------------------------------------------
    # Finalize a session (locks it from further editing)
    # ------------------------------------------------------------------

    @classmethod
    def finalize_session(cls, org_id: str, session_id: str, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM attendance_sessions WHERE id = %s AND org_id = %s", (session_id, org_id)
        )
        if not rows:
            raise NotFoundError(f"Session {session_id} not found")
        if rows[0]["is_finalized"]:
            raise BusinessRuleViolation(message="Session already finalized")

        execute_transaction([(
            "UPDATE attendance_sessions SET is_finalized = TRUE, finalized_at = NOW() WHERE id = %s",
            (session_id,),
        )])

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="attendance_session", entity_id=session_id, org_id=org_id,
                     module="E05-S06", metadata={"action": "finalize"})

        return {"session_id": session_id, "is_finalized": True}

    # ------------------------------------------------------------------
    # Compute attendance percentage for a student in a course
    # ------------------------------------------------------------------

    @classmethod
    def get_student_summary(cls, org_id: str, student_id: str,
                             course_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN ar.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END) AS attended,
                SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END) AS absent,
                SUM(CASE WHEN ar.status = 'EXCUSED' THEN 1 ELSE 0 END) AS excused
            FROM attendance_records ar
            JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE ar.student_id = %s AND s.course_id = %s
              AND s.academic_year = %s AND s.org_id = %s
            """,
            (student_id, course_id, academic_year, org_id),
        )
        r = rows[0] if rows else {}
        total = int(r.get("total_sessions") or 0)
        attended = int(r.get("attended") or 0)
        pct = round((attended / total * 100), 2) if total > 0 else 0.0

        from server.admissions.policy_store import PolicyKey, PolicyStore
        min_pct = float(PolicyStore.get(org_id, PolicyKey.MIN_ATTENDANCE_PCT) or 75.0)

        return {
            "student_id": student_id,
            "course_id": course_id,
            "academic_year": academic_year,
            "total_sessions": total,
            "attended": attended,
            "absent": int(r.get("absent") or 0),
            "excused": int(r.get("excused") or 0),
            "percentage": pct,
            "min_required": min_pct,
            "at_risk": pct < min_pct,
        }

    @classmethod
    def get_course_summary(cls, org_id: str, course_id: str, academic_year: str) -> list[dict]:
        """Attendance summary for all enrolled students in a course."""
        students = execute_query(
            "SELECT student_id FROM course_enrollments WHERE course_id = %s AND academic_year = %s AND org_id = %s AND status = 'ENROLLED'",
            (course_id, academic_year, org_id),
        )
        return [
            cls.get_student_summary(org_id, str(s["student_id"]), course_id, academic_year)
            for s in students
        ]

    # ------------------------------------------------------------------
    # Finalize all attendance for semester-end (fires AttendanceFinalized event)
    # ------------------------------------------------------------------

    @classmethod
    def finalize_semester_attendance(cls, org_id: str, academic_year: str,
                                      semester: int, actor_id: str) -> dict:
        """
        Lock all open sessions for a semester and publish AttendanceFinalized event.
        Called by the academic calendar daemon when ATTENDANCE_LOCK phase starts.
        """
        open_sessions = execute_query(
            """
            SELECT s.id FROM attendance_sessions s
            JOIN courses c ON c.id = s.course_id
            WHERE s.org_id = %s AND s.academic_year = %s
              AND c.semester = %s AND s.is_finalized = FALSE
            """,
            (org_id, academic_year, semester),
        )

        for session in open_sessions:
            execute_transaction([(
                "UPDATE attendance_sessions SET is_finalized = TRUE, finalized_at = NOW() WHERE id = %s",
                (str(session["id"]),),
            )])

        DomainEventBus.publish(DomainEvent(
            event_type="AttendanceFinalized",
            entity_type="semester",
            entity_id=f"{org_id}:{academic_year}:sem{semester}",
            org_id=org_id,
            payload={"academic_year": academic_year, "semester": semester,
                     "sessions_finalized": len(open_sessions)},
            actor_id=actor_id,
        ))

        logger.info("AttendanceFinalized: org=%s year=%s semester=%d sessions=%d",
                    org_id, academic_year, semester, len(open_sessions))

        return {
            "academic_year": academic_year,
            "semester": semester,
            "sessions_finalized": len(open_sessions),
        }
