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
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLedger
from server.db_service import (
    execute_system_query,
    execute_system_transaction,
    execute_transaction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics (optional — no hard dependency)
# ---------------------------------------------------------------------------
try:
    from server.core.metrics import (
        AVAILABLE as _METRICS_AVAILABLE,
    )
    from server.core.metrics import (
        DOMAIN_EVENTS_PROCESSED as _DOMAIN_EVENTS_PROCESSED,
    )
    from server.core.metrics import (
        DOMAIN_EVENTS_PUBLISHED as _DOMAIN_EVENTS_PUBLISHED,
    )
except Exception:
    _METRICS_AVAILABLE = False
    _DOMAIN_EVENTS_PUBLISHED = None
    _DOMAIN_EVENTS_PROCESSED = None

# ---------------------------------------------------------------------------
# Handler registry (populated at startup by each module's event_handlers.py)
# ---------------------------------------------------------------------------

_handlers: dict[str, list[Callable]] = {}


def register_handler(event_type: str, handler: Callable) -> None:
    """Register a handler function for a domain event type."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)
        logger.info(
            "DomainEventBus: registered handler %s for %s", handler.__name__, event_type
        )


def get_handlers(event_type: str) -> list[Callable]:
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
        org_id: str,
        payload: dict[str, Any],
        entity_type: str = "",
        entity_id: str = "",
        actor_id: str = "system",
        correlation_id: str | None = None,
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
        execute_transaction(
            [
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
            ]
        )
        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=event.actor_id or "system",
            actor_role="system",
            entity_type="domain_event",
            entity_id=event.id,
            tenant_id=event.org_id,
            metadata={
                "source": "DomainEventBus.publish",
                "event_type": event.event_type,
            },
        )

        # 2. Async dispatch via Celery (with deferred fallback)
        #
        # Optimization: If Celery is unavailable OR if the caller wants
        # minimum latency, the event stays PENDING in DB and the
        # perf_tasks.dispatch_pending_events beat task picks it up
        # within 3 seconds. This decouples Celery availability from
        # the publish() call path.
        try:
            from server.worker import celery_app

            celery_app.send_task(
                "server.tasks.events.dispatch_domain_event", args=[event.id]
            )
        except Exception as e:
            # Celery unavailable — beat task will pick it up within 3s
            logger.warning(
                "DomainEventBus: Celery unavailable, event %s deferred to dispatcher: %s",
                event.id,
                e,
            )

        if _METRICS_AVAILABLE and _DOMAIN_EVENTS_PUBLISHED is not None:
            try:
                _DOMAIN_EVENTS_PUBLISHED.labels(event_type=event.event_type).inc()
            except Exception:
                pass  # noqa: S110 — intentionally suppressed
        logger.info(
            "DomainEventBus: published %s [entity=%s/%s, org=%s]",
            event.event_type,
            event.entity_type,
            event.entity_id,
            event.org_id,
        )
        return event.id

    @classmethod
    def publish_fast(cls, event: DomainEvent) -> str:
        """
        Minimum-latency publish: DB INSERT only, no Celery dispatch.

        The perf_tasks.dispatch_pending_events beat task (every 3s) picks up
        PENDING events and dispatches them to Celery. Use this when the
        event doesn't need sub-second processing and you want to minimize
        the request latency path.

        Same durability guarantee as publish() — event is persisted to DB.
        """
        from server.core.perf import DeferredEventPublisher

        event_id = DeferredEventPublisher.publish_deferred(event)

        if _METRICS_AVAILABLE and _DOMAIN_EVENTS_PUBLISHED is not None:
            try:
                _DOMAIN_EVENTS_PUBLISHED.labels(event_type=event.event_type).inc()
            except Exception:
                pass  # noqa: S110 — intentionally suppressed
        logger.info(
            "DomainEventBus: published_fast %s [entity=%s/%s, org=%s]",
            event.event_type,
            event.entity_type,
            event.entity_id,
            event.org_id,
        )
        return event_id

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
        """Called by Celery task OR publish_sync to run handlers.

        Uses execute_system_* throughout because domain_events has RLS enabled
        and this method runs in the Celery worker context (no tenant scope).
        """
        rows = execute_system_query(
            "SELECT * FROM domain_events WHERE id = %s",
            (event_id,),
        )
        if not rows:
            logger.error("DomainEventBus: event %s not found", event_id)
            return

        row = rows[0]
        event_type = row["event_type"]
        payload = (
            row["payload"]
            if isinstance(row["payload"], dict)
            else json.loads(row["payload"])
        )

        # Mark as PROCESSING (idempotent — task may have already done this)
        execute_system_transaction(
            [
                (
                    "UPDATE domain_events SET status = 'PROCESSING', processed_at = %s WHERE id = %s",
                    (datetime.now(timezone.utc), event_id),
                )
            ]
        )

        handlers = get_handlers(event_type)
        errors = []

        # Set tenant context so handlers can call tenant-scoped DB operations.
        # Event handlers are cross-module and may call services that use execute_transaction
        # (which requires tenant context via ContextVar). We set it here from the event's
        # org_id and clear it in the finally block regardless of success or failure.
        org_id = row.get("org_id", "")
        _ctx_token = None
        if org_id:
            try:
                from server.core.security import _current_tenant_id as _tid_var

                _ctx_token = _tid_var.set(org_id)
            except Exception as _ctx_err:
                logger.warning(
                    "DomainEventBus: could not set tenant context for org %s: %s",
                    org_id,
                    _ctx_err,
                )

        try:
            for handler in handlers:
                handler_name = f"{handler.__module__}.{handler.__name__}"
                # EC-CROSS-01: idempotency guard — skip if this handler already ran
                try:
                    execute_system_transaction(
                        [
                            (
                                "INSERT INTO domain_event_handler_log "
                                "(event_id, handler_name, status) VALUES (%s, %s, 'PROCESSING') "
                                "ON CONFLICT (event_id, handler_name) DO NOTHING",
                                (event_id, handler_name),
                            )
                        ]
                    )
                    # If the INSERT was a no-op (conflict), the row exists → already ran
                    already_ran = execute_system_query(
                        "SELECT status FROM domain_event_handler_log "
                        "WHERE event_id = %s AND handler_name = %s",
                        (event_id, handler_name),
                    )
                    if already_ran and already_ran[0]["status"] in (
                        "SUCCESS",
                        "PROCESSING",
                    ):
                        if already_ran[0]["status"] == "SUCCESS":
                            logger.info(
                                "DomainEventBus: skipping handler %s (already ran for event %s)",
                                handler_name,
                                event_id,
                            )
                            continue
                        # PROCESSING → this worker previously crashed mid-handler → retry is OK
                except Exception as idem_err:
                    logger.warning(
                        "EC-CROSS-01: idempotency check failed for %s: %s",
                        handler_name,
                        idem_err,
                    )

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
                    # Mark handler as successfully completed
                    execute_system_transaction(
                        [
                            (
                                "UPDATE domain_event_handler_log SET status = 'SUCCESS' "
                                "WHERE event_id = %s AND handler_name = %s",
                                (event_id, handler_name),
                            )
                        ]
                    )
                except Exception as e:
                    logger.error(
                        "DomainEventBus: handler %s failed for event %s: %s",
                        handler.__name__,
                        event_id,
                        e,
                    )
                    errors.append(str(e))
                    try:
                        execute_system_transaction(
                            [
                                (
                                    "UPDATE domain_event_handler_log SET status = 'FAILED', "
                                    "error_detail = %s WHERE event_id = %s AND handler_name = %s",
                                    (str(e), event_id, handler_name),
                                )
                            ]
                        )
                    except Exception:
                        pass  # noqa: S110 — intentionally suppressed
        finally:
            # Always restore tenant context after handler execution
            if _ctx_token is not None:
                try:
                    from server.core.security import _current_tenant_id as _tid_var

                    _tid_var.reset(_ctx_token)
                except Exception:
                    pass  # noqa: S110 — intentionally suppressed

        if errors:
            retry_count = int(row.get("retry_count", 0)) + 1
            max_retries = 3
            final_status = "FAILED" if retry_count >= max_retries else "PENDING"
            if retry_count >= max_retries:
                execute_system_transaction(
                    [
                        (
                            "UPDATE domain_events SET status = 'FAILED', retry_count = %s, "
                            "failure_reason = %s WHERE id = %s",
                            (retry_count, "; ".join(errors), event_id),
                        )
                    ]
                )
            else:
                execute_system_transaction(
                    [
                        (
                            "UPDATE domain_events SET status = 'PENDING', retry_count = %s WHERE id = %s",
                            (retry_count, event_id),
                        )
                    ]
                )
            if _METRICS_AVAILABLE and _DOMAIN_EVENTS_PROCESSED is not None:
                try:
                    _DOMAIN_EVENTS_PROCESSED.labels(
                        event_type=event_type, status=final_status
                    ).inc()
                except Exception:
                    pass  # noqa: S110 — intentionally suppressed
        else:
            execute_system_transaction(
                [
                    (
                        "UPDATE domain_events SET status = 'DONE', processed_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc), event_id),
                    )
                ]
            )
            if _METRICS_AVAILABLE and _DOMAIN_EVENTS_PROCESSED is not None:
                try:
                    _DOMAIN_EVENTS_PROCESSED.labels(
                        event_type=event_type, status="DONE"
                    ).inc()
                except Exception:
                    pass  # noqa: S110 — intentionally suppressed

        # P21 — Outbound webhook dispatch (after all internal handlers)
        # Runs for every event type; WebhookDispatcher checks subscriptions.
        try:
            import asyncio

            from server.core.webhook_dispatcher import WebhookDispatcher

            org_id = row.get("org_id", "")
            if org_id:
                asyncio.run(WebhookDispatcher.dispatch(org_id, event_type, payload))
        except Exception as _wh_exc:
            logger.debug(
                "Webhook dispatch skipped or failed for event %s: %s", event_id, _wh_exc
            )
