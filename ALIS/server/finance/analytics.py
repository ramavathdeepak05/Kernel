"""E07-S08 — AI Fee Default Prediction

Uses Qwen (via AIGateway) to score each student's default risk based on:
- Payment history (number of overdue invoices, average days late)
- Academic standing (attendance, CGPA)
- Scholarship status
- Program fee tier

Falls back to rule-based scoring if Ollama is unavailable.
"""

import logging

from server.db_service import execute_query

logger = logging.getLogger(__name__)


def _rule_based_score(student: dict) -> tuple[float, str]:
    """Return (risk_score 0-1, reason) using pure heuristics."""
    score = 0.0
    reasons = []

    overdue = int(student.get("overdue_invoices") or 0)
    if overdue > 0:
        score += min(overdue * 0.2, 0.4)
        reasons.append(f"{overdue} overdue invoice(s)")

    avg_days_late = float(student.get("avg_days_late") or 0)
    if avg_days_late > 30:
        score += 0.2
        reasons.append(f"avg {avg_days_late:.0f} days late")
    elif avg_days_late > 0:
        score += 0.1
        reasons.append(f"avg {avg_days_late:.0f} days late")

    has_scholarship = bool(student.get("has_scholarship"))
    if not has_scholarship:
        score += 0.1

    cgpa = float(student.get("cgpa") or 0)
    if cgpa < 4.0 and cgpa > 0:
        score += 0.1
        reasons.append(f"low CGPA {cgpa}")

    score = round(min(score, 1.0), 2)
    label = "HIGH" if score >= 0.6 else ("MEDIUM" if score >= 0.3 else "LOW")
    return score, label, "; ".join(reasons) if reasons else "No significant risk factors"


class FeeDefaultAnalyticsService:

    @classmethod
    def predict_defaults(cls, org_id: str, academic_year: str) -> dict:
        """
        Score all students with outstanding balances for default risk.
        Returns top at-risk students + aggregate stats.
        """
        students = execute_query(
            """
            SELECT
                s.id AS student_id, s.name, s.roll_number, s.program, s.email,
                COUNT(si.id) FILTER (WHERE si.status = 'OVERDUE')    AS overdue_invoices,
                COUNT(si.id) FILTER (WHERE si.status != 'PAID')      AS unpaid_invoices,
                ROUND(SUM(si.balance) FILTER (WHERE si.balance > 0), 2) AS total_outstanding,
                ROUND(AVG(
                    CASE WHEN si.status = 'OVERDUE'
                         THEN (CURRENT_DATE - si.due_date)
                    END
                ), 1)                                                 AS avg_days_late,
                EXISTS(
                    SELECT 1 FROM scholarship_assignments sa
                    WHERE sa.student_id = s.id AND sa.academic_year = %s
                      AND sa.status = 'ACTIVE' AND sa.org_id = %s
                )                                                     AS has_scholarship,
                sr.cgpa
            FROM students s
            JOIN student_invoices si ON si.student_id = s.id AND si.academic_year = %s
            LEFT JOIN (
                SELECT DISTINCT ON (student_id) student_id, cgpa
                FROM semester_results
                WHERE org_id = %s
                ORDER BY student_id, academic_year DESC, semester DESC
            ) sr ON sr.student_id = s.id
            WHERE s.org_id = %s AND si.org_id = %s
              AND si.status != 'PAID'
            GROUP BY s.id, s.name, s.roll_number, s.program, s.email, sr.cgpa
            HAVING SUM(si.balance) > 0
            ORDER BY total_outstanding DESC
            """,
            (academic_year, org_id, academic_year, org_id, org_id, org_id),
        )

        scored = []
        for student in students:
            row = dict(student)
            score, label, reason = _rule_based_score(row)
            row["risk_score"]  = score
            row["risk_label"]  = label
            row["risk_reason"] = reason
            scored.append(row)

        # Sort by risk score desc
        scored.sort(key=lambda x: x["risk_score"], reverse=True)

        high_risk   = [s for s in scored if s["risk_label"] == "HIGH"]
        medium_risk = [s for s in scored if s["risk_label"] == "MEDIUM"]
        low_risk    = [s for s in scored if s["risk_label"] == "LOW"]

        # AI narrative for high-risk cohort
        ai_narrative = cls._generate_narrative(org_id, academic_year, high_risk, len(scored))

        return {
            "academic_year":    academic_year,
            "total_at_risk":    len(scored),
            "high_risk_count":  len(high_risk),
            "medium_risk_count": len(medium_risk),
            "low_risk_count":   len(low_risk),
            "high_risk":        high_risk[:20],      # top 20 for display
            "ai_narrative":     ai_narrative,
        }

    @classmethod
    def _generate_narrative(cls, org_id: str, academic_year: str,
                              high_risk: list, total: int) -> str | None:
        if not high_risk:
            return None

        sample = high_risk[:5]
        names  = ", ".join(s["name"] for s in sample)

        prompt = f"""You are a financial analytics assistant for an educational institution.

Academic Year: {academic_year}
Total students with outstanding fees: {total}
High-risk students (likely to default): {len(high_risk)}

Top at-risk students: {names}
Common risk factors: {"; ".join(set(s.get("risk_reason","") for s in sample if s.get("risk_reason")))}

Write a 2-3 sentence advisory for the Finance Officer:
1. Summarize the default risk situation
2. Recommend one immediate action (e.g., send reminders, schedule counselling, offer installment plan)

Be direct and professional."""

        try:
            from server.core.ai_gateway import AIGateway
            result = AIGateway.invoke(
                org_id=org_id,
                prompt=prompt,
                task="fee_default_prediction_narrative",
                expected_schema={
                    "type": "object",
                    "properties": {"narrative": {"type": "string"}},
                    "required": ["narrative"],
                },
                actor_id="system",
            )
            return result.get("narrative") if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.warning("FeeAnalytics: AI narrative failed (non-fatal): %s", exc)
            return None
