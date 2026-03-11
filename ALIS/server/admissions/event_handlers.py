"""
M1 Admissions — Domain Event Handlers — E04-S16

Registers handlers for domain events that trigger admissions pipeline actions
or send auto-notifications at each lifecycle step.

Registered at application startup (server/main.py calls register_all()).
"""

import logging

from server.core.domain_events import DomainEvent, register_handler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _send_notification(template_id: str, applicant_id: str, org_id: str, context: dict) -> None:
    """Fire-and-forget notification via Celery."""
    try:
        from server.db_service import execute_query
        rows = execute_query(
            "SELECT name, email, phone FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not rows:
            return
        applicant = rows[0]
        from server.tasks.notifications import send_templated
        send_templated.delay(
            template_id=template_id,
            recipient_id=applicant_id,
            recipient_address=applicant["email"],
            context={**context, "name": applicant["name"]},
            org_id=org_id,
            channels=["EMAIL"],
        )
    except Exception as exc:
        logger.warning("E04-S16: notification dispatch failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Handler: ApplicantEligible → notify applicant + advance pipeline
# ---------------------------------------------------------------------------

def on_applicant_eligible(event: DomainEvent) -> None:
    applicant_id = event.entity_id
    org_id = event.org_id

    _send_notification(
        template_id="applicant_eligible",
        applicant_id=applicant_id,
        org_id=org_id,
        context={"flags": event.payload.get("flags", [])},
    )
    # Pipeline will already be advanced by the task that published this event.
    # No re-queue needed.


# ---------------------------------------------------------------------------
# Handler: ApplicantFlaggedForReview → notify staff
# ---------------------------------------------------------------------------

def on_applicant_flagged(event: DomainEvent) -> None:
    org_id = event.org_id

    try:
        # Notify all ADMIN users in the org
        from server.db_service import execute_query
        from server.tasks.notifications import send_templated
        admins = execute_query(
            "SELECT id, email, name FROM users WHERE org_id = %s AND role IN ('ADMIN','SUPER_ADMIN') AND status = 'ACTIVE'",
            (org_id,),
        )
        for admin in admins:
            send_templated.delay(
                template_id="review_required",
                recipient_id=str(admin["id"]),
                recipient_address=admin["email"],
                context={
                    "name": admin["name"],
                    "applicant_id": event.entity_id,
                    "reason": event.payload.get("reason", ""),
                    "flags": event.payload.get("flags", []),
                },
                org_id=org_id,
                channels=["EMAIL"],
            )
    except Exception as exc:
        logger.warning("E04-S16: staff notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Handler: ApplicantRejected → notify applicant
# ---------------------------------------------------------------------------

def on_applicant_rejected(event: DomainEvent) -> None:
    _send_notification(
        template_id="applicant_rejected",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={"reason": event.payload.get("reason", "")},
    )


# ---------------------------------------------------------------------------
# Handler: OfferLetterIssued → notify applicant with payment instructions
# ---------------------------------------------------------------------------

def on_offer_letter_issued(event: DomainEvent) -> None:
    _send_notification(
        template_id="offer_letter_issued",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={},
    )


# ---------------------------------------------------------------------------
# Handler: StudentEnrolled → welcome email + trigger downstream modules
# ---------------------------------------------------------------------------

def on_student_enrolled(event: DomainEvent) -> None:
    applicant_id = event.entity_id
    org_id = event.org_id

    _send_notification(
        template_id="student_enrolled",
        applicant_id=applicant_id,
        org_id=org_id,
        context={
            "roll_number": event.payload.get("roll_number", ""),
            "program": event.payload.get("program", ""),
        },
    )
    # Downstream modules (E05 Academics, E07 Finance) subscribe to StudentEnrolled
    # via their own event_handlers.py — no direct calls from here.


# ---------------------------------------------------------------------------
# Handler: OfferLetterExpired → notify applicant + mark offer invalid
# ---------------------------------------------------------------------------

def on_offer_expired(event: DomainEvent) -> None:
    applicant_id = event.entity_id
    org_id = event.org_id

    try:
        from server.db_service import execute_transaction
        execute_transaction([
            (
                "UPDATE offer_letters SET is_valid = FALSE WHERE applicant_id = %s AND org_id = %s AND is_valid = TRUE",
                (applicant_id, org_id),
            )
        ])
    except Exception as exc:
        logger.error("E04-S16: offer expiry update failed: %s", exc)

    _send_notification(
        template_id="offer_expired",
        applicant_id=applicant_id,
        org_id=org_id,
        context={"expired_on": event.payload.get("expired_on", "")},
    )


# ---------------------------------------------------------------------------
# Handler: ReviewDecided → resume pipeline
# ---------------------------------------------------------------------------

def on_review_decided(event: DomainEvent) -> None:
    """After staff decides on a review item, re-queue the pipeline."""
    try:
        from server.tasks.admissions import advance_pipeline
        advance_pipeline.delay(
            org_id=event.org_id,
            applicant_id=event.entity_id,
        )
    except Exception as exc:
        logger.warning("E04-S16: pipeline re-queue after review failed: %s", exc)


# ---------------------------------------------------------------------------
# P9 — Offer Letter
# ---------------------------------------------------------------------------

def on_offer_accepted(event: DomainEvent) -> None:
    _send_notification(
        template_id="offer_accepted",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "payment_deadline": event.payload.get("payment_deadline", ""),
            "portal_url": event.payload.get("portal_url", ""),
        },
    )


def on_offer_declined(event: DomainEvent) -> None:
    _send_notification(
        template_id="offer_declined",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={},
    )


def on_offer_reminder_t3(event: DomainEvent) -> None:
    _send_notification(
        template_id="offer_reminder_t3",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "deadline": event.payload.get("deadline", ""),
            "portal_url": event.payload.get("portal_url", ""),
            "program": event.payload.get("program", ""),
        },
    )


def on_offer_reminder_t1(event: DomainEvent) -> None:
    _send_notification(
        template_id="offer_reminder_t1",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "deadline": event.payload.get("deadline", ""),
            "portal_url": event.payload.get("portal_url", ""),
            "program": event.payload.get("program", ""),
        },
    )


# ---------------------------------------------------------------------------
# P8 — Merit List
# ---------------------------------------------------------------------------

def on_merit_list_published(event: DomainEvent) -> None:
    """Notify staff (broadcast) when merit list is published."""
    org_id = event.org_id
    payload = event.payload

    try:
        from server.db_service import execute_query
        from server.tasks.notifications import send_templated
        admins = execute_query(
            "SELECT id, email, name FROM users "
            "WHERE org_id = %s AND role IN ('ADMIN','SUPER_ADMIN') AND status = 'ACTIVE'",
            (org_id,),
        )
        for admin in admins:
            send_templated.delay(
                template_id="merit_list_published",
                recipient_id=str(admin["id"]),
                recipient_address=admin["email"],
                context={
                    "name": admin["name"],
                    "program": payload.get("program", ""),
                    "batch": payload.get("batch", ""),
                    "total_ranked": payload.get("total_ranked", 0),
                    "total_waitlisted": payload.get("total_waitlisted", 0),
                },
                org_id=org_id,
                channels=["EMAIL"],
            )
    except Exception as exc:
        logger.warning("P13: merit_list_published notification failed: %s", exc)


def on_merit_listed(event: DomainEvent) -> None:
    _send_notification(
        template_id="merit_listed",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "rank": event.payload.get("rank", ""),
            "category": event.payload.get("category", ""),
            "program": event.payload.get("program", ""),
            "batch": event.payload.get("batch", ""),
        },
    )


def on_waitlisted(event: DomainEvent) -> None:
    _send_notification(
        template_id="waitlisted",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "waitlist_position": event.payload.get("waitlist_position", ""),
            "program": event.payload.get("program", ""),
            "batch": event.payload.get("batch", ""),
        },
    )


# ---------------------------------------------------------------------------
# P10 — Payment
# ---------------------------------------------------------------------------

def on_demand_draft_submitted(event: DomainEvent) -> None:
    _send_notification(
        template_id="demand_draft_received",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "dd_number": event.payload.get("dd_number", ""),
            "bank_name": event.payload.get("bank_name", ""),
            "amount": event.payload.get("amount", ""),
        },
    )


def on_payment_verified(event: DomainEvent) -> None:
    _send_notification(
        template_id="payment_verified",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={"amount": event.payload.get("amount", "")},
    )


def on_refund_approved(event: DomainEvent) -> None:
    _send_notification(
        template_id="refund_approved",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "refund_amount": event.payload.get("refund_amount", ""),
            "policy_label": event.payload.get("policy_label", ""),
            "application_id": event.payload.get("application_id", ""),
        },
    )


def on_refund_processed(event: DomainEvent) -> None:
    _send_notification(
        template_id="refund_processed",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "refund_amount": event.payload.get("refund_amount", ""),
            "gateway_refund_id": event.payload.get("gateway_refund_id", ""),
            "application_id": event.payload.get("application_id", ""),
        },
    )


# ---------------------------------------------------------------------------
# P11 — Final Verification
# ---------------------------------------------------------------------------

def on_verification_initiated(event: DomainEvent) -> None:
    _send_notification(
        template_id="verification_initiated",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "verification_mode": event.payload.get("verification_mode", ""),
            "reporting_date": event.payload.get("reporting_date", "TBD"),
            "assigned_officer": event.payload.get("assigned_officer", "Admissions Office"),
            "application_id": event.payload.get("application_id", ""),
        },
    )


def on_verification_cleared(event: DomainEvent) -> None:
    _send_notification(
        template_id="verification_cleared",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={"application_id": event.payload.get("application_id", "")},
    )


def on_verification_cleared_undertaking(event: DomainEvent) -> None:
    _send_notification(
        template_id="verification_cleared_undertaking",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "application_id": event.payload.get("application_id", ""),
            "due_date": event.payload.get("due_date", ""),
        },
    )


def on_verification_rejected(event: DomainEvent) -> None:
    _send_notification(
        template_id="verification_rejected",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "reason": event.payload.get("reason", ""),
            "application_id": event.payload.get("application_id", ""),
        },
    )


# ---------------------------------------------------------------------------
# P12 — Enrollment
# ---------------------------------------------------------------------------

def on_university_email_assigned(event: DomainEvent) -> None:
    _send_notification(
        template_id="university_email_assigned",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "university_email": event.payload.get("university_email", ""),
            "email_portal_url": event.payload.get("email_portal_url", ""),
        },
    )


def on_lms_account_created(event: DomainEvent) -> None:
    _send_notification(
        template_id="lms_account_created",
        applicant_id=event.entity_id,
        org_id=event.org_id,
        context={
            "lms_account_id": event.payload.get("lms_account_id", ""),
            "lms_url": event.payload.get("lms_url", ""),
        },
    )


# ---------------------------------------------------------------------------
# Registration — called once at startup
# ---------------------------------------------------------------------------

def register_all() -> None:
    """Register all M1 event handlers with the DomainEventBus."""
    # Existing (E04-S16)
    register_handler("ApplicantEligible",         on_applicant_eligible)
    register_handler("ApplicantFlaggedForReview",  on_applicant_flagged)
    register_handler("ApplicantRejected",          on_applicant_rejected)
    register_handler("OfferLetterIssued",          on_offer_letter_issued)
    register_handler("StudentEnrolled",            on_student_enrolled)
    register_handler("OfferLetterExpired",         on_offer_expired)
    register_handler("ReviewItemDecided",          on_review_decided)

    # P8 — Merit List
    register_handler("MeritListPublished",         on_merit_list_published)
    register_handler("ApplicantMeritListed",       on_merit_listed)
    register_handler("ApplicantWaitlisted",        on_waitlisted)

    # P9 — Offer Letter
    register_handler("OfferAccepted",              on_offer_accepted)
    register_handler("OfferDeclined",              on_offer_declined)
    register_handler("OfferReminderT3",            on_offer_reminder_t3)
    register_handler("OfferReminderT1",            on_offer_reminder_t1)

    # P10 — Payment
    register_handler("DemandDraftSubmitted",       on_demand_draft_submitted)
    register_handler("PaymentVerified",            on_payment_verified)
    register_handler("RefundApproved",             on_refund_approved)
    register_handler("RefundProcessed",            on_refund_processed)

    # P11 — Verification
    register_handler("VerificationInitiated",      on_verification_initiated)
    register_handler("VerificationCleared",        on_verification_cleared)
    register_handler("VerificationClearedUndertaking", on_verification_cleared_undertaking)
    register_handler("VerificationRejected",       on_verification_rejected)

    # P12 — Enrollment
    register_handler("UniversityEmailAssigned",    on_university_email_assigned)
    register_handler("LMSAccountCreated",          on_lms_account_created)

    # Register templates into in-memory TemplateRegistry
    try:
        from server.admissions.admissions_templates import AdmissionsTemplates
        AdmissionsTemplates.register_all()
    except Exception as exc:
        logger.warning("P13: template registration failed (non-fatal): %s", exc)

    logger.info("E04-S16 + P13: M1 event handlers registered (24 handlers, 35 templates)")
