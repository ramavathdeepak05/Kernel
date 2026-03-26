"""E11-S03 — Academic Reports"""
from __future__ import annotations

import logging
from server.db_service import execute_query

logger = logging.getLogger(__name__)


class AcademicsReportService:

    @classmethod
    def enrollment_summary(cls, org_id: str, academic_year: str, semester: int | None = None) -> dict:
        """Enrollment counts by program and semester."""
        sql = """
            SELECT
                s.program,
                ce.semester,
                COUNT(DISTINCT ce.student_id) AS enrolled_students,
                COUNT(DISTINCT ce.course_id)  AS courses
            FROM course_enrollments ce
            JOIN students s ON s.id = ce.student_id
            WHERE ce.org_id = %s AND ce.academic_year = %s AND ce.status = 'ENROLLED'
        """
        params: list = [org_id, academic_year]
        if semester:
            sql += " AND ce.semester = %s"; params.append(semester)
        sql += " GROUP BY s.program, ce.semester ORDER BY s.program, ce.semester"
        rows = execute_query(sql, params)
        return {"academic_year": academic_year, "breakdown": [dict(r) for r in rows]}

    @classmethod
    def attendance_summary(cls, org_id: str, academic_year: str, semester: int | None = None) -> list[dict]:
        """Average attendance % per course."""
        sql = """
            SELECT
                c.code AS course_code,
                c.name AS course_name,
                COUNT(DISTINCT ar.student_id) AS students,
                ROUND(AVG(
                    CASE WHEN ar.status IN ('PRESENT','LATE') THEN 100.0 ELSE 0.0 END
                ), 1) AS avg_attendance_pct,
                COUNT(DISTINCT sess.id) AS total_sessions
            FROM attendance_sessions sess
            JOIN courses c ON c.id = sess.course_id
            LEFT JOIN attendance_records ar ON ar.session_id = sess.id
            WHERE sess.org_id = %s AND sess.academic_year = %s
        """
        params: list = [org_id, academic_year]
        if semester:
            sql += " AND sess.semester = %s"; params.append(semester)
        sql += " GROUP BY c.id, c.code, c.name ORDER BY avg_attendance_pct"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def low_attendance_students(
        cls, org_id: str, academic_year: str, semester: int, threshold: float = 75.0
    ) -> list[dict]:
        """Students below attendance threshold across any course."""
        rows = execute_query(
            """
            SELECT
                s.id AS student_id, s.name, s.roll_number, s.program,
                c.code AS course_code, c.name AS course_name,
                ROUND(AVG(
                    CASE WHEN ar.status IN ('PRESENT','LATE') THEN 100.0 ELSE 0.0 END
                ), 1) AS attendance_pct
            FROM students s
            JOIN course_enrollments ce ON ce.student_id = s.id
            JOIN courses c ON c.id = ce.course_id
            JOIN attendance_sessions sess ON sess.course_id = c.id
                AND sess.academic_year = ce.academic_year
            LEFT JOIN attendance_records ar ON ar.session_id = sess.id
                AND ar.student_id = s.id
            WHERE s.org_id = %s AND ce.academic_year = %s
              AND ce.semester = %s AND ce.status = 'ENROLLED'
            GROUP BY s.id, s.name, s.roll_number, s.program, c.id, c.code, c.name
            HAVING ROUND(AVG(
                CASE WHEN ar.status IN ('PRESENT','LATE') THEN 100.0 ELSE 0.0 END
            ), 1) < %s
            ORDER BY attendance_pct, s.name
            """,
            (org_id, academic_year, semester, threshold),
        )
        return [dict(r) for r in rows]

    @classmethod
    def faculty_workload(cls, org_id: str, academic_year: str) -> list[dict]:
        """Courses and weekly hours assigned to each faculty member."""
        rows = execute_query(
            """
            SELECT
                sp.name AS faculty_name,
                sp.employee_id,
                COUNT(DISTINCT fa.course_id)                AS courses_assigned,
                SUM(c.weekly_hours)                         AS total_weekly_hours
            FROM faculty_assignments fa
            JOIN staff_profiles sp ON sp.id = fa.faculty_id
            JOIN courses c ON c.id = fa.course_id
            WHERE fa.org_id = %s AND fa.academic_year = %s AND fa.status = 'ACTIVE'
            GROUP BY sp.id, sp.name, sp.employee_id
            ORDER BY total_weekly_hours DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def timetable_conflicts(cls, org_id: str, academic_year: str, semester: int) -> list[dict]:
        """Detect overlapping timetable slots for the same faculty or room."""
        rows = execute_query(
            """
            SELECT
                t1.id AS slot1, t1.faculty_id, t1.room, t1.day_of_week,
                t1.start_time AS t1_start, t1.end_time AS t1_end,
                t2.id AS slot2, t2.start_time AS t2_start, t2.end_time AS t2_end
            FROM timetable_slots t1
            JOIN timetable_slots t2
                ON t1.id < t2.id
               AND t1.day_of_week = t2.day_of_week
               AND t1.org_id = t2.org_id
               AND (t1.faculty_id = t2.faculty_id OR (t1.room IS NOT NULL AND t1.room = t2.room))
               AND t1.start_time < t2.end_time
               AND t2.start_time < t1.end_time
            WHERE t1.org_id = %s AND t1.academic_year = %s AND t1.semester = %s
            """,
            (org_id, academic_year, semester),
        )
        return [dict(r) for r in rows]
