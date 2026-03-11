"""E06-S01 — Exam Schedule"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import ExamScheduleCreate

logger = logging.getLogger(__name__)


class ExamScheduleService:

    @classmethod
    def create(cls, org_id: str, req: ExamScheduleCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM exam_schedules WHERE course_id = %s AND academic_year = %s AND exam_type = %s AND org_id = %s",
            (req.course_id, req.academic_year, req.exam_type.value, org_id),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Exam schedule already exists for this course/{req.exam_type.value}/{req.academic_year}")

        sid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO exam_schedules
                (id, org_id, course_id, academic_year, semester, exam_type,
                 exam_date, start_time, end_time, venue, max_marks, pass_marks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::time, %s::time, %s, %s, %s)
            """,
            (sid, org_id, req.course_id, req.academic_year, req.semester,
             req.exam_type.value, req.exam_date, req.start_time, req.end_time,
             req.venue, req.max_marks, req.pass_marks),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="exam_schedule", entity_id=sid, org_id=org_id,
                     module="E06-S01", metadata={"course_id": req.course_id, "date": req.exam_date})
        return cls.get(org_id, sid)

    @classmethod
    def get(cls, org_id: str, schedule_id: str) -> dict:
        rows = execute_query(
            """
            SELECT es.*, c.name AS course_name, c.code AS course_code
            FROM exam_schedules es
            JOIN courses c ON c.id = es.course_id
            WHERE es.id = %s AND es.org_id = %s
            """,
            (schedule_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Exam schedule {schedule_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, academic_year: str, semester: int | None = None,
             exam_type: str | None = None) -> list[dict]:
        sql = """
            SELECT es.*, c.name AS course_name, c.code AS course_code
            FROM exam_schedules es
            JOIN courses c ON c.id = es.course_id
            WHERE es.org_id = %s AND es.academic_year = %s
        """
        params: list = [org_id, academic_year]
        if semester:
            sql += " AND es.semester = %s"
            params.append(semester)
        if exam_type:
            sql += " AND es.exam_type = %s"
            params.append(exam_type)
        sql += " ORDER BY es.exam_date, es.start_time"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def update_status(cls, org_id: str, schedule_id: str, status: str, actor_id: str) -> dict:
        cls.get(org_id, schedule_id)
        execute_transaction([(
            "UPDATE exam_schedules SET status = %s WHERE id = %s AND org_id = %s",
            (status, schedule_id, org_id),
        )])
        return cls.get(org_id, schedule_id)
