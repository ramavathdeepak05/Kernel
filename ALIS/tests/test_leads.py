"""
Tests for P3 — Lead CRM Service (Stage 1)

Covers:
  - Lead creation (multi-channel)
  - Lead status transitions (valid + invalid)
  - Activity logging
  - Lead → Applicant conversion
  - Consultant CRUD
  - Referral code generation and validation
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from server.admissions.models import (
    ConsultantCommissionType,
    ConsultantCreate,
    LeadActivityCreate,
    LeadActivityType,
    LeadConvertRequest,
    LeadCreate,
    LeadStatus,
    LeadUpdateRequest,
    ReferralCodeCreate,
    SourceChannel,
)
from server.admissions.lead_service import (
    ConsultantService,
    LeadService,
    ReferralCodeService,
)
from server.core.exceptions import BusinessRuleViolation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_ID = "org-test"
ACTOR_ID = "staff-001"
LEAD_ID = str(uuid4())
CONSULTANT_ID = str(uuid4())

_BASE_LEAD_ROW = {
    "id": LEAD_ID,
    "org_id": ORG_ID,
    "full_name": "Priya Sharma",
    "email": "priya@example.com",
    "phone": "+919876543210",
    "city": "Mumbai",
    "state_region": "Maharashtra",
    "course_interest": "B.Tech Computer Science",
    "intake_year": "2025",
    "source_type": "WEBSITE",
    "source_detail": None,
    "utm_source": "google",
    "utm_medium": "cpc",
    "utm_campaign": "admissions-2025",
    "utm_term": None,
    "utm_content": None,
    "referred_by_user_id": None,
    "consultant_id": None,
    "status": "NEW",
    "assigned_counsellor_id": None,
    "last_contacted_at": None,
    "next_followup_at": None,
    "disqualify_reason": None,
    "converted_applicant_id": None,
    "converted_at": None,
    "metadata": {},
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}

_BASE_CONSULTANT_ROW = {
    "id": CONSULTANT_ID,
    "org_id": ORG_ID,
    "name": "ABC Education",
    "company_name": "ABC Pvt Ltd",
    "email": "abc@consultants.com",
    "phone": "+919900000000",
    "city": "Delhi",
    "state_region": "Delhi",
    "status": "ACTIVE",
    "commission_type": "PERCENTAGE",
    "commission_rate": 5.0,
    "commission_amount": None,
    "portal_user_id": None,
    "agreement_signed_at": None,
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}

MOD = "server.admissions.lead_service"


# =============================================================================
# LEAD SERVICE
# =============================================================================

class TestLeadServiceCreate:
    def test_create_website_lead(self):
        req = LeadCreate(
            full_name="Priya Sharma",
            email="priya@example.com",
            phone="+919876543210",
            course_interest="B.Tech CS",
            source_type=SourceChannel.WEBSITE,
        )
        with (
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]) as mock_q,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = LeadService.create(req, ORG_ID, ACTOR_ID)

        assert result.full_name == "Priya Sharma"
        assert result.status == "NEW"
        mock_tx.assert_called()  # at least the INSERT + activity insert

    def test_create_consultant_lead_creates_referral(self):
        req = LeadCreate(
            full_name="Raj Patel",
            email="raj@example.com",
            phone="9876543210",
            source_type=SourceChannel.CONSULTANT,
            consultant_id=CONSULTANT_ID,
        )
        with (
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]),
            patch(f"{MOD}.AuditLog.log"),
        ):
            LeadService.create(req, ORG_ID, ACTOR_ID)

        # Transaction should be called 3 times: INSERT lead, INSERT activity, INSERT referral
        assert mock_tx.call_count >= 3

    def test_create_with_invalid_referral_code_raises(self):
        req = LeadCreate(
            full_name="Test User",
            email="test@example.com",
            phone="9999999999",
            source_type=SourceChannel.REFERRAL_STUDENT,
            referral_code="BADCODE",
        )
        with patch(f"{MOD}.execute_query", return_value=[]):  # code not found
            with pytest.raises(BusinessRuleViolation, match="Referral code"):
                LeadService.create(req, ORG_ID, ACTOR_ID)

    def test_invalid_email_rejected(self):
        with pytest.raises(Exception):
            LeadCreate(
                full_name="Bad Email",
                email="not-an-email",
                phone="9999999999",
                source_type=SourceChannel.WEBSITE,
            )


class TestLeadServiceRead:
    def test_get_existing_lead(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]):
            result = LeadService.get(LEAD_ID, ORG_ID)
        assert result.id == LEAD_ID
        assert result.email == "priya@example.com"

    def test_get_nonexistent_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                LeadService.get("bad-id", ORG_ID)

    def test_list_with_status_filter(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]) as mock_q:
            results = LeadService.list(ORG_ID, status="NEW", limit=10, offset=0)
        assert len(results) == 1
        sql = mock_q.call_args[0][0]
        assert "status = %s" in sql

    def test_list_with_counsellor_filter(self):
        with patch(f"{MOD}.execute_query", return_value=[]) as mock_q:
            results = LeadService.list(ORG_ID, counsellor_id="c-001")
        sql = mock_q.call_args[0][0]
        assert "assigned_counsellor_id = %s" in sql


class TestLeadServiceUpdate:
    def test_valid_status_transition_new_to_contacted(self):
        row = {**_BASE_LEAD_ROW, "status": "NEW"}
        req = LeadUpdateRequest(status=LeadStatus.CONTACTED)
        with (
            patch(f"{MOD}.execute_query", side_effect=[[row], [_BASE_LEAD_ROW]]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = LeadService.update(LEAD_ID, ORG_ID, req, ACTOR_ID)
        assert mock_tx.called

    def test_invalid_transition_converted_to_new_raises(self):
        row = {**_BASE_LEAD_ROW, "status": "CONVERTED"}
        req = LeadUpdateRequest(status=LeadStatus.NEW)
        with patch(f"{MOD}.execute_query", return_value=[row]):
            with pytest.raises(BusinessRuleViolation, match="Illegal lead status transition"):
                LeadService.update(LEAD_ID, ORG_ID, req, ACTOR_ID)

    def test_update_counsellor_assignment(self):
        req = LeadUpdateRequest(assigned_counsellor_id="counsellor-42")
        with (
            patch(f"{MOD}.execute_query", side_effect=[[_BASE_LEAD_ROW], [_BASE_LEAD_ROW]]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            LeadService.update(LEAD_ID, ORG_ID, req, ACTOR_ID)
        # UPDATE should include assigned_counsellor_id
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "assigned_counsellor_id" in tx_sql

    def test_note_creates_activity(self):
        req = LeadUpdateRequest(note="Called, no answer. Will retry tomorrow.")
        with (
            patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            LeadService.update(LEAD_ID, ORG_ID, req, ACTOR_ID)
        # Activity INSERT should have been called
        assert mock_tx.call_count >= 1

    def test_update_nonexistent_lead_raises(self):
        req = LeadUpdateRequest(status=LeadStatus.CONTACTED)
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                LeadService.update("bad-id", ORG_ID, req, ACTOR_ID)


class TestLeadActivityLog:
    def test_log_call_activity(self):
        activity_row = {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "lead_id": LEAD_ID,
            "activity_type": "CALL_LOGGED",
            "summary": "Spoke for 10 mins. Very interested.",
            "actor_id": ACTOR_ID,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
        }
        req = LeadActivityCreate(
            lead_id=LEAD_ID,
            activity_type=LeadActivityType.CALL_LOGGED,
            summary="Spoke for 10 mins. Very interested.",
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[[{"id": LEAD_ID}], [activity_row]]),
            patch(f"{MOD}.execute_transaction"),
        ):
            result = LeadService.log_activity(req, ORG_ID, ACTOR_ID)
        assert result.activity_type == "CALL_LOGGED"

    def test_log_activity_nonexistent_lead_raises(self):
        req = LeadActivityCreate(
            lead_id="bad-id",
            activity_type=LeadActivityType.NOTE,
            summary="Test note",
        )
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                LeadService.log_activity(req, ORG_ID, ACTOR_ID)

    def test_list_activities(self):
        activity_rows = [
            {
                "id": str(uuid4()),
                "org_id": ORG_ID,
                "lead_id": LEAD_ID,
                "activity_type": "EMAIL_SENT",
                "summary": "Sent brochure",
                "actor_id": ACTOR_ID,
                "metadata": {},
                "created_at": datetime.now(timezone.utc),
            }
        ]
        with patch(f"{MOD}.execute_query", return_value=activity_rows):
            results = LeadService.list_activities(LEAD_ID, ORG_ID)
        assert len(results) == 1
        assert results[0].activity_type == "EMAIL_SENT"


class TestLeadConversion:
    def test_convert_ready_to_apply_lead(self):
        ready_row = {**_BASE_LEAD_ROW, "status": "READY_TO_APPLY"}
        req = LeadConvertRequest(
            lead_id=LEAD_ID,
            intended_program="B.Tech Computer Science",
        )
        with (
            patch(f"{MOD}.execute_query", return_value=[ready_row]),
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = LeadService.convert_to_applicant(req, ORG_ID, ACTOR_ID)

        assert result["lead_id"] == LEAD_ID
        assert "applicant_id" in result
        # Should have: INSERT applicant + UPDATE lead + UPDATE referral = 1 transaction with 3 ops
        mock_tx.assert_called()

    def test_convert_interested_lead_also_allowed(self):
        interested_row = {**_BASE_LEAD_ROW, "status": "INTERESTED"}
        req = LeadConvertRequest(lead_id=LEAD_ID, intended_program="MBA")
        with (
            patch(f"{MOD}.execute_query", return_value=[interested_row]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = LeadService.convert_to_applicant(req, ORG_ID, ACTOR_ID)
        assert "applicant_id" in result

    def test_convert_new_lead_raises(self):
        req = LeadConvertRequest(lead_id=LEAD_ID, intended_program="B.Tech")
        with patch(f"{MOD}.execute_query", return_value=[_BASE_LEAD_ROW]):  # status=NEW
            with pytest.raises(BusinessRuleViolation, match="READY_TO_APPLY"):
                LeadService.convert_to_applicant(req, ORG_ID, ACTOR_ID)

    def test_convert_nonexistent_lead_raises(self):
        req = LeadConvertRequest(lead_id="bad-id", intended_program="MBA")
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                LeadService.convert_to_applicant(req, ORG_ID, ACTOR_ID)


# =============================================================================
# CONSULTANT SERVICE
# =============================================================================

class TestConsultantService:
    def test_create_consultant(self):
        req = ConsultantCreate(
            name="ABC Education Pvt Ltd",
            email="abc@example.com",
            phone="9800000000",
            commission_type=ConsultantCommissionType.PERCENTAGE,
            commission_rate=5.0,
        )
        with (
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.execute_query", return_value=[_BASE_CONSULTANT_ROW]),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ConsultantService.create(req, ORG_ID, ACTOR_ID)
        assert result.commission_type == "PERCENTAGE"
        assert result.status == "ACTIVE"

    def test_get_nonexistent_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                ConsultantService.get("bad-id", ORG_ID)

    def test_list_with_status_filter(self):
        with patch(f"{MOD}.execute_query", return_value=[_BASE_CONSULTANT_ROW]) as mock_q:
            ConsultantService.list(ORG_ID, status="ACTIVE")
        sql = mock_q.call_args[0][0]
        assert "status = %s" in sql

    def test_update_status_valid(self):
        with (
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.execute_query", return_value=[_BASE_CONSULTANT_ROW]),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ConsultantService.update_status(
                CONSULTANT_ID, ORG_ID, "SUSPENDED", ACTOR_ID
            )
        assert result is not None

    def test_update_status_invalid_raises(self):
        with pytest.raises(BusinessRuleViolation, match="Invalid consultant status"):
            ConsultantService.update_status(
                CONSULTANT_ID, ORG_ID, "GARBAGE", ACTOR_ID
            )


# =============================================================================
# REFERRAL CODE SERVICE
# =============================================================================

class TestReferralCodeService:
    _CODE_ROW = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "code": "ABCD1234",
        "referrer_type": "STUDENT",
        "referrer_id": "user-111",
        "max_uses": 10,
        "use_count": 2,
        "expires_at": None,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    def test_create_referral_code(self):
        req = ReferralCodeCreate(
            referrer_type="STUDENT",
            referrer_id="user-111",
            max_uses=10,
        )
        with (
            patch(f"{MOD}.execute_query", side_effect=[[], [self._CODE_ROW]]),
            patch(f"{MOD}.execute_transaction"),
            patch(f"{MOD}.AuditLog.log"),
        ):
            result = ReferralCodeService.create(req, ORG_ID, ACTOR_ID)
        assert result.referrer_type == "STUDENT"
        assert result.is_active is True

    def test_get_by_code(self):
        with patch(f"{MOD}.execute_query", return_value=[self._CODE_ROW]):
            result = ReferralCodeService.get_by_code("ABCD1234", ORG_ID)
        assert result.code == "ABCD1234"
        assert result.use_count == 2

    def test_get_nonexistent_raises(self):
        with patch(f"{MOD}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                ReferralCodeService.get_by_code("BADCODE", ORG_ID)

    def test_deactivate(self):
        with (
            patch(f"{MOD}.execute_transaction") as mock_tx,
            patch(f"{MOD}.AuditLog.log"),
        ):
            ReferralCodeService.deactivate("ABCD1234", ORG_ID, ACTOR_ID)
        tx_sql = mock_tx.call_args[0][0][0][0]
        assert "is_active = FALSE" in tx_sql

    def test_referral_code_validation_expired_raises(self):
        expired_row = {
            "id": str(uuid4()),
            "use_count": 0,
            "max_uses": 10,
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            "is_active": True,
        }
        with patch(f"{MOD}.execute_query", return_value=[expired_row]):
            with pytest.raises(BusinessRuleViolation, match="expired"):
                LeadService._validate_and_consume_referral_code("OLDCODE", ORG_ID)

    def test_referral_code_validation_max_uses_reached_raises(self):
        maxed_row = {
            "id": str(uuid4()),
            "use_count": 10,
            "max_uses": 10,
            "expires_at": None,
            "is_active": True,
        }
        with patch(f"{MOD}.execute_query", return_value=[maxed_row]):
            with pytest.raises(BusinessRuleViolation, match="usage limit"):
                LeadService._validate_and_consume_referral_code("FULL_CODE", ORG_ID)

    def test_referral_code_validation_inactive_raises(self):
        inactive_row = {
            "id": str(uuid4()),
            "use_count": 0,
            "max_uses": None,
            "expires_at": None,
            "is_active": False,
        }
        with patch(f"{MOD}.execute_query", return_value=[inactive_row]):
            with pytest.raises(BusinessRuleViolation, match="inactive"):
                LeadService._validate_and_consume_referral_code("DEAD_CODE", ORG_ID)
