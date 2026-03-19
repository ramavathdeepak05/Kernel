"""E12 — Alumni & Placement API Router

Endpoints:
  E12-S01  POST   /alumni/profiles
           GET    /alumni/profiles
           GET    /alumni/profiles/{id}
           PATCH  /alumni/profiles/{id}
           POST   /alumni/profiles/{id}/verify
           GET    /alumni/profiles/stats

  E12-S02  POST   /alumni/placements
           GET    /alumni/placements
           GET    /alumni/placements/student/{student_id}
           GET    /alumni/placements/stats

  E12-S03  POST   /alumni/jobs
           GET    /alumni/jobs
           GET    /alumni/jobs/{id}
           POST   /alumni/jobs/{id}/close
           POST   /alumni/jobs/{id}/apply
           GET    /alumni/jobs/{id}/applications
           PATCH  /alumni/jobs/applications/{id}/status
           GET    /alumni/jobs/applications/mine

  E12-S04  POST   /alumni/drives
           GET    /alumni/drives
           GET    /alumni/drives/{id}
           PATCH  /alumni/drives/{id}/status
           POST   /alumni/drives/{id}/register
           PATCH  /alumni/drives/registrations/{id}/status
           GET    /alumni/drives/{id}/registrations
           GET    /alumni/drives/student/{student_id}

  E12-S05  POST   /alumni/network/connect/{target_id}
           POST   /alumni/network/connections/{id}/respond
           GET    /alumni/network/connections/mine
           GET    /alumni/network/connections/pending
           GET    /alumni/network/mentors
           POST   /alumni/network/mentorship
           POST   /alumni/network/mentorship/{id}/respond
           GET    /alumni/network/mentorship/mine
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.alumni.profiles import AlumniProfileService
from server.alumni.placement import PlacementService
from server.alumni.job_board import JobBoardService
from server.alumni.drives    import RecruitmentDriveService
from server.alumni.network   import AlumniNetworkService
from server.alumni.models    import (
    AlumniProfileCreate, AlumniProfileUpdate,
    PlacementRecordCreate, JobPostingCreate, JobApplicationCreate,
    DriveCreate, MentorshipRequestCreate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/alumni", tags=["alumni"])


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


# ══════════════════════════════════════════════════════════════
# E12-S01 — Alumni Profiles
# ══════════════════════════════════════════════════════════════

@router.post("/profiles", status_code=201)
@require_permission(Permission.ALUMNI_MANAGE)
async def create_profile(request: Request, body: AlumniProfileCreate) -> JSONResponse:
    result = AlumniProfileService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/profiles/stats")
@require_permission(Permission.ALUMNI_READ)
async def alumni_stats(request: Request) -> JSONResponse:
    return JSONResponse(content=AlumniProfileService.statistics(_org(request)))


@router.get("/profiles")
@require_permission(Permission.ALUMNI_READ)
async def list_alumni(
    request: Request,
    program: Optional[str] = Query(None),
    graduation_year: Optional[int] = Query(None),
    is_mentor: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> JSONResponse:
    items = AlumniProfileService.list(
        _org(request), program, graduation_year, is_mentor, limit, offset
    )
    return JSONResponse(content={"alumni": items, "total": len(items)})


@router.get("/profiles/{alumni_id}")
@require_permission(Permission.ALUMNI_READ)
async def get_alumni(request: Request, alumni_id: str) -> JSONResponse:
    return JSONResponse(content=AlumniProfileService.get(_org(request), alumni_id))


@router.patch("/profiles/{alumni_id}")
@require_permission(Permission.ALUMNI_READ)
async def update_profile(request: Request, alumni_id: str, body: AlumniProfileUpdate) -> JSONResponse:
    result = AlumniProfileService.update(_org(request), alumni_id, body, _actor(request))
    return JSONResponse(content=result)


@router.post("/profiles/{alumni_id}/verify")
@require_permission(Permission.ALUMNI_MANAGE)
async def verify_alumni(request: Request, alumni_id: str) -> JSONResponse:
    result = AlumniProfileService.verify(_org(request), alumni_id, _actor(request))
    return JSONResponse(content=result)


# ══════════════════════════════════════════════════════════════
# E12-S02 — Placement Records
# ══════════════════════════════════════════════════════════════

@router.post("/placements", status_code=201)
@require_permission(Permission.PLACEMENT_MANAGE)
async def record_placement(request: Request, body: PlacementRecordCreate) -> JSONResponse:
    result = PlacementService.record(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/placements/stats")
@require_permission(Permission.ALUMNI_READ)
async def placement_stats(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(content=PlacementService.statistics(_org(request), academic_year))


@router.get("/placements")
@require_permission(Permission.ALUMNI_READ)
async def list_placements(
    request: Request,
    academic_year: Optional[str] = Query(None),
    placement_type: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
) -> JSONResponse:
    items = PlacementService.list(_org(request), academic_year, placement_type, company_name)
    return JSONResponse(content={"placements": items, "total": len(items)})


@router.get("/placements/student/{student_id}")
@require_permission(Permission.ALUMNI_READ)
async def student_placements(request: Request, student_id: str) -> JSONResponse:
    items = PlacementService.student_records(_org(request), student_id)
    return JSONResponse(content={"placements": items})


# ══════════════════════════════════════════════════════════════
# E12-S03 — Job Board
# ══════════════════════════════════════════════════════════════

@router.post("/jobs", status_code=201)
@require_permission(Permission.ALUMNI_READ)
async def create_job(request: Request, body: JobPostingCreate) -> JSONResponse:
    result = JobBoardService.create_posting(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/jobs")
@require_permission(Permission.ALUMNI_READ)
async def list_jobs(
    request: Request,
    job_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
) -> JSONResponse:
    items = JobBoardService.list_postings(_org(request), job_type, active_only, search, limit)
    return JSONResponse(content={"jobs": items, "total": len(items)})


@router.get("/jobs/applications/mine")
@require_permission(Permission.ALUMNI_READ)
async def my_job_applications(request: Request) -> JSONResponse:
    items = JobBoardService.my_applications(_org(request), _actor(request))
    return JSONResponse(content={"applications": items})


@router.get("/jobs/{job_id}")
@require_permission(Permission.ALUMNI_READ)
async def get_job(request: Request, job_id: str) -> JSONResponse:
    return JSONResponse(content=JobBoardService.get_posting(_org(request), job_id))


@router.post("/jobs/{job_id}/close")
@require_permission(Permission.ALUMNI_MANAGE)
async def close_job(request: Request, job_id: str) -> JSONResponse:
    return JSONResponse(content=JobBoardService.close_posting(_org(request), job_id, _actor(request)))


@router.post("/jobs/{job_id}/apply", status_code=201)
@require_permission(Permission.ALUMNI_READ)
async def apply_to_job(request: Request, job_id: str, body: JobApplicationCreate) -> JSONResponse:
    body.job_id = job_id
    result = JobBoardService.apply(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/jobs/{job_id}/applications")
@require_permission(Permission.ALUMNI_MANAGE)
async def job_applications(request: Request, job_id: str) -> JSONResponse:
    items = JobBoardService.list_applications(_org(request), job_id)
    return JSONResponse(content={"applications": items, "total": len(items)})


@router.patch("/jobs/applications/{application_id}/status")
@require_permission(Permission.ALUMNI_MANAGE)
async def update_application(request: Request, application_id: str, body: dict) -> JSONResponse:
    result = JobBoardService.update_application_status(
        _org(request), application_id, body["status"], _actor(request)
    )
    return JSONResponse(content=result)


# ══════════════════════════════════════════════════════════════
# E12-S04 — Recruitment Drives
# ══════════════════════════════════════════════════════════════

@router.post("/drives", status_code=201)
@require_permission(Permission.PLACEMENT_MANAGE)
async def create_drive(request: Request, body: DriveCreate) -> JSONResponse:
    result = RecruitmentDriveService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/drives")
@require_permission(Permission.ALUMNI_READ)
async def list_drives(
    request: Request, status: Optional[str] = Query(None)
) -> JSONResponse:
    items = RecruitmentDriveService.list(_org(request), status)
    return JSONResponse(content={"drives": items, "total": len(items)})


@router.get("/drives/student/{student_id}")
@require_permission(Permission.ALUMNI_READ)
async def student_drives(request: Request, student_id: str) -> JSONResponse:
    items = RecruitmentDriveService.student_drives(_org(request), student_id)
    return JSONResponse(content={"drives": items})


@router.get("/drives/{drive_id}")
@require_permission(Permission.ALUMNI_READ)
async def get_drive(request: Request, drive_id: str) -> JSONResponse:
    return JSONResponse(content=RecruitmentDriveService.get(_org(request), drive_id))


@router.patch("/drives/{drive_id}/status")
@require_permission(Permission.PLACEMENT_MANAGE)
async def update_drive_status(request: Request, drive_id: str, body: dict) -> JSONResponse:
    result = RecruitmentDriveService.update_status(
        _org(request), drive_id, body["status"], _actor(request)
    )
    return JSONResponse(content=result)


@router.post("/drives/{drive_id}/register", status_code=201)
@require_permission(Permission.ALUMNI_READ)
async def register_for_drive(request: Request, drive_id: str) -> JSONResponse:
    result = RecruitmentDriveService.register_student(_org(request), drive_id, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.patch("/drives/registrations/{registration_id}/status")
@require_permission(Permission.PLACEMENT_MANAGE)
async def update_registration(request: Request, registration_id: str, body: dict) -> JSONResponse:
    result = RecruitmentDriveService.update_registration_status(
        _org(request), registration_id, body["status"], _actor(request)
    )
    return JSONResponse(content=result)


@router.get("/drives/{drive_id}/registrations")
@require_permission(Permission.PLACEMENT_MANAGE)
async def drive_registrations(request: Request, drive_id: str) -> JSONResponse:
    items = RecruitmentDriveService.list_registrations(_org(request), drive_id)
    return JSONResponse(content={"registrations": items, "total": len(items)})


# ══════════════════════════════════════════════════════════════
# E12-S05 — Alumni Network
# ══════════════════════════════════════════════════════════════

@router.post("/network/connect/{target_id}", status_code=201)
@require_permission(Permission.ALUMNI_READ)
async def send_connection(request: Request, target_id: str) -> JSONResponse:
    result = AlumniNetworkService.send_connection_request(
        _org(request), _actor(request), target_id
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/network/connections/{connection_id}/respond")
@require_permission(Permission.ALUMNI_READ)
async def respond_connection(request: Request, connection_id: str, body: dict) -> JSONResponse:
    result = AlumniNetworkService.respond_connection(
        _org(request), connection_id, body["accept"], _actor(request)
    )
    return JSONResponse(content=result)


@router.get("/network/connections/mine")
@require_permission(Permission.ALUMNI_READ)
async def my_connections(request: Request) -> JSONResponse:
    items = AlumniNetworkService.my_connections(_org(request), _actor(request))
    return JSONResponse(content={"connections": items})


@router.get("/network/connections/pending")
@require_permission(Permission.ALUMNI_READ)
async def pending_connections(request: Request) -> JSONResponse:
    items = AlumniNetworkService.pending_requests(_org(request), _actor(request))
    return JSONResponse(content={"pending": items})


@router.get("/network/mentors")
@require_permission(Permission.ALUMNI_READ)
async def list_mentors(
    request: Request, program: Optional[str] = Query(None)
) -> JSONResponse:
    items = AlumniNetworkService.list_mentors(_org(request), program)
    return JSONResponse(content={"mentors": items, "total": len(items)})


@router.post("/network/mentorship", status_code=201)
@require_permission(Permission.ALUMNI_READ)
async def request_mentorship(request: Request, body: MentorshipRequestCreate) -> JSONResponse:
    result = AlumniNetworkService.request_mentorship(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.post("/network/mentorship/{request_id}/respond")
@require_permission(Permission.ALUMNI_READ)
async def respond_mentorship(request: Request, request_id: str, body: dict) -> JSONResponse:
    result = AlumniNetworkService.respond_mentorship(
        _org(request), request_id,
        accept=body["accept"],
        session_date=body.get("session_date"),
        actor_alumni_id=_actor(request),
    )
    return JSONResponse(content=result)


@router.get("/network/mentorship/mine")
@require_permission(Permission.ALUMNI_READ)
async def my_mentorship(request: Request) -> JSONResponse:
    items = AlumniNetworkService.my_mentorship_requests(_org(request), _actor(request))
    return JSONResponse(content={"requests": items})
