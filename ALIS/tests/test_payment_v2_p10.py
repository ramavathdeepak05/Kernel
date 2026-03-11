"""
Tests for P10 — Payment v2 (Stage 8)

Covers:
  DemandDraftService:
    - submit(): SEAT_CONFIRMED pre-condition, duplicate DD rejection
    - verify(): PENDING → VERIFIED, state transition → VERIFICATION_PENDING
    - reject(): PENDING → REJECTED, reason validation
    - get() / list_for_applicant()

  RefundRequestService:
    - submit(): slab calculation (100%/80%/50%/0%), SEAT_CONFIRMED pre-condition
    - review(): APPROVED / REJECTED, invalid status guard
    - process(): gateway_refund_id required, APPROVED guard
    - get() / list_for_applicant() / list_pending_review()

  Refund slab helpers:
    - _calculate_slab() for each band
    - _load_slabs() fallback to defaults when policy not configured
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from server.admissions.payment_v2 import (
    DemandDraftCreate,
    DemandDraftRead,
    DemandDraftService,
    RefundRequestCreate,
    RefundRequestRead,
    RefundRequestService,
    _DEFAULT_REFUND_SLABS,
)
from server.core.exceptions import BusinessRuleViolation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_ID = "org-p10"
ACTOR_ID = "staff-001"
APPLICANT_ID = str(uuid4())
DD_ID = str(uuid4())
REFUND_ID = str(uuid4())

MOD = "server.admissions.payment_v2"

_NOW = datetime.now(timezone.utc)

_BASE_DD_ROW = {
    "id": DD_ID,
    "org_id": ORG_ID,
    "applicant_id": APPLICANT_ID,
    "dd_number": "DD-2025-001234",
    "bank_name": "State Bank of India",
    "branch_name": "Mumbai Main",
    "amount": Decimal("120000.00"),
    "dd_date": "2025-06-01",
    "scan_file_path": "/dd/scan.pdf",
    "verification_status": "PENDING",
    "verified_by": None,
    "verified_at": None,
    "rejection_reason": None,
    "created_at": _NOW,
}

_BASE_REFUND_ROW = {
    "id": REFUND_ID,
    "org_id": ORG_ID,
    "applicant_id": APPLICANT_ID,
    "payment_id": None,
    "amount_paid": Decimal("120000.00"),
    "refund_amount": Decimal("120000.00"),
    "refund_policy_slab": "BEFORE_15_DAYS_100PCT",
    "reason": "I am withdrawing my admission due to personal reasons.",
    "status": "REQUESTED",
    "requested_by": ACTOR_ID,
    "reviewed_by": None,
    "reviewed_at": None,
    "review_notes": None,
    "processed_at": None,
    "gateway_refund_id": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}


# =============================================================================
# DemandDraftCreate model
# =============================================================================

class TestDDModel:
    def test_valid_create(self):
        req = DemandDraftCreate(
            applicant_id=APPLICANT_ID,
            dd_number="DD-001",
            bank_name="SBI",
            amount=50000,
            dd_date="2025-06-15",
        )
        assert req.amount == 50000
        assert req.branch_name is None

    def test_amount_must_be_positive(self):
        with pytest.raises(Exception):
            DemandDraftCreate(
                applicant_id="a1", dd_number="X", bank_name="SBI",
                amount=0, dd_date="2025-06-01",
            )

    def test_dd_number_min_length(self):
        with pytest.raises(Exception):
            DemandDraftCreate(
                applicant_id="a1", dd_number="AB", bank_name="SBI",
                amount=100, dd_date="2025-06-01",
            )


# =============================================================================
# DemandDraftService.submit()
# =============================================================================

class TestDDSubmit:

    def _seat_confirmed_rows(self):
        return [{"status": "SEAT_CONFIRMED"}]

    def test_submit_creates_record(self):
        req = DemandDraftCreate(
            applicant_id=APPLICANT_ID, dd_number="DD-XYZ-001",
            bank_name="HDFC", amount=120000, dd_date="2025-06-01",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                self._seat_confirmed_rows(),  # applicant status
                [],                           # no duplicate
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.DemandDraftService.get", return_value=DemandDraftRead(**_BASE_DD_ROW)),
        ):
            result = DemandDraftService.submit(req, ORG_ID, ACTOR_ID)

        assert result.id == DD_ID
        mock_tx.assert_called_once()

    def test_submit_requires_seat_confirmed(self):
        req = DemandDraftCreate(
            applicant_id=APPLICANT_ID, dd_number="DD-001",
            bank_name="SBI", amount=100, dd_date="2025-06-01",
        )
        with patch(f"{MOD}.execute_query", return_value=[{"status": "ELIGIBLE"}]):
            with pytest.raises(BusinessRuleViolation, match="SEAT_CONFIRMED"):
                DemandDraftService.submit(req, ORG_ID, ACTOR_ID)

    def test_submit_rejects_duplicate_dd_number(self):
        req = DemandDraftCreate(
            applicant_id=APPLICANT_ID, dd_number="DD-DUPE-001",
            bank_name="SBI", amount=100, dd_date="2025-06-01",
        )
        with patch(f"{MOD}.execute_query", side_effect=[
            self._seat_confirmed_rows(),
            [{"id": "existing-dd"}],  # duplicate
        ]):
            with pytest.raises(BusinessRuleViolation, match="already been submitted"):
                DemandDraftService.submit(req, ORG_ID, ACTOR_ID)

    def test_submit_applicant_not_found_raises(self):
        req = DemandDraftCreate(
            applicant_id="ghost", dd_number="DD-001",
            bank_name="SBI", amount=100, dd_date="2025-06-01",
        )
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DemandDraftService.submit(req, ORG_ID, ACTOR_ID)


# =============================================================================
# DemandDraftService.verify()
# =============================================================================

class TestDDVerify:

    def test_verify_transitions_to_verification_pending(self):
        mock_transition = MagicMock()
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_DD_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state", mock_transition),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.DemandDraftService.get",
                  return_value=DemandDraftRead(**{**_BASE_DD_ROW, "verification_status": "VERIFIED"})),
        ):
            result = DemandDraftService.verify(DD_ID, ORG_ID, ACTOR_ID)

        assert result.verification_status == "VERIFIED"
        from server.core.state_registry import StudentState
        mock_transition.assert_called_once()
        assert mock_transition.call_args[1]["to_state"] == StudentState.VERIFICATION_PENDING

    def test_verify_non_pending_raises(self):
        verified_row = {**_BASE_DD_ROW, "verification_status": "VERIFIED"}
        with patch(f"{MOD}.execute_query", return_value=[verified_row]):
            with pytest.raises(BusinessRuleViolation, match="cannot be verified"):
                DemandDraftService.verify(DD_ID, ORG_ID, ACTOR_ID)

    def test_verify_not_found_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DemandDraftService.verify("bad-id", ORG_ID, ACTOR_ID)


# =============================================================================
# DemandDraftService.reject()
# =============================================================================

class TestDDReject:

    def test_reject_pending_dd(self):
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_DD_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.DemandDraftService.get",
                  return_value=DemandDraftRead(**{**_BASE_DD_ROW, "verification_status": "REJECTED",
                                                  "rejection_reason": "Amount mismatch"})),
        ):
            result = DemandDraftService.reject(DD_ID, ORG_ID, ACTOR_ID, "Amount mismatch on DD")

        assert result.verification_status == "REJECTED"
        sql = mock_tx.call_args[0][0][0][0]
        assert "REJECTED" in sql

    def test_reject_short_reason_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_DD_ROW]):
            with pytest.raises(BusinessRuleViolation, match="5 characters"):
                DemandDraftService.reject(DD_ID, ORG_ID, ACTOR_ID, "Bad")

    def test_reject_non_pending_raises(self):
        verified_row = {**_BASE_DD_ROW, "verification_status": "VERIFIED"}
        with patch(f"{MOD}.execute_query", return_value=[verified_row]):
            with pytest.raises(BusinessRuleViolation, match="not PENDING"):
                DemandDraftService.reject(DD_ID, ORG_ID, ACTOR_ID, "Amount mismatch on DD")


# =============================================================================
# DemandDraftService read helpers
# =============================================================================

class TestDDRead:

    def test_get_by_id(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_DD_ROW]):
            result = DemandDraftService.get(DD_ID, ORG_ID)
        assert result.dd_number == "DD-2025-001234"

    def test_get_not_found_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DemandDraftService.get("bad-id", ORG_ID)

    def test_list_for_applicant(self):
        rows = [_BASE_DD_ROW, {**_BASE_DD_ROW, "id": str(uuid4())}]
        with patch(f"{MOD}.execute_query", return_value=rows):
            results = DemandDraftService.list_for_applicant(APPLICANT_ID, ORG_ID)
        assert len(results) == 2

    def test_list_with_status_filter(self):
        with patch(f"{MOD}.execute_query", return_value=[]) as mock_q:
            DemandDraftService.list_for_applicant(APPLICANT_ID, ORG_ID, status="VERIFIED")
        params = mock_q.call_args[0][1]
        assert "VERIFIED" in params

    def test_row_to_read_coerces_decimal(self):
        row = {**_BASE_DD_ROW, "amount": Decimal("99999.99")}
        result = DemandDraftService._row_to_read(row)
        assert isinstance(result.amount, float)
        assert result.amount == pytest.approx(99999.99)


# =============================================================================
# Refund slabs
# =============================================================================

class TestRefundSlabs:

    def test_within_15_days_full_refund(self):
        label, pct = RefundRequestService._calculate_slab(10, _DEFAULT_REFUND_SLABS)
        assert pct == 100.0
        assert label == "BEFORE_15_DAYS_100PCT"

    def test_at_15_days_boundary(self):
        label, pct = RefundRequestService._calculate_slab(15, _DEFAULT_REFUND_SLABS)
        assert pct == 100.0

    def test_day_16_to_30_eighty_pct(self):
        label, pct = RefundRequestService._calculate_slab(20, _DEFAULT_REFUND_SLABS)
        assert pct == 80.0

    def test_day_31_to_45_fifty_pct(self):
        label, pct = RefundRequestService._calculate_slab(40, _DEFAULT_REFUND_SLABS)
        assert pct == 50.0

    def test_after_45_days_zero(self):
        label, pct = RefundRequestService._calculate_slab(60, _DEFAULT_REFUND_SLABS)
        assert pct == 0.0

    def test_load_slabs_falls_back_to_defaults(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            slabs = RefundRequestService._load_slabs(ORG_ID)
        assert slabs == _DEFAULT_REFUND_SLABS

    def test_load_slabs_from_policy(self):
        custom = [{"label": "ALL_100", "max_days": None, "pct": 100.0}]
        with patch(f"{MOD}.execute_query", return_value=[{"value": custom}]):
            slabs = RefundRequestService._load_slabs(ORG_ID)
        assert slabs == custom


# =============================================================================
# RefundRequestService.submit()
# =============================================================================

class TestRefundSubmit:

    def _seat_confirmed_app(self, days_ago: int = 5):
        confirmed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return [{"status": "SEAT_CONFIRMED", "status_updated_at": confirmed_at}]

    def test_submit_calculates_100_pct_within_15_days(self):
        req = RefundRequestCreate(
            applicant_id=APPLICANT_ID,
            amount_paid=120000,
            reason="I am withdrawing my admission due to personal reasons.",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                self._seat_confirmed_app(days_ago=5),  # applicant
                [],                                    # no duplicate
                [],                                    # _load_slabs — no policy row
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.RefundRequestService.get",
                  return_value=RefundRequestRead(**_BASE_REFUND_ROW)),
        ):
            result = RefundRequestService.submit(req, ORG_ID, ACTOR_ID)

        assert result.refund_amount == 120000.0  # 100% slab

        # Verify the INSERT params contain the correct refund amount
        tx_params = mock_tx.call_args[0][0][0][1]
        # refund_amount is index 5
        assert tx_params[5] == 120000.0

    def test_submit_calculates_80_pct_after_15_days(self):
        req = RefundRequestCreate(
            applicant_id=APPLICANT_ID,
            amount_paid=100000,
            reason="I am withdrawing my admission due to personal reasons.",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                self._seat_confirmed_app(days_ago=20),
                [],
                [],
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.RefundRequestService.get",
                  return_value=RefundRequestRead(**_BASE_REFUND_ROW)),
        ):
            RefundRequestService.submit(req, ORG_ID, ACTOR_ID)

        tx_params = mock_tx.call_args[0][0][0][1]
        assert tx_params[5] == 80000.0  # 80% of 100000

    def test_submit_requires_seat_confirmed_or_verification_pending(self):
        req = RefundRequestCreate(
            applicant_id=APPLICANT_ID,
            amount_paid=100000,
            reason="I am withdrawing my admission due to personal reasons.",
        )
        with patch(f"{MOD}.execute_query",
                   return_value=[{"status": "ENROLLED", "status_updated_at": _NOW}]):
            with pytest.raises(BusinessRuleViolation, match="SEAT_CONFIRMED or VERIFICATION_PENDING"):
                RefundRequestService.submit(req, ORG_ID, ACTOR_ID)

    def test_submit_blocks_duplicate_active_request(self):
        req = RefundRequestCreate(
            applicant_id=APPLICANT_ID,
            amount_paid=100000,
            reason="I am withdrawing my admission due to personal reasons.",
        )
        with patch(f"{MOD}.execute_query", side_effect=[
            self._seat_confirmed_app(),
            [{"id": "existing-refund"}],  # duplicate
        ]):
            with pytest.raises(BusinessRuleViolation, match="active refund request"):
                RefundRequestService.submit(req, ORG_ID, ACTOR_ID)

    def test_submit_applicant_not_found_raises(self):
        req = RefundRequestCreate(
            applicant_id="ghost",
            amount_paid=100,
            reason="I am withdrawing my admission due to personal reasons.",
        )
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                RefundRequestService.submit(req, ORG_ID, ACTOR_ID)


# =============================================================================
# RefundRequestService.review()
# =============================================================================

class TestRefundReview:

    def test_approve_refund_request(self):
        approved_row = {**_BASE_REFUND_ROW, "status": "APPROVED"}
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_REFUND_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.RefundRequestService.get",
                  return_value=RefundRequestRead(**approved_row)),
        ):
            result = RefundRequestService.review(
                REFUND_ID, ORG_ID, ACTOR_ID, "APPROVED", notes="All clear"
            )

        assert result.status == "APPROVED"
        tx_params = mock_tx.call_args[0][0][0][1]
        assert "APPROVED" in tx_params

    def test_reject_refund_request(self):
        rejected_row = {**_BASE_REFUND_ROW, "status": "REJECTED"}
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_REFUND_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.RefundRequestService.get",
                  return_value=RefundRequestRead(**rejected_row)),
        ):
            result = RefundRequestService.review(REFUND_ID, ORG_ID, ACTOR_ID, "REJECTED")

        assert result.status == "REJECTED"

    def test_review_invalid_decision_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_REFUND_ROW]):
            with pytest.raises(BusinessRuleViolation, match="Invalid decision"):
                RefundRequestService.review(REFUND_ID, ORG_ID, ACTOR_ID, "MAYBE")

    def test_review_already_processed_raises(self):
        processed_row = {**_BASE_REFUND_ROW, "status": "PROCESSED"}
        with patch(f"{MOD}.execute_query", return_value=[processed_row]):
            with pytest.raises(BusinessRuleViolation, match="cannot be reviewed"):
                RefundRequestService.review(REFUND_ID, ORG_ID, ACTOR_ID, "APPROVED")


# =============================================================================
# RefundRequestService.process()
# =============================================================================

class TestRefundProcess:

    def test_process_approved_refund(self):
        approved_row = {**_BASE_REFUND_ROW, "status": "APPROVED"}
        processed_row = {**_BASE_REFUND_ROW, "status": "PROCESSED",
                         "gateway_refund_id": "GW-REF-001"}
        with (
            patch(f"{MOD}.execute_query", return_value=[approved_row]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.RefundRequestService.get",
                  return_value=RefundRequestRead(**processed_row)),
        ):
            result = RefundRequestService.process(
                REFUND_ID, ORG_ID, ACTOR_ID, "GW-REF-001"
            )

        assert result.status == "PROCESSED"
        sql = mock_tx.call_args[0][0][0][0]
        assert "PROCESSED" in sql

    def test_process_empty_gateway_id_raises(self):
        approved_row = {**_BASE_REFUND_ROW, "status": "APPROVED"}
        with patch(f"{MOD}.execute_query", return_value=[approved_row]):
            with pytest.raises(BusinessRuleViolation, match="gateway_refund_id"):
                RefundRequestService.process(REFUND_ID, ORG_ID, ACTOR_ID, "")

    def test_process_non_approved_raises(self):
        requested_row = {**_BASE_REFUND_ROW, "status": "REQUESTED"}
        with patch(f"{MOD}.execute_query", return_value=[requested_row]):
            with pytest.raises(BusinessRuleViolation, match="APPROVED"):
                RefundRequestService.process(REFUND_ID, ORG_ID, ACTOR_ID, "GW-001")


# =============================================================================
# RefundRequestService read helpers
# =============================================================================

class TestRefundRead:

    def test_get_by_id(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_REFUND_ROW]):
            result = RefundRequestService.get(REFUND_ID, ORG_ID)
        assert result.id == REFUND_ID

    def test_get_not_found_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                RefundRequestService.get("bad-id", ORG_ID)

    def test_list_for_applicant(self):
        rows = [_BASE_REFUND_ROW]
        with patch(f"{MOD}.execute_query", return_value=rows):
            results = RefundRequestService.list_for_applicant(APPLICANT_ID, ORG_ID)
        assert len(results) == 1

    def test_list_pending_review(self):
        rows = [_BASE_REFUND_ROW, {**_BASE_REFUND_ROW, "id": str(uuid4()), "status": "UNDER_REVIEW"}]
        with patch(f"{MOD}.execute_query", return_value=rows):
            results = RefundRequestService.list_pending_review(ORG_ID)
        assert len(results) == 2

    def test_row_to_read_coerces_decimal(self):
        row = {**_BASE_REFUND_ROW, "amount_paid": Decimal("100000.00"), "refund_amount": Decimal("80000.00")}
        result = RefundRequestService._row_to_read(row)
        assert isinstance(result.amount_paid, float)
        assert isinstance(result.refund_amount, float)
