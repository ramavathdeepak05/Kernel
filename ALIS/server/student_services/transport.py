"""E09-S03 — Transport Management"""
from __future__ import annotations

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction, safe_identifier

from .models import TransportAssignCreate, TransportRouteCreate

logger = logging.getLogger(__name__)


class TransportService:

    # ── Routes ───────────────────────────────────────────────

    @classmethod
    def create_route(cls, org_id: str, req: TransportRouteCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM transport_routes WHERE org_id = %s AND route_code = %s",
            (org_id, req.route_code.upper()),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Route code {req.route_code} already exists")

        rid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO transport_routes
                (id, org_id, route_name, route_code, stops, vehicle_number,
                 driver_name, driver_contact, capacity)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
            """,
            (rid, org_id, req.route_name, req.route_code.upper(),
             json.dumps(req.stops), req.vehicle_number,
             req.driver_name, req.driver_contact, req.capacity),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="transport_route", entity_id=rid, org_id=org_id,
                     module="E09-S03", metadata={"code": req.route_code})

        return cls.get_route(org_id, rid)

    @classmethod
    def update_route(cls, org_id: str, route_id: str, updates: dict, actor_id: str) -> dict:
        allowed = {"route_name", "stops", "vehicle_number", "driver_name",
                   "driver_contact", "capacity", "is_active"}
        fields = []
        values: list = []
        for k, v in updates.items():
            if k in allowed:
                if k == "stops":
                    fields.append("stops = %s::jsonb")
                    values.append(json.dumps(v))
                else:
                    fields.append(f"{safe_identifier(k)} = %s")
                    values.append(v)
        if not fields:
            return cls.get_route(org_id, route_id)
        values.extend([route_id, org_id])
        execute_transaction([(
            f"UPDATE transport_routes SET {', '.join(fields)} WHERE id = %s AND org_id = %s",
            values,
        )])
        return cls.get_route(org_id, route_id)

    @classmethod
    def get_route(cls, org_id: str, route_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM transport_routes WHERE id = %s AND org_id = %s",
            (route_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Route {route_id} not found")
        return dict(rows[0])

    @classmethod
    def list_routes(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT r.*,
                   COUNT(a.id) FILTER (WHERE a.status = 'ACTIVE') AS assigned_students
            FROM transport_routes r
            LEFT JOIN transport_assignments a ON a.route_id = r.id
            WHERE r.org_id = %s AND r.is_active = TRUE
            GROUP BY r.id
            ORDER BY r.route_name
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]

    # ── Assignments ──────────────────────────────────────────

    @classmethod
    def assign_student(cls, org_id: str, req: TransportAssignCreate, actor_id: str) -> dict:
        # Unique per student per year
        existing = execute_query(
            "SELECT id FROM transport_assignments WHERE student_id = %s AND academic_year = %s AND org_id = %s AND status = 'ACTIVE'",
            (req.student_id, req.academic_year, org_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message="Student already has an active transport assignment this year"
            )

        # Capacity check
        route = cls.get_route(org_id, req.route_id)
        assigned = execute_query(
            "SELECT COUNT(*) AS cnt FROM transport_assignments WHERE route_id = %s AND status = 'ACTIVE' AND org_id = %s",
            (req.route_id, org_id),
        )
        if int(assigned[0]["cnt"] or 0) >= int(route["capacity"]):
            raise BusinessRuleViolation(
                message=f"Route {route['route_name']} is at full capacity ({route['capacity']})"
            )

        # Generate pass number
        student_rows = execute_query(
            "SELECT roll_number FROM students WHERE id = %s", (req.student_id,)
        )
        roll = student_rows[0]["roll_number"] if student_rows else req.student_id[:8]
        pass_number = f"TP-{route['route_code']}-{roll}-{req.academic_year.replace('-','')}"

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO transport_assignments
                (id, org_id, student_id, route_id, stop_name, academic_year,
                 pass_number, valid_from, valid_to, assigned_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (aid, org_id, req.student_id, req.route_id, req.stop_name,
             req.academic_year, pass_number, req.valid_from,
             req.valid_to, actor_id),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="transport_assignment", entity_id=aid, org_id=org_id,
                     module="E09-S03",
                     metadata={"student_id": req.student_id, "route": route["route_name"]})

        return cls.get_assignment(org_id, aid)

    @classmethod
    def cancel_assignment(cls, org_id: str, assignment_id: str, actor_id: str) -> dict:
        execute_transaction([(
            "UPDATE transport_assignments SET status = 'CANCELLED' WHERE id = %s AND org_id = %s",
            (assignment_id, org_id),
        )])
        return cls.get_assignment(org_id, assignment_id)

    @classmethod
    def get_assignment(cls, org_id: str, assignment_id: str) -> dict:
        rows = execute_query(
            """
            SELECT a.*, s.name AS student_name, s.roll_number,
                   r.route_name, r.route_code, r.vehicle_number
            FROM transport_assignments a
            JOIN students s ON s.id = a.student_id
            JOIN transport_routes r ON r.id = a.route_id
            WHERE a.id = %s AND a.org_id = %s
            """,
            (assignment_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Assignment {assignment_id} not found")
        return dict(rows[0])

    @classmethod
    def get_student_assignment(cls, org_id: str, student_id: str,
                                academic_year: str) -> dict | None:
        rows = execute_query(
            """
            SELECT a.*, r.route_name, r.route_code, r.stops, r.vehicle_number,
                   r.driver_name, r.driver_contact
            FROM transport_assignments a
            JOIN transport_routes r ON r.id = a.route_id
            WHERE a.student_id = %s AND a.academic_year = %s AND a.org_id = %s
              AND a.status = 'ACTIVE'
            """,
            (student_id, academic_year, org_id),
        )
        return dict(rows[0]) if rows else None

    @classmethod
    def list_route_students(cls, org_id: str, route_id: str,
                             academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT a.*, s.name AS student_name, s.roll_number, s.email
            FROM transport_assignments a
            JOIN students s ON s.id = a.student_id
            WHERE a.route_id = %s AND a.academic_year = %s AND a.org_id = %s
              AND a.status = 'ACTIVE'
            ORDER BY a.stop_name, s.name
            """,
            (route_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]
