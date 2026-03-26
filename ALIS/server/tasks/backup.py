"""P22 — Daily Database Backup Task

Celery Beat task that triggers BackupService.run_daily_backup().
Scheduled daily at 03:00 UTC via worker.py beat_schedule.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="server.tasks.backup.run_daily_backup", bind=True, max_retries=1)
def run_daily_backup(self):
    """Trigger pg_dump + MinIO upload via BackupService.

    Fires platform.backup_failed domain event on failure.
    """
    try:
        from server.core.backup_service import BackupService
        result = BackupService.run_daily_backup()
        if result.get("status") == "FAILED":
            logger.error("Daily backup FAILED: %s", result.get("error"))
        else:
            logger.info("Daily backup complete: %s (uploaded=%s)", result.get("filename"), result.get("uploaded"))
        return result
    except Exception as exc:
        logger.exception("Backup task raised an exception: %s", exc)
        raise self.retry(exc=exc, countdown=300)  # retry once after 5 min
