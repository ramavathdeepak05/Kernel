"""E08-S04 — Payroll Processing

Flow:
  1. Define payroll components (HRA, PF, etc.)
  2. Assign salary structure to each staff member
  3. Run monthly payroll:
     - Pull attendance for the month → compute LOP days
     - Apply earnings + deductions → net salary
     - Generate payslip record (+ PDF via ReportLab)
     - Status: DRAFT → PROCESSED → PAID
"""
from __future__ import annotations

import json
import logging
import uuid
from io import BytesIO

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import PayrollComponentCreate, PayslipGenerate, SalaryStructureCreate

logger = logging.getLogger(__name__)


class PayrollComponentService:

    @classmethod
    def create(cls, org_id: str, req: PayrollComponentCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM payroll_components WHERE org_id = %s AND code = %s",
            (org_id, req.code.upper()),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Component code {req.code} already exists")

        cid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO payroll_components
                (id, org_id, name, code, component_type, calc_type, value, is_taxable)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (cid, org_id, req.name, req.code.upper(),
             req.component_type.value, req.calc_type.value,
             req.value, req.is_taxable),
        )])
        rows = execute_query("SELECT * FROM payroll_components WHERE id = %s", (cid,))
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM payroll_components WHERE org_id = %s AND is_active = TRUE ORDER BY component_type, name",
            (org_id,),
        )
        return [dict(r) for r in rows]


class SalaryStructureService:

    @classmethod
    def create(cls, org_id: str, req: SalaryStructureCreate, actor_id: str) -> dict:
        # Close any existing open structure
        execute_transaction([(
            """
            UPDATE staff_salary_structures
            SET effective_to = %s::date - INTERVAL '1 day'
            WHERE staff_id = %s AND org_id = %s AND effective_to IS NULL
            """,
            (req.effective_from, req.staff_id, org_id),
        )])

        sid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO staff_salary_structures
                (id, org_id, staff_id, basic_salary, components, effective_from, created_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (sid, org_id, req.staff_id, req.basic_salary,
             json.dumps(req.components), req.effective_from, actor_id),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="salary_structure", entity_id=sid, org_id=org_id,
                     module="E08-S04",
                     metadata={"staff_id": req.staff_id, "basic": req.basic_salary})

        rows = execute_query("SELECT * FROM staff_salary_structures WHERE id = %s", (sid,))
        return dict(rows[0])

    @classmethod
    def get_active(cls, org_id: str, staff_id: str) -> dict | None:
        rows = execute_query(
            """
            SELECT * FROM staff_salary_structures
            WHERE staff_id = %s AND org_id = %s
              AND effective_from <= CURRENT_DATE
              AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
            ORDER BY effective_from DESC LIMIT 1
            """,
            (staff_id, org_id),
        )
        return dict(rows[0]) if rows else None


class PayslipService:

    @classmethod
    def generate(cls, org_id: str, staff_id: str,
                  req: PayslipGenerate, actor_id: str) -> dict:
        """Compute and upsert a payslip for the given month/year."""
        # Idempotency check
        existing = execute_query(
            "SELECT * FROM payslips WHERE staff_id = %s AND month = %s AND year = %s AND org_id = %s",
            (staff_id, req.month, req.year, org_id),
        )
        if existing and dict(existing[0])["status"] not in ("DRAFT",):
            raise BusinessRuleViolation(
                message=f"Payslip for {req.month}/{req.year} already processed"
            )

        structure = SalaryStructureService.get_active(org_id, staff_id)
        if not structure:
            raise BusinessRuleViolation(
                message=f"No active salary structure for staff {staff_id}"
            )

        basic = float(structure["basic_salary"])

        # Attendance for the month
        att_rows = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('HOLIDAY', 'LEAVE')) AS working_days,
                COUNT(*) FILTER (WHERE status = 'PRESENT' OR status = 'WFH') AS present_days,
                COUNT(*) FILTER (WHERE status = 'LEAVE')   AS leave_days,
                COUNT(*) FILTER (WHERE status = 'ABSENT')  AS absent_days
            FROM staff_attendance
            WHERE staff_id = %s AND org_id = %s
              AND EXTRACT(MONTH FROM date) = %s
              AND EXTRACT(YEAR FROM date) = %s
            """,
            (staff_id, org_id, req.month, req.year),
        )
        att = dict(att_rows[0]) if att_rows else {}
        working_days = int(att.get("working_days") or 26)  # default 26 working days
        present_days = int(att.get("present_days") or working_days)
        leave_days   = float(att.get("leave_days") or 0)
        absent_days  = float(att.get("absent_days") or 0)
        lop_days     = absent_days  # Loss of Pay = unpaid absences

        # Attendance ratio
        ratio = (present_days + leave_days) / working_days if working_days > 0 else 1.0
        ratio = min(ratio, 1.0)

        # Load components
        component_overrides = structure.get("components") or []
        if isinstance(component_overrides, str):
            component_overrides = json.loads(component_overrides)

        org_components = {r["id"]: dict(r) for r in execute_query(
            "SELECT * FROM payroll_components WHERE org_id = %s AND is_active = TRUE",
            (org_id,),
        )}

        overrides_map = {c["component_id"]: c.get("override_value") for c in component_overrides}

        earnings    = {}
        deductions  = {}
        gross = basic * ratio

        for comp_id, comp in org_components.items():
            val = float(overrides_map.get(str(comp_id)) or comp["value"])
            if comp["calc_type"] == "PERCENTAGE_OF_BASIC":
                amount = (val / 100) * basic
            elif comp["calc_type"] == "PERCENTAGE_OF_GROSS":
                amount = (val / 100) * gross
            else:
                amount = val

            amount = round(amount * ratio, 2)

            if comp["component_type"] == "EARNING":
                earnings[comp["name"]] = amount
                gross += amount
            else:
                deductions[comp["name"]] = amount

        total_earnings   = basic * ratio + sum(earnings.values())
        total_deductions = sum(deductions.values())
        net_salary       = round(total_earnings - total_deductions, 2)

        pid = str(uuid.uuid4()) if not existing else str(existing[0]["id"])
        if existing:
            execute_transaction([(
                """
                UPDATE payslips SET
                    working_days = %s, present_days = %s, leave_days = %s, lop_days = %s,
                    gross_salary = %s, total_deductions = %s, net_salary = %s,
                    earnings_detail = %s::jsonb, deductions_detail = %s::jsonb,
                    processed_by = %s, processed_at = NOW(), status = 'PROCESSED'
                WHERE id = %s
                """,
                (working_days, present_days, leave_days, lop_days,
                 round(total_earnings, 2), total_deductions, net_salary,
                 json.dumps(earnings), json.dumps(deductions),
                 actor_id, pid),
            )])
        else:
            execute_transaction([(
                """
                INSERT INTO payslips
                    (id, org_id, staff_id, month, year, working_days, present_days,
                     leave_days, lop_days, gross_salary, total_deductions, net_salary,
                     earnings_detail, deductions_detail, processed_by, processed_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, NOW(), 'PROCESSED')
                """,
                (pid, org_id, staff_id, req.month, req.year,
                 working_days, present_days, leave_days, lop_days,
                 round(total_earnings, 2), total_deductions, net_salary,
                 json.dumps(earnings), json.dumps(deductions), actor_id),
            )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="payslip", entity_id=pid, org_id=org_id,
                     module="E08-S04",
                     metadata={"staff_id": staff_id, "month": req.month,
                               "year": req.year, "net": net_salary})

        return cls.get(org_id, pid)

    @classmethod
    def mark_paid(cls, org_id: str, payslip_id: str, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM payslips WHERE id = %s AND org_id = %s",
            (payslip_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Payslip {payslip_id} not found")
        if rows[0]["status"] != "PROCESSED":
            raise BusinessRuleViolation(message="Only PROCESSED payslips can be marked as PAID")

        execute_transaction([(
            "UPDATE payslips SET status = 'PAID', paid_at = NOW() WHERE id = %s AND org_id = %s",
            (payslip_id, org_id),
        )])
        return cls.get(org_id, payslip_id)

    @classmethod
    def get(cls, org_id: str, payslip_id: str) -> dict:
        rows = execute_query(
            """
            SELECT p.*, u.display_name AS staff_name, sp.employee_code, sp.designation
            FROM payslips p
            JOIN staff_profiles sp ON sp.id = p.staff_id
            JOIN users u ON u.id = sp.user_id
            WHERE p.id = %s AND p.org_id = %s
            """,
            (payslip_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Payslip {payslip_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_staff(cls, org_id: str, staff_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM payslips WHERE staff_id = %s AND org_id = %s ORDER BY year DESC, month DESC",
            (staff_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def monthly_summary(cls, org_id: str, month: int, year: int) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*) AS total_staff,
                ROUND(SUM(net_salary), 2) AS total_net_payroll,
                ROUND(SUM(gross_salary), 2) AS total_gross_payroll,
                ROUND(SUM(total_deductions), 2) AS total_deductions,
                COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
                COUNT(*) FILTER (WHERE status = 'PROCESSED') AS processed_count
            FROM payslips
            WHERE org_id = %s AND month = %s AND year = %s
            """,
            (org_id, month, year),
        )
        return dict(rows[0]) if rows else {}
