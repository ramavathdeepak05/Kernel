"""E10-S01 — DB-backed Notification Template Management"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import TemplateCreate, TemplateUpdate

logger = logging.getLogger(__name__)


class NotifTemplateService:
    @classmethod
    def create(cls, org_id: str, req: TemplateCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM notification_templates WHERE org_id = %s AND key = %s AND channel = %s",
            (org_id, req.key, req.channel.value),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Template '{req.key}' for channel {req.channel.value} already exists"
            )

        tid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO notification_templates
                (id, org_id, key, name, subject, body, channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                    (
                        tid,
                        org_id,
                        req.key,
                        req.name,
                        req.subject,
                        req.body,
                        req.channel.value,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="notification_template",
            entity_id=tid,
            org_id=org_id,
            module="E10-S01",
            metadata={"key": req.key, "channel": req.channel.value},
        )
        return cls.get(org_id, tid)

    @classmethod
    def get(cls, org_id: str, template_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM notification_templates WHERE id = %s AND org_id = %s",
            (template_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Template {template_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, channel: str | None = None) -> list[dict]:
        sql = "SELECT * FROM notification_templates WHERE org_id = %s"
        params: list = [org_id]
        if channel:
            sql += " AND channel = %s"
            params.append(channel)
        sql += " ORDER BY key, channel"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def update(
        cls, org_id: str, template_id: str, req: TemplateUpdate, actor_id: str
    ) -> dict:
        cls.get(org_id, template_id)
        fields, params = [], []
        if req.name is not None:
            fields.append("name = %s")
            params.append(req.name)
        if req.subject is not None:
            fields.append("subject = %s")
            params.append(req.subject)
        if req.body is not None:
            fields.append("body = %s")
            params.append(req.body)
        if req.is_active is not None:
            fields.append("is_active = %s")
            params.append(req.is_active)
        if req.whatsapp_template_id is not None:
            fields.append("whatsapp_template_id = %s")
            params.append(req.whatsapp_template_id)
        if not fields:
            return cls.get(org_id, template_id)
        fields.append("updated_at = NOW()")
        params += [template_id, org_id]
        execute_transaction(
            [
                (
                    f"UPDATE notification_templates SET {', '.join(fields)} WHERE id = %s AND org_id = %s",  # noqa: S608
                    params,
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="update",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "update"},
        )
        return cls.get(org_id, template_id)

    @classmethod
    def resolve(
        cls, org_id: str, key: str, channel: str = "EMAIL"
    ) -> tuple[str, str] | None:
        """
        Look up template by key+channel. Returns (subject, body) or None.
        Falls back to hardcoded TemplateRegistry if not in DB.
        """
        rows = execute_query(
            """
            SELECT subject, body FROM notification_templates
            WHERE org_id = %s AND key = %s AND channel = %s AND is_active = TRUE
            """,
            (org_id, key, channel),
        )
        if rows:
            row = rows[0]
            return (row["subject"] or "", row["body"])

        # Fallback — check core TemplateRegistry (hardcoded defaults)
        try:
            from server.core.notifications.templates import TemplateRegistry

            subj, body = TemplateRegistry.render(key, {})
            return (subj, body)
        except Exception:
            return None
