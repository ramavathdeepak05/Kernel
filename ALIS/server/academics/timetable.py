"""E05-S05 — Academic Timetable"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import TimetableSlotCreate

logger = logging.getLogger(__name__)

_DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}


class TimetableService:
    @classmethod
    def add_slot(cls, org_id: str, req: TimetableSlotCreate, actor_id: str) -> dict:
        # Conflict check: same faculty, same day+time
        if req.faculty_id:
            conflict = execute_query(
                """
                SELECT id FROM timetable_slots
                WHERE faculty_id = %s AND academic_year = %s AND day_of_week = %s
                  AND org_id = %s
                  AND (start_time, end_time) OVERLAPS (%s::time, %s::time)
                """,
                (
                    req.faculty_id,
                    req.academic_year,
                    req.day_of_week,
                    org_id,
                    req.start_time,
                    req.end_time,
                ),
            )
            if conflict:
                raise BusinessRuleViolation(
                    message=f"Faculty has a timetable conflict on {_DAY_NAMES.get(req.day_of_week)} {req.start_time}–{req.end_time}"
                )

        sid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO timetable_slots
                (id, org_id, course_id, faculty_id, academic_year, day_of_week,
                 start_time, end_time, room, slot_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s::time, %s::time, %s, %s)
            """,
                    (
                        sid,
                        org_id,
                        req.course_id,
                        req.faculty_id,
                        req.academic_year,
                        req.day_of_week,
                        req.start_time,
                        req.end_time,
                        req.room,
                        req.slot_type,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="timetable_slot",
            entity_id=sid,
            org_id=org_id,
            module="E05-S05",
            metadata={
                "course_id": req.course_id,
                "day": req.day_of_week,
                "time": f"{req.start_time}-{req.end_time}",
            },
        )
        return cls.get(org_id, sid)

    @classmethod
    def get(cls, org_id: str, slot_id: str) -> dict:
        rows = execute_query(
            """
            SELECT ts.*, c.name AS course_name, c.code AS course_code,
                   u.display_name AS faculty_name
            FROM timetable_slots ts
            JOIN courses c ON c.id = ts.course_id
            LEFT JOIN users u ON u.id = ts.faculty_id
            WHERE ts.id = %s AND ts.org_id = %s
            """,
            (slot_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Timetable slot {slot_id} not found")
        return dict(rows[0])

    @classmethod
    def get_weekly(
        cls,
        org_id: str,
        academic_year: str,
        course_id: str | None = None,
        faculty_id: str | None = None,
    ) -> list[dict]:
        """Return full weekly timetable, optionally filtered by course or faculty."""
        sql = """
            SELECT ts.*, c.name AS course_name, c.code, u.display_name AS faculty_name
            FROM timetable_slots ts
            JOIN courses c ON c.id = ts.course_id
            LEFT JOIN users u ON u.id = ts.faculty_id
            WHERE ts.org_id = %s AND ts.academic_year = %s
        """
        params: list = [org_id, academic_year]
        if course_id:
            sql += " AND ts.course_id = %s"
            params.append(course_id)
        if faculty_id:
            sql += " AND ts.faculty_id = %s"
            params.append(faculty_id)
        sql += " ORDER BY ts.day_of_week, ts.start_time"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def delete_slot(cls, org_id: str, slot_id: str, actor_id: str) -> None:
        cls.get(org_id, slot_id)
        execute_transaction(
            [
                (
                    "DELETE FROM timetable_slots WHERE id = %s AND org_id = %s",
                    (slot_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.DELETE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="timetable_slot",
            entity_id=slot_id,
            org_id=org_id,
            module="E05-S05",
            metadata={},
        )
