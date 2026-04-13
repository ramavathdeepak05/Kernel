"""E12 — Alumni & Placement Event Handlers

Subscribes to:
  - StudentGraduated              → auto-create alumni profile
  - result.final_published        → alumni saga signal 1/3
  - student.dues_cleared          → alumni saga signal 2/3
  - graduation.verified           → alumni saga signal 3/3
"""

from __future__ import annotations

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_student_graduated(event: dict) -> None:
    """
    When a student graduates, automatically create their alumni profile
    seeded from the students table.
    """
    org_id = event.get("org_id")
    entity_id = event.get("entity_id")  # student_id
    event.get("payload", {})

    if not (org_id and entity_id):
        logger.warning("E12: StudentGraduated missing fields: %s", event)
        return

    try:
        from .profiles import AlumniProfileService

        profile = AlumniProfileService.create_from_student(
            org_id=org_id,
            student_id=str(entity_id),
            actor_id="system",
        )
        logger.info(
            "E12: Alumni profile created for student %s → alumni %s",
            entity_id,
            profile.get("id"),
        )
    except Exception as exc:
        logger.error(
            "E12: Alumni profile creation failed for student %s: %s",
            entity_id,
            exc,
            exc_info=True,
        )


def on_result_published(event: dict) -> None:
    """Alumni saga signal 1/3 — moved from student_services.event_handlers."""
    payload = (
        event.get("payload", {}) if isinstance(event, dict) else (event.payload or {})
    )
    org_id = event.get("org_id") if isinstance(event, dict) else event.org_id
    student_id = payload.get("student_id", "")
    if student_id:
        try:
            from .graduation_saga import AlumniTransitionSaga

            AlumniTransitionSaga.record_signal(
                org_id, student_id, "result.final_published"
            )
        except Exception as exc:
            logger.warning("E12: Alumni saga signal (result) failed: %s", exc)


def on_dues_cleared(event: dict) -> None:
    """Alumni saga signal 2/3 — moved from student_services.event_handlers."""
    payload = (
        event.get("payload", {}) if isinstance(event, dict) else (event.payload or {})
    )
    org_id = event.get("org_id") if isinstance(event, dict) else event.org_id
    student_id = payload.get("student_id", "")
    if student_id:
        try:
            from .graduation_saga import AlumniTransitionSaga

            AlumniTransitionSaga.record_signal(
                org_id, student_id, "student.dues_cleared"
            )
        except Exception as exc:
            logger.warning("E12: Alumni saga signal (dues) failed: %s", exc)


def on_graduation_verified(event: dict) -> None:
    """Alumni saga signal 3/3 — moved from student_services.event_handlers."""
    payload = (
        event.get("payload", {}) if isinstance(event, dict) else (event.payload or {})
    )
    org_id = event.get("org_id") if isinstance(event, dict) else event.org_id
    student_id = payload.get("student_id", "")
    if student_id:
        try:
            from .graduation_saga import AlumniTransitionSaga

            AlumniTransitionSaga.record_signal(
                org_id, student_id, "graduation.verified"
            )
        except Exception as exc:
            logger.warning("E12: Alumni saga signal (graduation) failed: %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("StudentGraduated", on_student_graduated)
    DomainEventBus.subscribe("result.final_published", on_result_published)
    DomainEventBus.subscribe("student.dues_cleared", on_dues_cleared)
    DomainEventBus.subscribe("graduation.verified", on_graduation_verified)
    logger.info("E12 event handlers registered (4 handlers)")
