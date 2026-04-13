"""E07-S01 — Fee Structure Management"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import FeeStructureCreate

logger = logging.getLogger(__name__)


class FeeStructureService:
    @classmethod
    def create(cls, org_id: str, req: FeeStructureCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM fee_structures WHERE org_id = %s AND program_id IS NOT DISTINCT FROM %s AND academic_year = %s AND semester IS NOT DISTINCT FROM %s",
            (org_id, req.program_id, req.academic_year, req.semester),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Fee structure already exists for program={req.program_id} year={req.academic_year} sem={req.semester}"
            )

        fee_items = [item.model_dump() for item in req.fee_items]
        total = sum(item["amount"] for item in fee_items if not item["is_optional"])

        sid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO fee_structures
                (id, org_id, program_id, academic_year, semester, fee_items, total_amount, currency, created_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
                    (
                        sid,
                        org_id,
                        req.program_id,
                        req.academic_year,
                        req.semester,
                        __import__("json").dumps(fee_items),
                        total,
                        req.currency,
                        actor_id,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="fee_structure",
            entity_id=sid,
            org_id=org_id,
            module="E07-S01",
            metadata={"academic_year": req.academic_year, "total": total},
        )

        return cls.get(org_id, sid)

    @classmethod
    def get(cls, org_id: str, structure_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM fee_structures WHERE id = %s AND org_id = %s",
            (structure_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Fee structure {structure_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls, org_id: str, academic_year: str, program_id: str | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM fee_structures WHERE org_id = %s AND academic_year = %s AND is_active = TRUE"
        params: list = [org_id, academic_year]
        if program_id:
            sql += " AND (program_id = %s OR program_id IS NULL)"
            params.append(program_id)
        sql += " ORDER BY created_at"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def deactivate(cls, org_id: str, structure_id: str, actor_id: str) -> dict:
        cls.get(org_id, structure_id)
        execute_transaction(
            [
                (
                    "UPDATE fee_structures SET is_active = FALSE WHERE id = %s AND org_id = %s",
                    (structure_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="fee_structure",
            entity_id=structure_id,
            org_id=org_id,
            module="E07-S01",
            metadata={"action": "deactivate"},
        )
        return cls.get(org_id, structure_id)
