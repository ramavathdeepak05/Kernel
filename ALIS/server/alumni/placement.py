"""E12-S02 — Placement Records"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import PlacementRecordCreate

logger = logging.getLogger(__name__)


class PlacementService:

    @classmethod
    def record(cls, org_id: str, req: PlacementRecordCreate, actor_id: str) -> dict:
        pid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO placement_records
                (id, org_id, student_id, academic_year, company_name, role,
                 package_lpa, placement_type, offer_date, joining_date,
                 location, is_ppo, recorded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pid, org_id, req.student_id, req.academic_year, req.company_name,
                req.role, req.package_lpa, req.placement_type.value,
                req.offer_date, req.joining_date, req.location, req.is_ppo, actor_id,
            ),
        )])

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="placement_record", entity_id=pid, org_id=org_id,
            module="E12-S02",
            metadata={
                "student_id": req.student_id, "company": req.company_name,
                "package_lpa": req.package_lpa,
            },
        )
        return cls.get(org_id, pid)

    @classmethod
    def get(cls, org_id: str, record_id: str) -> dict:
        rows = execute_query(
            """
            SELECT pr.*, s.name AS student_name, s.roll_number
            FROM placement_records pr
            JOIN students s ON s.id = pr.student_id
            WHERE pr.id = %s AND pr.org_id = %s
            """,
            (record_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Placement record {record_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        academic_year: str | None = None,
        placement_type: str | None = None,
        company_name: str | None = None,
    ) -> list[dict]:
        sql = """
            SELECT pr.*, s.name AS student_name, s.roll_number, s.program
            FROM placement_records pr
            JOIN students s ON s.id = pr.student_id
            WHERE pr.org_id = %s
        """
        params: list = [org_id]
        if academic_year:
            sql += " AND pr.academic_year = %s"; params.append(academic_year)
        if placement_type:
            sql += " AND pr.placement_type = %s"; params.append(placement_type)
        if company_name:
            sql += " AND pr.company_name ILIKE %s"; params.append(f"%{company_name}%")
        sql += " ORDER BY pr.created_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def student_records(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM placement_records WHERE student_id = %s AND org_id = %s ORDER BY created_at DESC",
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def statistics(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(DISTINCT student_id)                          AS students_placed,
                COUNT(*)                                            AS total_offers,
                ROUND(AVG(package_lpa), 2)                         AS avg_package_lpa,
                ROUND(MAX(package_lpa), 2)                         AS highest_package_lpa,
                ROUND(MIN(package_lpa), 2)                         AS lowest_package_lpa,
                COUNT(*) FILTER (WHERE placement_type = 'CAMPUS')  AS campus_placements,
                COUNT(*) FILTER (WHERE placement_type = 'OFF_CAMPUS') AS off_campus,
                COUNT(*) FILTER (WHERE is_ppo = TRUE)              AS ppos
            FROM placement_records
            WHERE org_id = %s AND academic_year = %s
            """,
            (org_id, academic_year),
        )
        stats = dict(rows[0]) if rows else {}

        # Company-wise breakdown
        company_rows = execute_query(
            """
            SELECT company_name, COUNT(*) AS offers,
                   ROUND(AVG(package_lpa), 2) AS avg_package
            FROM placement_records
            WHERE org_id = %s AND academic_year = %s
            GROUP BY company_name
            ORDER BY offers DESC
            LIMIT 20
            """,
            (org_id, academic_year),
        )
        stats["top_companies"] = [dict(r) for r in company_rows]
        stats["academic_year"] = academic_year
        return stats
