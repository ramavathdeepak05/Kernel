"""
FM-3 — Refund & Cancellation Policy (UGC Mandatory)

Implements UGC refund regulations (mandatory for all institutions):
- 15+ days before classes: Full refund minus ₹1,000 processing fee
- Within 15 days of classes: Proportional deduction
- After 30 days: No refund (except documented medical/compassionate)

Also:
- Fee version locking per student (FM-1 gap)
- Scholarship revocation uses reversal entries, never UPDATE (EC-FIN-03)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class RefundStatus(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    REFUNDED = "REFUNDED"
    REJECTED = "REJECTED"


class UGCRefundPolicyService:
    """
    Computes refund amounts per UGC refund policy.

    Reference: UGC (Refund of Fees on Cancellation of Admission) Regulations.
    """

    PROCESSING_FEE = 1000.0  # ₹1,000 processing fee (non-refundable)

    @classmethod
    def compute_refund(
        cls,
        cancellation_date: datetime,
        class_start_date: datetime,
        total_fee_paid: float,
        reason: str = "voluntary",
    ) -> Dict[str, Any]:
        """
        Compute refund amount per UGC policy.

        Returns refund breakdown with policy justification.
        """
        days_before = (class_start_date - cancellation_date).days

        if days_before > 15:
            # 15+ days before: full refund minus processing fee
            refund = max(total_fee_paid - cls.PROCESSING_FEE, 0)
            policy = "UGC: >15 days before classes — full refund minus ₹1,000 processing fee"
            deduction_pct = 0.0
        elif 0 < days_before <= 15:
            # Within 15 days: proportional deduction
            deduction_pct = (15 - days_before) / 15 * 100
            deduction = total_fee_paid * (deduction_pct / 100) + cls.PROCESSING_FEE
            refund = max(total_fee_paid - deduction, 0)
            policy = f"UGC: {days_before} days before classes — {deduction_pct:.0f}% proportional deduction"
        else:
            # After class start
            if reason in ("medical", "compassionate", "death_in_family"):
                # Special cases: 50% refund with documentation
                refund = total_fee_paid * 0.5
                deduction_pct = 50.0
                policy = f"UGC: post-start {reason} exception — 50% refund with documentation"
            else:
                refund = 0
                deduction_pct = 100.0
                policy = "UGC: after class start — no refund (voluntary withdrawal)"

        return {
            "total_fee_paid": total_fee_paid,
            "refund_amount": round(refund, 2),
            "processing_fee": cls.PROCESSING_FEE,
            "deduction_percentage": round(deduction_pct, 1),
            "days_before_classes": days_before,
            "policy_applied": policy,
            "reason": reason,
        }

    @classmethod
    def request_refund(
        cls,
        org_id: str,
        student_id: str,
        total_fee_paid: float,
        class_start_date: datetime,
        reason: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Submit a refund request. Computes amount per UGC policy."""
        now = datetime.now(timezone.utc)
        computation = cls.compute_refund(now, class_start_date, total_fee_paid, reason)

        refund_id = str(uuid4())
        execute_transaction([
            (
                """
                INSERT INTO refund_requests
                    (id, org_id, student_id, total_fee_paid, refund_amount,
                     processing_fee, deduction_pct, policy_applied, reason,
                     status, requested_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    refund_id, org_id, student_id, total_fee_paid,
                    computation["refund_amount"], computation["processing_fee"],
                    computation["deduction_percentage"], computation["policy_applied"],
                    reason, RefundStatus.REQUESTED.value, actor_id, now,
                ),
            )
        ], tenant_id=org_id)

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_role="finance",
            entity_type="refund_request", entity_id=refund_id, tenant_id=org_id,
            metadata=computation,
        )
        return {"id": refund_id, **computation, "status": RefundStatus.REQUESTED.value}

    @classmethod
    def approve_refund(cls, org_id: str, refund_id: str, actor_id: str) -> Dict[str, Any]:
        execute_transaction([
            ("UPDATE refund_requests SET status = %s, approved_by = %s, approved_at = NOW() "
             "WHERE id = %s AND org_id = %s AND status = %s",
             (RefundStatus.APPROVED.value, actor_id, refund_id, org_id, RefundStatus.REQUESTED.value))
        ], tenant_id=org_id)
        return {"id": refund_id, "status": RefundStatus.APPROVED.value}


class FeeVersionLockService:
    """
    FM-1 Gap: Fee version locking per student.

    When a student is admitted, they are locked to the fee structure
    version that was active at admission time. Fee hikes in subsequent
    years do NOT affect already-admitted students.
    """

    @classmethod
    def lock_fee_version(
        cls, org_id: str, student_id: str, fee_structure_id: str, academic_year: str,
    ) -> Dict[str, Any]:
        """Lock a student to a specific fee structure version at admission."""
        assignment_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO student_fee_assignments
                    (id, org_id, student_id, fee_structure_id, academic_year,
                     locked_at, is_locked)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (org_id, student_id, fee_structure_id)
                DO NOTHING
                """,
                (assignment_id, org_id, student_id, fee_structure_id, academic_year, now),
            )
        ], tenant_id=org_id)

        return {"assignment_id": assignment_id, "locked": True}

    @classmethod
    def get_locked_fee(cls, org_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        """Get the locked fee structure for a student."""
        rows = execute_query(
            """
            SELECT sfa.id, sfa.fee_structure_id, sfa.academic_year, sfa.locked_at,
                   fs.name AS fee_structure_name, fs.total_amount
            FROM student_fee_assignments sfa
            JOIN fee_structures fs ON fs.id = sfa.fee_structure_id
            WHERE sfa.org_id = %s AND sfa.student_id = %s AND sfa.is_locked = TRUE
            ORDER BY sfa.locked_at DESC LIMIT 1
            """,
            (org_id, student_id),
            tenant_id=org_id,
        )
        return dict(rows[0]) if rows else None
