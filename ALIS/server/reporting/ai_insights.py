"""E11-S07 — AI Narrative Insights

Generates executive-level narrative summaries of institution performance
using Qwen via AIGateway. Falls back to structured data if AI unavailable.
"""

import logging

from server.db_service import execute_query

logger = logging.getLogger(__name__)


class AIInsightsService:

    @classmethod
    def institution_summary(cls, org_id: str, academic_year: str) -> dict:
        """
        Full institution health narrative for the academic year.
        Pulls KPIs from all modules and asks Qwen to narrate findings.
        """
        from .dashboard import DashboardService
        kpis = DashboardService.get_kpis(org_id, academic_year)

        adm  = kpis.get("admissions", {})
        acad = kpis.get("academics", {})
        fin  = kpis.get("finance", {})
        exam = kpis.get("examinations", {})

        prompt = f"""You are an academic analytics advisor for an educational institution.
Here is the institution's performance summary for Academic Year {academic_year}:

ADMISSIONS:
- Total Applications: {adm.get('total_applications', 'N/A')}
- Enrolled: {adm.get('enrolled', 'N/A')}
- Conversion Rate: {adm.get('conversion_rate', 'N/A')}%

ACADEMICS:
- Total Enrolled Students: {acad.get('total_enrolled', 'N/A')}
- Active Courses: {acad.get('active_courses', 'N/A')}
- Average Attendance: {acad.get('avg_attendance_pct', 'N/A')}%

EXAMINATIONS:
- Pass Rate: {exam.get('pass_rate', 'N/A')}%
- Average CGPA: {exam.get('avg_cgpa', 'N/A')}

FINANCE:
- Total Billed: Rs. {fin.get('total_billed', 'N/A')}
- Collection Rate: {fin.get('collection_rate', 'N/A')}%
- Overdue Invoices: {fin.get('overdue_invoices', 'N/A')}

Write a 4-5 sentence executive narrative that:
1. Summarizes overall institutional health
2. Highlights the top 2 strengths
3. Identifies the top 2 areas of concern
4. Gives one concrete, actionable recommendation

Be factual, professional, and concise. Output JSON: {{"narrative": "..."}}"""

        narrative = cls._call_ai(org_id, prompt, "institution_summary")
        return {
            "academic_year": academic_year,
            "kpis":          kpis,
            "ai_narrative":  narrative,
        }

    @classmethod
    def admissions_insights(cls, org_id: str, academic_year: str) -> dict:
        """AI narrative focused on admissions funnel and conversion."""
        from .admissions_report import AdmissionsReportService
        funnel    = AdmissionsReportService.funnel(org_id, academic_year)
        prog_wise = AdmissionsReportService.program_wise(org_id, academic_year)

        prompt = f"""Analyze this admissions data for Academic Year {academic_year}:

Funnel: {funnel}
Program breakdown: {prog_wise[:5]}

Write a 3-4 sentence insight covering:
1. Funnel efficiency (where drop-off is highest)
2. Which programs are performing well vs struggling
3. One actionable recommendation for the admissions team

Output JSON: {{"narrative": "..."}}"""

        return {
            "academic_year":   academic_year,
            "funnel":          funnel,
            "program_wise":    prog_wise,
            "ai_narrative":    cls._call_ai(org_id, prompt, "admissions_insights"),
        }

    @classmethod
    def finance_insights(cls, org_id: str, academic_year: str) -> dict:
        """AI narrative on fee collection health and default risk."""
        from .finance_report import FinanceReportService
        aging   = FinanceReportService.payment_aging(org_id, academic_year)
        waiver  = FinanceReportService.waiver_impact(org_id, academic_year)

        # Fee default prediction from E07
        try:
            from server.finance.analytics import FeeDefaultAnalyticsService
            risk = FeeDefaultAnalyticsService.predict_defaults(org_id, academic_year)
        except Exception:
            risk = {}

        prompt = f"""Analyze this financial data for Academic Year {academic_year}:

Payment aging: {aging}
Waiver impact: {waiver}
Default risk: {risk}

Write a 3-4 sentence insight covering:
1. Collection health and overdue trend
2. Impact of waivers on revenue
3. One recommendation to reduce defaults

Output JSON: {{"narrative": "..."}}"""

        return {
            "academic_year":  academic_year,
            "aging":          aging,
            "waiver_impact":  waiver,
            "default_risk":   risk,
            "ai_narrative":   cls._call_ai(org_id, prompt, "finance_insights"),
        }

    @classmethod
    def academics_insights(cls, org_id: str, academic_year: str, semester: int) -> dict:
        """AI narrative on academic performance and attendance."""
        from .academics_report import AcademicsReportService
        att_summary = AcademicsReportService.attendance_summary(org_id, academic_year, semester)
        low_att     = AcademicsReportService.low_attendance_students(
            org_id, academic_year, semester, threshold=75.0
        )

        prompt = f"""Analyze academic data for {academic_year} Semester {semester}:

Attendance by course (top 5 lowest): {att_summary[:5]}
Students below 75% attendance: {len(low_att)} students

Write a 3-4 sentence insight covering:
1. Overall attendance health
2. Courses or programs most at risk
3. One intervention recommendation

Output JSON: {{"narrative": "..."}}"""

        return {
            "academic_year":   academic_year,
            "semester":        semester,
            "attendance":      att_summary,
            "low_attendance_count": len(low_att),
            "ai_narrative":    cls._call_ai(org_id, prompt, "academics_insights"),
        }

    # ------------------------------------------------------------------
    # Internal AI call with graceful fallback
    # ------------------------------------------------------------------

    @classmethod
    def _call_ai(cls, org_id: str, prompt: str, task: str) -> str | None:
        try:
            from server.core.ai_gateway import AIGateway
            result = AIGateway.invoke(
                org_id=org_id,
                prompt=prompt,
                task=task,
                expected_schema={
                    "type": "object",
                    "properties": {"narrative": {"type": "string"}},
                    "required": ["narrative"],
                },
                actor_id="system",
            )
            return result.get("narrative") if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.warning("AIInsights: AI call failed (non-fatal): %s", exc)
            return None
