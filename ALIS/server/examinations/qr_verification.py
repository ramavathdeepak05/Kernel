"""
QR Code Generation & Verification — Exam Hall Tickets + Transcripts

Generates QR codes containing a verification URL that points to
a public endpoint for document authenticity verification.

Used by:
- Hall ticket generation (Stage 4)
- Transcript generation (Stage 12 — AIU format)
- Degree certificate

QR contains: verification_url + document_hash + issue_date
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class QRVerificationService:
    """
    Generates and verifies QR codes for exam documents.
    """

    @classmethod
    def generate_qr_data(
        cls,
        org_id: str,
        document_type: str,
        document_id: str,
        student_id: str,
        content_hash: str,
        base_url: str = "",
    ) -> Dict[str, Any]:
        """
        Generate QR code data (URL + hash) for a document.

        Returns a dict with verification_url and qr_payload.
        The caller renders this into an actual QR image.
        """
        from server.core.settings import settings

        verification_id = str(uuid4())
        now = datetime.now(timezone.utc)

        if not base_url:
            base_url = f"https://{settings.saas_domain_suffix}"

        verification_url = f"{base_url}/verify/{verification_id}"

        # Store verification record
        execute_transaction([
            (
                """
                INSERT INTO document_verifications
                    (id, org_id, document_type, document_id, student_id,
                     content_hash, verification_url, issued_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (verification_id, org_id, document_type, document_id,
                 student_id, content_hash, verification_url, now),
            )
        ], tenant_id=org_id)

        qr_payload = json.dumps({
            "v": verification_id,
            "t": document_type,
            "h": content_hash[:16],
            "d": now.strftime("%Y-%m-%d"),
        })

        return {
            "verification_id": verification_id,
            "verification_url": verification_url,
            "qr_payload": qr_payload,
            "content_hash": content_hash,
        }

    @classmethod
    def verify_document(cls, verification_id: str) -> Optional[Dict[str, Any]]:
        """
        Public verification endpoint — no auth required.
        Returns document verification status.
        """
        rows = execute_query(
            "SELECT * FROM document_verifications WHERE id = %s",
            (verification_id,),
        )
        if not rows:
            return None

        record = dict(rows[0])
        return {
            "valid": True,
            "document_type": record["document_type"],
            "issued_at": str(record["issued_at"]),
            "institution": record["org_id"],
            "content_hash": record["content_hash"],
        }

    @classmethod
    def generate_hall_ticket_qr(cls, org_id: str, hall_ticket_id: str, student_id: str) -> Dict[str, Any]:
        """Generate QR for a hall ticket — includes verification URL."""
        content_hash = hashlib.sha256(
            f"{org_id}:{hall_ticket_id}:{student_id}".encode()
        ).hexdigest()
        return cls.generate_qr_data(org_id, "HALL_TICKET", hall_ticket_id, student_id, content_hash)

    @classmethod
    def generate_transcript_qr(cls, org_id: str, transcript_id: str, student_id: str) -> Dict[str, Any]:
        """Generate QR for a transcript — AIU standard verification."""
        content_hash = hashlib.sha256(
            f"{org_id}:TRANSCRIPT:{transcript_id}:{student_id}".encode()
        ).hexdigest()
        return cls.generate_qr_data(org_id, "TRANSCRIPT", transcript_id, student_id, content_hash)

    @classmethod
    def generate_degree_qr(cls, org_id: str, degree_id: str, student_id: str) -> Dict[str, Any]:
        """Generate QR for a degree certificate."""
        content_hash = hashlib.sha256(
            f"{org_id}:DEGREE:{degree_id}:{student_id}".encode()
        ).hexdigest()
        return cls.generate_qr_data(org_id, "DEGREE_CERTIFICATE", degree_id, student_id, content_hash)


class HallTicketDuesGate:
    """
    Re-queries student dues at hall ticket generation time.
    (Not just at eligibility stage — must be re-checked per workflow doc.)
    """

    @classmethod
    def check_dues_at_generation(cls, org_id: str, student_id: str) -> Dict[str, Any]:
        """
        Re-query dues status at hall ticket generation time.
        Returns {cleared: bool, total_due: float}
        """
        dues = execute_query(
            "SELECT total_due FROM student_dues_status WHERE student_id = %s AND org_id = %s",
            (student_id, org_id), tenant_id=org_id,
        )
        total_due = float(dues[0]["total_due"]) if dues else 0
        # Check for exemptions (EC-FIN-01)
        exempted = execute_query(
            "SELECT id FROM student_fee_exemptions WHERE student_id = %s AND org_id = %s "
            "AND is_active = TRUE AND (valid_until IS NULL OR valid_until > NOW())",
            (student_id, org_id), tenant_id=org_id,
        )

        return {
            "student_id": student_id,
            "total_due": total_due,
            "exempted": bool(exempted),
            "cleared": total_due <= 0 or bool(exempted),
        }
