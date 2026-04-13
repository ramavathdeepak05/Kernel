"""E07-S07 — Financial Reports

Reports:
1. Collection summary — total billed vs collected vs outstanding per academic year
2. Defaulters list — students with OVERDUE invoices
3. Payment method breakdown — cash/cheque/razorpay/etc.
4. Scholarship impact — total discounts granted
5. Program-wise revenue breakdown
"""

from __future__ import annotations

import logging

from server.db_service import execute_query

logger = logging.getLogger(__name__)


class FinanceReportService:
    @classmethod
    def collection_summary(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                            AS total_invoices,
                ROUND(SUM(amount_due), 2)                          AS total_billed,
                ROUND(SUM(amount_paid), 2)                         AS total_collected,
                ROUND(SUM(discount), 2)                            AS total_discounts,
                ROUND(SUM(balance), 2)                             AS total_outstanding,
                COUNT(*) FILTER (WHERE status = 'PAID')            AS paid_count,
                COUNT(*) FILTER (WHERE status = 'PARTIAL')         AS partial_count,
                COUNT(*) FILTER (WHERE status = 'OVERDUE')         AS overdue_count,
                COUNT(*) FILTER (WHERE status = 'UNPAID')          AS unpaid_count
            FROM student_invoices
            WHERE org_id = %s AND academic_year = %s
            """,
            (org_id, academic_year),
        )
        summary = dict(rows[0]) if rows else {}

        # Collection rate
        billed = float(summary.get("total_billed") or 0)
        collected = float(summary.get("total_collected") or 0)
        summary["collection_rate"] = (
            round((collected / billed * 100), 1) if billed > 0 else 0.0
        )

        return summary

    @classmethod
    def defaulters_list(cls, org_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                s.id AS student_id, s.name, s.roll_number, s.email, s.program,
                si.id AS invoice_id, si.invoice_number, si.amount_due,
                si.amount_paid, si.balance, si.due_date, si.status
            FROM student_invoices si
            JOIN students s ON s.id = si.student_id
            WHERE si.org_id = %s AND si.academic_year = %s
              AND si.status IN ('OVERDUE', 'UNPAID')
              AND si.due_date < CURRENT_DATE
            ORDER BY si.balance DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def payment_method_breakdown(cls, org_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                p.method,
                COUNT(*) AS transaction_count,
                ROUND(SUM(p.amount), 2) AS total_amount
            FROM payments p
            JOIN student_invoices si ON si.id = p.invoice_id
            WHERE p.org_id = %s AND si.academic_year = %s AND p.status = 'CAPTURED'
            GROUP BY p.method
            ORDER BY total_amount DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def scholarship_impact(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                s.name AS scholarship_name, s.type,
                COUNT(sa.id) AS recipients,
                ROUND(SUM(sa.amount_applied), 2) AS total_discount_applied
            FROM scholarship_assignments sa
            JOIN scholarships s ON s.id = sa.scholarship_id
            WHERE sa.org_id = %s AND sa.academic_year = %s AND sa.status = 'ACTIVE'
            GROUP BY s.id, s.name, s.type
            ORDER BY total_discount_applied DESC
            """,
            (org_id, academic_year),
        )
        breakdown = [dict(r) for r in rows]

        total_rows = execute_query(
            """
            SELECT ROUND(SUM(sa.amount_applied), 2) AS total
            FROM scholarship_assignments sa
            WHERE sa.org_id = %s AND sa.academic_year = %s AND sa.status = 'ACTIVE'
            """,
            (org_id, academic_year),
        )
        total = float(total_rows[0]["total"] or 0) if total_rows else 0.0

        return {"total_discount_granted": total, "breakdown": breakdown}

    @classmethod
    def program_wise_revenue(cls, org_id: str, academic_year: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                p.name AS program_name, p.code AS program_code,
                COUNT(si.id) AS invoice_count,
                ROUND(SUM(si.amount_due), 2) AS total_billed,
                ROUND(SUM(si.amount_paid), 2) AS total_collected,
                ROUND(SUM(si.balance), 2) AS outstanding
            FROM student_invoices si
            JOIN fee_structures fs ON fs.id = si.fee_structure_id
            JOIN programs p ON p.id = fs.program_id
            WHERE si.org_id = %s AND si.academic_year = %s
            GROUP BY p.id, p.name, p.code
            ORDER BY total_billed DESC
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]

    @classmethod
    def monthly_collection(cls, org_id: str, academic_year: str) -> list[dict]:
        """Month-by-month payment collection for the academic year."""
        rows = execute_query(
            """
            SELECT
                DATE_TRUNC('month', p.recorded_at) AS month,
                COUNT(*) AS transactions,
                ROUND(SUM(p.amount), 2) AS collected
            FROM payments p
            JOIN student_invoices si ON si.id = p.invoice_id
            WHERE p.org_id = %s AND si.academic_year = %s AND p.status = 'CAPTURED'
            GROUP BY 1
            ORDER BY 1
            """,
            (org_id, academic_year),
        )
        return [dict(r) for r in rows]
