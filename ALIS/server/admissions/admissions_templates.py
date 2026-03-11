"""
P13 — Admissions Notification Templates

Defines 35 canonical notification templates covering all 10 admissions stages:

  Stage 1  — Lead CRM              (2 templates)
  Stage 2  — Application Form      (2 templates)
  Stage 3  — Document Management   (4 templates)
  Stage 4  — Eligibility           (4 templates)
  Stage 5  — Tests & Interviews    (3 templates)
  Stage 6  — Merit List            (3 templates)
  Stage 7  — Offer Letter (P9)     (6 templates)
  Stage 8  — Payment (P10)         (4 templates)
  Stage 9  — Verification (P11)    (4 templates)
  Stage 10 — Enrollment (P12)      (3 templates)

Usage:
    # Register into in-memory TemplateRegistry (called at startup):
    AdmissionsTemplates.register_all()

    # Seed into DB for a specific org (run once per org or via migration):
    AdmissionsTemplates.seed_to_db(org_id="org-001", actor_id="system")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemplateSpec:
    key: str
    name: str
    subject: str
    body: str
    channel: str = "EMAIL"  # EMAIL | SMS | IN_APP


# fmt: off
ADMISSIONS_TEMPLATES: List[TemplateSpec] = [

    # =========================================================================
    # Stage 1 — Lead CRM
    # =========================================================================
    TemplateSpec(
        key="lead_created",
        name="Lead Created — Enquiry Received",
        subject="Thank you for your enquiry, $name",
        body=(
            "Dear $name,\n\n"
            "Thank you for your interest in $institution_name.\n"
            "Our counsellor will get in touch with you within 2 working days.\n\n"
            "Reference ID: $lead_id\n"
            "Program of interest: $program\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="lead_converted",
        name="Lead Converted — Application Open",
        subject="Your application is now open — $institution_name",
        body=(
            "Dear $name,\n\n"
            "Great news! Your profile has been approved to proceed with a formal application.\n\n"
            "Please complete your application at your earliest convenience:\n"
            "Application portal: $portal_url\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 2 — Application Form
    # =========================================================================
    TemplateSpec(
        key="application_submitted",
        name="Application Submitted",
        subject="Application received — $application_id",
        body=(
            "Dear $name,\n\n"
            "We have received your application for $program.\n\n"
            "Application ID: $application_id\n"
            "Submitted on: $submitted_at\n\n"
            "Next step: Upload your documents in the application portal.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="application_fee_paid",
        name="Application Fee Payment Confirmed",
        subject="Application fee payment confirmed — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your application fee payment of $amount has been received.\n\n"
            "Application ID: $application_id\n"
            "Transaction ID: $transaction_id\n"
            "Amount: $amount\n\n"
            "Please proceed to upload your documents.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 3 — Document Management
    # =========================================================================
    TemplateSpec(
        key="document_upload_received",
        name="Documents Received — Under Review",
        subject="Documents received and under review — $application_id",
        body=(
            "Dear $name,\n\n"
            "We have received your uploaded documents for application $application_id.\n"
            "Our team will review them within 3–5 working days.\n\n"
            "You will be notified of the outcome via email.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="document_approved",
        name="Document Approved",
        subject="Documents verified — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your documents for application $application_id have been verified successfully.\n\n"
            "Your application is now advancing to the next stage.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="document_rejected",
        name="Document Rejected — Action Required",
        subject="Action required: Document issue — $application_id",
        body=(
            "Dear $name,\n\n"
            "One or more of your documents for application $application_id could not be verified.\n\n"
            "Document: $doc_type\n"
            "Reason: $reason\n\n"
            "Please log in to the application portal and re-upload the corrected document.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="document_reupload_required",
        name="Document Re-upload Required",
        subject="Please re-upload: $doc_type — $application_id",
        body=(
            "Dear $name,\n\n"
            "We need you to re-upload the following document for your application ($application_id):\n\n"
            "Document: $doc_type\n"
            "Note: $note\n\n"
            "Please log in and re-upload at the earliest.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 4 — Eligibility
    # =========================================================================
    TemplateSpec(
        key="applicant_eligible",
        name="Eligibility Confirmed",
        subject="Eligibility confirmed — $application_id",
        body=(
            "Dear $name,\n\n"
            "Congratulations! You have been found eligible for admission to $program.\n\n"
            "Application ID: $application_id\n\n"
            "Your application will now be considered for the merit list.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="applicant_not_eligible",
        name="Eligibility Not Met",
        subject="Eligibility not met — $application_id",
        body=(
            "Dear $name,\n\n"
            "We regret to inform you that your application ($application_id) for $program "
            "does not meet the eligibility criteria.\n\n"
            "Reason: $reason\n\n"
            "If you believe this is an error, please contact our admissions office.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="review_required",
        name="Staff Review Required (Internal)",
        subject="[Admissions] Review required — Applicant $applicant_id",
        body=(
            "Hello $name,\n\n"
            "An applicant requires your review:\n\n"
            "Applicant ID: $applicant_id\n"
            "Reason: $reason\n"
            "Flags: $flags\n\n"
            "Please log in to the ALIS admin portal to take action.\n\n"
            "ALIS System"
        ),
    ),
    TemplateSpec(
        key="applicant_rejected",
        name="Application Not Progressed",
        subject="Update on your application — $application_id",
        body=(
            "Dear $name,\n\n"
            "After careful review, we are unable to progress your application ($application_id) "
            "at this time.\n\n"
            "Reason: $reason\n\n"
            "We appreciate your interest in $institution_name and encourage you to apply in future cycles.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 5 — Entrance Test & Interview
    # =========================================================================
    TemplateSpec(
        key="test_slot_booked",
        name="Entrance Test Slot Confirmed",
        subject="Entrance test slot confirmed — $test_name",
        body=(
            "Dear $name,\n\n"
            "Your entrance test slot has been confirmed.\n\n"
            "Test: $test_name\n"
            "Date: $test_date\n"
            "Venue / Mode: $venue\n"
            "Report by: $report_time\n\n"
            "Your admit card will be available closer to the test date.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="admit_card_ready",
        name="Admit Card Available",
        subject="Admit card ready — $test_name",
        body=(
            "Dear $name,\n\n"
            "Your admit card for $test_name is now available.\n\n"
            "Roll Number: $roll_number\n"
            "Test Date: $test_date\n"
            "Venue: $venue\n\n"
            "Download your admit card from the portal. Carry a printout on the day of the test.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="interview_scheduled",
        name="Interview Scheduled",
        subject="Interview scheduled — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your interview for $program admission has been scheduled.\n\n"
            "Date: $interview_date\n"
            "Time: $interview_time\n"
            "Mode / Venue: $venue\n"
            "Panel: $panel_name\n\n"
            "Please be prepared with original documents.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 6 — Merit List
    # =========================================================================
    TemplateSpec(
        key="merit_list_published",
        name="Merit List Published (Staff / Broadcast)",
        subject="[Admissions] Merit list published — $program ($batch)",
        body=(
            "The merit list for $program (Batch $batch) has been published.\n\n"
            "Total ranked: $total_ranked\n"
            "Waitlisted: $total_waitlisted\n\n"
            "Offers will be dispatched to ranked applicants automatically.\n\n"
            "ALIS System"
        ),
    ),
    TemplateSpec(
        key="merit_listed",
        name="Merit Listed — Offer Forthcoming",
        subject="You are on the merit list — $program",
        body=(
            "Dear $name,\n\n"
            "Congratulations! You have been included in the merit list for $program (Batch $batch).\n\n"
            "Merit Rank: $rank\n"
            "Category: $category\n\n"
            "Your offer letter will be issued shortly. Please keep an eye on your inbox.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="waitlisted",
        name="Waitlisted",
        subject="Waitlisted — $program",
        body=(
            "Dear $name,\n\n"
            "You have been placed on the waitlist for $program (Batch $batch).\n\n"
            "Waitlist Position: $waitlist_position\n\n"
            "We will contact you if a seat becomes available. Please do not take any other action at this stage.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 7 — Offer Letter (P9)
    # =========================================================================
    TemplateSpec(
        key="offer_letter_issued",
        name="Offer Letter Issued",
        subject="Offer of admission — $program — Action required by $deadline",
        body=(
            "Dear $name,\n\n"
            "We are pleased to offer you admission to $program at $institution_name.\n\n"
            "Offer Reference: $offer_id\n"
            "Acceptance Deadline: $deadline\n"
            "Seat Fee Payable: $fee_amount\n\n"
            "Please log in to the portal to accept this offer and initiate your seat payment.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="offer_accepted",
        name="Offer Accepted — Seat Confirmed",
        subject="Seat confirmed — $program",
        body=(
            "Dear $name,\n\n"
            "Your offer of admission to $program has been accepted and your seat is confirmed.\n\n"
            "Next step: Complete the seat security fee payment by $payment_deadline.\n"
            "Portal: $portal_url\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="offer_declined",
        name="Offer Declined — Confirmation",
        subject="Offer declined — $program",
        body=(
            "Dear $name,\n\n"
            "We have recorded your decision to decline the offer of admission to $program.\n\n"
            "If this was a mistake, please contact our admissions office immediately.\n\n"
            "We wish you the very best in your future endeavours.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="offer_expired",
        name="Offer Letter Expired",
        subject="Your offer has expired — $program",
        body=(
            "Dear $name,\n\n"
            "Unfortunately, your offer of admission to $program has expired as you did not "
            "accept it by the deadline ($expired_on).\n\n"
            "If you still wish to be considered, please contact our admissions office as soon as possible.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="offer_reminder_t3",
        name="Offer Reminder — 3 Days Left",
        subject="Reminder: 3 days left to accept your offer — $program",
        body=(
            "Dear $name,\n\n"
            "This is a reminder that you have 3 days left to accept your offer of admission to $program.\n\n"
            "Acceptance Deadline: $deadline\n"
            "Portal: $portal_url\n\n"
            "Please log in and accept your offer before the deadline to secure your seat.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="offer_reminder_t1",
        name="Offer Reminder — Last Day",
        subject="URGENT: Last day to accept your offer — $program",
        body=(
            "Dear $name,\n\n"
            "Today is the LAST DAY to accept your offer of admission to $program.\n\n"
            "Acceptance Deadline: $deadline\n"
            "Portal: $portal_url\n\n"
            "If you do not respond today, your offer will be cancelled and your seat released.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 8 — Payment (P10)
    # =========================================================================
    TemplateSpec(
        key="demand_draft_received",
        name="Demand Draft Received — Under Verification",
        subject="Demand draft received — $dd_number",
        body=(
            "Dear $name,\n\n"
            "We have received your demand draft and it is currently under verification.\n\n"
            "DD Number: $dd_number\n"
            "Bank: $bank_name\n"
            "Amount: $amount\n\n"
            "You will be notified once the verification is complete.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="payment_verified",
        name="Payment Verified — Verification Stage Initiated",
        subject="Payment verified — document verification now open",
        body=(
            "Dear $name,\n\n"
            "Your payment has been verified successfully.\n\n"
            "Amount Verified: $amount\n\n"
            "Your application has now moved to the document verification stage. "
            "You will be contacted shortly with your verification appointment details.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="refund_approved",
        name="Refund Approved",
        subject="Refund approved — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your refund request for application $application_id has been approved.\n\n"
            "Refund Amount: $refund_amount\n"
            "Refund Policy: $policy_label\n\n"
            "The amount will be processed within 5–7 working days to your original payment source.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="refund_processed",
        name="Refund Processed",
        subject="Refund processed — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your refund of $refund_amount for application $application_id has been processed.\n\n"
            "Gateway Reference: $gateway_refund_id\n\n"
            "Please allow 2–3 business days for the amount to reflect in your account.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 9 — Final Verification (P11)
    # =========================================================================
    TemplateSpec(
        key="verification_initiated",
        name="Document Verification Appointment",
        subject="Document verification appointment — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your document verification session has been scheduled.\n\n"
            "Mode: $verification_mode\n"
            "Reporting Date: $reporting_date\n"
            "Assigned Officer: $assigned_officer\n\n"
            "Please bring original documents along with self-attested copies.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="verification_cleared",
        name="Verification Cleared — Enrollment Proceeding",
        subject="Document verification cleared — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your document verification has been completed successfully.\n\n"
            "Your enrollment is now being processed. You will receive your roll number and "
            "student credentials shortly.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="verification_cleared_undertaking",
        name="Verification Cleared with Undertaking",
        subject="Verification cleared with undertaking — $application_id",
        body=(
            "Dear $name,\n\n"
            "Your document verification has been cleared with a signed undertaking.\n\n"
            "Please ensure you submit the required documents by $due_date. "
            "Failure to do so may result in cancellation of admission.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),
    TemplateSpec(
        key="verification_rejected",
        name="Verification Rejected",
        subject="Document verification unsuccessful — $application_id",
        body=(
            "Dear $name,\n\n"
            "We regret to inform you that your document verification for application $application_id "
            "was unsuccessful.\n\n"
            "Reason: $reason\n\n"
            "If you believe this is an error, please contact the admissions office within 48 hours.\n\n"
            "Best regards,\n"
            "$institution_name Admissions Team"
        ),
    ),

    # =========================================================================
    # Stage 10 — Enrollment (P12)
    # =========================================================================
    TemplateSpec(
        key="student_enrolled",
        name="Welcome — Enrollment Complete",
        subject="Welcome to $institution_name — Roll No: $roll_number",
        body=(
            "Dear $name,\n\n"
            "Congratulations and welcome to $institution_name!\n\n"
            "Program: $program\n"
            "Roll Number: $roll_number\n"
            "Batch: $batch_year\n\n"
            "Your student credentials and portal access will be shared shortly.\n\n"
            "We look forward to a wonderful academic journey with you.\n\n"
            "Best regards,\n"
            "$institution_name"
        ),
    ),
    TemplateSpec(
        key="university_email_assigned",
        name="University Email Assigned",
        subject="Your university email is ready — $university_email",
        body=(
            "Dear $name,\n\n"
            "Your university email account has been created.\n\n"
            "Email: $university_email\n\n"
            "Please log in and change your temporary password immediately.\n"
            "Login portal: $email_portal_url\n\n"
            "Best regards,\n"
            "$institution_name IT Team"
        ),
    ),
    TemplateSpec(
        key="lms_account_created",
        name="LMS Account Ready",
        subject="Your learning portal account is ready",
        body=(
            "Dear $name,\n\n"
            "Your Learning Management System (LMS) account has been created.\n\n"
            "LMS Account ID: $lms_account_id\n"
            "Portal: $lms_url\n\n"
            "Your course materials for the upcoming semester will be available before the start date.\n\n"
            "Best regards,\n"
            "$institution_name"
        ),
    ),
]
# fmt: on


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------

class AdmissionsTemplates:
    """
    Registry of all admissions notification templates.
    """

    @classmethod
    def all(cls) -> List[TemplateSpec]:
        return list(ADMISSIONS_TEMPLATES)

    @classmethod
    def get(cls, key: str) -> TemplateSpec | None:
        return next((t for t in ADMISSIONS_TEMPLATES if t.key == key), None)

    @classmethod
    def register_all(cls) -> None:
        """
        Register all templates into the in-memory TemplateRegistry.
        Call once at application startup.
        """
        from server.core.notifications.templates import NotificationTemplate, TemplateRegistry

        registered = 0
        for spec in ADMISSIONS_TEMPLATES:
            template = NotificationTemplate(
                id=spec.key,
                name=spec.name,
                subject_template=spec.subject,
                body_template=spec.body,
            )
            TemplateRegistry.register(template)
            registered += 1

        logger.info("P13: %d admissions templates registered in TemplateRegistry", registered)

    @classmethod
    def seed_to_db(cls, org_id: str, actor_id: str = "system") -> int:
        """
        Seed all admissions templates into the notification_templates DB table
        for the given org. Skips templates that already exist (by key+channel).

        Returns the number of templates inserted.
        """
        from server.communication.models import TemplateCreate, NotifChannel
        from server.communication.notif_templates import NotifTemplateService

        inserted = 0
        skipped = 0

        for spec in ADMISSIONS_TEMPLATES:
            try:
                channel = NotifChannel(spec.channel)
                req = TemplateCreate(
                    key=spec.key,
                    name=spec.name,
                    subject=spec.subject,
                    body=spec.body,
                    channel=channel,
                )
                NotifTemplateService.create(org_id=org_id, req=req, actor_id=actor_id)
                inserted += 1
            except Exception as exc:
                # BusinessRuleViolation = already exists → skip silently
                skipped += 1
                logger.debug("P13 seed skip [%s]: %s", spec.key, exc)

        logger.info(
            "P13: Admissions templates seeded — inserted=%d, skipped=%d, org=%s",
            inserted, skipped, org_id,
        )
        return inserted
