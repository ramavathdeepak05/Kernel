"""E10-S04 — In-App Notifications"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class InAppNotificationService:
    @classmethod
    def send(
        cls,
        org_id: str,
        recipient_id: str,
        title: str,
        body: str,
        link: str | None = None,
    ) -> dict:
        nid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO in_app_notifications (id, org_id, recipient_id, title, body, link)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
                    (nid, org_id, recipient_id, title, body, link),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="send",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "send"},
        )
        return {"id": nid, "recipient_id": recipient_id, "title": title}

    @classmethod
    def list_for_user(
        cls,
        org_id: str,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        sql = """
            SELECT * FROM in_app_notifications
            WHERE org_id = %s AND recipient_id = %s
        """
        params: list = [org_id, user_id]
        if unread_only:
            sql += " AND is_read = FALSE"
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def mark_read(cls, org_id: str, user_id: str, notification_id: str) -> dict:
        execute_transaction(
            [
                (
                    """
            UPDATE in_app_notifications
            SET is_read = TRUE, read_at = NOW()
            WHERE id = %s AND recipient_id = %s AND org_id = %s
            """,
                    (notification_id, user_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="read",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "mark_read"},
        )
        rows = execute_query(
            "SELECT * FROM in_app_notifications WHERE id = %s AND org_id = %s",
            (notification_id, org_id),
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def mark_all_read(cls, org_id: str, user_id: str) -> dict:
        execute_transaction(
            [
                (
                    """
            UPDATE in_app_notifications
            SET is_read = TRUE, read_at = NOW()
            WHERE recipient_id = %s AND org_id = %s AND is_read = FALSE
            """,
                    (user_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="all_read",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "mark_all_read"},
        )
        return {"status": "ok"}

    @classmethod
    def unread_count(cls, org_id: str, user_id: str) -> int:
        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM in_app_notifications WHERE recipient_id = %s AND org_id = %s AND is_read = FALSE",
            (user_id, org_id),
        )
        return int(rows[0]["cnt"]) if rows else 0
