"""
EC-ACA-03 — Mass Bunk Detection

Before sending individual parent alerts for low attendance, check if the
entire class has low attendance (mass bunk). If < THRESHOLD of the class
attended, halt individual alerts and escalate to HOD.

MASS_BUNK_THRESHOLD = 0.20 (configurable via policy engine)

If < 20% of enrolled students attended a session → MASS_BUNK detected:
1. Halt individual parent alerts for that session
2. Notify HOD for confirmation
3. HOD decides: legitimate (excused all) or escalate to Dean

EC-ACA-04 — Adjunct / Industry Faculty Scheduling
Ad-hoc scheduling zone for variable-availability adjunct faculty.
Week-by-week availability vs. fixed weekly slots.
"""

from __future__ import annotations

import logging
from typing import Any

from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class MassBunkDetector:
    """
    Checks attendance sessions for mass bunk before triggering parent alerts.
    """

    @classmethod
    def check_session(cls, org_id: str, session_id: str) -> dict[str, Any]:
        """
        Check if a session has a mass bunk (attendance < threshold).

        Returns:
            {is_mass_bunk: bool, attendance_rate: float, action: str}
        """
        threshold = float(
            policy_engine.get_value("academics.mass_bunk_threshold", org_id, 0.20)
        )

        # Get session attendance stats
        stats = execute_query(
            """
            SELECT
                COUNT(*) AS total_enrolled,
                COUNT(*) FILTER (WHERE status = 'PRESENT') AS present_count
            FROM attendance_records
            WHERE session_id = %s AND org_id = %s
            """,
            (session_id, org_id),
            tenant_id=org_id,
        )

        if not stats or stats[0]["total_enrolled"] == 0:
            return {"is_mass_bunk": False, "attendance_rate": 0, "action": "no_data"}

        total = stats[0]["total_enrolled"]
        present = stats[0]["present_count"]
        rate = present / total

        if rate < threshold:
            # Mass bunk detected — halt individual alerts, notify HOD
            logger.warning(
                "EC-ACA-03: Mass bunk detected for session=%s (rate=%.1f%%, threshold=%.0f%%)",
                session_id,
                rate * 100,
                threshold * 100,
            )

            # Flag the session
            execute_transaction(
                [
                    (
                        "UPDATE attendance_sessions SET mass_bunk_flagged = TRUE, "
                        "mass_bunk_rate = %s WHERE id = %s AND org_id = %s",
                        (rate, session_id, org_id),
                    )
                ],
                tenant_id=org_id,
            )

            # Notify HOD
            DomainEventBus.publish(
                DomainEvent(
                    event_type="academics.mass_bunk_detected",
                    org_id=org_id,
                    payload={
                        "session_id": session_id,
                        "attendance_rate": round(rate * 100, 1),
                        "threshold": threshold * 100,
                        "total_enrolled": total,
                        "present": present,
                    },
                )
            )

            return {
                "is_mass_bunk": True,
                "attendance_rate": round(rate * 100, 1),
                "total_enrolled": total,
                "present": present,
                "action": "halt_parent_alerts_notify_hod",
            }

        return {
            "is_mass_bunk": False,
            "attendance_rate": round(rate * 100, 1),
            "action": "proceed_with_alerts",
        }

    @classmethod
    def hod_resolve(
        cls, org_id: str, session_id: str, decision: str, actor_id: str
    ) -> dict[str, Any]:
        """
        HOD resolves a mass bunk flag.
        decision: 'EXCUSE_ALL' | 'ESCALATE_DEAN' | 'CONFIRM_BUNK'
        """
        if decision == "EXCUSE_ALL":
            execute_transaction(
                [
                    (
                        "UPDATE attendance_records SET status = 'EXCUSED_DISRUPTION' "
                        "WHERE session_id = %s AND org_id = %s AND status = 'ABSENT'",
                        (session_id, org_id),
                    ),
                    (
                        "UPDATE attendance_sessions SET mass_bunk_resolved = %s, "
                        "mass_bunk_resolved_by = %s WHERE id = %s AND org_id = %s",
                        (decision, actor_id, session_id, org_id),
                    ),
                ],
                tenant_id=org_id,
            )
        else:
            execute_transaction(
                [
                    (
                        "UPDATE attendance_sessions SET mass_bunk_resolved = %s, "
                        "mass_bunk_resolved_by = %s WHERE id = %s AND org_id = %s",
                        (decision, actor_id, session_id, org_id),
                    ),
                ],
                tenant_id=org_id,
            )

        return {"session_id": session_id, "decision": decision}


class AdjunctSchedulingService:
    """
    EC-ACA-04 — Ad-hoc scheduling zone for adjunct/industry faculty.

    Unlike regular faculty who have fixed weekly slot patterns,
    adjunct faculty declare week-by-week availability.
    The timetable engine reserves ad-hoc zones that bypass
    weekly pattern constraints.
    """

    @classmethod
    def submit_availability(
        cls,
        org_id: str,
        faculty_id: str,
        week_start: str,
        slots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Adjunct faculty submits weekly availability.

        slots: [{day: "MON", start_time: "09:00", end_time: "11:00"}, ...]
        """
        import json
        from uuid import uuid4

        avail_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO adjunct_availability
                    (id, org_id, faculty_id, week_start, slots, status, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, 'SUBMITTED', NOW())
                ON CONFLICT (org_id, faculty_id, week_start) DO UPDATE SET
                    slots = EXCLUDED.slots, status = 'SUBMITTED'
                """,
                    (avail_id, org_id, faculty_id, week_start, json.dumps(slots)),
                )
            ],
            tenant_id=org_id,
        )

        return {"id": avail_id, "week_start": week_start, "slot_count": len(slots)}

    @classmethod
    def get_availability(
        cls, org_id: str, faculty_id: str, week_start: str
    ) -> list[dict[str, Any]]:
        rows = execute_query(
            "SELECT slots FROM adjunct_availability "
            "WHERE org_id = %s AND faculty_id = %s AND week_start = %s",
            (org_id, faculty_id, week_start),
            tenant_id=org_id,
        )
        if rows and rows[0].get("slots"):
            import json

            slots = rows[0]["slots"]
            return json.loads(slots) if isinstance(slots, str) else slots
        return []

    @classmethod
    def allocate_adhoc_slots(
        cls,
        org_id: str,
        faculty_id: str,
        course_id: str,
        week_start: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Allocate timetable slots from adjunct availability (bypasses weekly pattern)."""
        slots = cls.get_availability(org_id, faculty_id, week_start)
        if not slots:
            raise ValueError(f"No availability submitted for week {week_start}")

        from uuid import uuid4

        allocated = []
        for slot in slots:
            slot_id = str(uuid4())
            execute_transaction(
                [
                    (
                        """
                    INSERT INTO timetable_slots
                        (id, org_id, course_id, faculty_id, day_of_week, start_time,
                         end_time, slot_type, week_start, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ADHOC', %s, NOW())
                    """,
                        (
                            slot_id,
                            org_id,
                            course_id,
                            faculty_id,
                            slot["day"],
                            slot["start_time"],
                            slot["end_time"],
                            week_start,
                        ),
                    )
                ],
                tenant_id=org_id,
            )
            allocated.append(slot_id)

        return {"allocated_slots": len(allocated), "week_start": week_start}
