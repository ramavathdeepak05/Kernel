"""E05-S03 — Student-Course Enrollment"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import StudentEnrollRequest

logger = logging.getLogger(__name__)


class AcademicEnrollmentService:
    """
    Enrolls students into courses for a given semester/year.
    Distinct from AdmissionsEnrollment — this is per-course academic enrollment.
    Triggered automatically by the StudentEnrolled domain event.
    """

    @classmethod
    def enroll_student(
        cls, org_id: str, req: StudentEnrollRequest, actor_id: str
    ) -> list[dict]:
        """Enroll a student into a list of courses. Idempotent."""
        # Validate student exists
        student = execute_query(
            "SELECT id, name, program FROM students WHERE id = %s AND org_id = %s",
            (req.student_id, org_id),
        )
        if not student:
            raise NotFoundError(f"Student {req.student_id} not found")

        created = []
        skipped = []

        for course_id in req.course_ids:
            existing = execute_query(
                "SELECT id FROM course_enrollments WHERE student_id = %s AND course_id = %s AND academic_year = %s",
                (req.student_id, course_id, req.academic_year),
            )
            if existing:
                skipped.append(course_id)
                continue

            eid = str(uuid.uuid4())
            execute_transaction(
                [
                    (
                        """
                INSERT INTO course_enrollments
                    (id, org_id, student_id, course_id, academic_year, semester)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                        (
                            eid,
                            org_id,
                            req.student_id,
                            course_id,
                            req.academic_year,
                            req.semester,
                        ),
                    )
                ]
            )
            created.append(course_id)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="course_enrollment",
            entity_id=req.student_id,
            org_id=org_id,
            module="E05-S03",
            metadata={
                "enrolled": created,
                "skipped": skipped,
                "academic_year": req.academic_year,
            },
        )

        logger.info(
            "AcademicEnrollment: student=%s enrolled=%d skipped=%d",
            req.student_id,
            len(created),
            len(skipped),
        )
        return cls.list_for_student(org_id, req.student_id, req.academic_year)

    @classmethod
    def drop_course(
        cls,
        org_id: str,
        student_id: str,
        course_id: str,
        academic_year: str,
        actor_id: str,
    ) -> dict:
        rows = execute_query(
            "SELECT id FROM course_enrollments WHERE student_id = %s AND course_id = %s AND academic_year = %s AND org_id = %s",
            (student_id, course_id, academic_year, org_id),
        )
        if not rows:
            raise NotFoundError("Enrollment not found")

        execute_transaction(
            [
                (
                    "UPDATE course_enrollments SET status = 'DROPPED' WHERE id = %s",
                    (rows[0]["id"],),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="course_enrollment",
            entity_id=str(rows[0]["id"]),
            org_id=org_id,
            module="E05-S03",
            metadata={
                "student_id": student_id,
                "course_id": course_id,
                "action": "drop",
            },
        )
        return {"status": "DROPPED", "student_id": student_id, "course_id": course_id}

    @classmethod
    def list_for_student(
        cls, org_id: str, student_id: str, academic_year: str
    ) -> list[dict]:
        rows = execute_query(
            """
            SELECT ce.*, c.name AS course_name, c.code AS course_code,
                   c.credits, c.course_type, c.semester
            FROM course_enrollments ce
            JOIN courses c ON c.id = ce.course_id
            WHERE ce.student_id = %s AND ce.academic_year = %s AND ce.org_id = %s
            ORDER BY c.semester, c.name
            """,
            (student_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def auto_enroll_from_program(
        cls,
        org_id: str,
        student_id: str,
        program_id: str,
        academic_year: str,
        semester: int,
        actor_id: str,
    ) -> list[dict]:
        """
        Auto-enroll a student in all mandatory courses for their program + semester.
        Called by the StudentEnrolled event handler.
        """
        courses = execute_query(
            """
            SELECT id FROM courses
            WHERE program_id = %s AND semester = %s AND org_id = %s
              AND status = 'ACTIVE' AND course_type != 'ELECTIVE'
            """,
            (program_id, semester, org_id),
        )
        if not courses:
            logger.warning(
                "E05-S03: no mandatory courses for program=%s semester=%d",
                program_id,
                semester,
            )
            return []

        return cls.enroll_student(
            org_id=org_id,
            req=StudentEnrollRequest(
                student_id=student_id,
                course_ids=[str(c["id"]) for c in courses],
                academic_year=academic_year,
                semester=semester,
            ),
            actor_id=actor_id,
        )
