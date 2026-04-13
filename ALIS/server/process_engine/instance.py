"""E13-S03 — Process Instance tracker.

Handles launching, querying, cancelling, and resuming process instances.
"""

from __future__ import annotations

import builtins
import json
import logging
from typing import Any

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class ProcessInstanceService:
    @staticmethod
    def launch(
        org_id: str,
        process_id: str,
        triggered_by: str,
        context: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        trigger_event: str | None = None,
    ) -> dict[str, Any]:
        rows = execute_transaction(
            [
                (
                    """
            INSERT INTO process_instances
                (org_id, process_id, entity_type, entity_id, triggered_by,
                 trigger_event, context, status, current_step)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 'RUNNING', 1)
            RETURNING *
            """,
                    (
                        org_id,
                        process_id,
                        entity_type,
                        entity_id,
                        triggered_by,
                        trigger_event,
                        json.dumps(context or {}),
                    ),
                )
            ],
            tenant_id=org_id,
        )
        instance = dict(rows[0])

        # Immediately try to execute the first step
        from server.process_engine.executor import StepExecutor

        try:
            executor = StepExecutor(org_id, str(instance["id"]))
            result = executor.execute_current_step()
            instance["step_result"] = result
        except Exception as exc:
            logger.warning("Auto-execute first step failed on launch: %s", exc)

        return instance

    @staticmethod
    def get(org_id: str, instance_id: str) -> dict[str, Any] | None:
        rows = execute_query(
            "SELECT * FROM process_instances WHERE id = %s AND org_id = %s",
            (instance_id, org_id),
        )
        if not rows:
            return None
        instance = dict(rows[0])
        instance["step_logs"] = ProcessInstanceService.get_step_logs(
            org_id, instance_id
        )
        return instance

    @staticmethod
    def list(
        org_id: str,
        process_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[dict[str, Any]]:
        conditions = ["org_id = %s"]
        params: list = [org_id]
        if process_id:
            conditions.append("process_id = %s")
            params.append(process_id)
        if entity_type:
            conditions.append("entity_type = %s")
            params.append(entity_type)
        if entity_id:
            conditions.append("entity_id = %s")
            params.append(entity_id)
        if status:
            conditions.append("status = %s")
            params.append(status)
        where = "WHERE " + " AND ".join(conditions)
        rows = execute_query(
            f"SELECT * FROM process_instances {where} ORDER BY started_at DESC LIMIT %s OFFSET %s",  # noqa: S608
            params + [limit, offset],
        )
        return [dict(r) for r in rows]

    @staticmethod
    def cancel(org_id: str, instance_id: str) -> bool:
        execute_transaction(
            [
                (
                    """
            UPDATE process_instances
               SET status = 'CANCELLED', completed_at = NOW()
             WHERE id = %s AND org_id = %s AND status = 'RUNNING'
            """,
                    (instance_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="process_instance",
            entity_id="",
            tenant_id="",
            metadata={"source": "cancel"},
        )
        return True

    @staticmethod
    def resume(org_id: str, instance_id: str) -> dict[str, Any]:
        """Re-execute the current step (e.g. after form submission or approval)."""
        from server.process_engine.executor import StepExecutor

        executor = StepExecutor(org_id, instance_id)
        return executor.execute_current_step()

    @staticmethod
    def get_step_logs(org_id: str, instance_id: str) -> builtins.list[dict[str, Any]]:
        rows = execute_query(
            "SELECT * FROM process_step_logs WHERE instance_id = %s AND org_id = %s ORDER BY step_order",
            (instance_id, org_id),
        )
        return [dict(r) for r in rows]

    @staticmethod
    def submit_form(
        org_id: str,
        instance_id: str,
        step_id: str,
        submitted_by: str,
        form_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a form submission and resume the instance."""
        execute_transaction(
            [
                (
                    """
            INSERT INTO process_form_submissions
                (org_id, instance_id, step_id, submitted_by, form_data)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT DO NOTHING
            """,
                    (org_id, instance_id, step_id, submitted_by, json.dumps(form_data)),
                )
            ]
        )
        return ProcessInstanceService.resume(org_id, instance_id)
