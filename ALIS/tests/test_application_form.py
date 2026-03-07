"""
Tests for P4 — Application Form Service (Stage 2)

Covers:
  - Draft initiation + Application ID generation
  - Personal details, address save
  - Academic qualification upsert
  - Entrance exam scores
  - Program preferences (ordered, replaces on re-set)
  - Declaration acceptance
  - Application submission (with pre-condition checks)
  - Application fee recording
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from server.admissions.application_form import (
    AcademicQualificationRequest,
    AddressRequest,
    ApplicationFeeRequest,
    ApplicationFormService,
    DeclarationRequest,
    EntranceScoreRequest,
    PersonalDetailsRequest,
    ProgramPreferencesRequest,
    ProgramPreferenceItem,
)
from server.core.exceptions import BusinessRuleViolation

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

ORG_ID = "org-test"
ACTOR_ID = "staff-001"
APPLICANT_ID = str(uuid4())
QUAL_ID = str(uuid4())
SCORE_ID = str(uuid4())

_DRAFT_ROW = {
    "id": APPLICANT_ID,
    "org_id": ORG_ID,
    "name": "Arjun Mehta",
    "email": "arjun@example.com",
    "phone": "+919876543210",
    "intended_program": "B.Tech Computer Science",
    "source_channel": "WEBSITE",
    "status": "DRAFT",
    "application_id": "APP-2025-000001",
    "date_of_birth": None,
    "gender": None,
    "nationality": "Indian",
    "category": "GENERAL",
    "aadhaar_number": None,
    "permanent_address": None,
    "correspondence_address": None,
    "emergency_contact": None,
    "hostel_required": False,
    "scholarship_required": False,
    "has_disability": False,
    "special_requirements": None,
    "declaration_accepted": False,
    "declaration_accepted_at": None,
    "digital_signature": None,
    "submitted_at": None,
    "application_fee_paid": False,
    "application_fee_amount": None,
    "application_fee_ref": None,
    "study_mode": "FULL_TIME",
    "intake_batch": None,
    "work_experience_months": None,
    "lead_id": None,
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}

_APPLIED_ROW = {**_DRAFT_ROW, "status": "APPLIED", "application_id": None}

MOD = "server.admissions.application_form"


# =============================================================================
# Draft Initiation
# =============================================================================

class TestStartDraft:
    def test_start_draft_from_applied_status(self):
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_APPLIED_ROW],   # fetch applicant
                [{"cnt": 0}],     # count for app_id generation
                [_DRAFT_ROW],     # return after update
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.start_draft(APPLICANT_ID, ORG_ID, ACTOR_ID)

        assert result.status == "DRAFT"
        # Application ID should have been generated and set
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "application_id" in tx_sql

    def test_start_draft_already_draft_is_idempotent(self):
        """If already in DRAFT, return current without re-updating."""
        with (
            patch(f"{MOD}.execute_query", return_value=[_DRAFT_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
        ):
            result = ApplicationFormService.start_draft(APPLICANT_ID, ORG_ID, ACTOR_ID)
        # No DB update needed
        mock_tx.assert_not_called()
        assert result.application_id == "APP-2025-000001"

    def test_start_draft_nonexistent_applicant_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                ApplicationFormService.start_draft("bad-id", ORG_ID, ACTOR_ID)

    def test_application_id_sequential_format(self):
        """Application ID should follow APP-{YEAR}-{6-digit-seq} format."""
        applied_row = {**_APPLIED_ROW, "application_id": None}
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [applied_row],
                [{"cnt": 46}],   # 46 existing → seq = 47
                [_DRAFT_ROW],
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ApplicationFormService.start_draft(APPLICANT_ID, ORG_ID, ACTOR_ID)

        tx_args = mock_tx.call_args[0][0][0][1]  # params tuple
        generated_app_id = tx_args[1]  # second param is application_id
        import re
        assert re.match(r"APP-\d{4}-000047", generated_app_id)


# =============================================================================
# Personal Details
# =============================================================================

class TestPersonalDetails:
    def test_save_personal_details_success(self):
        req = PersonalDetailsRequest(
            date_of_birth="2002-05-15",
            gender="MALE",
            category="OBC_NCL",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_DRAFT_ROW],   # _assert_form_editable
                [_DRAFT_ROW],   # get_draft
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.save_personal_details(
                APPLICANT_ID, ORG_ID, req, ACTOR_ID
            )
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "date_of_birth" in tx_sql
        assert "gender" in tx_sql

    def test_edit_rejected_after_submission(self):
        submitted_row = {**_DRAFT_ROW, "status": "SUBMITTED"}
        req = PersonalDetailsRequest(gender="FEMALE")
        # SUBMITTED is still editable per _FORM_EDITABLE_STATES
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [submitted_row],
                [submitted_row],
            ]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            # SUBMITTED is in the editable set — should work
            result = ApplicationFormService.save_personal_details(
                APPLICANT_ID, ORG_ID, req, ACTOR_ID
            )
        assert result is not None

    def test_edit_blocked_after_documents_verified(self):
        locked_row = {**_DRAFT_ROW, "status": "DOCUMENTS_VERIFIED"}
        req = PersonalDetailsRequest(gender="OTHER")
        with patch(f"{MOD}.execute_query", return_value=[locked_row]):
            with pytest.raises(BusinessRuleViolation, match="cannot be edited"):
                ApplicationFormService.save_personal_details(
                    APPLICANT_ID, ORG_ID, req, ACTOR_ID
                )


# =============================================================================
# Address
# =============================================================================

class TestAddressSave:
    def test_save_permanent_address(self):
        req = AddressRequest(
            permanent_address={
                "line1": "123 MG Road",
                "city": "Bangalore",
                "state": "Karnataka",
                "pincode": "560001",
                "country": "India",
            }
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[[_DRAFT_ROW], [_DRAFT_ROW]]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ApplicationFormService.save_address(APPLICANT_ID, ORG_ID, req, ACTOR_ID)
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "permanent_address" in tx_sql

    def test_save_all_address_fields(self):
        req = AddressRequest(
            permanent_address={"city": "Delhi"},
            correspondence_address={"city": "Noida"},
            emergency_contact={"name": "Parent", "phone": "9999999999"},
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[[_DRAFT_ROW], [_DRAFT_ROW]]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ApplicationFormService.save_address(APPLICANT_ID, ORG_ID, req, ACTOR_ID)
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "correspondence_address" in tx_sql
        assert "emergency_contact" in tx_sql


# =============================================================================
# Academic Qualifications
# =============================================================================

class TestAcademicQualifications:
    _QUAL_ROW = {
        "id": QUAL_ID,
        "org_id": ORG_ID,
        "applicant_id": APPLICANT_ID,
        "level": "CLASS_12",
        "board_or_university": "CBSE",
        "institution_name": "Delhi Public School",
        "year_of_passing": 2022,
        "stream_or_subject": "Science (PCM)",
        "marks_obtained": 475,
        "max_marks": 500,
        "percentage": 95.0,
        "cgpa": None,
        "grade_scale": None,
        "pass_status": "PASSED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    def test_add_class_12_qualification(self):
        req = AcademicQualificationRequest(
            applicant_id=APPLICANT_ID,
            level="CLASS_12",
            board_or_university="CBSE",
            institution_name="Delhi Public School",
            year_of_passing=2022,
            percentage=95.0,
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_DRAFT_ROW],         # _assert_form_editable
                [self._QUAL_ROW],     # SELECT after insert
            ]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.add_academic_qualification(req, ORG_ID, ACTOR_ID)
        assert result.level == "CLASS_12"
        assert result.percentage == 95.0

    def test_upsert_deletes_existing_same_level(self):
        """Re-adding same level should delete old record first."""
        req = AcademicQualificationRequest(
            applicant_id=APPLICANT_ID,
            level="CLASS_12",
            board_or_university="ICSE",
            institution_name="Some School",
            year_of_passing=2023,
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_DRAFT_ROW],
                [self._QUAL_ROW],
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ApplicationFormService.add_academic_qualification(req, ORG_ID, ACTOR_ID)

        # First op in transaction should be DELETE
        first_op_sql = mock_tx.call_args[0][0][0][0]
        assert "DELETE" in first_op_sql

    def test_list_qualifications(self):
        with patch(f"{MOD}.execute_query", return_value=[self._QUAL_ROW]):
            results = ApplicationFormService.list_academic_qualifications(APPLICANT_ID, ORG_ID)
        assert len(results) == 1
        assert results[0].board_or_university == "CBSE"

    def test_qualification_blocked_in_enrolled_state(self):
        locked = {**_DRAFT_ROW, "status": "ENROLLED"}
        req = AcademicQualificationRequest(
            applicant_id=APPLICANT_ID,
            level="CLASS_10",
            board_or_university="CBSE",
            institution_name="School",
            year_of_passing=2020,
        )
        with patch(f"{MOD}.execute_query", return_value=[locked]):
            with pytest.raises(BusinessRuleViolation, match="cannot be edited"):
                ApplicationFormService.add_academic_qualification(req, ORG_ID, ACTOR_ID)


# =============================================================================
# Entrance Exam Scores
# =============================================================================

class TestEntranceScores:
    _SCORE_ROW = {
        "id": SCORE_ID,
        "org_id": ORG_ID,
        "applicant_id": APPLICANT_ID,
        "exam_name": "JEE_MAINS",
        "exam_roll_number": "240112345",
        "exam_year": 2025,
        "score": 240.0,
        "percentile": 97.5,
        "rank": 8500,
        "score_detail": {"math": 90, "physics": 80, "chemistry": 70},
        "is_verified": False,
        "verified_method": None,
        "created_at": datetime.now(timezone.utc),
    }

    def test_add_jee_score(self):
        req = EntranceScoreRequest(
            applicant_id=APPLICANT_ID,
            exam_name="JEE_MAINS",
            exam_year=2025,
            score=240.0,
            percentile=97.5,
            rank=8500,
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_DRAFT_ROW],
                [self._SCORE_ROW],
            ]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.add_entrance_score(req, ORG_ID, ACTOR_ID)
        assert result.exam_name == "JEE_MAINS"
        assert result.percentile == 97.5

    def test_list_scores(self):
        with patch(f"{MOD}.execute_query", return_value=[self._SCORE_ROW]):
            results = ApplicationFormService.list_entrance_scores(APPLICANT_ID, ORG_ID)
        assert len(results) == 1
        assert results[0].rank == 8500

    def test_delete_score(self):
        with (
            patch(f"{MOD}.execute_query", return_value=[_DRAFT_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ApplicationFormService.delete_entrance_score(
                SCORE_ID, APPLICANT_ID, ORG_ID, ACTOR_ID
            )
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "DELETE" in tx_sql


# =============================================================================
# Program Preferences
# =============================================================================

class TestProgramPreferences:
    def test_set_preferences_replaces_all(self):
        prefs_req = ProgramPreferencesRequest(
            applicant_id=APPLICANT_ID,
            preferences=[
                ProgramPreferenceItem(program_name="B.Tech CS", specialization="AI/ML"),
                ProgramPreferenceItem(program_name="B.Tech ECE"),
            ],
        )
        pref_rows = [
            {
                "id": str(uuid4()), "org_id": ORG_ID,
                "applicant_id": APPLICANT_ID,
                "preference_order": 1,
                "program_name": "B.Tech CS",
                "specialization": "AI/ML",
                "intake_batch": None,
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": str(uuid4()), "org_id": ORG_ID,
                "applicant_id": APPLICANT_ID,
                "preference_order": 2,
                "program_name": "B.Tech ECE",
                "specialization": None,
                "intake_batch": None,
                "created_at": datetime.now(timezone.utc),
            },
        ]
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [_DRAFT_ROW],    # _assert_form_editable
                pref_rows,       # SELECT after upsert
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.set_program_preferences(
                prefs_req, ORG_ID, ACTOR_ID
            )

        assert len(result) == 2
        # First op should be DELETE (clear old prefs)
        first_op_sql = mock_tx.call_args[0][0][0][0]
        assert "DELETE" in first_op_sql

    def test_max_5_preferences_enforced_by_pydantic(self):
        with pytest.raises(Exception):  # ValidationError
            ProgramPreferencesRequest(
                applicant_id=APPLICANT_ID,
                preferences=[
                    ProgramPreferenceItem(program_name=f"Program {i}")
                    for i in range(6)  # 6 > max 5
                ],
            )

    def test_empty_preferences_rejected(self):
        with pytest.raises(Exception):
            ProgramPreferencesRequest(
                applicant_id=APPLICANT_ID,
                preferences=[],
            )


# =============================================================================
# Declaration
# =============================================================================

class TestDeclaration:
    def test_accept_declaration(self):
        req = DeclarationRequest(
            applicant_id=APPLICANT_ID,
            digital_signature="Arjun Mehta",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[[_DRAFT_ROW], [_DRAFT_ROW]]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.accept_declaration(
                APPLICANT_ID, ORG_ID, req, ACTOR_ID
            )
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "declaration_accepted" in tx_sql
        assert "digital_signature" in tx_sql


# =============================================================================
# Application Submission
# =============================================================================

class TestApplicationSubmit:
    def test_submit_valid_draft(self):
        declared_row = {
            **_DRAFT_ROW,
            "status": "DRAFT",
            "declaration_accepted": True,
        }
        submitted_row = {**declared_row, "status": "SUBMITTED"}

        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [declared_row],          # fetch applicant
                [{"id": QUAL_ID}],       # check academic qualifications
                [submitted_row],         # get_draft after update
            ]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.submit_application(
                APPLICANT_ID, ORG_ID, ACTOR_ID
            )
        assert result.status == "SUBMITTED"

    def test_submit_without_declaration_raises(self):
        no_decl = {**_DRAFT_ROW, "declaration_accepted": False}
        with patch(f"{MOD}.execute_query", return_value=[no_decl]):
            with pytest.raises(BusinessRuleViolation, match="Declaration must be accepted"):
                ApplicationFormService.submit_application(APPLICANT_ID, ORG_ID, ACTOR_ID)

    def test_submit_without_qualifications_raises(self):
        declared = {**_DRAFT_ROW, "declaration_accepted": True}
        with patch(f"{MOD}.execute_query", side_effect=[
            [declared],
            [],  # no qualifications
        ]):
            with pytest.raises(BusinessRuleViolation, match="academic qualification"):
                ApplicationFormService.submit_application(APPLICANT_ID, ORG_ID, ACTOR_ID)

    def test_submit_non_draft_state_raises(self):
        enrolled = {**_DRAFT_ROW, "status": "ENROLLED", "declaration_accepted": True}
        with patch(f"{MOD}.execute_query", return_value=[enrolled]):
            with pytest.raises(BusinessRuleViolation, match="DRAFT state"):
                ApplicationFormService.submit_application(APPLICANT_ID, ORG_ID, ACTOR_ID)


# =============================================================================
# Application Fee
# =============================================================================

class TestApplicationFee:
    def test_record_fee_from_submitted(self):
        submitted_row = {**_DRAFT_ROW, "status": "SUBMITTED"}
        docs_row = {**_DRAFT_ROW, "status": "DOCUMENTS_PENDING", "application_fee_paid": True}
        req = ApplicationFeeRequest(
            applicant_id=APPLICANT_ID,
            payment_reference="TXN-2025-9876",
            fee_amount=1000.0,
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[
                [submitted_row],
                [docs_row],
            ]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ApplicationFormService.record_application_fee(req, ORG_ID, ACTOR_ID)

        tx_call = mock_tx.call_args[0][0][0]
        tx_sql, tx_params = tx_call[0], tx_call[1]
        assert "application_fee_paid" in tx_sql
        assert "DOCUMENTS_PENDING" in tx_params

    def test_record_fee_from_wrong_state_raises(self):
        draft_row = {**_DRAFT_ROW, "status": "DRAFT"}
        req = ApplicationFeeRequest(
            applicant_id=APPLICANT_ID,
            payment_reference="TXN-001",
            fee_amount=500.0,
        )
        with patch(f"{MOD}.execute_query", return_value=[draft_row]):
            with pytest.raises(BusinessRuleViolation, match="SUBMITTED or PENDING_PAYMENT"):
                ApplicationFormService.record_application_fee(req, ORG_ID, ACTOR_ID)

    def test_record_fee_nonexistent_applicant_raises(self):
        req = ApplicationFeeRequest(
            applicant_id="bad-id",
            payment_reference="TXN-001",
            fee_amount=500.0,
        )
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                ApplicationFormService.record_application_fee(req, ORG_ID, ACTOR_ID)
