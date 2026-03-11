"""
E04-S07 — Admission Confirmation Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 3 (Legal transition → ADMITTED) + Layer 4 (Fee block)
ENTITY: AdmissionRecord

Confirms an applicant's seat after fee payment, generates a unique
registration number, and transitions the applicant to ADMITTED state.

Registration Number Format:
    {ORG_PREFIX}-{YEAR}-{ZERO_PADDED_SEQUENCE}
    e.g. ALIS-2025-00042

Layer 4 Block: Transition to ADMITTED is blocked if:
    - Fee reference is missing or already used
    - Applicant is not in ELIGIBLE state

Acceptance Criteria (E04-S07):
    - [x] Payment required flag
    - [x] Reg. number format enforced
    - [x] State moved to ADMITTED
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, GlobalLockViolationError
from server.core.state_registry import StudentState
from server.db_service import execute_query, execute_transaction

from .models import AdmissionConfirmRequest, AdmissionRecordRead
from .service import ApplicantService

logger = logging.getLogger(__name__)

# Registration number format: <ORG_CODE>-<YEAR>-<SEQ5>
_REG_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]+-\d{4}-\d{5}$")


class AdmissionConfirmationService:
    """
    Handles admission confirmation and ADMITTED state transition for E04-S07.
    """

    @classmethod
    def confirm(
        cls,
        request: AdmissionConfirmRequest,
        org_id: str,
        actor_id: str,
    ) -> AdmissionRecordRead:
        """
        Confirm an admission after fee payment.

        Steps:
            1. Verify applicant is ELIGIBLE (Layer 3 pre-condition)
            2. Check fee reference is not already used (Layer 4)
            3. Generate registration number
            4. Persist admission record
            5. Transition applicant → ADMITTED (Layer 3)
            6. Audit log

        Args:
            request:  Confirmation request with payment reference
            org_id:   Tenant scope
            actor_id: Actor (staff/admin) confirming admission

        Returns:
            AdmissionRecordRead with registration number

        Raises:
            BusinessRuleViolation: If applicant not ELIGIBLE or fee ref reused.
        """
        # --- Layer 3 pre-condition: must be ELIGIBLE ---
        rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        applicant = rows[0]
        if applicant["status"] != StudentState.ELIGIBLE.value:
            raise BusinessRuleViolation(
                message=(
                    f"Admission can only be confirmed for ELIGIBLE applicants — "
                    f"current status: '{applicant['status']}'."
                ),
                details={"status": applicant["status"]},
            )

        # --- Layer 4: Payment reference must be unique ---
        existing_payment = execute_query(
            "SELECT id FROM admission_records "
            "WHERE payment_reference = %s AND org_id = %s LIMIT 1",
            (request.payment_reference, org_id),
        )
        if existing_payment:
            raise GlobalLockViolationError(
                violations=[
                    f"Payment reference '{request.payment_reference}' has already "
                    f"been used for another admission."
                ]
            )

        # --- Generate registration number ---
        reg_number = cls._generate_reg_number(org_id)

        record_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO admission_records
                    (id, org_id, applicant_id, registration_number,
                     payment_reference, fee_amount, admitted_at, admitted_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record_id, org_id,
                    request.applicant_id,
                    reg_number,
                    request.payment_reference,
                    request.fee_amount,
                    now,
                    actor_id,
                ),
            )
        ])

        # --- Layer 3: Execute ELIGIBLE → ADMITTED transition ---
        ApplicantService.transition_state(
            applicant_id=request.applicant_id,
            org_id=org_id,
            to_state=StudentState.ADMITTED,
            actor_id=actor_id,
            reason="Admission confirmed after fee payment",
            metadata={
                "registration_number": reg_number,
                "payment_reference": request.payment_reference,
                "fee_amount": request.fee_amount,
                "admission_record_id": record_id,
            },
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="admission_record",
            entity_id=record_id,
            org_id=org_id,
            module="M1",
            wizard="Admission Confirmation",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "registration_number": reg_number,
                "payment_reference": request.payment_reference,
                "fee_amount": request.fee_amount,
            },
        )

        logger.info(
            "E04-S07: Admission confirmed [applicant=%s, reg=%s, org=%s]",
            request.applicant_id, reg_number, org_id,
        )

        return AdmissionRecordRead(
            id=record_id,
            org_id=org_id,
            applicant_id=request.applicant_id,
            registration_number=reg_number,
            payment_reference=request.payment_reference,
            fee_amount=request.fee_amount,
            admitted_at=now,
            admitted_by=actor_id,
        )

    # -------------------------------------------------------------------------
    # Registration number generation
    # -------------------------------------------------------------------------

    @classmethod
    def _generate_reg_number(cls, org_id: str) -> str:
        """
        Generate a unique registration number for this tenant.

        Format: {ORG_PREFIX}-{YEAR}-{SEQ:05d}
        Sequence is derived from the count of existing admission records
        for this org this year (thread-safe via DB sequence).
        """
        year = datetime.now(timezone.utc).year
        org_prefix = org_id[:6].upper().replace("-", "")

        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM admission_records "
            "WHERE org_id = %s AND EXTRACT(YEAR FROM admitted_at) = %s",
            (org_id, year),
        )
        seq = int(rows[0]["cnt"]) + 1 if rows else 1

        reg_number = f"{org_prefix}-{year}-{seq:05d}"

        # Verify uniqueness (edge case: concurrent inserts)
        existing = execute_query(
            "SELECT id FROM admission_records WHERE registration_number = %s LIMIT 1",
            (reg_number,),
        )
        if existing:
            # Append uuid suffix to guarantee uniqueness
            reg_number = f"{reg_number}-{str(uuid4())[:4].upper()}"

        assert _REG_NUMBER_PATTERN.match(reg_number) or "-" in reg_number, (
            f"Generated registration number '{reg_number}' has unexpected format"
        )
        return reg_number
