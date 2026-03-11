"""E08 — HR & Staff Models"""

from __future__ import annotations
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT  = "CONTRACT"
    VISITING  = "VISITING"


class LeaveStatus(str, Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    CANCELLED = "CANCELLED"


class PayrollComponentType(str, Enum):
    EARNING   = "EARNING"
    DEDUCTION = "DEDUCTION"
    STATUTORY = "STATUTORY"


class CalcType(str, Enum):
    FIXED                 = "FIXED"
    PERCENTAGE_OF_BASIC   = "PERCENTAGE_OF_BASIC"
    PERCENTAGE_OF_GROSS   = "PERCENTAGE_OF_GROSS"


class ReviewType(str, Enum):
    ANNUAL      = "ANNUAL"
    HALF_YEARLY = "HALF_YEARLY"
    PROBATION   = "PROBATION"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT  = "ABSENT"
    HALF_DAY = "HALF_DAY"
    LEAVE   = "LEAVE"
    HOLIDAY = "HOLIDAY"
    WFH     = "WFH"


# --- Request models ---

class StaffProfileCreate(BaseModel):
    user_id:           str
    employee_code:     str
    department:        str
    designation:       str
    employment_type:   EmploymentType = EmploymentType.FULL_TIME
    date_of_joining:   str   # YYYY-MM-DD
    salary_grade:      Optional[str] = None
    reporting_to:      Optional[str] = None
    specializations:   Optional[List[str]] = None
    qualifications:    Optional[List[Dict[str, Any]]] = None
    experience_years:  Optional[int] = None


class StaffProfileUpdate(BaseModel):
    department:       Optional[str] = None
    designation:      Optional[str] = None
    employment_type:  Optional[EmploymentType] = None
    salary_grade:     Optional[str] = None
    reporting_to:     Optional[str] = None
    specializations:  Optional[List[str]] = None
    qualifications:   Optional[List[Dict[str, Any]]] = None
    experience_years: Optional[int] = None


class LeaveTypeCreate(BaseModel):
    name:               str
    code:               str
    annual_quota:       float = Field(..., ge=0)
    carry_forward:      bool = False
    max_carry_forward:  float = 0
    is_paid:            bool = True
    applicable_to:      str = "ALL"


class LeaveRequestCreate(BaseModel):
    leave_type_id: str
    from_date:     str   # YYYY-MM-DD
    to_date:       str
    reason:        str = Field(..., min_length=10)


class LeaveDecision(BaseModel):
    decision:       str   # "APPROVED" | "REJECTED"
    rejection_note: Optional[str] = None


class PayrollComponentCreate(BaseModel):
    name:           str
    code:           str
    component_type: PayrollComponentType = PayrollComponentType.EARNING
    calc_type:      CalcType = CalcType.FIXED
    value:          float = Field(..., ge=0)
    is_taxable:     bool = True


class SalaryStructureCreate(BaseModel):
    staff_id:       str
    basic_salary:   float = Field(..., gt=0)
    components:     List[Dict[str, Any]] = []
    effective_from: str   # YYYY-MM-DD


class PayslipGenerate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year:  int = Field(..., ge=2000)


class PerformanceReviewCreate(BaseModel):
    staff_id:      str
    review_period: str
    review_type:   ReviewType = ReviewType.ANNUAL
    ratings:       Dict[str, float] = {}
    strengths:     Optional[str] = None
    improvements:  Optional[str] = None
    goals_next:    Optional[str] = None


class PerformanceReviewUpdate(BaseModel):
    ratings:       Optional[Dict[str, float]] = None
    strengths:     Optional[str] = None
    improvements:  Optional[str] = None
    goals_next:    Optional[str] = None
    staff_comments: Optional[str] = None
    status:        Optional[str] = None  # SUBMITTED | ACKNOWLEDGED


class StaffAttendanceMark(BaseModel):
    staff_id:  str
    date:      str   # YYYY-MM-DD
    status:    AttendanceStatus = AttendanceStatus.PRESENT
    check_in:  Optional[str] = None   # ISO datetime
    check_out: Optional[str] = None
    remarks:   Optional[str] = None


class StaffAttendanceBulk(BaseModel):
    date:    str
    records: List[StaffAttendanceMark]
