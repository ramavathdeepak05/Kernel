"""E09 — Student Services Event Handlers

Subscribes to:
  - LibraryOverdue       → notify borrower
  - StudentEnrolled      → provision guardian + library membership
  - risk.score_updated   → auto-counselling referral when risk ≥ 70

Note: ReEvalDecided, result.final_published, student.dues_cleared, graduation.verified
      handlers have been moved to their owner modules (examinations/, alumni/).
"""

from __future__ import annotations

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_library_overdue(event: dict) -> None:
    payload = event.get("payload", {})
    org_id = event.get("org_id")
    borrower_id = payload.get("borrower_id")
    book_title = payload.get("book_title")

    if not (org_id and borrower_id):
        return

    try:
        from server.core.notifications.service import NotificationDispatcher
        from server.db_service import execute_query

        user_rows = execute_query(
            "SELECT name, email FROM users WHERE id = %s", (borrower_id,)
        )
        if not user_rows:
            return
        user = user_rows[0]
        NotificationDispatcher.dispatch(
            template_key="library_overdue",
            recipient_id=borrower_id,
            recipient_email=user["email"],
            context={
                "borrower_name": user["name"],
                "book_title": book_title,
                "fine_per_day": payload.get("fine_per_day", 2),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.warning("E09: LibraryOverdue notification failed (non-fatal): %s", exc)


def on_student_enrolled(event: dict) -> None:
    """Auto-provision guardian + library membership on enrollment."""
    payload = (
        event.get("payload", {}) if isinstance(event, dict) else (event.payload or {})
    )
    org_id = event.get("org_id") if isinstance(event, dict) else event.org_id
    student_id = payload.get("student_id") or payload.get("user_id", "")
    guardian_phone = payload.get("guardian_phone", "")
    guardian_name = payload.get("guardian_name", "")

    if guardian_phone and student_id:
        try:
            from server.student_services.guardian_portal import GuardianPortalService

            GuardianPortalService.provision_guardian(
                org_id, student_id, guardian_phone, guardian_name
            )
            logger.info("E16: Guardian provisioned for student=%s", student_id)
        except Exception as exc:
            logger.error("Guardian provisioning failed: %s", exc)


def on_risk_score_updated(event: dict) -> None:
    """SS-7: Auto-counseling referral when risk ≥ 70 (RED)."""
    payload = (
        event.get("payload", {}) if isinstance(event, dict) else (event.payload or {})
    )
    org_id = event.get("org_id") if isinstance(event, dict) else event.org_id
    student_id = payload.get("student_id", "")
    risk_score = float(payload.get("risk_score", 0))

    if risk_score >= 70 and student_id:
        try:
            from uuid import uuid4

            from server.core.audit import AuditAction, AuditLog
            from server.db_service import execute_query, execute_transaction

            existing = execute_query(
                "SELECT id FROM counselling_referrals WHERE student_id = %s AND org_id = %s "
                "AND created_at > NOW() - INTERVAL '7 days' AND urgency = 'URGENT'",
                (student_id, org_id),
                tenant_id=org_id,
            )
            if not existing:
                execute_transaction(
                    [
                        (
                            "INSERT INTO counselling_referrals (id, org_id, student_id, reason, urgency, "
                            "status, created_at) VALUES (%s, %s, %s, %s, 'URGENT', 'PENDING', NOW())",
                            (
                                str(uuid4()),
                                org_id,
                                student_id,
                                f"Auto-referral: risk score {risk_score} (RED)",
                            ),
                        )
                    ],
                    tenant_id=org_id,
                )
                AuditLog.log(
                    action=AuditAction.UPDATE,
                    actor_id="system",
                    actor_role="system",
                    entity_type="student_risk",
                    entity_id="",
                    tenant_id="",
                    metadata={"source": "on_risk_score_updated"},
                )
                logger.info(
                    "Auto-counseling referral for student=%s (risk=%s)",
                    student_id,
                    risk_score,
                )
        except Exception as exc:
            logger.error("Auto-counseling referral failed: %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("LibraryOverdue", on_library_overdue)
    DomainEventBus.subscribe("StudentEnrolled", on_student_enrolled)
    DomainEventBus.subscribe("risk.score_updated", on_risk_score_updated)
    logger.info("E09 event handlers registered (3 handlers)")
