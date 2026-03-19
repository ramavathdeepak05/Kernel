"""E08 — HR & Staff API Router

Endpoints:
  E08-S01  POST   /hr/staff
           GET    /hr/staff
           GET    /hr/staff/{id}
           PATCH  /hr/staff/{id}
           DELETE /hr/staff/{id}   (deactivate)
           GET    /hr/staff/{id}/workload

  E08-S03  POST   /hr/leave-types
           GET    /hr/leave-types
           POST   /hr/leave
           GET    /hr/leave/pending
           GET    /hr/leave/staff/{staff_id}
           GET    /hr/leave/balance/{staff_id}
           POST   /hr/leave/{id}/decide
           POST   /hr/leave/{id}/cancel

  E08-S04  POST   /hr/payroll/components
           GET    /hr/payroll/components
           POST   /hr/payroll/salary-structure
           POST   /hr/payroll/generate
           POST   /hr/payroll/{id}/mark-paid
           GET    /hr/payroll/staff/{staff_id}
           GET    /hr/payroll/summary

  E08-S05  POST   /hr/reviews
           PATCH  /hr/reviews/{id}
           GET    /hr/reviews/pending
           GET    /hr/reviews/staff/{staff_id}

  E08-S06  POST   /hr/attendance/mark
           POST   /hr/attendance/bulk
           GET    /hr/attendance/roster
           GET    /hr/attendance/staff/{staff_id}/monthly
           GET    /hr/attendance/department/summary

  E08-S07  GET    /hr/analytics/workload
           GET    /hr/analytics/leave-patterns
           GET    /hr/analytics/department-performance
           GET    /hr/analytics/ai-insights
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.hr.staff        import StaffService
from server.hr.leave        import LeaveTypeService, LeaveService
from server.hr.payroll      import PayrollComponentService, SalaryStructureService, PayslipService
from server.hr.performance  import PerformanceReviewService
from server.hr.attendance   import StaffAttendanceService
from server.hr.analytics    import HRAnalyticsService
from server.hr.models       import (
    StaffProfileCreate, StaffProfileUpdate,
    LeaveTypeCreate, LeaveRequestCreate, LeaveDecision,
    PayrollComponentCreate, SalaryStructureCreate, PayslipGenerate,
    PerformanceReviewCreate, PerformanceReviewUpdate,
    StaffAttendanceMark, StaffAttendanceBulk,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/hr", tags=["hr"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")

def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")

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
# E08-S01 — Staff Profiles
# ──────────────────────────────────────────────────────────────

@router.post("/staff", status_code=201)
@require_permission(Permission.STAFF_CREATE)
async def create_staff(request: Request, body: StaffProfileCreate) -> JSONResponse:
    result = StaffService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/staff")
@require_permission(Permission.STAFF_READ)
async def list_staff(
    request: Request,
    department: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    is_active: bool = Query(True),
) -> JSONResponse:
    items = StaffService.list(_org(request), department, employment_type, is_active)
    return JSONResponse(content={"staff": items, "total": len(items)})


@router.get("/staff/{staff_id}")
@require_permission(Permission.STAFF_READ)
async def get_staff(request: Request, staff_id: str) -> JSONResponse:
    return JSONResponse(content=StaffService.get(_org(request), staff_id))


@router.patch("/staff/{staff_id}")
@require_permission(Permission.STAFF_UPDATE)
async def update_staff(request: Request, staff_id: str, body: StaffProfileUpdate) -> JSONResponse:
    result = StaffService.update(_org(request), staff_id, body, _actor(request))
    return JSONResponse(content=result)


@router.delete("/staff/{staff_id}")
@require_permission(Permission.STAFF_UPDATE)
async def deactivate_staff(request: Request, staff_id: str, body: dict) -> JSONResponse:
    result = StaffService.deactivate(
        _org(request), staff_id, body["date_of_leaving"], _actor(request)
    )
    return JSONResponse(content=result)


@router.get("/staff/{staff_id}/workload")
@require_permission(Permission.STAFF_READ)
async def staff_workload(
    request: Request, staff_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=StaffService.get_workload_summary(_org(request), staff_id, academic_year)
    )


# ──────────────────────────────────────────────────────────────
# E08-S03 — Leave Management
# ──────────────────────────────────────────────────────────────

@router.post("/leave-types", status_code=201)
@require_permission(Permission.STAFF_CREATE)
async def create_leave_type(request: Request, body: LeaveTypeCreate) -> JSONResponse:
    result = LeaveTypeService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/leave-types")
@require_permission(Permission.STAFF_READ)
async def list_leave_types(request: Request) -> JSONResponse:
    items = LeaveTypeService.list(_org(request))
    return JSONResponse(content={"leave_types": items})


@router.post("/leave", status_code=201)
@require_permission(Permission.STAFF_READ)
async def apply_leave(request: Request, body: LeaveRequestCreate) -> JSONResponse:
    from server.hr.staff import StaffService as SS
    staff = SS.get_by_user(_org(request), _actor(request))
    result = LeaveService.apply(_org(request), str(staff["id"]), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/leave/pending")
@require_permission(Permission.LEAVE_APPROVE)
async def list_pending_leave(request: Request) -> JSONResponse:
    items = LeaveService.list_pending(_org(request))
    return JSONResponse(content={"leave_requests": items, "total": len(items)})


@router.get("/leave/staff/{staff_id}")
@require_permission(Permission.STAFF_READ)
async def list_staff_leave(
    request: Request,
    staff_id: str,
    status: Optional[str] = Query(None),
) -> JSONResponse:
    items = LeaveService.list_for_staff(_org(request), staff_id, status)
    return JSONResponse(content={"leave_requests": items})


@router.get("/leave/balance/{staff_id}")
@require_permission(Permission.STAFF_READ)
async def leave_balance(
    request: Request, staff_id: str, year: str = Query(...)
) -> JSONResponse:
    items = LeaveService.get_balance(_org(request), staff_id, year)
    return JSONResponse(content={"balances": items})


@router.post("/leave/{request_id}/decide")
@require_permission(Permission.LEAVE_APPROVE)
async def decide_leave(
    request: Request, request_id: str, body: LeaveDecision
) -> JSONResponse:
    result = LeaveService.decide(_org(request), request_id, body, _actor(request))
    return JSONResponse(content=result)


@router.post("/leave/{request_id}/cancel")
@require_permission(Permission.STAFF_READ)
async def cancel_leave(request: Request, request_id: str) -> JSONResponse:
    result = LeaveService.cancel(_org(request), request_id, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E08-S04 — Payroll
# ──────────────────────────────────────────────────────────────

@router.post("/payroll/components", status_code=201)
@require_permission(Permission.PAYROLL_PROCESS)
async def create_payroll_component(
    request: Request, body: PayrollComponentCreate
) -> JSONResponse:
    result = PayrollComponentService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/payroll/components")
@require_permission(Permission.PAYROLL_READ)
async def list_payroll_components(request: Request) -> JSONResponse:
    items = PayrollComponentService.list(_org(request))
    return JSONResponse(content={"components": items})


@router.post("/payroll/salary-structure", status_code=201)
@require_permission(Permission.PAYROLL_PROCESS)
async def create_salary_structure(
    request: Request, body: SalaryStructureCreate
) -> JSONResponse:
    result = SalaryStructureService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.post("/payroll/generate", status_code=201)
@require_permission(Permission.PAYROLL_PROCESS)
async def generate_payslip(request: Request, body: dict) -> JSONResponse:
    req = PayslipGenerate(month=body["month"], year=body["year"])
    result = PayslipService.generate(_org(request), body["staff_id"], req, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.post("/payroll/{payslip_id}/mark-paid")
@require_permission(Permission.PAYROLL_PROCESS)
async def mark_payslip_paid(request: Request, payslip_id: str) -> JSONResponse:
    result = PayslipService.mark_paid(_org(request), payslip_id, _actor(request))
    return JSONResponse(content=result)


@router.get("/payroll/staff/{staff_id}")
@require_permission(Permission.PAYROLL_READ)
async def list_staff_payslips(request: Request, staff_id: str) -> JSONResponse:
    items = PayslipService.list_for_staff(_org(request), staff_id)
    return JSONResponse(content={"payslips": items})


@router.get("/payroll/summary")
@require_permission(Permission.PAYROLL_READ)
async def payroll_monthly_summary(
    request: Request,
    month: int = Query(...),
    year: int = Query(...),
) -> JSONResponse:
    return JSONResponse(content=PayslipService.monthly_summary(_org(request), month, year))


# ──────────────────────────────────────────────────────────────
# E08-S05 — Performance Reviews
# ──────────────────────────────────────────────────────────────

@router.post("/reviews", status_code=201)
@require_permission(Permission.STAFF_UPDATE)
async def create_review(request: Request, body: PerformanceReviewCreate) -> JSONResponse:
    result = PerformanceReviewService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.patch("/reviews/{review_id}")
@require_permission(Permission.STAFF_UPDATE)
async def update_review(
    request: Request, review_id: str, body: PerformanceReviewUpdate
) -> JSONResponse:
    result = PerformanceReviewService.update(_org(request), review_id, body, _actor(request))
    return JSONResponse(content=result)


@router.get("/reviews/pending")
@require_permission(Permission.STAFF_READ)
async def list_pending_reviews(request: Request) -> JSONResponse:
    items = PerformanceReviewService.list_pending(_org(request))
    return JSONResponse(content={"reviews": items, "total": len(items)})


@router.get("/reviews/staff/{staff_id}")
@require_permission(Permission.STAFF_READ)
async def list_staff_reviews(request: Request, staff_id: str) -> JSONResponse:
    items = PerformanceReviewService.list_for_staff(_org(request), staff_id)
    return JSONResponse(content={"reviews": items})


# ──────────────────────────────────────────────────────────────
# E08-S06 — Staff Attendance
# ──────────────────────────────────────────────────────────────

@router.post("/attendance/mark")
@require_permission(Permission.STAFF_UPDATE)
async def mark_attendance(request: Request, body: StaffAttendanceMark) -> JSONResponse:
    result = StaffAttendanceService.mark(_org(request), body, _actor(request))
    return JSONResponse(content=result)


@router.post("/attendance/bulk")
@require_permission(Permission.STAFF_UPDATE)
async def bulk_mark_attendance(request: Request, body: StaffAttendanceBulk) -> JSONResponse:
    result = StaffAttendanceService.bulk_mark(_org(request), body, _actor(request))
    return JSONResponse(content=result)


@router.get("/attendance/roster")
@require_permission(Permission.STAFF_READ)
async def daily_roster(request: Request, date: str = Query(...)) -> JSONResponse:
    items = StaffAttendanceService.get_daily_roster(_org(request), date)
    return JSONResponse(content={"roster": items, "date": date})


@router.get("/attendance/staff/{staff_id}/monthly")
@require_permission(Permission.STAFF_READ)
async def staff_monthly_attendance(
    request: Request,
    staff_id: str,
    month: int = Query(...),
    year: int = Query(...),
) -> JSONResponse:
    return JSONResponse(
        content=StaffAttendanceService.get_monthly_summary(_org(request), staff_id, month, year)
    )


@router.get("/attendance/department/summary")
@require_permission(Permission.STAFF_READ)
async def department_attendance_summary(
    request: Request,
    month: int = Query(...),
    year: int = Query(...),
) -> JSONResponse:
    items = StaffAttendanceService.get_department_summary(_org(request), month, year)
    return JSONResponse(content={"departments": items})


# ──────────────────────────────────────────────────────────────
# E08-S07 — HR Analytics
# ──────────────────────────────────────────────────────────────

@router.get("/analytics/workload")
@require_permission(Permission.STAFF_READ)
async def workload_distribution(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = HRAnalyticsService.workload_distribution(_org(request), academic_year)
    return JSONResponse(content={"workload": items})


@router.get("/analytics/leave-patterns")
@require_permission(Permission.STAFF_READ)
async def leave_patterns(request: Request, year: int = Query(...)) -> JSONResponse:
    return JSONResponse(content=HRAnalyticsService.leave_patterns(_org(request), year))


@router.get("/analytics/department-performance")
@require_permission(Permission.STAFF_READ)
async def department_performance(
    request: Request, review_period: str = Query(...)
) -> JSONResponse:
    items = HRAnalyticsService.department_performance_summary(_org(request), review_period)
    return JSONResponse(content={"departments": items})


@router.get("/analytics/ai-insights")
@require_permission(Permission.STAFF_READ)
async def hr_ai_insights(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=HRAnalyticsService.generate_ai_insights(_org(request), academic_year)
    )
