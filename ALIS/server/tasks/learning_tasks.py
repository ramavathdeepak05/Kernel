"""
Learning Module Celery Tasks — P40

close_overdue_assignments: Hourly beat task that transitions PUBLISHED
  assignments past their due_date (+ max_late_days grace) to CLOSED.
"""
from __future__ import annotations

import logging
from datetime import timezone

from server.worker import celery_app
from server.db_service import execute_system_query

logger = logging.getLogger(__name__)


@celery_app.task(
    name="server.tasks.learning_tasks.close_overdue_assignments",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def close_overdue_assignments(self) -> dict:
    """
    Find all PUBLISHED assignments where:
      - allow_late=FALSE and due_date < NOW(), OR
      - allow_late=TRUE and due_date + max_late_days < NOW()

    Transition each to CLOSED via AssignmentService.close_assignment().
    Uses system queries (bypasses RLS) because this runs in Celery context.
    """
    try:
        rows = execute_system_query(
            """
            SELECT a.id, a.org_id, a.title,
                   a.due_date, a.allow_late,
                   COALESCE(
                       (SELECT value::int FROM institution_policies
                        WHERE org_id=a.org_id
                          AND key='learning.assignment.max_late_days'
                          AND is_active=TRUE
                        LIMIT 1),
                       3
                   ) AS max_late_days
            FROM assignments a
            WHERE a.status = 'PUBLISHED'
              AND (
                  (a.allow_late = FALSE AND a.due_date < NOW())
                  OR
                  (a.allow_late = TRUE
                   AND a.due_date + (
                       COALESCE(
                           (SELECT value::int FROM institution_policies
                            WHERE org_id=a.org_id
                              AND key='learning.assignment.max_late_days'
                              AND is_active=TRUE
                            LIMIT 1),
                           3
                       ) * INTERVAL '1 day'
                   ) < NOW())
              )
            """,
            (),
        )

        closed_count = 0
        for row in rows:
            try:
                from server.academics.learning_service import AssignmentService
                from server.core.security import _current_tenant_id as _tid_var
                token = _tid_var.set(str(row["org_id"]))
                try:
                    AssignmentService.close_assignment(
                        org_id=str(row["org_id"]),
                        assignment_id=str(row["id"]),
                        actor_id="system",
                    )
                    closed_count += 1
                    logger.info(
                        "close_overdue_assignments: closed assignment %s (%s)",
                        row["id"], row["title"],
                    )
                finally:
                    _tid_var.reset(token)
            except Exception as e:
                logger.error(
                    "close_overdue_assignments: failed to close %s — %s", row["id"], e
                )

        return {"closed": closed_count}

    except Exception as exc:
        logger.error("close_overdue_assignments: task failed — %s", exc)
        raise self.retry(exc=exc)
