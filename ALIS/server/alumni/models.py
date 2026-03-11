"""E12 — Alumni & Placement Models"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlacementType(str, Enum):
    CAMPUS     = "CAMPUS"
    OFF_CAMPUS = "OFF_CAMPUS"
    INTERNSHIP = "INTERNSHIP"


class JobType(str, Enum):
    FULL_TIME  = "FULL_TIME"
    PART_TIME  = "PART_TIME"
    INTERNSHIP = "INTERNSHIP"
    CONTRACT   = "CONTRACT"


class DriveStatus(str, Enum):
    SCHEDULED  = "SCHEDULED"
    ONGOING    = "ONGOING"
    COMPLETED  = "COMPLETED"
    CANCELLED  = "CANCELLED"


# --- Request models ---

class AlumniProfileCreate(BaseModel):
    name:               str
    email:              str
    phone:              Optional[str] = None
    program:            str
    graduation_year:    int
    roll_number:        Optional[str] = None
    cgpa:               Optional[float] = None
    current_employer:   Optional[str] = None
    current_designation: Optional[str] = None
    current_location:   Optional[str] = None
    linkedin_url:       Optional[str] = None
    bio:                Optional[str] = None
    is_mentor:          bool = False


class AlumniProfileUpdate(BaseModel):
    current_employer:    Optional[str] = None
    current_designation: Optional[str] = None
    current_location:    Optional[str] = None
    linkedin_url:        Optional[str] = None
    bio:                 Optional[str] = None
    is_mentor:           Optional[bool] = None
    phone:               Optional[str] = None


class PlacementRecordCreate(BaseModel):
    student_id:     str
    academic_year:  str
    company_name:   str
    role:           str
    package_lpa:    Optional[float] = None
    placement_type: PlacementType = PlacementType.CAMPUS
    offer_date:     Optional[str] = None   # YYYY-MM-DD
    joining_date:   Optional[str] = None
    location:       Optional[str] = None
    is_ppo:         bool = False


class JobPostingCreate(BaseModel):
    title:            str
    company_name:     str
    description:      str
    location:         Optional[str] = None
    job_type:         JobType = JobType.FULL_TIME
    experience_min:   int = 0
    experience_max:   Optional[int] = None
    salary_range:     Optional[str] = None
    skills_required:  List[str] = Field(default_factory=list)
    apply_url:        Optional[str] = None
    apply_email:      Optional[str] = None
    source:           str = "ALUMNI"
    expires_at:       Optional[str] = None


class JobApplicationCreate(BaseModel):
    job_id:         str
    resume_path:    Optional[str] = None
    cover_note:     Optional[str] = None
    applicant_type: str = "STUDENT"


class DriveCreate(BaseModel):
    company_name:   str
    drive_date:     str                    # YYYY-MM-DD
    venue:          Optional[str] = None
    roles_offered:  List[Dict[str, Any]] = Field(default_factory=list)
    eligibility:    Dict[str, Any] = Field(default_factory=dict)
    description:    Optional[str] = None


class MentorshipRequestCreate(BaseModel):
    mentor_id: str
    topic:     str
    message:   Optional[str] = None
