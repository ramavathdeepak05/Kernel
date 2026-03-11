"""E05-S07 — Attendance Analytics (AI)

Identifies at-risk students and generates narrative insights using the
AI Gateway (Qwen via Ollama). All AI output is advisory only.
"""

import logging
from typing import Optional

from server.core.ai_gateway import AIGateway, AIGatewayContext
from server.core.rbac import Role
from server.db_service import execute_query

from .attendance import AttendanceService

logger = logging.getLogger(__name__)


class AttendanceAnalyticsService:

    @classmethod
    def get_at_risk_students(cls, org_id: str, academic_year: str,
                              course_id: Optional[str] = None) -> list[dict]:
        """
        Return all students below the minimum attendance threshold.
        Pure DB query — no AI needed for the list itself.
        """
        from server.admissions.policy_store import PolicyKey, PolicyStore
        min_pct = float(PolicyStore.get(org_id, PolicyKey.MIN_ATTENDANCE_PCT) or 75.0)

        sql = """
            SELECT
                ar.student_id,
                s.course_id,
                s.academic_year,
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN ar.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END) AS attended,
                ROUND(
                    SUM(CASE WHEN ar.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 2
                ) AS percentage
            FROM attendance_records ar
            JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE s.org_id = %s AND s.academic_year = %s
        """
        params: list = [org_id, academic_year]
        if course_id:
            sql += " AND s.course_id = %s"
            params.append(course_id)

        sql += """
            GROUP BY ar.student_id, s.course_id, s.academic_year
            HAVING ROUND(
                SUM(CASE WHEN ar.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0) * 100, 2
            ) < %s
            ORDER BY percentage ASC
        """
        params.append(min_pct)

        rows = execute_query(sql, params)
        return [dict(r) for r in rows]

    @classmethod
    def generate_ai_insights(cls, org_id: str, academic_year: str,
                              course_id: Optional[str] = None,
                              actor_id: str = "system") -> dict:
        """
        Use the AI Gateway to generate a narrative attendance analysis.

        Returns:
            {
                "at_risk_count": int,
                "insight": "...",          # AI-generated narrative
                "recommendations": [...],  # actionable suggestions
                "confidence": float,
            }
        """
        at_risk = cls.get_at_risk_students(org_id, academic_year, course_id)

        if not at_risk:
            return {
                "at_risk_count": 0,
                "insight": "No students are currently below the minimum attendance threshold.",
                "recommendations": [],
                "confidence": 1.0,
            }

        # Build a compact summary for the LLM (no PII — just aggregates)
        total_students = execute_query(
            "SELECT COUNT(DISTINCT student_id) AS n FROM course_enrollments WHERE org_id = %s AND academic_year = %s AND status = 'ENROLLED'",
            (org_id, academic_year),
        )
        total_n = int(total_students[0]["n"]) if total_students else len(at_risk)

        avg_pct = round(sum(float(r["percentage"] or 0) for r in at_risk) / len(at_risk), 1)
        lowest = at_risk[0] if at_risk else {}

        context = (
            f"Academic year: {academic_year}. "
            f"Total enrolled students: {total_n}. "
            f"Students below attendance threshold: {len(at_risk)} ({round(len(at_risk)/total_n*100, 1)}%). "
            f"Average attendance among at-risk students: {avg_pct}%. "
            f"Lowest attendance recorded: {lowest.get('percentage', 'N/A')}%. "
        )
        if course_id:
            context += f"Analysis is for course ID: {course_id}."

        prompt = (
            "You are an academic analytics assistant. "
            "Based on the following attendance statistics, provide:\n"
            "1. A 2-3 sentence narrative insight about attendance patterns.\n"
            "2. 2-3 specific, actionable recommendations for the academic coordinator.\n\n"
            f"Data: {context}\n\n"
            "Respond in JSON: {\"insight\": \"...\", \"recommendations\": [\"...\", \"...\"]}"
        )

        ctx = AIGatewayContext(
            actor_id=actor_id,
            actor_role=Role.SYSTEM,
            org_id=org_id,
            module="E05-S07",
        )

        try:
            result = AIGateway.invoke(
                context=ctx,
                prompt=prompt,
                output_schema={
                    "type": "object",
                    "required": ["insight", "recommendations"],
                    "properties": {
                        "insight": {"type": "string"},
                        "recommendations": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )
            return {
                "at_risk_count": len(at_risk),
                "insight": result.data.get("insight", ""),
                "recommendations": result.data.get("recommendations", []),
                "confidence": result.confidence,
            }
        except Exception as exc:
            logger.warning("E05-S07: AI insight generation failed: %s", exc)
            return {
                "at_risk_count": len(at_risk),
                "insight": f"{len(at_risk)} students are below the attendance threshold with an average of {avg_pct}%.",
                "recommendations": [
                    "Send attendance warning notifications to at-risk students.",
                    "Schedule counsellor meetings for students below 60% attendance.",
                ],
                "confidence": 0.0,
            }
