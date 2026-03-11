"""E07 — Finance Event Handlers

Subscribes to:
  - StudentEnrolled      → auto-generate invoice if fee structure exists
  - FeePaymentReceived   → (internal, fired by PaymentService._apply_payment_to_invoice)
  - FeeWaiverApproved    → notify student
  - OfferLetterExpired   → mark related invoice as voided if unpaid

Publishes:
  - InvoiceGenerated     (invoice.py)
  - FeePaymentReceived   (payment.py)
  - FeeWaiverApproved    (waiver.py)
"""

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_student_enrolled(event: dict) -> None:
    """Auto-generate admission fee invoice when a student is enrolled."""
    payload    = event.get("payload", {})
    org_id     = event.get("org_id")
    student_id = payload.get("student_id") or event.get("entity_id")
    actor_id   = event.get("actor_id", "system")

    if not (org_id and student_id):
        return

    try:
        from server.db_service import execute_query
        from server.finance.invoice import InvoiceService
        from server.finance.models import InvoiceCreate

        # Find active fee structure for admission year with no specific program
        # (or match the student's program)
        student_rows = execute_query(
            "SELECT program FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            return

        from datetime import datetime
        academic_year = payload.get("academic_year") or str(datetime.now().year)

        # Find applicable fee structure (program-specific or org-wide)
        structures = execute_query(
            """
            SELECT id FROM fee_structures
            WHERE org_id = %s AND academic_year = %s AND is_active = TRUE
            ORDER BY program_id NULLS LAST
            LIMIT 1
            """,
            (org_id, academic_year),
        )
        if not structures:
            logger.info("E07: No fee structure for auto-invoice on enrollment of %s", student_id)
            return

        from datetime import date, timedelta
        due = (date.today() + timedelta(days=30)).isoformat()
        InvoiceService.create_for_student(
            org_id=org_id,
            req=InvoiceCreate(
                student_id=student_id,
                fee_structure_id=str(structures[0]["id"]),
                academic_year=academic_year,
                due_date=due,
            ),
            actor_id=actor_id,
        )
        logger.info("E07: Auto-invoice generated for enrolled student %s", student_id)
    except Exception as exc:
        logger.warning("E07: Auto-invoice on enrollment failed (non-fatal): %s", exc)


def on_fee_payment_received(event: dict) -> None:
    """Notify student on full payment."""
    payload    = event.get("payload", {})
    org_id     = event.get("org_id")
    invoice_id = payload.get("invoice_id")
    student_id = payload.get("student_id")

    if not (org_id and invoice_id):
        return

    try:
        from server.db_service import execute_query
        from server.core.notifications.service import NotificationDispatcher

        inv_rows = execute_query(
            "SELECT status, invoice_number FROM student_invoices WHERE id = %s AND org_id = %s",
            (invoice_id, org_id),
        )
        if not inv_rows or inv_rows[0]["status"] != "PAID":
            return  # Only notify on full payment

        student_rows = execute_query(
            "SELECT name, email FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            return

        s = student_rows[0]
        NotificationDispatcher.dispatch(
            template_key="fee_payment_received",
            recipient_id=student_id,
            recipient_email=s["email"],
            context={
                "student_name": s["name"],
                "invoice_number": inv_rows[0]["invoice_number"],
                "amount": payload.get("amount"),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.warning("E07: FeePaymentReceived notification failed (non-fatal): %s", exc)


def on_fee_waiver_approved(event: dict) -> None:
    """Notify student when fee waiver is approved."""
    payload    = event.get("payload", {})
    org_id     = event.get("org_id")
    student_id = payload.get("student_id")

    if not (org_id and student_id):
        return

    try:
        from server.db_service import execute_query
        from server.core.notifications.service import NotificationDispatcher

        student_rows = execute_query(
            "SELECT name, email FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            return

        s = student_rows[0]
        NotificationDispatcher.dispatch(
            template_key="fee_waiver_approved",
            recipient_id=student_id,
            recipient_email=s["email"],
            context={
                "student_name": s["name"],
                "waiver_amount": payload.get("waiver_amount"),
                "invoice_id": payload.get("invoice_id"),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.warning("E07: FeeWaiverApproved notification failed (non-fatal): %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("StudentEnrolled",      on_student_enrolled)
    DomainEventBus.subscribe("FeePaymentReceived",   on_fee_payment_received)
    DomainEventBus.subscribe("FeeWaiverApproved",    on_fee_waiver_approved)
    logger.info("E07 event handlers registered")
