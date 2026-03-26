"""EC-HR-03 — Employee Department Assignments

Shared / cross-department faculty tracking.

Rules
─────
• A staff member may be assigned to multiple departments simultaneously.
• weight_pct values for the same staff_id must sum to exactly 100.
• Exactly one assignment may have is_primary = TRUE per staff member.
• Used by Regulatory E14 to compute faculty-to-student ratio per department.
"""
from __future__ import annotations

import uuid
import logging
from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DepartmentAssignmentCreate(BaseModel):
    staff_id: str
    department_id: str
    department_name: str
    weight_pct: float
    is_primary: bool = False
    effective_from: date
    effective_to: Optional[date] = None

    @field_validator("weight_pct")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v <= 0 or v > 100:
            raise ValueError("weight_pct must be > 0 and <= 100")
        return v


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EmployeeDepartmentService:

    @classmethod
    def list_assignments(
        cls,
        org_id: str,
        staff_id: str,
        active_only: bool = True,
    ) -> list[dict]:
        sql = """
            SELECT *
            FROM employee_department_assignments
            WHERE org_id = %s AND staff_id = %s
        """
        params: list = [org_id, staff_id]
        if active_only:
            sql += " AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)"
        sql += " ORDER BY is_primary DESC, department_name"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def assign(
        cls,
        org_id: str,
        req: DepartmentAssignmentCreate,
        actor_id: str,
    ) -> dict:
        """Create a department assignment, enforcing weight_pct sum = 100."""
        # Fetch existing active assignments for this staff member
        existing = cls.list_assignments(org_id, req.staff_id, active_only=True)

        # Check duplicate department
        for a in existing:
            if str(a["department_id"]) == req.department_id:
                raise BusinessRuleViolation(
                    f"Staff {req.staff_id} is already assigned to department {req.department_id}"
                )

        # Validate weight sum does not exceed 100
        current_total = sum(float(a["weight_pct"]) for a in existing)
        if current_total + req.weight_pct > 100.01:  # small float tolerance
            raise BusinessRuleViolation(
                f"Total weight_pct would be {current_total + req.weight_pct:.1f}; "
                "must not exceed 100"
            )

        # If marking as primary, ensure no other primary exists
        if req.is_primary:
            for a in existing:
                if a["is_primary"]:
                    raise BusinessRuleViolation(
                        f"Staff {req.staff_id} already has a primary department assignment. "
                        "Update the existing primary first."
                    )

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO employee_department_assignments
                (id, org_id, staff_id, department_id, department_name,
                 weight_pct, is_primary, effective_from, effective_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (aid, org_id, req.staff_id, req.department_id, req.department_name,
             req.weight_pct, req.is_primary, req.effective_from, req.effective_to),
        )])

        AuditLog.log(
            org_id=org_id, actor_id=actor_id, actor_type="human",
            action=AuditAction.CREATE,
            resource_type="employee_department_assignment",
            resource_id=aid,
            detail={
                "staff_id": req.staff_id,
                "department_id": req.department_id,
                "weight_pct": req.weight_pct,
            },
        )

        rows = execute_query(
            "SELECT * FROM employee_department_assignments WHERE id = %s AND org_id = %s",
            (aid, org_id),
        )
        return dict(rows[0])

    @classmethod
    def remove(cls, org_id: str, assignment_id: str, actor_id: str) -> None:
        """End-date an assignment (sets effective_to = today)."""
        rows = execute_query(
            "SELECT * FROM employee_department_assignments WHERE id = %s AND org_id = %s",
            (assignment_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Assignment {assignment_id} not found")

        execute_transaction([(
            """UPDATE employee_department_assignments
               SET effective_to = CURRENT_DATE
               WHERE id = %s AND org_id = %s""",
            (assignment_id, org_id),
        )])

        AuditLog.log(
            org_id=org_id, actor_id=actor_id, actor_type="human",
            action=AuditAction.UPDATE,
            resource_type="employee_department_assignment",
            resource_id=assignment_id,
            detail={"action": "end_dated"},
        )
        logger.info("Department assignment %s end-dated by %s", assignment_id, actor_id)
