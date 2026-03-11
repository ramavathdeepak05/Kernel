"""
P12 — Enrollment Provisioning (Stage 10) Tests

Tests for:
  - _generate_roll_number / _program_prefix helpers
  - EnrollmentProvisioningService: initiate (idempotent, pre-conditions, roll number),
    provision_lms, provision_email, provision_library, dispatch_id_card,
    sync_erp, mark_welcome_email_sent, complete (gates, student record, ENROLLED transition)
  - Read helpers: get, get_for_applicant, get_student
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, call

MOD = "server.admissions.enrollment_provisioning"
MOD_EQ = f"{MOD}.execute_query"
MOD_TX = f"{MOD}.execute_transaction"
MOD_AUDIT = f"{MOD}.AuditLog.log"
MOD_TRANS = f"{MOD}.ApplicantService.transition_state"

ORG = "org-001"
ACTOR = "staff-001"
APPLICANT_ID = "app-001"
PROV_ID = "prov-001"
STUDENT_ID = "stu-001"

NOW = datetime(2025, 3, 8, 10, 0, 0, tzinfo=timezone.utc)


def _prov_row(
    id=PROV_ID,
    applicant_id=APPLICANT_ID,
    roll_number="CS-2025-0001",
    student_id=None,
    lms_status="PENDING",
    lms_account_id=None,
    email_status="PENDING",
    university_email=None,
    library_status="PENDING",
    library_member_id=None,
    id_card_status="PENDING",
    erp_status="PENDING",
    erp_export_path=None,
    welcome_email_sent=False,
    parent_email_sent=False,
    university_reg_number=None,
):
    return {
        "id": id,
        "org_id": ORG,
        "applicant_id": applicant_id,
        "student_id": student_id,
        "roll_number": roll_number,
        "university_reg_number": university_reg_number,
        "lms_status": lms_status,
        "lms_account_id": lms_account_id,
        "lms_created_at": None,
        "email_status": email_status,
        "university_email": university_email,
        "email_created_at": None,
        "library_status": library_status,
        "library_member_id": library_member_id,
        "library_created_at": None,
        "id_card_status": id_card_status,
        "id_card_dispatched_at": None,
        "erp_status": erp_status,
        "erp_synced_at": None,
        "erp_export_path": erp_export_path,
        "welcome_email_sent": welcome_email_sent,
        "parent_email_sent": parent_email_sent,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _student_row(id=STUDENT_ID, roll_number="CS-2025-0001", program="Computer Science"):
    return {
        "id": id,
        "org_id": ORG,
        "applicant_id": APPLICANT_ID,
        "roll_number": roll_number,
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "9876543210",
        "program": program,
        "enrolled_at": NOW,
    }


# =============================================================================
# Roll Number Helpers
# =============================================================================

class TestProgramPrefix:
    def test_single_word(self):
        from server.admissions.enrollment_provisioning import _program_prefix
        assert _program_prefix("ENGINEERING") == "ENGINE"

    def test_multi_word_acronym(self):
        from server.admissions.enrollment_provisioning import _program_prefix
        assert _program_prefix("Computer Science") == "CS"

    def test_three_word(self):
        from server.admissions.enrollment_provisioning import _program_prefix
        assert _program_prefix("Master of Business Administration") == "MOBA"

    def test_empty_program(self):
        from server.admissions.enrollment_provisioning import _program_prefix
        assert _program_prefix("") == "GEN"

    def test_none_program(self):
        from server.admissions.enrollment_provisioning import _program_prefix
        assert _program_prefix(None) == "GEN"


class TestGenerateRollNumber:
    def test_first_student_sequence_1(self):
        from server.admissions.enrollment_provisioning import _generate_roll_number
        with patch(MOD_EQ, return_value=[{"cnt": 0}]):
            roll = _generate_roll_number(ORG, "Computer Science", 2025)
        assert roll == "CS-2025-0001"

    def test_tenth_student_sequence_10(self):
        from server.admissions.enrollment_provisioning import _generate_roll_number
        with patch(MOD_EQ, return_value=[{"cnt": 9}]):
            roll = _generate_roll_number(ORG, "MBA", 2025)
        assert roll == "MBA-2025-0010"

    def test_roll_format_zero_padded(self):
        from server.admissions.enrollment_provisioning import _generate_roll_number
        with patch(MOD_EQ, return_value=[{"cnt": 99}]):
            roll = _generate_roll_number(ORG, "BBA", 2025)
        assert roll == "BBA-2025-0100"

    def test_empty_query_result(self):
        from server.admissions.enrollment_provisioning import _generate_roll_number
        with patch(MOD_EQ, return_value=[]):
            roll = _generate_roll_number(ORG, "Physics", 2026)
        # Single-word programs use first 6 chars of the uppercased word
        assert roll == "PHYSIC-2026-0001"


# =============================================================================
# EnrollmentProvisioningService — initiate
# =============================================================================

class TestInitiate:
    def test_idempotent_returns_existing(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EnrollmentInitiateRequest,
        )
        existing = _prov_row()
        with patch(MOD_EQ, return_value=[existing]):
            req = EnrollmentInitiateRequest(applicant_id=APPLICANT_ID, batch_year=2025)
            result = EnrollmentProvisioningService.initiate(req, ORG, ACTOR)
        assert result.id == PROV_ID
        assert result.roll_number == "CS-2025-0001"

    def test_precondition_applicant_not_found(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EnrollmentInitiateRequest,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, side_effect=[[], []]):
            req = EnrollmentInitiateRequest(applicant_id="no-such", batch_year=2025)
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EnrollmentProvisioningService.initiate(req, ORG, ACTOR)

    def test_precondition_wrong_status(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EnrollmentInitiateRequest,
        )
        from server.core.exceptions import BusinessRuleViolation
        app = {"status": "OFFER_ACCEPTED", "name": "X", "email": "x@x.com", "phone": None, "intended_program": "CS"}
        with patch(MOD_EQ, side_effect=[[], [app]]):
            req = EnrollmentInitiateRequest(applicant_id=APPLICANT_ID, batch_year=2025)
            with pytest.raises(BusinessRuleViolation, match="READY_FOR_ENROLLMENT"):
                EnrollmentProvisioningService.initiate(req, ORG, ACTOR)

    def test_creates_record_with_roll_number(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EnrollmentInitiateRequest,
        )
        app = {"status": "READY_FOR_ENROLLMENT", "name": "A", "email": "a@b.com", "phone": None, "intended_program": "Computer Science"}
        new_prov = _prov_row(roll_number="CS-2025-0001")
        with (
            patch(MOD_EQ, side_effect=[[], [app], [{"cnt": 0}], [new_prov]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = EnrollmentInitiateRequest(applicant_id=APPLICANT_ID, batch_year=2025)
            result = EnrollmentProvisioningService.initiate(req, ORG, ACTOR)

        mock_tx.assert_called_once()
        insert_sql = mock_tx.call_args[0][0][0][0]
        assert "INSERT INTO enrollment_provisioning" in insert_sql
        assert result.roll_number == "CS-2025-0001"

    def test_batch_year_validation(self):
        from server.admissions.enrollment_provisioning import EnrollmentInitiateRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EnrollmentInitiateRequest(applicant_id="x", batch_year=1999)

    def test_university_reg_number_stored(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EnrollmentInitiateRequest,
        )
        app = {"status": "READY_FOR_ENROLLMENT", "name": "A", "email": "a@b.com", "phone": None, "intended_program": "MBA"}
        new_prov = _prov_row(university_reg_number="UNIV-2025-007")
        with (
            patch(MOD_EQ, side_effect=[[], [app], [{"cnt": 0}], [new_prov]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = EnrollmentInitiateRequest(applicant_id=APPLICANT_ID, batch_year=2025, university_reg_number="UNIV-2025-007")
            result = EnrollmentProvisioningService.initiate(req, ORG, ACTOR)

        params = mock_tx.call_args[0][0][0][1]
        assert "UNIV-2025-007" in params


# =============================================================================
# Provisioning Steps
# =============================================================================

class TestProvisionLMS:
    def test_provision_lms_done(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, LMSProvisionRequest,
        )
        prov = _prov_row()
        updated = _prov_row(lms_status="DONE", lms_account_id="LMS-123")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = LMSProvisionRequest(lms_account_id="LMS-123")
            result = EnrollmentProvisioningService.provision_lms(PROV_ID, req, ORG, ACTOR)

        assert result.lms_status == "DONE"
        assert result.lms_account_id == "LMS-123"
        sql = mock_tx.call_args[0][0][0][0]
        assert "lms_status" in sql

    def test_provision_lms_skipped(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, LMSProvisionRequest,
        )
        prov = _prov_row()
        updated = _prov_row(lms_status="SKIPPED", lms_account_id="N/A")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            req = LMSProvisionRequest(lms_account_id="N/A", status="SKIPPED")
            result = EnrollmentProvisioningService.provision_lms(PROV_ID, req, ORG, ACTOR)
        assert result.lms_status == "SKIPPED"

    def test_provision_lms_not_found(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, LMSProvisionRequest,
        )
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            req = LMSProvisionRequest(lms_account_id="X")
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EnrollmentProvisioningService.provision_lms("no-id", req, ORG, ACTOR)


class TestProvisionEmail:
    def test_provision_email_done(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, EmailProvisionRequest,
        )
        prov = _prov_row()
        updated = _prov_row(email_status="DONE", university_email="jdoe@university.edu")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = EmailProvisionRequest(university_email="jdoe@university.edu")
            result = EnrollmentProvisioningService.provision_email(PROV_ID, req, ORG, ACTOR)

        assert result.email_status == "DONE"
        assert result.university_email == "jdoe@university.edu"
        sql = mock_tx.call_args[0][0][0][0]
        assert "email_status" in sql


class TestProvisionLibrary:
    def test_provision_library_done(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, LibraryProvisionRequest,
        )
        prov = _prov_row()
        updated = _prov_row(library_status="DONE", library_member_id="LIB-789")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX),
            patch(MOD_AUDIT),
        ):
            req = LibraryProvisionRequest(library_member_id="LIB-789")
            result = EnrollmentProvisioningService.provision_library(PROV_ID, req, ORG, ACTOR)
        assert result.library_status == "DONE"
        assert result.library_member_id == "LIB-789"


class TestDispatchIDCard:
    def test_dispatch_id_card(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = _prov_row()
        updated = _prov_row(id_card_status="DONE")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.dispatch_id_card(PROV_ID, ORG, ACTOR)

        assert result.id_card_status == "DONE"
        sql = mock_tx.call_args[0][0][0][0]
        assert "id_card_status" in sql
        assert "DONE" in sql


class TestSyncERP:
    def test_sync_erp_synced(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, ERPSyncRequest,
        )
        prov = _prov_row()
        updated = _prov_row(erp_status="SYNCED")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = ERPSyncRequest(status="SYNCED")
            result = EnrollmentProvisioningService.sync_erp(PROV_ID, req, ORG, ACTOR)

        assert result.erp_status == "SYNCED"
        sql = mock_tx.call_args[0][0][0][0]
        assert "erp_status" in sql

    def test_sync_erp_export_ready_with_path(self):
        from server.admissions.enrollment_provisioning import (
            EnrollmentProvisioningService, ERPSyncRequest,
        )
        prov = _prov_row()
        updated = _prov_row(erp_status="EXPORT_READY", erp_export_path="/exports/2025/batch1.csv")
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            req = ERPSyncRequest(status="EXPORT_READY", erp_export_path="/exports/2025/batch1.csv")
            result = EnrollmentProvisioningService.sync_erp(PROV_ID, req, ORG, ACTOR)

        assert result.erp_export_path == "/exports/2025/batch1.csv"
        params = mock_tx.call_args[0][0][0][1]
        assert "/exports/2025/batch1.csv" in params


class TestWelcomeEmail:
    def test_mark_student_welcome_email(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = _prov_row()
        updated = _prov_row(welcome_email_sent=True)
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.mark_welcome_email_sent(PROV_ID, ORG, ACTOR, parent=False)

        assert result.welcome_email_sent is True
        sql = mock_tx.call_args[0][0][0][0]
        assert "welcome_email_sent" in sql

    def test_mark_parent_email(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = _prov_row()
        updated = _prov_row(parent_email_sent=True)
        with (
            patch(MOD_EQ, side_effect=[[prov], [updated]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.mark_welcome_email_sent(PROV_ID, ORG, ACTOR, parent=True)

        assert result.parent_email_sent is True
        sql = mock_tx.call_args[0][0][0][0]
        assert "parent_email_sent" in sql


# =============================================================================
# EnrollmentProvisioningService — complete
# =============================================================================

class TestComplete:
    def _ready_prov(self):
        return _prov_row(
            lms_status="DONE", lms_account_id="LMS-1",
            email_status="DONE", university_email="j@uni.edu",
        )

    def _app(self):
        return {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "9876543210",
            "intended_program": "Computer Science",
        }

    def test_complete_creates_student(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = self._ready_prov()
        student = _student_row()
        with (
            patch(MOD_EQ, side_effect=[[prov], [self._app()], [student]]),
            patch(MOD_TX) as mock_tx,
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)

        assert result.id == STUDENT_ID
        assert result.roll_number == "CS-2025-0001"
        assert mock_tx.call_count == 1
        # Two statements in one transaction: INSERT students + UPDATE provisioning
        stmts = mock_tx.call_args[0][0]
        assert len(stmts) == 2
        assert "INSERT INTO students" in stmts[0][0]
        assert "UPDATE enrollment_provisioning" in stmts[1][0]

    def test_complete_transitions_to_enrolled(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.state_registry import StudentState
        prov = self._ready_prov()
        student = _student_row()
        with (
            patch(MOD_EQ, side_effect=[[prov], [self._app()], [student]]),
            patch(MOD_TX),
            patch(MOD_TRANS) as mock_trans,
            patch(MOD_AUDIT),
        ):
            EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)

        mock_trans.assert_called_once()
        call_kwargs = mock_trans.call_args[1]
        assert call_kwargs["to_state"] == StudentState.ENROLLED
        assert call_kwargs["applicant_id"] == APPLICANT_ID

    def test_complete_blocks_if_lms_pending(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        prov = _prov_row(lms_status="PENDING", email_status="DONE")
        with patch(MOD_EQ, return_value=[prov]):
            with pytest.raises(BusinessRuleViolation, match="LMS"):
                EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)

    def test_complete_blocks_if_email_pending(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        prov = _prov_row(lms_status="DONE", email_status="PENDING")
        with patch(MOD_EQ, return_value=[prov]):
            with pytest.raises(BusinessRuleViolation, match="Email"):
                EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)

    def test_complete_blocks_if_no_roll_number(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        prov = _prov_row(lms_status="DONE", email_status="DONE", roll_number=None)
        with patch(MOD_EQ, return_value=[prov]):
            with pytest.raises(BusinessRuleViolation, match="roll number"):
                EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)

    def test_complete_lms_skipped_allowed(self):
        """SKIPPED counts as done for mandatory gate check."""
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = _prov_row(lms_status="SKIPPED", email_status="DONE")
        student = _student_row()
        with (
            patch(MOD_EQ, side_effect=[[prov], [self._app()], [student]]),
            patch(MOD_TX),
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)
        assert result.id == STUDENT_ID

    def test_complete_email_skipped_allowed(self):
        """SKIPPED counts as done for mandatory gate check."""
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        prov = _prov_row(lms_status="DONE", email_status="SKIPPED")
        student = _student_row()
        with (
            patch(MOD_EQ, side_effect=[[prov], [self._app()], [student]]),
            patch(MOD_TX),
            patch(MOD_TRANS),
            patch(MOD_AUDIT),
        ):
            result = EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)
        assert result.id == STUDENT_ID

    def test_complete_applicant_not_found_raises(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        prov = _prov_row(lms_status="DONE", email_status="DONE")
        with patch(MOD_EQ, side_effect=[[prov], []]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EnrollmentProvisioningService.complete(PROV_ID, ORG, ACTOR)


# =============================================================================
# Read Helpers
# =============================================================================

class TestReadHelpers:
    def test_get_not_found(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EnrollmentProvisioningService.get("no-id", ORG)

    def test_get_returns_read(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        with patch(MOD_EQ, return_value=[_prov_row()]):
            result = EnrollmentProvisioningService.get(PROV_ID, ORG)
        assert result.id == PROV_ID
        assert result.lms_status == "PENDING"

    def test_get_for_applicant_none_if_missing(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        with patch(MOD_EQ, return_value=[]):
            result = EnrollmentProvisioningService.get_for_applicant(APPLICANT_ID, ORG)
        assert result is None

    def test_get_for_applicant_returns_read(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        with patch(MOD_EQ, return_value=[_prov_row()]):
            result = EnrollmentProvisioningService.get_for_applicant(APPLICANT_ID, ORG)
        assert result.applicant_id == APPLICANT_ID

    def test_get_student_not_found(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        from server.core.exceptions import BusinessRuleViolation
        with patch(MOD_EQ, return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EnrollmentProvisioningService.get_student("no-id", ORG)

    def test_get_student_returns_read(self):
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService
        with patch(MOD_EQ, return_value=[_student_row()]):
            result = EnrollmentProvisioningService.get_student(STUDENT_ID, ORG)
        assert result.id == STUDENT_ID
        assert result.roll_number == "CS-2025-0001"
        assert result.program == "Computer Science"
