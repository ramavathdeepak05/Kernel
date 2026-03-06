"""
ALIS Domain Event Bus — P0-S17

DB-backed, Celery-dispatched cross-module event system.

Extends the existing in-process EventBus (events.py / E02-S09) with:
  1. Persistence — every event written to `domain_events` table before dispatch
  2. Async dispatch — Celery worker picks up and calls subscribed handlers
  3. Retry — failed events retried up to 3× with backoff
  4. Dead-letter — events that exhaust retries marked FAILED with reason

Design:
  Publisher writes to DB (durable) → Celery task dispatches to handlers.
  If Celery is down, events are not lost — they stay PENDING in DB and
  are picked up by the retry beat task (every 5 min).

Modules communicate ONLY through domain events — never by calling each
other's services directly.

Event type registry (authoritative list):
    See: memory/architecture.md → Domain Event Bus → Complete Event Type Registry
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Handler registry (populated at startup by each module's event_handlers.py)
# ---------------------------------------------------------------------------

_handlers: Dict[str, List[Callable]] = {}


def register_handler(event_type: str, handler: Callable) -> None:
    """Register a handler function for a domain event type."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)
        logger.info("DomainEventBus: registered handler %s for %s", handler.__name__, event_type)


def get_handlers(event_type: str) -> List[Callable]:
    return _handlers.get(event_type, [])


# ---------------------------------------------------------------------------
# DomainEvent
# ---------------------------------------------------------------------------

class DomainEvent:
    """
    A domain event published by one module and consumed by others.

    Args:
        event_type:   One of the registered event types (e.g. "StudentEnrolled")
        entity_type:  The entity that changed (e.g. "student")
        entity_id:    UUID of the entity
        org_id:       Tenant ID
        payload:      Dict of relevant data for subscribers
        actor_id:     Who triggered the event (user_id or "system")
        correlation_id: Optional — link events in a pipeline chain
    """

    def __init__(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        org_id: str,
        payload: Dict[str, Any],
        actor_id: str = "system",
        correlation_id: Optional[str] = None,
    ):
        self.id = str(uuid4())
        self.event_type = event_type
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.org_id = org_id
        self.payload = payload
        self.actor_id = actor_id
        self.correlation_id = correlation_id or self.id
        self.published_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class DomainEventBus:
    """
    Publish domain events reliably via DB persistence + Celery dispatch.

    Usage:
        DomainEventBus.publish(DomainEvent(
            event_type="StudentEnrolled",
            entity_type="student",
            entity_id=student_id,
            org_id=org_id,
            payload={"program": program, "roll_number": roll_number},
            actor_id=actor_id,
        ))
    """

    @classmethod
    def publish(cls, event: DomainEvent) -> str:
        """
        Persist event to DB then dispatch to Celery.
        Returns event ID.
        """
        # 1. Persist (durable — survives Celery downtime)
        execute_transaction([
            (
                """
                INSERT INTO domain_events
                    (id, org_id, event_type, entity_type, entity_id,
                     payload, actor_id, correlation_id, status, published_at,
                     retry_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, 0)
                """,
                (
                    event.id,
                    event.org_id,
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                    json.dumps(event.payload),
                    event.actor_id,
                    event.correlation_id,
                    event.published_at,
                ),
            )
        ])

        # 2. Async dispatch via Celery
        try:
            from server.tasks.events import dispatch_domain_event
            dispatch_domain_event.delay(event.id)
        except Exception as e:
            # Celery unavailable — beat retry task will pick it up
            logger.warning("DomainEventBus: Celery unavailable, event %s queued in DB: %s", event.id, e)

        logger.info("DomainEventBus: published %s [entity=%s/%s, org=%s]",
                    event.event_type, event.entity_type, event.entity_id, event.org_id)
        return event.id

    @classmethod
    def publish_sync(cls, event: DomainEvent) -> None:
        """
        Publish and immediately dispatch handlers in-process (for tests / scripts).
        Does NOT use Celery.
        """
        cls.publish(event)
        cls._dispatch_sync(event.id)

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type. Alias for register_handler."""
        register_handler(event_type, handler)

    @classmethod
    def _dispatch_sync(cls, event_id: str) -> None:
        """Called by Celery task OR publish_sync to run handlers."""
        rows = execute_query(
            "SELECT * FROM domain_events WHERE id = %s",
            (event_id,),
        )
        if not rows:
            logger.error("DomainEventBus: event %s not found", event_id)
            return

        row = rows[0]
        event_type = row["event_type"]
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])

        # Mark as PROCESSING
        execute_transaction([(
            "UPDATE domain_events SET status = 'PROCESSING', processed_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), event_id),
        )])

        handlers = get_handlers(event_type)
        errors = []

        for handler in handlers:
            try:
                handler(
                    event_type=event_type,
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    org_id=row["org_id"],
                    payload=payload,
                    actor_id=row["actor_id"],
                    correlation_id=row["correlation_id"],
                )
            except Exception as e:
                logger.error("DomainEventBus: handler %s failed for event %s: %s",
                             handler.__name__, event_id, e)
                errors.append(str(e))

        if errors:
            retry_count = int(row.get("retry_count", 0)) + 1
            max_retries = 3
            if retry_count >= max_retries:
                execute_transaction([(
                    "UPDATE domain_events SET status = 'FAILED', retry_count = %s, "
                    "failure_reason = %s WHERE id = %s",
                    (retry_count, "; ".join(errors), event_id),
                )])
            else:
                execute_transaction([(
                    "UPDATE domain_events SET status = 'PENDING', retry_count = %s WHERE id = %s",
                    (retry_count, event_id),
                )])
        else:
            execute_transaction([(
                "UPDATE domain_events SET status = 'DONE', processed_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), event_id),
            )])
