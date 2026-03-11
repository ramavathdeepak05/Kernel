"""E11-S04 — Financial Reports (cross-cutting, complements E07 finance module)

E07 has module-scoped reports (collection summary, defaulters, etc.).
E11 adds institution-wide financial analytics, trend reports, and
reconciliation views that span multiple academic years.
"""

import logging
from server.db_service import execute_query

logger = logging.getLogger(__name__)


class FinanceReportService:

    @classmethod
    def year_over_year(cls, org_id: str, years: list[str]) -> list[dict]:
        """Compare total billed, collected, and outstanding across academic years."""
        if not years:
            return []
        placeholders = ", ".join(["%s"] * len(years))
        rows = execute_query(
            f"""
            SELECT
                academic_year,
                SUM(total_amount)       AS total_billed,
                SUM(amount_paid)        AS total_collected,
                SUM(total_amount - amount_paid)
                    FILTER (WHERE status != 'PAID')  AS outstanding,
                COUNT(*) FILTER (WHERE status = 'OVERDUE') AS overdue_invoices
            FROM fee_invoices
            WHERE org_id = %s AND academic_year IN ({placeholders})
            GROUP BY academic_year
            ORDER BY academic_year
            """,
            [org_id] + years,
        )
        return [dict(r) for r in rows]

    @classmethod
    def scholarship_budget(cls, org_id: str, academic_year: str) -> dict:
        """Total scholarship value disbursed vs tuition billed."""
        scholar_rows = execute_query(
            """
            SELECT
                s.type,
                COUNT(sa.id)                    AS recipients,
                SUM(
                    CASE s.discount_type
                        WHEN 'PERCENTAGE' THEN fi.total_amount * s.discount_value / 100
                        ELSE s.discount_value
                    END
                ) AS total_discount_value
            FROM scholarship_assignments sa
            JOIN scholarships s ON s.id = sa.scholarship_id
            JOIN fee_invoices fi ON fi.student_id = sa.student_id
                AND fi.academic_year = sa.academic_year
            WHERE sa.org_id = %s AND sa.academic_year = %s
            GROUP BY s.type
            """,
            (org_id, academic_year),
        )
        tuition_rows = execute_query(
            "SELECT SUM(total_amount) AS total FROM fee_invoices WHERE org_id = %s AND academic_year = %s",
            (org_id, academic_year),
        )
        return {
            "academic_year":  academic_year,
            "total_billed":   float(tuition_rows[0]["total"] or 0) if tuition_rows else 0,
            "by_scholarship_type": [dict(r) for r in scholar_rows],
        }

    @classmethod
    def payment_aging(cls, org_id: str, academic_year: str) -> list[dict]:
        """
        Outstanding invoices bucketed by how overdue they are.
        Buckets: Current, 1–30d, 31–60d, 61–90d, 90d+
        """
        rows = execute_query(
            """
            SELECT
                CASE
                    WHEN due_date >= CURRENT_DATE THEN 'Current'
                    WHEN due_date >= CURRENT_DATE - 30 THEN '1-30 days'
                    WHEN due_date >= CURRENT_DATE - 60 THEN '31-60 days'
                    WHEN due_date >= CURRENT_DATE - 90 THEN '61-90 days'
                    ELSE '90+ days'
                END AS aging_bucket,
                COUNT(*) AS invoices,
                SUM(total_amount - amount_paid) AS outstanding_amount
            FROM fee_invoices
            WHERE org_id = %s AND academic_year = %s AND status != 'PAID'
            GROUP BY 1
            ORDER BY
                CASE
                    WHEN due_date >= CURRENT_DATE THEN 0
                    WHEN due_date >= CURRENT_DATE - 30 THEN 1
                    WHEN due_date >= CURRENT_DATE - 60 THEN 2
                    WHEN due_date >= CURRENT_DATE - 90 THEN 3
                    ELSE 4
                END
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def revenue_by_fee_type(cls, org_id: str, academic_year: str) -> list[dict]:
        """Revenue breakdown by fee type (tuition, hostel, exam, etc.)."""
        rows = execute_query(
            """
            SELECT
                fii.fee_type,
                SUM(fii.amount)                                         AS billed,
                SUM(fii.amount * fi.amount_paid / NULLIF(fi.total_amount, 0)) AS collected_est
            FROM fee_invoice_items fii
            JOIN fee_invoices fi ON fi.id = fii.invoice_id
            WHERE fi.org_id = %s AND fi.academic_year = %s
            GROUP BY fii.fee_type
            ORDER BY billed DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def waiver_impact(cls, org_id: str, academic_year: str) -> dict:
        """Total waiver amount approved vs total billed."""
        rows = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE fw.status = 'APPROVED')          AS approved_waivers,
                SUM(fw.waiver_amount) FILTER (WHERE fw.status = 'APPROVED') AS total_waived,
                COUNT(*) FILTER (WHERE fw.status = 'REJECTED')          AS rejected_waivers
            FROM fee_waivers fw
            JOIN fee_invoices fi ON fi.id = fw.invoice_id
            WHERE fi.org_id = %s AND fi.academic_year = %s
            """,
            (org_id, academic_year),
        )
        return dict(rows[0]) if rows else {}
