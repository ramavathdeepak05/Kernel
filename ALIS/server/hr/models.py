"""E08 — HR & Staff Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    VISITING = "VISITING"


class LeaveStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PayrollComponentType(str, Enum):
    EARNING = "EARNING"
    DEDUCTION = "DEDUCTION"
    STATUTORY = "STATUTORY"


class CalcType(str, Enum):
    FIXED = "FIXED"
    PERCENTAGE_OF_BASIC = "PERCENTAGE_OF_BASIC"
    PERCENTAGE_OF_GROSS = "PERCENTAGE_OF_GROSS"


class ReviewType(str, Enum):
    ANNUAL = "ANNUAL"
    HALF_YEARLY = "HALF_YEARLY"
    PROBATION = "PROBATION"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    LEAVE = "LEAVE"
    HOLIDAY = "HOLIDAY"
    WFH = "WFH"


# --- Request models ---


class StaffProfileCreate(BaseModel):
    user_id: str
    employee_code: str
    department: str
    designation: str
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    date_of_joining: str  # YYYY-MM-DD
    salary_grade: str | None = None
    reporting_to: str | None = None
    specializations: list[str] | None = None
    qualifications: list[dict[str, Any]] | None = None
    experience_years: int | None = None


class StaffProfileUpdate(BaseModel):
    department: str | None = None
    designation: str | None = None
    employment_type: EmploymentType | None = None
    salary_grade: str | None = None
    reporting_to: str | None = None
    specializations: list[str] | None = None
    qualifications: list[dict[str, Any]] | None = None
    experience_years: int | None = None


class LeaveTypeCreate(BaseModel):
    name: str
    code: str
    annual_quota: float = Field(..., ge=0)
    carry_forward: bool = False
    max_carry_forward: float = 0
    is_paid: bool = True
    applicable_to: str = "ALL"


class LeaveRequestCreate(BaseModel):
    leave_type_id: str
    from_date: str  # YYYY-MM-DD
    to_date: str
    reason: str = Field(..., min_length=10)


class LeaveDecision(BaseModel):
    decision: str  # "APPROVED" | "REJECTED"
    rejection_note: str | None = None


class PayrollComponentCreate(BaseModel):
    name: str
    code: str
    component_type: PayrollComponentType = PayrollComponentType.EARNING
    calc_type: CalcType = CalcType.FIXED
    value: float = Field(..., ge=0)
    is_taxable: bool = True


class SalaryStructureCreate(BaseModel):
    staff_id: str
    basic_salary: float = Field(..., gt=0)
    components: list[dict[str, Any]] = []
    effective_from: str  # YYYY-MM-DD


class PayslipGenerate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000)


class PerformanceReviewCreate(BaseModel):
    staff_id: str
    review_period: str
    review_type: ReviewType = ReviewType.ANNUAL
    ratings: dict[str, float] = {}
    strengths: str | None = None
    improvements: str | None = None
    goals_next: str | None = None


class PerformanceReviewUpdate(BaseModel):
    ratings: dict[str, float] | None = None
    strengths: str | None = None
    improvements: str | None = None
    goals_next: str | None = None
    staff_comments: str | None = None
    status: str | None = None  # SUBMITTED | ACKNOWLEDGED


class StaffAttendanceMark(BaseModel):
    staff_id: str
    date: str  # YYYY-MM-DD
    status: AttendanceStatus = AttendanceStatus.PRESENT
    check_in: str | None = None  # ISO datetime
    check_out: str | None = None
    remarks: str | None = None


class StaffAttendanceBulk(BaseModel):
    date: str
    records: list[StaffAttendanceMark]
