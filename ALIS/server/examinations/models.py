"""E06 — Examinations & Grades Models (Layer 1)"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExamType(str, Enum):
    SEMESTER_END = "SEMESTER_END"
    MID_TERM     = "MID_TERM"
    INTERNAL     = "INTERNAL"


class ExamStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ONGOING   = "ONGOING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReEvalStatus(str, Enum):
    PENDING      = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVISED      = "REVISED"
    REJECTED     = "REJECTED"


# --- Request models ---

class ExamScheduleCreate(BaseModel):
    course_id: str
    academic_year: str
    semester: int = Field(..., ge=1)
    exam_type: ExamType = ExamType.SEMESTER_END
    exam_date: str          # "YYYY-MM-DD"
    start_time: str         # "HH:MM"
    end_time: str           # "HH:MM"
    venue: Optional[str] = None
    max_marks: int = 100
    pass_marks: int = 40


class GradeEntryItem(BaseModel):
    student_id: str
    marks_obtained: Optional[float] = None
    is_absent: bool = False


class GradesBulkEntry(BaseModel):
    exam_schedule_id: str
    academic_year: str
    semester: int
    entries: List[GradeEntryItem]


class ReEvalRequest(BaseModel):
    grade_id: str
    reason: str = Field(..., min_length=20)


class ReEvalDecision(BaseModel):
    revised_marks: Optional[float] = None
    review_note: str
    decision: str  # "REVISED" | "REJECTED"
