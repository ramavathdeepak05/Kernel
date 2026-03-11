"""E05 — Academics Event Handlers

Subscribes: StudentEnrolled
Publishes:  AttendanceFinalized (via AttendanceService)
"""

import logging
from datetime import date

from server.core.domain_events import DomainEvent, register_handler

logger = logging.getLogger(__name__)


def on_student_enrolled(event: DomainEvent) -> None:
    """
    When a student is enrolled (M1 fires StudentEnrolled), auto-enroll them
    into all mandatory courses for their program and current semester.
    """
    try:
        student_id = event.payload.get("student_id")
        org_id = event.org_id

        if not student_id:
            logger.warning("E05: StudentEnrolled event missing student_id in payload")
            return

        from server.db_service import execute_query
        student = execute_query(
            "SELECT id, program, enrolled_at FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student:
            logger.warning("E05: student %s not found", student_id)
            return

        program_name = student[0]["program"]

        # Resolve program_id from program name
        program = execute_query(
            "SELECT id FROM programs WHERE org_id = %s AND name = %s AND status = 'ACTIVE'",
            (org_id, program_name),
        )
        if not program:
            logger.warning("E05: no active program found for '%s' — skipping auto-enrollment", program_name)
            return

        program_id = str(program[0]["id"])
        enrolled_year = student[0]["enrolled_at"].year
        academic_year = f"{enrolled_year}-{enrolled_year + 1}"

        from server.academics.enrollment import AcademicEnrollmentService
        AcademicEnrollmentService.auto_enroll_from_program(
            org_id=org_id,
            student_id=student_id,
            program_id=program_id,
            academic_year=academic_year,
            semester=1,  # New enrollments always start at semester 1
            actor_id="system",
        )
        logger.info("E05: auto-enrolled student %s in semester 1 courses", student_id)

    except Exception as exc:
        logger.error("E05: on_student_enrolled failed: %s", exc)


def register_all() -> None:
    register_handler("StudentEnrolled", on_student_enrolled)
    logger.info("E05: Academics event handlers registered")
