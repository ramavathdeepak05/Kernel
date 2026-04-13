"""E09 — Student Services API Router

Endpoints:
  E09-S01 Hostel
    POST   /services/hostel/blocks
    GET    /services/hostel/blocks
    POST   /services/hostel/rooms
    GET    /services/hostel/rooms/{block_id}
    POST   /services/hostel/allocations
    POST   /services/hostel/allocations/{id}/vacate
    GET    /services/hostel/allocations/student/{student_id}
    POST   /services/hostel/complaints
    PATCH  /services/hostel/complaints/{id}
    GET    /services/hostel/complaints
    GET    /services/hostel/occupancy

  E09-S02 Library
    POST   /services/library/books
    GET    /services/library/books
    GET    /services/library/books/search
    GET    /services/library/books/{id}
    POST   /services/library/borrow
    POST   /services/library/return/{id}
    GET    /services/library/borrowings/{borrower_id}
    GET    /services/library/overdue
    GET    /services/library/summary

  E09-S03 Transport
    POST   /services/transport/routes
    GET    /services/transport/routes
    PATCH  /services/transport/routes/{id}
    POST   /services/transport/assign
    POST   /services/transport/assign/{id}/cancel
    GET    /services/transport/student/{student_id}
    GET    /services/transport/routes/{id}/students

  E09-S04 Counselling
    POST   /services/counselling/sessions
    PATCH  /services/counselling/sessions/{id}
    GET    /services/counselling/sessions/student/{student_id}
    GET    /services/counselling/sessions/counsellor
    GET    /services/counselling/follow-ups
    POST   /services/counselling/referrals
    PATCH  /services/counselling/referrals/{id}/status
    GET    /services/counselling/referrals
    GET    /services/counselling/summary

  SS-3 Placement Drive Management (EC-SS-02/03)
    POST   /services/placement/drives
    GET    /services/placement/drives
    GET    /services/placement/drives/{drive_id}
    POST   /services/placement/drives/{drive_id}/open
    POST   /services/placement/drives/{drive_id}/register
    POST   /services/placement/drives/{drive_id}/offer-accepted
    GET    /services/placement/drives/{drive_id}/registrations
    GET    /services/placement/student/{student_id}/status

    POST   /services/placement/offer-revocations          (EC-SS-02)
    GET    /services/placement/offer-revocations/pending
    POST   /services/placement/offer-revocations/{id}/verify

    POST   /services/placement/verbal-locks              (EC-SS-03)
    POST   /services/placement/verbal-locks/expire-overdue
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from server.core.rbac import Permission, require_permission
from server.student_services.counselling import CounsellingService
from server.student_services.hostel import HostelService
from server.student_services.library import LibraryService
from server.student_services.models import (
    BorrowingCreate,
    CounsellingReferralCreate,
    CounsellingSessionCreate,
    HostelAllocationCreate,
    HostelBlockCreate,
    HostelComplaintCreate,
    HostelRoomCreate,
    LibraryBookCreate,
    ReturnBook,
    TransportAssignCreate,
    TransportRouteCreate,
)
from server.student_services.transport import TransportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/services", tags=["student_services"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


def _jsonify(obj):
    """Recursively convert Decimal/date/datetime/time to JSON-safe types."""
    from datetime import date, datetime
    from datetime import time as _time
    from decimal import Decimal

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
# E09-S01 — Hostel
# ══════════════════════════════════════════════════════════════


@router.post("/hostel/blocks", status_code=201)
@require_permission(Permission.HOSTEL_MANAGE)
async def create_block(request: Request, body: HostelBlockCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=HostelService.create_block(_org(request), body, _actor(request)),
    )


@router.get("/hostel/blocks")
@require_permission(Permission.SERVICE_READ)
async def list_blocks(request: Request) -> JSONResponse:
    items = HostelService.list_blocks(_org(request))
    return JSONResponse(content={"blocks": items, "total": len(items)})


@router.post("/hostel/rooms", status_code=201)
@require_permission(Permission.HOSTEL_MANAGE)
async def create_room(request: Request, body: HostelRoomCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=HostelService.create_room(_org(request), body, _actor(request)),
    )


@router.get("/hostel/rooms/{block_id}")
@require_permission(Permission.SERVICE_READ)
async def list_rooms(
    request: Request, block_id: str, available_only: bool = Query(False)
) -> JSONResponse:
    items = HostelService.list_rooms(_org(request), block_id, available_only)
    return JSONResponse(content={"rooms": items, "total": len(items)})


@router.post("/hostel/allocations", status_code=201)
@require_permission(Permission.HOSTEL_MANAGE)
async def allocate_room(request: Request, body: HostelAllocationCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=HostelService.allocate(_org(request), body, _actor(request)),
    )


@router.post("/hostel/allocations/{allocation_id}/vacate")
@require_permission(Permission.HOSTEL_MANAGE)
async def vacate_room(request: Request, allocation_id: str, body: dict) -> JSONResponse:
    return JSONResponse(
        content=HostelService.vacate(
            _org(request), allocation_id, body["checkout_date"], _actor(request)
        )
    )


@router.get("/hostel/allocations/student/{student_id}")
@require_permission(Permission.SERVICE_READ)
async def student_allocation(
    request: Request, student_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    result = HostelService.get_student_allocation(
        _org(request), student_id, academic_year
    )
    return JSONResponse(content=result or {})


@router.post("/hostel/complaints", status_code=201)
@require_permission(Permission.SERVICE_READ)
async def file_complaint(request: Request, body: HostelComplaintCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=HostelService.file_complaint(
            _org(request), _actor(request), body, _actor(request)
        ),
    )


@router.patch("/hostel/complaints/{complaint_id}")
@require_permission(Permission.HOSTEL_MANAGE)
async def update_complaint(
    request: Request, complaint_id: str, body: dict
) -> JSONResponse:
    return JSONResponse(
        content=HostelService.update_complaint(
            _org(request),
            complaint_id,
            body["status"],
            body.get("resolution_note"),
            _actor(request),
        )
    )


@router.get("/hostel/complaints")
@require_permission(Permission.SERVICE_READ)
async def list_complaints(
    request: Request, status: str | None = Query(None)
) -> JSONResponse:
    items = HostelService.list_complaints(_org(request), status)
    return JSONResponse(content={"complaints": items, "total": len(items)})


@router.get("/hostel/occupancy")
@require_permission(Permission.SERVICE_READ)
async def hostel_occupancy(request: Request) -> JSONResponse:
    items = HostelService.occupancy_summary(_org(request))
    return JSONResponse(content={"blocks": items})


# ══════════════════════════════════════════════════════════════
# E09-S02 — Library
# ══════════════════════════════════════════════════════════════


@router.post("/library/books", status_code=201)
@require_permission(Permission.SERVICE_MANAGE)
async def add_book(request: Request, body: LibraryBookCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=LibraryService.add_book(_org(request), body, _actor(request)),
    )


@router.get("/library/books")
@require_permission(Permission.SERVICE_READ)
async def list_books(
    request: Request,
    category: str | None = Query(None),
    available_only: bool = Query(False),
) -> JSONResponse:
    items = LibraryService.list_books(_org(request), category, available_only)
    return JSONResponse(content={"books": items, "total": len(items)})


@router.get("/library/books/search")
@require_permission(Permission.SERVICE_READ)
async def search_books(request: Request, q: str = Query(...)) -> JSONResponse:
    items = LibraryService.search(_org(request), q)
    return JSONResponse(content={"books": items, "total": len(items)})


@router.get("/library/books/{book_id}")
@require_permission(Permission.SERVICE_READ)
async def get_book(request: Request, book_id: str) -> JSONResponse:
    return JSONResponse(content=LibraryService.get_book(_org(request), book_id))


@router.post("/library/borrow", status_code=201)
@require_permission(Permission.SERVICE_MANAGE)
async def borrow_book(request: Request, body: BorrowingCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=LibraryService.issue_book(_org(request), body, _actor(request)),
    )


@router.post("/library/return/{borrowing_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def return_book(
    request: Request, borrowing_id: str, body: ReturnBook
) -> JSONResponse:
    return JSONResponse(
        content=LibraryService.return_book(
            _org(request), borrowing_id, body, _actor(request)
        )
    )


@router.get("/library/borrowings/{borrower_id}")
@require_permission(Permission.SERVICE_READ)
async def borrower_history(
    request: Request, borrower_id: str, status: str | None = Query(None)
) -> JSONResponse:
    items = LibraryService.list_for_borrower(_org(request), borrower_id, status)
    return JSONResponse(content={"borrowings": items})


@router.get("/library/overdue")
@require_permission(Permission.SERVICE_MANAGE)
async def overdue_books(request: Request) -> JSONResponse:
    items = LibraryService.list_overdue(_org(request))
    return JSONResponse(content={"overdue": items, "total": len(items)})


@router.get("/library/summary")
@require_permission(Permission.SERVICE_READ)
async def library_summary(request: Request) -> JSONResponse:
    return JSONResponse(content=LibraryService.summary(_org(request)))


# ══════════════════════════════════════════════════════════════
# E09-S03 — Transport
# ══════════════════════════════════════════════════════════════


@router.post("/transport/routes", status_code=201)
@require_permission(Permission.TRANSPORT_MANAGE)
async def create_route(request: Request, body: TransportRouteCreate) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=TransportService.create_route(_org(request), body, _actor(request)),
    )


@router.get("/transport/routes")
@require_permission(Permission.SERVICE_READ)
async def list_routes(request: Request) -> JSONResponse:
    items = TransportService.list_routes(_org(request))
    return JSONResponse(content={"routes": items, "total": len(items)})


@router.patch("/transport/routes/{route_id}")
@require_permission(Permission.TRANSPORT_MANAGE)
async def update_route(request: Request, route_id: str, body: dict) -> JSONResponse:
    return JSONResponse(
        content=TransportService.update_route(
            _org(request), route_id, body, _actor(request)
        )
    )


@router.post("/transport/assign", status_code=201)
@require_permission(Permission.TRANSPORT_MANAGE)
async def assign_transport(
    request: Request, body: TransportAssignCreate
) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=TransportService.assign_student(_org(request), body, _actor(request)),
    )


@router.post("/transport/assign/{assignment_id}/cancel")
@require_permission(Permission.TRANSPORT_MANAGE)
async def cancel_transport(request: Request, assignment_id: str) -> JSONResponse:
    return JSONResponse(
        content=TransportService.cancel_assignment(
            _org(request), assignment_id, _actor(request)
        )
    )


@router.get("/transport/student/{student_id}")
@require_permission(Permission.SERVICE_READ)
async def student_transport(
    request: Request, student_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    result = TransportService.get_student_assignment(
        _org(request), student_id, academic_year
    )
    return JSONResponse(content=result or {})


@router.get("/transport/routes/{route_id}/students")
@require_permission(Permission.SERVICE_READ)
async def route_students(
    request: Request, route_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    items = TransportService.list_route_students(_org(request), route_id, academic_year)
    return JSONResponse(content={"students": items, "total": len(items)})


# ══════════════════════════════════════════════════════════════
# E09-S04 — Counselling
# ══════════════════════════════════════════════════════════════


@router.post("/counselling/sessions", status_code=201)
@require_permission(Permission.SERVICE_MANAGE)
async def create_session(
    request: Request, body: CounsellingSessionCreate
) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=CounsellingService.create_session(_org(request), body, _actor(request)),
    )


@router.patch("/counselling/sessions/{session_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def update_session(request: Request, session_id: str, body: dict) -> JSONResponse:
    return JSONResponse(
        content=CounsellingService.update_session(
            _org(request), session_id, body, _actor(request)
        )
    )


@router.get("/counselling/sessions/student/{student_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def student_sessions(
    request: Request,
    student_id: str,
    include_notes: bool = Query(False),
) -> JSONResponse:
    items = CounsellingService.list_for_student(
        _org(request), student_id, include_notes
    )
    return JSONResponse(content={"sessions": items})


@router.get("/counselling/sessions/counsellor")
@require_permission(Permission.SERVICE_MANAGE)
async def counsellor_sessions(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> JSONResponse:
    items = CounsellingService.list_for_counsellor(
        _org(request), _actor(request), date_from, date_to
    )
    return JSONResponse(content={"sessions": items})


@router.get("/counselling/follow-ups")
@require_permission(Permission.SERVICE_MANAGE)
async def follow_ups(request: Request) -> JSONResponse:
    items = CounsellingService.upcoming_follow_ups(_org(request), _actor(request))
    return JSONResponse(content={"follow_ups": items})


@router.post("/counselling/referrals", status_code=201)
@require_permission(Permission.SERVICE_MANAGE)
async def create_referral(
    request: Request, body: CounsellingReferralCreate
) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=CounsellingService.create_referral(
            _org(request), body, _actor(request)
        ),
    )


@router.patch("/counselling/referrals/{referral_id}/status")
@require_permission(Permission.SERVICE_MANAGE)
async def update_referral(
    request: Request, referral_id: str, body: dict
) -> JSONResponse:
    return JSONResponse(
        content=CounsellingService.update_referral_status(
            _org(request), referral_id, body["status"], _actor(request)
        )
    )


@router.get("/counselling/referrals")
@require_permission(Permission.SERVICE_MANAGE)
async def list_referrals(
    request: Request, status: str | None = Query(None)
) -> JSONResponse:
    items = CounsellingService.list_referrals(_org(request), status)
    return JSONResponse(content={"referrals": items, "total": len(items)})


@router.get("/counselling/summary")
@require_permission(Permission.SERVICE_READ)
async def counselling_summary(request: Request) -> JSONResponse:
    return JSONResponse(content=CounsellingService.summary(_org(request)))


# ══════════════════════════════════════════════════════════════
# SS-3 — Placement Drive Management (EC-SS-02/03)
# ══════════════════════════════════════════════════════════════

from server.alumni.placement_drives import (  # noqa: E402
    DriveCreate as PlacementDriveCreate,
)
from server.alumni.placement_drives import (  # noqa: E402
    OfferRevocationCreate,
    OfferRevocationService,
    PlacementDriveService,
    VerbalLockCreate,
    VerbalLockService,
)


@router.post("/placement/drives", status_code=201)
@require_permission(Permission.PLACEMENT_MANAGE)
async def create_placement_drive(
    request: Request, body: PlacementDriveCreate
) -> JSONResponse:
    result = PlacementDriveService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/placement/drives")
@require_permission(Permission.PLACEMENT_MANAGE)
async def list_placement_drives(
    request: Request,
    status: str | None = Query(None),
    drive_type: str | None = Query(None),
) -> JSONResponse:
    items = PlacementDriveService.list(_org(request), status, drive_type)
    return JSONResponse(content=_jsonify({"drives": items, "total": len(items)}))


@router.get("/placement/drives/{drive_id}")
@require_permission(Permission.PLACEMENT_MANAGE)
async def get_placement_drive(request: Request, drive_id: str) -> JSONResponse:
    return JSONResponse(
        content=_jsonify(PlacementDriveService.get(_org(request), drive_id))
    )


@router.post("/placement/drives/{drive_id}/open")
@require_permission(Permission.PLACEMENT_MANAGE)
async def open_placement_drive(request: Request, drive_id: str) -> JSONResponse:
    result = PlacementDriveService.open_drive(_org(request), drive_id, _actor(request))
    return JSONResponse(content=_jsonify(result))


@router.post("/placement/drives/{drive_id}/register", status_code=201)
@require_permission(Permission.SERVICE_READ)
async def register_for_placement_drive(
    request: Request,
    drive_id: str,
    student_id: str | None = Query(None),
) -> JSONResponse:
    sid = student_id or _actor(request)
    result = PlacementDriveService.register_student(
        _org(request), drive_id, sid, _actor(request)
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.post("/placement/drives/{drive_id}/offer-accepted")
@require_permission(Permission.PLACEMENT_MANAGE)
async def record_offer_accepted(
    request: Request, drive_id: str, body: dict
) -> JSONResponse:
    result = PlacementDriveService.record_offer_accepted(
        _org(request),
        drive_id,
        student_id=body["student_id"],
        ctc_lpa=float(body.get("ctc_lpa", 0)),
        offer_letter_url=body.get("offer_letter_url"),
        actor_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


@router.get("/placement/student/{student_id}/status")
@require_permission(Permission.SERVICE_READ)
async def student_placement_status(request: Request, student_id: str) -> JSONResponse:
    from server.db_service import execute_query as _eq

    rows = _eq(
        "SELECT * FROM student_placement_status WHERE org_id = %s AND student_id = %s",
        (_org(request), student_id),
    )
    return JSONResponse(
        content=_jsonify(
            dict(rows[0])
            if rows
            else {
                "student_id": student_id,
                "profile_active": False,
                "student_offer_locked": False,
            }
        )
    )


# EC-SS-02 — Offer Revocation


@router.post("/placement/offer-revocations", status_code=201)
@require_permission(Permission.SERVICE_READ)
async def submit_offer_revocation(
    request: Request, body: OfferRevocationCreate
) -> JSONResponse:
    result = OfferRevocationService.submit_revocation(
        _org(request), body, _actor(request)
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/placement/offer-revocations/pending")
@require_permission(Permission.PLACEMENT_MANAGE)
async def pending_offer_revocations(request: Request) -> JSONResponse:
    items = OfferRevocationService.list_pending(_org(request))
    return JSONResponse(content=_jsonify({"revocations": items, "total": len(items)}))


@router.post("/placement/offer-revocations/{revocation_id}/verify")
@require_permission(Permission.PLACEMENT_MANAGE)
async def verify_offer_revocation(
    request: Request, revocation_id: str, body: dict
) -> JSONResponse:
    result = OfferRevocationService.tpo_verify(
        _org(request),
        revocation_id,
        approved=bool(body.get("approved", False)),
        actor_id=_actor(request),
    )
    return JSONResponse(content=_jsonify(result))


# EC-SS-03 — Verbal Offer Lock


@router.post("/placement/verbal-locks", status_code=201)
@require_permission(Permission.PLACEMENT_MANAGE)
async def create_verbal_lock(request: Request, body: VerbalLockCreate) -> JSONResponse:
    result = VerbalLockService.create_lock(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.post("/placement/verbal-locks/expire-overdue")
@require_permission(Permission.PLACEMENT_MANAGE)
async def expire_overdue_verbal_locks(request: Request) -> JSONResponse:
    count = VerbalLockService.expire_overdue_locks(_org(request))
    return JSONResponse(content={"expired_count": count})
