"""
P10 — Payment v2 (Stage 8)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 3 (State Transitions) + Layer 6 (Audit)
ENTITIES: DemandDraftUpload, RefundRequest

Manages payment workflows for confirmed applicants:

  DemandDraftService
    - submit():   Applicant submits DD scan as proof of fee payment
    - verify():   Staff verifies DD → transitions applicant SEAT_CONFIRMED → VERIFICATION_PENDING
    - reject():   Staff rejects DD (with reason) → applicant must resubmit
    - list/get

  RefundRequestService
    - submit():   Applicant requests refund; amount computed from refund policy slabs
    - review():   Staff approves/rejects with notes
    - process():  Finance records gateway refund reference → PROCESSED
    - list/get

Refund Policy Slabs (configurable via institution_policies):
    Key: admissions.refund_policy
    Default:
        0–15 days from confirmation:    100%
        16–30 days:                     80%
        31–45 days:                     50%
        >45 days:                       0%

State transitions owned here:
    SEAT_CONFIRMED + DD verified → VERIFICATION_PENDING
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation
from server.core.state_registry import StudentState
from server.db_service import execute_query, execute_transaction

from .service import ApplicantService

logger = logging.getLogger(__name__)


# =============================================================================
# Default refund policy slabs
# =============================================================================

_DEFAULT_REFUND_SLABS = [
    {"label": "BEFORE_15_DAYS_100PCT", "max_days": 15, "pct": 100.0},
    {"label": "DAY_15_TO_30_80PCT", "max_days": 30, "pct": 80.0},
    {"label": "DAY_30_TO_45_50PCT", "max_days": 45, "pct": 50.0},
    {"label": "AFTER_45_DAYS_0PCT", "max_days": None, "pct": 0.0},
]

_DD_STATUSES = {"PENDING", "VERIFIED", "REJECTED"}
_REFUND_STATUSES = {"REQUESTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "PROCESSED"}


# =============================================================================
# Pydantic Models
# =============================================================================


class DemandDraftCreate(BaseModel):
    applicant_id: str
    dd_number: str = Field(..., min_length=3, max_length=50)
    bank_name: str = Field(..., min_length=2, max_length=200)
    branch_name: str | None = None
    amount: float = Field(..., gt=0)
    dd_date: str = Field(..., description="ISO date: YYYY-MM-DD")
    scan_file_path: str | None = Field(
        default=None,
        description="Path in MinIO after file upload (optional at submission)",
    )


class DemandDraftRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    dd_number: str
    bank_name: str
    branch_name: str | None = None
    amount: float
    dd_date: str
    scan_file_path: str | None = None
    verification_status: str  # PENDING | VERIFIED | REJECTED
    verified_by: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime


class RefundRequestCreate(BaseModel):
    applicant_id: str
    payment_id: str | None = Field(
        default=None,
        description="Finance payment record ID (if linked to a payments row)",
    )
    amount_paid: float = Field(..., gt=0, description="Total amount paid by applicant")
    reason: str = Field(..., min_length=10, max_length=2000)


class RefundRequestRead(BaseModel):
    id: str
    org_id: str
    applicant_id: str
    payment_id: str | None = None
    amount_paid: float
    refund_amount: float
    refund_policy_slab: str | None = None
    reason: str
    status: str  # REQUESTED | UNDER_REVIEW | APPROVED | REJECTED | PROCESSED
    requested_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    processed_at: datetime | None = None
    gateway_refund_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


# =============================================================================
# DEMAND DRAFT SERVICE
# =============================================================================


class DemandDraftService:
    """
    Manages demand draft (DD) submissions and staff verification workflow.

    Flow:
        Applicant submits DD details → PENDING
        Staff verifies → VERIFIED  → applicant → VERIFICATION_PENDING
        Staff rejects  → REJECTED  → applicant resubmits
    """

    @classmethod
    def submit(
        cls,
        request: DemandDraftCreate,
        org_id: str,
        actor_id: str,
    ) -> DemandDraftRead:
        """
        Applicant submits demand draft details as proof of fee payment.

        Pre-condition: applicant must be SEAT_CONFIRMED.
        Duplicate DD numbers are rejected (within org).
        """
        # --- Pre-condition: SEAT_CONFIRMED ---
        app_rows = execute_query(
            "SELECT status FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        status = app_rows[0]["status"]
        if status not in (StudentState.SEAT_CONFIRMED.value, "SEAT_CONFIRMED"):
            raise BusinessRuleViolation(
                message=(
                    f"DD can only be submitted for SEAT_CONFIRMED applicants — "
                    f"current status: '{status}'."
                ),
                details={"applicant_id": request.applicant_id, "status": status},
            )

        # --- Duplicate DD number check ---
        dup = execute_query(
            "SELECT id FROM demand_draft_uploads "
            "WHERE dd_number = %s AND org_id = %s AND verification_status != 'REJECTED'",
            (request.dd_number, org_id),
        )
        if dup:
            raise BusinessRuleViolation(
                message=f"DD number '{request.dd_number}' has already been submitted.",
                details={"dd_number": request.dd_number},
            )

        dd_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO demand_draft_uploads (
                    id, org_id, applicant_id, dd_number, bank_name,
                    branch_name, amount, dd_date, scan_file_path,
                    verification_status, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                    (
                        dd_id,
                        org_id,
                        request.applicant_id,
                        request.dd_number,
                        request.bank_name,
                        request.branch_name,
                        request.amount,
                        request.dd_date,
                        request.scan_file_path,
                        "PENDING",
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="demand_draft",
            entity_id=dd_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "dd_number": request.dd_number,
                "amount": request.amount,
            },
        )

        logger.info(
            "P10: DD submitted [id=%s, applicant=%s, amount=%.2f]",
            dd_id,
            request.applicant_id,
            request.amount,
        )
        return cls.get(dd_id, org_id)

    @classmethod
    def verify(
        cls,
        dd_id: str,
        org_id: str,
        actor_id: str,
    ) -> DemandDraftRead:
        """
        Staff verifies a demand draft.

        On verification:
        - Sets verification_status = VERIFIED
        - Transitions applicant → VERIFICATION_PENDING
        """
        dd = cls._require_dd(dd_id, org_id)

        if dd["verification_status"] != "PENDING":
            raise BusinessRuleViolation(
                message=(
                    f"DD '{dd_id}' cannot be verified — "
                    f"current status: '{dd['verification_status']}'."
                ),
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    "UPDATE demand_draft_uploads "
                    "SET verification_status = 'VERIFIED', verified_by = %s, verified_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (actor_id, now, dd_id, org_id),
                )
            ]
        )

        # Transition applicant → VERIFICATION_PENDING
        ApplicantService.transition_state(
            applicant_id=dd["applicant_id"],
            org_id=org_id,
            to_state=StudentState.VERIFICATION_PENDING,
            actor_id=actor_id,
            reason=f"DD {dd['dd_number']} verified by {actor_id}",
            metadata={
                "dd_id": dd_id,
                "dd_number": dd["dd_number"],
                "amount": float(dd["amount"]),
            },
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="demand_draft",
            entity_id=dd_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={"action": "verified", "applicant_id": dd["applicant_id"]},
        )

        logger.info("P10: DD verified [id=%s, applicant=%s]", dd_id, dd["applicant_id"])
        return cls.get(dd_id, org_id)

    @classmethod
    def reject(
        cls,
        dd_id: str,
        org_id: str,
        actor_id: str,
        reason: str,
    ) -> DemandDraftRead:
        """
        Staff rejects a demand draft.

        Applicant must resubmit a new DD. No state transition — applicant
        remains SEAT_CONFIRMED.
        """
        if not reason or len(reason.strip()) < 5:
            raise BusinessRuleViolation(
                message="Rejection reason must be at least 5 characters."
            )

        dd = cls._require_dd(dd_id, org_id)

        if dd["verification_status"] != "PENDING":
            raise BusinessRuleViolation(
                message=f"DD '{dd_id}' is not PENDING. Cannot reject.",
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    "UPDATE demand_draft_uploads "
                    "SET verification_status = 'REJECTED', verified_by = %s, verified_at = %s, "
                    "rejection_reason = %s WHERE id = %s AND org_id = %s",
                    (actor_id, now, reason.strip(), dd_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="demand_draft",
            entity_id=dd_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={
                "action": "rejected",
                "applicant_id": dd["applicant_id"],
                "reason": reason,
            },
        )

        logger.info("P10: DD rejected [id=%s, reason=%s]", dd_id, reason)
        return cls.get(dd_id, org_id)

    @classmethod
    def get(cls, dd_id: str, org_id: str) -> DemandDraftRead:
        rows = execute_query(
            "SELECT * FROM demand_draft_uploads WHERE id = %s AND org_id = %s",
            (dd_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Demand draft '{dd_id}' not found.")
        return cls._row_to_read(rows[0])

    @classmethod
    def list_for_applicant(
        cls,
        applicant_id: str,
        org_id: str,
        status: str | None = None,
    ) -> list[DemandDraftRead]:
        conditions = ["applicant_id = %s", "org_id = %s"]
        params: list = [applicant_id, org_id]
        if status:
            conditions.append("verification_status = %s")
            params.append(status)
        rows = execute_query(
            f"SELECT * FROM demand_draft_uploads WHERE {' AND '.join(conditions)} "  # noqa: S608
            "ORDER BY created_at DESC",
            tuple(params),
        )
        return [cls._row_to_read(r) for r in rows]

    @classmethod
    def _require_dd(cls, dd_id: str, org_id: str) -> dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM demand_draft_uploads WHERE id = %s AND org_id = %s",
            (dd_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Demand draft '{dd_id}' not found.")
        return rows[0]

    @classmethod
    def _row_to_read(cls, row: dict[str, Any]) -> DemandDraftRead:
        data = dict(row)
        # Coerce Decimal → float for Pydantic
        if isinstance(data.get("amount"), Decimal):
            data["amount"] = float(data["amount"])
        # Coerce date → str
        if hasattr(data.get("dd_date"), "isoformat"):
            data["dd_date"] = data["dd_date"].isoformat()
        return DemandDraftRead(**data)


# =============================================================================
# REFUND REQUEST SERVICE
# =============================================================================


class RefundRequestService:
    """
    Manages refund requests from applicants who have paid confirmation fees.

    Refund amount is calculated by policy slabs (loaded from institution_policies
    or falling back to module defaults). Slabs are based on days elapsed since
    the applicant's seat confirmation.

    Workflow:
        Applicant submits → REQUESTED
        Staff reviews     → UNDER_REVIEW → APPROVED | REJECTED
        Finance processes → PROCESSED (gateway_refund_id recorded)
    """

    _POLICY_KEY = "admissions.refund_policy"

    @classmethod
    def submit(
        cls,
        request: RefundRequestCreate,
        org_id: str,
        actor_id: str,
    ) -> RefundRequestRead:
        """
        Submit a refund request.

        Calculates the eligible refund amount using policy slabs and the
        number of days since the applicant's seat was confirmed.

        Pre-condition: applicant must be SEAT_CONFIRMED or VERIFICATION_PENDING.
        One active (non-rejected) refund request per applicant.
        """
        # --- Load applicant confirmation date ---
        app_rows = execute_query(
            "SELECT status, status_updated_at FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        status = app_rows[0]["status"]
        allowed = {
            StudentState.SEAT_CONFIRMED.value,
            "SEAT_CONFIRMED",
            StudentState.VERIFICATION_PENDING.value,
            "VERIFICATION_PENDING",
        }
        if status not in allowed:
            raise BusinessRuleViolation(
                message=(
                    f"Refund requests are only available for SEAT_CONFIRMED or "
                    f"VERIFICATION_PENDING applicants — current status: '{status}'."
                ),
                details={"status": status},
            )

        # --- Duplicate check ---
        existing = execute_query(
            "SELECT id FROM refund_requests "
            "WHERE applicant_id = %s AND org_id = %s AND status != 'REJECTED'",
            (request.applicant_id, org_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message="An active refund request already exists for this applicant.",
                details={"existing_id": existing[0]["id"]},
            )

        # --- Calculate refund amount from policy slabs ---
        confirmation_date = app_rows[0].get("status_updated_at") or datetime.now(
            timezone.utc
        )
        days_since = (datetime.now(timezone.utc) - confirmation_date).days
        slabs = cls._load_slabs(org_id)
        slab_label, refund_pct = cls._calculate_slab(days_since, slabs)
        refund_amount = round(request.amount_paid * refund_pct / 100, 2)

        request_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO refund_requests (
                    id, org_id, applicant_id, payment_id, amount_paid,
                    refund_amount, refund_policy_slab, reason, status,
                    requested_by, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                    (
                        request_id,
                        org_id,
                        request.applicant_id,
                        request.payment_id,
                        request.amount_paid,
                        refund_amount,
                        slab_label,
                        request.reason,
                        "REQUESTED",
                        actor_id,
                        now,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="refund_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "amount_paid": request.amount_paid,
                "refund_amount": refund_amount,
                "slab": slab_label,
                "days_since_confirmation": days_since,
            },
        )

        logger.info(
            "P10: Refund request submitted [id=%s, applicant=%s, amount=%.2f, slab=%s]",
            request_id,
            request.applicant_id,
            refund_amount,
            slab_label,
        )
        return cls.get(request_id, org_id)

    @classmethod
    def review(
        cls,
        request_id: str,
        org_id: str,
        actor_id: str,
        decision: str,
        notes: str | None = None,
    ) -> RefundRequestRead:
        """
        Staff reviews a refund request (APPROVED or REJECTED).

        APPROVED → moves to APPROVED (awaiting finance processing)
        REJECTED → request closed; no refund issued
        """
        valid_decisions = {"APPROVED", "REJECTED"}
        if decision not in valid_decisions:
            raise BusinessRuleViolation(
                message=f"Invalid decision '{decision}'.",
                details={"valid": list(valid_decisions)},
            )

        req_row = cls._require_request(request_id, org_id)

        if req_row["status"] not in ("REQUESTED", "UNDER_REVIEW"):
            raise BusinessRuleViolation(
                message=(
                    f"Refund request '{request_id}' cannot be reviewed — "
                    f"current status: '{req_row['status']}'."
                ),
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    "UPDATE refund_requests "
                    "SET status = %s, reviewed_by = %s, reviewed_at = %s, "
                    "review_notes = %s, updated_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (decision, actor_id, now, notes, now, request_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="refund_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={
                "action": decision.lower(),
                "applicant_id": req_row["applicant_id"],
                "notes": notes,
            },
        )

        logger.info("P10: Refund %s [id=%s]", decision.lower(), request_id)
        return cls.get(request_id, org_id)

    @classmethod
    def process(
        cls,
        request_id: str,
        org_id: str,
        actor_id: str,
        gateway_refund_id: str,
    ) -> RefundRequestRead:
        """
        Finance records the completed refund with gateway reference.
        Moves status → PROCESSED.
        """
        if not gateway_refund_id or not gateway_refund_id.strip():
            raise BusinessRuleViolation(
                message="gateway_refund_id is required to process a refund."
            )

        req_row = cls._require_request(request_id, org_id)

        if req_row["status"] != "APPROVED":
            raise BusinessRuleViolation(
                message=f"Only APPROVED refund requests can be processed — status: '{req_row['status']}'.",
            )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    "UPDATE refund_requests "
                    "SET status = 'PROCESSED', gateway_refund_id = %s, "
                    "processed_at = %s, updated_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (gateway_refund_id.strip(), now, now, request_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="refund_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Payment v2",
            success=True,
            metadata={
                "action": "processed",
                "gateway_refund_id": gateway_refund_id,
                "applicant_id": req_row["applicant_id"],
            },
        )

        logger.info(
            "P10: Refund processed [id=%s, gateway=%s]", request_id, gateway_refund_id
        )
        return cls.get(request_id, org_id)

    @classmethod
    def get(cls, request_id: str, org_id: str) -> RefundRequestRead:
        rows = execute_query(
            "SELECT * FROM refund_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Refund request '{request_id}' not found."
            )
        return cls._row_to_read(rows[0])

    @classmethod
    def list_for_applicant(
        cls,
        applicant_id: str,
        org_id: str,
    ) -> list[RefundRequestRead]:
        rows = execute_query(
            "SELECT * FROM refund_requests WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY created_at DESC",
            (applicant_id, org_id),
        )
        return [cls._row_to_read(r) for r in rows]

    @classmethod
    def list_pending_review(cls, org_id: str) -> list[RefundRequestRead]:
        """Return all REQUESTED or UNDER_REVIEW requests for staff dashboard."""
        rows = execute_query(
            "SELECT * FROM refund_requests "
            "WHERE org_id = %s AND status IN ('REQUESTED', 'UNDER_REVIEW') "
            "ORDER BY created_at ASC",
            (org_id,),
        )
        return [cls._row_to_read(r) for r in rows]

    # -------------------------------------------------------------------------
    # Refund slab helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _load_slabs(cls, org_id: str) -> list:
        """Load refund policy slabs from institution_policies or use defaults."""
        rows = execute_query(
            "SELECT value FROM institution_policies "
            "WHERE org_id = %s AND key = %s AND is_active = TRUE",
            (org_id, cls._POLICY_KEY),
        )
        if not rows:
            return _DEFAULT_REFUND_SLABS
        try:
            val = rows[0]["value"]
            slabs = val if isinstance(val, list) else json.loads(val)
            return slabs if isinstance(slabs, list) and slabs else _DEFAULT_REFUND_SLABS
        except Exception:
            return _DEFAULT_REFUND_SLABS

    @classmethod
    def _calculate_slab(cls, days_since: int, slabs: list) -> tuple[str, float]:
        """Return (slab_label, refund_percentage) for the given days elapsed."""
        for slab in slabs:
            max_days = slab.get("max_days")
            if max_days is None or days_since <= max_days:
                return slab["label"], float(slab["pct"])
        # Fallback: no refund
        return "NO_REFUND", 0.0

    @classmethod
    def _require_request(cls, request_id: str, org_id: str) -> dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM refund_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Refund request '{request_id}' not found."
            )
        return rows[0]

    @classmethod
    def _row_to_read(cls, row: dict[str, Any]) -> RefundRequestRead:
        data = dict(row)
        for key in ("amount_paid", "refund_amount"):
            if isinstance(data.get(key), Decimal):
                data[key] = float(data[key])
        return RefundRequestRead(**data)
