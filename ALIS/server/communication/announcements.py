"""E10-S05 — Announcements"""
from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import AnnouncementCreate

logger = logging.getLogger(__name__)


class AnnouncementService:

    @classmethod
    def create(cls, org_id: str, req: AnnouncementCreate, actor_id: str) -> dict:
        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO announcements
                (id, org_id, title, body, target_audience, priority, expires_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                aid, org_id, req.title, req.body,
                req.target_audience.value, req.priority.value,
                req.expires_at, actor_id,
            ),
        )])

        # Also create an in-app notification for all affected users (fan-out via Celery task)
        try:
            from server.tasks.notifications import task_fanout_announcement
            task_fanout_announcement.delay(org_id, aid)
        except Exception as exc:
            logger.warning("Announcement: fanout task queue failed (non-fatal): %s", exc)

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="announcement", entity_id=aid, org_id=org_id,
            module="E10-S05", metadata={"title": req.title, "audience": req.target_audience.value},
        )
        return cls.get(org_id, aid)

    @classmethod
    def get(cls, org_id: str, announcement_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM announcements WHERE id = %s AND org_id = %s",
            (announcement_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Announcement {announcement_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        audience: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict]:
        sql = """
            SELECT * FROM announcements
            WHERE org_id = %s
        """
        params: list = [org_id]
        if active_only:
            sql += " AND is_active = TRUE AND (expires_at IS NULL OR expires_at > NOW())"
        if audience and audience != "ALL":
            sql += " AND (target_audience = %s OR target_audience = 'ALL')"
            params.append(audience)
        sql += " ORDER BY priority DESC, published_at DESC LIMIT %s"
        params.append(limit)
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def mark_read(cls, org_id: str, announcement_id: str, user_id: str) -> dict:
        cls.get(org_id, announcement_id)
        execute_transaction([(
            """
            INSERT INTO announcement_reads (id, announcement_id, user_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (announcement_id, user_id) DO NOTHING
            """,
            (str(uuid.uuid4()), announcement_id, user_id),
        )])
        return {"status": "ok"}

    @classmethod
    def deactivate(cls, org_id: str, announcement_id: str, actor_id: str) -> dict:
        cls.get(org_id, announcement_id)
        execute_transaction([(
            "UPDATE announcements SET is_active = FALSE WHERE id = %s AND org_id = %s",
            (announcement_id, org_id),
        )])
        return {"status": "deactivated", "id": announcement_id}

    @classmethod
    def get_recipients(cls, org_id: str, announcement_id: str) -> list[str]:
        """
        Return user_ids of users who match the announcement's target audience.
        Used by the fanout task to create in-app notifications.
        """
        rows = execute_query(
            "SELECT target_audience FROM announcements WHERE id = %s AND org_id = %s",
            (announcement_id, org_id),
        )
        if not rows:
            return []
        audience = rows[0]["target_audience"]

        if audience == "ALL":
            user_rows = execute_query(
                "SELECT id FROM users WHERE org_id = %s AND status = 'ACTIVE'", (org_id,)
            )
        elif audience == "STUDENTS":
            user_rows = execute_query(
                "SELECT id FROM students WHERE org_id = %s AND status = 'ENROLLED'", (org_id,)
            )
        elif audience in ("STAFF", "FACULTY"):
            user_rows = execute_query(
                "SELECT id FROM users WHERE org_id = %s AND status = 'ACTIVE' AND role = %s",
                (org_id, audience),
            )
        else:
            user_rows = []

        return [str(r["id"]) for r in user_rows]
