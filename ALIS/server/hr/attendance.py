"""E08-S06 — Staff Attendance"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import StaffAttendanceBulk, StaffAttendanceMark

logger = logging.getLogger(__name__)


class StaffAttendanceService:

    @classmethod
    def mark(cls, org_id: str, record: StaffAttendanceMark, actor_id: str) -> dict:
        execute_transaction([(
            """
            INSERT INTO staff_attendance
                (id, org_id, staff_id, date, check_in, check_out,
                 status, source, remarks, marked_by)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, 'MANUAL', %s, %s)
            ON CONFLICT (org_id, staff_id, date) DO UPDATE SET
                check_in  = EXCLUDED.check_in,
                check_out = EXCLUDED.check_out,
                status    = EXCLUDED.status,
                remarks   = EXCLUDED.remarks,
                marked_by = EXCLUDED.marked_by
            """,
            (org_id, record.staff_id, record.date,
             record.check_in, record.check_out,
             record.status.value, record.remarks, actor_id),
        )])

        rows = execute_query(
            "SELECT * FROM staff_attendance WHERE org_id = %s AND staff_id = %s AND date = %s",
            (org_id, record.staff_id, record.date),
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def bulk_mark(cls, org_id: str, req: StaffAttendanceBulk, actor_id: str) -> dict:
        ops = []
        for record in req.records:
            ops.append((
                """
                INSERT INTO staff_attendance
                    (id, org_id, staff_id, date, check_in, check_out,
                     status, source, remarks, marked_by)
                VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, 'MANUAL', %s, %s)
                ON CONFLICT (org_id, staff_id, date) DO UPDATE SET
                    check_in  = EXCLUDED.check_in,
                    check_out = EXCLUDED.check_out,
                    status    = EXCLUDED.status,
                    remarks   = EXCLUDED.remarks,
                    marked_by = EXCLUDED.marked_by
                """,
                (org_id, record.staff_id, req.date,
                 record.check_in, record.check_out,
                 record.status.value, record.remarks, actor_id),
            ))
        if ops:
            execute_transaction(ops)

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="staff_attendance_bulk", entity_id=req.date, org_id=org_id,
                     module="E08-S06", metadata={"date": req.date, "count": len(ops)})

        return {"marked": len(ops), "date": req.date}

    @classmethod
    def get_monthly_summary(cls, org_id: str, staff_id: str,
                              month: int, year: int) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                                AS total_days,
                COUNT(*) FILTER (WHERE status = 'PRESENT')             AS present,
                COUNT(*) FILTER (WHERE status = 'ABSENT')              AS absent,
                COUNT(*) FILTER (WHERE status = 'HALF_DAY')            AS half_day,
                COUNT(*) FILTER (WHERE status = 'LEAVE')               AS on_leave,
                COUNT(*) FILTER (WHERE status = 'WFH')                 AS wfh,
                COUNT(*) FILTER (WHERE status = 'HOLIDAY')             AS holidays
            FROM staff_attendance
            WHERE staff_id = %s AND org_id = %s
              AND EXTRACT(MONTH FROM date) = %s
              AND EXTRACT(YEAR FROM date) = %s
            """,
            (staff_id, org_id, month, year),
        )
        summary = dict(rows[0]) if rows else {}

        # Attendance %
        working = int(summary.get("total_days") or 0) - int(summary.get("holidays") or 0)
        present = int(summary.get("present") or 0) + int(summary.get("wfh") or 0)
        summary["attendance_pct"] = round((present / working * 100), 1) if working > 0 else 0.0
        summary["staff_id"] = staff_id
        summary["month"] = month
        summary["year"]  = year

        return summary

    @classmethod
    def get_daily_roster(cls, org_id: str, date: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT sa.*, u.display_name AS staff_name, sp.department, sp.employee_code
            FROM staff_attendance sa
            JOIN staff_profiles sp ON sp.id = sa.staff_id
            JOIN users u ON u.id = sp.user_id
            WHERE sa.org_id = %s AND sa.date = %s
            ORDER BY sp.department, u.name
            """,
            (org_id, date),
        )
        return [dict(r) for r in rows]

    @classmethod
    def get_department_summary(cls, org_id: str, month: int, year: int) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                sp.department,
                COUNT(DISTINCT sa.staff_id) AS staff_count,
                ROUND(
                    AVG(CASE WHEN sa.status IN ('PRESENT','WFH') THEN 100.0 ELSE 0.0 END), 1
                ) AS avg_attendance_pct
            FROM staff_attendance sa
            JOIN staff_profiles sp ON sp.id = sa.staff_id
            WHERE sa.org_id = %s
              AND EXTRACT(MONTH FROM sa.date) = %s
              AND EXTRACT(YEAR FROM sa.date) = %s
              AND sa.status != 'HOLIDAY'
            GROUP BY sp.department
            ORDER BY sp.department
            """,
            (org_id, month, year),
        )
        return [dict(r) for r in rows]
