"""E13-S06 — Event-triggered process launch.

Subscribes to domain events and auto-launches matching process definitions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def _launch_matching_processes(event_name: str, payload: Dict[str, Any]) -> None:
    """Find all active process definitions that subscribe to event_name and launch them."""
    try:
        from server.process_engine.definition import ProcessDefinitionService
        from server.process_engine.instance import ProcessInstanceService

        definitions = ProcessDefinitionService.find_by_event(event_name)
        for defn in definitions:
            import json
            trigger_filter = defn.get("trigger_filter") or {}
            if isinstance(trigger_filter, str):
                trigger_filter = json.loads(trigger_filter)

            # Apply trigger filter: all k/v in filter must match payload
            if any(payload.get(k) != v for k, v in trigger_filter.items()):
                continue

            try:
                ProcessInstanceService.launch(
                    org_id=str(defn["org_id"]),
                    process_id=str(defn["id"]),
                    triggered_by="system",
                    context=payload,
                    entity_type=payload.get("entity_type"),
                    entity_id=str(payload.get("entity_id", "")),
                    trigger_event=event_name,
                )
                logger.info("Launched process '%s' for event '%s'", defn["name"], event_name)
            except Exception as exc:
                logger.exception("Failed to launch process '%s' for event '%s': %s", defn["name"], event_name, exc)

    except Exception as exc:
        logger.exception("_launch_matching_processes error for '%s': %s", event_name, exc)


# Events that can trigger process definitions
_TRIGGER_EVENTS = [
    "AdmissionConfirmed",
    "ApplicationSubmitted",
    "ApplicationReviewStarted",
    "FeeInvoiceGenerated",
    "FeePaymentReceived",
    "EnrollmentConfirmed",
    "StudentGraduated",
    "SemesterStarted",
    "SemesterEnded",
    "ResultsDeclared",
    "LeaveApplicationSubmitted",
    "GrievanceSubmitted",
    "DocumentUploadRequested",
    "ScholarshipApplicationSubmitted",
]


def register_all() -> None:
    for event in _TRIGGER_EVENTS:
        _event = event  # capture for closure

        def _handler(payload: Dict[str, Any], ev: str = _event) -> None:
            _launch_matching_processes(ev, payload)

        DomainEventBus.subscribe(_event, _handler)
    logger.info("E13 Process Engine event handlers registered (%d events)", len(_TRIGGER_EVENTS))
