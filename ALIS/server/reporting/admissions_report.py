"""E11-S02 — Admissions Reports"""
from __future__ import annotations

import logging
from server.db_service import execute_query

logger = logging.getLogger(__name__)


class AdmissionsReportService:

    @classmethod
    def funnel(cls, org_id: str, academic_year: str) -> dict:
        """Admission funnel: applied → reviewed → offered → paid → enrolled."""
        rows = execute_query(
            """
            SELECT status, COUNT(*) AS count
            FROM applicants
            WHERE org_id = %s AND academic_year = %s
            GROUP BY status
            ORDER BY status
            """,
            (org_id, academic_year),
        )
        by_status = {r["status"]: int(r["count"]) for r in rows}
        total = sum(by_status.values())

        stages = [
            ("Applied",       total),
            ("Under Review",  by_status.get("DOCUMENT_REVIEW", 0) + by_status.get("POLICY_EVAL", 0)),
            ("Offered",       by_status.get("OFFER_ISSUED", 0)),
            ("Fee Paid",      by_status.get("PAYMENT_CONFIRMED", 0)),
            ("Enrolled",      by_status.get("ENROLLED", 0)),
        ]
        return {
            "academic_year": academic_year,
            "total":         total,
            "by_status":     by_status,
            "funnel":        [{"stage": s, "count": c} for s, c in stages],
        }

    @classmethod
    def program_wise(cls, org_id: str, academic_year: str) -> list[dict]:
        """Application and enrollment count per program."""
        rows = execute_query(
            """
            SELECT
                a.program_applied AS program,
                COUNT(*)                                        AS applications,
                COUNT(*) FILTER (WHERE a.status = 'ENROLLED')  AS enrolled,
                COUNT(*) FILTER (WHERE a.status IN ('REJECTED','AUTO_REJECTED')) AS rejected
            FROM applicants a
            WHERE a.org_id = %s AND a.academic_year = %s
            GROUP BY a.program_applied
            ORDER BY applications DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def source_analysis(cls, org_id: str, academic_year: str) -> list[dict]:
        """Applications by source channel (if tracked)."""
        rows = execute_query(
            """
            SELECT
                COALESCE(source_channel, 'DIRECT') AS source,
                COUNT(*) AS count
            FROM applicants
            WHERE org_id = %s AND academic_year = %s
            GROUP BY source_channel
            ORDER BY count DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def counsellor_performance(cls, org_id: str, academic_year: str) -> list[dict]:
        """Conversion rate by assigned counsellor."""
        rows = execute_query(
            """
            SELECT
                c.name AS counsellor,
                COUNT(a.id)                                         AS assigned,
                COUNT(*) FILTER (WHERE a.status = 'ENROLLED')       AS enrolled,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE a.status = 'ENROLLED') /
                    NULLIF(COUNT(a.id), 0), 1
                )                                                    AS conversion_rate
            FROM applicants a
            JOIN counsellors c ON c.id = a.assigned_counsellor_id
            WHERE a.org_id = %s AND a.academic_year = %s
            GROUP BY c.id, c.name
            ORDER BY enrolled DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def monthly_trend(cls, org_id: str, academic_year: str) -> list[dict]:
        """Applications received per month."""
        rows = execute_query(
            """
            SELECT
                TO_CHAR(submitted_at, 'YYYY-MM') AS month,
                COUNT(*) AS count
            FROM applicants
            WHERE org_id = %s AND academic_year = %s
            GROUP BY 1
            ORDER BY 1
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]
