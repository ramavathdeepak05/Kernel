"""
ALIS Celery Worker — P0-S04

Async task queue for all background work:
- AI document verification (async — don't block the upload response)
- Offer letter PDF generation
- Email / SMS notification delivery
- Domain event dispatch (P0-S17)
- Academic calendar triggers (P0-S19)
- Automation pipeline task chains (E04-S13+)

Run worker:
    celery -A server.worker worker --loglevel=info --concurrency=4

Run beat scheduler (for calendar triggers):
    celery -A server.worker beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    # OR simple file-based scheduler:
    celery -A server.worker beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from server.core.settings import settings

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

celery_app = Celery(
    "alis",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "server.tasks.notifications",   # E10 — email/SMS delivery tasks
        "server.tasks.ai_tasks",        # AI doc verify, eligibility, etc.
        "server.tasks.events",          # Domain event dispatch (P0-S17)
        "server.tasks.calendar",        # Academic calendar triggers (P0-S19)
        "server.tasks.admissions",      # M1 automation pipeline (E04-S13)
        "server.tasks.finance",         # M4 finance beat tasks (E07)
        "server.tasks.reporting",       # M8 reporting & analytics (E11)
    ],
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_task_serializer,
    accept_content=[settings.celery_task_serializer],
    result_expires=settings.celery_result_expires,
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,            # Re-queue on worker crash
    worker_prefetch_multiplier=1,   # Fair dispatch, one task at a time per worker
    task_reject_on_worker_lost=True,
    # Retry policy defaults (tasks can override)
    task_max_retries=3,
    task_default_retry_delay=60,    # seconds
)

# ---------------------------------------------------------------------------
# Beat Schedule (Celery Beat — periodic tasks)
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Academic calendar: check phase transitions every day at midnight
    "calendar-phase-check": {
        "task": "server.tasks.calendar.check_calendar_phases",
        "schedule": crontab(hour=0, minute=0),
    },
    # Fee overdue check: daily at 9 AM (admissions offer expiry)
    "fee-overdue-check": {
        "task": "server.tasks.admissions.check_fee_overdue",
        "schedule": crontab(hour=9, minute=0),
    },
    # Invoice overdue check: daily at 9:05 AM (mark UNPAID→OVERDUE)
    "invoice-overdue-check": {
        "task": "finance.check_invoice_overdue",
        "schedule": crontab(hour=9, minute=5),
    },
    # Task reminders: every hour
    "task-reminders": {
        "task": "server.tasks.notifications.send_pending_reminders",
        "schedule": crontab(minute=0),
    },
    # Retry failed domain events: every 5 minutes
    "retry-failed-events": {
        "task": "server.tasks.events.retry_failed_events",
        "schedule": crontab(minute="*/5"),
    },
    # KPI snapshots: daily at 00:30 AM (after calendar check)
    "refresh-kpi-snapshots": {
        "task": "reporting.refresh_kpi_snapshots",
        "schedule": crontab(hour=0, minute=30),
    },
}
