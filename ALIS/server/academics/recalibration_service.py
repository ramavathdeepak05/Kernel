"""EC-ACA-01 — Global Campus Recalibration Trigger

Handles institution-wide or scoped disruptions (floods, strikes, power outages)
that require attendance sessions to be marked EXCUSED_DISRUPTION and deadlines
to shift forward.

Scope: INSTITUTION_WIDE | DEPARTMENT | PROGRAM | SECTION
Pre-locked exam dates are immovable — only non-exam deadlines shift.

All thresholds from policy_engine (R1). State transitions via state machine (R6).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class RecalibrationScope(str, Enum):
    INSTITUTION_WIDE = "INSTITUTION_WIDE"
    DEPARTMENT = "DEPARTMENT"
    PROGRAM = "PROGRAM"
    SECTION = "SECTION"


class RecalibrationRequest(BaseModel):
    scope: RecalibrationScope
    scope_ref: Optional[str] = None   # department_id / program_id / section_id
    reason: str
    disruption_days: int              # number of days to shift deadlines
    disruption_start: str             # ISO date — first disrupted day
    disruption_end: str               # ISO date — last disrupted day


class RecalibrationService:

    @classmethod
    async def trigger(
        cls,
        org_id: str,
        request: RecalibrationRequest,
        actor_id: str,
    ) -> dict:
        """Trigger global or scoped recalibration.

        1. Identify affected sessions (within disruption window, matching scope).
        2. Mark sessions EXCUSED_DISRUPTION.
        3. Shift non-exam deadlines forward by disruption_days.
        4. Return preview counts to Registrar.
        5. Write to course_recalibration_log and emit domain event.
        """
        if request.disruption_days < 1:
            raise BusinessRuleViolation("disruption_days must be at least 1")

        # ---------------------------------------------------------------
        # 1. Find affected sessions
        # ---------------------------------------------------------------
        scope_clause = cls._scope_clause(request)

        affected_sessions_rows = execute_query(f"""
            SELECT s.id, s.course_id, s.session_date
            FROM attendance_sessions s
            WHERE s.org_id = %s
              AND s.session_date BETWEEN %s AND %s
              AND s.status NOT IN ('EXCUSED_DISRUPTION', 'EXAM')
              {scope_clause}
        """, (org_id, request.disruption_start, request.disruption_end))

        affected_session_ids = [str(r["id"]) for r in affected_sessions_rows]

        # ---------------------------------------------------------------
        # 2. Find shiftable deadlines (non-exam)
        # ---------------------------------------------------------------
        shiftable_deadlines_rows = execute_query(f"""
            SELECT d.id, d.title, d.due_date
            FROM course_deadlines d
            WHERE d.org_id = %s
              AND d.due_date >= %s
              AND d.is_exam_date = FALSE
              {scope_clause.replace('s.', 'd.')}
        """, (org_id, request.disruption_start))

        # Exam deadlines that are immovable
        locked_exam_rows = execute_query(f"""
            SELECT d.id, d.title, d.due_date
            FROM course_deadlines d
            WHERE d.org_id = %s
              AND d.due_date >= %s
              AND d.is_exam_date = TRUE
              {scope_clause.replace('s.', 'd.')}
        """, (org_id, request.disruption_start))

        # ---------------------------------------------------------------
        # 3 & 4. Apply changes (in a single transaction)
        # ---------------------------------------------------------------
        log_id = str(uuid.uuid4())
        ops = []

        # Mark sessions EXCUSED_DISRUPTION
        if affected_session_ids:
            placeholders = ", ".join(["%s"] * len(affected_session_ids))
            ops.append((f"""
                UPDATE attendance_sessions
                SET status = 'EXCUSED_DISRUPTION', updated_at = NOW()
                WHERE id IN ({placeholders}) AND org_id = %s
            """, (*affected_session_ids, org_id)))

            # Also mark individual attendance records as EXCUSED_DISRUPTION
            ops.append((f"""
                UPDATE attendance_records
                SET status = 'EXCUSED_DISRUPTION'
                WHERE session_id IN ({placeholders}) AND org_id = %s
            """, (*affected_session_ids, org_id)))

        # Shift deadlines
        if shiftable_deadlines_rows:
            deadline_ids = [str(r["id"]) for r in shiftable_deadlines_rows]
            placeholders_d = ", ".join(["%s"] * len(deadline_ids))
            ops.append((f"""
                UPDATE course_deadlines
                SET due_date = due_date + INTERVAL '%s days', updated_at = NOW()
                WHERE id IN ({placeholders_d}) AND org_id = %s
            """, (request.disruption_days, *deadline_ids, org_id)))

        # Write log
        ops.append(("""
            INSERT INTO course_recalibration_log
                (id, org_id, scope, affected_sessions, actor_id, triggered_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (
            log_id, org_id, request.scope.value,
            len(affected_session_ids), actor_id,
        )))

        if ops:
            execute_transaction(ops)

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="recalibration",
            resource_id=log_id,
            detail={
                "scope": request.scope.value,
                "disruption_days": request.disruption_days,
                "affected_sessions": len(affected_session_ids),
                "shifted_deadlines": len(shiftable_deadlines_rows),
                "locked_exam_dates": len(locked_exam_rows),
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="academics.recalibration_triggered",
            org_id=org_id,
            payload={
                "log_id": log_id,
                "scope": request.scope.value,
                "scope_ref": request.scope_ref,
                "disruption_days": request.disruption_days,
                "affected_sessions": len(affected_session_ids),
            },
        ))

        return {
            "log_id": log_id,
            "affected_sessions": len(affected_session_ids),
            "shifted_deadlines": len(shiftable_deadlines_rows),
            "locked_exam_dates_not_shifted": len(locked_exam_rows),
            "locked_exam_dates": [
                {"title": r["title"], "due_date": str(r["due_date"])}
                for r in locked_exam_rows
            ],
            "preview_message": (
                f"This shifts {len(affected_session_ids)} sessions, "
                f"{len(shiftable_deadlines_rows)} deadlines. "
                f"{len(locked_exam_rows)} exam date(s) are pre-locked and will not shift."
            ),
        }

    @classmethod
    def _scope_clause(cls, request: RecalibrationRequest) -> str:
        """Build scope-specific WHERE clause fragment."""
        if request.scope == RecalibrationScope.INSTITUTION_WIDE:
            return ""
        if request.scope == RecalibrationScope.DEPARTMENT and request.scope_ref:
            return f"AND s.department_id = '{request.scope_ref}'"
        if request.scope == RecalibrationScope.PROGRAM and request.scope_ref:
            return f"AND s.program_id = '{request.scope_ref}'"
        if request.scope == RecalibrationScope.SECTION and request.scope_ref:
            return f"AND s.section_id = '{request.scope_ref}'"
        return ""
