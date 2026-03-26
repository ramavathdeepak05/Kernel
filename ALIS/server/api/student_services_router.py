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
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.student_services.hostel     import HostelService
from server.student_services.library    import LibraryService
from server.student_services.transport  import TransportService
from server.student_services.counselling import CounsellingService
from server.student_services.models     import (
    HostelBlockCreate, HostelRoomCreate, HostelAllocationCreate, HostelComplaintCreate,
    LibraryBookCreate, BorrowingCreate, ReturnBook,
    TransportRouteCreate, TransportAssignCreate,
    CounsellingSessionCreate, CounsellingReferralCreate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/services", tags=["student_services"])


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
# E09-S01 — Hostel
# ══════════════════════════════════════════════════════════════

@router.post("/hostel/blocks", status_code=201)
@require_permission(Permission.HOSTEL_MANAGE)
async def create_block(request: Request, body: HostelBlockCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=HostelService.create_block(_org(request), body, _actor(request)))


@router.get("/hostel/blocks")
@require_permission(Permission.SERVICE_READ)
async def list_blocks(request: Request) -> JSONResponse:
    items = HostelService.list_blocks(_org(request))
    return JSONResponse(content={"blocks": items, "total": len(items)})


@router.post("/hostel/rooms", status_code=201)
@require_permission(Permission.HOSTEL_MANAGE)
async def create_room(request: Request, body: HostelRoomCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=HostelService.create_room(_org(request), body, _actor(request)))


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
    return JSONResponse(status_code=201,
                        content=HostelService.allocate(_org(request), body, _actor(request)))


@router.post("/hostel/allocations/{allocation_id}/vacate")
@require_permission(Permission.HOSTEL_MANAGE)
async def vacate_room(request: Request, allocation_id: str, body: dict) -> JSONResponse:
    return JSONResponse(content=HostelService.vacate(
        _org(request), allocation_id, body["checkout_date"], _actor(request)
    ))


@router.get("/hostel/allocations/student/{student_id}")
@require_permission(Permission.SERVICE_READ)
async def student_allocation(
    request: Request, student_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    result = HostelService.get_student_allocation(_org(request), student_id, academic_year)
    return JSONResponse(content=result or {})


@router.post("/hostel/complaints", status_code=201)
@require_permission(Permission.SERVICE_READ)
async def file_complaint(request: Request, body: HostelComplaintCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=HostelService.file_complaint(
                            _org(request), _actor(request), body, _actor(request)
                        ))


@router.patch("/hostel/complaints/{complaint_id}")
@require_permission(Permission.HOSTEL_MANAGE)
async def update_complaint(request: Request, complaint_id: str, body: dict) -> JSONResponse:
    return JSONResponse(content=HostelService.update_complaint(
        _org(request), complaint_id, body["status"],
        body.get("resolution_note"), _actor(request)
    ))


@router.get("/hostel/complaints")
@require_permission(Permission.SERVICE_READ)
async def list_complaints(
    request: Request, status: Optional[str] = Query(None)
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
    return JSONResponse(status_code=201,
                        content=LibraryService.add_book(_org(request), body, _actor(request)))


@router.get("/library/books")
@require_permission(Permission.SERVICE_READ)
async def list_books(
    request: Request,
    category: Optional[str] = Query(None),
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
    return JSONResponse(status_code=201,
                        content=LibraryService.issue_book(_org(request), body, _actor(request)))


@router.post("/library/return/{borrowing_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def return_book(request: Request, borrowing_id: str, body: ReturnBook) -> JSONResponse:
    return JSONResponse(content=LibraryService.return_book(
        _org(request), borrowing_id, body, _actor(request)
    ))


@router.get("/library/borrowings/{borrower_id}")
@require_permission(Permission.SERVICE_READ)
async def borrower_history(
    request: Request, borrower_id: str, status: Optional[str] = Query(None)
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
    return JSONResponse(status_code=201,
                        content=TransportService.create_route(_org(request), body, _actor(request)))


@router.get("/transport/routes")
@require_permission(Permission.SERVICE_READ)
async def list_routes(request: Request) -> JSONResponse:
    items = TransportService.list_routes(_org(request))
    return JSONResponse(content={"routes": items, "total": len(items)})


@router.patch("/transport/routes/{route_id}")
@require_permission(Permission.TRANSPORT_MANAGE)
async def update_route(request: Request, route_id: str, body: dict) -> JSONResponse:
    return JSONResponse(content=TransportService.update_route(
        _org(request), route_id, body, _actor(request)
    ))


@router.post("/transport/assign", status_code=201)
@require_permission(Permission.TRANSPORT_MANAGE)
async def assign_transport(request: Request, body: TransportAssignCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=TransportService.assign_student(_org(request), body, _actor(request)))


@router.post("/transport/assign/{assignment_id}/cancel")
@require_permission(Permission.TRANSPORT_MANAGE)
async def cancel_transport(request: Request, assignment_id: str) -> JSONResponse:
    return JSONResponse(content=TransportService.cancel_assignment(
        _org(request), assignment_id, _actor(request)
    ))


@router.get("/transport/student/{student_id}")
@require_permission(Permission.SERVICE_READ)
async def student_transport(
    request: Request, student_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    result = TransportService.get_student_assignment(_org(request), student_id, academic_year)
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
async def create_session(request: Request, body: CounsellingSessionCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=CounsellingService.create_session(
                            _org(request), body, _actor(request)
                        ))


@router.patch("/counselling/sessions/{session_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def update_session(request: Request, session_id: str, body: dict) -> JSONResponse:
    return JSONResponse(content=CounsellingService.update_session(
        _org(request), session_id, body, _actor(request)
    ))


@router.get("/counselling/sessions/student/{student_id}")
@require_permission(Permission.SERVICE_MANAGE)
async def student_sessions(
    request: Request,
    student_id: str,
    include_notes: bool = Query(False),
) -> JSONResponse:
    items = CounsellingService.list_for_student(_org(request), student_id, include_notes)
    return JSONResponse(content={"sessions": items})


@router.get("/counselling/sessions/counsellor")
@require_permission(Permission.SERVICE_MANAGE)
async def counsellor_sessions(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
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
async def create_referral(request: Request, body: CounsellingReferralCreate) -> JSONResponse:
    return JSONResponse(status_code=201,
                        content=CounsellingService.create_referral(
                            _org(request), body, _actor(request)
                        ))


@router.patch("/counselling/referrals/{referral_id}/status")
@require_permission(Permission.SERVICE_MANAGE)
async def update_referral(request: Request, referral_id: str, body: dict) -> JSONResponse:
    return JSONResponse(content=CounsellingService.update_referral_status(
        _org(request), referral_id, body["status"], _actor(request)
    ))


@router.get("/counselling/referrals")
@require_permission(Permission.SERVICE_MANAGE)
async def list_referrals(
    request: Request, status: Optional[str] = Query(None)
) -> JSONResponse:
    items = CounsellingService.list_referrals(_org(request), status)
    return JSONResponse(content={"referrals": items, "total": len(items)})


@router.get("/counselling/summary")
@require_permission(Permission.SERVICE_READ)
async def counselling_summary(request: Request) -> JSONResponse:
    return JSONResponse(content=CounsellingService.summary(_org(request)))
