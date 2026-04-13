"""E12 — Alumni & Placement Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlacementType(str, Enum):
    CAMPUS = "CAMPUS"
    OFF_CAMPUS = "OFF_CAMPUS"
    INTERNSHIP = "INTERNSHIP"


class JobType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    INTERNSHIP = "INTERNSHIP"
    CONTRACT = "CONTRACT"


class DriveStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# --- Request models ---


class AlumniProfileCreate(BaseModel):
    name: str
    email: str
    phone: str | None = None
    program: str
    graduation_year: int
    roll_number: str | None = None
    cgpa: float | None = None
    current_employer: str | None = None
    current_designation: str | None = None
    current_location: str | None = None
    linkedin_url: str | None = None
    bio: str | None = None
    is_mentor: bool = False


class AlumniProfileUpdate(BaseModel):
    current_employer: str | None = None
    current_designation: str | None = None
    current_location: str | None = None
    linkedin_url: str | None = None
    bio: str | None = None
    is_mentor: bool | None = None
    phone: str | None = None


class PlacementRecordCreate(BaseModel):
    student_id: str
    academic_year: str
    company_name: str
    role: str
    package_lpa: float | None = None
    placement_type: PlacementType = PlacementType.CAMPUS
    offer_date: str | None = None  # YYYY-MM-DD
    joining_date: str | None = None
    location: str | None = None
    is_ppo: bool = False


class JobPostingCreate(BaseModel):
    title: str
    company_name: str
    description: str
    location: str | None = None
    job_type: JobType = JobType.FULL_TIME
    experience_min: int = 0
    experience_max: int | None = None
    salary_range: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    apply_url: str | None = None
    apply_email: str | None = None
    source: str = "ALUMNI"
    expires_at: str | None = None


class JobApplicationCreate(BaseModel):
    job_id: str
    resume_path: str | None = None
    cover_note: str | None = None
    applicant_type: str = "STUDENT"


class DriveCreate(BaseModel):
    company_name: str
    drive_date: str  # YYYY-MM-DD
    venue: str | None = None
    roles_offered: list[dict[str, Any]] = Field(default_factory=list)
    eligibility: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class MentorshipRequestCreate(BaseModel):
    mentor_id: str
    topic: str
    message: str | None = None
