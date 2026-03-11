"""
Domain Event Celery Tasks — P0-S17/S18

Celery tasks that dispatch domain events to registered handlers,
and retry failed events from the DB.
"""

import logging
from datetime import datetime, timezone

from server.worker import celery_app
from server.db_service import execute_query, execute_transaction

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
    """
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
    rows = execute_query(
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
