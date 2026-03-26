"""E08-S03 — Leave Management"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import LeaveDecision, LeaveRequestCreate, LeaveTypeCreate

logger = logging.getLogger(__name__)


def _count_working_days(from_date: str, to_date: str) -> float:
    """Count Mon-Fri days between from and to (inclusive)."""
    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end   = datetime.strptime(to_date,   "%Y-%m-%d").date()
    if end < start:
        return 0.0
    days = 0.0
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days += 1
        current = date.fromordinal(current.toordinal() + 1)
    return days


class LeaveTypeService:

    @classmethod
    def create(cls, org_id: str, req: LeaveTypeCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM leave_types WHERE org_id = %s AND code = %s",
            (org_id, req.code.upper()),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Leave type code {req.code} already exists")

        lid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO leave_types
                (id, org_id, name, code, annual_quota, carry_forward,
                 max_carry_forward, is_paid, applicable_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (lid, org_id, req.name, req.code.upper(), req.annual_quota,
             req.carry_forward, req.max_carry_forward, req.is_paid, req.applicable_to),
        )])
        rows = execute_query("SELECT * FROM leave_types WHERE id = %s", (lid,))
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM leave_types WHERE org_id = %s AND is_active = TRUE ORDER BY name",
            (org_id,),
        )
        return [dict(r) for r in rows]


class LeaveService:

    @classmethod
    def apply(cls, org_id: str, staff_id: str,
               req: LeaveRequestCreate, actor_id: str) -> dict:
        # Validate staff
        staff_rows = execute_query(
            "SELECT id, user_id FROM staff_profiles WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (staff_id, org_id),
        )
        if not staff_rows:
            raise NotFoundError(f"Staff {staff_id} not found")

        # Validate leave type
        lt_rows = execute_query(
            "SELECT * FROM leave_types WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (req.leave_type_id, org_id),
        )
        if not lt_rows:
            raise NotFoundError(f"Leave type {req.leave_type_id} not found")
        lt = dict(lt_rows[0])

        days = _count_working_days(req.from_date, req.to_date)
        if days <= 0:
            raise BusinessRuleViolation(message="Invalid date range — from_date must be before to_date")

        # Check quota (approximate — doesn't account for carry-forward for now)
        used = cls._used_days(org_id, staff_id, req.leave_type_id,
                               req.from_date[:4])  # current year
        available = float(lt["annual_quota"]) - used
        if days > available:
            raise BusinessRuleViolation(
                message=f"Insufficient {lt['name']} balance. Available: {available:.1f} days, Requested: {days:.1f} days"
            )

        # Check for overlapping approved leave
        overlap = execute_query(
            """
            SELECT id FROM leave_requests
            WHERE staff_id = %s AND org_id = %s AND status = 'APPROVED'
              AND from_date <= %s::date AND to_date >= %s::date
            """,
            (staff_id, org_id, req.to_date, req.from_date),
        )
        if overlap:
            raise BusinessRuleViolation(message="Overlapping approved leave exists for this period")

        rid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO leave_requests
                (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (rid, org_id, staff_id, req.leave_type_id,
             req.from_date, req.to_date, days, req.reason),
        )])

        DomainEventBus.publish(DomainEvent(
            event_type="LeaveRequested",
            entity_type="leave_request",
            entity_id=rid,
            org_id=org_id,
            payload={"staff_id": staff_id, "days": days, "leave_type": lt["name"]},
            actor_id=actor_id,
        ))

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="leave_request", entity_id=rid, org_id=org_id,
                     module="E08-S03",
                     metadata={"days": days, "from": req.from_date, "to": req.to_date})

        return cls.get(org_id, rid)

    @classmethod
    def decide(cls, org_id: str, request_id: str,
                decision: LeaveDecision, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM leave_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Leave request {request_id} not found")
        req = dict(rows[0])

        if req["status"] != "PENDING":
            raise BusinessRuleViolation(message=f"Request is already {req['status']}")

        if decision.decision not in ("APPROVED", "REJECTED"):
            raise BusinessRuleViolation(message="decision must be 'APPROVED' or 'REJECTED'")

        execute_transaction([(
            """
            UPDATE leave_requests
            SET status = %s, approved_by = %s, approved_at = NOW(),
                rejection_note = %s
            WHERE id = %s AND org_id = %s
            """,
            (decision.decision, actor_id, decision.rejection_note, request_id, org_id),
        )])

        if decision.decision == "APPROVED":
            # Mark staff_attendance rows as LEAVE for the period
            cls._mark_attendance_leave(org_id, str(req["staff_id"]),
                                        str(req["from_date"]), str(req["to_date"]),
                                        actor_id)

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="leave_request", entity_id=request_id, org_id=org_id,
                     module="E08-S03", metadata={"decision": decision.decision})

        return cls.get(org_id, request_id)

    @classmethod
    def cancel(cls, org_id: str, request_id: str, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM leave_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Leave request {request_id} not found")
        if rows[0]["status"] not in ("PENDING",):
            raise BusinessRuleViolation(message="Only PENDING requests can be cancelled")

        execute_transaction([(
            "UPDATE leave_requests SET status = 'CANCELLED' WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )])
        return cls.get(org_id, request_id)

    @classmethod
    def get(cls, org_id: str, request_id: str) -> dict:
        rows = execute_query(
            """
            SELECT lr.*, lt.name AS leave_type_name, lt.is_paid,
                   sp.employee_code, u.display_name AS staff_name
            FROM leave_requests lr
            JOIN leave_types lt ON lt.id = lr.leave_type_id
            JOIN staff_profiles sp ON sp.id = lr.staff_id
            JOIN users u ON u.id = sp.user_id
            WHERE lr.id = %s AND lr.org_id = %s
            """,
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Leave request {request_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_staff(cls, org_id: str, staff_id: str,
                        status: str | None = None) -> list[dict]:
        sql = """
            SELECT lr.*, lt.name AS leave_type_name
            FROM leave_requests lr
            JOIN leave_types lt ON lt.id = lr.leave_type_id
            WHERE lr.staff_id = %s AND lr.org_id = %s
        """
        params: list = [staff_id, org_id]
        if status:
            sql += " AND lr.status = %s"
            params.append(status)
        sql += " ORDER BY lr.applied_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def list_pending(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT lr.*, lt.name AS leave_type_name, u.display_name AS staff_name, sp.department
            FROM leave_requests lr
            JOIN leave_types lt ON lt.id = lr.leave_type_id
            JOIN staff_profiles sp ON sp.id = lr.staff_id
            JOIN users u ON u.id = sp.user_id
            WHERE lr.org_id = %s AND lr.status = 'PENDING'
            ORDER BY lr.applied_at
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]

    @classmethod
    def get_balance(cls, org_id: str, staff_id: str, year: str) -> list[dict]:
        """Return leave balance per type for the given year."""
        leave_types = execute_query(
            "SELECT * FROM leave_types WHERE org_id = %s AND is_active = TRUE",
            (org_id,),
        )
        result = []
        for lt in leave_types:
            used = cls._used_days(org_id, staff_id, str(lt["id"]), year)
            result.append({
                "leave_type_id":   str(lt["id"]),
                "leave_type_name": lt["name"],
                "code":            lt["code"],
                "annual_quota":    float(lt["annual_quota"]),
                "used":            used,
                "available":       max(0.0, float(lt["annual_quota"]) - used),
            })
        return result

    @classmethod
    def _used_days(cls, org_id: str, staff_id: str,
                    leave_type_id: str, year: str) -> float:
        rows = execute_query(
            """
            SELECT COALESCE(SUM(days), 0) AS used
            FROM leave_requests
            WHERE staff_id = %s AND leave_type_id = %s AND org_id = %s
              AND status = 'APPROVED'
              AND EXTRACT(YEAR FROM from_date) = %s
            """,
            (staff_id, leave_type_id, org_id, year),
        )
        return float(rows[0]["used"] or 0) if rows else 0.0

    @classmethod
    def _mark_attendance_leave(cls, org_id: str, staff_id: str,
                                 from_date: str, to_date: str, actor_id: str) -> None:
        """Mark each working day in the leave period as LEAVE in staff_attendance."""
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d").date()
            end   = datetime.strptime(to_date,   "%Y-%m-%d").date()
            current = start
            ops = []
            while current <= end:
                if current.weekday() < 5:
                    ops.append((
                        """
                        INSERT INTO staff_attendance
                            (id, org_id, staff_id, date, status, source, marked_by)
                        VALUES (uuid_generate_v4(), %s, %s, %s, 'LEAVE', 'SYSTEM', %s)
                        ON CONFLICT (org_id, staff_id, date) DO UPDATE SET status = 'LEAVE'
                        """,
                        (org_id, staff_id, current.isoformat(), actor_id),
                    ))
                current = date.fromordinal(current.toordinal() + 1)
            if ops:
                execute_transaction(ops)
        except Exception as exc:
            logger.warning("LeaveService: attendance marking failed (non-fatal): %s", exc)
