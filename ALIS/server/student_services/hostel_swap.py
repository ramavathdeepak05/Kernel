"""EC-SS-04 — Hostel Room Swap at 100% Capacity

Swap request flow when hostel is full:
  student → swap request → system finds compatible match → Warden approves

SAFETY severity (altercation/harassment):
  Warden bypasses exchange → temp overflow → Dean notified immediately.
  Overflow SLA: from policy_engine (R1 — never hardcoded 72h).
  Deadline stored as absolute TIMESTAMPTZ (R3).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class SwapSeverity(str, Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    SAFETY = "SAFETY"


class SwapRequestCreate(BaseModel):
    student_id: str
    current_room_id: str
    preferred_room_type: Optional[str] = None  # e.g. "SINGLE", "DOUBLE"
    reason: str
    severity: SwapSeverity = SwapSeverity.ROUTINE


class HostelSwapService:

    # ------------------------------------------------------------------
    # Create swap request
    # ------------------------------------------------------------------

    @classmethod
    async def create_swap_request(
        cls,
        org_id: str,
        request: SwapRequestCreate,
        actor_id: str,
    ) -> dict:
        """Create a swap request. SAFETY severity bypasses matching and places in overflow."""
        request_id = str(uuid.uuid4())

        if request.severity == SwapSeverity.SAFETY:
            return await cls._handle_safety_case(
                org_id=org_id,
                request_id=request_id,
                student_id=request.student_id,
                current_room_id=request.current_room_id,
                reason=request.reason,
                actor_id=actor_id,
            )

        # Standard swap: find a compatible match
        execute_transaction([("""
            INSERT INTO hostel_swap_requests
                (id, org_id, student_id, current_room_id,
                 preferred_room_type, reason, severity, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING_MATCH', NOW())
        """, (
            request_id, org_id,
            request.student_id, request.current_room_id,
            request.preferred_room_type, request.reason,
            request.severity.value,
        ))])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.CREATED,
            resource_type="hostel_swap_request",
            resource_id=request_id,
            detail={"severity": request.severity.value, "reason": request.reason},
        )

        # Try to find a match immediately
        match = await cls._find_match(org_id, request_id, request)

        DomainEventBus.publish(DomainEvent(
            event_type="student_services.hostel_swap_requested",
            org_id=org_id,
            payload={
                "request_id": request_id,
                "student_id": request.student_id,
                "severity": request.severity.value,
                "match_found": match is not None,
            },
        ))

        return {
            "request_id": request_id,
            "status": "MATCH_FOUND" if match else "PENDING_MATCH",
            "match": match,
        }

    # ------------------------------------------------------------------
    # Find compatible match
    # ------------------------------------------------------------------

    @classmethod
    async def find_match(
        cls,
        org_id: str,
        request_id: str,
        actor_id: str,
    ) -> dict:
        """Manually trigger match-finding for a PENDING_MATCH request."""
        rows = execute_query(
            "SELECT * FROM hostel_swap_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Swap request {request_id} not found")

        req = rows[0]
        request = SwapRequestCreate(
            student_id=str(req["student_id"]),
            current_room_id=str(req["current_room_id"]),
            preferred_room_type=req.get("preferred_room_type"),
            reason=str(req.get("reason", "")),
            severity=SwapSeverity(req.get("severity", "ROUTINE")),
        )
        match = await cls._find_match(org_id, request_id, request)
        return {"request_id": request_id, "match": match}

    # ------------------------------------------------------------------
    # Approve swap
    # ------------------------------------------------------------------

    @classmethod
    async def approve_swap(
        cls,
        org_id: str,
        request_id: str,
        actor_id: str,
    ) -> dict:
        """Warden approves the swap — executes room reassignment."""
        rows = execute_query(
            "SELECT * FROM hostel_swap_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Swap request {request_id} not found")

        req = rows[0]
        if req["status"] not in ("MATCH_FOUND", "PENDING_MATCH"):
            raise BusinessRuleViolation(
                f"Cannot approve swap in status {req['status']}"
            )

        matched_request_id = req.get("matched_request_id")
        student_a = str(req["student_id"])
        room_a = str(req["current_room_id"])

        ops = [("""
            UPDATE hostel_swap_requests
            SET status = 'APPROVED', approved_by = %s, approved_at = NOW()
            WHERE id = %s AND org_id = %s
        """, (actor_id, request_id, org_id))]

        if matched_request_id:
            matched_rows = execute_query(
                "SELECT student_id, current_room_id FROM hostel_swap_requests WHERE id = %s",
                (matched_request_id,),
            )
            if matched_rows:
                student_b = str(matched_rows[0]["student_id"])
                room_b = str(matched_rows[0]["current_room_id"])

                # Execute the room swap
                ops.extend([
                    ("""
                    UPDATE hostel_room_assignments
                    SET room_id = %s, updated_at = NOW()
                    WHERE student_id = %s AND org_id = %s AND status = 'ACTIVE'
                    """, (room_b, student_a, org_id)),
                    ("""
                    UPDATE hostel_room_assignments
                    SET room_id = %s, updated_at = NOW()
                    WHERE student_id = %s AND org_id = %s AND status = 'ACTIVE'
                    """, (room_a, student_b, org_id)),
                    ("""
                    UPDATE hostel_swap_requests
                    SET status = 'APPROVED', approved_by = %s, approved_at = NOW()
                    WHERE id = %s AND org_id = %s
                    """, (actor_id, matched_request_id, org_id)),
                ])

        execute_transaction(ops)

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="hostel_swap_request",
            resource_id=request_id,
            detail={"status": "APPROVED"},
        )

        DomainEventBus.publish(DomainEvent(
            event_type="student_services.hostel_swap_approved",
            org_id=org_id,
            payload={"request_id": request_id, "approved_by": actor_id},
        ))

        return {"request_id": request_id, "status": "APPROVED"}

    # ------------------------------------------------------------------
    # SAFETY: immediate overflow placement
    # ------------------------------------------------------------------

    @classmethod
    async def _handle_safety_case(
        cls,
        org_id: str,
        request_id: str,
        student_id: str,
        current_room_id: str,
        reason: str,
        actor_id: str,
    ) -> dict:
        """SAFETY severity: bypass exchange, place in temp overflow immediately."""
        # R1 — never hardcode 72h
        overflow_hours = int(policy_engine.get_value(
            "hostel.safety_overflow_max_hours", org_id, 72
        ))
        # R3 — absolute TIMESTAMPTZ deadline
        overflow_deadline = datetime.now(timezone.utc) + timedelta(hours=overflow_hours)

        execute_transaction([("""
            INSERT INTO hostel_swap_requests
                (id, org_id, student_id, current_room_id, reason, severity,
                 status, overflow_deadline, created_at)
            VALUES (%s, %s, %s, %s, %s, 'SAFETY', 'OVERFLOW_PLACED', %s, NOW())
        """, (
            request_id, org_id, student_id, current_room_id, reason, overflow_deadline,
        ))])

        # Emit SAFETY domain event — Dean notified immediately
        DomainEventBus.publish(DomainEvent(
            event_type="student_services.hostel_safety_overflow",
            org_id=org_id,
            payload={
                "request_id": request_id,
                "student_id": student_id,
                "reason": reason,
                "overflow_deadline": overflow_deadline.isoformat(),
                "template_key": "HOSTEL_SAFETY_DEAN_ALERT",
            },
        ))

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.CREATED,
            resource_type="hostel_safety_overflow",
            resource_id=request_id,
            detail={
                "student_id": student_id,
                "overflow_deadline": overflow_deadline.isoformat(),
                "reason": reason,
            },
        )

        logger.warning(
            "SAFETY hostel overflow: student=%s org=%s deadline=%s",
            student_id, org_id, overflow_deadline.isoformat(),
        )

        return {
            "request_id": request_id,
            "status": "OVERFLOW_PLACED",
            "severity": "SAFETY",
            "overflow_deadline": overflow_deadline.isoformat(),
            "message": f"Student placed in temporary overflow. Dean notified. Resolve by {overflow_deadline.isoformat()}.",
        }

    # ------------------------------------------------------------------
    # Internal match-finding
    # ------------------------------------------------------------------

    @classmethod
    async def _find_match(
        cls,
        org_id: str,
        request_id: str,
        request: SwapRequestCreate,
    ) -> Optional[dict]:
        """Find another student willing to swap into the current room."""
        # Find other PENDING_MATCH requests wanting the room type of this student's room
        room_info = execute_query(
            "SELECT room_type FROM hostel_rooms WHERE id = %s AND org_id = %s",
            (request.current_room_id, org_id),
        )
        if not room_info:
            return None

        current_room_type = room_info[0].get("room_type")

        # Find a compatible counter-request
        matches = execute_query("""
            SELECT sr.id, sr.student_id, sr.current_room_id
            FROM hostel_swap_requests sr
            JOIN hostel_rooms r ON r.id = sr.current_room_id
            WHERE sr.org_id = %s
              AND sr.id != %s
              AND sr.status = 'PENDING_MATCH'
              AND sr.severity != 'SAFETY'
              AND (sr.preferred_room_type IS NULL OR sr.preferred_room_type = %s)
            ORDER BY sr.created_at ASC
            LIMIT 1
        """, (org_id, request_id, current_room_type))

        if not matches:
            return None

        match = matches[0]
        matched_id = str(match["id"])

        # Link the two requests
        execute_transaction([
            ("""
            UPDATE hostel_swap_requests
            SET status = 'MATCH_FOUND', matched_request_id = %s, updated_at = NOW()
            WHERE id = %s AND org_id = %s
            """, (matched_id, request_id, org_id)),
            ("""
            UPDATE hostel_swap_requests
            SET status = 'MATCH_FOUND', matched_request_id = %s, updated_at = NOW()
            WHERE id = %s AND org_id = %s
            """, (request_id, matched_id, org_id)),
        ])

        return {
            "matched_request_id": matched_id,
            "matched_student_id": str(match["student_id"]),
            "matched_room_id": str(match["current_room_id"]),
        }
