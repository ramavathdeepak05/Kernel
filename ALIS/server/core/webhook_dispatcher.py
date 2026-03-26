"""Outbound Webhook Dispatcher (§31)

Delivers domain events to externally-registered HTTP endpoints.
- HMAC-SHA256 payload signing (X-ALIS-Signature header)
- Exponential back-off retry: 1m → 5m → 15m → 1h → 6h (max 5 attempts)
- After 5 failures: status=DEAD, SUPER_ADMIN notified via domain event
- Beat retry task (every 5 min) picks up PENDING deliveries past next_retry_at

Usage:
    subscription_id = await WebhookDispatcher.register(org_id, event_type, url, secret, actor_id)
    await WebhookDispatcher.dispatch(org_id, event_type, payload)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Retry back-off in minutes
_RETRY_DELAYS = [1, 5, 15, 60, 360]  # attempt 1-5
_MAX_ATTEMPTS = 5
_REQUEST_TIMEOUT = 10.0  # seconds


def _hash_secret(secret: str) -> str:
    """Store a one-way hash of the webhook secret."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _sign_payload(secret_hash: str, payload_bytes: bytes) -> str:
    """HMAC-SHA256 signature using the stored secret hash as key.

    Note: we store the SHA256 of the original secret, and sign with that.
    Clients must compute: HMAC-SHA256(sha256(their_secret), json_body).
    """
    return hmac.new(
        secret_hash.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


class WebhookDispatcher:

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    async def register(
        cls,
        org_id: str,
        event_type: str,
        url: str,
        secret: str,
        actor_id: str,
    ) -> str:
        """Register a new webhook subscription. Returns subscription_id."""
        subscription_id = str(uuid.uuid4())
        secret_hash = _hash_secret(secret)

        execute_transaction([
            ("""
            INSERT INTO outbound_webhook_subscriptions
                (id, org_id, event_type, url, secret_hash, active, created_by)
            VALUES (%s, %s, %s, %s, %s, TRUE, %s)
            """, (subscription_id, org_id, event_type, url, secret_hash, actor_id)),
        ])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.CREATED,
            resource_type="webhook_subscription",
            resource_id=subscription_id,
            detail={"event_type": event_type, "url": url},
        )

        logger.info("Webhook registered: %s → %s for org %s", event_type, url, org_id)
        return subscription_id

    @classmethod
    async def deactivate(
        cls,
        subscription_id: str,
        org_id: str,
        actor_id: str,
    ) -> None:
        """Deactivate a subscription — no new deliveries will be dispatched."""
        execute_transaction([
            ("""
            UPDATE outbound_webhook_subscriptions
            SET active = FALSE
            WHERE id = %s AND org_id = %s
            """, (subscription_id, org_id)),
        ])
        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="webhook_subscription",
            resource_id=subscription_id,
            detail={"active": False},
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    @classmethod
    async def dispatch(
        cls,
        org_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        """Find active subscriptions and queue a delivery for each."""
        subscriptions = execute_query("""
            SELECT id, url, secret_hash
            FROM outbound_webhook_subscriptions
            WHERE org_id = %s AND event_type = %s AND active = TRUE
        """, (org_id, event_type))

        if not subscriptions:
            return

        for sub in subscriptions:
            delivery_id = str(uuid.uuid4())
            next_retry_at = _next_retry_at(attempt=0)

            execute_transaction([
                ("""
                INSERT INTO outbound_webhook_deliveries
                    (id, subscription_id, payload, status, attempt_count, next_retry_at)
                VALUES (%s, %s, %s, 'PENDING', 0, %s)
                """, (
                    delivery_id,
                    sub["id"],
                    json.dumps(payload),
                    next_retry_at,
                )),
            ])

            # Attempt first delivery immediately (non-blocking)
            try:
                await cls._attempt_delivery(delivery_id, sub["url"], sub["secret_hash"], payload)
            except Exception as exc:
                logger.warning("Initial delivery %s failed: %s", delivery_id, exc)

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    @classmethod
    async def replay(cls, delivery_id: str, org_id: str) -> None:
        """Reset a DEAD or FAILED delivery for immediate retry."""
        rows = execute_query("""
            SELECT d.id, d.payload, s.url, s.secret_hash
            FROM outbound_webhook_deliveries d
            JOIN outbound_webhook_subscriptions s ON s.id = d.subscription_id
            WHERE d.id = %s AND s.org_id = %s
        """, (delivery_id, org_id))

        if not rows:
            from server.core.exceptions import NotFoundError
            raise NotFoundError(f"Delivery {delivery_id} not found")

        row = rows[0]
        execute_transaction([
            ("""
            UPDATE outbound_webhook_deliveries
            SET status = 'PENDING', attempt_count = 0, next_retry_at = NOW(), last_error = NULL
            WHERE id = %s
            """, (delivery_id,)),
        ])

        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        try:
            await cls._attempt_delivery(delivery_id, row["url"], row["secret_hash"], payload)
        except Exception as exc:
            logger.warning("Replay delivery %s failed: %s", delivery_id, exc)

    # ------------------------------------------------------------------
    # Internal delivery attempt
    # ------------------------------------------------------------------

    @classmethod
    async def _attempt_delivery(
        cls,
        delivery_id: str,
        url: str,
        secret_hash: str,
        payload: dict,
    ) -> None:
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = _sign_payload(secret_hash, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-ALIS-Signature": f"sha256={signature}",
            "X-ALIS-Delivery": delivery_id,
        }

        # Fetch current attempt count
        rows = execute_query(
            "SELECT attempt_count FROM outbound_webhook_deliveries WHERE id = %s",
            (delivery_id,),
        )
        attempt_count = int(rows[0]["attempt_count"]) + 1 if rows else 1

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.post(url, content=payload_bytes, headers=headers)
                resp.raise_for_status()

            execute_transaction([
                ("""
                UPDATE outbound_webhook_deliveries
                SET status = 'DELIVERED', attempt_count = %s, last_error = NULL
                WHERE id = %s
                """, (attempt_count, delivery_id)),
            ])
            logger.info("Webhook delivered: %s → %s", delivery_id, url)

        except Exception as exc:
            error_msg = str(exc)[:500]
            if attempt_count >= _MAX_ATTEMPTS:
                # Mark dead, notify SUPER_ADMIN via domain event
                execute_transaction([
                    ("""
                    UPDATE outbound_webhook_deliveries
                    SET status = 'DEAD', attempt_count = %s, last_error = %s
                    WHERE id = %s
                    """, (attempt_count, error_msg, delivery_id)),
                ])
                logger.error("Webhook DEAD after %d attempts: %s", attempt_count, delivery_id)
                # Domain event to alert admin
                sub_rows = execute_query(
                    "SELECT subscription_id FROM outbound_webhook_deliveries WHERE id = %s",
                    (delivery_id,),
                )
                if sub_rows:
                    sub_id = sub_rows[0]["subscription_id"]
                    sub_info = execute_query(
                        "SELECT org_id, event_type, url FROM outbound_webhook_subscriptions WHERE id = %s",
                        (sub_id,),
                    )
                    if sub_info:
                        DomainEventBus.publish(DomainEvent(
                            event_type="webhook.delivery_dead",
                            org_id=sub_info[0]["org_id"],
                            payload={
                                "delivery_id": delivery_id,
                                "subscription_id": sub_id,
                                "url": sub_info[0]["url"],
                                "event_type": sub_info[0]["event_type"],
                                "attempts": attempt_count,
                            },
                        ))
            else:
                next_retry = _next_retry_at(attempt=attempt_count)
                execute_transaction([
                    ("""
                    UPDATE outbound_webhook_deliveries
                    SET status = 'FAILED', attempt_count = %s,
                        next_retry_at = %s, last_error = %s
                    WHERE id = %s
                    """, (attempt_count, next_retry, error_msg, delivery_id)),
                ])
                logger.warning(
                    "Webhook attempt %d failed for %s, retry at %s: %s",
                    attempt_count, delivery_id, next_retry, error_msg,
                )
            raise


def _next_retry_at(attempt: int) -> datetime:
    """Return absolute UTC timestamp for next retry."""
    delay_minutes = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
    return datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
