"""E09-S01 — Hostel Management"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import HostelAllocationCreate, HostelBlockCreate, HostelComplaintCreate, HostelRoomCreate

logger = logging.getLogger(__name__)


class HostelService:

    # ── Blocks ──────────────────────────────────────────────

    @classmethod
    def create_block(cls, org_id: str, req: HostelBlockCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM hostel_blocks WHERE org_id = %s AND name = %s",
            (org_id, req.name),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Block '{req.name}' already exists")

        bid = str(uuid.uuid4())
        execute_transaction([(
            "INSERT INTO hostel_blocks (id, org_id, name, gender, total_rooms, warden_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (bid, org_id, req.name, req.gender, req.total_rooms, req.warden_id),
        )])
        return cls.get_block(org_id, bid)

    @classmethod
    def get_block(cls, org_id: str, block_id: str) -> dict:
        rows = execute_query(
            "SELECT b.*, u.display_name AS warden_name FROM hostel_blocks b LEFT JOIN users u ON u.id = b.warden_id WHERE b.id = %s AND b.org_id = %s",
            (block_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Block {block_id} not found")
        return dict(rows[0])

    @classmethod
    def list_blocks(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT b.*, u.display_name AS warden_name FROM hostel_blocks b LEFT JOIN users u ON u.id = b.warden_id WHERE b.org_id = %s AND b.is_active = TRUE ORDER BY b.name",
            (org_id,),
        )
        return [dict(r) for r in rows]

    # ── Rooms ───────────────────────────────────────────────

    @classmethod
    def create_room(cls, org_id: str, req: HostelRoomCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM hostel_rooms WHERE org_id = %s AND block_id = %s AND room_number = %s",
            (org_id, req.block_id, req.room_number),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Room {req.room_number} already exists in block")

        rid = str(uuid.uuid4())
        execute_transaction([(
            "INSERT INTO hostel_rooms (id, org_id, block_id, room_number, room_type, capacity, floor, amenities) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (rid, org_id, req.block_id, req.room_number, req.room_type.value,
             req.capacity, req.floor, req.amenities),
        )])
        rows = execute_query("SELECT * FROM hostel_rooms WHERE id = %s", (rid,))
        return dict(rows[0])

    @classmethod
    def list_rooms(cls, org_id: str, block_id: str,
                    available_only: bool = False) -> list[dict]:
        sql = """
            SELECT r.*,
                   COUNT(a.id) FILTER (WHERE a.status = 'ACTIVE') AS occupied
            FROM hostel_rooms r
            LEFT JOIN hostel_allocations a ON a.room_id = r.id AND a.status = 'ACTIVE'
            WHERE r.org_id = %s AND r.block_id = %s AND r.is_active = TRUE
            GROUP BY r.id
        """
        params: list = [org_id, block_id]
        if available_only:
            sql += " HAVING COUNT(a.id) FILTER (WHERE a.status = 'ACTIVE') < r.capacity"
        sql += " ORDER BY r.floor, r.room_number"
        return [dict(r) for r in execute_query(sql, params)]

    # ── Allocations ─────────────────────────────────────────

    @classmethod
    def allocate(cls, org_id: str, req: HostelAllocationCreate, actor_id: str) -> dict:
        # Check student already allocated this year
        existing = execute_query(
            "SELECT id FROM hostel_allocations WHERE student_id = %s AND academic_year = %s AND org_id = %s AND status = 'ACTIVE'",
            (req.student_id, req.academic_year, org_id),
        )
        if existing:
            raise BusinessRuleViolation(message="Student already has an active hostel allocation this year")

        # Check room capacity
        room_rows = execute_query(
            "SELECT r.capacity, COUNT(a.id) AS occupied FROM hostel_rooms r LEFT JOIN hostel_allocations a ON a.room_id = r.id AND a.status = 'ACTIVE' WHERE r.id = %s AND r.org_id = %s GROUP BY r.capacity",
            (req.room_id, org_id),
        )
        if not room_rows:
            raise NotFoundError(f"Room {req.room_id} not found")
        room = dict(room_rows[0])
        if int(room["occupied"] or 0) >= int(room["capacity"]):
            raise BusinessRuleViolation(message="Room is at full capacity")

        aid = str(uuid.uuid4())
        execute_transaction([(
            "INSERT INTO hostel_allocations (id, org_id, student_id, room_id, academic_year, check_in_date, allocated_by, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (aid, org_id, req.student_id, req.room_id, req.academic_year,
             req.check_in_date, actor_id, req.notes),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="hostel_allocation", entity_id=aid, org_id=org_id,
                     module="E09-S01",
                     metadata={"student_id": req.student_id, "room_id": req.room_id})

        return cls.get_allocation(org_id, aid)

    @classmethod
    def vacate(cls, org_id: str, allocation_id: str,
                checkout_date: str, actor_id: str) -> dict:
        execute_transaction([(
            "UPDATE hostel_allocations SET status = 'VACATED', check_out_date = %s WHERE id = %s AND org_id = %s",
            (checkout_date, allocation_id, org_id),
        )])
        return cls.get_allocation(org_id, allocation_id)

    @classmethod
    def get_allocation(cls, org_id: str, allocation_id: str) -> dict:
        rows = execute_query(
            """
            SELECT a.*, s.name AS student_name, s.roll_number,
                   r.room_number, b.name AS block_name
            FROM hostel_allocations a
            JOIN students s ON s.id = a.student_id
            JOIN hostel_rooms r ON r.id = a.room_id
            JOIN hostel_blocks b ON b.id = r.block_id
            WHERE a.id = %s AND a.org_id = %s
            """,
            (allocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Allocation {allocation_id} not found")
        return dict(rows[0])

    @classmethod
    def get_student_allocation(cls, org_id: str, student_id: str,
                                academic_year: str) -> dict | None:
        rows = execute_query(
            """
            SELECT a.*, r.room_number, b.name AS block_name
            FROM hostel_allocations a
            JOIN hostel_rooms r ON r.id = a.room_id
            JOIN hostel_blocks b ON b.id = r.block_id
            WHERE a.student_id = %s AND a.academic_year = %s AND a.org_id = %s
            """,
            (student_id, academic_year, org_id),
        )
        return dict(rows[0]) if rows else None

    # ── Complaints ──────────────────────────────────────────

    @classmethod
    def file_complaint(cls, org_id: str, student_id: str,
                        req: HostelComplaintCreate, actor_id: str) -> dict:
        cid = str(uuid.uuid4())
        execute_transaction([(
            "INSERT INTO hostel_complaints (id, org_id, student_id, room_id, category, description, priority) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cid, org_id, student_id, req.room_id, req.category,
             req.description, req.priority.value),
        )])
        rows = execute_query("SELECT * FROM hostel_complaints WHERE id = %s", (cid,))
        return dict(rows[0])

    @classmethod
    def update_complaint(cls, org_id: str, complaint_id: str,
                          status: str, resolution_note: str | None,
                          actor_id: str) -> dict:
        execute_transaction([(
            """
            UPDATE hostel_complaints
            SET status = %s, assigned_to = %s, resolution_note = %s,
                resolved_at = CASE WHEN %s IN ('RESOLVED','CLOSED') THEN NOW() ELSE resolved_at END
            WHERE id = %s AND org_id = %s
            """,
            (status, actor_id, resolution_note, status, complaint_id, org_id),
        )])
        rows = execute_query("SELECT * FROM hostel_complaints WHERE id = %s", (complaint_id,))
        return dict(rows[0]) if rows else {}

    @classmethod
    def list_complaints(cls, org_id: str, status: str | None = None) -> list[dict]:
        sql = "SELECT c.*, s.name AS student_name FROM hostel_complaints c JOIN students s ON s.id = c.student_id WHERE c.org_id = %s"
        params: list = [org_id]
        if status:
            sql += " AND c.status = %s"
            params.append(status)
        sql += " ORDER BY c.created_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def occupancy_summary(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                b.name AS block_name, b.gender,
                COUNT(r.id) AS total_rooms,
                SUM(r.capacity) AS total_capacity,
                COUNT(a.id) FILTER (WHERE a.status = 'ACTIVE') AS occupied
            FROM hostel_blocks b
            JOIN hostel_rooms r ON r.block_id = b.id
            LEFT JOIN hostel_allocations a ON a.room_id = r.id
            WHERE b.org_id = %s AND b.is_active = TRUE
            GROUP BY b.id, b.name, b.gender
            ORDER BY b.name
            """,
            (org_id,),
        )
        result = []
        for r in rows:
            row = dict(r)
            cap = int(row.get("total_capacity") or 0)
            occ = int(row.get("occupied") or 0)
            row["occupancy_pct"] = round((occ / cap * 100), 1) if cap > 0 else 0.0
            row["available"]     = cap - occ
            result.append(row)
        return result
