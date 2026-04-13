"""E06 — Examinations Event Handlers

Subscribes to:
  - AttendanceFinalized           → trigger hall ticket issuance
  - FeePaymentReceived            → mark student fee-cleared (gate for hall ticket)
  - ResultsDeclared               → notify students their results are published
  - ReEvalDecided                 → notify student + resolve supplementary escrow
  - alumni.graduation_saga_completed → seal transcript (decoupled from alumni module)

Publishes (via domain events in service layer):
  - HallTicketIssued     (hall_ticket.py)
  - ResultsDeclared      (grades.py)
  - ReEvalDecided        (reeval.py)
"""

from __future__ import annotations

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_attendance_finalized(event: dict) -> None:
    """
    When attendance for a semester is finalized, issue hall tickets
    for all eligible students automatically.
    """
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    actor_id = event.get("actor_id", "system")

    academic_year = payload.get("academic_year")
    semester = payload.get("semester")
    exam_type = payload.get("exam_type", "SEMESTER_END")

    if not (org_id and academic_year and semester):
        logger.warning("E06: AttendanceFinalized missing fields: %s", event)
        return

    try:
        from .hall_ticket import HallTicketService

        result = HallTicketService.issue_for_semester(
            org_id=org_id,
            academic_year=academic_year,
            semester=int(semester),
            exam_type=exam_type,
            actor_id=actor_id,
        )
        logger.info(
            "E06: Hall tickets issued after AttendanceFinalized: issued=%d blocked=%d",
            result["issued"],
            len(result["blocked"]),
        )
    except Exception as exc:
        logger.error("E06: Hall ticket issuance failed: %s", exc, exc_info=True)


def on_results_declared(event: dict) -> None:
    """Notify all students in the cohort that results are published."""
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    academic_year = payload.get("academic_year")
    semester = payload.get("semester")

    if not (org_id and academic_year and semester):
        return

    try:
        from server.core.notifications.service import NotificationDispatcher
        from server.db_service import execute_query

        students = execute_query(
            """
            SELECT DISTINCT s.id AS student_id, s.name, s.email
            FROM semester_results sr
            JOIN students s ON s.id = sr.student_id
            WHERE sr.org_id = %s AND sr.academic_year = %s AND sr.semester = %s
              AND sr.is_published = TRUE
            """,
            (org_id, academic_year, semester),
        )

        for student in students:
            try:
                NotificationDispatcher.dispatch(
                    template_key="results_declared",
                    recipient_id=str(student["student_id"]),
                    recipient_email=student["email"],
                    context={
                        "student_name": student["name"],
                        "academic_year": academic_year,
                        "semester": semester,
                    },
                    org_id=org_id,
                )
            except Exception as exc:
                logger.warning(
                    "E06: Notification failed for student %s: %s",
                    student["student_id"],
                    exc,
                )
    except Exception as exc:
        logger.error("E06: ResultsDeclared handler failed: %s", exc, exc_info=True)


def on_reeval_decided(event: dict) -> None:
    """Notify student of re-evaluation outcome AND resolve supplementary escrow."""
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    student_id = payload.get("student_id")
    decision = payload.get("decision", "")
    reeval_id = payload.get("reeval_id") or event.get("entity_id", "")

    if not (org_id and student_id):
        return

    # Resolve supplementary escrow (was in student_services/event_handlers.py — moved here)
    if decision in ("REVISED", "REJECTED") and reeval_id:
        try:
            from .reeval import RevalSupplementaryEscrowService

            RevalSupplementaryEscrowService.resolve_on_reeval_decision(
                org_id, reeval_id, decision
            )
        except Exception as exc:
            logger.warning("E06: Escrow resolution failed: %s", exc)

    try:
        from server.core.notifications.service import NotificationDispatcher
        from server.db_service import execute_query

        student_rows = execute_query(
            "SELECT name, email FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            return

        student = student_rows[0]
        NotificationDispatcher.dispatch(
            template_key="reeval_decided",
            recipient_id=student_id,
            recipient_email=student["email"],
            context={
                "student_name": student["name"],
                "decision": decision,
                "revised_marks": payload.get("revised_marks"),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.error("E06: ReEvalDecided handler failed: %s", exc, exc_info=True)


def on_graduation_saga_completed(event: dict) -> None:
    """Seal the student transcript when alumni graduation saga completes."""
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    student_id = payload.get("student_id", "")
    actor_id = event.get("actor_id", "system")

    if not (org_id and student_id):
        return

    try:
        from .transcript import TranscriptService

        TranscriptService.seal_transcript(org_id, student_id, actor_id)
        logger.info("E06: Transcript sealed for student=%s", student_id)
    except Exception as exc:
        logger.warning("E06: Transcript seal failed (non-fatal): %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("AttendanceFinalized", on_attendance_finalized)
    DomainEventBus.subscribe("ResultsDeclared", on_results_declared)
    DomainEventBus.subscribe("ReEvalDecided", on_reeval_decided)
    DomainEventBus.subscribe(
        "alumni.graduation_saga_completed", on_graduation_saga_completed
    )
    logger.info("E06 event handlers registered (4 handlers)")
