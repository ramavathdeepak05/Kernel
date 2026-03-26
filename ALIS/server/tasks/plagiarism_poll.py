"""Celery beat task — Drillbit plagiarism result polling.

Runs every 5 minutes (300 s).  Finds all PENDING plagiarism reports that have
a Drillbit submission ID and calls PlagiarismService.poll_result() for each.
"""
from __future__ import annotations

import logging

from celery import shared_task

from server.db_service import execute_query

logger = logging.getLogger(__name__)


@shared_task(
    name="server.tasks.plagiarism_poll.poll_drillbit_results",
    bind=True,
    max_retries=0,          # Beat task — never retry; next tick will run again
    ignore_result=True,
)
def poll_drillbit_results(self) -> None:  # noqa: ANN001
    """Poll Drillbit for PENDING plagiarism checks. Runs every 5 minutes."""
    from server.phd.plagiarism_service import PlagiarismService

    pending_rows = execute_query(
        """
        SELECT id, org_id, drillbit_submission_id
        FROM phd_plagiarism_reports
        WHERE status = 'PENDING'
          AND drillbit_submission_id IS NOT NULL
        ORDER BY created_at ASC
        """,
        (),
    )

    if not pending_rows:
        logger.debug("poll_drillbit_results: no pending reports to poll.")
        return

    logger.info(
        "poll_drillbit_results: polling %d pending report(s) from Drillbit.",
        len(pending_rows),
    )

    for row in pending_rows:
        drillbit_submission_id: str = row["drillbit_submission_id"]
        org_id: str = str(row["org_id"])
        report_id: str = str(row["id"])

        try:
            result = PlagiarismService.poll_result(
                drillbit_submission_id=drillbit_submission_id,
                org_id=org_id,
            )
            status = result.get("status", "UNKNOWN")
            logger.info(
                "poll_drillbit_results: report_id=%s submission_id=%s → status=%s",
                report_id, drillbit_submission_id, status,
            )
        except Exception as exc:  # noqa: BLE001
            # Log and continue — do not let one failure abort the whole batch.
            logger.error(
                "poll_drillbit_results: error polling report_id=%s submission_id=%s: %s",
                report_id, drillbit_submission_id, exc,
                exc_info=True,
            )
