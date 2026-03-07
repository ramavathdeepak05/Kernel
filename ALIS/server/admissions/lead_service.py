"""
P3 — Lead CRM Service (Stage 1)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 2 (CRM Logic) + Layer 6 (Audit)

Handles the full lead lifecycle before a prospect converts to an applicant:
  - Multi-channel lead capture (web, referral, consultant, walk-in, CSV)
  - CRM state machine: NEW → CONTACTED → INTERESTED → READY_TO_APPLY → CONVERTED
  - Activity logging (calls, emails, notes, status changes)
  - Counsellor assignment and follow-up scheduling
  - Lead → Applicant conversion (creates applicant record atomically)
  - Consultant management and commission tracking
  - Referral code generation and redemption

State Machine:
    NEW → CONTACTED | INTERESTED | NOT_INTERESTED | UNRESPONSIVE | DISQUALIFIED
    CONTACTED → INTERESTED | NOT_INTERESTED | UNRESPONSIVE | DISQUALIFIED
    INTERESTED → READY_TO_APPLY | NOT_INTERESTED | UNRESPONSIVE | DISQUALIFIED
    READY_TO_APPLY → CONVERTED | NOT_INTERESTED | DISQUALIFIED
    CONVERTED → (terminal)
    NOT_INTERESTED | UNRESPONSIVE | DISQUALIFIED → (can re-open via CONTACTED)
"""

from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, PermissionDeniedError
from server.db_service import execute_query, execute_transaction

from .models import (
    ConsultantCreate,
    ConsultantRead,
    LeadActivityCreate,
    LeadActivityRead,
    LeadActivityType,
    LeadConvertRequest,
    LeadCreate,
    LeadRead,
    LeadStatus,
    LeadUpdateRequest,
    ReferralCodeCreate,
    ReferralCodeRead,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed CRM status transitions
# ---------------------------------------------------------------------------
_LEAD_TRANSITIONS: Dict[LeadStatus, set] = {
    LeadStatus.NEW: {
        LeadStatus.CONTACTED, LeadStatus.INTERESTED,
        LeadStatus.NOT_INTERESTED, LeadStatus.UNRESPONSIVE, LeadStatus.DISQUALIFIED,
    },
    LeadStatus.CONTACTED: {
        LeadStatus.INTERESTED, LeadStatus.NOT_INTERESTED,
        LeadStatus.UNRESPONSIVE, LeadStatus.DISQUALIFIED,
    },
    LeadStatus.INTERESTED: {
        LeadStatus.READY_TO_APPLY, LeadStatus.NOT_INTERESTED,
        LeadStatus.UNRESPONSIVE, LeadStatus.DISQUALIFIED,
    },
    LeadStatus.READY_TO_APPLY: {
        LeadStatus.CONVERTED, LeadStatus.NOT_INTERESTED, LeadStatus.DISQUALIFIED,
    },
    # Re-open paths for dormant leads
    LeadStatus.NOT_INTERESTED: {LeadStatus.CONTACTED},
    LeadStatus.UNRESPONSIVE: {LeadStatus.CONTACTED},
    # Terminal / conversion
    LeadStatus.CONVERTED: set(),
    LeadStatus.DISQUALIFIED: set(),
}


# =============================================================================
# LEAD SERVICE
# =============================================================================

class LeadService:
    """Full CRM lead lifecycle management."""

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        request: LeadCreate,
        org_id: str,
        actor_id: str,
    ) -> LeadRead:
        """
        Capture a new lead from any source channel.

        Validates referral code if provided (increments use_count).
        Logs a STATUS_CHANGE activity (NEW).

        Returns:
            LeadRead for the created lead.
        """
        lead_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Validate + consume referral code
        if request.referral_code:
            cls._validate_and_consume_referral_code(request.referral_code, org_id)

        execute_transaction([
            (
                """
                INSERT INTO leads (
                    id, org_id, full_name, email, phone,
                    city, state_region, course_interest, intake_year,
                    source_type, source_detail,
                    utm_source, utm_medium, utm_campaign, utm_term, utm_content,
                    referred_by_user_id, consultant_id,
                    status, metadata, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s::jsonb, %s, %s
                )
                """,
                (
                    lead_id, org_id,
                    request.full_name, request.email, request.phone,
                    request.city, request.state_region,
                    request.course_interest, request.intake_year,
                    request.source_type.value,
                    request.source_detail,
                    request.utm_source, request.utm_medium,
                    request.utm_campaign, request.utm_term, request.utm_content,
                    request.referred_by_user_id,
                    request.consultant_id,
                    LeadStatus.NEW.value,
                    __import__("json").dumps(request.metadata or {}),
                    now, now,
                ),
            )
        ])

        # If from consultant, create a referral record
        if request.consultant_id:
            cls._create_consultant_referral(
                org_id=org_id,
                consultant_id=request.consultant_id,
                lead_id=lead_id,
                referral_code=request.referral_code,
            )

        # Log first activity
        cls._log_activity_internal(
            lead_id=lead_id,
            org_id=org_id,
            activity_type=LeadActivityType.STATUS_CHANGE.value,
            summary=f"Lead created via {request.source_type.value}.",
            actor_id=actor_id,
            metadata={"status": LeadStatus.NEW.value},
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=lead_id,
            org_id=org_id,
            module="M1",
            wizard="Lead Capture",
            success=True,
            metadata={
                "source_type": request.source_type.value,
                "email": request.email,
            },
        )

        logger.info("Lead created: %s [org=%s source=%s]", lead_id, org_id, request.source_type.value)
        return cls.get(lead_id, org_id)

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    @classmethod
    def get(cls, lead_id: str, org_id: str) -> LeadRead:
        rows = execute_query(
            "SELECT * FROM leads WHERE id = %s AND org_id = %s",
            (lead_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Lead '{lead_id}' not found.")
        return LeadRead(**rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        status: Optional[str] = None,
        counsellor_id: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[LeadRead]:
        conditions = ["org_id = %s"]
        params: list = [org_id]

        if status:
            conditions.append("status = %s")
            params.append(status)
        if counsellor_id:
            conditions.append("assigned_counsellor_id = %s")
            params.append(counsellor_id)
        if source_type:
            conditions.append("source_type = %s")
            params.append(source_type)

        where = " AND ".join(conditions)
        params += [limit, offset]

        rows = execute_query(
            f"SELECT * FROM leads WHERE {where} "
            "ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params),
        )
        return [LeadRead(**r) for r in rows]

    # -------------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------------

    @classmethod
    def update(
        cls,
        lead_id: str,
        org_id: str,
        request: LeadUpdateRequest,
        actor_id: str,
    ) -> LeadRead:
        """
        Update CRM fields. Validates status transitions.
        Logs an activity for status changes and notes.
        """
        rows = execute_query(
            "SELECT status FROM leads WHERE id = %s AND org_id = %s",
            (lead_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Lead '{lead_id}' not found.")

        current_status = LeadStatus(rows[0]["status"])
        now = datetime.now(timezone.utc)

        updates: Dict[str, Any] = {"updated_at": now}
        activities = []

        if request.status and request.status != current_status:
            cls._validate_lead_transition(current_status, request.status)
            updates["status"] = request.status.value
            if request.status == LeadStatus.CONTACTED:
                updates["last_contacted_at"] = now
            activities.append({
                "type": LeadActivityType.STATUS_CHANGE.value,
                "summary": f"Status changed: {current_status.value} → {request.status.value}",
                "metadata": {
                    "from": current_status.value,
                    "to": request.status.value,
                },
            })

        if request.assigned_counsellor_id is not None:
            updates["assigned_counsellor_id"] = request.assigned_counsellor_id

        if request.next_followup_at is not None:
            updates["next_followup_at"] = request.next_followup_at

        if request.course_interest is not None:
            updates["course_interest"] = request.course_interest

        if request.intake_year is not None:
            updates["intake_year"] = request.intake_year

        if request.disqualify_reason is not None:
            updates["disqualify_reason"] = request.disqualify_reason

        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            execute_transaction([
                (
                    f"UPDATE leads SET {set_clause} WHERE id = %s AND org_id = %s",
                    (*updates.values(), lead_id, org_id),
                )
            ])

        if request.note:
            activities.append({
                "type": LeadActivityType.NOTE.value,
                "summary": request.note,
                "metadata": {},
            })

        for act in activities:
            cls._log_activity_internal(
                lead_id=lead_id,
                org_id=org_id,
                activity_type=act["type"],
                summary=act["summary"],
                actor_id=actor_id,
                metadata=act["metadata"],
            )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=lead_id,
            org_id=org_id,
            module="M1",
            wizard="Lead CRM",
            success=True,
            metadata={"updates": list(updates.keys())},
        )

        return cls.get(lead_id, org_id)

    # -------------------------------------------------------------------------
    # Activity Log
    # -------------------------------------------------------------------------

    @classmethod
    def log_activity(
        cls,
        request: LeadActivityCreate,
        org_id: str,
        actor_id: str,
    ) -> LeadActivityRead:
        """Log a CRM activity (call, email, note, etc.) against a lead."""
        # Verify lead exists
        rows = execute_query(
            "SELECT id FROM leads WHERE id = %s AND org_id = %s",
            (request.lead_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Lead '{request.lead_id}' not found.")

        activity_id = cls._log_activity_internal(
            lead_id=request.lead_id,
            org_id=org_id,
            activity_type=request.activity_type.value,
            summary=request.summary,
            actor_id=actor_id,
            metadata=request.metadata or {},
        )

        # Update last_contacted_at for outreach activities
        if request.activity_type in (
            LeadActivityType.CALL_LOGGED,
            LeadActivityType.EMAIL_SENT,
            LeadActivityType.SMS_SENT,
            LeadActivityType.WHATSAPP_SENT,
            LeadActivityType.MEETING_SCHEDULED,
        ):
            execute_transaction([
                (
                    "UPDATE leads SET last_contacted_at = %s, updated_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (datetime.now(timezone.utc), datetime.now(timezone.utc),
                     request.lead_id, org_id),
                )
            ])

        row = execute_query(
            "SELECT * FROM lead_activities WHERE id = %s",
            (activity_id,),
        )
        return LeadActivityRead(**row[0])

    @classmethod
    def list_activities(cls, lead_id: str, org_id: str) -> List[LeadActivityRead]:
        """Return all CRM activities for a lead, newest first."""
        rows = execute_query(
            "SELECT * FROM lead_activities WHERE lead_id = %s AND org_id = %s "
            "ORDER BY created_at DESC",
            (lead_id, org_id),
        )
        return [LeadActivityRead(**r) for r in rows]

    # -------------------------------------------------------------------------
    # Convert Lead → Applicant
    # -------------------------------------------------------------------------

    @classmethod
    def convert_to_applicant(
        cls,
        request: LeadConvertRequest,
        org_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Convert a lead into an applicant (READY_TO_APPLY → CONVERTED).

        Creates an applicant record, marks the lead CONVERTED, links them,
        and updates any consultant referral record.

        Returns:
            Dict with lead_id and applicant_id.

        Raises:
            BusinessRuleViolation: If lead not in READY_TO_APPLY state.
        """
        rows = execute_query(
            "SELECT * FROM leads WHERE id = %s AND org_id = %s",
            (request.lead_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Lead '{request.lead_id}' not found.")

        lead = rows[0]
        current_status = LeadStatus(lead["status"])

        if current_status not in (LeadStatus.READY_TO_APPLY, LeadStatus.INTERESTED):
            raise BusinessRuleViolation(
                message=(
                    f"Lead must be in READY_TO_APPLY or INTERESTED status to convert. "
                    f"Current: {current_status.value}"
                ),
                details={"lead_id": request.lead_id, "status": current_status.value},
            )

        now = datetime.now(timezone.utc)
        applicant_id = str(uuid4())

        execute_transaction([
            # Create applicant
            (
                """
                INSERT INTO applicants (
                    id, org_id, name, email, phone,
                    intended_program, source_channel,
                    status, lead_id, metadata, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    applicant_id, org_id,
                    lead["full_name"], lead["email"], lead["phone"],
                    request.intended_program,
                    lead.get("source_type", "WEBSITE"),
                    "APPLIED",
                    request.lead_id,
                    __import__("json").dumps(lead.get("metadata") or {}),
                    now, now,
                ),
            ),
            # Mark lead converted
            (
                """
                UPDATE leads
                SET status = %s,
                    converted_applicant_id = %s,
                    converted_at = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    LeadStatus.CONVERTED.value,
                    applicant_id, now, now,
                    request.lead_id, org_id,
                ),
            ),
            # Link referral if exists
            (
                """
                UPDATE consultant_referrals
                SET applicant_id = %s, updated_at = %s
                WHERE lead_id = %s AND org_id = %s
                """,
                (applicant_id, now, request.lead_id, org_id),
            ),
        ])

        cls._log_activity_internal(
            lead_id=request.lead_id,
            org_id=org_id,
            activity_type=LeadActivityType.STATUS_CHANGE.value,
            summary=f"Lead converted to applicant {applicant_id} for program '{request.intended_program}'.",
            actor_id=actor_id,
            metadata={"applicant_id": applicant_id, "program": request.intended_program},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="lead",
            entity_id=request.lead_id,
            org_id=org_id,
            module="M1",
            wizard="Lead Conversion",
            success=True,
            metadata={"applicant_id": applicant_id, "program": request.intended_program},
        )

        logger.info(
            "Lead %s converted to applicant %s [org=%s]",
            request.lead_id, applicant_id, org_id,
        )
        return {"lead_id": request.lead_id, "applicant_id": applicant_id}

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    @classmethod
    def _validate_lead_transition(
        cls, current: LeadStatus, target: LeadStatus
    ) -> None:
        allowed = _LEAD_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise BusinessRuleViolation(
                message=f"Illegal lead status transition: {current.value} → {target.value}",
                details={"allowed": [s.value for s in allowed]},
            )

    @classmethod
    def _log_activity_internal(
        cls,
        lead_id: str,
        org_id: str,
        activity_type: str,
        summary: str,
        actor_id: str,
        metadata: Dict[str, Any],
    ) -> str:
        activity_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO lead_activities
                    (id, org_id, lead_id, activity_type, summary, actor_id, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    activity_id, org_id, lead_id,
                    activity_type, summary[:1000], actor_id,
                    __import__("json").dumps(metadata),
                    now,
                ),
            )
        ])
        return activity_id

    @classmethod
    def _validate_and_consume_referral_code(cls, code: str, org_id: str) -> None:
        rows = execute_query(
            "SELECT id, use_count, max_uses, expires_at, is_active "
            "FROM referral_codes WHERE code = %s AND org_id = %s",
            (code, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Referral code '{code}' not found.")

        rc = rows[0]
        if not rc["is_active"]:
            raise BusinessRuleViolation(message=f"Referral code '{code}' is inactive.")

        if rc["expires_at"] and rc["expires_at"] < datetime.now(timezone.utc):
            raise BusinessRuleViolation(message=f"Referral code '{code}' has expired.")

        if rc["max_uses"] and rc["use_count"] >= rc["max_uses"]:
            raise BusinessRuleViolation(message=f"Referral code '{code}' has reached its usage limit.")

        execute_transaction([
            (
                "UPDATE referral_codes SET use_count = use_count + 1 WHERE id = %s",
                (rc["id"],),
            )
        ])

    @classmethod
    def _create_consultant_referral(
        cls, org_id: str, consultant_id: str, lead_id: str, referral_code: Optional[str]
    ) -> None:
        referral_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO consultant_referrals
                    (id, org_id, consultant_id, lead_id, referral_code, status, commission_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    referral_id, org_id, consultant_id, lead_id,
                    referral_code, "PENDING", "UNPAID", now,
                ),
            )
        ])


# =============================================================================
# CONSULTANT SERVICE
# =============================================================================

class ConsultantService:
    """CRUD management for third-party education consultants."""

    @classmethod
    def create(
        cls,
        request: ConsultantCreate,
        org_id: str,
        actor_id: str,
    ) -> ConsultantRead:
        consultant_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO consultants (
                    id, org_id, name, company_name, email, phone,
                    city, state_region, status,
                    commission_type, commission_rate, commission_amount,
                    portal_user_id, metadata, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    consultant_id, org_id,
                    request.name, request.company_name,
                    request.email, request.phone,
                    request.city, request.state_region,
                    "ACTIVE",
                    request.commission_type.value,
                    request.commission_rate,
                    request.commission_amount,
                    request.portal_user_id,
                    "{}",
                    now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="consultant",
            entity_id=consultant_id,
            org_id=org_id,
            module="M1",
            wizard="Consultant Management",
            success=True,
            metadata={"name": request.name, "email": request.email},
        )

        return cls.get(consultant_id, org_id)

    @classmethod
    def get(cls, consultant_id: str, org_id: str) -> ConsultantRead:
        rows = execute_query(
            "SELECT * FROM consultants WHERE id = %s AND org_id = %s",
            (consultant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Consultant '{consultant_id}' not found.")
        return ConsultantRead(**rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConsultantRead]:
        conditions = ["org_id = %s"]
        params: list = [org_id]
        if status:
            conditions.append("status = %s")
            params.append(status)
        params += [limit, offset]
        rows = execute_query(
            f"SELECT * FROM consultants WHERE {' AND '.join(conditions)} "
            "ORDER BY name ASC LIMIT %s OFFSET %s",
            tuple(params),
        )
        return [ConsultantRead(**r) for r in rows]

    @classmethod
    def update_status(
        cls,
        consultant_id: str,
        org_id: str,
        new_status: str,
        actor_id: str,
    ) -> ConsultantRead:
        from .models import ConsultantStatus
        if new_status not in {s.value for s in ConsultantStatus}:
            raise BusinessRuleViolation(
                message=f"Invalid consultant status: {new_status}",
                details={"valid": [s.value for s in ConsultantStatus]},
            )
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE consultants SET status = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (new_status, now, consultant_id, org_id),
            )
        ])
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="consultant",
            entity_id=consultant_id,
            org_id=org_id,
            module="M1",
            wizard="Consultant Management",
            success=True,
            metadata={"new_status": new_status},
        )
        return cls.get(consultant_id, org_id)


# =============================================================================
# REFERRAL CODE SERVICE
# =============================================================================

class ReferralCodeService:
    """Generate and manage referral codes for students, staff, and consultants."""

    @classmethod
    def create(
        cls,
        request: ReferralCodeCreate,
        org_id: str,
        actor_id: str,
    ) -> ReferralCodeRead:
        code = cls._generate_unique_code(org_id)
        code_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO referral_codes (
                    id, org_id, code, referrer_type, referrer_id,
                    max_uses, use_count, expires_at, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    code_id, org_id, code,
                    request.referrer_type, request.referrer_id,
                    request.max_uses, 0,
                    request.expires_at,
                    True, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="referral_code",
            entity_id=code_id,
            org_id=org_id,
            module="M1",
            wizard="Referral Code",
            success=True,
            metadata={
                "code": code,
                "referrer_type": request.referrer_type,
                "referrer_id": request.referrer_id,
            },
        )

        return cls.get_by_code(code, org_id)

    @classmethod
    def get_by_code(cls, code: str, org_id: str) -> ReferralCodeRead:
        rows = execute_query(
            "SELECT * FROM referral_codes WHERE code = %s AND org_id = %s",
            (code, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Referral code '{code}' not found.")
        return ReferralCodeRead(**rows[0])

    @classmethod
    def list_by_referrer(
        cls, referrer_id: str, org_id: str
    ) -> List[ReferralCodeRead]:
        rows = execute_query(
            "SELECT * FROM referral_codes WHERE referrer_id = %s AND org_id = %s "
            "ORDER BY created_at DESC",
            (referrer_id, org_id),
        )
        return [ReferralCodeRead(**r) for r in rows]

    @classmethod
    def deactivate(cls, code: str, org_id: str, actor_id: str) -> None:
        execute_transaction([
            (
                "UPDATE referral_codes SET is_active = FALSE "
                "WHERE code = %s AND org_id = %s",
                (code, org_id),
            )
        ])
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="referral_code",
            entity_id=code,
            org_id=org_id,
            module="M1",
            wizard="Referral Code",
            success=True,
            metadata={"code": code, "action": "deactivated"},
        )

    @classmethod
    def _generate_unique_code(cls, org_id: str, length: int = 8) -> str:
        """Generate a unique alphanumeric referral code."""
        chars = string.ascii_uppercase + string.digits
        for _ in range(10):  # max 10 attempts
            code = "".join(random.choices(chars, k=length))
            existing = execute_query(
                "SELECT id FROM referral_codes WHERE code = %s AND org_id = %s",
                (code, org_id),
            )
            if not existing:
                return code
        raise BusinessRuleViolation(message="Failed to generate unique referral code.")
