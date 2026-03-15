"""E07 — Finance API Router

Endpoints:
  E07-S01  POST   /finance/fee-structures
           GET    /finance/fee-structures
           GET    /finance/fee-structures/{id}
           DELETE /finance/fee-structures/{id}

  E07-S02  POST   /finance/invoices
           POST   /finance/invoices/bulk
           GET    /finance/invoices/{id}
           GET    /finance/invoices/student/{student_id}

  E07-S03  POST   /finance/payments/razorpay/order
           POST   /finance/payments/razorpay/capture

  E07-S04  POST   /finance/payments/manual
           GET    /finance/payments/student/{student_id}
           GET    /finance/payments/invoice/{invoice_id}

  E07-S05  POST   /finance/scholarships
           GET    /finance/scholarships
           POST   /finance/scholarships/assign
           DELETE /finance/scholarships/assign/{id}
           GET    /finance/scholarships/student/{student_id}

  E07-S06  POST   /finance/waivers
           POST   /finance/waivers/{id}/decide
           GET    /finance/waivers/pending
           GET    /finance/waivers/student/{student_id}

  E07-S07  GET    /finance/reports/collection
           GET    /finance/reports/defaulters
           GET    /finance/reports/payment-methods
           GET    /finance/reports/scholarships
           GET    /finance/reports/program-revenue
           GET    /finance/reports/monthly

  E07-S08  GET    /finance/analytics/default-risk
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.finance.fee_structure import FeeStructureService
from server.finance.invoice       import InvoiceService
from server.finance.payment       import PaymentService
from server.finance.scholarship   import ScholarshipService
from server.finance.waiver        import FeeWaiverService
from server.finance.reports       import FinanceReportService
from server.finance.analytics     import FeeDefaultAnalyticsService
from server.finance.models        import (
    FeeStructureCreate, InvoiceCreate, InvoiceBulkCreate,
    ManualPaymentRecord, ScholarshipCreate, ScholarshipAssign,
    FeeWaiverRequest, WaiverDecision,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")

def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")
n
def _jsonify(obj):
    """Recursively convert Decimal/date/datetime/time to JSON-safe types."""
    from decimal import Decimal
    from datetime import datetime, date, time as _time
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, _time):
        return obj.strftime("%H:%M")
    return obj


# ──────────────────────────────────────────────────────────────
# E07-S01 — Fee Structures
# ──────────────────────────────────────────────────────────────

@router.post("/fee-structures", status_code=201)
@require_permission(Permission.FEE_CREATE)
async def create_fee_structure(request: Request, body: FeeStructureCreate) -> JSONResponse:
    result = FeeStructureService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/fee-structures")
@require_permission(Permission.FEE_READ)
async def list_fee_structures(
    request: Request,
    academic_year: str = Query(...),
    program_id: Optional[str] = Query(None),
) -> JSONResponse:
    items = FeeStructureService.list(_org(request), academic_year, program_id)
    return JSONResponse(content={"fee_structures": items, "total": len(items)})


@router.get("/fee-structures/{structure_id}")
@require_permission(Permission.FEE_READ)
async def get_fee_structure(request: Request, structure_id: str) -> JSONResponse:
    return JSONResponse(content=FeeStructureService.get(_org(request), structure_id))


@router.delete("/fee-structures/{structure_id}")
@require_permission(Permission.FEE_CREATE)
async def deactivate_fee_structure(request: Request, structure_id: str) -> JSONResponse:
    result = FeeStructureService.deactivate(_org(request), structure_id, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E07-S02 — Invoices
# ──────────────────────────────────────────────────────────────

@router.post("/invoices", status_code=201)
@require_permission(Permission.FEE_CREATE)
async def create_invoice(request: Request, body: InvoiceCreate) -> JSONResponse:
    result = InvoiceService.create_for_student(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.post("/invoices/bulk", status_code=201)
@require_permission(Permission.FEE_CREATE)
async def bulk_generate_invoices(request: Request, body: InvoiceBulkCreate) -> JSONResponse:
    result = InvoiceService.bulk_generate(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/invoices/{invoice_id}")
@require_permission(Permission.FEE_READ)
async def get_invoice(request: Request, invoice_id: str) -> JSONResponse:
    return JSONResponse(content=InvoiceService.get(_org(request), invoice_id))


@router.get("/invoices/student/{student_id}")
@require_permission(Permission.FEE_READ)
async def list_student_invoices(
    request: Request,
    student_id: str,
    academic_year: Optional[str] = Query(None),
) -> JSONResponse:
    items = InvoiceService.list_for_student(_org(request), student_id, academic_year)
    return JSONResponse(content={"invoices": items, "total": len(items)})


# ──────────────────────────────────────────────────────────────
# E07-S03 — Razorpay Payments
# ──────────────────────────────────────────────────────────────

@router.post("/payments/razorpay/order", status_code=201)
@require_permission(Permission.PAYMENT_PROCESS)
async def create_razorpay_order(request: Request, body: dict) -> JSONResponse:
    result = PaymentService.create_razorpay_order(
        _org(request), body["invoice_id"], _actor(request)
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/payments/razorpay/capture")
@require_permission(Permission.PAYMENT_PROCESS)
async def capture_razorpay_payment(request: Request, body: dict) -> JSONResponse:
    result = PaymentService.capture_razorpay_payment(
        org_id=_org(request),
        invoice_id=body["invoice_id"],
        razorpay_order_id=body["razorpay_order_id"],
        razorpay_payment_id=body["razorpay_payment_id"],
        razorpay_signature=body["razorpay_signature"],
    )
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E07-S04 — Manual Payments
# ──────────────────────────────────────────────────────────────

@router.post("/payments/manual", status_code=201)
@require_permission(Permission.PAYMENT_PROCESS)
async def record_manual_payment(request: Request, body: ManualPaymentRecord) -> JSONResponse:
    result = PaymentService.record_manual(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/payments/student/{student_id}")
@require_permission(Permission.FEE_READ)
async def list_student_payments(request: Request, student_id: str) -> JSONResponse:
    items = PaymentService.list_for_student(_org(request), student_id)
    return JSONResponse(content={"payments": items, "total": len(items)})


@router.get("/payments/invoice/{invoice_id}")
@require_permission(Permission.FEE_READ)
async def list_invoice_payments(request: Request, invoice_id: str) -> JSONResponse:
    items = PaymentService.list_for_invoice(_org(request), invoice_id)
    return JSONResponse(content={"payments": items})


# ──────────────────────────────────────────────────────────────
# E07-S05 — Scholarships
# ──────────────────────────────────────────────────────────────

@router.post("/scholarships", status_code=201)
@require_permission(Permission.FEE_CREATE)
async def create_scholarship(request: Request, body: ScholarshipCreate) -> JSONResponse:
    result = ScholarshipService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/scholarships")
@require_permission(Permission.FEE_READ)
async def list_scholarships(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = ScholarshipService.list(_org(request), academic_year)
    return JSONResponse(content={"scholarships": items, "total": len(items)})


@router.post("/scholarships/assign", status_code=201)
@require_permission(Permission.FEE_CREATE)
async def assign_scholarship(request: Request, body: ScholarshipAssign) -> JSONResponse:
    result = ScholarshipService.assign(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.delete("/scholarships/assign/{assignment_id}")
@require_permission(Permission.FEE_CREATE)
async def revoke_scholarship(request: Request, assignment_id: str) -> JSONResponse:
    result = ScholarshipService.revoke(_org(request), assignment_id, _actor(request))
    return JSONResponse(content=result)


@router.get("/scholarships/student/{student_id}")
@require_permission(Permission.FEE_READ)
async def student_scholarships(
    request: Request,
    student_id: str,
    academic_year: Optional[str] = Query(None),
) -> JSONResponse:
    items = ScholarshipService.list_for_student(_org(request), student_id, academic_year)
    return JSONResponse(content={"scholarships": items})


# ──────────────────────────────────────────────────────────────
# E07-S06 — Fee Waivers
# ──────────────────────────────────────────────────────────────

@router.post("/waivers", status_code=201)
@require_permission(Permission.FEE_READ)
async def request_waiver(request: Request, body: FeeWaiverRequest) -> JSONResponse:
    result = FeeWaiverService.request_waiver(
        _org(request), _actor(request), body, _actor(request)
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/waivers/pending")
@require_permission(Permission.FEE_CREATE)
async def list_pending_waivers(request: Request) -> JSONResponse:
    items = FeeWaiverService.list_pending(_org(request))
    return JSONResponse(content={"waivers": items, "total": len(items)})


@router.get("/waivers/student/{student_id}")
@require_permission(Permission.FEE_READ)
async def list_student_waivers(request: Request, student_id: str) -> JSONResponse:
    items = FeeWaiverService.list_for_student(_org(request), student_id)
    return JSONResponse(content={"waivers": items})


@router.post("/waivers/{waiver_id}/decide")
@require_permission(Permission.FEE_CREATE)
async def decide_waiver(
    request: Request, waiver_id: str, body: WaiverDecision
) -> JSONResponse:
    result = FeeWaiverService.decide(_org(request), waiver_id, body, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E07-S07 — Financial Reports
# ──────────────────────────────────────────────────────────────

@router.get("/reports/collection")
@require_permission(Permission.LEDGER_READ)
async def collection_summary(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=FinanceReportService.collection_summary(_org(request), academic_year)
    )


@router.get("/reports/defaulters")
@require_permission(Permission.LEDGER_READ)
async def defaulters_list(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.defaulters_list(_org(request), academic_year)
    return JSONResponse(content={"defaulters": items, "total": len(items)})


@router.get("/reports/payment-methods")
@require_permission(Permission.LEDGER_READ)
async def payment_method_breakdown(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.payment_method_breakdown(_org(request), academic_year)
    return JSONResponse(content={"breakdown": items})


@router.get("/reports/scholarships")
@require_permission(Permission.LEDGER_READ)
async def scholarship_impact(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=FinanceReportService.scholarship_impact(_org(request), academic_year)
    )


@router.get("/reports/program-revenue")
@require_permission(Permission.LEDGER_READ)
async def program_revenue(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.program_wise_revenue(_org(request), academic_year)
    return JSONResponse(content={"programs": items})


@router.get("/reports/monthly")
@require_permission(Permission.LEDGER_READ)
async def monthly_collection(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    items = FinanceReportService.monthly_collection(_org(request), academic_year)
    return JSONResponse(content={"monthly": items})


# ──────────────────────────────────────────────────────────────
# E07-S08 — AI Fee Default Prediction
# ──────────────────────────────────────────────────────────────

@router.get("/analytics/default-risk")
@require_permission(Permission.LEDGER_READ)
async def default_risk(
    request: Request, academic_year: str = Query(...)
) -> JSONResponse:
    return JSONResponse(
        content=FeeDefaultAnalyticsService.predict_defaults(_org(request), academic_year)
    )
