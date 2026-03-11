"""
P11 — Final Verification (Stage 9) Tests

Tests for:
  - FinalVerificationService: initiate, start, check_document, clear,
    clear_with_undertaking, reject, get, get_for_applicant, list_items
  - DiscrepancyService: raise_discrepancy, resolve_discrepancy,
    escalate_discrepancy, list_discrepancies
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from pydantic import ValidationError

MOD_FV = "server.admissions.final_verification"
MOD_EQ = f"{MOD_FV}.execute_query"
MOD_TX = f"{MOD_FV}.execute_transaction"
MOD_AUDIT = f"{MOD_FV}.AuditLog.log"
MOD_TRANS = f"{MOD_FV}.ApplicantService.transition_state"

ORG = "org-001"
ACTOR = "officer-001"
APPLICANT_ID = "app-001"
VER_ID = "ver-001"
ITEM_ID = "item-001"
DISC_ID = "disc-001"

NOW = datetime(2025, 3, 8, 10, 0, 0, tzinfo=timezone.utc)


def _ver_row(
    id=VER_ID,
    status="PENDING",
    applicant_id=APPLICANT_ID,
    mode="IN_PERSON",
    officer=None,
    notes=None,
    completed_at=None,
    reporting_date=None,
):
    return {
        "id": id,
        "org_id": ORG,
        "applicant_id": applicant_id,
        "verification_mode": mode,
        "reporting_date": reporting_date,
        "status": status,
        "assigned_officer": officer,
        "completed_at": completed_at,
        "notes": notes,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _item_row(
    id=ITEM_ID,
    doc_type="MARKSHEET",
    outcome="VERIFIED",
    detail=None,
    officer_notes=None,
):
    return {
        "id": id,
        "org_id": ORG,
        "verification_id": VER_ID,
        "doc_type": doc_type,
        "outcome": outcome,
        "discrepancy_detail": detail,
        "officer_notes": officer_notes,
        "checked_at": NOW,
        "checked_by": ACTOR,
    }


def _disc_row(
    id=DISC_ID,
    status="OPEN",
    severity="MEDIUM",
    disc_type="DATA_MISMATCH",
    escalated_to=None,
    resolution=None,
    resolved_at=None,
    resolved_by=None,
):
    return {
        "id": id,
        "org_id": ORG,
        "verification_id": VER_ID,
        "applicant_id": APPLICANT_ID,
        "doc_type": "MARKSHEET",
        "discrepancy_type": disc_type,
        "description": "Certificate data does not match form entry",
        "severity": severity,
        "escalated_to": escalated_to,
        "resolution": resolution,
        "resolved_at": resolved_at,
        "resolved_by": resolved_by,
        "status": status,
        "created_at": NOW,
        "updated_at": NOW,
    }


# =============================================================================
# Model Validation
# =============================================================================

class TestModels:
    def test_create_defaults(self):
        from server.admissions.final_verification import FinalVerificationCreate
        obj = FinalVerificationCreate(applicant_id="app-1")
        assert obj.verification_mode == "IN_PERSON"
        assert obj.reporting_date is None

    def test_item_outcome_min_length(self):
        from server.admissions.final_verification import VerificationItemCreate
        with pytest.raises(ValidationError):
            VerificationItemCreate(doc_type="A", outcome="VERIFIED")  # doc_type < 2 chars

    def test_discrepancy_description_min(self):
        from server.admissions.final_verification import DiscrepancyCreate
        with pytest.raises(ValidationError):
            DiscrepancyCreate(
                doc_type="CERT",
                discrepancy_type="DATA_MISMATCH",
                description="short",  # < 10 chars
                severity="LOW",
            )

    def test_discrepancy_defaults(self):
        from server.admissions.final_verification import DiscrepancyCreate
        obj = DiscrepancyCreate(
            doc_type="CERT",
            discrepancy_type="DATA_MISMATCH",
            description="Data does not match the original certificate.",
        )
        assert obj.severity == "MEDIUM"


# =============================================================================
# FinalVerificationService — initiate
# =============================================================================

class TestInitiate:
    def test_idempotent_returns_existing(self):
        from server.admissions.final_verification import (
            FinalVerificationService, FinalVerificationCreate,
        )
        existing = _ver_row(status="PENDING")
        with patch(MOD_EQ) as mock_eq, patch(MOD_AUDIT):
            # idempotency check returns existing; get() also called inside _row_to_read
            mock_eq.return_value = [existing]
            req = FinalVerificationCreate(applicant_id=APPLICANT_ID)
            result = FinalVerificationService.initiate(req, ORG, ACTOR)
        assert result.id == VER_ID
        assert result.status == "PENDING"

    def test_idempotent_rejected_allows_reinitiate(self):
        """Rejected record is bypassed — new record created."""
        from server.admissions.final_verification import (
            FinalVerificationService, FinalVerificationCreate,
        )
        rejected = _ver_row(status="REJECTED")
        new_ver = _ver_row(id="ver-002", status="PENDING")
        with (
            patch(MOD_EQ, side_effect=[[rejected], [{"status": "VERIFICATION_PENDING"}], [new_ver]]) as _,
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            req = FinalVerificationCreate(applicant_id=APPLICANT_ID)
            result = FinalVerificationService.initiate(req, ORG, ACTOR)
        assert result.status == "PENDING"

    def test_precondition_applicant_not_found(self):
        from server.admissions.final_verification import (
            FinalVerificationService, FinalVerificationCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, side_effect=[[], []]):
            req = FinalVerificationCreate(applicant_id="no-such")
            with pytest.raises(BusinessRuleViolation, match="not found"):
                FinalVerificationService.initiate(req, ORG, ACTOR)

    def test_precondition_wrong_status(self):
        from server.admissions.final_verification import (
            FinalVerificationService, FinalVerificationCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, side_effect=[[], [{"status": "OFFER_ACCEPTED"}]]):
            req = FinalVerificationCreate(applicant_id=APPLICANT_ID)
            with pytest.raises(BusinessRuleViolation, match="VERIFICATION_PENDING"):
                FinalVerificationService.initiate(req, ORG, ACTOR)

    def test_creates_record_for_verification_pending(self):
        from server.admissions.final_verification import (
            FinalVerificationService, FinalVerificationCreate,
        )
        new_ver = _ver_row(status="PENDING")
        with (
            patch(MOD_EQ, side_effect=[[], [{"status": "VERIFICATION_PENDING"}], [new_ver]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = FinalVerificationCreate(
                applicant_id=APPLICANT_ID,
                verification_mode="DIGILOCKER",
                reporting_date="2025-03-15",
            )
            result = FinalVerificationService.initiate(req, ORG, ACTOR)

        mock_tx.assert_called()
        insert_sql = mock_tx.call_args[0][0][0][0]
        assert "INSERT INTO final_verifications" in insert_sql
        assert result.id == VER_ID


# =============================================================================
# FinalVerificationService — start
# =============================================================================

class TestStart:
    def test_start_from_pending(self):
        from server.admissions.final_verification import FinalVerificationService
        ver_pending = _ver_row(status="PENDING")
        ver_in_progress = _ver_row(status="IN_PROGRESS", officer=ACTOR)
        with (
            patch(MOD_EQ, side_effect=[[ver_pending], [ver_in_progress]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.start(VER_ID, ORG, ACTOR)
        assert result.status == "IN_PROGRESS"
        sql = mock_tx.call_args[0][0][0][0]
        assert "IN_PROGRESS" in sql

    def test_start_from_discrepancy_found(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="DISCREPANCY_FOUND")
        ver_progress = _ver_row(status="IN_PROGRESS")
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_progress]]),
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.start(VER_ID, ORG, ACTOR)
        assert result.status == "IN_PROGRESS"

    def test_start_from_in_progress_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="IN_PROGRESS")]):
            with pytest.raises(BusinessRuleViolation, match="cannot be started"):
                FinalVerificationService.start(VER_ID, ORG, ACTOR)

    def test_start_assigns_officer(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="PENDING")
        ver_out = _ver_row(status="IN_PROGRESS", officer="officer-xyz")
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_out]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            FinalVerificationService.start(VER_ID, ORG, ACTOR, assigned_officer="officer-xyz")
        params = mock_tx.call_args[0][0][0][1]
        assert params[0] == "officer-xyz"

    def test_start_not_found(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                FinalVerificationService.start(VER_ID, ORG, ACTOR)


# =============================================================================
# FinalVerificationService — check_document
# =============================================================================

class TestCheckDocument:
    def test_check_verified_outcome(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        ver = _ver_row(status="IN_PROGRESS")
        item_row = _item_row(outcome="VERIFIED")
        with (
            patch(MOD_EQ, side_effect=[[ver], [item_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            item = VerificationItemCreate(doc_type="MARKSHEET", outcome="VERIFIED")
            result = FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)

        assert result.outcome == "VERIFIED"
        assert result.doc_type == "MARKSHEET"
        # Should NOT call status escalation (no extra TX call)
        assert mock_tx.call_count == 1  # only upsert, no status update

    def test_check_discrepancy_escalates_verification_status(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        ver = _ver_row(status="IN_PROGRESS")
        item_row = _item_row(outcome="DISCREPANCY")
        with (
            patch(MOD_EQ, side_effect=[[ver], [item_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            item = VerificationItemCreate(doc_type="MARKSHEET", outcome="DISCREPANCY", discrepancy_detail="DOB mismatch")
            result = FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)

        assert result.outcome == "DISCREPANCY"
        assert mock_tx.call_count == 2  # upsert + status escalation
        escalation_sql = mock_tx.call_args_list[1][0][0][0][0]
        assert "DISCREPANCY_FOUND" in escalation_sql

    def test_check_not_produced_escalates(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        ver = _ver_row(status="IN_PROGRESS")
        item_row = _item_row(outcome="NOT_PRODUCED")
        with (
            patch(MOD_EQ, side_effect=[[ver], [item_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            item = VerificationItemCreate(doc_type="CERTIFICATE", outcome="NOT_PRODUCED")
            FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)

        assert mock_tx.call_count == 2

    def test_check_invalid_outcome_raises(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="IN_PROGRESS")]):
            item = VerificationItemCreate(doc_type="MARKSHEET", outcome="PENDING")
            with pytest.raises(BusinessRuleViolation, match="Invalid outcome"):
                FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)

    def test_check_wrong_verification_status(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="PENDING")]):
            item = VerificationItemCreate(doc_type="CERT", outcome="VERIFIED")
            with pytest.raises(BusinessRuleViolation, match="Cannot check documents"):
                FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)

    def test_check_allowed_from_discrepancy_found(self):
        from server.admissions.final_verification import (
            FinalVerificationService, VerificationItemCreate,
        )
        ver = _ver_row(status="DISCREPANCY_FOUND")
        item_row = _item_row(outcome="VERIFIED")
        with (
            patch(MOD_EQ, side_effect=[[ver], [item_row]]),
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            item = VerificationItemCreate(doc_type="MARKSHEET", outcome="VERIFIED")
            result = FinalVerificationService.check_document(VER_ID, item, ORG, ACTOR)
        assert result.outcome == "VERIFIED"


# =============================================================================
# FinalVerificationService — clear
# =============================================================================

class TestClear:
    def test_clear_all_docs_ok(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="IN_PROGRESS")
        ver_cleared = _ver_row(status="VERIFIED", completed_at=NOW)
        with (
            patch(MOD_EQ, side_effect=[[ver], [{"cnt": 0}], [ver_cleared]]),
            patch(MOD_TX),
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.clear(VER_ID, ORG, ACTOR)
        assert result.status == "VERIFIED"

    def test_clear_transitions_applicant(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.state_registry import StudentState
        ver = _ver_row(status="IN_PROGRESS")
        ver_cleared = _ver_row(status="VERIFIED", completed_at=NOW)
        with (
            patch(MOD_EQ, side_effect=[[ver], [{"cnt": 0}], [ver_cleared]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            FinalVerificationService.clear(VER_ID, ORG, ACTOR)
        mock_trans.assert_called_once()
        call_kwargs = mock_trans.call_args[1]
        assert call_kwargs["to_state"] == StudentState.READY_FOR_ENROLLMENT

    def test_clear_blocks_open_discrepancies(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        ver = _ver_row(status="IN_PROGRESS")
        with patch(MOD_EQ, side_effect=[[ver], [{"cnt": 3}]]):
            with pytest.raises(BusinessRuleViolation, match="unresolved discrepancy"):
                FinalVerificationService.clear(VER_ID, ORG, ACTOR)

    def test_clear_from_pending_allowed(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="PENDING")
        ver_cleared = _ver_row(status="VERIFIED")
        with (
            patch(MOD_EQ, side_effect=[[ver], [{"cnt": 0}], [ver_cleared]]),
            patch(MOD_TX),
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.clear(VER_ID, ORG, ACTOR)
        assert result.status == "VERIFIED"

    def test_clear_from_verified_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="VERIFIED")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot clear"):
                FinalVerificationService.clear(VER_ID, ORG, ACTOR)

    def test_clear_from_rejected_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="REJECTED")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot clear"):
                FinalVerificationService.clear(VER_ID, ORG, ACTOR)


# =============================================================================
# FinalVerificationService — clear_with_undertaking
# =============================================================================

class TestClearWithUndertaking:
    def test_clear_with_undertaking_ok(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="DISCREPANCY_FOUND")
        ver_cleared = _ver_row(status="CLEARED_WITH_UNDERTAKING")
        notes = "Minor mismatch — undertaking signed by student and parent."
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_cleared]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.clear_with_undertaking(VER_ID, ORG, ACTOR, notes)
        assert result.status == "CLEARED_WITH_UNDERTAKING"
        mock_trans.assert_called_once()

    def test_undertaking_notes_too_short(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation, match="min 10 chars"):
            FinalVerificationService.clear_with_undertaking(VER_ID, ORG, ACTOR, "too short")

    def test_undertaking_notes_empty(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation):
            FinalVerificationService.clear_with_undertaking(VER_ID, ORG, ACTOR, "")

    def test_undertaking_transitions_to_ready_for_enrollment(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.state_registry import StudentState
        ver = _ver_row(status="IN_PROGRESS")
        ver_cleared = _ver_row(status="CLEARED_WITH_UNDERTAKING")
        notes = "Cleared with undertaking signed and filed."
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_cleared]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            FinalVerificationService.clear_with_undertaking(VER_ID, ORG, ACTOR, notes)
        call_kwargs = mock_trans.call_args[1]
        assert call_kwargs["to_state"] == StudentState.READY_FOR_ENROLLMENT

    def test_undertaking_from_verified_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="VERIFIED")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot clear"):
                FinalVerificationService.clear_with_undertaking(
                    VER_ID, ORG, ACTOR, "This is a valid undertaking note."
                )


# =============================================================================
# FinalVerificationService — reject
# =============================================================================

class TestReject:
    def test_reject_ok(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="DISCREPANCY_FOUND")
        ver_rejected = _ver_row(status="REJECTED")
        reason = "Suspected fraudulent certificate detected."
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_rejected]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.reject(VER_ID, ORG, ACTOR, reason)
        assert result.status == "REJECTED"
        mock_trans.assert_called_once()

    def test_reject_transitions_to_cancelled(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.state_registry import StudentState
        ver = _ver_row(status="IN_PROGRESS")
        ver_rejected = _ver_row(status="REJECTED")
        reason = "Critical document fraud identified."
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_rejected]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            FinalVerificationService.reject(VER_ID, ORG, ACTOR, reason)
        call_kwargs = mock_trans.call_args[1]
        assert call_kwargs["to_state"] == StudentState.CANCELLED

    def test_reject_reason_too_short(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation, match="min 10 chars"):
            FinalVerificationService.reject(VER_ID, ORG, ACTOR, "bad")

    def test_reject_already_verified_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="VERIFIED")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot reject"):
                FinalVerificationService.reject(VER_ID, ORG, ACTOR, "A valid rejection reason here.")

    def test_reject_already_rejected_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="REJECTED")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot reject"):
                FinalVerificationService.reject(VER_ID, ORG, ACTOR, "A valid rejection reason here.")

    def test_reject_cleared_with_undertaking_raises(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row(status="CLEARED_WITH_UNDERTAKING")]):
            with pytest.raises(BusinessRuleViolation, match="Cannot reject"):
                FinalVerificationService.reject(VER_ID, ORG, ACTOR, "A valid rejection reason here.")

    def test_reject_from_pending_ok(self):
        from server.admissions.final_verification import FinalVerificationService
        ver = _ver_row(status="PENDING")
        ver_rejected = _ver_row(status="REJECTED")
        with (
            patch(MOD_EQ, side_effect=[[ver], [ver_rejected]]),
            patch(MOD_TX),
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = FinalVerificationService.reject(
                VER_ID, ORG, ACTOR, "Document completely missing, cannot proceed."
            )
        assert result.status == "REJECTED"


# =============================================================================
# FinalVerificationService — read helpers
# =============================================================================

class TestReadHelpers:
    def test_get_not_found(self):
        from server.admissions.final_verification import FinalVerificationService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                FinalVerificationService.get("no-id", ORG)

    def test_get_returns_read(self):
        from server.admissions.final_verification import FinalVerificationService
        with patch(MOD_EQ, return_value=[_ver_row()]):
            result = FinalVerificationService.get(VER_ID, ORG)
        assert result.id == VER_ID

    def test_get_for_applicant_none_if_missing(self):
        from server.admissions.final_verification import FinalVerificationService
        with patch(MOD_EQ, return_value=[]):
            result = FinalVerificationService.get_for_applicant(APPLICANT_ID, ORG)
        assert result is None

    def test_get_for_applicant_returns_read(self):
        from server.admissions.final_verification import FinalVerificationService
        with patch(MOD_EQ, return_value=[_ver_row()]):
            result = FinalVerificationService.get_for_applicant(APPLICANT_ID, ORG)
        assert result.applicant_id == APPLICANT_ID

    def test_list_items_empty(self):
        from server.admissions.final_verification import FinalVerificationService
        with patch(MOD_EQ, return_value=[]):
            items = FinalVerificationService.list_items(VER_ID, ORG)
        assert items == []

    def test_list_items_returns_list(self):
        from server.admissions.final_verification import FinalVerificationService
        rows = [_item_row(), _item_row(id="item-002", doc_type="CERTIFICATE")]
        with patch(MOD_EQ, return_value=rows):
            items = FinalVerificationService.list_items(VER_ID, ORG)
        assert len(items) == 2
        assert items[0].doc_type == "MARKSHEET"
        assert items[1].doc_type == "CERTIFICATE"

    def test_row_to_read_date_coercion(self):
        """reporting_date as a date object is coerced to ISO string."""
        from server.admissions.final_verification import FinalVerificationService
        import datetime as dt
        row = _ver_row(reporting_date=dt.date(2025, 3, 15))
        with patch(MOD_EQ, return_value=[row]):
            result = FinalVerificationService.get(VER_ID, ORG)
        assert result.reporting_date == "2025-03-15"


# =============================================================================
# DiscrepancyService — raise_discrepancy
# =============================================================================

class TestRaiseDiscrepancy:
    def test_raise_medium_severity(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        ver_row = _ver_row(status="IN_PROGRESS")
        disc_row = _disc_row(severity="MEDIUM")
        with (
            patch(MOD_EQ, side_effect=[[ver_row], [disc_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = DiscrepancyCreate(
                doc_type="MARKSHEET",
                discrepancy_type="DATA_MISMATCH",
                description="Date of birth on certificate differs from application.",
                severity="MEDIUM",
            )
            result = DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)
        assert result.severity == "MEDIUM"
        assert result.status == "OPEN"
        # Only one TX call for MEDIUM (no status escalation)
        assert mock_tx.call_count == 1

    def test_raise_high_severity_escalates_verification(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        ver_row = _ver_row(status="IN_PROGRESS")
        disc_row = _disc_row(severity="HIGH")
        with (
            patch(MOD_EQ, side_effect=[[ver_row], [disc_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = DiscrepancyCreate(
                doc_type="DEGREE_CERT",
                discrepancy_type="SUSPECTED_FRAUD",
                description="Degree certificate appears to be a forgery.",
                severity="HIGH",
            )
            DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)
        # 2 TX calls: insert + status escalation
        assert mock_tx.call_count == 2
        escalation_sql = mock_tx.call_args_list[1][0][0][0][0]
        assert "DISCREPANCY_FOUND" in escalation_sql

    def test_raise_critical_severity_escalates(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        ver_row = _ver_row(status="IN_PROGRESS")
        disc_row = _disc_row(severity="CRITICAL")
        with (
            patch(MOD_EQ, side_effect=[[ver_row], [disc_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = DiscrepancyCreate(
                doc_type="PHOTO_ID",
                discrepancy_type="SUSPECTED_FRAUD",
                description="Photo ID appears to belong to a different individual.",
                severity="CRITICAL",
            )
            DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)
        assert mock_tx.call_count == 2

    def test_raise_low_severity_no_escalation(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        ver_row = _ver_row(status="IN_PROGRESS")
        disc_row = _disc_row(severity="LOW")
        with (
            patch(MOD_EQ, side_effect=[[ver_row], [disc_row]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = DiscrepancyCreate(
                doc_type="MARKSHEET",
                discrepancy_type="UNRECOGNIZED_BOARD",
                description="Board name not in recognized list, minor variance.",
                severity="LOW",
            )
            DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)
        assert mock_tx.call_count == 1

    def test_invalid_discrepancy_type_raises(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row()]):
            req = DiscrepancyCreate(
                doc_type="CERT",
                discrepancy_type="INVALID_TYPE",
                description="Some description long enough to pass validation.",
                severity="LOW",
            )
            with pytest.raises(BusinessRuleViolation, match="Invalid discrepancy_type"):
                DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)

    def test_invalid_severity_raises(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_ver_row()]):
            req = DiscrepancyCreate(
                doc_type="CERT",
                discrepancy_type="DATA_MISMATCH",
                description="Some description long enough to pass validation.",
                severity="EXTREME",
            )
            with pytest.raises(BusinessRuleViolation, match="Invalid severity"):
                DiscrepancyService.raise_discrepancy(VER_ID, req, ORG, ACTOR)

    def test_verification_not_found(self):
        from server.admissions.final_verification import (
            DiscrepancyService, DiscrepancyCreate,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            req = DiscrepancyCreate(
                doc_type="CERT",
                discrepancy_type="DATA_MISMATCH",
                description="Some description long enough to pass validation.",
            )
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DiscrepancyService.raise_discrepancy("no-id", req, ORG, ACTOR)


# =============================================================================
# DiscrepancyService — resolve_discrepancy
# =============================================================================

class TestResolveDiscrepancy:
    def test_resolve_ok(self):
        from server.admissions.final_verification import DiscrepancyService
        disc = _disc_row(status="OPEN")
        disc_resolved = _disc_row(status="RESOLVED", resolution="Original certificate confirmed valid.")
        with (
            patch(MOD_EQ, side_effect=[[disc], [disc_resolved]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = DiscrepancyService.resolve_discrepancy(
                DISC_ID, ORG, ACTOR, "Original certificate confirmed valid."
            )
        assert result.status == "RESOLVED"
        sql = mock_tx.call_args[0][0][0][0]
        assert "RESOLVED" in sql

    def test_resolve_under_review_ok(self):
        from server.admissions.final_verification import DiscrepancyService
        disc = _disc_row(status="UNDER_REVIEW")
        disc_resolved = _disc_row(status="RESOLVED")
        with (
            patch(MOD_EQ, side_effect=[[disc], [disc_resolved]]),
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            result = DiscrepancyService.resolve_discrepancy(
                DISC_ID, ORG, ACTOR, "Resolved after review."
            )
        assert result.status == "RESOLVED"

    def test_resolve_empty_resolution_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation, match="min 5 chars"):
            DiscrepancyService.resolve_discrepancy(DISC_ID, ORG, ACTOR, "ab")

    def test_resolve_already_resolved_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_disc_row(status="RESOLVED")]):
            with pytest.raises(BusinessRuleViolation, match="already closed"):
                DiscrepancyService.resolve_discrepancy(DISC_ID, ORG, ACTOR, "Valid resolution note.")

    def test_resolve_closed_rejected_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_disc_row(status="CLOSED_REJECTED")]):
            with pytest.raises(BusinessRuleViolation, match="already closed"):
                DiscrepancyService.resolve_discrepancy(DISC_ID, ORG, ACTOR, "Valid resolution note.")

    def test_resolve_not_found_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DiscrepancyService.resolve_discrepancy(DISC_ID, ORG, ACTOR, "Valid resolution.")


# =============================================================================
# DiscrepancyService — escalate_discrepancy
# =============================================================================

class TestEscalateDiscrepancy:
    def test_escalate_ok(self):
        from server.admissions.final_verification import DiscrepancyService
        disc = _disc_row(status="OPEN")
        disc_esc = _disc_row(status="ESCALATED", escalated_to="REGISTRAR")
        with (
            patch(MOD_EQ, side_effect=[[disc], [disc_esc]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = DiscrepancyService.escalate_discrepancy(
                DISC_ID, ORG, ACTOR, "REGISTRAR"
            )
        assert result.status == "ESCALATED"
        sql = mock_tx.call_args[0][0][0][0]
        assert "ESCALATED" in sql

    def test_escalate_empty_target_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation, match="escalate_to is required"):
            DiscrepancyService.escalate_discrepancy(DISC_ID, ORG, ACTOR, "")

    def test_escalate_whitespace_only_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with pytest.raises(BusinessRuleViolation, match="escalate_to is required"):
            DiscrepancyService.escalate_discrepancy(DISC_ID, ORG, ACTOR, "   ")

    def test_escalate_resolved_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[_disc_row(status="RESOLVED")]):
            with pytest.raises(BusinessRuleViolation, match="already closed"):
                DiscrepancyService.escalate_discrepancy(DISC_ID, ORG, ACTOR, "DEAN")

    def test_escalate_not_found_raises(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DiscrepancyService.escalate_discrepancy("no-id", ORG, ACTOR, "DEAN")


# =============================================================================
# DiscrepancyService — list_discrepancies
# =============================================================================

class TestListDiscrepancies:
    def test_list_all(self):
        from server.admissions.final_verification import DiscrepancyService
        rows = [_disc_row(), _disc_row(id="disc-002", status="RESOLVED")]
        with patch(MOD_EQ, return_value=rows):
            result = DiscrepancyService.list_discrepancies(VER_ID, ORG)
        assert len(result) == 2

    def test_list_with_status_filter(self):
        from server.admissions.final_verification import DiscrepancyService
        rows = [_disc_row(status="RESOLVED")]
        with patch(MOD_EQ, return_value=rows) as mock_eq:
            result = DiscrepancyService.list_discrepancies(VER_ID, ORG, status="RESOLVED")
        assert len(result) == 1
        # Verify status param was passed to query
        call_params = mock_eq.call_args[0][1]
        assert "RESOLVED" in call_params

    def test_list_empty(self):
        from server.admissions.final_verification import DiscrepancyService
        with patch(MOD_EQ, return_value=[]):
            result = DiscrepancyService.list_discrepancies(VER_ID, ORG)
        assert result == []

    def test_get_discrepancy_not_found(self):
        from server.admissions.final_verification import DiscrepancyService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                DiscrepancyService.get_discrepancy("no-id", ORG)
