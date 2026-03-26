"""E07-S06 — Fee Waiver Management

Waiver requests route through the E02 approval engine.
On approval: discount column on the invoice is updated.
"""
from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import FeeWaiverRequest, WaiverDecision

logger = logging.getLogger(__name__)


class FeeWaiverService:

    @classmethod
    def request_waiver(cls, org_id: str, student_id: str,
                        req: FeeWaiverRequest, actor_id: str) -> dict:
        invoice = execute_query(
            "SELECT * FROM student_invoices WHERE id = %s AND org_id = %s",
            (req.invoice_id, org_id),
        )
        if not invoice:
            raise NotFoundError(f"Invoice {req.invoice_id} not found")
        inv = dict(invoice[0])

        if inv["status"] == "PAID":
            raise BusinessRuleViolation(message="Cannot request waiver on a fully paid invoice")

        # Idempotency
        pending = execute_query(
            "SELECT id FROM fee_waivers WHERE invoice_id = %s AND status = 'PENDING' AND org_id = %s",
            (req.invoice_id, org_id),
        )
        if pending:
            raise BusinessRuleViolation(message="A waiver request is already pending for this invoice")

        balance = float(inv["balance"] or 0)
        if req.waiver_amount > balance:
            raise BusinessRuleViolation(
                message=f"Waiver amount {req.waiver_amount} exceeds outstanding balance {balance:.2f}"
            )

        wid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO fee_waivers
                (id, org_id, student_id, invoice_id, waiver_type, waiver_amount, reason, requested_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (wid, org_id, student_id, req.invoice_id,
             req.waiver_type.value, req.waiver_amount, req.reason, actor_id),
        )])

        # Route through E02 approval engine
        try:
            from server.approvals.service import ApprovalService
            ApprovalService.create_request(
                org_id=org_id,
                entity_type="fee_waiver",
                entity_id=wid,
                requested_by=actor_id,
                metadata={
                    "student_id": student_id,
                    "invoice_id": req.invoice_id,
                    "waiver_amount": req.waiver_amount,
                    "reason": req.reason,
                },
            )
        except Exception as exc:
            logger.warning("FeeWaiver: approval routing failed (non-fatal): %s", exc)

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="fee_waiver", entity_id=wid, org_id=org_id,
                     module="E07-S06",
                     metadata={"invoice_id": req.invoice_id, "amount": req.waiver_amount})

        return cls.get(org_id, wid)

    @classmethod
    def decide(cls, org_id: str, waiver_id: str,
                decision: WaiverDecision, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM fee_waivers WHERE id = %s AND org_id = %s",
            (waiver_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Fee waiver {waiver_id} not found")
        waiver = dict(rows[0])

        if waiver["status"] != "PENDING":
            raise BusinessRuleViolation(message=f"Waiver is already {waiver['status']}")

        if decision.decision not in ("APPROVED", "REJECTED"):
            raise BusinessRuleViolation(message="decision must be 'APPROVED' or 'REJECTED'")

        execute_transaction([(
            """
            UPDATE fee_waivers
            SET status = %s, approved_by = %s, approved_at = NOW(),
                rejection_note = %s
            WHERE id = %s AND org_id = %s
            """,
            (decision.decision, actor_id, decision.rejection_note, waiver_id, org_id),
        )])

        if decision.decision == "APPROVED":
            # Apply waiver to invoice discount
            execute_transaction([(
                """
                UPDATE student_invoices
                SET discount = discount + %s,
                    status = CASE
                        WHEN (amount_paid + discount + %s) >= amount_due THEN 'WAIVED'
                        ELSE status
                    END
                WHERE id = %s AND org_id = %s
                """,
                (waiver["waiver_amount"], waiver["waiver_amount"],
                 str(waiver["invoice_id"]), org_id),
            )])

            DomainEventBus.publish(DomainEvent(
                event_type="FeeWaiverApproved",
                entity_type="fee_waiver",
                entity_id=waiver_id,
                org_id=org_id,
                payload={"student_id": str(waiver["student_id"]),
                         "invoice_id": str(waiver["invoice_id"]),
                         "waiver_amount": float(waiver["waiver_amount"])},
                actor_id=actor_id,
            ))

        AuditLog.log(action=AuditAction.UPDATE, actor_id=actor_id, actor_type="human",
                     entity_type="fee_waiver", entity_id=waiver_id, org_id=org_id,
                     module="E07-S06",
                     metadata={"decision": decision.decision})

        return cls.get(org_id, waiver_id)

    @classmethod
    def get(cls, org_id: str, waiver_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM fee_waivers WHERE id = %s AND org_id = %s",
            (waiver_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Fee waiver {waiver_id} not found")
        return dict(rows[0])

    @classmethod
    def list_pending(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM fee_waivers WHERE org_id = %s AND status = 'PENDING' ORDER BY requested_at",
            (org_id,),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM fee_waivers WHERE student_id = %s AND org_id = %s ORDER BY requested_at DESC",
            (student_id, org_id),
        )
        return [dict(r) for r in rows]
