"""E05-S02 — Course Management"""

from __future__ import annotations

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import CourseCreate

logger = logging.getLogger(__name__)


class CourseService:
    @classmethod
    def create(cls, org_id: str, req: CourseCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM courses WHERE org_id = %s AND code = %s", (org_id, req.code)
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Course code '{req.code}' already exists"
            )

        cid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO courses (id, org_id, program_id, name, code, semester, credits, course_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                    (
                        cid,
                        org_id,
                        req.program_id,
                        req.name,
                        req.code,
                        req.semester,
                        req.credits,
                        req.course_type.value,
                        json.dumps(req.metadata),
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="course",
            entity_id=cid,
            org_id=org_id,
            module="E05-S02",
            metadata={"name": req.name, "code": req.code, "semester": req.semester},
        )
        return cls.get(org_id, cid)

    @classmethod
    def get(cls, org_id: str, course_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM courses WHERE id = %s AND org_id = %s", (course_id, org_id)
        )
        if not rows:
            raise NotFoundError(f"Course {course_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls, org_id: str, program_id: str | None = None, semester: int | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM courses WHERE org_id = %s AND status = 'ACTIVE'"
        params: list = [org_id]
        if program_id:
            sql += " AND program_id = %s"
            params.append(program_id)
        if semester is not None:
            sql += " AND semester = %s"
            params.append(semester)
        sql += " ORDER BY semester, name"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def list_for_student(
        cls, org_id: str, student_id: str, academic_year: str
    ) -> list[dict]:
        """Return courses a student is currently enrolled in."""
        rows = execute_query(
            """
            SELECT c.*, ce.status AS enrollment_status
            FROM courses c
            JOIN course_enrollments ce ON ce.course_id = c.id
            WHERE ce.student_id = %s AND ce.academic_year = %s AND ce.org_id = %s
            ORDER BY c.semester, c.name
            """,
            (student_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]
