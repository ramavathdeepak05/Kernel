"""
Notification tasks — P0-S15

Celery tasks for async notification delivery. The heavy lifting is done by
NotificationDispatcher (channels.py + service.py). These tasks just ensure
delivery happens off the request thread with retries.
"""
from __future__ import annotations

import logging

from server.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="notifications.send_email", bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, recipient: str, subject: str, body: str, org_id: str) -> dict:
    """
    Send an email notification via SMTP.

    Delegates to NotificationDispatcher → EmailChannel → smtplib.
    Retries up to 3 times on SMTP failure.
    """
    from server.core.notifications.channels import EmailChannel

    channel = EmailChannel()
    result = channel.send(recipient=recipient, subject=subject, body=body)

    if not result.success:
        logger.warning("notifications.send_email failed (attempt %s): %s", self.request.retries + 1, result.error_message)
        raise self.retry(exc=Exception(result.error_message))

    logger.info("notifications.send_email OK → %s", recipient)
    return {"status": "sent", "recipient": recipient, "provider_response": result.provider_response}


@celery_app.task(name="notifications.send_templated", bind=True, max_retries=3, default_retry_delay=60)
def send_templated(
    self,
    template_id: str,
    recipient_id: str,
    recipient_address: str,
    context: dict,
    org_id: str,
    channels: list[str] | None = None,
) -> dict:
    """
    Send a templated notification via NotificationDispatcher.

    Args:
        template_id: ID from TemplateRegistry (e.g. "welcome_email")
        recipient_id: User UUID for audit
        recipient_address: Email or phone
        context: Template variables dict
        org_id: Tenant identifier
        channels: List of channel names (default: ["EMAIL"])
    """
    from server.core.notifications.service import get_dispatcher
    from server.core.models import NotificationChannel

    channel_enums = [NotificationChannel(c) for c in (channels or ["EMAIL"])]
    dispatcher = get_dispatcher()

    try:
        logs = dispatcher.send(
            template_id=template_id,
            recipient_id=recipient_id,
            recipient_address=recipient_address,
            context=context,
            channels=channel_enums,
            org_id=org_id,
        )
        failed = [l for l in logs if l.status.value == "FAILED"]
        if failed:
            raise self.retry(exc=Exception(f"{len(failed)} channel(s) failed"))

        return {"status": "sent", "log_ids": [l.id for l in logs]}

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="notifications.send_sms", bind=True, max_retries=3, default_retry_delay=60)
def send_sms(self, phone: str, message: str, org_id: str) -> dict:
    """
    Send an SMS notification.
    Provider is configured via settings.sms_provider (msg91 | twilio | "").
    Falls back to console logging when no provider is configured.
    """
    from server.core.notifications.channels import SMSChannel

    channel = SMSChannel()
    result = channel.send(recipient=phone, subject=None, body=message)

    if not result.success:
        raise self.retry(exc=Exception(result.error_message))

    return {"status": "sent", "recipient": phone}


@celery_app.task(name="notifications.send_pending_reminders")
def send_pending_reminders() -> dict:
    """
    Hourly beat task: dispatch any queued reminder notifications.
    E10 (Communication Hub) will extend this with reminder query logic.
    Currently a no-op placeholder that confirms the beat schedule is running.
    """
    logger.debug("notifications.send_pending_reminders: heartbeat OK")
    return {"status": "ok", "sent": 0}


# ---------------------------------------------------------------------------
# E10 tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="notifications.fanout_announcement", bind=True, max_retries=2)
def task_fanout_announcement(self, org_id: str, announcement_id: str) -> dict:
    """
    Fan out an announcement as in-app notifications to all target recipients.
    Called after an announcement is created.
    """
    try:
        from server.communication.announcements import AnnouncementService
        from server.communication.in_app import InAppNotificationService
        from server.db_service import execute_query

        ann_rows = execute_query(
            "SELECT title, body, target_audience FROM announcements WHERE id = %s AND org_id = %s",
            (announcement_id, org_id),
        )
        if not ann_rows:
            return {"status": "not_found"}
        ann = ann_rows[0]

        recipients = AnnouncementService.get_recipients(org_id, announcement_id)
        sent = 0
        for user_id in recipients:
            try:
                InAppNotificationService.send(
                    org_id=org_id,
                    recipient_id=user_id,
                    title=ann["title"],
                    body=ann["body"],
                    link=f"/announcements/{announcement_id}",
                )
                sent += 1
            except Exception as exc:
                logger.warning("fanout_announcement: failed for user %s: %s", user_id, exc)

        logger.info("fanout_announcement: %s sent %d notifications", announcement_id, sent)
        return {"status": "done", "sent": sent}
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="notifications.process_bulk_message", bind=True, max_retries=2)
def task_process_bulk_message(self, org_id: str, job_id: str) -> dict:
    """Process a bulk message job asynchronously."""
    try:
        from server.communication.bulk import BulkMessagingService
        BulkMessagingService.process_job(org_id, job_id)
        return {"status": "done", "job_id": job_id}
    except Exception as exc:
        raise self.retry(exc=exc)
