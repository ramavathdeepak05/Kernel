"""E08-S07 — AI Staff Analytics

Provides:
1. Workload distribution analysis (who is overloaded?)
2. Leave pattern insights (frequent absences, burnout risk)
3. Department performance summary
4. AI narrative via Qwen (non-fatal fallback)
"""

from __future__ import annotations

import logging

from server.db_service import execute_query

logger = logging.getLogger(__name__)


class HRAnalyticsService:
    @classmethod
    def workload_distribution(cls, org_id: str, academic_year: str) -> list[dict]:
        """Faculty workload: courses per faculty, credit hours, vs. policy limit."""
        from server.core.policy_store import PolicyStore

        max_courses = int(
            PolicyStore.get(org_id, "academics.faculty.max_courses_per_year") or 6
        )

        rows = execute_query(
            """
            SELECT
                u.id AS user_id, u.name, sp.department, sp.designation,
                COUNT(fa.id) AS courses_assigned,
                COALESCE(SUM(c.credits), 0) AS total_credits
            FROM faculty_assignments fa
            JOIN courses c ON c.id = fa.course_id
            JOIN staff_profiles sp ON sp.user_id = fa.faculty_id AND sp.org_id = %s
            JOIN users u ON u.id = fa.faculty_id
            WHERE fa.org_id = %s AND fa.academic_year = %s
            GROUP BY u.id, u.name, sp.department, sp.designation
            ORDER BY courses_assigned DESC
            """,
            (org_id, org_id, academic_year),
        )
        result = []
        for r in rows:
            row = dict(r)
            row["max_courses"] = max_courses
            row["is_overloaded"] = int(row["courses_assigned"]) > max_courses
            result.append(row)
        return result

    @classmethod
    def leave_patterns(cls, org_id: str, year: int) -> dict:
        """Identify high-leave staff, frequent single-day absences, department trends."""
        high_leave = execute_query(
            """
            SELECT
                u.name, sp.department, sp.employee_code,
                SUM(lr.days) AS total_days_taken,
                COUNT(lr.id) AS leave_applications
            FROM leave_requests lr
            JOIN staff_profiles sp ON sp.id = lr.staff_id AND sp.org_id = %s
            JOIN users u ON u.id = sp.user_id
            WHERE lr.org_id = %s AND lr.status = 'APPROVED'
              AND EXTRACT(YEAR FROM lr.from_date) = %s
            GROUP BY u.name, sp.department, sp.employee_code
            ORDER BY total_days_taken DESC
            LIMIT 15
            """,
            (org_id, org_id, year),
        )

        dept_summary = execute_query(
            """
            SELECT
                sp.department,
                ROUND(AVG(lr.days), 2) AS avg_days_per_request,
                COUNT(lr.id) AS total_requests,
                SUM(lr.days) AS total_days
            FROM leave_requests lr
            JOIN staff_profiles sp ON sp.id = lr.staff_id AND sp.org_id = %s
            WHERE lr.org_id = %s AND lr.status = 'APPROVED'
              AND EXTRACT(YEAR FROM lr.from_date) = %s
            GROUP BY sp.department
            ORDER BY total_days DESC
            """,
            (org_id, org_id, year),
        )

        return {
            "year": year,
            "high_leave_staff": [dict(r) for r in high_leave],
            "department_summary": [dict(r) for r in dept_summary],
        }

    @classmethod
    def department_performance_summary(
        cls, org_id: str, review_period: str
    ) -> list[dict]:
        rows = execute_query(
            """
            SELECT
                sp.department,
                COUNT(pr.id) AS reviews_count,
                ROUND(AVG(pr.overall_rating), 2) AS avg_rating,
                ROUND(MAX(pr.overall_rating), 1) AS top_rating,
                ROUND(MIN(pr.overall_rating), 1) AS bottom_rating
            FROM performance_reviews pr
            JOIN staff_profiles sp ON sp.id = pr.staff_id AND sp.org_id = %s
            WHERE pr.org_id = %s AND pr.review_period = %s
              AND pr.status IN ('SUBMITTED', 'ACKNOWLEDGED', 'FINALIZED')
            GROUP BY sp.department
            ORDER BY avg_rating DESC
            """,
            (org_id, org_id, review_period),
        )
        return [dict(r) for r in rows]

    @classmethod
    def generate_ai_insights(cls, org_id: str, academic_year: str) -> dict:
        """AI narrative summary of HR analytics."""
        workload = cls.workload_distribution(org_id, academic_year)
        overloaded = [w for w in workload if w.get("is_overloaded")]

        leave_data = cls.leave_patterns(org_id, int(academic_year[:4]))
        high_leave = leave_data.get("high_leave_staff", [])[:3]

        prompt = f"""You are an HR analytics assistant for an educational institution.

Academic Year: {academic_year}

Faculty Workload:
- Total faculty with assignments: {len(workload)}
- Overloaded faculty (> policy limit): {len(overloaded)}
- Overloaded names: {", ".join(w["name"] for w in overloaded[:5]) or "None"}

Leave Patterns:
- Top leave takers: {", ".join(f"{s['name']} ({s['total_days_taken']} days)" for s in high_leave) or "No data"}

Write a 2-3 sentence HR advisory for the HR Manager covering:
1. Faculty workload concern if any
2. Leave pattern observations
3. One recommended HR action

Be concise and professional."""

        ai_narrative = None
        try:
            from server.core.ai_gateway import AIGateway

            result = AIGateway.invoke(
                org_id=org_id,
                prompt=prompt,
                task="hr_analytics_narrative",
                expected_schema={
                    "type": "object",
                    "properties": {"narrative": {"type": "string"}},
                    "required": ["narrative"],
                },
                actor_id="system",
            )
            ai_narrative = (
                result.get("narrative") if isinstance(result, dict) else str(result)
            )
        except Exception as exc:
            logger.warning("HRAnalytics: AI narrative failed (non-fatal): %s", exc)

        return {
            "academic_year": academic_year,
            "workload_summary": workload,
            "overloaded_count": len(overloaded),
            "leave_patterns": leave_data,
            "ai_narrative": ai_narrative,
        }
