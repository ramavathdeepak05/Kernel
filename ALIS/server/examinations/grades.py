"""E06-S03 + S04 — Grade Entry & GPA/CGPA Computation

Grading scale is configurable via PolicyStore:
  exams.grading.scale = "10" | "4" | "percentage"
  exams.grading.grade_table = {...}  (marks → grade → points mapping)
"""

import logging
import uuid
from decimal import Decimal
from typing import Optional

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import GradesBulkEntry

logger = logging.getLogger(__name__)

# Default grade table (10-point scale, configurable via policy)
_DEFAULT_GRADE_TABLE = [
    (90, "O",   10.0),
    (80, "A+",   9.0),
    (70, "A",    8.0),
    (60, "B+",   7.0),
    (50, "B",    6.0),
    (40, "C",    5.0),
    (0,  "F",    0.0),
]


def _compute_grade(marks: float, max_marks: int, pass_marks: int,
                   grade_table: list) -> tuple[str, float, bool]:
    """Return (grade, grade_points, is_pass)."""
    if marks < pass_marks:
        return "F", 0.0, False
    pct = (marks / max_marks) * 100
    for threshold, grade, points in grade_table:
        if pct >= threshold:
            return grade, points, True
    return "F", 0.0, False


class GradeService:

    @classmethod
    def _load_grade_table(cls, org_id: str) -> list:
        from server.core.policy_store import PolicyStore
        table = PolicyStore.get(org_id, "exams.grading.grade_table")
        if table and isinstance(table, list):
            return [(row[0], row[1], row[2]) for row in table]
        return _DEFAULT_GRADE_TABLE

    # ------------------------------------------------------------------
    # S03 — Bulk grade entry
    # ------------------------------------------------------------------

    @classmethod
    def enter_grades(cls, org_id: str, req: GradesBulkEntry, actor_id: str) -> dict:
        schedule = execute_query(
            "SELECT * FROM exam_schedules WHERE id = %s AND org_id = %s",
            (req.exam_schedule_id, org_id),
        )
        if not schedule:
            raise NotFoundError(f"Exam schedule {req.exam_schedule_id} not found")

        sched = schedule[0]
        max_marks  = int(sched["max_marks"])
        pass_marks = int(sched["pass_marks"])
        grade_table = cls._load_grade_table(org_id)

        ops = []
        entered = 0
        for entry in req.entries:
            gid = str(uuid.uuid4())
            grade = grade_pts = None
            is_pass = None

            if not entry.is_absent and entry.marks_obtained is not None:
                grade, grade_pts, is_pass = _compute_grade(
                    float(entry.marks_obtained), max_marks, pass_marks, grade_table
                )

            ops.append((
                """
                INSERT INTO grades
                    (id, org_id, student_id, course_id, exam_schedule_id,
                     academic_year, semester, marks_obtained, max_marks,
                     grade, grade_points, is_absent, is_pass, entered_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (student_id, course_id, academic_year, semester)
                DO UPDATE SET
                    marks_obtained = EXCLUDED.marks_obtained,
                    grade = EXCLUDED.grade,
                    grade_points = EXCLUDED.grade_points,
                    is_absent = EXCLUDED.is_absent,
                    is_pass = EXCLUDED.is_pass,
                    entered_by = EXCLUDED.entered_by,
                    entered_at = NOW()
                """,
                (gid, org_id, entry.student_id, str(sched["course_id"]),
                 req.exam_schedule_id, req.academic_year, req.semester,
                 entry.marks_obtained, max_marks, grade, grade_pts,
                 entry.is_absent, is_pass, actor_id),
            ))
            entered += 1

        if ops:
            execute_transaction(ops)

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="grades", entity_id=req.exam_schedule_id, org_id=org_id,
                     module="E06-S03", metadata={"entered": entered, "academic_year": req.academic_year})

        return {"entered": entered, "exam_schedule_id": req.exam_schedule_id}

    @classmethod
    def get_student_grades(cls, org_id: str, student_id: str,
                            academic_year: str, semester: int | None = None) -> list[dict]:
        sql = """
            SELECT g.*, c.name AS course_name, c.code AS course_code, c.credits
            FROM grades g
            JOIN courses c ON c.id = g.course_id
            WHERE g.student_id = %s AND g.academic_year = %s AND g.org_id = %s
        """
        params: list = [student_id, academic_year, org_id]
        if semester:
            sql += " AND g.semester = %s"
            params.append(semester)
        sql += " ORDER BY g.semester, c.name"
        return [dict(r) for r in execute_query(sql, params)]

    # ------------------------------------------------------------------
    # S04 — GPA/CGPA computation
    # ------------------------------------------------------------------

    @classmethod
    def compute_semester_result(
        cls, org_id: str, student_id: str, academic_year: str, semester: int, actor_id: str
    ) -> dict:
        """
        Compute SGPA for the semester and CGPA (all semesters to date).
        Upserts into semester_results table.
        """
        grades = execute_query(
            """
            SELECT g.grade_points, g.is_pass, g.is_absent, c.credits
            FROM grades g
            JOIN courses c ON c.id = g.course_id
            WHERE g.student_id = %s AND g.academic_year = %s
              AND g.semester = %s AND g.org_id = %s
            """,
            (student_id, academic_year, semester, org_id),
        )
        if not grades:
            raise BusinessRuleViolation(message=f"No grades found for student {student_id} sem {semester}")

        total_credits  = sum(int(g["credits"]) for g in grades)
        earned_credits = sum(int(g["credits"]) for g in grades if g["is_pass"] and not g["is_absent"])
        weighted_pts   = sum(
            float(g["grade_points"] or 0) * int(g["credits"])
            for g in grades if not g["is_absent"]
        )
        sgpa = round(weighted_pts / total_credits, 2) if total_credits > 0 else 0.0

        # CGPA — all semesters up to and including this one
        all_grades = execute_query(
            """
            SELECT g.grade_points, g.is_pass, g.is_absent, c.credits
            FROM grades g
            JOIN courses c ON c.id = g.course_id
            WHERE g.student_id = %s AND g.org_id = %s
              AND (g.academic_year < %s OR (g.academic_year = %s AND g.semester <= %s))
            """,
            (student_id, org_id, academic_year, academic_year, semester),
        )
        all_credits = sum(int(g["credits"]) for g in all_grades)
        all_weighted = sum(
            float(g["grade_points"] or 0) * int(g["credits"])
            for g in all_grades if not g["is_absent"]
        )
        cgpa = round(all_weighted / all_credits, 2) if all_credits > 0 else 0.0

        status = "PASS" if earned_credits == total_credits else "FAIL"

        execute_transaction([(
            """
            INSERT INTO semester_results
                (id, org_id, student_id, academic_year, semester,
                 sgpa, cgpa, total_credits, credits_earned, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (student_id, academic_year, semester)
            DO UPDATE SET
                sgpa = EXCLUDED.sgpa, cgpa = EXCLUDED.cgpa,
                total_credits = EXCLUDED.total_credits,
                credits_earned = EXCLUDED.credits_earned,
                status = EXCLUDED.status
            """,
            (str(uuid.uuid4()), org_id, student_id, academic_year, semester,
             sgpa, cgpa, total_credits, earned_credits, status),
        )])

        return {
            "student_id": student_id, "academic_year": academic_year,
            "semester": semester, "sgpa": sgpa, "cgpa": cgpa,
            "total_credits": total_credits, "credits_earned": earned_credits,
            "status": status,
        }

    # ------------------------------------------------------------------
    # S05 — Publish results
    # ------------------------------------------------------------------

    @classmethod
    def publish_results(cls, org_id: str, academic_year: str,
                         semester: int, actor_id: str) -> dict:
        """Mark all grades as published and fire ResultsDeclared event."""
        from server.core.domain_events import DomainEvent, DomainEventBus

        execute_transaction([(
            """
            UPDATE grades SET is_published = TRUE
            WHERE org_id = %s AND academic_year = %s AND semester = %s AND is_published = FALSE
            """,
            (org_id, academic_year, semester),
        )])
        execute_transaction([(
            """
            UPDATE semester_results
            SET is_published = TRUE, declared_at = NOW()
            WHERE org_id = %s AND academic_year = %s AND semester = %s
            """,
            (org_id, academic_year, semester),
        )])

        DomainEventBus.publish(DomainEvent(
            event_type="ResultsDeclared",
            entity_type="semester",
            entity_id=f"{org_id}:{academic_year}:sem{semester}",
            org_id=org_id,
            payload={"academic_year": academic_year, "semester": semester},
            actor_id=actor_id,
        ))

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="semester_results", entity_id=f"{academic_year}:sem{semester}",
                     org_id=org_id, module="E06-S05",
                     metadata={"academic_year": academic_year, "semester": semester})

        logger.info("Results published: org=%s year=%s sem=%d", org_id, academic_year, semester)
        return {"status": "published", "academic_year": academic_year, "semester": semester}
