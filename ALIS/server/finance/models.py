"""E07 — Finance Models"""

from __future__ import annotations
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FeeType(str, Enum):
    TUITION       = "TUITION"
    HOSTEL        = "HOSTEL"
    EXAM          = "EXAM"
    LIBRARY       = "LIBRARY"
    TRANSPORT     = "TRANSPORT"
    DEVELOPMENT   = "DEVELOPMENT"
    MISCELLANEOUS = "MISCELLANEOUS"


class PaymentMethod(str, Enum):
    RAZORPAY = "RAZORPAY"
    CASH     = "CASH"
    CHEQUE   = "CHEQUE"
    DD       = "DD"
    NEFT     = "NEFT"
    UPI      = "UPI"


class ScholarshipType(str, Enum):
    MERIT         = "MERIT"
    NEED          = "NEED"
    SPORTS        = "SPORTS"
    GOVT          = "GOVT"
    INSTITUTIONAL = "INSTITUTIONAL"


class DiscountType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED      = "FIXED"


class WaiverType(str, Enum):
    PARTIAL = "PARTIAL"
    FULL    = "FULL"


# --- Request models ---

class FeeItem(BaseModel):
    label:       str
    amount:      float = Field(..., gt=0)
    fee_type:    FeeType = FeeType.TUITION
    is_optional: bool = False


class FeeStructureCreate(BaseModel):
    program_id:    Optional[str] = None   # None = applies to all programs
    academic_year: str
    semester:      Optional[int] = None   # None = annual
    fee_items:     List[FeeItem]
    currency:      str = "INR"


class InvoiceCreate(BaseModel):
    student_id:       str
    fee_structure_id: str
    academic_year:    str
    semester:         Optional[int] = None
    due_date:         str   # YYYY-MM-DD
    notes:            Optional[str] = None


class InvoiceBulkCreate(BaseModel):
    fee_structure_id: str
    academic_year:    str
    semester:         Optional[int] = None
    due_date:         str
    student_ids:      Optional[List[str]] = None  # None = all enrolled in program


class ManualPaymentRecord(BaseModel):
    invoice_id:       str
    amount:           float = Field(..., gt=0)
    method:           PaymentMethod
    reference_number: Optional[str] = None
    bank_name:        Optional[str] = None
    cheque_date:      Optional[str] = None
    notes:            Optional[str] = None


class ScholarshipCreate(BaseModel):
    name:           str
    description:    Optional[str] = None
    type:           ScholarshipType = ScholarshipType.MERIT
    discount_type:  DiscountType = DiscountType.PERCENTAGE
    discount_value: float = Field(..., gt=0)
    academic_year:  str
    max_recipients: Optional[int] = None
    criteria:       Optional[Dict[str, Any]] = None


class ScholarshipAssign(BaseModel):
    scholarship_id: str
    student_id:     str
    academic_year:  str


class FeeWaiverRequest(BaseModel):
    invoice_id:   str
    waiver_type:  WaiverType = WaiverType.PARTIAL
    waiver_amount: float = Field(..., gt=0)
    reason:       str = Field(..., min_length=20)


class WaiverDecision(BaseModel):
    decision:       str   # "APPROVED" | "REJECTED"
    rejection_note: Optional[str] = None
