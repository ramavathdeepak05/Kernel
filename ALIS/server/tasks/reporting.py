"""E11 — Reporting & Analytics Celery Tasks"""

from __future__ import annotations

import logging

from server.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="reporting.run_export", bind=True, max_retries=2, default_retry_delay=30
)
def task_run_export(self, org_id: str, job_id: str) -> dict:
    """Process an export job asynchronously."""
    try:
        from server.reporting.export_engine import ExportEngine

        ExportEngine.process_job(org_id, job_id)
        return {"status": "done", "job_id": job_id}
    except Exception as exc:
        logger.error("reporting.run_export failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(name="reporting.refresh_kpi_snapshots")
def task_refresh_kpi_snapshots() -> dict:
    """
    Daily beat task: recompute KPI snapshots for all active organizations.
    Runs at midnight so dashboards load from cache instantly.
    """
    try:
        from server.db_service import execute_system_query

        orgs = execute_system_query(
            "SELECT id FROM organizations WHERE status = 'ACTIVE'"
        )
        refreshed = 0
        for org in orgs:
            org_id = str(org["id"])
            try:
                # Find the most recent academic year for this org
                year_rows = execute_system_query(
                    """
                    SELECT academic_year FROM course_enrollments
                    WHERE org_id = %s
                    ORDER BY academic_year DESC LIMIT 1
                    """,
                    (org_id,),
                )
                if not year_rows:
                    continue
                academic_year = year_rows[0]["academic_year"]
                from server.reporting.dashboard import DashboardService

                DashboardService.cache_snapshot(org_id, academic_year)
                refreshed += 1
            except Exception as exc:
                logger.warning("KPI snapshot failed for org %s: %s", org_id, exc)
        return {"status": "ok", "refreshed": refreshed}
    except Exception as exc:
        logger.error("reporting.refresh_kpi_snapshots failed: %s", exc)
        return {"status": "error", "error": str(exc)}
