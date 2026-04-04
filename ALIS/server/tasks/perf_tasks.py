"""
ALIS Performance Tasks — Background workers for optimized pipelines.

Tasks:
  1. drain_audit_queue — Persist async audit entries from Redis → DB
  2. dispatch_pending_events — Poll domain_events for PENDING and push to Celery
  3. warm_caches — Periodic cache warming for hot RBAC/policy lookups
"""
from __future__ import annotations

import logging

from server.worker import celery_app

logger = logging.getLogger(__name__)


# =============================================================================
# 1. DRAIN ASYNC AUDIT QUEUE
# =============================================================================

@celery_app.task(name="server.tasks.perf_tasks.drain_audit_queue", queue="default")
def drain_audit_queue(batch_size: int = 200) -> dict:
    """
    Drain pending audit entries from Redis and persist to DB.

    Runs every 2 seconds via beat. Each invocation drains up to batch_size
    entries, maintaining hash-chain integrity via the existing AuditLedger.log()
    which acquires per-tenant advisory locks.

    Returns {"persisted": N, "remaining": M}
    """
    from server.core.perf import AsyncAuditWriter, _get_redis

    persisted = AsyncAuditWriter.drain_batch(batch_size=batch_size)

    # Check remaining queue length
    remaining = 0
    try:
        r = _get_redis()
        if r:
            remaining = r.llen("alis:audit:pending") or 0
    except Exception:
        pass

    if persisted > 0:
        logger.info("drain_audit_queue: persisted=%d remaining=%d", persisted, remaining)

    return {"persisted": persisted, "remaining": remaining}


# =============================================================================
# 2. DISPATCH PENDING DOMAIN EVENTS (Stage 2 of two-stage events)
# =============================================================================

@celery_app.task(name="server.tasks.perf_tasks.dispatch_pending_events", queue="default")
def dispatch_pending_events(batch_size: int = 50) -> dict:
    """
    Poll domain_events table for PENDING events and dispatch to Celery.

    This is Stage 2 of the two-stage event system:
      Stage 1 (in request): INSERT into domain_events with status=PENDING
      Stage 2 (this task): SELECT PENDING → dispatch_domain_event.delay()

    Runs every 3 seconds via beat. Picks up events that were written
    by DeferredEventPublisher (perf.py) without immediate Celery dispatch.

    Also handles events from the standard DomainEventBus.publish() path
    where Celery was unavailable at publish time.
    """
    from server.db_service import execute_system_query, execute_system_transaction
    from datetime import datetime, timezone

    # Only pick up events that have been PENDING for at least 5 seconds.
    # This avoids racing with DomainEventBus.publish() which dispatches
    # to Celery immediately — those events go PENDING → PROCESSING within
    # seconds. Events still PENDING after 5s were either:
    #   1. Written by DeferredEventPublisher (no Celery dispatch)
    #   2. Written when Celery was unavailable
    # The 2-minute check on processing_started_at catches events where
    # a previous dispatch_domain_event worker crashed mid-flight.
    rows = execute_system_query(
        """
        SELECT id FROM domain_events
        WHERE status = 'PENDING'
          AND published_at < NOW() - INTERVAL '5 seconds'
          AND (processing_started_at IS NULL
               OR processing_started_at < NOW() - INTERVAL '2 minutes')
        ORDER BY published_at ASC
        LIMIT %s
        """,
        (batch_size,),
    )

    if not rows:
        return {"dispatched": 0}

    dispatched = 0
    for row in rows:
        event_id = row["id"]
        try:
            # Mark as being picked up to prevent double-dispatch
            execute_system_transaction([(
                "UPDATE domain_events SET processing_started_at = %s WHERE id = %s AND status = 'PENDING'",
                (datetime.now(timezone.utc), event_id),
            )])
            from server.tasks.events import dispatch_domain_event
            dispatch_domain_event.delay(event_id)
            dispatched += 1
        except Exception as e:
            logger.warning("dispatch_pending_events: failed to dispatch %s: %s", event_id, e)

    if dispatched > 0:
        logger.info("dispatch_pending_events: dispatched=%d of %d", dispatched, len(rows))

    return {"dispatched": dispatched}


# =============================================================================
# 3. CACHE WARMING — Periodic hot-cache refresh
# =============================================================================

@celery_app.task(name="server.tasks.perf_tasks.warm_caches", queue="default")
def warm_caches() -> dict:
    """
    Warm frequently-used caches to avoid cold-start latency.

    Currently warms:
      - Nothing by default (extensible hook for future use)

    Vault warm-up happens at FastAPI startup (lifespan), not here.
    """
    return {"warmed": 0}
