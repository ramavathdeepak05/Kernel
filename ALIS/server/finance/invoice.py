"""E07-S02 — Invoice Generation

Generates invoices from fee structures. Supports:
- Single student invoice
- Bulk invoice generation for all enrolled students in a program/semester
- Automatic discount application (scholarships + approved waivers)
"""

import json
import logging
import uuid
from datetime import datetime

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import InvoiceBulkCreate, InvoiceCreate

logger = logging.getLogger(__name__)


def _invoice_number(org_id: str, student_id: str, year: str) -> str:
    seq = execute_query(
        "SELECT COUNT(*) AS cnt FROM student_invoices WHERE org_id = %s AND academic_year = %s",
        (org_id, year),
    )
    n = int(seq[0]["cnt"]) + 1 if seq else 1
    prefix = org_id[:4].upper().replace("-", "")
    return f"INV-{prefix}-{year.replace('-', '')}-{n:05d}"


class InvoiceService:

    @classmethod
    def create_for_student(cls, org_id: str, req: InvoiceCreate, actor_id: str) -> dict:
        # Validate student
        student = execute_query(
            "SELECT id, name FROM students WHERE id = %s AND org_id = %s",
            (req.student_id, org_id),
        )
        if not student:
            raise NotFoundError(f"Student {req.student_id} not found")

        # Validate fee structure
        structure = execute_query(
            "SELECT * FROM fee_structures WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (req.fee_structure_id, org_id),
        )
        if not structure:
            raise NotFoundError(f"Fee structure {req.fee_structure_id} not found")
        struct = dict(structure[0])

        # Idempotency — one invoice per student per structure
        existing = execute_query(
            "SELECT id FROM student_invoices WHERE student_id = %s AND fee_structure_id = %s AND org_id = %s",
            (req.student_id, req.fee_structure_id, org_id),
        )
        if existing:
            return cls.get(org_id, str(existing[0]["id"]))

        # Compute scholarship discount
        discount = cls._compute_scholarship_discount(
            org_id, req.student_id, req.academic_year, float(struct["total_amount"])
        )

        inv_num = _invoice_number(org_id, req.student_id, req.academic_year)
        iid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO student_invoices
                (id, org_id, student_id, fee_structure_id, academic_year, semester,
                 invoice_number, amount_due, discount, currency, due_date, generated_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (iid, org_id, req.student_id, req.fee_structure_id,
             req.academic_year, req.semester,
             inv_num, struct["total_amount"], discount,
             struct["currency"], req.due_date, actor_id, req.notes),
        )])

        DomainEventBus.publish(DomainEvent(
            event_type="InvoiceGenerated",
            entity_type="student_invoice",
            entity_id=iid,
            org_id=org_id,
            payload={"student_id": req.student_id, "amount_due": float(struct["total_amount"]),
                     "invoice_number": inv_num, "due_date": req.due_date},
            actor_id=actor_id,
        ))

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="student_invoice", entity_id=iid, org_id=org_id,
                     module="E07-S02",
                     metadata={"invoice_number": inv_num, "amount_due": float(struct["total_amount"])})

        return cls.get(org_id, iid)

    @classmethod
    def bulk_generate(cls, org_id: str, req: InvoiceBulkCreate, actor_id: str) -> dict:
        """Generate invoices for all enrolled students in a program/semester."""
        structure = execute_query(
            "SELECT * FROM fee_structures WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (req.fee_structure_id, org_id),
        )
        if not structure:
            raise NotFoundError(f"Fee structure {req.fee_structure_id} not found")
        struct = dict(structure[0])

        if req.student_ids:
            student_ids = req.student_ids
        else:
            # All enrolled students for this program/semester
            enrolled = execute_query(
                """
                SELECT DISTINCT ce.student_id
                FROM course_enrollments ce
                JOIN courses c ON c.id = ce.course_id
                WHERE c.program_id = %s AND ce.academic_year = %s
                  AND ce.status = 'ENROLLED' AND c.org_id = %s
                """,
                (struct["program_id"], req.academic_year, org_id),
            )
            if not enrolled and struct["program_id"] is None:
                enrolled = execute_query(
                    "SELECT id AS student_id FROM students WHERE org_id = %s AND status = 'ACTIVE'",
                    (org_id,),
                )
            student_ids = [str(r["student_id"]) for r in enrolled]

        generated = 0
        skipped   = 0
        for student_id in student_ids:
            existing = execute_query(
                "SELECT id FROM student_invoices WHERE student_id = %s AND fee_structure_id = %s AND org_id = %s",
                (student_id, req.fee_structure_id, org_id),
            )
            if existing:
                skipped += 1
                continue

            discount = cls._compute_scholarship_discount(
                org_id, student_id, req.academic_year, float(struct["total_amount"])
            )
            inv_num = _invoice_number(org_id, student_id, req.academic_year)
            iid = str(uuid.uuid4())
            execute_transaction([(
                """
                INSERT INTO student_invoices
                    (id, org_id, student_id, fee_structure_id, academic_year, semester,
                     invoice_number, amount_due, discount, currency, due_date, generated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (iid, org_id, student_id, req.fee_structure_id,
                 req.academic_year, req.semester,
                 inv_num, struct["total_amount"], discount,
                 struct["currency"], req.due_date, actor_id),
            )])
            generated += 1

        logger.info("Bulk invoice: generated=%d skipped=%d for %s", generated, skipped, req.academic_year)
        return {"generated": generated, "skipped": skipped, "academic_year": req.academic_year}

    @classmethod
    def get(cls, org_id: str, invoice_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM student_invoices WHERE id = %s AND org_id = %s",
            (invoice_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str,
                          academic_year: str | None = None) -> list[dict]:
        sql = "SELECT * FROM student_invoices WHERE student_id = %s AND org_id = %s"
        params: list = [student_id, org_id]
        if academic_year:
            sql += " AND academic_year = %s"
            params.append(academic_year)
        sql += " ORDER BY generated_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def mark_overdue(cls, org_id: str) -> int:
        """Called by Celery beat daily. Marks unpaid invoices past due_date as OVERDUE."""
        result = execute_query(
            """
            UPDATE student_invoices
            SET status = 'OVERDUE'
            WHERE org_id = %s AND status = 'UNPAID' AND due_date < CURRENT_DATE
            RETURNING id
            """,
            (org_id,),
        )
        return len(result)

    @classmethod
    def _compute_scholarship_discount(cls, org_id: str, student_id: str,
                                       academic_year: str, total: float) -> float:
        """Sum up all active scholarship discounts for this student."""
        assignments = execute_query(
            """
            SELECT s.discount_type, s.discount_value
            FROM scholarship_assignments sa
            JOIN scholarships s ON s.id = sa.scholarship_id
            WHERE sa.student_id = %s AND sa.academic_year = %s
              AND sa.status = 'ACTIVE' AND sa.org_id = %s
            """,
            (student_id, academic_year, org_id),
        )
        discount = 0.0
        for a in assignments:
            if a["discount_type"] == "PERCENTAGE":
                discount += (float(a["discount_value"]) / 100) * total
            else:
                discount += float(a["discount_value"])
        return min(round(discount, 2), total)
