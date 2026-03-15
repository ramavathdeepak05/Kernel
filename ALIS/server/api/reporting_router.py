"""E11 — Reporting & Analytics API Router

Endpoints:
  E11-S01  GET  /reports/dashboard/kpis
           GET  /reports/dashboard/trend/{kpi_key}

  E11-S02  GET  /reports/admissions/funnel
           GET  /reports/admissions/programs
           GET  /reports/admissions/sources
           GET  /reports/admissions/counsellors
           GET  /reports/admissions/monthly

  E11-S03  GET  /reports/academics/enrollment
           GET  /reports/academics/attendance
           GET  /reports/academics/low-attendance
           GET  /reports/academics/faculty-workload
           GET  /reports/academics/timetable-conflicts
           GET  /reports/academics/ai-insights

  E11-S04  GET  /reports/finance/year-over-year
           GET  /reports/finance/scholarship-budget
           GET  /reports/finance/aging
           GET  /reports/finance/by-fee-type
           GET  /reports/finance/waiver-impact
           GET  /reports/finance/ai-insights

  E11-S05  POST /reports/saved
           GET  /reports/saved
           GET  /reports/saved/{id}
           POST /reports/saved/{id}/run
           DELETE /reports/saved/{id}
           GET  /reports/schema/{module}

  E11-S06  POST /reports/exports
           GET  /reports/exports
           GET  /reports/exports/{id}

  E11-S07  GET  /reports/ai/institution-summary
           GET  /reports/ai/admissions
           GET  /reports/ai/finance
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.reporting.dashboard        import DashboardService
from server.reporting.admissions_report import AdmissionsReportService
from server.reporting.academics_report  import AcademicsReportService
from server.reporting.finance_report    import FinanceReportService
from server.reporting.custom_reports    import CustomReportService
from server.reporting.export_engine     import ExportEngine
from server.reporting.ai_insights       import AIInsightsService
from server.reporting.models            import SavedReportCreate, ExportRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")

def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")
n
def _jsonify(obj):
    """Recursively convert Decimal/date/datetime/time to JSON-safe types."""
    from decimal import Decimal
    from datetime import datetime, date, time as _time
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, _time):
        return obj.strftime("%H:%M")
    return obj


# ──────────────────────────────────────────────────────────────
# E11-S01 — Dashboard KPIs
# ──────────────────────────────────────────────────────────────

@router.get("/dashboard/kpis")
@require_permission(Permission.REPORT_READ)
async def get_dashboard_kpis(
    request: Request,
    academic_year: str = Query(...),
) -> JSONResponse:
    return JSONResponse(content=DashboardService.get_kpis(_org(request), academic_year))


@router.get("/dashboard/trend/{kpi_key}")
@require_permission(Permission.REPORT_READ)
async def get_kpi_trend(
    request: Request,
    kpi_key: str,
    days: int = Query(30, le=365),
) -> JSONResponse:
    items = DashboardService.get_trend(_org(request), kpi_key, days)
    return JSONResponse(content={"kpi_key": kpi_key, "trend": items})


# ──────────────────────────────────────────────────────────────
# E11-S02 — Admissions Reports
# ──────────────────────────────────────────────────────────────

@router.get("/admissions/funnel")
@require_permission(Permission.REPORT_READ)
async def admissions_funnel(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=AdmissionsReportService.funnel(_org(request), academic_year)
    )


@router.get("/admissions/programs")
@require_permission(Permission.REPORT_READ)
async def admissions_by_program(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = AdmissionsReportService.program_wise(_org(request), academic_year)
    return JSONResponse(content={"programs": items})


@router.get("/admissions/sources")
@require_permission(Permission.REPORT_READ)
async def admissions_sources(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = AdmissionsReportService.source_analysis(_org(request), academic_year)
    return JSONResponse(content={"sources": items})


@router.get("/admissions/counsellors")
@require_permission(Permission.REPORT_READ)
async def counsellor_performance(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = AdmissionsReportService.counsellor_performance(_org(request), academic_year)
    return JSONResponse(content={"counsellors": items})


@router.get("/admissions/monthly")
@require_permission(Permission.REPORT_READ)
async def admissions_monthly(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = AdmissionsReportService.monthly_trend(_org(request), academic_year)
    return JSONResponse(content={"monthly": items})


# ──────────────────────────────────────────────────────────────
# E11-S03 — Academic Reports
# ──────────────────────────────────────────────────────────────

@router.get("/academics/enrollment")
@require_permission(Permission.REPORT_READ)
async def enrollment_summary(
    request: Request,
    academic_year: str = Query(...),
    semester: Optional[int] = Query(None),
) -> JSONResponse:
    return JSONResponse(
        content=AcademicsReportService.enrollment_summary(_org(request), academic_year, semester)
    )


@router.get("/academics/attendance")
@require_permission(Permission.REPORT_READ)
async def attendance_summary(
    request: Request,
    academic_year: str = Query(...),
    semester: Optional[int] = Query(None),
) -> JSONResponse:
    items = AcademicsReportService.attendance_summary(_org(request), academic_year, semester)
    return JSONResponse(content={"courses": items})


@router.get("/academics/low-attendance")
@require_permission(Permission.REPORT_READ)
async def low_attendance(
    request: Request,
    academic_year: str = Query(...),
    semester: int = Query(...),
    threshold: float = Query(75.0),
) -> JSONResponse:
    items = AcademicsReportService.low_attendance_students(
        _org(request), academic_year, semester, threshold
    )
    return JSONResponse(content={"students": items, "total": len(items)})


@router.get("/academics/faculty-workload")
@require_permission(Permission.REPORT_READ)
async def faculty_workload(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = AcademicsReportService.faculty_workload(_org(request), academic_year)
    return JSONResponse(content={"faculty": items})


@router.get("/academics/timetable-conflicts")
@require_permission(Permission.REPORT_READ)
async def timetable_conflicts(
    request: Request,
    academic_year: str = Query(...),
    semester: int = Query(...),
) -> JSONResponse:
    items = AcademicsReportService.timetable_conflicts(_org(request), academic_year, semester)
    return JSONResponse(content={"conflicts": items, "total": len(items)})


@router.get("/academics/ai-insights")
@require_permission(Permission.REPORT_READ)
async def academics_ai_insights(
    request: Request,
    academic_year: str = Query(...),
    semester: int = Query(...),
) -> JSONResponse:
    return JSONResponse(
        content=AIInsightsService.academics_insights(_org(request), academic_year, semester)
    )


# ──────────────────────────────────────────────────────────────
# E11-S04 — Financial Reports
# ──────────────────────────────────────────────────────────────

@router.get("/finance/year-over-year")
@require_permission(Permission.REPORT_READ)
async def year_over_year(
    request: Request,
    years: List[str] = Query(...),
) -> JSONResponse:
    items = FinanceReportService.year_over_year(_org(request), years)
    return JSONResponse(content={"years": items})


@router.get("/finance/scholarship-budget")
@require_permission(Permission.REPORT_READ)
async def scholarship_budget(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=FinanceReportService.scholarship_budget(_org(request), academic_year)
    )


@router.get("/finance/aging")
@require_permission(Permission.REPORT_READ)
async def payment_aging(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.payment_aging(_org(request), academic_year)
    return JSONResponse(content={"aging": items})


@router.get("/finance/by-fee-type")
@require_permission(Permission.REPORT_READ)
async def revenue_by_fee_type(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.revenue_by_fee_type(_org(request), academic_year)
    return JSONResponse(content={"fee_types": items})


@router.get("/finance/waiver-impact")
@require_permission(Permission.REPORT_READ)
async def waiver_impact(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=FinanceReportService.waiver_impact(_org(request), academic_year)
    )


@router.get("/finance/ai-insights")
@require_permission(Permission.REPORT_READ)
async def finance_ai_insights(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=AIInsightsService.finance_insights(_org(request), academic_year)
    )


# ──────────────────────────────────────────────────────────────
# E11-S05 — Custom / Saved Reports
# ──────────────────────────────────────────────────────────────

@router.post("/saved", status_code=201)
@require_permission(Permission.REPORT_CREATE)
async def create_saved_report(request: Request, body: SavedReportCreate) -> JSONResponse:
    result = CustomReportService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/saved")
@require_permission(Permission.REPORT_READ)
async def list_saved_reports(
    request: Request,
    module: Optional[str] = Query(None),
) -> JSONResponse:
    items = CustomReportService.list(_org(request), module)
    return JSONResponse(content={"reports": items, "total": len(items)})


@router.get("/saved/{report_id}")
@require_permission(Permission.REPORT_READ)
async def get_saved_report(request: Request, report_id: str) -> JSONResponse:
    return JSONResponse(content=CustomReportService.get(_org(request), report_id))


@router.post("/saved/{report_id}/run")
@require_permission(Permission.REPORT_READ)
async def run_saved_report(request: Request, report_id: str) -> JSONResponse:
    rows = CustomReportService.run(_org(request), report_id)
    return JSONResponse(content={"rows": rows, "total": len(rows)})


@router.delete("/saved/{report_id}")
@require_permission(Permission.REPORT_CREATE)
async def delete_saved_report(request: Request, report_id: str) -> JSONResponse:
    return JSONResponse(content=CustomReportService.delete(_org(request), report_id))


@router.get("/schema/{module}")
@require_permission(Permission.REPORT_READ)
async def report_schema(request: Request, module: str) -> JSONResponse:
    return JSONResponse(content=CustomReportService.get_schema(module))


# ──────────────────────────────────────────────────────────────
# E11-S06 — Export Engine
# ──────────────────────────────────────────────────────────────

@router.post("/exports", status_code=201)
@require_permission(Permission.REPORT_EXPORT)
async def request_export(request: Request, body: ExportRequest) -> JSONResponse:
    result = ExportEngine.request_export(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/exports")
@require_permission(Permission.REPORT_EXPORT)
async def list_exports(request: Request) -> JSONResponse:
    items = ExportEngine.list(_org(request))
    return JSONResponse(content={"exports": items, "total": len(items)})


@router.get("/exports/{job_id}")
@require_permission(Permission.REPORT_EXPORT)
async def get_export(request: Request, job_id: str) -> JSONResponse:
    return JSONResponse(content=ExportEngine.get(_org(request), job_id))


# ──────────────────────────────────────────────────────────────
# E11-S07 — AI Narrative Insights
# ──────────────────────────────────────────────────────────────

@router.get("/ai/institution-summary")
@require_permission(Permission.REPORT_READ)
async def institution_ai_summary(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=AIInsightsService.institution_summary(_org(request), academic_year)
    )


@router.get("/ai/admissions")
@require_permission(Permission.REPORT_READ)
async def admissions_ai_insights(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=AIInsightsService.admissions_insights(_org(request), academic_year)
    )
