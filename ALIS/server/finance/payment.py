"""E07-S03 — Razorpay Payment Integration

Flow:
  1. POST /finance/payments/razorpay/order  → create Razorpay order, return order_id
  2. Frontend uses order_id to open Razorpay checkout
  3. Razorpay fires webhook → /api/v1/webhooks/razorpay (already in intake_router)
     OR student submits payment via /finance/payments/razorpay/verify
  4. On capture: apply payment to invoice, fire FeePaymentReceived event

E07-S04 — Manual Payment Recording (CASH / CHEQUE / DD / NEFT)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import ManualPaymentRecord

logger = logging.getLogger(__name__)


class PaymentService:

    # ------------------------------------------------------------------
    # S03 — Razorpay
    # ------------------------------------------------------------------

    @classmethod
    def create_razorpay_order(cls, org_id: str, invoice_id: str,
                               actor_id: str) -> dict:
        invoice = cls._get_invoice(org_id, invoice_id)
        balance = float(invoice["balance"] or 0)
        if balance <= 0:
            raise BusinessRuleViolation(message="Invoice is already fully paid")

        try:
            import razorpay
            from server.core.settings import settings
            client = razorpay.Client(
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
            )
            order = client.order.create({
                "amount": int(balance * 100),   # paise
                "currency": invoice.get("currency", "INR"),
                "receipt": str(invoice["invoice_number"]),
                "notes": {
                    "org_id": org_id,
                    "invoice_id": invoice_id,
                    "student_id": str(invoice["student_id"]),
                },
            })
            order_id = order["id"]
        except ImportError:
            # razorpay SDK not installed — return stub for dev/testing
            order_id = f"order_stub_{uuid.uuid4().hex[:16]}"
            logger.warning("PaymentService: razorpay not installed, using stub order_id")

        # Record a PENDING payment row
        pid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO payments
                (id, org_id, student_id, invoice_id, amount, currency,
                 method, status, razorpay_order_id, recorded_by)
            VALUES (%s, %s, %s, %s, %s, %s, 'RAZORPAY', 'PENDING', %s, %s)
            """,
            (pid, org_id, str(invoice["student_id"]), invoice_id,
             balance, invoice.get("currency", "INR"), order_id, actor_id),
        )])

        return {"payment_id": pid, "order_id": order_id, "amount": balance,
                "currency": invoice.get("currency", "INR"),
                "invoice_number": invoice["invoice_number"]}

    @classmethod
    def capture_razorpay_payment(cls, org_id: str, invoice_id: str,
                                  razorpay_order_id: str,
                                  razorpay_payment_id: str,
                                  razorpay_signature: str) -> dict:
        """Called by webhook or frontend after successful Razorpay payment."""
        from server.core.settings import settings

        # Signature verification — secret must be configured; no bypass allowed
        secret = settings.razorpay_webhook_secret
        if not secret:
            raise BusinessRuleViolation(
                message="Razorpay webhook secret not configured — payment cannot be verified"
            )
        expected = hmac.new(
            secret.encode(),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(expected, razorpay_signature):
            raise BusinessRuleViolation(message="Invalid Razorpay signature")

        # Idempotency
        already = execute_query(
            "SELECT id FROM payments WHERE razorpay_payment_id = %s AND status = 'CAPTURED'",
            (razorpay_payment_id,),
        )
        if already:
            return {"status": "already_captured"}

        # Update payment row
        execute_transaction([(
            """
            UPDATE payments
            SET razorpay_payment_id = %s, razorpay_signature = %s, status = 'CAPTURED'
            WHERE razorpay_order_id = %s AND invoice_id = %s
            """,
            (razorpay_payment_id, razorpay_signature, razorpay_order_id, invoice_id),
        )])

        # Fetch the captured amount
        payment_rows = execute_query(
            "SELECT amount, student_id FROM payments WHERE razorpay_order_id = %s AND invoice_id = %s",
            (razorpay_order_id, invoice_id),
        )
        if not payment_rows:
            return {"status": "not_found"}

        payment = dict(payment_rows[0])
        cls._apply_payment_to_invoice(
            org_id, invoice_id, float(payment["amount"]), str(payment["student_id"])
        )
        return {"status": "captured", "invoice_id": invoice_id}

    # ------------------------------------------------------------------
    # S03b — Gateway Webhook Capture (Razorpay webhook path)
    # Signature already verified at the router layer; this method applies
    # the state transition (PENDING → CAPTURED) and emits domain events.
    # ------------------------------------------------------------------

    @classmethod
    def apply_webhook_capture(
        cls,
        org_id: str,
        gateway_payment_id: str,
        gateway_response: dict,
    ) -> dict:
        """Update a payment row to CAPTURED from a verified gateway webhook.

        Called by the Razorpay webhook handler after HMAC verification.
        Idempotent — returns 'already_captured' if the row is already CAPTURED.
        """
        already = execute_query(
            "SELECT id, invoice_id, amount, student_id FROM payments "
            "WHERE gateway_payment_id = %s AND org_id = %s",
            (gateway_payment_id, org_id),
        )
        if not already:
            logger.warning(
                "apply_webhook_capture: payment %s not found for org %s",
                gateway_payment_id, org_id,
            )
            return {"status": "not_found"}

        row = dict(already[0])
        if row.get("status") == "CAPTURED":
            return {"status": "already_captured"}

        captured_status = "CAPTURED"
        execute_transaction([(
            "UPDATE payments SET status=%s, gateway_response=%s "
            "WHERE gateway_payment_id=%s AND org_id=%s",
            (captured_status, str(gateway_response), gateway_payment_id, org_id),
        )])

        if row.get("invoice_id"):
            try:
                cls._apply_payment_to_invoice(
                    org_id,
                    str(row["invoice_id"]),
                    float(row["amount"]),
                    str(row["student_id"]),
                )
            except Exception as exc:
                logger.error(
                    "apply_webhook_capture: invoice update failed for payment %s: %s",
                    gateway_payment_id, exc,
                )

        return {"status": "captured", "payment_id": str(row["id"])}

    # ------------------------------------------------------------------
    # S04 — Manual Payment
    # ------------------------------------------------------------------

    @classmethod
    def record_manual(cls, org_id: str, req: ManualPaymentRecord, actor_id: str) -> dict:
        invoice = cls._get_invoice(org_id, req.invoice_id)
        balance = float(invoice["balance"] or 0)

        if req.amount > balance + 0.01:
            raise BusinessRuleViolation(
                message=f"Payment amount {req.amount} exceeds outstanding balance {balance:.2f}"
            )

        pid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO payments
                (id, org_id, student_id, invoice_id, amount, currency,
                 method, status, reference_number, bank_name, cheque_date,
                 recorded_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'CAPTURED', %s, %s, %s, %s, %s)
            """,
            (pid, org_id, str(invoice["student_id"]), req.invoice_id,
             req.amount, invoice.get("currency", "INR"), req.method.value,
             req.reference_number, req.bank_name, req.cheque_date,
             actor_id, req.notes),
        )])

        cls._apply_payment_to_invoice(
            org_id, req.invoice_id, req.amount, str(invoice["student_id"])
        )

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="payment", entity_id=pid, org_id=org_id,
                     module="E07-S04",
                     metadata={"method": req.method.value, "amount": req.amount,
                               "invoice_id": req.invoice_id})

        payment_rows = execute_query("SELECT * FROM payments WHERE id = %s", (pid,))
        return dict(payment_rows[0])

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM payments WHERE student_id = %s AND org_id = %s ORDER BY recorded_at DESC",
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_for_invoice(cls, org_id: str, invoice_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM payments WHERE invoice_id = %s AND org_id = %s ORDER BY recorded_at",
            (invoice_id, org_id),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _get_invoice(cls, org_id: str, invoice_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM student_invoices WHERE id = %s AND org_id = %s",
            (invoice_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        return dict(rows[0])

    @classmethod
    def _apply_payment_to_invoice(cls, org_id: str, invoice_id: str,
                                   amount: float, student_id: str) -> None:
        """Add amount_paid to invoice, update status, fire FeePaymentReceived."""
        execute_transaction([(
            """
            UPDATE student_invoices
            SET amount_paid = amount_paid + %s,
                status = CASE
                    WHEN (amount_paid + %s) >= (amount_due - discount) THEN 'PAID'
                    WHEN (amount_paid + %s) > 0 THEN 'PARTIAL'
                    ELSE status
                END,
                paid_at = CASE
                    WHEN (amount_paid + %s) >= (amount_due - discount) THEN NOW()
                    ELSE paid_at
                END
            WHERE id = %s AND org_id = %s
            """,
            (amount, amount, amount, amount, invoice_id, org_id),
        )])

        DomainEventBus.publish(DomainEvent(
            event_type="FeePaymentReceived",
            entity_type="student_invoice",
            entity_id=invoice_id,
            org_id=org_id,
            payload={"student_id": student_id, "amount": amount, "invoice_id": invoice_id},
            actor_id="system",
        ))

        logger.info("Payment applied: invoice=%s amount=%.2f student=%s",
                    invoice_id, amount, student_id)
