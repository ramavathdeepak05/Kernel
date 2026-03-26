"""EC-ADM-04 — Forged Document Detection (3-tier verification)

Verification tiers (in order of trust):
  Tier 1: OCR_FORMAT_ONLY        — cheapest; confidence-based
  Tier 2: DIGILOCKER_API         — live DigiLocker verification
  Tier 3: BOARD_API              — direct Board/University API cross-check
  Tier 4: MANUAL_OFFICER         — assigned to admin review queue
  Tier 5: MANUAL_FORENSIC        — escalated to forensic examiner

Rules (R1 — no hardcoded thresholds):
  - ACADEMIC_CERTIFICATE docs MUST use DIGILOCKER_API or BOARD_API
  - OCR-only confidence < policy threshold → auto-route to MANUAL_FORENSIC
  - Dual auth (CoE + Registrar) required to flag forgery
  - forgery_flags stored as JSONB array on document record
"""
from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Optional

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Academic certificates that require API-level verification
_ACADEMIC_DOC_TYPES = {
    "MARKSHEET_10",
    "MARKSHEET_12",
    "DEGREE_CERTIFICATE",
    "ENTRANCE_SCORECARD",
    "EQUIVALENCY_CERTIFICATE",
}


class DocumentVerificationMethodV2(str, Enum):
    """Extended verification methods for 3-tier detection (EC-ADM-04)."""
    OCR_FORMAT_ONLY = "OCR_FORMAT_ONLY"
    DIGILOCKER_API = "DIGILOCKER_API"
    BOARD_API = "BOARD_API"
    MANUAL_OFFICER = "MANUAL_OFFICER"
    MANUAL_FORENSIC = "MANUAL_FORENSIC"


class ForgeryDetectionService:

    @classmethod
    def evaluate_document(
        cls,
        org_id: str,
        document_id: str,
        doc_type: str,
        ocr_confidence: float,
        actor_id: str,
    ) -> dict:
        """Run verification tier routing for a document.

        1. Academic docs must use DigiLocker or Board API.
        2. OCR confidence below threshold → MANUAL_FORENSIC.
        3. Otherwise route to MANUAL_OFFICER.

        Returns the assigned verification_method and next action.
        """
        # R1 — threshold from policy, not literal
        ocr_threshold = float(policy_engine.get_value(
            "admissions.forgery_ocr_confidence_threshold", org_id, 0.5
        ))

        rows = execute_query(
            "SELECT id, doc_type, status FROM application_documents WHERE id = %s AND org_id = %s",
            (document_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Document {document_id} not found")

        doc = rows[0]

        # Determine required method
        if doc_type in _ACADEMIC_DOC_TYPES:
            # Academic docs must be API-verified — OCR alone is not acceptable
            required_method = DocumentVerificationMethodV2.DIGILOCKER_API
            queue = "digilocker_verification"
        elif ocr_confidence < ocr_threshold:
            # Low confidence → forensic queue (don't show AI score to officer — prevents anchoring)
            required_method = DocumentVerificationMethodV2.MANUAL_FORENSIC
            queue = "forensic_review"
        else:
            required_method = DocumentVerificationMethodV2.MANUAL_OFFICER
            queue = "officer_review"

        import json
        execute_transaction([("""
            UPDATE application_documents
            SET verification_method = %s,
                confidence_score    = %s,
                review_queue        = %s,
                status              = 'UNDER_REVIEW',
                updated_at          = NOW()
            WHERE id = %s AND org_id = %s
        """, (
            required_method.value, ocr_confidence, queue,
            document_id, org_id,
        ))])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="application_document",
            resource_id=document_id,
            detail={
                "verification_method": required_method.value,
                "ocr_confidence": ocr_confidence,
                "queue": queue,
            },
        )

        logger.info(
            "Document %s routed to %s (confidence=%.2f, doc_type=%s)",
            document_id, required_method.value, ocr_confidence, doc_type,
        )

        return {
            "document_id": document_id,
            "verification_method": required_method.value,
            "queue": queue,
            "ocr_confidence": ocr_confidence,
        }

    @classmethod
    def flag_forgery(
        cls,
        org_id: str,
        document_id: str,
        forgery_flags: list[str],
        notes: str,
        coe_actor_id: str,
        registrar_actor_id: Optional[str],
    ) -> dict:
        """Flag a document as forged (dual auth: CoE + Registrar required).

        If registrar_actor_id is None, creates a pending dual-auth task.
        """
        if not registrar_actor_id:
            # Create pending dual-auth approval task
            task_id = str(uuid.uuid4())
            import json
            execute_transaction([("""
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, resource_id, status,
                     created_by, payload, created_at)
                VALUES (%s, %s, 'FORGERY_FLAG_DUAL_AUTH', %s, 'PENDING_APPROVAL',
                        %s, %s, NOW())
            """, (
                task_id, org_id, document_id, coe_actor_id,
                json.dumps({
                    "forgery_flags": forgery_flags,
                    "notes": notes,
                    "coe_actor_id": coe_actor_id,
                }),
            ))])
            return {
                "status": "pending_dual_auth",
                "task_id": task_id,
                "message": "Registrar approval required to complete forgery flag",
            }

        import json
        execute_transaction([("""
            UPDATE application_documents
            SET forgery_flags = %s,
                forgery_notes = %s,
                status        = 'REJECTED',
                verified_by   = %s,
                updated_at    = NOW()
            WHERE id = %s AND org_id = %s
        """, (
            json.dumps(forgery_flags), notes,
            coe_actor_id,
            document_id, org_id,
        ))])

        AuditLog.log(
            org_id=org_id,
            actor_id=coe_actor_id,
            action=AuditAction.UPDATED,
            resource_type="application_document",
            resource_id=document_id,
            detail={
                "forgery_flagged": True,
                "flags": forgery_flags,
                "registrar_confirmed": registrar_actor_id,
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="admissions.document_forgery_flagged",
            org_id=org_id,
            payload={
                "document_id": document_id,
                "forgery_flags": forgery_flags,
                "coe_actor_id": coe_actor_id,
                "registrar_actor_id": registrar_actor_id,
            },
        ))

        return {
            "status": "flagged",
            "document_id": document_id,
            "forgery_flags": forgery_flags,
        }
