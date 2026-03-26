"""E06-S08 — AI Grade Analytics

Provides:
1. Pure-SQL grade distribution and pass/fail statistics
2. AI narrative insights via Qwen (through AIGateway)
   - Falls back gracefully if Ollama is unavailable
"""
from __future__ import annotations

import logging

from server.db_service import execute_query

logger = logging.getLogger(__name__)


class GradeAnalyticsService:

    @classmethod
    def get_course_statistics(cls, org_id: str, exam_schedule_id: str) -> dict:
        """Grade distribution, pass rate, average marks for one exam schedule."""
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                            AS total_students,
                COUNT(*) FILTER (WHERE is_pass = TRUE)             AS passed,
                COUNT(*) FILTER (WHERE is_pass = FALSE
                                    AND is_absent = FALSE)         AS failed,
                COUNT(*) FILTER (WHERE is_absent = TRUE)           AS absent,
                ROUND(AVG(marks_obtained) FILTER
                    (WHERE is_absent = FALSE), 2)                  AS avg_marks,
                ROUND(MAX(marks_obtained), 2)                      AS max_marks_scored,
                ROUND(MIN(marks_obtained) FILTER
                    (WHERE is_absent = FALSE), 2)                  AS min_marks_scored
            FROM grades
            WHERE exam_schedule_id = %s AND org_id = %s
            """,
            (exam_schedule_id, org_id),
        )
        stats = dict(rows[0]) if rows else {}

        # Grade distribution
        dist_rows = execute_query(
            """
            SELECT grade, COUNT(*) AS count
            FROM grades
            WHERE exam_schedule_id = %s AND org_id = %s AND is_absent = FALSE
            GROUP BY grade
            ORDER BY grade
            """,
            (exam_schedule_id, org_id),
        )
        stats["grade_distribution"] = {r["grade"]: int(r["count"]) for r in dist_rows}

        total = int(stats.get("total_students") or 0)
        passed = int(stats.get("passed") or 0)
        stats["pass_rate"] = round((passed / total) * 100, 1) if total > 0 else 0.0

        return stats

    @classmethod
    def get_semester_statistics(cls, org_id: str, academic_year: str, semester: int) -> dict:
        """Aggregate SGPA distribution and pass/fail across all courses in a semester."""
        result_rows = execute_query(
            """
            SELECT
                COUNT(*)                                        AS total_students,
                COUNT(*) FILTER (WHERE status = 'PASS')        AS passed,
                COUNT(*) FILTER (WHERE status = 'FAIL')        AS failed,
                ROUND(AVG(sgpa), 2)                            AS avg_sgpa,
                ROUND(AVG(cgpa), 2)                            AS avg_cgpa,
                ROUND(MAX(sgpa), 2)                            AS top_sgpa,
                ROUND(MIN(sgpa), 2)                            AS lowest_sgpa
            FROM semester_results
            WHERE org_id = %s AND academic_year = %s AND semester = %s
              AND is_published = TRUE
            """,
            (org_id, academic_year, semester),
        )
        stats = dict(result_rows[0]) if result_rows else {}

        # SGPA bands
        band_rows = execute_query(
            """
            SELECT
                CASE
                    WHEN sgpa >= 9.0 THEN 'O (9.0+)'
                    WHEN sgpa >= 8.0 THEN 'A+ (8.0-9.0)'
                    WHEN sgpa >= 7.0 THEN 'A (7.0-8.0)'
                    WHEN sgpa >= 6.0 THEN 'B+ (6.0-7.0)'
                    WHEN sgpa >= 5.0 THEN 'B (5.0-6.0)'
                    ELSE 'Below 5.0'
                END AS band,
                COUNT(*) AS count
            FROM semester_results
            WHERE org_id = %s AND academic_year = %s AND semester = %s
              AND is_published = TRUE
            GROUP BY 1
            ORDER BY 1
            """,
            (org_id, academic_year, semester),
        )
        stats["sgpa_bands"] = {r["band"]: int(r["count"]) for r in band_rows}

        total = int(stats.get("total_students") or 0)
        passed = int(stats.get("passed") or 0)
        stats["pass_rate"] = round((passed / total) * 100, 1) if total > 0 else 0.0

        return stats

    @classmethod
    def get_student_performance_trend(cls, org_id: str, student_id: str) -> list[dict]:
        """SGPA/CGPA trend across all published semesters for a student."""
        rows = execute_query(
            """
            SELECT academic_year, semester, sgpa, cgpa, status, credits_earned, total_credits
            FROM semester_results
            WHERE student_id = %s AND org_id = %s AND is_published = TRUE
            ORDER BY academic_year, semester
            """,
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def generate_ai_insights(cls, org_id: str, academic_year: str, semester: int) -> dict:
        """
        Ask Qwen to narrate grade analytics findings for the semester.
        Falls back to plain summary dict if Ollama is unavailable.
        """
        stats = cls.get_semester_statistics(org_id, academic_year, semester)

        prompt = f"""You are an academic analytics assistant for an educational institution.
Here are the grade statistics for Academic Year {academic_year}, Semester {semester}:

- Total students: {stats.get('total_students', 0)}
- Passed: {stats.get('passed', 0)} ({stats.get('pass_rate', 0)}%)
- Failed: {stats.get('failed', 0)}
- Average SGPA: {stats.get('avg_sgpa', 'N/A')}
- Top SGPA: {stats.get('top_sgpa', 'N/A')}
- SGPA bands: {stats.get('sgpa_bands', {})}

Write a brief (3-4 sentence) narrative summary for the academic coordinator highlighting:
1. Overall performance level
2. Any concerns (high failure rate, low average SGPA)
3. One actionable recommendation

Be concise and professional."""

        ai_narrative = None
        try:
            from server.core.ai_gateway import AIGateway
            result = AIGateway.invoke(
                org_id=org_id,
                prompt=prompt,
                task="grade_analytics_narrative",
                expected_schema={
                    "type": "object",
                    "properties": {"narrative": {"type": "string"}},
                    "required": ["narrative"],
                },
                actor_id="system",
            )
            ai_narrative = result.get("narrative") if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.warning("GradeAnalytics: AI narrative failed (non-fatal): %s", exc)

        return {
            "statistics": stats,
            "ai_narrative": ai_narrative,
            "academic_year": academic_year,
            "semester": semester,
        }
