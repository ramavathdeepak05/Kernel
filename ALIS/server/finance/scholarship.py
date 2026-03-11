"""E07-S05 — Scholarship Management"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import ScholarshipAssign, ScholarshipCreate

logger = logging.getLogger(__name__)


class ScholarshipService:

    @classmethod
    def create(cls, org_id: str, req: ScholarshipCreate, actor_id: str) -> dict:
        import json
        sid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO scholarships
                (id, org_id, name, description, type, discount_type, discount_value,
                 academic_year, max_recipients, criteria, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (sid, org_id, req.name, req.description, req.type.value,
             req.discount_type.value, req.discount_value,
             req.academic_year, req.max_recipients,
             json.dumps(req.criteria) if req.criteria else None, actor_id),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="scholarship", entity_id=sid, org_id=org_id,
                     module="E07-S05",
                     metadata={"name": req.name, "type": req.type.value})

        return cls.get(org_id, sid)

    @classmethod
    def assign(cls, org_id: str, req: ScholarshipAssign, actor_id: str) -> dict:
        scholarship = execute_query(
            "SELECT * FROM scholarships WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (req.scholarship_id, org_id),
        )
        if not scholarship:
            raise NotFoundError(f"Scholarship {req.scholarship_id} not found")
        sc = dict(scholarship[0])

        # Max recipients check
        if sc["max_recipients"]:
            current = execute_query(
                "SELECT COUNT(*) AS cnt FROM scholarship_assignments WHERE scholarship_id = %s AND academic_year = %s AND status = 'ACTIVE' AND org_id = %s",
                (req.scholarship_id, req.academic_year, org_id),
            )
            if int(current[0]["cnt"]) >= int(sc["max_recipients"]):
                raise BusinessRuleViolation(message="Scholarship has reached maximum recipients")

        # Compute discount amount for reference
        if sc["discount_type"] == "FIXED":
            amount_applied = float(sc["discount_value"])
        else:
            # For percentage, store the percentage value; invoice service applies it
            amount_applied = float(sc["discount_value"])

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO scholarship_assignments
                (id, org_id, scholarship_id, student_id, academic_year, amount_applied, assigned_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scholarship_id, student_id, academic_year)
            DO UPDATE SET status = 'ACTIVE', amount_applied = EXCLUDED.amount_applied,
                          assigned_by = EXCLUDED.assigned_by, assigned_at = NOW()
            """,
            (aid, org_id, req.scholarship_id, req.student_id,
             req.academic_year, amount_applied, actor_id),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="scholarship_assignment", entity_id=aid, org_id=org_id,
                     module="E07-S05",
                     metadata={"scholarship_id": req.scholarship_id,
                               "student_id": req.student_id})

        rows = execute_query(
            "SELECT sa.*, s.name AS scholarship_name FROM scholarship_assignments sa JOIN scholarships s ON s.id = sa.scholarship_id WHERE sa.id = %s OR (sa.scholarship_id = %s AND sa.student_id = %s AND sa.academic_year = %s)",
            (aid, req.scholarship_id, req.student_id, req.academic_year),
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def revoke(cls, org_id: str, assignment_id: str, actor_id: str) -> dict:
        execute_transaction([(
            "UPDATE scholarship_assignments SET status = 'SUSPENDED' WHERE id = %s AND org_id = %s",
            (assignment_id, org_id),
        )])
        rows = execute_query(
            "SELECT * FROM scholarship_assignments WHERE id = %s", (assignment_id,)
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def get(cls, org_id: str, scholarship_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM scholarships WHERE id = %s AND org_id = %s",
            (scholarship_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Scholarship {scholarship_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM scholarships WHERE org_id = %s AND academic_year = %s ORDER BY name",
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str,
                          academic_year: str | None = None) -> list[dict]:
        sql = """
            SELECT sa.*, s.name AS scholarship_name, s.type, s.discount_type, s.discount_value
            FROM scholarship_assignments sa
            JOIN scholarships s ON s.id = sa.scholarship_id
            WHERE sa.student_id = %s AND sa.org_id = %s
        """
        params: list = [student_id, org_id]
        if academic_year:
            sql += " AND sa.academic_year = %s"
            params.append(academic_year)
        sql += " ORDER BY sa.assigned_at DESC"
        return [dict(r) for r in execute_query(sql, params)]
