"""E11-S01 — Dashboard KPI API

Live aggregate KPIs for the institution dashboard.
Expensive queries are cached in kpi_snapshots (refreshed by Celery beat).
"""
from __future__ import annotations

import logging
from datetime import date

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class DashboardService:

    # ------------------------------------------------------------------
    # Top-level KPI bundle
    # ------------------------------------------------------------------

    @classmethod
    def get_kpis(cls, org_id: str, academic_year: str) -> dict:
        """
        Returns all institution-level KPIs in one call.
        Used by the main dashboard page.
        """
        return {
            "academic_year": academic_year,
            "admissions":    cls._admissions_kpis(org_id, academic_year),
            "academics":     cls._academics_kpis(org_id, academic_year),
            "finance":       cls._finance_kpis(org_id, academic_year),
            "examinations":  cls._exam_kpis(org_id, academic_year),
            "hr":            cls._hr_kpis(org_id),
            "services":      cls._services_kpis(org_id),
        }

    # ------------------------------------------------------------------
    # Admissions KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _admissions_kpis(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                                    AS total_applications,
                COUNT(*) FILTER (WHERE status = 'ENROLLED')                AS enrolled,
                COUNT(*) FILTER (WHERE status = 'OFFER_ISSUED')            AS offers_pending,
                COUNT(*) FILTER (WHERE status = 'DOCUMENT_REVIEW')         AS under_review,
                COUNT(*) FILTER (WHERE status IN ('REJECTED','AUTO_REJECTED')) AS rejected,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE status = 'ENROLLED') /
                    NULLIF(COUNT(*), 0), 1
                )                                                           AS conversion_rate
            FROM applicants
            WHERE org_id = %s AND academic_year = %s
            """,
            (org_id, academic_year),
        )
        return dict(rows[0]) if rows else {}

    # ------------------------------------------------------------------
    # Academics KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _academics_kpis(cls, org_id: str, academic_year: str) -> dict:
        enroll_rows = execute_query(
            """
            SELECT
                COUNT(DISTINCT student_id)  AS total_enrolled,
                COUNT(DISTINCT course_id)   AS active_courses
            FROM course_enrollments
            WHERE org_id = %s AND academic_year = %s AND status = 'ENROLLED'
            """,
            (org_id, academic_year),
        )

        att_rows = execute_query(
            """
            SELECT ROUND(AVG(
                CASE WHEN ar.status IN ('PRESENT','LATE') THEN 100.0 ELSE 0.0 END
            ), 1) AS avg_attendance_pct
            FROM attendance_records ar
            JOIN attendance_sessions sess ON sess.id = ar.session_id
            WHERE sess.org_id = %s AND sess.academic_year = %s
            """,
            (org_id, academic_year),
        )

        result = dict(enroll_rows[0]) if enroll_rows else {}
        if att_rows:
            result["avg_attendance_pct"] = att_rows[0]["avg_attendance_pct"]
        return result

    # ------------------------------------------------------------------
    # Finance KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _finance_kpis(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                SUM(total_amount)                                            AS total_billed,
                SUM(amount_paid)                                             AS total_collected,
                SUM(total_amount - amount_paid) FILTER (WHERE status != 'PAID') AS outstanding,
                COUNT(*) FILTER (WHERE status = 'OVERDUE')                  AS overdue_invoices,
                COUNT(*) FILTER (WHERE status = 'PAID')                     AS paid_invoices,
                ROUND(
                    100.0 * SUM(amount_paid) / NULLIF(SUM(total_amount), 0), 1
                )                                                            AS collection_rate
            FROM fee_invoices
            WHERE org_id = %s AND academic_year = %s
            """,
            (org_id, academic_year),
        )
        return dict(rows[0]) if rows else {}

    # ------------------------------------------------------------------
    # Examination KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _exam_kpis(cls, org_id: str, academic_year: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(DISTINCT student_id)                              AS students_appeared,
                COUNT(*) FILTER (WHERE is_pass = TRUE)                 AS passed,
                COUNT(*) FILTER (WHERE is_pass = FALSE AND is_absent = FALSE) AS failed,
                COUNT(*) FILTER (WHERE is_absent = TRUE)               AS absent,
                ROUND(AVG(marks_obtained) FILTER (WHERE is_absent = FALSE), 1) AS avg_marks
            FROM grades
            WHERE org_id = %s AND academic_year = %s AND is_published = TRUE
            """,
            (org_id, academic_year),
        )
        result = dict(rows[0]) if rows else {}

        cgpa_rows = execute_query(
            """
            SELECT ROUND(AVG(cgpa), 2) AS avg_cgpa
            FROM semester_results
            WHERE org_id = %s AND academic_year = %s AND is_published = TRUE
            """,
            (org_id, academic_year),
        )
        if cgpa_rows:
            result["avg_cgpa"] = cgpa_rows[0]["avg_cgpa"]

        total = int(result.get("students_appeared") or 0)
        passed = int(result.get("passed") or 0)
        result["pass_rate"] = round((passed / total) * 100, 1) if total else 0.0
        return result

    # ------------------------------------------------------------------
    # HR KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _hr_kpis(cls, org_id: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                            AS total_staff,
                COUNT(*) FILTER (WHERE employment_type = 'FULL_TIME') AS full_time,
                COUNT(*) FILTER (WHERE employment_type = 'PART_TIME') AS part_time,
                COUNT(*) FILTER (WHERE status = 'ON_LEAVE')         AS on_leave
            FROM staff_profiles
            WHERE org_id = %s AND status != 'TERMINATED'
            """,
            (org_id,),
        )
        return dict(rows[0]) if rows else {}

    # ------------------------------------------------------------------
    # Services KPIs
    # ------------------------------------------------------------------

    @classmethod
    def _services_kpis(cls, org_id: str) -> dict:
        hostel_rows = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'OCCUPIED') AS occupied_rooms,
                COUNT(*)                                      AS total_rooms
            FROM hostel_rooms
            WHERE org_id = %s AND is_active = TRUE
            """,
            (org_id,),
        )

        library_rows = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'BORROWED') AS books_borrowed,
                COUNT(*) FILTER (WHERE return_date < CURRENT_DATE AND status = 'BORROWED') AS overdue
            FROM library_borrowings
            WHERE org_id = %s
            """,
            (org_id,),
        )

        result = {}
        if hostel_rows:
            h = dict(hostel_rows[0])
            total = int(h.get("total_rooms") or 0)
            occ   = int(h.get("occupied_rooms") or 0)
            result["hostel_occupancy_pct"] = round((occ / total) * 100, 1) if total else 0.0
            result["hostel_occupied"] = occ
            result["hostel_total"]    = total
        if library_rows:
            result["library_books_borrowed"] = int(library_rows[0]["books_borrowed"] or 0)
            result["library_overdue"]        = int(library_rows[0]["overdue"] or 0)
        return result

    # ------------------------------------------------------------------
    # KPI snapshot cache (written by Celery beat task)
    # ------------------------------------------------------------------

    @classmethod
    def cache_snapshot(cls, org_id: str, academic_year: str) -> None:
        """Called by Celery beat daily to persist KPIs into kpi_snapshots."""
        import json
        kpis = cls.get_kpis(org_id, academic_year)
        today = date.today().isoformat()
        for key, value in kpis.items():
            if not isinstance(value, dict):
                continue
            execute_transaction([(
                """
                INSERT INTO kpi_snapshots (id, org_id, snapshot_date, kpi_key, value)
                VALUES (uuid_generate_v4(), %s, %s, %s, %s::jsonb)
                ON CONFLICT (org_id, snapshot_date, kpi_key)
                DO UPDATE SET value = EXCLUDED.value, computed_at = NOW()
                """,
                (org_id, today, key, json.dumps(value)),
            )])

    @classmethod
    def get_trend(cls, org_id: str, kpi_key: str, days: int = 30) -> list[dict]:
        """Return daily KPI snapshots for trend charts."""
        rows = execute_query(
            """
            SELECT snapshot_date, value
            FROM kpi_snapshots
            WHERE org_id = %s AND kpi_key = %s
              AND snapshot_date >= CURRENT_DATE - %s
            ORDER BY snapshot_date
            """,
            (org_id, kpi_key, days),
        )
        return [{"date": str(r["snapshot_date"]), "value": r["value"]} for r in rows]
