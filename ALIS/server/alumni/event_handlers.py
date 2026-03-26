"""E12 — Alumni & Placement Event Handlers

Subscribes to:
  - StudentGraduated → auto-create alumni profile
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
    org_id     = event.get("org_id")
    entity_id  = event.get("entity_id")   # student_id
    payload    = event.get("payload", {})

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
            entity_id, profile.get("id"),
        )
    except Exception as exc:
        logger.error("E12: Alumni profile creation failed for student %s: %s", entity_id, exc, exc_info=True)


def register_all() -> None:
    DomainEventBus.subscribe("StudentGraduated", on_student_graduated)
    logger.info("E12 event handlers registered")
