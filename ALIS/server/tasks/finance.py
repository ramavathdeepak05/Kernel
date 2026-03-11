"""Finance Celery tasks — E07

Beat tasks:
  - check_invoice_overdue: daily — marks unpaid past-due invoices as OVERDUE
"""

import logging

from server.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="finance.check_invoice_overdue")
def check_invoice_overdue() -> dict:
    """
    Beat task — runs daily.
    Marks invoices with due_date < today and status UNPAID as OVERDUE,
    and fires domain events for each organisation.
    """
    try:
        from server.db_service import execute_query, execute_transaction

        # Get all distinct org_ids with outstanding invoices
        orgs = execute_query(
            "SELECT DISTINCT org_id FROM student_invoices WHERE status = 'UNPAID' AND due_date < CURRENT_DATE",
            (),
        )

        total_marked = 0
        for row in orgs:
            org_id = row["org_id"]
            marked = execute_query(
                """
                UPDATE student_invoices
                SET status = 'OVERDUE'
                WHERE org_id = %s AND status = 'UNPAID' AND due_date < CURRENT_DATE
                RETURNING id, student_id
                """,
                (org_id,),
            )
            total_marked += len(marked)

            # Notify each affected student
            from server.core.domain_events import DomainEvent, DomainEventBus
            for inv in marked:
                try:
                    DomainEventBus.publish(DomainEvent(
                        event_type="InvoiceOverdue",
                        entity_type="student_invoice",
                        entity_id=str(inv["id"]),
                        org_id=org_id,
                        payload={"student_id": str(inv["student_id"])},
                        actor_id="system",
                    ))
                except Exception as exc:
                    logger.warning("finance: InvoiceOverdue event failed: %s", exc)

        logger.info("finance.check_invoice_overdue: marked %d invoices", total_marked)
        return {"marked_overdue": total_marked}
    except Exception as exc:
        logger.error("finance.check_invoice_overdue failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
