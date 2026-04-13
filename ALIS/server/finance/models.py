"""E07 — Finance Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FeeType(str, Enum):
    TUITION = "TUITION"
    HOSTEL = "HOSTEL"
    EXAM = "EXAM"
    LIBRARY = "LIBRARY"
    TRANSPORT = "TRANSPORT"
    DEVELOPMENT = "DEVELOPMENT"
    MISCELLANEOUS = "MISCELLANEOUS"


class PaymentMethod(str, Enum):
    RAZORPAY = "RAZORPAY"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    DD = "DD"
    NEFT = "NEFT"
    UPI = "UPI"


class ScholarshipType(str, Enum):
    MERIT = "MERIT"
    NEED = "NEED"
    SPORTS = "SPORTS"
    GOVT = "GOVT"
    INSTITUTIONAL = "INSTITUTIONAL"


class DiscountType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class WaiverType(str, Enum):
    PARTIAL = "PARTIAL"
    FULL = "FULL"


# --- Request models ---


class FeeItem(BaseModel):
    label: str
    amount: float = Field(..., gt=0)
    fee_type: FeeType = FeeType.TUITION
    is_optional: bool = False


class FeeStructureCreate(BaseModel):
    program_id: str | None = None  # None = applies to all programs
    academic_year: str
    semester: int | None = None  # None = annual
    fee_items: list[FeeItem]
    currency: str = "INR"


class InvoiceCreate(BaseModel):
    student_id: str
    fee_structure_id: str
    academic_year: str
    semester: int | None = None
    due_date: str  # YYYY-MM-DD
    notes: str | None = None


class InvoiceBulkCreate(BaseModel):
    fee_structure_id: str
    academic_year: str
    semester: int | None = None
    due_date: str
    student_ids: list[str] | None = None  # None = all enrolled in program


class ManualPaymentRecord(BaseModel):
    invoice_id: str
    amount: float = Field(..., gt=0)
    method: PaymentMethod
    reference_number: str | None = None
    bank_name: str | None = None
    cheque_date: str | None = None
    notes: str | None = None


class ScholarshipCreate(BaseModel):
    name: str
    description: str | None = None
    type: ScholarshipType = ScholarshipType.MERIT
    discount_type: DiscountType = DiscountType.PERCENTAGE
    discount_value: float = Field(..., gt=0)
    academic_year: str
    max_recipients: int | None = None
    criteria: dict[str, Any] | None = None


class ScholarshipAssign(BaseModel):
    scholarship_id: str
    student_id: str
    academic_year: str


class FeeWaiverRequest(BaseModel):
    invoice_id: str
    waiver_type: WaiverType = WaiverType.PARTIAL
    waiver_amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=20)


class WaiverDecision(BaseModel):
    decision: str  # "APPROVED" | "REJECTED"
    rejection_note: str | None = None
