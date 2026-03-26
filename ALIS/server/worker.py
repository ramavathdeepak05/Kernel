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
from __future__ import annotations

import json
import logging
import traceback as tb_module
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure
from kombu import Queue

from server.core.settings import settings

logger = logging.getLogger(__name__)

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
        "server.tasks.finance",          # M4 finance beat tasks (E07)
        "server.tasks.reporting",        # M8 reporting & analytics (E11)
        "server.tasks.shadow_divergence", # P21 shadow mode nightly divergence
        "server.tasks.webhook_retry",    # P21 outbound webhook retry
        "server.tasks.backup",           # P22 daily database backup
        "server.tasks.plagiarism_poll",  # E15 Drillbit plagiarism result polling
        "server.tasks.lms_sync",         # P14 Moodle LMS grade sync
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

celery_app.conf.task_queues = (
    Queue("default"),
    Queue("high_priority"),
    Queue("dead_letter"),   # Receives tasks that exhausted all retries
)
celery_app.conf.task_default_queue = "default"

# ---------------------------------------------------------------------------
# Dead-Letter Queue — task_failure signal
#
# Fired by Celery after a task has exhausted all retries.  Writes a row to
# the failed_task_log table so ops can inspect and manually replay via
# GET/POST /api/v1/admin/failed-tasks.
# ---------------------------------------------------------------------------

@task_failure.connect
def on_task_failure(
    sender: Any,
    task_id: str,
    exception: Exception,
    args: Any,
    kwargs: Any,
    traceback: Any,
    einfo: Any,
    **rest: Any,
) -> None:
    """Persist failed task metadata to the dead-letter log."""
    try:
        from server.db_service import execute_transaction
        task_name: str = getattr(sender, "name", str(sender))
        full_tb = tb_module.format_tb(traceback) if traceback else []
        # Extract tenant_id if it was threaded through kwargs
        tenant_id: str | None = (kwargs or {}).get("tenant_id") or (kwargs or {}).get("org_id")
        execute_transaction([(
            """
            INSERT INTO failed_task_log
                (task_id, task_name, args, kwargs, error, traceback, tenant_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                task_name,
                json.dumps(list(args or [])),
                json.dumps(dict(kwargs or {})),
                str(exception),
                "".join(full_tb)[:4000],  # cap at 4 KB
                tenant_id,
            ),
        )])
    except Exception:
        # Never let DLQ logging crash the worker process
        logger.exception("DLQ: failed to persist failed_task_log entry for task %s", task_id)

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
    # Retry PENDING domain events that were never dispatched: every 5 minutes
    "retry-failed-events": {
        "task": "server.tasks.events.retry_failed_events",
        "schedule": crontab(minute="*/5"),
    },
    # Detect PROCESSING events whose worker crashed mid-flight.
    # Targets FINANCE and EXAMINATION topics only — these have near-zero
    # acceptable inconsistency windows (payment confirmation → enrollment,
    # grade finalization → transcript generation).
    # Runs every 30 seconds via a timedelta schedule (not a crontab).
    "retry-stuck-critical-events": {
        "task": "server.tasks.events.retry_stuck_events",
        "schedule": 30.0,  # seconds
        "kwargs": {"topics": ["FINANCE", "EXAMINATION"], "stuck_after_seconds": 120},
    },
    # KPI snapshots: daily at 00:30 AM (after calendar check)
    "refresh-kpi-snapshots": {
        "task": "reporting.refresh_kpi_snapshots",
        "schedule": crontab(hour=0, minute=30),
    },
    # AQAR draft compilation: annually on 1 July (NAAC Annual Quality Assurance Report)
    # Gated by regulatory.naac_evidence_collection feature flag — no-op if disabled.
    "aqar-annual-draft": {
        "task": "server.tasks.events.compile_aqar_draft",
        "schedule": crontab(hour=6, minute=0, month_of_year=7, day_of_month=1),
    },
    # P21 — Shadow mode nightly divergence tracker (02:00 IST = 20:30 UTC)
    "shadow-divergence-nightly": {
        "task": "server.tasks.shadow_divergence.run_shadow_divergence",
        "schedule": crontab(hour=20, minute=30),
    },
    # P21 — Webhook retry (every 5 minutes)
    "webhook-retry": {
        "task": "server.tasks.webhook_retry.retry_pending_webhooks",
        "schedule": 300.0,  # seconds (5 minutes)
    },
    # P21 — Reporting gate deadline check (daily at 08:00 IST = 02:30 UTC)
    "reporting-gate-check": {
        "task": "server.tasks.admissions.check_reporting_deadlines",
        "schedule": crontab(hour=2, minute=30),
    },
    # P22 — Daily database backup (03:00 UTC)
    "daily-db-backup": {
        "task": "server.tasks.backup.run_daily_backup",
        "schedule": crontab(hour=3, minute=0),
    },
    # E15 — Poll Drillbit for PhD plagiarism results (every 5 minutes)
    "drillbit-poll": {
        "task": "server.tasks.plagiarism_poll.poll_drillbit_results",
        "schedule": 300.0,  # seconds (5 minutes)
    },
    # P14 — Moodle LMS grade sync: weekly, Sunday 01:00 UTC
    "lms-grade-sync": {
        "task": "server.tasks.lms_sync.sync_lms_grades",
        "schedule": crontab(hour=1, minute=0, day_of_week=0),  # 0 = Sunday
    },
}
