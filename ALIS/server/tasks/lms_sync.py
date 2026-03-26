"""
LMS Sync Celery Tasks

Periodic tasks for Moodle LMS integration:
  - sync_lms_grades: weekly (Sunday 01:00 UTC) — pulls grades for all active
    students from Moodle and upserts into the lms_grade_sync table.

Run worker:
    celery -A server.worker worker --loglevel=info
"""
from __future__ import annotations

import logging

from server.worker import celery_app
from server.db_service import execute_query

logger = logging.getLogger(__name__)


@celery_app.task(
    name="server.tasks.lms_sync.sync_lms_grades",
    bind=True,
    max_retries=2,
    default_retry_delay=300,   # 5 minutes between retries
    acks_late=True,
)
def sync_lms_grades(self) -> dict:
    """
    Weekly grade sync: iterate all active tenants → all active students →
    call MoodleLMSService.sync_grades_to_alis().

    Skips tenants where LMS is not configured or the feature flag is off.
    Individual student failures are logged and counted rather than aborting
    the entire run.
    """
    from server.integrations.lms_service import MoodleLMSService

    service = MoodleLMSService()
    if not service.is_enabled():
        logger.info("sync_lms_grades: LMS not globally configured — skipping")
        return {"status": "skipped", "reason": "LMS not configured"}

    # Fetch all active tenants
    orgs = execute_query(
        "SELECT id FROM organizations WHERE status = 'ACTIVE'",
        (),
    )

    total_ok    = 0
    total_skip  = 0
    total_error = 0

    for org_row in orgs:
        org_id = str(org_row["id"])

        # Tenant-level feature flag check (service checks internally, but we
        # skip the per-student loop early here to avoid N unnecessary queries)
        try:
            from server.core.feature_flags import feature_flags
            if not feature_flags.is_enabled("integrations.lms_enabled", org_id):
                logger.debug("sync_lms_grades: LMS disabled for org=%s — skipping", org_id)
                continue
        except Exception:
            pass  # Feature flags unavailable — continue

        # Fetch all active students for this tenant
        students = execute_query(
            """
            SELECT id FROM students
            WHERE org_id = %s AND status NOT IN ('WITHDRAWN', 'EXPELLED', 'GRADUATED')
            """,
            (org_id,),
        )

        for row in students:
            student_id = str(row["id"])
            try:
                result = service.sync_grades_to_alis(org_id=org_id, student_id=student_id)
                if result.get("status") == "ok":
                    total_ok += 1
                else:
                    total_skip += 1
            except Exception as exc:
                logger.error(
                    "sync_lms_grades: failed for org=%s student=%s — %s",
                    org_id, student_id, exc,
                )
                total_error += 1

    summary = {
        "status": "ok",
        "synced": total_ok,
        "skipped": total_skip,
        "errors": total_error,
    }
    logger.info("sync_lms_grades: completed — %s", summary)
    return summary
