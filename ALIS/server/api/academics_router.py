"""E05 — Academics API Router"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request, Response
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
from server.academics.ta_assignment_service import TAAssignmentService

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


@router.delete("/faculty/assignments/{assignment_id}", status_code=204, response_model=None)
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


@router.delete("/timetable/{slot_id}", status_code=204, response_model=None)
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


# ---------------------------------------------------------------------------
# E20 — OBE / CO-PO Mapping Routes (P22)
# ---------------------------------------------------------------------------

@router.post("/obe/program-outcomes")
@require_permission(Permission.ACADEMICS_MANAGE)
async def create_program_outcome(request: Request, body: dict) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.create_program_outcome(
        org_id=_org(request), program_id=body["program_id"], code=body["code"],
        description=body["description"], domain=body.get("domain"), nba_mapping=body.get("nba_mapping"),
    )
    return JSONResponse(content=_jsonify(result), status_code=201)


@router.post("/obe/course-outcomes")
@require_permission(Permission.ACADEMICS_MANAGE)
async def create_course_outcome(request: Request, body: dict) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.create_course_outcome(
        org_id=_org(request), course_id=body["course_id"], code=body["code"],
        description=body["description"], bloom_level=body.get("bloom_level"),
    )
    return JSONResponse(content=_jsonify(result), status_code=201)


@router.post("/obe/mapping")
@require_permission(Permission.ACADEMICS_MANAGE)
async def map_co_to_po(request: Request, body: dict) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.map_co_to_po(
        org_id=_org(request), course_id=body["course_id"], co_id=body["co_id"],
        po_id=body["po_id"], strength=body.get("strength", "M"), justification=body.get("justification"),
    )
    return JSONResponse(content=_jsonify(result), status_code=201)


@router.get("/obe/matrix/{course_id}")
@require_permission(Permission.ACADEMICS_READ)
async def get_co_po_matrix(request: Request, course_id: str) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.get_co_po_matrix(_org(request), course_id)
    return JSONResponse(content=_jsonify(result))


@router.post("/obe/attainment/{course_id}")
@require_permission(Permission.ACADEMICS_MANAGE)
async def compute_attainment(request: Request, course_id: str, body: dict) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.compute_attainment(
        org_id=_org(request), program_id=body["program_id"], course_id=course_id,
        semester_id=body["semester_id"], actor_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


@router.get("/obe/attainment/{program_id}")
@require_permission(Permission.ACADEMICS_READ)
async def get_attainment_report(request: Request, program_id: str) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.get_attainment_report(_org(request), program_id)
    return JSONResponse(content=_jsonify(result))


@router.get("/obe/gap-analysis/{program_id}")
@require_permission(Permission.ACADEMICS_READ)
async def get_gap_analysis(request: Request, program_id: str) -> JSONResponse:
    from server.academics.obe_service import OBEService
    result = OBEService.get_gap_analysis(_org(request), program_id)
    return JSONResponse(content=_jsonify(result))


# =============================================================================
# P26-TA — Teaching Assistant Assignments
# =============================================================================

@router.post("/courses/{course_id}/ta-assignments", status_code=201, tags=["TA Assignments"])
@require_permission(Permission.ACADEMICS_MANAGE)
async def assign_course_ta(request: Request, course_id: str, body: dict) -> JSONResponse:
    """
    Assign a student as TA for a course (semester-long).
    Replaces any existing active course TA — old TA is notified of revocation.
    body.student_identifier: student UUID, roll number, or email.
    body.notes: optional notes (e.g. 'Lab section TA').
    """
    result = TAAssignmentService.assign_course_ta(
        tenant_id=_org(request),
        course_id=course_id,
        faculty_id=_actor(request),
        student_identifier=body["student_identifier"],
        notes=body.get("notes"),
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/courses/{course_id}/ta-assignments", tags=["TA Assignments"])
@require_permission(Permission.ACADEMICS_READ)
async def list_course_tas(request: Request, course_id: str) -> JSONResponse:
    """List active TA assignments for a course."""
    result = TAAssignmentService.list_course_tas(
        tenant_id=_org(request),
        course_id=course_id,
        faculty_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


@router.delete("/courses/{course_id}/ta-assignments/{assignment_id}", tags=["TA Assignments"])
@require_permission(Permission.ACADEMICS_MANAGE)
async def revoke_course_ta(request: Request, course_id: str, assignment_id: str) -> JSONResponse:
    """Revoke a course-level TA assignment. TA is notified via WhatsApp/SMS."""
    result = TAAssignmentService.revoke_course_ta(
        tenant_id=_org(request),
        course_id=course_id,
        assignment_id=assignment_id,
        faculty_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


@router.post("/sessions/{session_ref}/ta-assignments", status_code=201, tags=["TA Assignments"])
@require_permission(Permission.ACADEMICS_MANAGE)
async def assign_session_ta(request: Request, session_ref: str, body: dict) -> JSONResponse:
    """
    Assign a TA for a specific attendance session only (one-time delegation).
    body.student_identifier: student UUID, roll number, or email.
    body.course_id: UUID of the course the session belongs to.
    body.session_type: 'WIFI' (default) or 'MANUAL'.
    """
    result = TAAssignmentService.assign_session_ta(
        tenant_id=_org(request),
        course_id=body.get("course_id", ""),
        session_ref=session_ref,
        session_type=body.get("session_type", "WIFI"),
        faculty_id=_actor(request),
        student_identifier=body["student_identifier"],
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.delete("/sessions/{session_ref}/ta-assignments", tags=["TA Assignments"])
@require_permission(Permission.ACADEMICS_MANAGE)
async def revoke_session_ta(request: Request, session_ref: str) -> JSONResponse:
    """Revoke all TA assignments for a specific attendance session."""
    result = TAAssignmentService.revoke_session_ta(
        tenant_id=_org(request),
        session_ref=session_ref,
        faculty_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


@router.get("/my-ta-assignments", tags=["TA Assignments"])
@require_permission(Permission.STUDENT_READ)
async def get_my_ta_assignments(request: Request) -> JSONResponse:
    """
    Returns all courses where the current user is an active TA.
    Used by mobile/desktop app to show TA's attendance management scope.
    """
    result = TAAssignmentService.get_ta_courses(
        student_id=_actor(request),
        tenant_id=_org(request),
    )
    return JSONResponse(content=_jsonify(result))
