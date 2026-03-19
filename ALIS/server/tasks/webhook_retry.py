"""Webhook Retry Task — Celery Beat every 5 minutes (§31)

Finds all FAILED deliveries past their next_retry_at and re-attempts them.

Beat schedule entry (added in worker.py):
    "webhook-retry": {
        "task": "server.tasks.webhook_retry.retry_pending_webhooks",
        "schedule": timedelta(minutes=5),
    }
"""

import logging

from celery import shared_task

from server.db_service import execute_query

logger = logging.getLogger(__name__)


@shared_task(
    name="server.tasks.webhook_retry.retry_pending_webhooks",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def retry_pending_webhooks(self):
    """Re-attempt all FAILED webhook deliveries past their next_retry_at."""
    rows = execute_query("""
        SELECT d.id, d.payload, s.url, s.secret_hash, s.org_id
        FROM outbound_webhook_deliveries d
        JOIN outbound_webhook_subscriptions s ON s.id = d.subscription_id
        WHERE d.status = 'FAILED'
          AND d.next_retry_at <= NOW()
          AND d.attempt_count < 5
          AND s.active = TRUE
        LIMIT 100
    """, ())

    if not rows:
        return

    import asyncio
    from server.core.webhook_dispatcher import WebhookDispatcher

    async def _run_all():
        for row in rows:
            import json
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
            try:
                await WebhookDispatcher._attempt_delivery(
                    delivery_id=row["id"],
                    url=row["url"],
                    secret_hash=row["secret_hash"],
                    payload=payload,
                )
            except Exception as exc:
                logger.warning("Retry failed for delivery %s: %s", row["id"], exc)

    asyncio.run(_run_all())
    logger.info("Webhook retry task processed %d deliveries", len(rows))
