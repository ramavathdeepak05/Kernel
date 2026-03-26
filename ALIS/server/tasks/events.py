"""
Domain Event Celery Tasks — P0-S17/S18

Celery tasks that dispatch domain events to registered handlers,
and retry failed events from the DB.
"""
from __future__ import annotations

import logging
from typing import List

from server.worker import celery_app
from server.db_service import execute_query, execute_system_query, execute_system_transaction

logger = logging.getLogger(__name__)


@celery_app.task(
    name="server.tasks.events.dispatch_domain_event",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def dispatch_domain_event(self, event_id: str) -> None:
    """
    Celery task: load a domain event from DB and run all registered handlers.
    Retries up to 3× on failure with 60s delay.

    Stamps processing_started_at before calling the bus so that the
    retry_stuck_events Beat task can detect worker crashes:
        status=PROCESSING + processing_started_at > 2 min ago → stuck.
    """
    # Mark the event as in-flight so stuck-event detection can find it
    # if this worker crashes before DomainEventBus marks it PROCESSED.
    execute_system_transaction([
        (
            "UPDATE domain_events "
            "SET status = 'PROCESSING', processing_started_at = NOW() "
            "WHERE id = %s AND status IN ('PENDING', 'PROCESSING')",
            (event_id,),
        )
    ])
    try:
        from server.core.domain_events import DomainEventBus
        DomainEventBus._dispatch_sync(event_id)
    except Exception as exc:
        logger.error("dispatch_domain_event failed for %s: %s", event_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="server.tasks.events.retry_failed_events",
    ignore_result=True,
)
def retry_failed_events() -> None:
    """
    Beat task: pick up PENDING events that Celery missed (e.g. worker was down).
    Runs every 5 minutes via Celery Beat.
    """
    rows = execute_system_query(
        """
        SELECT id FROM domain_events
        WHERE status = 'PENDING' AND retry_count < 3
          AND published_at < NOW() - INTERVAL '2 minutes'
        ORDER BY published_at ASC
        LIMIT 50
        """,
        (),
    )
    for row in rows:
        dispatch_domain_event.delay(row["id"])
        logger.info("retry_failed_events: re-queued event %s", row["id"])


@celery_app.task(
    name="server.tasks.events.retry_stuck_events",
    ignore_result=True,
)
def retry_stuck_events(
    topics: List[str],
    stuck_after_seconds: int = 120,
) -> None:
    """
    Beat task: find PROCESSING events whose worker crashed before completing.

    Without processing_started_at we cannot distinguish 'actively processing'
    from 'stuck forever'.  This task resets any PROCESSING event that has been
    in that state for more than `stuck_after_seconds` back to PENDING, then
    re-queues it for immediate dispatch.

    Called every 30 seconds for FINANCE and EXAMINATION topics — these carry
    the highest inconsistency cost (payment → enrollment, grade → transcript).

    Args:
        topics: List of event_type topic prefixes to scope the search.
        stuck_after_seconds: Age threshold — events older than this are stuck.
    """
    rows = execute_system_query(
        """
        SELECT id, event_type FROM domain_events
        WHERE status = 'PROCESSING'
          AND event_type = ANY(%s)
          AND processing_started_at < NOW() - INTERVAL '1 second' * %s
        ORDER BY processing_started_at ASC
        LIMIT 20
        """,
        (topics, stuck_after_seconds),
    )
    if not rows:
        return

    stuck_ids = [row["id"] for row in rows]
    execute_system_transaction([
        (
            "UPDATE domain_events "
            "SET status = 'PENDING', processing_started_at = NULL "
            "WHERE id = ANY(%s)",
            (stuck_ids,),
        )
    ])
    for row in rows:
        dispatch_domain_event.delay(row["id"])
        logger.warning(
            "retry_stuck_events: reset stuck event %s (type=%s, stuck_threshold=%ds)",
            row["id"], row["event_type"], stuck_after_seconds,
        )



@celery_app.task(bind=True, max_retries=3)
def compile_aqar_draft(self):
    """Annual AQAR draft compilation task (Celery Beat — 1 July 06:00).

    For each active tenant that has regulatory.naac_evidence_collection enabled,
    triggers NIRF computation for the closing academic year and logs the event.

    Gated by feature flag so tenants that have not onboarded E14 are skipped.
    """
    from server.core.feature_flags import feature_flags

    logger.info("compile_aqar_draft: starting annual AQAR draft compilation")

    tenants = execute_system_query(
        "SELECT id, name FROM organizations WHERE status = 'ACTIVE'"
    )
    compiled = 0
    for tenant in tenants:
        org_id = str(tenant["id"])
        if not feature_flags.is_enabled("regulatory.naac_evidence_collection", org_id):
            continue
        try:
            from server.regulatory.nirf_service import NIRFService
            import datetime
            year = datetime.date.today().year
            NIRFService.compute_submission(org_id, submission_year=year)
            compiled += 1
            logger.info("compile_aqar_draft: NIRF draft computed for org %s (year=%d)", org_id, year)
        except Exception as exc:
            logger.error("compile_aqar_draft: failed for org %s: %s", org_id, exc)

    logger.info("compile_aqar_draft: completed — %d tenants processed", compiled)


# =============================================================================
# P26-TA — TA Assignment Notification Handlers
# =============================================================================

from server.core.domain_events import DomainEventBus as _DomainEventBus


async def _handle_ta_assigned(payload: dict) -> None:
    """Notify student they've been assigned as TA."""
    scope = payload.get("scope", "COURSE")
    course_name = payload.get("course_name", "")
    course_code = payload.get("course_code", "")
    faculty_name = payload.get("faculty_name", "Faculty")
    phone = payload.get("phone")

    if scope == "COURSE":
        message = (
            f"\U0001f4cb TA Assignment \u2014 {course_code}\n"
            f"Prof. {faculty_name} has assigned you as Teaching Assistant "
            f"for *{course_name}*.\n\n"
            f"You can now start attendance sessions for this course from the ALIS app."
        )
    else:
        message = (
            f"\U0001f4cb Session TA \u2014 {course_code}\n"
            f"Prof. {faculty_name} has assigned you as TA for an upcoming "
            f"attendance session in *{course_name}*."
        )

    logger.info(
        "ta_assigned_notify student=%s scope=%s course=%s",
        payload.get("student_id"), scope, course_code,
    )
    if phone:
        await _DomainEventBus.publish_async(
            "notification.sms_requested",
            {"phone": phone, "message": message, "student_id": payload.get("student_id")},
        )


_DomainEventBus.subscribe("attendance.ta_assigned", _handle_ta_assigned)


async def _handle_ta_revoked(payload: dict) -> None:
    """Notify student their TA assignment has been revoked."""
    course_code = payload.get("course_code", "")
    course_name = payload.get("course_name", "")
    phone = payload.get("phone")

    message = (
        f"\U0001f4cb TA Assignment Ended \u2014 {course_code}\n"
        f"Your Teaching Assistant assignment for *{course_name}* has been revoked. "
        f"Contact your faculty for more information."
    )

    logger.info(
        "ta_revoked_notify student=%s course=%s",
        payload.get("student_id"), course_code,
    )
    if phone:
        await _DomainEventBus.publish_async(
            "notification.sms_requested",
            {"phone": phone, "message": message, "student_id": payload.get("student_id")},
        )

_DomainEventBus.subscribe("attendance.ta_revoked", _handle_ta_revoked)
