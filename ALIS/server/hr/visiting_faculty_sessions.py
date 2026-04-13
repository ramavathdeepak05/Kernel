"""EC-HR-01 — Visiting Faculty Session Billing

Visiting/contract faculty are paid per delivered session.
This service manages session tracking, OTP confirmation, and payroll input generation.

Flow:
  1. Timetable creates SCHEDULED entries for upcoming sessions.
  2. AI sends OTP via SMS to faculty at session start time (Celery Beat task).
  3. Faculty confirms OTP → session marked DELIVERED + faculty_confirmed = TRUE.
  4. Unconfirmed sessions after 30 min → flagged for HOD review.
  5. On payroll cut-off (20th): HR Officer runs generate_payroll_input() → FM-5 picks up.

Only sessions where faculty_confirmed=TRUE AND status='DELIVERED' are payable.
"""

from __future__ import annotations

import hashlib
import logging
import random
import string
import uuid
from datetime import date

from pydantic import BaseModel, field_validator
from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    faculty_id: str
    session_date: date
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    session_type: str = "lecture"
    timetable_slot_id: str | None = None
    rate_per_session: float
    status: str = "SCHEDULED"

    @field_validator("session_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"lecture", "tutorial", "lab", "other"}
        if v not in allowed:
            raise ValueError(f"session_type must be one of {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"SCHEDULED", "DELIVERED", "CANCELLED", "UNSCHEDULED_ADDED"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class SessionOTPConfirm(BaseModel):
    otp: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VisitingFacultySessionService:
    @classmethod
    def create_session(
        cls,
        org_id: str,
        req: SessionCreate,
        actor_id: str,
    ) -> dict:
        """Create a session log entry (usually called from timetable or manually by HR)."""
        # Validate faculty is visiting/contract type
        staff = execute_query(
            """SELECT id, employment_type
               FROM staff_profiles
               WHERE id = %s AND org_id = %s""",
            (req.faculty_id, org_id),
        )
        if not staff:
            raise NotFoundError(f"Staff profile {req.faculty_id} not found")

        # Rate must be positive
        if req.rate_per_session <= 0:
            raise BusinessRuleViolation("rate_per_session must be positive")

        sid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO visiting_faculty_session_log
                (id, org_id, faculty_id, timetable_slot_id, session_date,
                 start_time, end_time, session_type, status, rate_per_session)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                    (
                        sid,
                        org_id,
                        req.faculty_id,
                        req.timetable_slot_id,
                        req.session_date,
                        req.start_time,
                        req.end_time,
                        req.session_type,
                        req.status,
                        req.rate_per_session,
                    ),
                )
            ]
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.CREATE,
            resource_type="visiting_faculty_session",
            resource_id=sid,
            detail={
                "faculty_id": req.faculty_id,
                "session_date": str(req.session_date),
            },
        )
        return cls.get(org_id, sid)

    @classmethod
    def get(cls, org_id: str, session_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM visiting_faculty_session_log WHERE id = %s AND org_id = %s",
            (session_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Session {session_id} not found")
        return dict(rows[0])

    @classmethod
    def list_sessions(
        cls,
        org_id: str,
        faculty_id: str,
        month: date | None = None,
        payable_only: bool = False,
    ) -> list[dict]:
        sql = """
            SELECT *
            FROM visiting_faculty_session_log
            WHERE org_id = %s AND faculty_id = %s
        """
        params: list = [org_id, faculty_id]

        if month:
            sql += (
                " AND DATE_TRUNC('month', session_date) = DATE_TRUNC('month', %s::date)"
            )
            params.append(str(month))

        if payable_only:
            sql += " AND faculty_confirmed = TRUE AND status = 'DELIVERED'"

        sql += " ORDER BY session_date, start_time"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def generate_otp(cls, org_id: str, session_id: str) -> str:
        """Generate a 6-digit OTP for faculty confirmation and store its hash.

        Returns the plain OTP (to be sent via SMS — not stored).
        """
        otp = "".join(random.choices(string.digits, k=6))
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()

        session = cls.get(org_id, session_id)
        if session["status"] not in ("SCHEDULED", "UNSCHEDULED_ADDED"):
            raise BusinessRuleViolation(
                f"Session is {session['status']} — OTP only valid for SCHEDULED sessions"
            )

        execute_transaction(
            [
                (
                    """UPDATE visiting_faculty_session_log
               SET faculty_otp_hash = %s, updated_at = NOW()
               WHERE id = %s AND org_id = %s""",
                    (otp_hash, session_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="generate_otp",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "generate_otp"},
        )

        logger.info(
            "OTP generated for session=%s faculty=%s", session_id, session["faculty_id"]
        )
        return otp  # caller sends this via SMS

    @classmethod
    def confirm_session(
        cls,
        org_id: str,
        session_id: str,
        req: SessionOTPConfirm,
        actor_id: str,
    ) -> dict:
        """Faculty confirms session delivery by providing the OTP."""
        session = cls.get(org_id, session_id)

        if session["faculty_confirmed"]:
            raise BusinessRuleViolation("Session already confirmed")

        if not session.get("faculty_otp_hash"):
            raise BusinessRuleViolation("No OTP generated for this session")

        provided_hash = hashlib.sha256(req.otp.encode()).hexdigest()
        if provided_hash != session["faculty_otp_hash"]:
            raise BusinessRuleViolation("Invalid OTP")

        execute_transaction(
            [
                (
                    """UPDATE visiting_faculty_session_log
               SET faculty_confirmed = TRUE,
                   confirmed_at = NOW(),
                   status = 'DELIVERED',
                   updated_at = NOW()
               WHERE id = %s AND org_id = %s""",
                    (session_id, org_id),
                )
            ]
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.UPDATE,
            resource_type="visiting_faculty_session",
            resource_id=session_id,
            detail={"confirmed": True, "faculty_id": session["faculty_id"]},
        )

        logger.info(
            "Session confirmed: id=%s faculty=%s date=%s",
            session_id,
            session["faculty_id"],
            session["session_date"],
        )
        return cls.get(org_id, session_id)

    @classmethod
    def hod_verify_unscheduled(
        cls,
        org_id: str,
        session_id: str,
        actor_id: str,
    ) -> dict:
        """HOD verifies an UNSCHEDULED_ADDED session before it becomes payable."""
        session = cls.get(org_id, session_id)
        if session["status"] != "UNSCHEDULED_ADDED":
            raise BusinessRuleViolation(
                "HOD verification only applies to UNSCHEDULED_ADDED sessions"
            )

        execute_transaction(
            [
                (
                    """UPDATE visiting_faculty_session_log
               SET hod_verified = TRUE,
                   hod_verified_at = NOW(),
                   hod_verified_by = %s,
                   updated_at = NOW()
               WHERE id = %s AND org_id = %s""",
                    (actor_id, session_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="hod_verify_unscheduled",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "hod_verify_unscheduled"},
        )

        return cls.get(org_id, session_id)

    @classmethod
    def cancel_session(
        cls,
        org_id: str,
        session_id: str,
        actor_id: str,
    ) -> dict:
        """Mark a session as CANCELLED (e.g. from recalibration / campus event)."""
        session = cls.get(org_id, session_id)
        if session["faculty_confirmed"]:
            raise BusinessRuleViolation(
                "Cannot cancel an already-confirmed session. Create a reversal entry instead."
            )

        execute_transaction(
            [
                (
                    """UPDATE visiting_faculty_session_log
               SET status = 'CANCELLED', updated_at = NOW()
               WHERE id = %s AND org_id = %s""",
                    (session_id, org_id),
                )
            ]
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.UPDATE,
            resource_type="visiting_faculty_session",
            resource_id=session_id,
            detail={"status": "CANCELLED"},
        )
        return cls.get(org_id, session_id)

    @classmethod
    def generate_payroll_input(
        cls,
        org_id: str,
        faculty_id: str,
        payroll_month: date,
        actor_id: str,
    ) -> dict:
        """Compute payable amount for visiting faculty for a given month.

        This is the ONLY input to FM-5 for visiting faculty — timetable-scheduled
        count is never used directly. Only payable sessions count.

        Returns payroll input summary and marks sessions as included_in_payroll=TRUE.
        """
        # Query payable sessions (faculty_confirmed=TRUE AND status='DELIVERED')
        payable_rows = execute_query(
            """
            SELECT id, session_date, session_type, start_time, end_time, rate_per_session
            FROM visiting_faculty_session_log
            WHERE org_id = %s
              AND faculty_id = %s
              AND DATE_TRUNC('month', session_date) = DATE_TRUNC('month', %s::date)
              AND faculty_confirmed = TRUE
              AND status = 'DELIVERED'
              AND included_in_payroll = FALSE
            ORDER BY session_date, start_time
            """,
            (org_id, faculty_id, str(payroll_month)),
        )

        total_sessions = len(payable_rows)
        payable_amount = sum(float(r["rate_per_session"]) for r in payable_rows)
        session_ids = [str(r["id"]) for r in payable_rows]

        if session_ids:
            placeholders = ", ".join(["%s"] * len(session_ids))
            execute_transaction(
                [
                    (
                        f"""UPDATE visiting_faculty_session_log  # noqa: S608
                    SET included_in_payroll = TRUE, payroll_month = %s
                    WHERE id IN ({placeholders}) AND org_id = %s""",
                        (str(payroll_month), *session_ids, org_id),
                    )
                ]
            )

        # Emit domain event for FM-5
        DomainEventBus.publish(
            DomainEvent(
                event_type="payroll.visiting_faculty_inputs_ready",
                org_id=org_id,
                payload={
                    "faculty_id": faculty_id,
                    "payroll_month": str(payroll_month),
                    "total_sessions": total_sessions,
                    "payable_amount": payable_amount,
                    "session_ids": session_ids,
                },
            )
        )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.UPDATED,
            resource_type="visiting_faculty_payroll",
            resource_id=faculty_id,
            detail={
                "payroll_month": str(payroll_month),
                "total_sessions": total_sessions,
                "payable_amount": payable_amount,
            },
        )

        logger.info(
            "Payroll input: faculty=%s month=%s sessions=%d amount=%.2f",
            faculty_id,
            payroll_month,
            total_sessions,
            payable_amount,
        )

        return {
            "faculty_id": faculty_id,
            "payroll_month": str(payroll_month),
            "total_sessions": total_sessions,
            "payable_amount": round(payable_amount, 2),
            "session_breakdown": [
                {
                    "id": str(r["id"]),
                    "date": str(r["session_date"]),
                    "type": r["session_type"],
                    "rate": float(r["rate_per_session"]),
                }
                for r in payable_rows
            ],
        }
