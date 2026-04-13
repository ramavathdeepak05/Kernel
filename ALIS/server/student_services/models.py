"""E09 — Student Services Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RoomType(str, Enum):
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    TRIPLE = "TRIPLE"
    SHARED = "SHARED"


class ComplaintPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class BorrowerType(str, Enum):
    STUDENT = "STUDENT"
    STAFF = "STAFF"


class SessionType(str, Enum):
    ACADEMIC = "ACADEMIC"
    PERSONAL = "PERSONAL"
    CAREER = "CAREER"
    CRISIS = "CRISIS"


class ReferralUrgency(str, Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    EMERGENCY = "EMERGENCY"


# ── Hostel ────────────────────────────────────────────────────


class HostelBlockCreate(BaseModel):
    name: str
    gender: str = "ANY"
    total_rooms: int = Field(..., ge=1)
    warden_id: str | None = None


class HostelRoomCreate(BaseModel):
    block_id: str
    room_number: str
    room_type: RoomType = RoomType.SHARED
    capacity: int = Field(2, ge=1)
    floor: int = 0
    amenities: list[str] | None = None


class HostelAllocationCreate(BaseModel):
    student_id: str
    room_id: str
    academic_year: str
    check_in_date: str  # YYYY-MM-DD
    notes: str | None = None


class HostelComplaintCreate(BaseModel):
    room_id: str | None = None
    category: str
    description: str = Field(..., min_length=20)
    priority: ComplaintPriority = ComplaintPriority.MEDIUM


# ── Library ───────────────────────────────────────────────────


class LibraryBookCreate(BaseModel):
    isbn: str | None = None
    title: str
    author: str
    publisher: str | None = None
    edition: str | None = None
    year_published: int | None = None
    category: str | None = None
    total_copies: int = Field(1, ge=1)
    location: str | None = None


class BorrowingCreate(BaseModel):
    book_id: str
    borrower_id: str
    borrower_type: BorrowerType = BorrowerType.STUDENT
    due_date: str  # YYYY-MM-DD


class ReturnBook(BaseModel):
    fine_paid: bool = False


# ── Transport ─────────────────────────────────────────────────


class TransportRouteCreate(BaseModel):
    route_name: str
    route_code: str
    stops: list[dict[str, Any]] = []
    vehicle_number: str | None = None
    driver_name: str | None = None
    driver_contact: str | None = None
    capacity: int = Field(40, ge=1)


class TransportAssignCreate(BaseModel):
    student_id: str
    route_id: str
    stop_name: str
    academic_year: str
    valid_from: str
    valid_to: str | None = None


# ── Counselling ───────────────────────────────────────────────


class CounsellingSessionCreate(BaseModel):
    student_id: str
    session_date: str
    session_type: SessionType = SessionType.ACADEMIC
    duration_mins: int = Field(30, ge=10)
    notes: str | None = None
    follow_up_date: str | None = None
    is_confidential: bool = True


class CounsellingReferralCreate(BaseModel):
    student_id: str
    referred_to: str
    reason: str = Field(..., min_length=20)
    urgency: ReferralUrgency = ReferralUrgency.ROUTINE
    notes: str | None = None
