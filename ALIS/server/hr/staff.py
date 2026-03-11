"""E08-S01 — Staff Profile Management"""

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import StaffProfileCreate, StaffProfileUpdate

logger = logging.getLogger(__name__)


class StaffService:

    @classmethod
    def create(cls, org_id: str, req: StaffProfileCreate, actor_id: str) -> dict:
        # Validate user exists
        user = execute_query(
            "SELECT id, name, email FROM users WHERE id = %s AND org_id = %s",
            (req.user_id, org_id),
        )
        if not user:
            raise NotFoundError(f"User {req.user_id} not found")

        # Check for duplicate employee_code
        existing = execute_query(
            "SELECT id FROM staff_profiles WHERE org_id = %s AND employee_code = %s",
            (org_id, req.employee_code),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Employee code {req.employee_code} already exists"
            )

        # Check if staff profile already exists for user
        existing_user = execute_query(
            "SELECT id FROM staff_profiles WHERE org_id = %s AND user_id = %s",
            (org_id, req.user_id),
        )
        if existing_user:
            raise BusinessRuleViolation(
                message=f"Staff profile already exists for user {req.user_id}"
            )

        sid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO staff_profiles
                (id, org_id, user_id, employee_code, department, designation,
                 employment_type, date_of_joining, salary_grade, reporting_to,
                 specializations, qualifications, experience_years)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (sid, org_id, req.user_id, req.employee_code, req.department,
             req.designation, req.employment_type.value, req.date_of_joining,
             req.salary_grade, req.reporting_to,
             req.specializations,
             json.dumps(req.qualifications) if req.qualifications else None,
             req.experience_years),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="staff_profile", entity_id=sid, org_id=org_id,
                     module="E08-S01",
                     metadata={"employee_code": req.employee_code,
                               "department": req.department})

        return cls.get(org_id, sid)

    @classmethod
    def update(cls, org_id: str, staff_id: str,
               req: StaffProfileUpdate, actor_id: str) -> dict:
        cls.get(org_id, staff_id)

        fields = []
        values: list = []
        for field, col in [
            ("department", "department"), ("designation", "designation"),
            ("employment_type", "employment_type"), ("salary_grade", "salary_grade"),
            ("reporting_to", "reporting_to"), ("specializations", "specializations"),
            ("experience_years", "experience_years"),
        ]:
            val = getattr(req, field)
            if val is not None:
                if field == "employment_type":
                    val = val.value
                fields.append(f"{col} = %s")
                values.append(val)

        if req.qualifications is not None:
            fields.append("qualifications = %s::jsonb")
            values.append(json.dumps(req.qualifications))

        if not fields:
            return cls.get(org_id, staff_id)

        fields.append("updated_at = NOW()")
        values.extend([staff_id, org_id])
        execute_transaction([(
            f"UPDATE staff_profiles SET {', '.join(fields)} WHERE id = %s AND org_id = %s",
            values,
        )])

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="staff_profile", entity_id=staff_id, org_id=org_id,
                     module="E08-S01", metadata={"fields": list(req.model_fields_set)})

        return cls.get(org_id, staff_id)

    @classmethod
    def deactivate(cls, org_id: str, staff_id: str,
                    date_of_leaving: str, actor_id: str) -> dict:
        cls.get(org_id, staff_id)
        execute_transaction([(
            "UPDATE staff_profiles SET is_active = FALSE, date_of_leaving = %s, updated_at = NOW() WHERE id = %s AND org_id = %s",
            (date_of_leaving, staff_id, org_id),
        )])
        return cls.get(org_id, staff_id)

    @classmethod
    def get(cls, org_id: str, staff_id: str) -> dict:
        rows = execute_query(
            """
            SELECT sp.*, u.name, u.email
            FROM staff_profiles sp
            JOIN users u ON u.id = sp.user_id
            WHERE sp.id = %s AND sp.org_id = %s
            """,
            (staff_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Staff profile {staff_id} not found")
        return dict(rows[0])

    @classmethod
    def get_by_user(cls, org_id: str, user_id: str) -> dict:
        rows = execute_query(
            "SELECT sp.*, u.name, u.email FROM staff_profiles sp JOIN users u ON u.id = sp.user_id WHERE sp.user_id = %s AND sp.org_id = %s",
            (user_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Staff profile for user {user_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, department: str | None = None,
              employment_type: str | None = None,
              is_active: bool = True) -> list[dict]:
        sql = """
            SELECT sp.*, u.name, u.email
            FROM staff_profiles sp
            JOIN users u ON u.id = sp.user_id
            WHERE sp.org_id = %s AND sp.is_active = %s
        """
        params: list = [org_id, is_active]
        if department:
            sql += " AND sp.department = %s"
            params.append(department)
        if employment_type:
            sql += " AND sp.employment_type = %s"
            params.append(employment_type)
        sql += " ORDER BY u.name"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def get_workload_summary(cls, org_id: str, staff_id: str,
                              academic_year: str) -> dict:
        """E08-S02: Faculty workload — courses assigned + hours."""
        profile = cls.get(org_id, staff_id)
        courses = execute_query(
            """
            SELECT c.id, c.code, c.name, c.credits, c.semester,
                   fa.created_at AS assigned_at
            FROM faculty_assignments fa
            JOIN courses c ON c.id = fa.course_id
            WHERE fa.faculty_id = %s AND fa.academic_year = %s AND fa.org_id = %s
            ORDER BY c.semester, c.name
            """,
            (str(profile["user_id"]), academic_year, org_id),
        )
        course_list = [dict(c) for c in courses]
        total_credits = sum(int(c["credits"]) for c in course_list)

        # Attendance sessions conducted
        sessions = execute_query(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE is_finalized) AS finalized
            FROM attendance_sessions
            WHERE faculty_id = %s AND academic_year = %s AND org_id = %s
            """,
            (str(profile["user_id"]), academic_year, org_id),
        )
        session_stats = dict(sessions[0]) if sessions else {}

        return {
            "staff_id": staff_id,
            "academic_year": academic_year,
            "courses_assigned": len(course_list),
            "total_credits": total_credits,
            "courses": course_list,
            "sessions_conducted": int(session_stats.get("total") or 0),
            "sessions_finalized": int(session_stats.get("finalized") or 0),
        }
