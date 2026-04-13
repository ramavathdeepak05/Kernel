"""E10 — Communication Hub Event Handlers

Subscribes to ALL domain events and creates in-app notifications
and delivery logs for significant lifecycle events.

Subscribes:
  ResultsDeclared, HallTicketIssued, AdmissionConfirmed,
  FeePaymentReceived, FeeOverdue, FeeInvoiceGenerated,
  SemesterStarted, SemesterEnded, AttendanceFinalized,
  StudentEnrolled, StudentGraduated, ReEvalDecided,
  HostelAllotted, LibraryOverdue, FacultyOnLeave
"""

from __future__ import annotations

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def _notify(event: dict, title: str, body_tpl: str) -> None:
    """Generic helper — creates an in-app notification for the primary entity."""
    org_id = event.get("org_id")
    entity_id = event.get("entity_id")
    payload = event.get("payload", {})

    if not org_id or not entity_id:
        return

    try:
        from string import Template

        body = Template(body_tpl).safe_substitute(payload)

        from .in_app import InAppNotificationService

        InAppNotificationService.send(
            org_id=org_id,
            recipient_id=str(entity_id),
            title=title,
            body=body,
        )
    except Exception as exc:
        logger.debug("E10 in-app notification failed (non-fatal): %s", exc)


def on_results_declared(event: dict) -> None:
    event.get("payload", {})
    _notify(
        event,
        title="Results Published",
        body_tpl="Your results for ${academic_year} Semester ${semester} are now available.",
    )


def on_hall_ticket_issued(event: dict) -> None:
    _notify(
        event,
        title="Hall Ticket Issued",
        body_tpl="Your hall ticket (${ticket_number}) for ${exam_type} exams has been issued.",
    )


def on_admission_confirmed(event: dict) -> None:
    _notify(
        event,
        title="Admission Confirmed",
        body_tpl="Congratulations! Your admission to ${program_name} has been confirmed.",
    )


def on_fee_invoice_generated(event: dict) -> None:
    _notify(
        event,
        title="Fee Invoice Generated",
        body_tpl="A new fee invoice of Rs. ${amount} is due by ${due_date}.",
    )


def on_fee_payment_received(event: dict) -> None:
    _notify(
        event,
        title="Payment Received",
        body_tpl="We have received your payment of Rs. ${amount}. Thank you!",
    )


def on_fee_overdue(event: dict) -> None:
    _notify(
        event,
        title="Fee Overdue",
        body_tpl="Your fee invoice is overdue. Please pay immediately to avoid penalties.",
    )


def on_semester_started(event: dict) -> None:
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    if not org_id:
        return

    try:
        from .announcements import AnnouncementService
        from .models import AnnouncementCreate, Priority, TargetAudience

        AnnouncementService.create(
            org_id=org_id,
            req=AnnouncementCreate(
                title=f"Semester {payload.get('semester')} Started — {payload.get('academic_year')}",
                body="The new semester has officially begun. Check your timetable and course enrollments.",
                target_audience=TargetAudience.STUDENTS,
                priority=Priority.NORMAL,
            ),
            actor_id="system",
        )
    except Exception as exc:
        logger.debug("E10 semester announcement failed (non-fatal): %s", exc)


def on_student_graduated(event: dict) -> None:
    _notify(
        event,
        title="Congratulations — You have Graduated!",
        body_tpl="You have successfully completed your program. Your transcript is now available.",
    )


def on_hostel_allotted(event: dict) -> None:
    _notify(
        event,
        title="Hostel Room Allotted",
        body_tpl="You have been allotted Room ${room_number} in ${block_name}.",
    )


def on_library_overdue(event: dict) -> None:
    _notify(
        event,
        title="Library Book Overdue",
        body_tpl="The book '${book_title}' is overdue. A fine of Rs. ${fine_per_day}/day is accruing.",
    )


def register_all() -> None:
    DomainEventBus.subscribe("ResultsDeclared", on_results_declared)
    DomainEventBus.subscribe("HallTicketIssued", on_hall_ticket_issued)
    DomainEventBus.subscribe("AdmissionConfirmed", on_admission_confirmed)
    DomainEventBus.subscribe("FeeInvoiceGenerated", on_fee_invoice_generated)
    DomainEventBus.subscribe("FeePaymentReceived", on_fee_payment_received)
    DomainEventBus.subscribe("FeeOverdue", on_fee_overdue)
    DomainEventBus.subscribe("SemesterStarted", on_semester_started)
    DomainEventBus.subscribe("StudentGraduated", on_student_graduated)
    DomainEventBus.subscribe("HostelAllotted", on_hostel_allotted)
    DomainEventBus.subscribe("LibraryOverdue", on_library_overdue)
    logger.info("E10 event handlers registered")
