"""StudentDuesStatus — Read Model for Hall Ticket Eligibility Gate

Queries the student_dues_status VIEW (created in migration 0022) plus
real-time library fines, hostel dues, and exam fees.

This is a synchronous read model — queried at hall-ticket generation gate.
The dues_cleared flag is computed from live DB state, not from events
(which can be stale if a library fine is posted after the event fires).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel
from server.db_service import execute_query

logger = logging.getLogger(__name__)


class StudentDuesStatus(BaseModel):
    student_id: str
    org_id: str
    total_outstanding: float
    pending_library_fines: float
    pending_hostel_dues: float
    pending_exam_fees: float
    exemption_active: bool
    promissory_cover_active: bool
    dues_cleared: bool  # True only if ALL dues are zero or covered


class StudentDuesStatusService:
    @classmethod
    async def get(cls, student_id: str, org_id: str) -> StudentDuesStatus:
        """Return real-time dues status for a student.

        Queries the student_dues_status VIEW plus auxiliary dues tables.
        """
        # 1. Invoice-level dues from student_dues_status VIEW (migration 0022)
        invoice_rows = execute_query(
            """
            SELECT
                COALESCE(SUM(balance), 0) AS total_outstanding,
                BOOL_OR(exemption_active) AS exemption_active,
                BOOL_OR(promissory_cover_active) AS promissory_cover_active
            FROM student_dues_status
            WHERE student_id = %s AND org_id = %s
        """,
            (student_id, org_id),
        )

        invoice_data = dict(invoice_rows[0]) if invoice_rows else {}
        total_outstanding = float(invoice_data.get("total_outstanding") or 0)
        exemption_active = bool(invoice_data.get("exemption_active", False))
        promissory_cover = bool(invoice_data.get("promissory_cover_active", False))

        # 2. Library fines
        lib_rows = execute_query(
            """
            SELECT COALESCE(SUM(fine_amount), 0) AS total
            FROM library_fines
            WHERE student_id = %s AND org_id = %s AND status = 'PENDING'
        """,
            (student_id, org_id),
        )
        lib_fines = float(lib_rows[0]["total"] or 0) if lib_rows else 0.0

        # 3. Hostel dues
        hostel_rows = execute_query(
            """
            SELECT COALESCE(SUM(amount_due - amount_paid), 0) AS total
            FROM hostel_invoices
            WHERE student_id = %s AND org_id = %s AND status NOT IN ('PAID', 'WAIVED')
        """,
            (student_id, org_id),
        )
        hostel_dues = float(hostel_rows[0]["total"] or 0) if hostel_rows else 0.0

        # 4. Exam fees
        exam_fee_rows = execute_query(
            """
            SELECT COALESCE(SUM(fee_amount - amount_paid), 0) AS total
            FROM exam_fee_payments
            WHERE student_id = %s AND org_id = %s AND status NOT IN ('PAID', 'WAIVED')
        """,
            (student_id, org_id),
        )
        exam_fees = float(exam_fee_rows[0]["total"] or 0) if exam_fee_rows else 0.0

        # dues_cleared = True only when ALL dues are zero (or exemption covers main fees)
        effective_outstanding = (
            total_outstanding if not (exemption_active or promissory_cover) else 0
        )
        dues_cleared = (
            effective_outstanding <= 0
            and lib_fines <= 0
            and hostel_dues <= 0
            and exam_fees <= 0
        )

        return StudentDuesStatus(
            student_id=student_id,
            org_id=org_id,
            total_outstanding=total_outstanding,
            pending_library_fines=lib_fines,
            pending_hostel_dues=hostel_dues,
            pending_exam_fees=exam_fees,
            exemption_active=exemption_active,
            promissory_cover_active=promissory_cover,
            dues_cleared=dues_cleared,
        )

    @classmethod
    async def assert_dues_cleared(cls, student_id: str, org_id: str) -> None:
        """Raise BusinessRuleViolation if dues are not cleared.

        Called from hall-ticket generation gate.
        """
        from server.core.exceptions import BusinessRuleViolation

        status = await cls.get(student_id, org_id)
        if not status.dues_cleared:
            breakdown = []
            if status.total_outstanding > 0 and not (
                status.exemption_active or status.promissory_cover_active
            ):
                breakdown.append(f"tuition dues ₹{status.total_outstanding:.2f}")
            if status.pending_library_fines > 0:
                breakdown.append(f"library fines ₹{status.pending_library_fines:.2f}")
            if status.pending_hostel_dues > 0:
                breakdown.append(f"hostel dues ₹{status.pending_hostel_dues:.2f}")
            if status.pending_exam_fees > 0:
                breakdown.append(f"exam fees ₹{status.pending_exam_fees:.2f}")
            raise BusinessRuleViolation(
                f"Hall ticket blocked: pending dues — {', '.join(breakdown)}"
            )
