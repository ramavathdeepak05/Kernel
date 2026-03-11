"""E09 — Student Services Models"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RoomType(str, Enum):
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    TRIPLE = "TRIPLE"
    SHARED = "SHARED"


class ComplaintPriority(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    URGENT = "URGENT"


class BorrowerType(str, Enum):
    STUDENT = "STUDENT"
    STAFF   = "STAFF"


class SessionType(str, Enum):
    ACADEMIC = "ACADEMIC"
    PERSONAL = "PERSONAL"
    CAREER   = "CAREER"
    CRISIS   = "CRISIS"


class ReferralUrgency(str, Enum):
    ROUTINE   = "ROUTINE"
    URGENT    = "URGENT"
    EMERGENCY = "EMERGENCY"


# ── Hostel ────────────────────────────────────────────────────

class HostelBlockCreate(BaseModel):
    name:       str
    gender:     str = "ANY"
    total_rooms: int = Field(..., ge=1)
    warden_id:  Optional[str] = None


class HostelRoomCreate(BaseModel):
    block_id:    str
    room_number: str
    room_type:   RoomType = RoomType.SHARED
    capacity:    int = Field(2, ge=1)
    floor:       int = 0
    amenities:   Optional[List[str]] = None


class HostelAllocationCreate(BaseModel):
    student_id:    str
    room_id:       str
    academic_year: str
    check_in_date: str   # YYYY-MM-DD
    notes:         Optional[str] = None


class HostelComplaintCreate(BaseModel):
    room_id:     Optional[str] = None
    category:    str
    description: str = Field(..., min_length=20)
    priority:    ComplaintPriority = ComplaintPriority.MEDIUM


# ── Library ───────────────────────────────────────────────────

class LibraryBookCreate(BaseModel):
    isbn:           Optional[str] = None
    title:          str
    author:         str
    publisher:      Optional[str] = None
    edition:        Optional[str] = None
    year_published: Optional[int] = None
    category:       Optional[str] = None
    total_copies:   int = Field(1, ge=1)
    location:       Optional[str] = None


class BorrowingCreate(BaseModel):
    book_id:       str
    borrower_id:   str
    borrower_type: BorrowerType = BorrowerType.STUDENT
    due_date:      str   # YYYY-MM-DD


class ReturnBook(BaseModel):
    fine_paid: bool = False


# ── Transport ─────────────────────────────────────────────────

class TransportRouteCreate(BaseModel):
    route_name:    str
    route_code:    str
    stops:         List[Dict[str, Any]] = []
    vehicle_number: Optional[str] = None
    driver_name:   Optional[str] = None
    driver_contact: Optional[str] = None
    capacity:      int = Field(40, ge=1)


class TransportAssignCreate(BaseModel):
    student_id:    str
    route_id:      str
    stop_name:     str
    academic_year: str
    valid_from:    str
    valid_to:      Optional[str] = None


# ── Counselling ───────────────────────────────────────────────

class CounsellingSessionCreate(BaseModel):
    student_id:     str
    session_date:   str
    session_type:   SessionType = SessionType.ACADEMIC
    duration_mins:  int = Field(30, ge=10)
    notes:          Optional[str] = None
    follow_up_date: Optional[str] = None
    is_confidential: bool = True


class CounsellingReferralCreate(BaseModel):
    student_id:  str
    referred_to: str
    reason:      str = Field(..., min_length=20)
    urgency:     ReferralUrgency = ReferralUrgency.ROUTINE
    notes:       Optional[str] = None
