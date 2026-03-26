"""E05-S04 — Faculty Assignment"""
from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import FacultyAssignRequest

logger = logging.getLogger(__name__)


class FacultyAssignmentService:

    @classmethod
    def assign(cls, org_id: str, req: FacultyAssignRequest, actor_id: str) -> dict:
        # Validate faculty exists and has FACULTY role
        faculty = execute_query(
            "SELECT id, name FROM users WHERE id = %s AND org_id = %s AND role IN ('FACULTY','ADMIN','SUPER_ADMIN')",
            (req.faculty_id, org_id),
        )
        if not faculty:
            raise NotFoundError(f"Faculty user {req.faculty_id} not found")

        # Check for existing assignment
        existing = execute_query(
            "SELECT id FROM faculty_assignments WHERE faculty_id = %s AND course_id = %s AND academic_year = %s",
            (req.faculty_id, req.course_id, req.academic_year),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Faculty already assigned to this course for {req.academic_year}"
            )

        # Workload check — configurable via PolicyStore
        from server.core.policy_store import PolicyStore
        max_load = int(PolicyStore.get(org_id, "academics.faculty.max_courses_per_year") or 6)
        current_load = execute_query(
            "SELECT COUNT(*) AS n FROM faculty_assignments WHERE faculty_id = %s AND academic_year = %s",
            (req.faculty_id, req.academic_year),
        )
        if current_load and current_load[0]["n"] >= max_load:
            raise BusinessRuleViolation(
                message=f"Faculty has reached maximum course load of {max_load} for {req.academic_year}"
            )

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO faculty_assignments
                (id, org_id, faculty_id, course_id, academic_year, semester, assigned_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (aid, org_id, req.faculty_id, req.course_id, req.academic_year, req.semester, actor_id),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="faculty_assignment", entity_id=aid, org_id=org_id,
                     module="E05-S04",
                     metadata={"faculty_id": req.faculty_id, "course_id": req.course_id})

        return cls.get(org_id, aid)

    @classmethod
    def get(cls, org_id: str, assignment_id: str) -> dict:
        rows = execute_query(
            """
            SELECT fa.*, u.display_name AS faculty_name, c.name AS course_name, c.code AS course_code
            FROM faculty_assignments fa
            JOIN users u ON u.id = fa.faculty_id
            JOIN courses c ON c.id = fa.course_id
            WHERE fa.id = %s AND fa.org_id = %s
            """,
            (assignment_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Assignment {assignment_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_faculty(cls, org_id: str, faculty_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT fa.*, c.name AS course_name, c.code, c.semester, c.credits
            FROM faculty_assignments fa
            JOIN courses c ON c.id = fa.course_id
            WHERE fa.faculty_id = %s AND fa.academic_year = %s AND fa.org_id = %s
            ORDER BY c.semester
            """,
            (faculty_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_for_course(cls, org_id: str, course_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT fa.*, u.display_name AS faculty_name, u.email
            FROM faculty_assignments fa
            JOIN users u ON u.id = fa.faculty_id
            WHERE fa.course_id = %s AND fa.academic_year = %s AND fa.org_id = %s
            """,
            (course_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def unassign(cls, org_id: str, assignment_id: str, actor_id: str) -> None:
        cls.get(org_id, assignment_id)
        execute_transaction([(
            "DELETE FROM faculty_assignments WHERE id = %s AND org_id = %s",
            (assignment_id, org_id),
        )])
        AuditLog.log(action=AuditAction.DELETE, actor_id=actor_id, actor_type="human",
                     entity_type="faculty_assignment", entity_id=assignment_id,
                     org_id=org_id, module="E05-S04", metadata={})
