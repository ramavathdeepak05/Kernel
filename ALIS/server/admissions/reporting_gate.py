"""EC-ADM-03 — Ghost Withdrawal / Physical Reporting Gate

Adds a REPORTING_PENDING state between SEAT_CONFIRMED and ENROLLED.
Students who fail to physically report to campus within the SLA window
have their seat forfeited and the next waitlist candidate (same category/quota)
is notified.

SLA and reminder schedule: all values from policy_engine — never literals.

Key policy keys
───────────────
admissions.reporting_gate_sla_days     default 5 (forfeiture deadline)
admissions.reporting_gate_reminder_1   default 1 (day 1 reminder)
admissions.reporting_gate_reminder_2   default 2 (day 2: second + parent)
admissions.reporting_gate_reminder_3   default 3 (day 3: warning + 48h deadline)

Feature flag
────────────
admissions.biometric_reporting_gate — enables biometric/QR check-in
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.feature_flags import feature_flags
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State values
# ---------------------------------------------------------------------------
STATE_SEAT_CONFIRMED = "SEAT_CONFIRMED"
STATE_REPORTING_PENDING = "REPORTING_PENDING"
STATE_ENROLLED = "ENROLLED"
STATE_FORFEITED = "FORFEITED"


class ReportingGateService:
    # ------------------------------------------------------------------
    # Transition to REPORTING_PENDING after seat confirmation
    # ------------------------------------------------------------------

    @classmethod
    def enter_reporting_pending(
        cls,
        org_id: str,
        application_id: str,
        actor_id: str,
    ) -> dict:
        """Transition applicant from SEAT_CONFIRMED → REPORTING_PENDING.

        Records the absolute SLA deadline (never relative sleep).
        """
        rows = execute_query(
            "SELECT id, status, category, quota FROM applicants WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Application {application_id} not found")

        applicant = rows[0]
        if applicant["status"] != STATE_SEAT_CONFIRMED:
            raise BusinessRuleViolation(
                f"Reporting gate can only be entered from SEAT_CONFIRMED "
                f"(current: {applicant['status']})"
            )

        sla_days = int(
            policy_engine.get_value("admissions.reporting_gate_sla_days", org_id, 5)
        )

        # Absolute deadline stored in DB — SLA timer uses this, never timedelta sleep
        from datetime import timedelta

        deadline = datetime.now(timezone.utc) + timedelta(days=sla_days)

        execute_transaction(
            [
                (
                    """
            UPDATE applicants
            SET status = %s, reporting_deadline = %s, updated_at = NOW()
            WHERE id = %s AND org_id = %s
            """,
                    (STATE_REPORTING_PENDING, deadline, application_id, org_id),
                ),
                (
                    """
            INSERT INTO reporting_gate_log
                (id, org_id, application_id, reported_at, method, actor_id)
            VALUES (%s, %s, %s, NULL, 'PENDING', %s)
            """,
                    (str(uuid.uuid4()), org_id, application_id, actor_id),
                ),
            ]
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="application",
            resource_id=application_id,
            detail={
                "status": STATE_REPORTING_PENDING,
                "deadline": deadline.isoformat(),
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.reporting_pending",
                org_id=org_id,
                payload={
                    "application_id": application_id,
                    "deadline": deadline.isoformat(),
                    "sla_days": sla_days,
                },
            )
        )

        return {
            "status": STATE_REPORTING_PENDING,
            "reporting_deadline": deadline.isoformat(),
        }

    # ------------------------------------------------------------------
    # Physical report-in (marks attendance on Reporting Day)
    # ------------------------------------------------------------------

    @classmethod
    def report_in(
        cls,
        org_id: str,
        application_id: str,
        method: str,  # WALK_IN | BIOMETRIC | QR_SCAN
        actor_id: str,
        biometric_verified: bool = False,
    ) -> dict:
        """Record physical reporting. Advances state to ENROLLED."""
        if feature_flags.is_enabled("admissions.biometric_reporting_gate", org_id):
            if method == "BIOMETRIC" and not biometric_verified:
                raise BusinessRuleViolation(
                    "Biometric verification required and not confirmed"
                )

        rows = execute_query(
            "SELECT id, status FROM applicants WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Application {application_id} not found")

        if rows[0]["status"] != STATE_REPORTING_PENDING:
            raise BusinessRuleViolation(
                f"Report-in only valid in REPORTING_PENDING state (current: {rows[0]['status']})"
            )

        execute_transaction(
            [
                (
                    """
            UPDATE applicants
            SET status = %s, updated_at = NOW()
            WHERE id = %s AND org_id = %s
            """,
                    (STATE_ENROLLED, application_id, org_id),
                ),
                (
                    """
            UPDATE reporting_gate_log
            SET reported_at = NOW(), method = %s
            WHERE application_id = %s AND org_id = %s AND reported_at IS NULL
            """,
                    (method, application_id, org_id),
                ),
            ]
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="application",
            resource_id=application_id,
            detail={"status": STATE_ENROLLED, "method": method},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.reported_in",
                org_id=org_id,
                payload={"application_id": application_id, "method": method},
            )
        )

        return {"status": STATE_ENROLLED, "reported_via": method}

    # ------------------------------------------------------------------
    # Daily deadline check (Celery Beat task)
    # ------------------------------------------------------------------

    @classmethod
    def check_reporting_deadlines(cls) -> None:
        """Called daily by Celery Beat.

        - Sends reminders (Day 1, Day 2, Day 3) per policy schedule
        - Forfeits seats past the SLA deadline
        """
        from datetime import timedelta

        # Find all orgs with REPORTING_PENDING applicants
        orgs = execute_query(
            """
            SELECT DISTINCT org_id FROM applicants WHERE status = 'REPORTING_PENDING'
        """,
            (),
        )

        for org_row in orgs:
            org_id = org_row["org_id"]
            sla_days = int(
                policy_engine.get_value("admissions.reporting_gate_sla_days", org_id, 5)
            )
            r1 = int(
                policy_engine.get_value(
                    "admissions.reporting_gate_reminder_1", org_id, 1
                )
            )
            r2 = int(
                policy_engine.get_value(
                    "admissions.reporting_gate_reminder_2", org_id, 2
                )
            )
            r3 = int(
                policy_engine.get_value(
                    "admissions.reporting_gate_reminder_3", org_id, 3
                )
            )

            now = datetime.now(timezone.utc)

            applicants = execute_query(
                """
                SELECT id, reporting_deadline, category, quota, program_id
                FROM applicants
                WHERE org_id = %s AND status = 'REPORTING_PENDING'
            """,
                (org_id,),
            )

            for app in applicants:
                app_id = str(app["id"])
                deadline = app["reporting_deadline"]
                if not deadline:
                    continue

                if isinstance(deadline, str):
                    from datetime import datetime as dt

                    deadline = dt.fromisoformat(deadline)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)

                days_elapsed = (now - (deadline - timedelta(days=sla_days))).days

                if now >= deadline:
                    # Forfeit seat
                    cls._forfeit_seat(
                        org_id,
                        app_id,
                        str(app.get("category", "GENERAL")),
                        str(app.get("quota", "GENERAL")),
                    )
                elif days_elapsed >= r3:
                    cls._send_reminder(
                        org_id, app_id, "DAY_3_FORFEITURE_WARNING", deadline
                    )
                elif days_elapsed >= r2:
                    cls._send_reminder(
                        org_id, app_id, "DAY_2_PARENT_REMINDER", deadline
                    )
                elif days_elapsed >= r1:
                    cls._send_reminder(org_id, app_id, "DAY_1_REMINDER", deadline)

    @classmethod
    def _forfeit_seat(
        cls, org_id: str, application_id: str, category: str, quota: str
    ) -> None:
        execute_transaction(
            [
                (
                    """
            UPDATE applicants
            SET status = 'FORFEITED', updated_at = NOW()
            WHERE id = %s AND org_id = %s AND status = 'REPORTING_PENDING'
        """,
                    (application_id, org_id),
                )
            ]
        )

        rows = execute_query(
            "SELECT program_id, intake_year FROM applicants WHERE id = %s",
            (application_id,),
        )
        if not rows:
            return

        program_id = str(rows[0].get("program_id") or "")
        intake_year = int(rows[0].get("intake_year") or 0)

        AuditLog.log(
            org_id=org_id,
            actor_id="system",
            action=AuditAction.UPDATED,
            resource_type="application",
            resource_id=application_id,
            detail={"status": "FORFEITED", "reason": "reporting_gate_sla_exceeded"},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.seat_forfeited",
                org_id=org_id,
                payload={
                    "application_id": application_id,
                    "category": category,
                    "quota": quota,
                    "program_id": program_id,
                    "intake_year": intake_year,
                },
            )
        )

    @classmethod
    def _send_reminder(
        cls, org_id: str, application_id: str, template_key: str, deadline: datetime
    ) -> None:
        DomainEventBus.publish(
            DomainEvent(
                event_type="notification.send",
                org_id=org_id,
                payload={
                    "template_key": template_key,
                    "application_id": application_id,
                    "deadline": deadline.isoformat(),
                },
            )
        )
