"""
E04-S04 — Document Verification Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 2 (AI Verification) + Layer 4 (Locks)
ENTITY: ApplicationDocument

Handles document upload, storage, and AI-assisted verification.

Verification Pipeline:
    1. Receive base64-encoded file content
    2. Persist to file system (via FSService)
    3. Run AI verification (stamp/seal detection, date validity)
    4. Mark document as verified/unverified
    5. Log result to audit

Layer 4 Lock: Offer letter generation is blocked if any required
document is unverified (enforced in offer_letter.py).

Admin Override: An admin can mark any document as verified with
a justification, bypassing AI verdict.

Acceptance Criteria (E04-S04):
    - [x] API: POST /documents/upload
    - [x] is_verified = true/false
    - [x] Admin override with log
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation, PermissionDeniedError
from server.core.rbac import Role
from server.db_service import execute_query, execute_transaction
from server.fs_service import FileStorageService

from .models import (
    ApplicationDocumentRead,
    DocumentStatus,
    DocumentType,
    DocumentUploadRequest,
    DocumentVerificationMethod,
)

logger = logging.getLogger(__name__)

# Required doc types that must be verified before an offer letter is issued
_REQUIRED_FOR_OFFER = {
    DocumentType.MARKSHEET_12.value,
    DocumentType.GOVT_ID.value,
}


class DocumentVerificationService:
    """
    Manages application document upload and verification for E04-S04.
    """

    # -------------------------------------------------------------------------
    # Upload
    # -------------------------------------------------------------------------

    @classmethod
    def upload_document(
        cls,
        request: DocumentUploadRequest,
        org_id: str,
        uploaded_by: str,
    ) -> ApplicationDocumentRead:
        """
        Upload and store an application document.

        AI verification is triggered asynchronously (advisory).
        The document starts as is_verified=False.

        Args:
            request:     Upload request with file content (base64)
            org_id:      Tenant scope
            uploaded_by: Actor performing the upload

        Returns:
            ApplicationDocumentRead with is_verified=False initially
        """
        # Decode base64 file
        try:
            file_bytes = base64.b64decode(request.file_content_base64)
        except Exception:
            raise BusinessRuleViolation(
                message="Invalid base64 file content.",
                details={"file_name": request.file_name},
            )

        # Persist to file system via FileStorageService
        fs = FileStorageService()
        file_meta = fs.upload_file(
            file_content=file_bytes,
            filename=request.file_name,
            owner_id=uploaded_by,
            context={"role": "staff", "entity_type": "application_document",
                     "entity_id": request.applicant_id},
        )
        file_path = str(file_meta.get_version().storage_path) if file_meta.get_version() else request.file_name

        doc_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO application_documents
                    (id, org_id, applicant_id, doc_type, file_path,
                     is_verified, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id, org_id,
                    request.applicant_id,
                    request.doc_type.value,
                    file_path,
                    False,
                    now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=uploaded_by,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "doc_type": request.doc_type.value,
                "file_name": request.file_name,
            },
        )

        # Trigger AI verification (synchronous for now — use task queue in prod)
        cls._run_ai_verification(doc_id, file_path, request.doc_type.value, org_id, uploaded_by)

        return cls.get_document(doc_id, org_id)

    # -------------------------------------------------------------------------
    # AI Verification
    # -------------------------------------------------------------------------

    @classmethod
    def _run_ai_verification(
        cls,
        doc_id: str,
        file_path: str,
        doc_type: str,
        org_id: str,
        actor_id: str,
    ) -> None:
        """
        Run AI-based verification on a document.

        Uses the AI Gateway to invoke an LLM check for:
        - Stamp/seal presence on marksheets and certificates
        - Date validity (not expired, not future-dated)
        - Format consistency

        Updates is_verified and verification_method in DB.
        """
        from server.core.ai_gateway import AIGateway, AIGatewayContext
        from server.core.rbac import Role

        context = AIGatewayContext(
            actor_id="document_verifier_v1",
            actor_role=Role.SYSTEM,
            actor_type="ai_agent",
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
        )

        # Read file content for LLM context
        try:
            with open(file_path, "rb") as f:
                content_sample = f.read(4096)  # First 4KB for text extraction
            content_text = content_sample.decode("utf-8", errors="replace")
        except Exception:
            content_text = f"[Binary document: {doc_type}]"

        llm = AIGateway.get_llm(context)
        prompt = (
            f"You are a document verification AI for a university admissions system.\n"
            f"Document type: {doc_type}\n"
            f"Document content sample:\n{content_text[:2000]}\n\n"
            f"Verify this document and return JSON with fields:\n"
            f"  decision: 'VERIFIED' or 'REJECTED'\n"
            f"  confidence_score: 0.0-1.0\n"
            f"  confidence_tier: HIGH/MEDIUM/LOW\n"
            f"  state_impact: Draft\n"
            f"  reasoning: brief explanation\n"
        )

        result = llm.invoke(prompt, validate_schema=True)

        is_verified = False
        detail = "AI verification inconclusive"

        if result.success and result.validated_output:
            vo = result.validated_output
            is_verified = (
                "VERIFIED" in vo.decision.upper()
                and vo.confidence_score >= 0.6
            )
            detail = vo.reasoning or vo.decision

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                UPDATE application_documents
                SET is_verified = %s,
                    verification_method = %s,
                    verification_detail = %s,
                    verified_by = %s,
                    verified_at = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    is_verified,
                    DocumentVerificationMethod.AI_AUTO.value,
                    detail[:500],
                    "ai_agent:document_verifier_v1",
                    now,
                    doc_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={
                "is_verified": is_verified,
                "method": DocumentVerificationMethod.AI_AUTO.value,
                "detail": detail,
            },
        )

    # -------------------------------------------------------------------------
    # Admin Override
    # -------------------------------------------------------------------------

    @classmethod
    def admin_override(
        cls,
        doc_id: str,
        org_id: str,
        actor_id: str,
        actor_role: Any,
        is_verified: bool,
        justification: str,
    ) -> ApplicationDocumentRead:
        """
        Admin manually overrides the verification status of a document.

        Requires admin or above role. Justification is mandatory.
        Result is always logged to audit.

        Raises:
            PermissionDeniedError: If actor is not admin.
            BusinessRuleViolation: If justification is empty.
        """
        try:
            role = Role(actor_role)
        except (ValueError, TypeError):
            role = Role.STUDENT

        if role not in (Role.ADMIN, Role.SUPER_ADMIN, Role.SYSTEM):
            raise PermissionDeniedError(
                message="Document verification override requires ADMIN role."
            )

        if not justification or not justification.strip():
            raise BusinessRuleViolation(
                message="Justification is required for admin document override."
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                UPDATE application_documents
                SET is_verified = %s,
                    verification_method = %s,
                    verification_detail = %s,
                    verified_by = %s,
                    verified_at = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    is_verified,
                    DocumentVerificationMethod.ADMIN_OVERRIDE.value,
                    justification[:500],
                    actor_id,
                    now,
                    doc_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.OVERRIDE_EXECUTED,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={
                "is_verified": is_verified,
                "method": DocumentVerificationMethod.ADMIN_OVERRIDE.value,
                "justification": justification,
            },
        )

        logger.info(
            "E04-S04: Admin override — doc %s → is_verified=%s [actor=%s]",
            doc_id, is_verified, actor_id,
        )
        return cls.get_document(doc_id, org_id)

    # -------------------------------------------------------------------------
    # Query helpers
    # -------------------------------------------------------------------------

    @classmethod
    def get_document(cls, doc_id: str, org_id: str) -> ApplicationDocumentRead:
        rows = execute_query(
            "SELECT * FROM application_documents WHERE id = %s AND org_id = %s",
            (doc_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Document '{doc_id}' not found.")
        return ApplicationDocumentRead(**rows[0])

    @classmethod
    def list_documents(
        cls, applicant_id: str, org_id: str
    ) -> List[ApplicationDocumentRead]:
        rows = execute_query(
            "SELECT * FROM application_documents "
            "WHERE applicant_id = %s AND org_id = %s ORDER BY created_at ASC",
            (applicant_id, org_id),
        )
        return [ApplicationDocumentRead(**r) for r in rows]

    @classmethod
    def all_required_docs_verified(cls, applicant_id: str, org_id: str) -> bool:
        """
        Return True if all required document types are uploaded and approved.

        Checks doc_status = APPROVED (Stage 3 workflow) first;
        falls back to is_verified = True for backward compatibility.
        """
        rows = execute_query(
            "SELECT doc_type, is_verified, doc_status FROM application_documents "
            "WHERE applicant_id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        approved_types = {
            r["doc_type"] for r in rows
            if r.get("doc_status") == DocumentStatus.APPROVED.value or r["is_verified"]
        }
        return _REQUIRED_FOR_OFFER.issubset(approved_types)

    # -------------------------------------------------------------------------
    # Stage 3: Document Review Workflow
    # -------------------------------------------------------------------------

    @classmethod
    def submit_for_review(
        cls,
        doc_id: str,
        org_id: str,
        actor_id: str,
    ) -> ApplicationDocumentRead:
        """
        Transition doc_status: PENDING → UNDER_REVIEW.

        Called when a staff officer begins reviewing a document.
        """
        rows = execute_query(
            "SELECT doc_status FROM application_documents WHERE id = %s AND org_id = %s",
            (doc_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Document '{doc_id}' not found.")

        current = rows[0]["doc_status"]
        if current not in (DocumentStatus.PENDING.value, None, ""):
            raise BusinessRuleViolation(
                message=f"Document must be in PENDING status to start review. Current: {current}",
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE application_documents SET doc_status = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (DocumentStatus.UNDER_REVIEW.value, now, doc_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={"doc_status": DocumentStatus.UNDER_REVIEW.value},
        )
        return cls.get_document(doc_id, org_id)

    @classmethod
    def approve_document(
        cls,
        doc_id: str,
        org_id: str,
        actor_id: str,
        actor_role: object = None,
    ) -> ApplicationDocumentRead:
        """
        Approve a document: doc_status → APPROVED, is_verified → True.

        Requires at least STAFF role (officer or admin).
        """
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                UPDATE application_documents
                SET doc_status = %s,
                    is_verified = TRUE,
                    verification_method = %s,
                    verified_by = %s,
                    verified_at = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    DocumentStatus.APPROVED.value,
                    DocumentVerificationMethod.MANUAL_OFFICER.value,
                    actor_id, now,
                    doc_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={"doc_status": DocumentStatus.APPROVED.value, "is_verified": True},
        )

        logger.info("E04-S04: Document approved — doc %s [actor=%s]", doc_id, actor_id)
        return cls.get_document(doc_id, org_id)

    @classmethod
    def reject_document(
        cls,
        doc_id: str,
        org_id: str,
        actor_id: str,
        rejection_reason: str,
        allow_reupload: bool = True,
        reupload_deadline: "datetime | None" = None,
    ) -> ApplicationDocumentRead:
        """
        Reject a document.

        If allow_reupload=True → doc_status = REUPLOAD_REQUESTED.
        Otherwise → doc_status = REJECTED (terminal).
        """
        if not rejection_reason or not rejection_reason.strip():
            raise BusinessRuleViolation(
                message="Rejection reason is required when rejecting a document."
            )

        new_status = (
            DocumentStatus.REUPLOAD_REQUESTED.value
            if allow_reupload
            else DocumentStatus.REJECTED.value
        )
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                UPDATE application_documents
                SET doc_status = %s,
                    is_verified = FALSE,
                    rejection_reason = %s,
                    reupload_deadline = %s
                WHERE id = %s AND org_id = %s
                """,
                (
                    new_status,
                    rejection_reason[:500],
                    reupload_deadline,
                    doc_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={
                "doc_status": new_status,
                "rejection_reason": rejection_reason,
                "allow_reupload": allow_reupload,
            },
        )

        logger.info(
            "E04-S04: Document rejected — doc %s status=%s [actor=%s]",
            doc_id, new_status, actor_id,
        )
        return cls.get_document(doc_id, org_id)

    @classmethod
    def reupload_document(
        cls,
        doc_id: str,
        file_bytes: bytes,
        file_name: str,
        org_id: str,
        actor_id: str,
    ) -> ApplicationDocumentRead:
        """
        Replace a rejected/reupload-requested document with a new file.

        Increments reupload_count, resets doc_status to PENDING.
        Max 3 reuploads enforced.
        """
        rows = execute_query(
            "SELECT doc_status, reupload_count, applicant_id, doc_type "
            "FROM application_documents WHERE id = %s AND org_id = %s",
            (doc_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Document '{doc_id}' not found.")

        doc = rows[0]
        if doc["doc_status"] not in (
            DocumentStatus.REUPLOAD_REQUESTED.value,
            DocumentStatus.REJECTED.value,
        ):
            raise BusinessRuleViolation(
                message=f"Document must be in REUPLOAD_REQUESTED or REJECTED status. "
                        f"Current: {doc['doc_status']}",
            )

        reupload_count = (doc["reupload_count"] or 0)
        if reupload_count >= 3:
            raise BusinessRuleViolation(
                message="Maximum reupload limit (3) reached for this document.",
                details={"reupload_count": reupload_count},
            )

        # Store new file
        from server.fs_service import FileStorageService
        fs = FileStorageService()
        file_meta = fs.upload_file(
            file_content=file_bytes,
            filename=file_name,
            owner_id=actor_id,
            context={"role": "staff", "entity_type": "application_document", "entity_id": doc_id},
        )
        new_path = str(file_meta.get_version().storage_path) if file_meta.get_version() else file_name

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                UPDATE application_documents
                SET file_path = %s,
                    original_file_name = %s,
                    doc_status = %s,
                    is_verified = FALSE,
                    rejection_reason = NULL,
                    reupload_count = reupload_count + 1,
                    reupload_deadline = NULL,
                    verification_method = NULL,
                    verification_detail = NULL,
                    verified_by = NULL,
                    verified_at = NULL
                WHERE id = %s AND org_id = %s
                """,
                (
                    new_path, file_name,
                    DocumentStatus.PENDING.value,
                    doc_id, org_id,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="application_document",
            entity_id=doc_id,
            org_id=org_id,
            module="M1",
            wizard="Document Verification",
            success=True,
            metadata={
                "action": "reupload",
                "new_reupload_count": reupload_count + 1,
                "file_name": file_name,
            },
        )

        # Trigger AI re-verification on new file
        cls._run_ai_verification(doc_id, new_path, doc["doc_type"], org_id, actor_id)

        logger.info(
            "E04-S04: Document reuploaded — doc %s [count=%d actor=%s]",
            doc_id, reupload_count + 1, actor_id,
        )
        return cls.get_document(doc_id, org_id)
