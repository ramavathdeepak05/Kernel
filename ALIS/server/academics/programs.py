"""E05-S01 — Program Management"""
from __future__ import annotations

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import ProgramCreate

logger = logging.getLogger(__name__)


class ProgramService:

    @classmethod
    def create(cls, org_id: str, req: ProgramCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM programs WHERE org_id = %s AND code = %s",
            (org_id, req.code),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Program code '{req.code}' already exists")

        pid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO programs (id, org_id, name, code, degree_type, duration_years, total_credits, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (pid, org_id, req.name, req.code, req.degree_type.value,
             req.duration_years, req.total_credits, json.dumps(req.metadata)),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="program", entity_id=pid, org_id=org_id, module="E05-S01",
                     metadata={"name": req.name, "code": req.code})

        return cls.get(org_id, pid)

    @classmethod
    def get(cls, org_id: str, program_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM programs WHERE id = %s AND org_id = %s", (program_id, org_id)
        )
        if not rows:
            raise NotFoundError(f"Program {program_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, status: str = "ACTIVE") -> list[dict]:
        rows = execute_query(
            "SELECT * FROM programs WHERE org_id = %s AND status = %s ORDER BY name",
            (org_id, status),
        )
        return [dict(r) for r in rows]

    @classmethod
    def update(cls, org_id: str, program_id: str, updates: dict, actor_id: str) -> dict:
        cls.get(org_id, program_id)  # ensures exists
        allowed = {"name", "total_credits", "status", "metadata"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            raise BusinessRuleViolation(message="No updatable fields provided")

        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [program_id, org_id]
        execute_transaction([(
            f"UPDATE programs SET {set_clause}, updated_at = NOW() WHERE id = %s AND org_id = %s",
            values,
        )])

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="program", entity_id=program_id, org_id=org_id,
                     module="E05-S01", metadata={"updated_fields": list(fields.keys())})
        return cls.get(org_id, program_id)
