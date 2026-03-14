"""E05 — Academics API Router"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.academics.models import (
    AttendanceMarkRequest,
    CourseCreate,
    FacultyAssignRequest,
    ProgramCreate,
    StudentEnrollRequest,
    TimetableSlotCreate,
)
from server.academics.programs import ProgramService
from server.academics.courses import CourseService
from server.academics.enrollment import AcademicEnrollmentService
from server.academics.faculty import FacultyAssignmentService
from server.academics.timetable import TimetableService
from server.academics.attendance import AttendanceService
from server.academics.analytics import AttendanceAnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/academics", tags=["academics"])


def _jsonify(obj):
    """Recursively convert Decimal/date/datetime to JSON-safe types."""
    from decimal import Decimal
    from datetime import datetime, date
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    from datetime import time as _time
    if isinstance(obj, _time):
        return obj.strftime("%H:%M")
    return obj


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")

def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")

def _role(r: Request) -> str:
    return getattr(r.state, "user_role", "STUDENT")


# =============================================================================
# E05-S01 — Programs
# =============================================================================

@router.post("/programs", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def create_program(request: Request, body: ProgramCreate) -> JSONResponse:
    result = ProgramService.create(org_id=_org(request), req=body, actor_id=_actor(request))
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/programs")
@require_permission(Permission.STUDENT_READ)
async def list_programs(request: Request) -> JSONResponse:
    items = ProgramService.list(org_id=_org(request))
    return JSONResponse(content=_jsonify({"programs": items, "total": len(items)}))


@router.get("/programs/{program_id}")
@require_permission(Permission.STUDENT_READ)
async def get_program(request: Request, program_id: str) -> JSONResponse:
    return JSONResponse(content=_jsonify(ProgramService.get(org_id=_org(request), program_id=program_id)))


@router.patch("/programs/{program_id}")
@require_permission(Permission.STUDENT_CREATE)
async def update_program(request: Request, program_id: str, body: dict) -> JSONResponse:
    result = ProgramService.update(org_id=_org(request), program_id=program_id,
                                   updates=body, actor_id=_actor(request))
    return JSONResponse(content=_jsonify(result))


# =============================================================================
# E05-S02 — Courses
# =============================================================================

@router.post("/courses", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def create_course(request: Request, body: CourseCreate) -> JSONResponse:
    result = CourseService.create(org_id=_org(request), req=body, actor_id=_actor(request))
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/courses")
@require_permission(Permission.STUDENT_READ)
async def list_courses(request: Request, program_id: Optional[str] = None,
                       semester: Optional[int] = None) -> JSONResponse:
    items = CourseService.list(org_id=_org(request), program_id=program_id, semester=semester)
    return JSONResponse(content=_jsonify({"courses": items, "total": len(items)}))


@router.get("/courses/{course_id}")
@require_permission(Permission.STUDENT_READ)
async def get_course(request: Request, course_id: str) -> JSONResponse:
    return JSONResponse(content=_jsonify(CourseService.get(org_id=_org(request), course_id=course_id)))


# =============================================================================
# E05-S03 — Student-Course Enrollment
# =============================================================================

@router.post("/enrollments", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def enroll_student(request: Request, body: StudentEnrollRequest) -> JSONResponse:
    result = AcademicEnrollmentService.enroll_student(
        org_id=_org(request), req=body, actor_id=_actor(request)
    )
    return JSONResponse(status_code=201, content={"enrollments": result})


@router.get("/enrollments/student/{student_id}")
@require_permission(Permission.STUDENT_READ)
async def get_student_enrollments(request: Request, student_id: str,
                                   academic_year: str = "") -> JSONResponse:
    items = AcademicEnrollmentService.list_for_student(
        org_id=_org(request), student_id=student_id, academic_year=academic_year
    )
    return JSONResponse(content={"enrollments": items, "total": len(items)})


@router.delete("/enrollments/{student_id}/{course_id}")
@require_permission(Permission.STUDENT_CREATE)
async def drop_course(request: Request, student_id: str, course_id: str,
                      academic_year: str = "") -> JSONResponse:
    result = AcademicEnrollmentService.drop_course(
        org_id=_org(request), student_id=student_id, course_id=course_id,
        academic_year=academic_year, actor_id=_actor(request)
    )
    return JSONResponse(content=result)


# =============================================================================
# E05-S04 — Faculty Assignments
# =============================================================================

@router.post("/faculty/assign", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def assign_faculty(request: Request, body: FacultyAssignRequest) -> JSONResponse:
    result = FacultyAssignmentService.assign(
        org_id=_org(request), req=body, actor_id=_actor(request)
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/faculty/{faculty_id}/assignments")
@require_permission(Permission.STUDENT_READ)
async def get_faculty_assignments(request: Request, faculty_id: str,
                                   academic_year: str = "") -> JSONResponse:
    items = FacultyAssignmentService.list_for_faculty(
        org_id=_org(request), faculty_id=faculty_id, academic_year=academic_year
    )
    return JSONResponse(content={"assignments": items, "total": len(items)})


@router.delete("/faculty/assignments/{assignment_id}", status_code=204)
@require_permission(Permission.STUDENT_CREATE)
async def unassign_faculty(request: Request, assignment_id: str) -> None:
    FacultyAssignmentService.unassign(
        org_id=_org(request), assignment_id=assignment_id, actor_id=_actor(request)
    )


# =============================================================================
# E05-S05 — Timetable
# =============================================================================

@router.post("/timetable", status_code=201)
@require_permission(Permission.STUDENT_CREATE)
async def add_timetable_slot(request: Request, body: TimetableSlotCreate) -> JSONResponse:
    result = TimetableService.add_slot(
        org_id=_org(request), req=body, actor_id=_actor(request)
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/timetable")
@require_permission(Permission.STUDENT_READ)
async def get_timetable(request: Request, academic_year: str = "",
                         course_id: Optional[str] = None,
                         faculty_id: Optional[str] = None) -> JSONResponse:
    slots = TimetableService.get_weekly(
        org_id=_org(request), academic_year=academic_year,
        course_id=course_id, faculty_id=faculty_id
    )
    return JSONResponse(content=_jsonify({"slots": slots, "total": len(slots)}))


@router.delete("/timetable/{slot_id}", status_code=204)
@require_permission(Permission.STUDENT_CREATE)
async def delete_timetable_slot(request: Request, slot_id: str) -> None:
    TimetableService.delete_slot(
        org_id=_org(request), slot_id=slot_id, actor_id=_actor(request)
    )


# =============================================================================
# E05-S06 — Attendance
# =============================================================================

@router.post("/attendance", status_code=201)
@require_permission(Permission.STUDENT_UPDATE)
async def mark_attendance(request: Request, body: AttendanceMarkRequest) -> JSONResponse:
    result = AttendanceService.mark_session(
        org_id=_org(request), req=body,
        faculty_id=_actor(request), actor_id=_actor(request)
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/attendance/sessions/{session_id}/finalize")
@require_permission(Permission.STUDENT_UPDATE)
async def finalize_session(request: Request, session_id: str) -> JSONResponse:
    result = AttendanceService.finalize_session(
        org_id=_org(request), session_id=session_id, actor_id=_actor(request)
    )
    return JSONResponse(content=result)


@router.get("/attendance/student/{student_id}")
@require_permission(Permission.STUDENT_READ)
async def get_student_attendance(request: Request, student_id: str,
                                  course_id: str = "", academic_year: str = "") -> JSONResponse:
    result = AttendanceService.get_student_summary(
        org_id=_org(request), student_id=student_id,
        course_id=course_id, academic_year=academic_year
    )
    return JSONResponse(content=_jsonify(result))


@router.get("/attendance/course/{course_id}")
@require_permission(Permission.STUDENT_READ)
async def get_course_attendance(request: Request, course_id: str,
                                 academic_year: str = "") -> JSONResponse:
    result = AttendanceService.get_course_summary(
        org_id=_org(request), course_id=course_id, academic_year=academic_year
    )
    return JSONResponse(content=_jsonify({"summary": result, "total": len(result)}))


# =============================================================================
# E05-S07 — Attendance Analytics (AI)
# =============================================================================

@router.get("/analytics/at-risk")
@require_permission(Permission.STUDENT_READ)
async def get_at_risk_students(request: Request, academic_year: str = "",
                                course_id: Optional[str] = None) -> JSONResponse:
    result = AttendanceAnalyticsService.get_at_risk_students(
        org_id=_org(request), academic_year=academic_year, course_id=course_id
    )
    return JSONResponse(content=_jsonify({"at_risk": result, "total": len(result)}))


@router.get("/analytics/insights")
@require_permission(Permission.STUDENT_READ)
async def get_ai_insights(request: Request, academic_year: str = "",
                           course_id: Optional[str] = None) -> JSONResponse:
    result = AttendanceAnalyticsService.generate_ai_insights(
        org_id=_org(request), academic_year=academic_year,
        course_id=course_id, actor_id=_actor(request)
    )
    return JSONResponse(content=_jsonify(result))
