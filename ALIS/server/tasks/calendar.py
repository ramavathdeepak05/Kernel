"""
Academic Calendar Celery Tasks — P0-S19

Celery Beat daemon that checks academic calendar phase boundaries
daily and fires the appropriate domain events.

Domain events fired:
    SemesterStarted      → when CLASSES phase begins
    AttendanceFinalized  → when ATTENDANCE_LOCK phase begins
    SemesterEnded        → when SEMESTER_BREAK phase begins
    ExamRegistrationOpen → when EXAM_REGISTRATION phase begins
    ExamPeriodStarted    → when EXAM_PERIOD phase begins
    ResultWindowOpen     → when RESULTS phase begins
"""

import logging
from datetime import date, datetime, timezone

from server.worker import celery_app
from server.db_service import execute_query, execute_transaction
from server.core.domain_events import DomainEvent, DomainEventBus

logger = logging.getLogger(__name__)

# Map phase name → domain event type
_PHASE_EVENTS = {
    "CLASSES":            "SemesterStarted",
    "ATTENDANCE_LOCK":    "AttendanceFinalized",
    "EXAM_REGISTRATION":  "ExamRegistrationOpen",
    "EXAM_PERIOD":        "ExamPeriodStarted",
    "RESULTS":            "ResultWindowOpen",
    "SEMESTER_BREAK":     "SemesterEnded",
}


@celery_app.task(
    name="server.tasks.calendar.check_calendar_phases",
    ignore_result=True,
)
def check_calendar_phases() -> None:
    """
    Runs daily at midnight (Celery Beat).
    For each academic calendar, checks if today crosses a phase boundary
    and fires the corresponding domain event if not already fired.
    """
    today = date.today()

    calendars = execute_query(
        "SELECT * FROM academic_calendars WHERE is_active = TRUE",
        (),
    )

    for cal in calendars:
        phases = execute_query(
            "SELECT * FROM calendar_phases WHERE calendar_id = %s ORDER BY start_date ASC",
            (cal["id"],),
        )
        for phase in phases:
            phase_start = phase["start_date"]
            if isinstance(phase_start, datetime):
                phase_start = phase_start.date()

            # Fire event on the first day of the phase
            if phase_start != today:
                continue

            event_type = _PHASE_EVENTS.get(phase["phase_name"])
            if not event_type:
                continue

            # Idempotency: skip if already fired for this phase
            already_fired = execute_query(
                """
                SELECT id FROM domain_events
                WHERE event_type = %s AND org_id = %s
                  AND payload->>'calendar_id' = %s
                  AND payload->>'phase_name' = %s
                LIMIT 1
                """,
                (event_type, cal["org_id"], str(cal["id"]), phase["phase_name"]),
            )
            if already_fired:
                continue

            DomainEventBus.publish(DomainEvent(
                event_type=event_type,
                entity_type="academic_calendar",
                entity_id=str(cal["id"]),
                org_id=cal["org_id"],
                payload={
                    "calendar_id": str(cal["id"]),
                    "calendar_name": cal["name"],
                    "phase_name": phase["phase_name"],
                    "academic_year": cal["academic_year"],
                    "phase_start": str(phase_start),
                    "phase_end": str(phase["end_date"]),
                },
                actor_id="system:calendar_daemon",
            ))

            logger.info(
                "CalendarDaemon: fired %s [calendar=%s, phase=%s, org=%s]",
                event_type, cal["id"], phase["phase_name"], cal["org_id"],
            )
