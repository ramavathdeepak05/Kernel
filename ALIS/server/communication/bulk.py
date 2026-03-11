"""E10-S07 — Bulk Messaging"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import BulkMessageCreate

logger = logging.getLogger(__name__)


class BulkMessagingService:

    @classmethod
    def create_job(cls, org_id: str, req: BulkMessageCreate, actor_id: str) -> dict:
        """Create a bulk message job and enqueue it for async processing."""
        # Count targets
        recipients = cls._resolve_targets(org_id, req.target_filter)
        job_id = str(uuid.uuid4())

        execute_transaction([(
            """
            INSERT INTO bulk_message_jobs
                (id, org_id, title, message, channel, target_filter, recipient_count,
                 status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 'QUEUED', %s)
            """,
            (
                job_id, org_id, req.title, req.message, req.channel.value,
                __import__('json').dumps(req.target_filter),
                len(recipients), actor_id,
            ),
        )])

        # Enqueue Celery task
        try:
            from server.tasks.notifications import task_process_bulk_message
            task_process_bulk_message.delay(org_id, job_id)
        except Exception as exc:
            logger.warning("BulkMessage: enqueue failed (non-fatal): %s", exc)

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="bulk_message_job", entity_id=job_id, org_id=org_id,
            module="E10-S07",
            metadata={"channel": req.channel.value, "recipients": len(recipients)},
        )

        return cls.get(org_id, job_id)

    @classmethod
    def get(cls, org_id: str, job_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM bulk_message_jobs WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Bulk message job {job_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, limit: int = 20) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM bulk_message_jobs WHERE org_id = %s ORDER BY created_at DESC LIMIT %s",
            (org_id, limit),
        )
        return [dict(r) for r in rows]

    @classmethod
    def _resolve_targets(cls, org_id: str, target_filter: dict) -> list[str]:
        """Resolve target_filter into a list of user_ids."""
        role = target_filter.get("role")
        program_id = target_filter.get("program_id")
        academic_year = target_filter.get("academic_year")
        semester = target_filter.get("semester")

        if role == "STUDENT" or (not role and (program_id or academic_year)):
            sql = "SELECT DISTINCT s.id FROM students s WHERE s.org_id = %s AND s.status = 'ENROLLED'"
            params: list = [org_id]
            if program_id:
                sql += " AND s.program_id = %s"; params.append(program_id)
            if academic_year:
                sql += """ AND EXISTS (
                    SELECT 1 FROM course_enrollments ce
                    WHERE ce.student_id = s.id AND ce.academic_year = %s
                    """
                params.append(academic_year)
                if semester:
                    sql += " AND ce.semester = %s"; params.append(semester)
                sql += ")"
            rows = execute_query(sql, params)
        elif role:
            rows = execute_query(
                "SELECT id FROM users WHERE org_id = %s AND role = %s AND status = 'ACTIVE'",
                (org_id, role.upper()),
            )
        else:
            rows = execute_query(
                "SELECT id FROM users WHERE org_id = %s AND status = 'ACTIVE'",
                (org_id,),
            )

        return [str(r["id"]) for r in rows]

    @classmethod
    def process_job(cls, org_id: str, job_id: str) -> None:
        """
        Called by Celery task. Sends the bulk message to all resolved targets.
        Updates job status and counters as it goes.
        """
        job_rows = execute_query(
            "SELECT * FROM bulk_message_jobs WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )
        if not job_rows:
            return
        job = dict(job_rows[0])

        if job["status"] != "QUEUED":
            return  # already running or done

        execute_transaction([(
            "UPDATE bulk_message_jobs SET status = 'RUNNING' WHERE id = %s",
            (job_id,),
        )])

        import json
        target_filter = job["target_filter"]
        if isinstance(target_filter, str):
            target_filter = json.loads(target_filter)

        targets = cls._resolve_targets(org_id, target_filter)
        sent = failed = 0
        channel = job["channel"]

        for user_id in targets:
            try:
                if channel == "IN_APP":
                    from .in_app import InAppNotificationService
                    InAppNotificationService.send(
                        org_id=org_id,
                        recipient_id=user_id,
                        title=job["title"],
                        body=job["message"],
                    )
                else:
                    # EMAIL / SMS — look up user's email/phone
                    user_rows = execute_query(
                        "SELECT email FROM users WHERE id = %s", (user_id,)
                    )
                    if not user_rows:
                        failed += 1
                        continue
                    addr = user_rows[0]["email"]
                    from server.core.notifications.service import NotificationDispatcher
                    NotificationDispatcher.dispatch(
                        template_key="_bulk_direct",
                        recipient_id=user_id,
                        recipient_email=addr,
                        context={"title": job["title"], "message": job["message"]},
                        org_id=org_id,
                        _subject_override=job["title"],
                        _body_override=job["message"],
                    )
                sent += 1
            except Exception as exc:
                logger.warning("BulkMessage: send failed for user %s: %s", user_id, exc)
                failed += 1

        execute_transaction([(
            """
            UPDATE bulk_message_jobs
            SET status = 'DONE', sent_count = %s, failed_count = %s, completed_at = NOW()
            WHERE id = %s
            """,
            (sent, failed, job_id),
        )])
        logger.info("BulkMessage job %s: sent=%d failed=%d", job_id, sent, failed)
