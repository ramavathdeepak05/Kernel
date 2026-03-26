"""EC-FIN-01 — DBT Exemption Service
EC-FIN-02 — Promissory Note Ledger Service

Business rules enforced here:
- DBT exemptions pause escalation only (do NOT waive the fee).
- MANAGEMENT_WAIVER above ₹50,000 requires dual approval (second_approver).
- Default validity: 180 days — overridable via institution_policies key
  'finance.dbt_exemption.validity_days'.
- Promissory components carry expected_date; a missed deadline triggers an
  adjustment invoice (never modifies the existing invoice).
- student_dues_status view provides the read model for hall-ticket block checks.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_VALIDITY_DAYS = 180
_DUAL_APPROVAL_THRESHOLD = 50_000.00

VALID_EXEMPTION_TYPES = {
    "AWAITING_GOVT_DBT",
    "MANAGEMENT_WAIVER",
    "COURT_ORDER",
    "OTHER",
}

VALID_COMPONENT_TYPES = {
    "DIRECT_PAYMENT",
    "DD",
    "NEFT",
    "UPI",
    "LOAN_TRANCHE",
    "SCHOLARSHIP_CREDIT",
    "PROMISSORY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy_validity_days(org_id: str) -> int:
    """Return configured validity days or the default 180."""
    rows = execute_query(
        """
        SELECT value FROM institution_policies
        WHERE org_id = %s AND key = 'finance.dbt_exemption.validity_days'
        LIMIT 1
        """,
        (org_id,),
    )
    if rows:
        try:
            import json as _json
            return int(_json.loads(rows[0]["value"]))
        except Exception:
            pass
    return _DEFAULT_VALIDITY_DAYS


def _invoice_balance(org_id: str, invoice_id: str) -> float:
    """Return the outstanding balance for an invoice."""
    rows = execute_query(
        "SELECT balance FROM student_invoices WHERE id = %s AND org_id = %s",
        (invoice_id, org_id),
    )
    if not rows:
        raise NotFoundError(f"Invoice {invoice_id} not found")
    return float(rows[0]["balance"] or 0)


def _adjustment_invoice_number(org_id: str, academic_year: str) -> str:
    seq = execute_query(
        "SELECT COUNT(*) AS cnt FROM student_invoices WHERE org_id = %s AND academic_year = %s",
        (org_id, academic_year),
    )
    n = int(seq[0]["cnt"]) + 1 if seq else 1
    prefix = org_id[:4].upper().replace("-", "")
    return f"ADJ-{prefix}-{academic_year.replace('-', '')}-{n:05d}"


# ===========================================================================
# ExemptionService — EC-FIN-01
# ===========================================================================

class ExemptionService:
    """Manages student fee exemptions (DBT holds, court orders, management waivers)."""

    @classmethod
    def create_exemption(
        cls,
        org_id: str,
        student_id: str,
        exemption_type: str,
        reason: str,
        approver_id: str,
        invoice_id: str | None = None,
        valid_days: int | None = None,
        second_approver_id: str | None = None,
    ) -> dict:
        """
        Create a fee exemption for a student.

        Parameters
        ----------
        org_id:              Tenant.
        student_id:          Student UUID.
        exemption_type:      One of VALID_EXEMPTION_TYPES.
        reason:              Mandatory narrative justification.
        approver_id:         First approver (Finance Officer).
        invoice_id:          Specific invoice to exempt; NULL = all pending invoices.
        valid_days:          Override validity window; falls back to policy then 180.
        second_approver_id:  Required for MANAGEMENT_WAIVER when invoice > ₹50,000.
        """
        # --- Validate type ---
        if exemption_type not in VALID_EXEMPTION_TYPES:
            raise BusinessRuleViolation(
                message=f"Invalid exemption_type '{exemption_type}'. "
                        f"Must be one of {sorted(VALID_EXEMPTION_TYPES)}"
            )

        # --- Validate student exists ---
        student_rows = execute_query(
            "SELECT id FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            raise NotFoundError(f"Student {student_id} not found")

        # --- Dual-approval check for large MANAGEMENT_WAIVER ---
        if exemption_type == "MANAGEMENT_WAIVER" and invoice_id:
            balance = _invoice_balance(org_id, invoice_id)
            if balance > _DUAL_APPROVAL_THRESHOLD and not second_approver_id:
                raise BusinessRuleViolation(
                    message=(
                        f"MANAGEMENT_WAIVER for invoice balance ₹{balance:,.2f} exceeds "
                        f"₹{_DUAL_APPROVAL_THRESHOLD:,.0f}. A second approver (Dean) is required."
                    )
                )

        # --- Validity window ---
        days = valid_days if valid_days and valid_days > 0 else _policy_validity_days(org_id)
        valid_from = date.today()
        valid_until = valid_from + timedelta(days=days)

        eid = str(uuid.uuid4())
        try:
            execute_transaction([(
                """
                INSERT INTO student_fee_exemptions
                    (id, org_id, student_id, invoice_id, exemption_type, reason,
                     valid_from, valid_until, status, approved_by, second_approver)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s)
                """,
                (
                    eid, org_id, student_id, invoice_id, exemption_type, reason,
                    valid_from, valid_until, approver_id, second_approver_id,
                ),
            )])
        except Exception as exc:
            # Unique constraint on (org_id, student_id, invoice_id, exemption_type)
            if "uq_exemption_student_invoice" in str(exc).lower() or "unique" in str(exc).lower():
                raise BusinessRuleViolation(
                    message=(
                        f"Active {exemption_type} exemption already exists for "
                        f"student {student_id}"
                        + (f" on invoice {invoice_id}" if invoice_id else "")
                    )
                ) from exc
            raise

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=approver_id,
            actor_type="human",
            entity_type="student_fee_exemption",
            entity_id=eid,
            org_id=org_id,
            module="EC-FIN-01",
            metadata={
                "exemption_type": exemption_type,
                "student_id": student_id,
                "invoice_id": invoice_id,
                "valid_from": valid_from.isoformat(),
                "valid_until": valid_until.isoformat(),
                "days": days,
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="FeeExemptionCreated",
            entity_type="student_fee_exemption",
            entity_id=eid,
            org_id=org_id,
            payload={
                "exemption_type": exemption_type,
                "student_id": student_id,
                "invoice_id": invoice_id,
                "valid_until": valid_until.isoformat(),
            },
            actor_id=approver_id,
        ))

        return cls._get(org_id, eid)

    @classmethod
    def revoke_exemption(cls, org_id: str, exemption_id: str, revoker_id: str) -> dict:
        """Revoke an active exemption.  Escalation resumes from next business day."""
        rows = execute_query(
            "SELECT * FROM student_fee_exemptions WHERE id = %s AND org_id = %s",
            (exemption_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Exemption {exemption_id} not found")
        exemption = dict(rows[0])

        if exemption["status"] != "ACTIVE":
            raise BusinessRuleViolation(
                message=f"Exemption is already {exemption['status']}"
            )

        execute_transaction([(
            """
            UPDATE student_fee_exemptions
               SET status = 'REVOKED', revoked_by = %s, revoked_at = NOW()
             WHERE id = %s AND org_id = %s
            """,
            (revoker_id, exemption_id, org_id),
        )])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=revoker_id,
            actor_type="human",
            entity_type="student_fee_exemption",
            entity_id=exemption_id,
            org_id=org_id,
            module="EC-FIN-01",
            metadata={"action": "revoke", "student_id": str(exemption["student_id"])},
        )

        DomainEventBus.publish(DomainEvent(
            event_type="FeeExemptionRevoked",
            entity_type="student_fee_exemption",
            entity_id=exemption_id,
            org_id=org_id,
            payload={"student_id": str(exemption["student_id"])},
            actor_id=revoker_id,
        ))

        return cls._get(org_id, exemption_id)

    @classmethod
    def get_active_exemptions(cls, org_id: str, student_id: str) -> list[dict]:
        """Return all ACTIVE, non-expired exemptions for a student."""
        rows = execute_query(
            """
            SELECT * FROM student_fee_exemptions
            WHERE org_id = %s
              AND student_id = %s
              AND status = 'ACTIVE'
              AND valid_until >= CURRENT_DATE
            ORDER BY valid_until ASC
            """,
            (org_id, student_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def is_student_exempt(
        cls, org_id: str, student_id: str, invoice_id: str | None = None
    ) -> bool:
        """
        Return True if the student has an active exemption covering the given
        invoice (or any invoice when invoice_id is None).

        Used by the defaulter escalation pipeline.
        """
        params: list = [org_id, student_id]
        sql = """
            SELECT 1 FROM student_fee_exemptions
            WHERE org_id = %s
              AND student_id = %s
              AND status = 'ACTIVE'
              AND valid_until >= CURRENT_DATE
        """
        if invoice_id:
            sql += " AND (invoice_id IS NULL OR invoice_id = %s)"
            params.append(invoice_id)
        sql += " LIMIT 1"

        rows = execute_query(sql, tuple(params))
        return bool(rows)

    @classmethod
    def _get(cls, org_id: str, exemption_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM student_fee_exemptions WHERE id = %s AND org_id = %s",
            (exemption_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Exemption {exemption_id} not found")
        return dict(rows[0])


# ===========================================================================
# PromissoryService — EC-FIN-02
# ===========================================================================

class PromissoryService:
    """
    Manages fee payment components including promissory notes, loan tranches,
    scholarship credits, and direct payment records.

    Key invariant: existing invoices are NEVER modified.  If a promissory note
    is missed an adjustment invoice is created instead.
    """

    @classmethod
    def log_component(
        cls,
        org_id: str,
        invoice_id: str,
        student_id: str,
        component_type: str,
        amount: float,
        created_by: str,
        expected_date: date | None = None,
        reference_no: str | None = None,
    ) -> dict:
        """
        Log a fee payment component (promissory note, loan tranche, etc.).

        Parameters
        ----------
        component_type:  One of VALID_COMPONENT_TYPES.
        amount:          Component amount in INR.
        expected_date:   Required for PROMISSORY — bank disbursal / payment date.
        reference_no:    UTR, DD number, bank sanction letter no., etc.
        """
        if component_type not in VALID_COMPONENT_TYPES:
            raise BusinessRuleViolation(
                message=f"Invalid component_type '{component_type}'. "
                        f"Must be one of {sorted(VALID_COMPONENT_TYPES)}"
            )
        if amount <= 0:
            raise BusinessRuleViolation(message="Component amount must be greater than zero")
        if component_type == "PROMISSORY" and not expected_date:
            raise BusinessRuleViolation(
                message="expected_date is required for PROMISSORY components"
            )

        # Validate invoice belongs to this tenant
        inv_rows = execute_query(
            "SELECT id, student_id FROM student_invoices WHERE id = %s AND org_id = %s",
            (invoice_id, org_id),
        )
        if not inv_rows:
            raise NotFoundError(f"Invoice {invoice_id} not found")

        cid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO fee_payment_components
                (id, org_id, invoice_id, student_id, component_type,
                 amount, expected_date, reference_no, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)
            """,
            (
                cid, org_id, invoice_id, student_id, component_type,
                amount, expected_date, reference_no, created_by,
            ),
        )])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=created_by,
            actor_type="human",
            entity_type="fee_payment_component",
            entity_id=cid,
            org_id=org_id,
            module="EC-FIN-02",
            metadata={
                "component_type": component_type,
                "invoice_id": invoice_id,
                "student_id": student_id,
                "amount": amount,
                "expected_date": expected_date.isoformat() if expected_date else None,
            },
        )

        return cls._get_component(org_id, cid)

    @classmethod
    def reconcile(
        cls,
        org_id: str,
        component_id: str,
        received_date: date,
        reference_no: str | None = None,
    ) -> dict:
        """
        Mark a component as RECONCILED when actual payment is confirmed.

        This is the canonical step for DD clearance, NEFT credit confirmation,
        or bank loan disbursement confirmation.
        """
        component = cls._load_component(org_id, component_id)

        if component["status"] in ("RECONCILED", "MISSED"):
            raise BusinessRuleViolation(
                message=f"Component is already {component['status']} and cannot be reconciled"
            )

        execute_transaction([(
            """
            UPDATE fee_payment_components
               SET status = 'RECONCILED',
                   received_date = %s,
                   reference_no = COALESCE(%s, reference_no)
             WHERE id = %s AND org_id = %s
            """,
            (received_date, reference_no, component_id, org_id),
        )])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_type="system",
            entity_type="fee_payment_component",
            entity_id=component_id,
            org_id=org_id,
            module="EC-FIN-02",
            metadata={
                "action": "reconcile",
                "received_date": received_date.isoformat(),
                "invoice_id": str(component["invoice_id"]),
            },
        )

        return cls._get_component(org_id, component_id)

    @classmethod
    def flag_missed(cls, org_id: str, component_id: str) -> dict:
        """
        Mark a PROMISSORY component as MISSED when it passes its expected_date
        without payment, and create an adjustment invoice for the shortfall.

        Rule: never modify the original invoice — post a NEW adjustment invoice.
        """
        component = cls._load_component(org_id, component_id)

        if component["status"] != "PENDING":
            raise BusinessRuleViolation(
                message=f"Component status is '{component['status']}'; only PENDING can be flagged missed"
            )

        # Mark MISSED
        execute_transaction([(
            """
            UPDATE fee_payment_components
               SET status = 'MISSED'
             WHERE id = %s AND org_id = %s
            """,
            (component_id, org_id),
        )])

        # Retrieve original invoice metadata for the adjustment invoice
        inv_rows = execute_query(
            "SELECT * FROM student_invoices WHERE id = %s AND org_id = %s",
            (str(component["invoice_id"]), org_id),
        )
        original_invoice = dict(inv_rows[0]) if inv_rows else None

        adjustment_id: str | None = None
        if original_invoice:
            try:
                academic_year = original_invoice["academic_year"]
                adj_num = _adjustment_invoice_number(org_id, academic_year)
                missed_amount = float(component["amount"])
                adjustment_id = str(uuid.uuid4())
                # Adjustment due: 14 days from today (immediate follow-up)
                from datetime import date as _date, timedelta as _td
                adj_due = _date.today() + _td(days=14)

                execute_transaction([(
                    """
                    INSERT INTO student_invoices
                        (id, org_id, student_id, fee_structure_id, academic_year, semester,
                         invoice_number, amount_due, discount, currency, due_date,
                         generated_by, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, 'system', %s)
                    """,
                    (
                        adjustment_id,
                        org_id,
                        str(original_invoice["student_id"]),
                        original_invoice.get("fee_structure_id"),
                        academic_year,
                        original_invoice.get("semester"),
                        adj_num,
                        missed_amount,
                        original_invoice.get("currency", "INR"),
                        adj_due,
                        f"Adjustment: promissory component {component_id} missed. "
                        f"Original invoice: {original_invoice['invoice_number']}",
                    ),
                )])

                DomainEventBus.publish(DomainEvent(
                    event_type="PromissoryMissed",
                    entity_type="fee_payment_component",
                    entity_id=component_id,
                    org_id=org_id,
                    payload={
                        "component_id": component_id,
                        "student_id": str(original_invoice["student_id"]),
                        "missed_amount": missed_amount,
                        "original_invoice_id": str(original_invoice["id"]),
                        "adjustment_invoice_id": adjustment_id,
                    },
                    actor_id="system",
                ))
            except Exception as exc:
                logger.error(
                    "PromissoryService.flag_missed: adjustment invoice creation failed "
                    "for component %s: %s",
                    component_id,
                    exc,
                )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_type="system",
            entity_type="fee_payment_component",
            entity_id=component_id,
            org_id=org_id,
            module="EC-FIN-02",
            metadata={
                "action": "flag_missed",
                "invoice_id": str(component["invoice_id"]),
                "missed_amount": float(component["amount"]),
                "adjustment_invoice_id": adjustment_id,
            },
        )

        return cls._get_component(org_id, component_id)

    @classmethod
    def get_dues_status(cls, org_id: str, student_id: str) -> list[dict]:
        """
        Query the student_dues_status view for all invoices of a student.

        Returns a list of rows containing:
          invoice_id, academic_year, amount_due, amount_paid, balance,
          invoice_status, due_date, exemption_active, promissory_cover_active,
          total_covered.
        """
        rows = execute_query(
            """
            SELECT *
            FROM student_dues_status
            WHERE org_id = %s AND student_id = %s
            ORDER BY due_date ASC
            """,
            (org_id, student_id),
        )
        return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @classmethod
    def _load_component(cls, org_id: str, component_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM fee_payment_components WHERE id = %s AND org_id = %s",
            (component_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Payment component {component_id} not found")
        return dict(rows[0])

    @classmethod
    def _get_component(cls, org_id: str, component_id: str) -> dict:
        return cls._load_component(org_id, component_id)
