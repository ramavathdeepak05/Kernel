"""E11-S05 — Custom Report Builder

Allows staff to define and save report queries by selecting:
- module (admissions, academics, finance, etc.)
- filters (academic_year, semester, program, date range, ...)
- columns (subset of available fields per module)

Saved reports can be re-run or scheduled for export.
"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import SavedReportCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available columns per module (used for validation and query building)
# ---------------------------------------------------------------------------
AVAILABLE_COLUMNS: dict[str, list[str]] = {
    "admissions": [
        "applicant_name", "email", "program_applied", "academic_year",
        "status", "submitted_at", "source_channel", "assigned_counsellor",
    ],
    "academics": [
        "student_name", "roll_number", "program", "course_code", "course_name",
        "semester", "academic_year", "attendance_pct", "enrollment_status",
    ],
    "examinations": [
        "student_name", "roll_number", "course_code", "exam_type",
        "marks_obtained", "max_marks", "grade", "grade_points",
        "is_pass", "is_absent", "academic_year", "semester",
    ],
    "finance": [
        "student_name", "roll_number", "invoice_number", "total_amount",
        "amount_paid", "outstanding", "due_date", "status", "academic_year",
    ],
    "hr": [
        "employee_name", "employee_id", "department", "employment_type",
        "designation", "join_date", "status",
    ],
    "services": [
        "student_name", "roll_number", "hostel_block", "room_number",
        "route_name", "book_title", "borrow_date", "return_date",
    ],
}


class CustomReportService:

    @classmethod
    def create(cls, org_id: str, req: SavedReportCreate, actor_id: str) -> dict:
        rid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO saved_reports
                (id, org_id, name, description, module, filters, columns, created_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            """,
            (
                rid, org_id, req.name, req.description, req.module.value,
                __import__('json').dumps(req.filters),
                __import__('json').dumps(req.columns),
                actor_id,
            ),
        )])
        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="saved_report", entity_id=rid, org_id=org_id,
            module="E11-S05", metadata={"name": req.name, "module": req.module.value},
        )
        return cls.get(org_id, rid)

    @classmethod
    def get(cls, org_id: str, report_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM saved_reports WHERE id = %s AND org_id = %s",
            (report_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Report {report_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, module: str | None = None) -> list[dict]:
        sql = "SELECT * FROM saved_reports WHERE org_id = %s"
        params: list = [org_id]
        if module:
            sql += " AND module = %s"; params.append(module)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def delete(cls, org_id: str, report_id: str) -> dict:
        cls.get(org_id, report_id)
        execute_transaction([(
            "DELETE FROM saved_reports WHERE id = %s AND org_id = %s",
            (report_id, org_id),
        )])
        return {"status": "deleted", "id": report_id}

    @classmethod
    def run(cls, org_id: str, report_id: str) -> list[dict]:
        """Execute a saved report and return raw rows."""
        report = cls.get(org_id, report_id)
        module  = report["module"]
        filters = report["filters"] or {}
        columns = report["columns"] or []

        # Update last_run_at
        execute_transaction([(
            "UPDATE saved_reports SET last_run_at = NOW() WHERE id = %s",
            (report_id,),
        )])

        return cls._execute_module_query(org_id, module, filters, columns)

    @classmethod
    def get_schema(cls, module: str) -> dict:
        """Return available columns and filter keys for a module."""
        return {
            "module": module,
            "available_columns": AVAILABLE_COLUMNS.get(module, []),
        }

    # ------------------------------------------------------------------
    # Internal — module-specific query executor
    # ------------------------------------------------------------------

    @classmethod
    def _execute_module_query(
        cls, org_id: str, module: str, filters: dict, columns: list[str]
    ) -> list[dict]:
        academic_year = filters.get("academic_year")
        semester      = filters.get("semester")
        program       = filters.get("program")

        if module == "admissions":
            sql = """
                SELECT a.applicant_name, a.email, a.program_applied, a.academic_year,
                       a.status, a.submitted_at, a.source_channel,
                       c.name AS assigned_counsellor
                FROM applications a
                LEFT JOIN counsellors c ON c.id = a.assigned_counsellor_id
                WHERE a.org_id = %s
            """
            params: list = [org_id]
            if academic_year: sql += " AND a.academic_year = %s"; params.append(academic_year)

        elif module == "academics":
            sql = """
                SELECT s.name AS student_name, s.roll_number, s.program,
                       c.code AS course_code, c.name AS course_name,
                       ce.semester, ce.academic_year, ce.status AS enrollment_status
                FROM course_enrollments ce
                JOIN students s ON s.id = ce.student_id
                JOIN courses c ON c.id = ce.course_id
                WHERE ce.org_id = %s
            """
            params = [org_id]
            if academic_year: sql += " AND ce.academic_year = %s"; params.append(academic_year)
            if semester:      sql += " AND ce.semester = %s"; params.append(semester)
            if program:       sql += " AND s.program = %s"; params.append(program)

        elif module == "examinations":
            sql = """
                SELECT s.name AS student_name, s.roll_number,
                       c.code AS course_code, g.academic_year, g.semester,
                       g.marks_obtained, g.max_marks, g.grade, g.grade_points,
                       g.is_pass, g.is_absent
                FROM grades g
                JOIN students s ON s.id = g.student_id
                JOIN courses c ON c.id = g.course_id
                WHERE g.org_id = %s AND g.is_published = TRUE
            """
            params = [org_id]
            if academic_year: sql += " AND g.academic_year = %s"; params.append(academic_year)
            if semester:      sql += " AND g.semester = %s"; params.append(semester)

        elif module == "finance":
            sql = """
                SELECT s.name AS student_name, s.roll_number,
                       fi.invoice_number, fi.total_amount, fi.amount_paid,
                       (fi.total_amount - fi.amount_paid) AS outstanding,
                       fi.due_date, fi.status, fi.academic_year
                FROM fee_invoices fi
                JOIN students s ON s.id = fi.student_id
                WHERE fi.org_id = %s
            """
            params = [org_id]
            if academic_year: sql += " AND fi.academic_year = %s"; params.append(academic_year)

        elif module == "hr":
            sql = """
                SELECT name AS employee_name, employee_id, department,
                       employment_type, designation, join_date, status
                FROM staff_profiles
                WHERE org_id = %s AND status != 'TERMINATED'
            """
            params = [org_id]

        else:
            return []

        sql += " ORDER BY 1 LIMIT 5000"
        rows = execute_query(sql, params)
        raw  = [dict(r) for r in rows]

        # Filter to requested columns (if specified)
        if columns:
            raw = [{k: v for k, v in row.items() if k in columns} for row in raw]
        return raw
