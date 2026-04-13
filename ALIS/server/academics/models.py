from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DegreeType(str, Enum):
    UG = "UG"
    PG = "PG"
    DIPLOMA = "DIPLOMA"
    CERTIFICATE = "CERTIFICATE"


class CourseType(str, Enum):
    THEORY = "THEORY"
    LAB = "LAB"
    PROJECT = "PROJECT"
    ELECTIVE = "ELECTIVE"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class EnrollmentStatus(str, Enum):
    ENROLLED = "ENROLLED"
    DROPPED = "DROPPED"
    COMPLETED = "COMPLETED"


# --- Request models ---


class ProgramCreate(BaseModel):
    name: str
    code: str
    degree_type: DegreeType
    duration_years: float = Field(..., gt=0)
    total_credits: int | None = None
    metadata: dict[str, Any] = {}


class CourseCreate(BaseModel):
    program_id: str
    name: str
    code: str
    semester: int = Field(..., ge=1, le=10)
    credits: int = Field(default=3, ge=1)
    course_type: CourseType = CourseType.THEORY
    metadata: dict[str, Any] = {}


class FacultyAssignRequest(BaseModel):
    faculty_id: str
    course_id: str
    academic_year: str
    semester: int = Field(..., ge=1)


class TimetableSlotCreate(BaseModel):
    course_id: str
    faculty_id: str | None = None
    academic_year: str
    day_of_week: int = Field(..., ge=1, le=7)
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    room: str | None = None
    slot_type: str = "LECTURE"


class AttendanceMarkRequest(BaseModel):
    course_id: str
    academic_year: str
    session_date: str  # "YYYY-MM-DD"
    slot_type: str = "LECTURE"
    records: list[dict[str, str]]  # [{"student_id": "...", "status": "PRESENT"}]


class StudentEnrollRequest(BaseModel):
    student_id: str
    course_ids: list[str]
    academic_year: str
    semester: int
