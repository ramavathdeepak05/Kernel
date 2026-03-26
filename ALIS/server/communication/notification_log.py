"""E10-S02/S03 — DB-backed Notification Delivery Log

Provides the `dispatch()` class method used by all other modules.
Replaces the in-memory _logs dict in the legacy NotificationDispatcher.
"""
from __future__ import annotations

import logging
import uuid
from string import Template
from typing import Any

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class NotificationLogService:

    @classmethod
    def dispatch(
        cls,
        template_key: str,
        recipient_id: str,
        recipient_email: str,
        context: dict[str, Any],
        org_id: str | None = None,
        channel: str = "EMAIL",
        _subject_override: str | None = None,
        _body_override: str | None = None,
    ) -> dict:
        """
        Central dispatch method called by all modules.

        1. Resolves template (DB → TemplateRegistry fallback)
        2. Renders subject/body with context
        3. Sends via channel (Email/SMS)
        4. Also creates an in-app notification
        5. Logs to notification_logs table
        """
        log_id = str(uuid.uuid4())
        status = "PENDING"
        error_msg = None

        subject, body = cls._resolve_and_render(
            org_id or "system", template_key, context,
            _subject_override, _body_override,
        )

        # Send via channel
        try:
            if channel == "EMAIL":
                from server.core.notifications.channels import EmailChannel
                result = EmailChannel().send(recipient=recipient_email, subject=subject, body=body)
                status = "SENT" if result.success else "FAILED"
                error_msg = None if result.success else result.error_message
            elif channel == "SMS":
                from server.core.notifications.channels import SMSChannel
                result = SMSChannel().send(recipient=recipient_email, subject=None, body=body)
                status = "SENT" if result.success else "FAILED"
                error_msg = None if result.success else result.error_message
            else:
                status = "SENT"
        except Exception as exc:
            logger.error("dispatch: channel send failed: %s", exc)
            status = "FAILED"
            error_msg = str(exc)

        # Also create in-app notification for email dispatches
        if org_id and channel == "EMAIL" and status == "SENT":
            try:
                from .in_app import InAppNotificationService
                InAppNotificationService.send(
                    org_id=org_id,
                    recipient_id=recipient_id,
                    title=subject or template_key,
                    body=body[:500],
                )
            except Exception as exc:
                logger.debug("dispatch: in-app creation skipped: %s", exc)

        # Persist log
        try:
            execute_transaction([(
                """
                INSERT INTO notification_logs
                    (id, org_id, recipient_id, recipient_addr, template_key, channel, status, error_message, sent_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (log_id, org_id, recipient_id, recipient_email,
                 template_key, channel, status, error_msg),
            )])
        except Exception as exc:
            logger.warning("dispatch: log persistence failed (non-fatal): %s", exc)

        return {"log_id": log_id, "status": status, "channel": channel}

    @classmethod
    def _resolve_and_render(
        cls,
        org_id: str,
        template_key: str,
        context: dict,
        subject_override: str | None,
        body_override: str | None,
    ) -> tuple[str, str]:
        if subject_override is not None and body_override is not None:
            return subject_override, body_override

        # 1. Check DB templates
        try:
            rows = execute_query(
                """
                SELECT subject, body FROM notification_templates
                WHERE org_id = %s AND key = %s AND is_active = TRUE
                LIMIT 1
                """,
                (org_id, template_key),
            )
            if rows:
                raw_subj = rows[0]["subject"] or ""
                raw_body = rows[0]["body"]
                subject = Template(raw_subj).safe_substitute(context)
                body = Template(raw_body).safe_substitute(context)
                return subject, body
        except Exception as exc:
            logger.debug("dispatch: DB template lookup failed: %s", exc)

        # 2. Fallback — core TemplateRegistry (in-memory hardcoded)
        try:
            from server.core.notifications.templates import TemplateRegistry
            subject, body = TemplateRegistry.render(template_key, context)
            return subject, body
        except Exception:
            pass

        # 3. Generic fallback
        title = context.get("title", template_key.replace("_", " ").title())
        body_text = context.get("message", str(context))
        return title, body_text

    @classmethod
    def list_for_recipient(cls, org_id: str, recipient_id: str, limit: int = 50) -> list[dict]:
        rows = execute_query(
            """
            SELECT * FROM notification_logs
            WHERE org_id = %s AND recipient_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (org_id, recipient_id, limit),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_failed(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT * FROM notification_logs
            WHERE org_id = %s AND status = 'FAILED' AND retry_count < 3
            ORDER BY created_at
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]

    @classmethod
    def retry(cls, org_id: str, log_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM notification_logs WHERE id = %s AND org_id = %s",
            (log_id, org_id),
        )
        if not rows:
            from server.core.exceptions import NotFoundError
            raise NotFoundError(f"Notification log {log_id} not found")
        log = dict(rows[0])

        if log["status"] == "SENT":
            return log

        result = cls.dispatch(
            template_key=log["template_key"],
            recipient_id=log["recipient_id"],
            recipient_email=log["recipient_addr"],
            context={},
            org_id=org_id,
            channel=log["channel"],
        )

        execute_transaction([(
            "UPDATE notification_logs SET retry_count = retry_count + 1 WHERE id = %s",
            (log_id,),
        )])
        return result
