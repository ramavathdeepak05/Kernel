"""
P13 — Admissions Notification Templates Tests

Tests for:
  - Template completeness (35 templates, required keys/fields)
  - Template rendering (variable substitution)
  - AdmissionsTemplates.register_all() — in-memory TemplateRegistry
  - AdmissionsTemplates.seed_to_db() — DB seed with idempotency
  - Event handler wiring — all 24 handlers registered
  - New P8-P12 handler dispatch (send_templated called with correct template_id)
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, call, MagicMock

MOD_HANDLERS = "server.admissions.event_handlers"
MOD_SEND = f"{MOD_HANDLERS}._send_notification"
MOD_EQ = f"{MOD_HANDLERS}.execute_query"
MOD_SEND_TASK = "server.tasks.notifications.send_templated"

ORG = "org-001"
APPLICANT_ID = "app-001"


# =============================================================================
# Template Definitions
# =============================================================================

class TestTemplateCompleteness:
    def test_total_count(self):
        from server.admissions.admissions_templates import ADMISSIONS_TEMPLATES
        assert len(ADMISSIONS_TEMPLATES) == 35

    def test_all_have_required_fields(self):
        from server.admissions.admissions_templates import ADMISSIONS_TEMPLATES
        for t in ADMISSIONS_TEMPLATES:
            assert t.key, f"Template missing key: {t}"
            assert t.name, f"Template missing name: {t.key}"
            assert t.subject, f"Template missing subject: {t.key}"
            assert t.body, f"Template missing body: {t.key}"
            assert t.channel in ("EMAIL", "SMS", "IN_APP"), f"Invalid channel: {t.key}"

    def test_keys_are_unique(self):
        from server.admissions.admissions_templates import ADMISSIONS_TEMPLATES
        keys = [t.key for t in ADMISSIONS_TEMPLATES]
        assert len(keys) == len(set(keys)), "Duplicate template keys found"

    def test_all_stage_keys_present(self):
        from server.admissions.admissions_templates import ADMISSIONS_TEMPLATES
        keys = {t.key for t in ADMISSIONS_TEMPLATES}
        required_keys = [
            # Stage 1
            "lead_created", "lead_converted",
            # Stage 2
            "application_submitted", "application_fee_paid",
            # Stage 3
            "document_upload_received", "document_approved",
            "document_rejected", "document_reupload_required",
            # Stage 4
            "applicant_eligible", "applicant_not_eligible",
            "review_required", "applicant_rejected",
            # Stage 5
            "test_slot_booked", "admit_card_ready", "interview_scheduled",
            # Stage 6
            "merit_list_published", "merit_listed", "waitlisted",
            # Stage 7
            "offer_letter_issued", "offer_accepted", "offer_declined",
            "offer_expired", "offer_reminder_t3", "offer_reminder_t1",
            # Stage 8
            "demand_draft_received", "payment_verified",
            "refund_approved", "refund_processed",
            # Stage 9
            "verification_initiated", "verification_cleared",
            "verification_cleared_undertaking", "verification_rejected",
            # Stage 10
            "student_enrolled", "university_email_assigned", "lms_account_created",
        ]
        for key in required_keys:
            assert key in keys, f"Missing required template: {key}"


class TestTemplateRendering:
    def test_lead_created_renders(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        spec = AdmissionsTemplates.get("lead_created")
        assert spec is not None
        from string import Template
        subject = Template(spec.subject).safe_substitute({"name": "Priya"})
        body = Template(spec.body).safe_substitute({
            "name": "Priya",
            "institution_name": "Test University",
            "lead_id": "LEAD-001",
            "program": "MBA",
        })
        assert "Priya" in subject
        assert "LEAD-001" in body
        assert "Test University" in body

    def test_offer_letter_issued_renders(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        from string import Template
        spec = AdmissionsTemplates.get("offer_letter_issued")
        subject = Template(spec.subject).safe_substitute({
            "program": "Computer Science",
            "deadline": "2025-04-01",
        })
        body = Template(spec.body).safe_substitute({
            "name": "Ravi",
            "program": "Computer Science",
            "institution_name": "Test University",
            "offer_id": "OFR-001",
            "deadline": "2025-04-01",
            "fee_amount": "₹50,000",
        })
        assert "Computer Science" in subject
        assert "2025-04-01" in body
        assert "OFR-001" in body

    def test_student_enrolled_renders(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        from string import Template
        spec = AdmissionsTemplates.get("student_enrolled")
        body = Template(spec.body).safe_substitute({
            "name": "Anjali",
            "institution_name": "Test University",
            "program": "B.Tech",
            "roll_number": "CS-2025-0001",
            "batch_year": "2025",
        })
        assert "CS-2025-0001" in body
        assert "B.Tech" in body

    def test_missing_vars_safe_substitute(self):
        """safe_substitute leaves $var unchanged — no KeyError on missing context."""
        from server.admissions.admissions_templates import AdmissionsTemplates
        from string import Template
        spec = AdmissionsTemplates.get("refund_approved")
        # Deliberately omit some variables — should not raise
        body = Template(spec.body).safe_substitute({"name": "Test"})
        assert "Test" in body or "$" in body  # safe_substitute leaves unknowns


# =============================================================================
# AdmissionsTemplates.register_all()
# =============================================================================

class TestRegisterAll:
    def test_register_all_populates_registry(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        from server.core.notifications.templates import TemplateRegistry

        AdmissionsTemplates.register_all()

        # Spot-check a few keys
        for key in ["lead_created", "offer_letter_issued", "student_enrolled", "verification_cleared"]:
            t = TemplateRegistry.get(key)
            assert t is not None, f"Template '{key}' not found in TemplateRegistry after register_all"
            assert t.id == key

    def test_register_all_idempotent(self):
        """Calling register_all twice does not raise."""
        from server.admissions.admissions_templates import AdmissionsTemplates
        AdmissionsTemplates.register_all()
        AdmissionsTemplates.register_all()  # second call — no error

    def test_registry_can_render_after_register(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        from server.core.notifications.templates import TemplateRegistry

        AdmissionsTemplates.register_all()
        subject, body = TemplateRegistry.render("application_submitted", {
            "name": "Test",
            "program": "MBA",
            "application_id": "APP-2025-001",
            "submitted_at": "2025-03-08",
            "institution_name": "Uni",
        })
        assert "APP-2025-001" in body


# =============================================================================
# AdmissionsTemplates.seed_to_db()
# =============================================================================

_PATCH_NOTIF_SVC = "server.communication.notif_templates.NotifTemplateService"


class TestSeedToDB:
    def test_seed_inserts_all_templates(self):
        from server.admissions.admissions_templates import AdmissionsTemplates, ADMISSIONS_TEMPLATES
        from server.communication import notif_templates as _nt_mod

        mock_create = MagicMock(return_value={"id": "tid-001"})

        with patch.object(_nt_mod.NotifTemplateService, "create", mock_create):
            count = AdmissionsTemplates.seed_to_db(ORG, actor_id="system")

        assert count == len(ADMISSIONS_TEMPLATES)
        assert mock_create.call_count == len(ADMISSIONS_TEMPLATES)

    def test_seed_skips_existing(self):
        """BusinessRuleViolation on create → skipped, returns count of inserted only."""
        from server.admissions.admissions_templates import AdmissionsTemplates, ADMISSIONS_TEMPLATES
        from server.core.exceptions import BusinessRuleViolation
        from server.communication import notif_templates as _nt_mod

        side_effects = (
            [{"id": "t"}] * 5
            + [BusinessRuleViolation(message="already exists")] * (len(ADMISSIONS_TEMPLATES) - 5)
        )
        mock_create = MagicMock(side_effect=side_effects)

        with patch.object(_nt_mod.NotifTemplateService, "create", mock_create):
            count = AdmissionsTemplates.seed_to_db(ORG)

        assert count == 5

    def test_seed_uses_correct_channel(self):
        from server.admissions.admissions_templates import AdmissionsTemplates
        from server.communication.models import NotifChannel
        from server.communication import notif_templates as _nt_mod

        captured = []

        def capture_create(org_id, req, actor_id):
            captured.append(req)
            return {"id": "tid"}

        with patch.object(_nt_mod.NotifTemplateService, "create", side_effect=capture_create):
            AdmissionsTemplates.seed_to_db(ORG)

        for req in captured:
            assert req.channel in (NotifChannel.EMAIL, NotifChannel.SMS, NotifChannel.IN_APP)


# =============================================================================
# Event Handler Registration
# =============================================================================

class TestHandlerRegistration:
    def test_register_all_registers_24_handlers(self):
        import server.core.domain_events as _dev
        from server.admissions import event_handlers

        # Clear module-level handler dict and re-register
        original = _dev._handlers.copy()
        _dev._handlers.clear()
        try:
            with patch("server.admissions.admissions_templates.AdmissionsTemplates.register_all"):
                event_handlers.register_all()

            registered_events = set(_dev._handlers.keys())
            expected_events = {
                "ApplicantEligible", "ApplicantFlaggedForReview", "ApplicantRejected",
                "OfferLetterIssued", "StudentEnrolled", "OfferLetterExpired", "ReviewItemDecided",
                "MeritListPublished", "ApplicantMeritListed", "ApplicantWaitlisted",
                "OfferAccepted", "OfferDeclined", "OfferReminderT3", "OfferReminderT1",
                "DemandDraftSubmitted", "PaymentVerified", "RefundApproved", "RefundProcessed",
                "VerificationInitiated", "VerificationCleared",
                "VerificationClearedUndertaking", "VerificationRejected",
                "UniversityEmailAssigned", "LMSAccountCreated",
            }
            for event in expected_events:
                assert event in registered_events, f"Handler for '{event}' not registered"
        finally:
            _dev._handlers.clear()
            _dev._handlers.update(original)

    def test_register_all_calls_template_registration(self):
        import server.core.domain_events as _dev
        from server.admissions import event_handlers

        original = _dev._handlers.copy()
        _dev._handlers.clear()
        try:
            with patch("server.admissions.admissions_templates.AdmissionsTemplates.register_all") as mock_reg:
                event_handlers.register_all()
            mock_reg.assert_called_once()
        finally:
            _dev._handlers.clear()
            _dev._handlers.update(original)


# =============================================================================
# New P9-P12 Handler Dispatch
# =============================================================================

def _make_event(event_type: str, entity_id: str = APPLICANT_ID, payload: dict = None):
    from server.core.domain_events import DomainEvent
    return DomainEvent(
        event_type=event_type,
        entity_type="applicant",
        entity_id=entity_id,
        org_id=ORG,
        payload=payload or {},
    )


class TestP9Handlers:
    def test_offer_accepted_handler(self):
        from server.admissions.event_handlers import on_offer_accepted
        with patch(MOD_SEND) as mock_send:
            on_offer_accepted(_make_event("OfferAccepted", payload={"payment_deadline": "2025-04-10"}))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "offer_accepted"
        assert mock_send.call_args[1]["context"]["payment_deadline"] == "2025-04-10"

    def test_offer_declined_handler(self):
        from server.admissions.event_handlers import on_offer_declined
        with patch(MOD_SEND) as mock_send:
            on_offer_declined(_make_event("OfferDeclined"))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "offer_declined"

    def test_offer_reminder_t3_handler(self):
        from server.admissions.event_handlers import on_offer_reminder_t3
        with patch(MOD_SEND) as mock_send:
            on_offer_reminder_t3(_make_event("OfferReminderT3", payload={"deadline": "2025-04-01"}))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "offer_reminder_t3"

    def test_offer_reminder_t1_handler(self):
        from server.admissions.event_handlers import on_offer_reminder_t1
        with patch(MOD_SEND) as mock_send:
            on_offer_reminder_t1(_make_event("OfferReminderT1"))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "offer_reminder_t1"


class TestP8Handlers:
    def test_merit_listed_handler(self):
        from server.admissions.event_handlers import on_merit_listed
        with patch(MOD_SEND) as mock_send:
            on_merit_listed(_make_event("ApplicantMeritListed", payload={"rank": 5, "category": "OPEN"}))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "merit_listed"
        assert mock_send.call_args[1]["context"]["rank"] == 5

    def test_waitlisted_handler(self):
        from server.admissions.event_handlers import on_waitlisted
        with patch(MOD_SEND) as mock_send:
            on_waitlisted(_make_event("ApplicantWaitlisted", payload={"waitlist_position": 3}))
        mock_send.assert_called_once()
        assert mock_send.call_args[1]["template_id"] == "waitlisted"
        assert mock_send.call_args[1]["context"]["waitlist_position"] == 3

    def test_merit_list_published_notifies_admins(self):
        from server.admissions.event_handlers import on_merit_list_published
        admins = [
            {"id": "u-1", "email": "admin@uni.edu", "name": "Admin 1"},
            {"id": "u-2", "email": "admin2@uni.edu", "name": "Admin 2"},
        ]
        mock_task = MagicMock()
        with (
            patch("server.db_service.execute_query", return_value=admins),
            patch("server.tasks.notifications.send_templated", mock_task),
        ):
            on_merit_list_published(_make_event("MeritListPublished", payload={
                "program": "CS", "batch": "2025",
                "total_ranked": 50, "total_waitlisted": 10,
            }))

        assert mock_task.delay.call_count == 2
        first_call = mock_task.delay.call_args_list[0]
        assert first_call[1]["template_id"] == "merit_list_published"


class TestP10Handlers:
    def test_demand_draft_submitted_handler(self):
        from server.admissions.event_handlers import on_demand_draft_submitted
        with patch(MOD_SEND) as mock_send:
            on_demand_draft_submitted(_make_event("DemandDraftSubmitted", payload={
                "dd_number": "DD-12345", "bank_name": "SBI", "amount": "50000"
            }))
        assert mock_send.call_args[1]["template_id"] == "demand_draft_received"
        assert mock_send.call_args[1]["context"]["dd_number"] == "DD-12345"

    def test_payment_verified_handler(self):
        from server.admissions.event_handlers import on_payment_verified
        with patch(MOD_SEND) as mock_send:
            on_payment_verified(_make_event("PaymentVerified", payload={"amount": "50000"}))
        assert mock_send.call_args[1]["template_id"] == "payment_verified"

    def test_refund_approved_handler(self):
        from server.admissions.event_handlers import on_refund_approved
        with patch(MOD_SEND) as mock_send:
            on_refund_approved(_make_event("RefundApproved", payload={
                "refund_amount": "40000", "policy_label": "DAY_15_TO_30_80PCT"
            }))
        assert mock_send.call_args[1]["template_id"] == "refund_approved"
        assert mock_send.call_args[1]["context"]["refund_amount"] == "40000"

    def test_refund_processed_handler(self):
        from server.admissions.event_handlers import on_refund_processed
        with patch(MOD_SEND) as mock_send:
            on_refund_processed(_make_event("RefundProcessed", payload={
                "refund_amount": "40000", "gateway_refund_id": "GW-999"
            }))
        assert mock_send.call_args[1]["template_id"] == "refund_processed"
        assert mock_send.call_args[1]["context"]["gateway_refund_id"] == "GW-999"


class TestP11Handlers:
    def test_verification_initiated_handler(self):
        from server.admissions.event_handlers import on_verification_initiated
        with patch(MOD_SEND) as mock_send:
            on_verification_initiated(_make_event("VerificationInitiated", payload={
                "verification_mode": "IN_PERSON",
                "reporting_date": "2025-03-20",
                "assigned_officer": "officer-1",
            }))
        assert mock_send.call_args[1]["template_id"] == "verification_initiated"
        assert mock_send.call_args[1]["context"]["verification_mode"] == "IN_PERSON"

    def test_verification_cleared_handler(self):
        from server.admissions.event_handlers import on_verification_cleared
        with patch(MOD_SEND) as mock_send:
            on_verification_cleared(_make_event("VerificationCleared"))
        assert mock_send.call_args[1]["template_id"] == "verification_cleared"

    def test_verification_cleared_undertaking_handler(self):
        from server.admissions.event_handlers import on_verification_cleared_undertaking
        with patch(MOD_SEND) as mock_send:
            on_verification_cleared_undertaking(_make_event("VerificationClearedUndertaking", payload={
                "due_date": "2025-04-15"
            }))
        assert mock_send.call_args[1]["template_id"] == "verification_cleared_undertaking"
        assert mock_send.call_args[1]["context"]["due_date"] == "2025-04-15"

    def test_verification_rejected_handler(self):
        from server.admissions.event_handlers import on_verification_rejected
        with patch(MOD_SEND) as mock_send:
            on_verification_rejected(_make_event("VerificationRejected", payload={
                "reason": "Suspected fraud"
            }))
        assert mock_send.call_args[1]["template_id"] == "verification_rejected"
        assert mock_send.call_args[1]["context"]["reason"] == "Suspected fraud"


class TestP12Handlers:
    def test_university_email_assigned_handler(self):
        from server.admissions.event_handlers import on_university_email_assigned
        with patch(MOD_SEND) as mock_send:
            on_university_email_assigned(_make_event("UniversityEmailAssigned", payload={
                "university_email": "j.doe@university.edu",
                "email_portal_url": "https://mail.university.edu",
            }))
        assert mock_send.call_args[1]["template_id"] == "university_email_assigned"
        assert mock_send.call_args[1]["context"]["university_email"] == "j.doe@university.edu"

    def test_lms_account_created_handler(self):
        from server.admissions.event_handlers import on_lms_account_created
        with patch(MOD_SEND) as mock_send:
            on_lms_account_created(_make_event("LMSAccountCreated", payload={
                "lms_account_id": "LMS-001",
                "lms_url": "https://lms.university.edu",
            }))
        assert mock_send.call_args[1]["template_id"] == "lms_account_created"
        assert mock_send.call_args[1]["context"]["lms_account_id"] == "LMS-001"
