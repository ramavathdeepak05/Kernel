"""
Tests for P9 — Offer Letter v2 (Stage 7)

Covers:
  - OfferLetterGenerateRequest / OfferLetterRead model validation (new fields)
  - generate(): idempotency, pre-condition (ELIGIBLE/MERIT_LISTED), state transition
  - accept(): PENDING → ACCEPTED + OFFER_ACCEPTED → SEAT_CONFIRMED, expired rejection
  - decline(): PENDING → DECLINED + OFFER_DECLINED + OfferDeclined event
  - revoke(): staff revokes PENDING offer → CANCELLED; blocks ACCEPTED offer
  - mark_delivery(): SENT / OPENED / BOUNCED
  - mark_reminder(): T3 / T1
  - expire_overdue(): batch expiry of overdue PENDING offers
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from server.admissions.models import (
    OfferLetterGenerateRequest,
    OfferLetterRead,
    OfferAcceptRequest,
    OfferDeclineRequest,
    OfferRevokeRequest,
)
from server.admissions.offer_letter import OfferLetterService
from server.core.exceptions import BusinessRuleViolation, GlobalLockViolationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_ID = "org-p9"
ACTOR_ID = "staff-001"
APPLICANT_ID = str(uuid4())
LETTER_ID = str(uuid4())
ML_ENTRY_ID = str(uuid4())

MOD = "server.admissions.offer_letter"

_NOW = datetime.now(timezone.utc)
_EXPIRES = _NOW + timedelta(days=7)

_BASE_LETTER_ROW = {
    "id": LETTER_ID,
    "org_id": ORG_ID,
    "applicant_id": APPLICANT_ID,
    "program_name": "B.Tech Computer Science",
    "academic_year": "2025-2026",
    "template_version": 1,
    "content_hash": "abc123",
    "pdf_path": "/offers/letter.pdf",
    "issued_at": _NOW,
    "is_valid": True,
    "expires_at": _EXPIRES,
    "accepted_at": None,
    "declined_at": None,
    "acceptance_status": "PENDING",
    "digital_signature_ref": None,
    "merit_list_entry_id": ML_ENTRY_ID,
    "delivery_status": "PENDING",
    "email_opened_at": None,
    "t3_reminder_sent": False,
    "t1_reminder_sent": False,
    "fee_structure": {"tuition": 120000, "hostel": 60000},
}


def _make_generate_req(**kwargs) -> OfferLetterGenerateRequest:
    defaults = dict(
        applicant_id=APPLICANT_ID,
        program_name="B.Tech Computer Science",
        academic_year="2025-2026",
        template_version=1,
        acceptance_deadline_days=7,
        fee_structure={"tuition": 120000},
        conditions=["Subject to medical fitness"],
    )
    defaults.update(kwargs)
    return OfferLetterGenerateRequest(**defaults)


# =============================================================================
# Model validation
# =============================================================================

class TestOfferLetterModels:
    def test_generate_request_defaults(self):
        req = OfferLetterGenerateRequest(
            applicant_id="a1",
            program_name="MBA",
            academic_year="2025-2026",
        )
        assert req.acceptance_deadline_days == 7
        assert req.fee_structure == {}
        assert req.conditions == []
        assert req.merit_list_entry_id is None

    def test_generate_request_invalid_year(self):
        with pytest.raises(Exception):
            OfferLetterGenerateRequest(
                applicant_id="a1",
                program_name="MBA",
                academic_year="2025",  # must be YYYY-YYYY
            )

    def test_generate_request_deadline_bounds(self):
        with pytest.raises(Exception):
            OfferLetterGenerateRequest(
                applicant_id="a1",
                program_name="MBA",
                academic_year="2025-2026",
                acceptance_deadline_days=0,
            )
        with pytest.raises(Exception):
            OfferLetterGenerateRequest(
                applicant_id="a1",
                program_name="MBA",
                academic_year="2025-2026",
                acceptance_deadline_days=61,
            )

    def test_offer_letter_read_defaults(self):
        row = dict(_BASE_LETTER_ROW)
        read = OfferLetterRead(**row)
        assert read.acceptance_status == "PENDING"
        assert read.delivery_status == "PENDING"
        assert read.t3_reminder_sent is False

    def test_revoke_request_requires_reason(self):
        with pytest.raises(Exception):
            OfferRevokeRequest(reason="short")  # min_length=10


# =============================================================================
# Generate
# =============================================================================

class TestOfferLetterGenerate:

    def _eligible_applicant(self):
        return [{"name": "Priya", "email": "priya@test.com", "status": "ELIGIBLE"}]

    def test_generate_idempotent_returns_existing(self):
        """If a valid offer already exists, return it without re-generating."""
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
        ):
            result = OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

        assert result.id == LETTER_ID

    def test_generate_creates_new_offer(self):
        updated_mock = MagicMock()
        updated_mock.status = "OFFER_ISSUED"
        file_mock = MagicMock()
        file_mock.get_version.return_value = None

        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [],                             # no existing offer
                self._eligible_applicant(),     # applicant lookup
            ]),
            patch(f"{MOD}.DocumentVerificationService.all_required_docs_verified",
                  return_value=True),
            patch(f"{MOD}.OfferLetterService._render_pdf", return_value=b"%PDF-test"),
            patch(f"{MOD}.FileStorageService") as mock_fs_cls,
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state", return_value=updated_mock),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._notify_offer_issued"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**_BASE_LETTER_ROW)),
        ):
            mock_fs_cls.return_value.upload_file.return_value = file_mock
            result = OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

        assert result.id == LETTER_ID

    def test_generate_requires_eligible_status(self):
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [],  # no existing offer
                [{"name": "A", "email": "a@b.com", "status": "SUBMITTED"}],
            ]),
        ):
            with pytest.raises(BusinessRuleViolation, match="ELIGIBLE or MERIT_LISTED"):
                OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

    def test_generate_accepts_merit_listed_status(self):
        """MERIT_LISTED should also be allowed as a pre-condition."""
        updated_mock = MagicMock()
        updated_mock.status = "OFFER_ISSUED"
        file_mock = MagicMock()
        file_mock.get_version.return_value = None

        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [],
                [{"name": "B", "email": "b@test.com", "status": "MERIT_LISTED"}],
            ]),
            patch(f"{MOD}.DocumentVerificationService.all_required_docs_verified",
                  return_value=True),
            patch(f"{MOD}.OfferLetterService._render_pdf", return_value=b"%PDF-test"),
            patch(f"{MOD}.FileStorageService") as mock_fs_cls,
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state", return_value=updated_mock),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._notify_offer_issued"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**_BASE_LETTER_ROW)),
        ):
            mock_fs_cls.return_value.upload_file.return_value = file_mock
            result = OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

        assert result is not None

    def test_generate_blocks_when_docs_not_verified(self):
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [],
                self._eligible_applicant(),
            ]),
            patch(f"{MOD}.DocumentVerificationService.all_required_docs_verified",
                  return_value=False),
        ):
            with pytest.raises(GlobalLockViolationError):
                OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

    def test_generate_applicant_not_found(self):
        with patch(f"{MOD}.execute_query", side_effect=[[], []]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                OfferLetterService.generate(_make_generate_req(), ORG_ID, ACTOR_ID)

    def test_generate_sets_expires_at_from_deadline_days(self):
        """The INSERT must include expires_at = now + deadline_days."""
        updated_mock = MagicMock()
        updated_mock.status = "OFFER_ISSUED"
        file_mock = MagicMock()
        file_mock.get_version.return_value = None

        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [],
                self._eligible_applicant(),
            ]),
            patch(f"{MOD}.DocumentVerificationService.all_required_docs_verified",
                  return_value=True),
            patch(f"{MOD}.OfferLetterService._render_pdf", return_value=b"%PDF"),
            patch(f"{MOD}.FileStorageService") as mock_fs_cls,
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.ApplicantService.transition_state", return_value=updated_mock),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._notify_offer_issued"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**_BASE_LETTER_ROW)),
        ):
            mock_fs_cls.return_value.upload_file.return_value = file_mock
            OfferLetterService.generate(
                _make_generate_req(acceptance_deadline_days=14), ORG_ID, ACTOR_ID
            )

        # The INSERT params tuple must include expires_at (14 days out)
        tx_params = mock_tx.call_args[0][0][0][1]
        # expires_at is the 11th positional param (index 10)
        expires_at_val = tx_params[10]
        assert isinstance(expires_at_val, datetime)
        delta = expires_at_val - datetime.now(timezone.utc)
        assert 13 <= delta.days <= 14


# =============================================================================
# Accept
# =============================================================================

class TestOfferLetterAccept:

    def test_accept_pending_offer(self):
        accept_req = OfferAcceptRequest(
            applicant_id=APPLICANT_ID,
            digital_signature_ref="sig-ref-001",
        )
        accepted_row = {**_BASE_LETTER_ROW, "acceptance_status": "ACCEPTED", "accepted_at": _NOW}

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**accepted_row)),
        ):
            result = OfferLetterService.accept(LETTER_ID, accept_req, ORG_ID, ACTOR_ID)

        assert result.acceptance_status == "ACCEPTED"

    def test_accept_transitions_to_seat_confirmed(self):
        accept_req = OfferAcceptRequest(applicant_id=APPLICANT_ID)
        mock_transition = MagicMock()

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state", mock_transition),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService.get",
                  return_value=OfferLetterRead(**{**_BASE_LETTER_ROW, "acceptance_status": "ACCEPTED"})),
        ):
            OfferLetterService.accept(LETTER_ID, accept_req, ORG_ID, ACTOR_ID)

        # Two transitions: OFFER_ACCEPTED then SEAT_CONFIRMED
        assert mock_transition.call_count == 2
        states = [c[1]["to_state"] for c in mock_transition.call_args_list]
        from server.core.state_registry import StudentState
        assert StudentState.OFFER_ACCEPTED in states
        assert StudentState.SEAT_CONFIRMED in states

    def test_accept_updates_merit_list_entry(self):
        accept_req = OfferAcceptRequest(applicant_id=APPLICANT_ID)

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService.get",
                  return_value=OfferLetterRead(**{**_BASE_LETTER_ROW, "acceptance_status": "ACCEPTED"})),
        ):
            OfferLetterService.accept(LETTER_ID, accept_req, ORG_ID, ACTOR_ID)

        # Second execute_transaction call should update merit_list_entries
        all_sqls = [call[0][0][0][0] for call in mock_tx.call_args_list]
        assert any("merit_list_entries" in sql for sql in all_sqls)

    def test_accept_already_accepted_raises(self):
        already_accepted = {**_BASE_LETTER_ROW, "acceptance_status": "ACCEPTED"}
        with patch(f"{MOD}.execute_query", return_value=[already_accepted]):
            with pytest.raises(BusinessRuleViolation, match="cannot be accepted"):
                OfferLetterService.accept(
                    LETTER_ID, OfferAcceptRequest(applicant_id=APPLICANT_ID), ORG_ID, ACTOR_ID
                )

    def test_accept_expired_offer_raises(self):
        expired_row = {
            **_BASE_LETTER_ROW,
            "acceptance_status": "PENDING",
            "expires_at": _NOW - timedelta(days=1),  # already past
        }
        with (
            patch(f"{MOD}.execute_query", return_value=[expired_row]),
            patch(f"{MOD}.OfferLetterService._do_expire"),
        ):
            with pytest.raises(BusinessRuleViolation, match="expired"):
                OfferLetterService.accept(
                    LETTER_ID, OfferAcceptRequest(applicant_id=APPLICANT_ID), ORG_ID, ACTOR_ID
                )

    def test_accept_letter_not_found_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                OfferLetterService.accept(
                    "bad-id", OfferAcceptRequest(applicant_id=APPLICANT_ID), ORG_ID, ACTOR_ID
                )


# =============================================================================
# Decline
# =============================================================================

class TestOfferLetterDecline:

    def test_decline_pending_offer(self):
        decline_req = OfferDeclineRequest(applicant_id=APPLICANT_ID, reason="Prefer another college")
        declined_row = {**_BASE_LETTER_ROW, "acceptance_status": "DECLINED", "declined_at": _NOW}

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._publish_decline_event"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**declined_row)),
        ):
            result = OfferLetterService.decline(LETTER_ID, decline_req, ORG_ID, ACTOR_ID)

        assert result.acceptance_status == "DECLINED"

    def test_decline_publishes_offer_declined_event(self):
        decline_req = OfferDeclineRequest(applicant_id=APPLICANT_ID)

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._publish_decline_event") as mock_event,
            patch(f"{MOD}.OfferLetterService.get",
                  return_value=OfferLetterRead(**{**_BASE_LETTER_ROW, "acceptance_status": "DECLINED"})),
        ):
            OfferLetterService.decline(LETTER_ID, decline_req, ORG_ID, ACTOR_ID)

        mock_event.assert_called_once()
        call_kwargs = mock_event.call_args[1]
        assert call_kwargs["merit_list_entry_id"] == ML_ENTRY_ID

    def test_decline_already_declined_raises(self):
        declined_row = {**_BASE_LETTER_ROW, "acceptance_status": "DECLINED"}
        with patch(f"{MOD}.execute_query", return_value=[declined_row]):
            with pytest.raises(BusinessRuleViolation, match="cannot be declined"):
                OfferLetterService.decline(
                    LETTER_ID, OfferDeclineRequest(applicant_id=APPLICANT_ID), ORG_ID, ACTOR_ID
                )

    def test_decline_updates_merit_list_entry(self):
        decline_req = OfferDeclineRequest(applicant_id=APPLICANT_ID)

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService._publish_decline_event"),
            patch(f"{MOD}.OfferLetterService.get",
                  return_value=OfferLetterRead(**{**_BASE_LETTER_ROW, "acceptance_status": "DECLINED"})),
        ):
            OfferLetterService.decline(LETTER_ID, decline_req, ORG_ID, ACTOR_ID)

        all_sqls = [call[0][0][0][0] for call in mock_tx.call_args_list]
        assert any("merit_list_entries" in sql for sql in all_sqls)


# =============================================================================
# Revoke
# =============================================================================

class TestOfferLetterRevoke:

    def test_revoke_pending_offer(self):
        revoke_req = OfferRevokeRequest(reason="Seat cancelled due to document fraud")
        revoked_row = {**_BASE_LETTER_ROW, "is_valid": False, "acceptance_status": "EXPIRED"}

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state"),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**revoked_row)),
        ):
            result = OfferLetterService.revoke(LETTER_ID, revoke_req, ORG_ID, ACTOR_ID)

        assert result.is_valid is False
        assert result.acceptance_status == "EXPIRED"

    def test_revoke_transitions_applicant_to_cancelled(self):
        revoke_req = OfferRevokeRequest(reason="Seat cancelled due to document fraud")
        mock_transition = MagicMock()

        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.ApplicantService.transition_state", mock_transition),
            patch(f"{MOD}.AuditLog.log"),
            patch(f"{MOD}.OfferLetterService.get",
                  return_value=OfferLetterRead(**{**_BASE_LETTER_ROW, "is_valid": False})),
        ):
            OfferLetterService.revoke(LETTER_ID, revoke_req, ORG_ID, ACTOR_ID)

        from server.core.state_registry import StudentState
        mock_transition.assert_called_once()
        assert mock_transition.call_args[1]["to_state"] == StudentState.CANCELLED

    def test_revoke_accepted_offer_raises(self):
        """Accepted offers cannot be revoked through normal path."""
        accepted_row = {**_BASE_LETTER_ROW, "acceptance_status": "ACCEPTED"}
        revoke_req = OfferRevokeRequest(reason="Seat cancelled due to document fraud")

        with patch(f"{MOD}.execute_query", return_value=[accepted_row]):
            with pytest.raises(BusinessRuleViolation, match="ACCEPTED"):
                OfferLetterService.revoke(LETTER_ID, revoke_req, ORG_ID, ACTOR_ID)


# =============================================================================
# Delivery tracking
# =============================================================================

class TestOfferLetterDelivery:

    def test_mark_delivery_sent(self):
        sent_row = {**_BASE_LETTER_ROW, "delivery_status": "SENT"}
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**sent_row)),
        ):
            result = OfferLetterService.mark_delivery(LETTER_ID, ORG_ID, "SENT", ACTOR_ID)
        assert result.delivery_status == "SENT"

    def test_mark_delivery_opened_sets_email_opened_at(self):
        opened_row = {**_BASE_LETTER_ROW, "delivery_status": "OPENED", "email_opened_at": _NOW}
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.OfferLetterService.get", return_value=OfferLetterRead(**opened_row)),
        ):
            OfferLetterService.mark_delivery(LETTER_ID, ORG_ID, "OPENED", ACTOR_ID)

        sql = mock_tx.call_args[0][0][0][0]
        assert "email_opened_at" in sql

    def test_mark_delivery_invalid_status_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]):
            with pytest.raises(BusinessRuleViolation, match="Invalid delivery status"):
                OfferLetterService.mark_delivery(LETTER_ID, ORG_ID, "UNKNOWN", ACTOR_ID)

    def test_mark_reminder_t3(self):
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
        ):
            OfferLetterService.mark_reminder(LETTER_ID, ORG_ID, "T3", ACTOR_ID)

        sql = mock_tx.call_args[0][0][0][0]
        assert "t3_reminder_sent" in sql

    def test_mark_reminder_t1(self):
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
        ):
            OfferLetterService.mark_reminder(LETTER_ID, ORG_ID, "T1", ACTOR_ID)

        sql = mock_tx.call_args[0][0][0][0]
        assert "t1_reminder_sent" in sql

    def test_mark_reminder_invalid_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]):
            with pytest.raises(BusinessRuleViolation, match="T3.*T1"):
                OfferLetterService.mark_reminder(LETTER_ID, ORG_ID, "T7", ACTOR_ID)


# =============================================================================
# Expire overdue
# =============================================================================

class TestExpireOverdue:

    def test_expire_overdue_expires_all(self):
        letter2 = str(uuid4())
        overdue_rows = [
            {"id": LETTER_ID, "applicant_id": APPLICANT_ID},
            {"id": letter2, "applicant_id": str(uuid4())},
        ]
        with (
            patch(f"{MOD}.execute_query", return_value=overdue_rows),
            patch(f"{MOD}.OfferLetterService._do_expire") as mock_expire,
        ):
            result = OfferLetterService.expire_overdue(ORG_ID, ACTOR_ID)

        assert result["expired_count"] == 2
        assert LETTER_ID in result["letter_ids"]
        assert mock_expire.call_count == 2

    def test_expire_overdue_skips_on_error(self):
        """A single failure should not stop the batch — others still expire."""
        overdue_rows = [
            {"id": LETTER_ID, "applicant_id": APPLICANT_ID},
            {"id": str(uuid4()), "applicant_id": str(uuid4())},
        ]

        call_count = {"n": 0}

        def failing_expire(lid, aid, oid, actor):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("DB timeout")

        with (
            patch(f"{MOD}.execute_query", return_value=overdue_rows),
            patch(f"{MOD}.OfferLetterService._do_expire", side_effect=failing_expire),
        ):
            result = OfferLetterService.expire_overdue(ORG_ID, ACTOR_ID)

        # Only the second one succeeds
        assert result["expired_count"] == 1

    def test_expire_overdue_empty(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            result = OfferLetterService.expire_overdue(ORG_ID, ACTOR_ID)
        assert result["expired_count"] == 0
        assert result["letter_ids"] == []


# =============================================================================
# Get helpers
# =============================================================================

class TestOfferLetterGet:

    def test_get_by_id(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]):
            result = OfferLetterService.get(LETTER_ID, ORG_ID)
        assert result.id == LETTER_ID

    def test_get_by_id_not_found_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                OfferLetterService.get("bad-id", ORG_ID)

    def test_get_for_applicant_returns_letter(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LETTER_ROW]):
            result = OfferLetterService.get_for_applicant(APPLICANT_ID, ORG_ID)
        assert result is not None
        assert result.applicant_id == APPLICANT_ID

    def test_get_for_applicant_none_when_missing(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            result = OfferLetterService.get_for_applicant(APPLICANT_ID, ORG_ID)
        assert result is None

    def test_row_to_read_parses_jsonb_fee_structure(self):
        row = {**_BASE_LETTER_ROW, "fee_structure": json.dumps({"tuition": 120000})}
        result = OfferLetterService._row_to_read(row)
        assert isinstance(result.fee_structure, dict)
        assert result.fee_structure["tuition"] == 120000
