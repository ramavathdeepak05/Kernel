"""E05 — Academics Entity Models (Layer 1)"""

from __future__ import annotations
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DegreeType(str, Enum):
    UG          = "UG"
    PG          = "PG"
    DIPLOMA     = "DIPLOMA"
    CERTIFICATE = "CERTIFICATE"


class CourseType(str, Enum):
    THEORY   = "THEORY"
    LAB      = "LAB"
    PROJECT  = "PROJECT"
    ELECTIVE = "ELECTIVE"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT  = "ABSENT"
    LATE    = "LATE"
    EXCUSED = "EXCUSED"


class EnrollmentStatus(str, Enum):
    ENROLLED  = "ENROLLED"
    DROPPED   = "DROPPED"
    COMPLETED = "COMPLETED"


# --- Request models ---

class ProgramCreate(BaseModel):
    name: str
    code: str
    degree_type: DegreeType
    duration_years: float = Field(..., gt=0)
    total_credits: Optional[int] = None
    metadata: Dict[str, Any] = {}


class CourseCreate(BaseModel):
    program_id: str
    name: str
    code: str
    semester: int = Field(..., ge=1, le=10)
    credits: int = Field(default=3, ge=1)
    course_type: CourseType = CourseType.THEORY
    metadata: Dict[str, Any] = {}


class FacultyAssignRequest(BaseModel):
    faculty_id: str
    course_id: str
    academic_year: str
    semester: int = Field(..., ge=1)


class TimetableSlotCreate(BaseModel):
    course_id: str
    faculty_id: Optional[str] = None
    academic_year: str
    day_of_week: int = Field(..., ge=1, le=7)
    start_time: str   # "HH:MM"
    end_time: str     # "HH:MM"
    room: Optional[str] = None
    slot_type: str = "LECTURE"


class AttendanceMarkRequest(BaseModel):
    course_id: str
    academic_year: str
    session_date: str   # "YYYY-MM-DD"
    slot_type: str = "LECTURE"
    records: List[Dict[str, str]]  # [{"student_id": "...", "status": "PRESENT"}]


class StudentEnrollRequest(BaseModel):
    student_id: str
    course_ids: List[str]
    academic_year: str
    semester: int
