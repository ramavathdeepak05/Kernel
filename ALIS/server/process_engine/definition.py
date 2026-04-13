"""E13-S01 — Process Definition CRUD service."""

from __future__ import annotations

import builtins
from typing import Any

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction


class ProcessDefinitionService:
    @staticmethod
    def create(org_id: str, created_by: str, data: dict[str, Any]) -> dict[str, Any]:
        steps = data.pop("steps", [])
        rows = execute_transaction(
            [
                (
                    """
            INSERT INTO process_definitions
                (org_id, name, description, trigger_event, trigger_filter, context_schema, created_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING *
            """,
                    (
                        org_id,
                        data["name"],
                        data.get("description"),
                        data.get("trigger_event"),
                        __import__("json").dumps(data.get("trigger_filter", {})),
                        __import__("json").dumps(data.get("context_schema", {})),
                        created_by,
                    ),
                )
            ],
            tenant_id=org_id,
        )
        defn = dict(rows[0])

        # Insert steps
        if steps:
            ProcessDefinitionService._upsert_steps(org_id, defn["id"], steps)

        return defn

    @staticmethod
    def _upsert_steps(
        org_id: str, process_id: str, steps: builtins.list[dict[str, Any]]
    ) -> None:
        import json

        ops = []
        for i, step in enumerate(steps, start=1):
            ops.append(
                (
                    """
                INSERT INTO process_steps
                    (org_id, process_id, step_order, name, step_type, config,
                     on_pass_step, on_fail_step, is_required)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                    (
                        org_id,
                        process_id,
                        i,
                        step["name"],
                        step["step_type"],
                        json.dumps(step.get("config", {})),
                        step.get("on_pass_step"),
                        step.get("on_fail_step"),
                        step.get("is_required", True),
                    ),
                )
            )
        execute_transaction(ops)
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="process_definition",
            entity_id="",
            tenant_id="",
            metadata={"source": "_upsert_steps"},
        )

    @staticmethod
    def get(org_id: str, process_id: str) -> dict[str, Any] | None:
        rows = execute_query(
            "SELECT * FROM process_definitions WHERE id = %s AND org_id = %s",
            (process_id, org_id),
        )
        if not rows:
            return None
        defn = dict(rows[0])
        defn["steps"] = ProcessDefinitionService.get_steps(org_id, process_id)
        return defn

    @staticmethod
    def get_steps(org_id: str, process_id: str) -> builtins.list[dict[str, Any]]:
        rows = execute_query(
            "SELECT * FROM process_steps WHERE process_id = %s AND org_id = %s ORDER BY step_order",
            (process_id, org_id),
        )
        return [dict(r) for r in rows]

    @staticmethod
    def list(
        org_id: str, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> builtins.list[dict[str, Any]]:
        where = "WHERE org_id = %s"
        params: list = [org_id]
        if active_only:
            where += " AND is_active = TRUE"
        rows = execute_query(
            f"SELECT * FROM process_definitions {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",  # noqa: S608
            params + [limit, offset],
        )
        return [dict(r) for r in rows]

    @staticmethod
    def update(
        org_id: str, process_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        sets, params = [], []
        for col in (
            "name",
            "description",
            "trigger_event",
            "trigger_filter",
            "is_active",
        ):
            if col in data and data[col] is not None:
                if col in ("trigger_filter",):
                    sets.append(f"{col} = %s::jsonb")
                    params.append(__import__("json").dumps(data[col]))
                else:
                    sets.append(f"{col} = %s")
                    params.append(data[col])
        if not sets:
            return ProcessDefinitionService.get(org_id, process_id)
        sets.append("updated_at = NOW()")
        params += [process_id, org_id]
        execute_transaction(
            [
                (
                    f"UPDATE process_definitions SET {', '.join(sets)} WHERE id = %s AND org_id = %s",  # noqa: S608
                    params,
                )
            ]
        )
        return ProcessDefinitionService.get(org_id, process_id)

    @staticmethod
    def delete(org_id: str, process_id: str) -> bool:
        execute_transaction(
            [
                (
                    "UPDATE process_definitions SET is_active = FALSE, updated_at = NOW() WHERE id = %s AND org_id = %s",
                    (process_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.DELETE,
            actor_id="system",
            actor_role="system",
            entity_type="process_definition",
            entity_id="",
            tenant_id="",
            metadata={"source": "delete"},
        )
        return True

    @staticmethod
    def find_by_event(event_name: str) -> builtins.list[dict[str, Any]]:
        """Return all active process definitions that subscribe to a domain event."""
        rows = execute_query(
            "SELECT * FROM process_definitions WHERE trigger_event = %s AND is_active = TRUE",
            (event_name,),
        )
        return [dict(r) for r in rows]
