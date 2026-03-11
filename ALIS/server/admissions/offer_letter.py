"""
P9 — Offer Letter v2 (Stage 7)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 3 (State Machine) + Layer 4 (Locks) + Layer 6 (Audit)
ENTITY: OfferLetter

Manages the full offer lifecycle:
  - Generate:  PDF letter with acceptance deadline + fee structure + conditions
  - Accept:    Applicant formally accepts → OFFER_ACCEPTED → SEAT_CONFIRMED
  - Decline:   Applicant declines → OFFER_DECLINED (triggers waitlist cascade)
  - Revoke:    Staff withdraws offer → CANCELLED (with mandatory reason)
  - Deliver:   Track email delivery / open events
  - Expire:    Batch-expire PENDING offers past their deadline
  - Remind:    Flag T-3/T-1 day reminders

State machine transitions owned here:
    ELIGIBLE | MERIT_LISTED → generate → OFFER_ISSUED
    OFFER_ISSUED → accept   → OFFER_ACCEPTED → SEAT_CONFIRMED
    OFFER_ISSUED → decline  → OFFER_DECLINED
    OFFER_ISSUED → revoke   → CANCELLED
    OFFER_ISSUED → expire   → CANCELLED  (scheduled, not staff-triggered)

Immutability:
    PDFs are generated once; re-generate returns the existing letter.
    Accepted offers cannot be revoked without OVERRIDE_APPROVE permission.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import textwrap
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, GlobalLockViolationError
from server.core.state_registry import StudentState
from server.db_service import execute_query, execute_transaction
from server.fs_service import FileStorageService

from .document_verification import DocumentVerificationService
from .service import ApplicantService
from .models import (
    OfferLetterGenerateRequest,
    OfferLetterRead,
    OfferAcceptRequest,
    OfferDeclineRequest,
    OfferRevokeRequest,
)

logger = logging.getLogger(__name__)

# Allowed pre-offer statuses (either direct ELIGIBLE or ranked MERIT_LISTED)
_PRE_OFFER_STATUSES = {
    StudentState.ELIGIBLE.value,
    "ELIGIBLE",
    StudentState.MERIT_LISTED.value,
    "MERIT_LISTED",
}

_ACCEPTANCE_STATUSES = {"PENDING", "ACCEPTED", "DECLINED", "EXPIRED"}
_DELIVERY_STATUSES = {"PENDING", "SENT", "OPENED", "BOUNCED"}


class OfferLetterService:
    """Full offer letter lifecycle — generate, accept, decline, revoke, expire."""

    # -------------------------------------------------------------------------
    # Generate
    # -------------------------------------------------------------------------

    @classmethod
    def generate(
        cls,
        request: OfferLetterGenerateRequest,
        org_id: str,
        actor_id: str,
    ) -> OfferLetterRead:
        """
        Generate a PDF offer letter for an eligible applicant.

        Idempotent — if a valid offer already exists, returns it unchanged.
        On success, transitions applicant → OFFER_ISSUED.

        Raises:
            BusinessRuleViolation: Applicant not found or not ELIGIBLE/MERIT_LISTED.
            GlobalLockViolationError: Required documents not all verified.
        """
        # --- Idempotency: return existing valid offer ---
        existing = execute_query(
            "SELECT * FROM offer_letters "
            "WHERE applicant_id = %s AND org_id = %s AND is_valid = TRUE LIMIT 1",
            (request.applicant_id, org_id),
        )
        if existing:
            logger.info(
                "P9: Returning existing offer letter [id=%s, applicant=%s]",
                existing[0]["id"], request.applicant_id,
            )
            return cls._row_to_read(existing[0])

        # --- Pre-condition: ELIGIBLE or MERIT_LISTED ---
        rows = execute_query(
            "SELECT name, email, status FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        applicant = rows[0]
        if applicant["status"] not in _PRE_OFFER_STATUSES:
            raise BusinessRuleViolation(
                message=(
                    f"Offer letters require ELIGIBLE or MERIT_LISTED status — "
                    f"current status: '{applicant['status']}'."
                ),
                details={"status": applicant["status"]},
            )

        # --- Layer 4: Required docs must be verified ---
        if not DocumentVerificationService.all_required_docs_verified(
            request.applicant_id, org_id
        ):
            raise GlobalLockViolationError(
                violations=[
                    "Required documents are not all verified. "
                    "Offer letter generation is blocked."
                ]
            )

        # --- Generate PDF ---
        pdf_bytes = cls._render_pdf(
            applicant_name=applicant["name"],
            applicant_email=applicant["email"],
            program=request.program_name,
            academic_year=request.academic_year,
            template_version=request.template_version,
            fee_structure=request.fee_structure,
            conditions=request.conditions,
            acceptance_deadline_days=request.acceptance_deadline_days,
        )
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # --- Persist PDF to MinIO ---
        fs = FileStorageService()
        file_meta = fs.upload_file(
            file_content=pdf_bytes,
            filename=f"offer_{request.applicant_id}_{request.academic_year}.pdf",
            owner_id=actor_id,
            context={"role": "staff", "entity_type": "offer_letter",
                     "entity_id": request.applicant_id},
        )
        file_path = (
            str(file_meta.get_version().storage_path)
            if file_meta.get_version() else
            f"offer_{request.applicant_id}_{request.academic_year}.pdf"
        )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=request.acceptance_deadline_days)
        letter_id = str(uuid4())

        execute_transaction([
            (
                """
                INSERT INTO offer_letters (
                    id, org_id, applicant_id, program_name, academic_year,
                    template_version, content_hash, pdf_path, issued_at, is_valid,
                    expires_at, acceptance_status, delivery_status,
                    fee_structure, merit_list_entry_id,
                    t3_reminder_sent, t1_reminder_sent
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                """,
                (
                    letter_id, org_id,
                    request.applicant_id,
                    request.program_name,
                    request.academic_year,
                    request.template_version,
                    content_hash,
                    file_path,
                    now,
                    True,
                    expires_at,
                    "PENDING",
                    "PENDING",
                    json.dumps(request.fee_structure),
                    request.merit_list_entry_id,
                    False,
                    False,
                ),
            )
        ])

        # --- Transition state: → OFFER_ISSUED ---
        ApplicantService.transition_state(
            applicant_id=request.applicant_id,
            org_id=org_id,
            to_state=StudentState.OFFER_ISSUED,
            actor_id=actor_id,
            reason=f"Offer letter issued for {request.program_name} ({request.academic_year})",
            metadata={
                "letter_id": letter_id,
                "expires_at": expires_at.isoformat(),
                "merit_list_entry_id": request.merit_list_entry_id,
            },
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="offer_letter",
            entity_id=letter_id,
            org_id=org_id,
            module="M1",
            wizard="Offer Letter v2",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "program": request.program_name,
                "academic_year": request.academic_year,
                "expires_at": expires_at.isoformat(),
                "content_hash": content_hash,
            },
        )

        cls._notify_offer_issued(
            applicant_email=applicant["email"],
            applicant_name=applicant["name"],
            letter_id=letter_id,
            expires_at=expires_at,
            org_id=org_id,
        )

        logger.info(
            "P9: Offer letter generated [id=%s, applicant=%s, expires=%s]",
            letter_id, request.applicant_id, expires_at.date(),
        )

        return cls.get(letter_id, org_id)

    # -------------------------------------------------------------------------
    # Accept
    # -------------------------------------------------------------------------

    @classmethod
    def accept(
        cls,
        letter_id: str,
        request: OfferAcceptRequest,
        org_id: str,
        actor_id: str,
    ) -> OfferLetterRead:
        """
        Applicant formally accepts their offer.

        Transitions:
            OFFER_ISSUED → OFFER_ACCEPTED → SEAT_CONFIRMED
        Updates:
            offer_letters.acceptance_status = ACCEPTED
            merit_list_entries.status = ACCEPTED (if linked)

        Raises:
            BusinessRuleViolation: Letter not found, already actioned, or expired.
        """
        letter = cls._require_letter(letter_id, org_id)

        if letter["acceptance_status"] != "PENDING":
            raise BusinessRuleViolation(
                message=(
                    f"Offer '{letter_id}' cannot be accepted — "
                    f"current status: '{letter['acceptance_status']}'."
                ),
                details={"acceptance_status": letter["acceptance_status"]},
            )

        if not letter["is_valid"]:
            raise BusinessRuleViolation(message=f"Offer '{letter_id}' is no longer valid.")

        now = datetime.now(timezone.utc)

        # Check expiry
        if letter.get("expires_at") and now > letter["expires_at"]:
            # Auto-expire before rejecting
            cls._do_expire(letter_id, letter["applicant_id"], org_id, actor_id)
            raise BusinessRuleViolation(
                message=f"Offer '{letter_id}' has expired. Cannot accept.",
                details={"expired_at": letter["expires_at"].isoformat()},
            )

        execute_transaction([
            (
                "UPDATE offer_letters SET acceptance_status = %s, accepted_at = %s, "
                "digital_signature_ref = %s WHERE id = %s AND org_id = %s",
                ("ACCEPTED", now, request.digital_signature_ref, letter_id, org_id),
            )
        ])

        # Update merit list entry if linked
        if letter.get("merit_list_entry_id"):
            execute_transaction([
                (
                    "UPDATE merit_list_entries SET status = 'ACCEPTED' "
                    "WHERE id = %s AND org_id = %s",
                    (letter["merit_list_entry_id"], org_id),
                )
            ])

        # Transition: OFFER_ISSUED → OFFER_ACCEPTED → SEAT_CONFIRMED
        ApplicantService.transition_state(
            applicant_id=letter["applicant_id"],
            org_id=org_id,
            to_state=StudentState.OFFER_ACCEPTED,
            actor_id=actor_id,
            reason="Applicant accepted the offer",
            metadata={"letter_id": letter_id, "signature": request.digital_signature_ref},
        )
        ApplicantService.transition_state(
            applicant_id=letter["applicant_id"],
            org_id=org_id,
            to_state=StudentState.SEAT_CONFIRMED,
            actor_id=actor_id,
            reason="Seat confirmed after offer acceptance",
            metadata={"letter_id": letter_id},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="offer_letter",
            entity_id=letter_id,
            org_id=org_id,
            module="M1",
            wizard="Offer Letter v2",
            success=True,
            metadata={
                "action": "accepted",
                "applicant_id": letter["applicant_id"],
                "digital_signature_ref": request.digital_signature_ref,
            },
        )

        logger.info("P9: Offer accepted [letter=%s, applicant=%s]", letter_id, letter["applicant_id"])
        return cls.get(letter_id, org_id)

    # -------------------------------------------------------------------------
    # Decline
    # -------------------------------------------------------------------------

    @classmethod
    def decline(
        cls,
        letter_id: str,
        request: OfferDeclineRequest,
        org_id: str,
        actor_id: str,
    ) -> OfferLetterRead:
        """
        Applicant declines their offer.

        Transitions:
            OFFER_ISSUED → OFFER_DECLINED
        Updates:
            offer_letters.acceptance_status = DECLINED
            merit_list_entries.status = DECLINED

        After decline, the waitlist cascade is triggered via domain event.
        """
        letter = cls._require_letter(letter_id, org_id)

        if letter["acceptance_status"] != "PENDING":
            raise BusinessRuleViolation(
                message=(
                    f"Offer '{letter_id}' cannot be declined — "
                    f"current status: '{letter['acceptance_status']}'."
                ),
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE offer_letters SET acceptance_status = %s, declined_at = %s "
                "WHERE id = %s AND org_id = %s",
                ("DECLINED", now, letter_id, org_id),
            )
        ])

        # Update merit list entry if linked
        if letter.get("merit_list_entry_id"):
            execute_transaction([
                (
                    "UPDATE merit_list_entries SET status = 'DECLINED' "
                    "WHERE id = %s AND org_id = %s",
                    (letter["merit_list_entry_id"], org_id),
                )
            ])

        ApplicantService.transition_state(
            applicant_id=letter["applicant_id"],
            org_id=org_id,
            to_state=StudentState.OFFER_DECLINED,
            actor_id=actor_id,
            reason=f"Applicant declined the offer. Reason: {request.reason or 'not provided'}",
            metadata={"letter_id": letter_id, "reason": request.reason},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="offer_letter",
            entity_id=letter_id,
            org_id=org_id,
            module="M1",
            wizard="Offer Letter v2",
            success=True,
            metadata={
                "action": "declined",
                "applicant_id": letter["applicant_id"],
                "reason": request.reason,
            },
        )

        # Fire event so waitlist service can activate next candidate
        cls._publish_decline_event(
            letter_id=letter_id,
            merit_list_entry_id=letter.get("merit_list_entry_id"),
            org_id=org_id,
            actor_id=actor_id,
        )

        logger.info("P9: Offer declined [letter=%s, applicant=%s]", letter_id, letter["applicant_id"])
        return cls.get(letter_id, org_id)

    # -------------------------------------------------------------------------
    # Revoke
    # -------------------------------------------------------------------------

    @classmethod
    def revoke(
        cls,
        letter_id: str,
        request: OfferRevokeRequest,
        org_id: str,
        actor_id: str,
    ) -> OfferLetterRead:
        """
        Staff revokes a previously issued offer (requires OVERRIDE_APPROVE).

        Cannot revoke an already ACCEPTED offer without elevated reason.
        Transitions applicant → CANCELLED.
        """
        letter = cls._require_letter(letter_id, org_id)

        if letter["acceptance_status"] == "ACCEPTED":
            raise BusinessRuleViolation(
                message="Cannot revoke an ACCEPTED offer. Escalate to senior administrator.",
                details={"letter_id": letter_id, "acceptance_status": "ACCEPTED"},
            )

        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE offer_letters SET is_valid = FALSE, acceptance_status = 'EXPIRED' "
                "WHERE id = %s AND org_id = %s",
                (letter_id, org_id),
            )
        ])

        ApplicantService.transition_state(
            applicant_id=letter["applicant_id"],
            org_id=org_id,
            to_state=StudentState.CANCELLED,
            actor_id=actor_id,
            reason=f"Offer revoked by staff. Reason: {request.reason}",
            metadata={"letter_id": letter_id, "revocation_reason": request.reason},
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="offer_letter",
            entity_id=letter_id,
            org_id=org_id,
            module="M1",
            wizard="Offer Letter v2",
            success=True,
            metadata={
                "action": "revoked",
                "applicant_id": letter["applicant_id"],
                "reason": request.reason,
            },
        )

        logger.info("P9: Offer revoked [letter=%s, actor=%s]", letter_id, actor_id)
        return cls.get(letter_id, org_id)

    # -------------------------------------------------------------------------
    # Delivery tracking
    # -------------------------------------------------------------------------

    @classmethod
    def mark_delivery(
        cls,
        letter_id: str,
        org_id: str,
        status: str,
        actor_id: str,
    ) -> OfferLetterRead:
        """Update delivery status (SENT / OPENED / BOUNCED)."""
        if status not in _DELIVERY_STATUSES:
            raise BusinessRuleViolation(
                message=f"Invalid delivery status '{status}'.",
                details={"valid": list(_DELIVERY_STATUSES)},
            )
        cls._require_letter(letter_id, org_id)
        now = datetime.now(timezone.utc)

        extra_set = ""
        extra_params: tuple = ()
        if status == "OPENED":
            extra_set = ", email_opened_at = %s"
            extra_params = (now,)

        execute_transaction([
            (
                f"UPDATE offer_letters SET delivery_status = %s{extra_set} "
                "WHERE id = %s AND org_id = %s",
                (status, *extra_params, letter_id, org_id),
            )
        ])

        logger.info("P9: Delivery status updated [letter=%s, status=%s]", letter_id, status)
        return cls.get(letter_id, org_id)

    @classmethod
    def mark_reminder(
        cls,
        letter_id: str,
        org_id: str,
        reminder_type: str,
        actor_id: str,
    ) -> None:
        """Mark T-3 or T-1 day reminder as sent."""
        if reminder_type not in ("T3", "T1"):
            raise BusinessRuleViolation(message="reminder_type must be 'T3' or 'T1'.")
        col = "t3_reminder_sent" if reminder_type == "T3" else "t1_reminder_sent"
        execute_transaction([
            (
                f"UPDATE offer_letters SET {col} = TRUE WHERE id = %s AND org_id = %s",
                (letter_id, org_id),
            )
        ])
        logger.info("P9: Reminder marked [letter=%s, type=%s]", letter_id, reminder_type)

    # -------------------------------------------------------------------------
    # Expire overdue
    # -------------------------------------------------------------------------

    @classmethod
    def expire_overdue(cls, org_id: str, actor_id: str) -> Dict[str, Any]:
        """
        Batch-expire all PENDING offer letters past their acceptance deadline.

        Intended to be called by the Celery beat scheduler.
        Each expired offer transitions the applicant → CANCELLED.

        Returns:
            {"expired_count": int, "letter_ids": [...]}
        """
        now = datetime.now(timezone.utc)
        overdue = execute_query(
            "SELECT id, applicant_id FROM offer_letters "
            "WHERE org_id = %s AND acceptance_status = 'PENDING' "
            "AND is_valid = TRUE AND expires_at < %s",
            (org_id, now),
        )

        expired_ids: List[str] = []
        for row in overdue:
            try:
                cls._do_expire(row["id"], row["applicant_id"], org_id, actor_id)
                expired_ids.append(row["id"])
            except Exception as exc:
                logger.error(
                    "P9: Failed to expire offer [letter=%s]: %s", row["id"], exc
                )

        logger.info("P9: Expired %d overdue offers [org=%s]", len(expired_ids), org_id)
        return {"expired_count": len(expired_ids), "letter_ids": expired_ids}

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get(cls, letter_id: str, org_id: str) -> OfferLetterRead:
        rows = execute_query(
            "SELECT * FROM offer_letters WHERE id = %s AND org_id = %s",
            (letter_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Offer letter '{letter_id}' not found.")
        return cls._row_to_read(rows[0])

    @classmethod
    def get_for_applicant(cls, applicant_id: str, org_id: str) -> Optional[OfferLetterRead]:
        """Return the current valid offer for an applicant (None if none exists)."""
        rows = execute_query(
            "SELECT * FROM offer_letters "
            "WHERE applicant_id = %s AND org_id = %s AND is_valid = TRUE LIMIT 1",
            (applicant_id, org_id),
        )
        return cls._row_to_read(rows[0]) if rows else None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _require_letter(cls, letter_id: str, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM offer_letters WHERE id = %s AND org_id = %s",
            (letter_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Offer letter '{letter_id}' not found.")
        return rows[0]

    @classmethod
    def _do_expire(
        cls,
        letter_id: str,
        applicant_id: str,
        org_id: str,
        actor_id: str,
    ) -> None:
        """Mark a single offer as EXPIRED and cancel the applicant."""
        execute_transaction([
            (
                "UPDATE offer_letters SET acceptance_status = 'EXPIRED', is_valid = FALSE "
                "WHERE id = %s AND org_id = %s",
                (letter_id, org_id),
            )
        ])
        try:
            ApplicantService.transition_state(
                applicant_id=applicant_id,
                org_id=org_id,
                to_state=StudentState.CANCELLED,
                actor_id=actor_id,
                reason="Offer acceptance deadline passed — offer expired automatically.",
                metadata={"letter_id": letter_id, "trigger": "auto_expire"},
            )
        except Exception as exc:
            logger.warning("P9: State transition failed on expiry [applicant=%s]: %s", applicant_id, exc)

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="offer_letter",
            entity_id=letter_id,
            org_id=org_id,
            module="M1",
            wizard="Offer Letter v2",
            success=True,
            metadata={"action": "expired", "applicant_id": applicant_id},
        )

    @classmethod
    def _row_to_read(cls, row: Dict[str, Any]) -> OfferLetterRead:
        """Convert a DB row dict to OfferLetterRead, handling JSONB fee_structure."""
        data = dict(row)
        if isinstance(data.get("fee_structure"), str):
            try:
                data["fee_structure"] = json.loads(data["fee_structure"])
            except (json.JSONDecodeError, TypeError):
                data["fee_structure"] = {}
        return OfferLetterRead(**data)

    @classmethod
    def _publish_decline_event(
        cls,
        letter_id: str,
        merit_list_entry_id: Optional[str],
        org_id: str,
        actor_id: str,
    ) -> None:
        """Publish OfferDeclined domain event so waitlist service can cascade."""
        try:
            from server.core.domain_events import DomainEvent, DomainEventBus
            DomainEventBus.publish(DomainEvent(
                event_type="OfferDeclined",
                entity_type="offer_letter",
                entity_id=letter_id,
                org_id=org_id,
                payload={"merit_list_entry_id": merit_list_entry_id},
                actor_id=actor_id,
            ))
        except Exception as exc:
            logger.warning("P9: Failed to publish OfferDeclined event: %s", exc)

    # -------------------------------------------------------------------------
    # PDF rendering
    # -------------------------------------------------------------------------

    @classmethod
    def _render_pdf(
        cls,
        applicant_name: str,
        applicant_email: str,
        program: str,
        academic_year: str,
        template_version: int,
        fee_structure: dict,
        conditions: list,
        acceptance_deadline_days: int,
    ) -> bytes:
        try:
            return cls._render_with_reportlab(
                applicant_name, applicant_email, program, academic_year,
                fee_structure, conditions, acceptance_deadline_days,
            )
        except ImportError:
            return cls._render_plaintext_pdf(
                applicant_name, applicant_email, program, academic_year,
                fee_structure, conditions, acceptance_deadline_days,
            )

    @classmethod
    def _render_with_reportlab(
        cls,
        name: str,
        email: str,
        program: str,
        academic_year: str,
        fee_structure: dict,
        conditions: list,
        deadline_days: int,
    ) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import cm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("OFFER OF ADMISSION", styles["Title"]))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(f"Dear {name},", styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"We are pleased to offer you admission to the <b>{program}</b> "
            f"programme for the academic year <b>{academic_year}</b>.",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"Please accept or decline this offer within <b>{deadline_days} days</b> "
            "of receipt via the applicant portal.",
            styles["Normal"],
        ))

        if fee_structure:
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("<b>Fee Structure:</b>", styles["Normal"]))
            for key, val in fee_structure.items():
                story.append(Paragraph(f"  {key.title()}: ₹{val:,}", styles["Normal"]))

        if conditions:
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("<b>Conditions of this Offer:</b>", styles["Normal"]))
            for i, cond in enumerate(conditions, 1):
                story.append(Paragraph(f"  {i}. {cond}", styles["Normal"]))

        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Yours sincerely,", styles["Normal"]))
        story.append(Paragraph("Admissions Office, ALIS Institution", styles["Normal"]))

        doc.build(story)
        return buf.getvalue()

    @classmethod
    def _render_plaintext_pdf(
        cls,
        name: str,
        email: str,
        program: str,
        academic_year: str,
        fee_structure: dict,
        conditions: list,
        deadline_days: int,
    ) -> bytes:
        fee_lines = "\n".join(
            f"  {k.title()}: {v}" for k, v in fee_structure.items()
        ) if fee_structure else "  (see portal for fee details)"
        cond_lines = "\n".join(
            f"  {i+1}. {c}" for i, c in enumerate(conditions)
        ) if conditions else "  None"

        content = textwrap.dedent(f"""
            OFFER OF ADMISSION
            ==================

            Dear {name},

            We are pleased to offer you admission to the {program} programme
            for the academic year {academic_year}.

            Please accept or decline this offer within {deadline_days} days.

            Fee Structure:
{fee_lines}

            Conditions:
{cond_lines}

            Yours sincerely,
            Admissions Office
        """).strip()

        lines = content.split("\n")
        y = 750
        stream_lines = []
        for line in lines:
            safe = line.replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"BT /F1 12 Tf 72 {y} Td ({safe}) Tj ET")
            y -= 16
        stream = "\n".join(stream_lines)
        pdf = (
            f"%PDF-1.4\n"
            f"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            f"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            f"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            f"/Resources<</Font<</F1<</Type/Font/Subtype/Type1"
            f"/BaseFont/Helvetica>>>>>>/Contents 4 0 R>>endobj\n"
            f"4 0 obj<</Length {len(stream)}>>\nstream\n"
            f"{stream}\nendstream\nendobj\n"
            f"xref\n0 5\n0000000000 65535 f\n"
            f"trailer<</Size 5/Root 1 0 R>>\n%%EOF"
        )
        return pdf.encode("latin-1", errors="replace")

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------

    @classmethod
    def _notify_offer_issued(
        cls,
        applicant_email: str,
        applicant_name: str,
        letter_id: str,
        expires_at: datetime,
        org_id: str,
    ) -> None:
        try:
            from server.core.notifications.service import NotificationService
            svc = NotificationService()
            svc.send(
                template_id="offer_letter_issued",
                recipient_id=applicant_email,
                recipient_address=applicant_email,
                context={
                    "name": applicant_name,
                    "letter_id": letter_id,
                    "expires_at": expires_at.strftime("%d %B %Y"),
                },
                org_id=org_id,
            )
        except Exception as exc:
            logger.warning("P9: Offer notification failed: %s", exc)
