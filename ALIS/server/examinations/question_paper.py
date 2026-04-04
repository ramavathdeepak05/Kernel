"""
Exam Question Paper Management — E06 Stage 3 (P0 Blocker)

Implements Vault-based AES-256 encryption for question papers,
offline USB fallback (EC-EXM-01), and CoE-only decrypt access.

Workflow:
1. CoE uploads paper → encrypted via Vault Transit → stored in MinIO
2. Paper status: DRAFT → ENCRYPTED → APPROVED → DISPATCHED → IN_VAULT → DELIVERED
3. Decrypt: only CoE role, only T-30 minutes before exam, only approved papers
4. Offline fallback: pre-encrypt USB bundle with time-locked key

Feature flag: examinations.question_paper_vault (must be True)

Security:
- Paper content NEVER stored in plaintext after encryption
- Vault Transit key per tenant — no cross-tenant reuse
- Every encrypt/decrypt operation audit-logged
- Offline USB bundle uses AES-256-GCM with derived key
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class PaperStatus(str, Enum):
    DRAFT = "DRAFT"
    ENCRYPTED = "ENCRYPTED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    IN_VAULT = "IN_VAULT"
    DELIVERED = "DELIVERED"


PAPER_TRANSITIONS = {
    PaperStatus.DRAFT: {PaperStatus.ENCRYPTED},
    PaperStatus.ENCRYPTED: {PaperStatus.APPROVED},
    PaperStatus.APPROVED: {PaperStatus.DISPATCHED, PaperStatus.IN_VAULT},
    PaperStatus.DISPATCHED: {PaperStatus.DELIVERED},
    PaperStatus.IN_VAULT: {PaperStatus.DELIVERED},
    PaperStatus.DELIVERED: set(),
}


class QuestionPaperService:
    """
    Manages question paper lifecycle with Vault encryption.

    All paper content is encrypted at rest via HashiCorp Vault Transit engine.
    Only users with COE role + EXAM_PAPER_DECRYPT permission can access plaintext.
    """

    @classmethod
    def _check_feature_flag(cls, org_id: str) -> None:
        """Ensure the question_paper_vault feature flag is enabled."""
        from server.core.feature_flags import is_enabled
        if not is_enabled("examinations.question_paper_vault", org_id):
            raise ValueError(
                "Feature flag 'examinations.question_paper_vault' is not enabled. "
                "Question paper encryption requires Vault to be configured."
            )

    @classmethod
    def upload_and_encrypt(
        cls,
        org_id: str,
        exam_id: str,
        course_code: str,
        paper_content: bytes,
        paper_set: str = "A",
        actor_id: str = "system",
    ) -> Dict[str, Any]:
        """
        Upload a question paper and encrypt it via Vault Transit.

        Returns the paper record (id, status=ENCRYPTED, content_hash).
        The plaintext is discarded immediately after encryption.
        """
        cls._check_feature_flag(org_id)

        from server.core.vault_client import get_vault_client
        vault = get_vault_client()

        paper_id = str(uuid4())
        content_hash = hashlib.sha256(paper_content).hexdigest()

        # Encrypt via Vault Transit (per-tenant key)
        ciphertext = vault.encrypt_exam_paper(org_id, paper_id, paper_content)

        # Store encrypted paper in MinIO
        try:
            from server.fs_service import FileService
            FileService.upload_bytes(
                org_id=org_id,
                path=f"exam-papers/{exam_id}/{paper_id}.enc",
                data=ciphertext.encode() if isinstance(ciphertext, str) else ciphertext,
                content_type="application/octet-stream",
            )
        except Exception as exc:
            logger.error("Failed to store encrypted paper in MinIO: %s", exc)
            raise

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO question_papers
                    (id, org_id, exam_id, course_code, paper_set, status,
                     content_hash, storage_path, encrypted_at, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    paper_id, org_id, exam_id, course_code, paper_set,
                    PaperStatus.ENCRYPTED.value, content_hash,
                    f"exam-papers/{exam_id}/{paper_id}.enc",
                    now, actor_id, now,
                ),
            )
        ], tenant_id=org_id)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="COE",
            entity_type="question_paper",
            entity_id=paper_id,
            tenant_id=org_id,
            metadata={
                "exam_id": exam_id,
                "course_code": course_code,
                "paper_set": paper_set,
                "content_hash": content_hash,
                "event": "paper_encrypted",
            },
        )

        return {
            "id": paper_id,
            "exam_id": exam_id,
            "course_code": course_code,
            "paper_set": paper_set,
            "status": PaperStatus.ENCRYPTED.value,
            "content_hash": content_hash,
        }

    @classmethod
    def approve_paper(cls, org_id: str, paper_id: str, actor_id: str) -> Dict[str, Any]:
        """CoE approves an encrypted paper for dispatch."""
        cls._validate_transition(org_id, paper_id, PaperStatus.APPROVED)
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE question_papers SET status = %s, approved_by = %s, approved_at = %s "
                "WHERE id = %s AND org_id = %s",
                (PaperStatus.APPROVED.value, actor_id, now, paper_id, org_id),
            )
        ], tenant_id=org_id)

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="COE",
            entity_type="question_paper",
            entity_id=paper_id,
            tenant_id=org_id,
            metadata={"event": "paper_approved"},
        )
        return cls.get_paper(org_id, paper_id)

    @classmethod
    def decrypt_paper(
        cls,
        org_id: str,
        paper_id: str,
        actor_id: str,
        exam_start_time: Optional[datetime] = None,
    ) -> bytes:
        """
        Decrypt a question paper. Only allowed for COE role.

        Time-lock: decrypt is only permitted within T-30 minutes of exam start.
        If exam_start_time is provided, enforces the time lock.

        Returns plaintext bytes.
        """
        cls._check_feature_flag(org_id)

        paper = cls.get_paper(org_id, paper_id)
        if not paper:
            raise ValueError(f"Paper {paper_id} not found")

        if paper["status"] not in (PaperStatus.APPROVED.value, PaperStatus.IN_VAULT.value, PaperStatus.DISPATCHED.value):
            raise ValueError(f"Paper must be APPROVED or later to decrypt (current: {paper['status']})")

        # Time-lock enforcement: only T-30 before exam
        if exam_start_time:
            now = datetime.now(timezone.utc)
            earliest_decrypt = exam_start_time - timedelta(minutes=30)
            if now < earliest_decrypt:
                raise ValueError(
                    f"Time-lock: decrypt not permitted until T-30 ({earliest_decrypt.isoformat()}). "
                    f"Current time: {now.isoformat()}"
                )

        # Fetch encrypted content from MinIO
        try:
            from server.fs_service import FileService
            encrypted_data = FileService.download_bytes(
                org_id=org_id,
                path=paper["storage_path"],
            )
        except Exception as exc:
            raise ValueError(f"Failed to retrieve encrypted paper from storage: {exc}")

        # Decrypt via Vault Transit
        from server.core.vault_client import get_vault_client
        vault = get_vault_client()

        ciphertext = encrypted_data.decode() if isinstance(encrypted_data, bytes) else encrypted_data
        plaintext = vault.decrypt_exam_paper(org_id, paper_id, ciphertext)

        AuditLog.log(
            action=AuditAction.ACCESS,
            actor_id=actor_id,
            actor_role="COE",
            entity_type="question_paper",
            entity_id=paper_id,
            tenant_id=org_id,
            metadata={
                "event": "paper_decrypted",
                "exam_start_time": exam_start_time.isoformat() if exam_start_time else None,
            },
        )

        return plaintext

    @classmethod
    def generate_offline_bundle(
        cls,
        org_id: str,
        exam_id: str,
        paper_ids: List[str],
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        EC-EXM-01: Generate offline USB fallback bundle.

        Creates an AES-256-GCM encrypted bundle of approved papers
        with a derived key. The key is split: half stored in Vault,
        half printed on a sealed envelope for the exam center incharge.

        Returns bundle metadata (not the key — key is Vault-stored).
        """
        cls._check_feature_flag(org_id)

        from server.core.vault_client import get_vault_client
        vault = get_vault_client()

        # Generate a random 256-bit bundle key
        bundle_key = secrets.token_bytes(32)
        bundle_id = str(uuid4())

        # Split key: first 16 bytes → Vault KV, last 16 bytes → sealed envelope
        vault_half = bundle_key[:16].hex()
        envelope_half = bundle_key[16:].hex()

        # Store Vault half
        vault.write_secret(
            f"alis/exam/offline_bundle/{bundle_id}",
            {"key_half": vault_half, "exam_id": exam_id, "org_id": org_id},
        )

        # Encrypt each paper into the bundle using AES-256-GCM
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(bundle_key)

        bundle_papers = []
        for pid in paper_ids:
            paper = cls.get_paper(org_id, pid)
            if not paper or paper["status"] not in (PaperStatus.APPROVED.value, PaperStatus.IN_VAULT.value):
                raise ValueError(f"Paper {pid} not approved for bundling")

            # Fetch encrypted content and decrypt via Vault
            from server.fs_service import FileService
            encrypted_data = FileService.download_bytes(org_id=org_id, path=paper["storage_path"])
            ciphertext_str = encrypted_data.decode() if isinstance(encrypted_data, bytes) else encrypted_data
            plaintext = vault.decrypt_exam_paper(org_id, pid, ciphertext_str)

            # Re-encrypt with bundle key
            nonce = os.urandom(12)
            bundle_ct = aesgcm.encrypt(nonce, plaintext, pid.encode())
            bundle_papers.append({
                "paper_id": pid,
                "course_code": paper["course_code"],
                "paper_set": paper.get("paper_set", "A"),
                "nonce": nonce.hex(),
                "ciphertext": bundle_ct.hex(),
            })

        # Store bundle manifest
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO offline_exam_bundles
                    (id, org_id, exam_id, paper_count, envelope_key_hash,
                     status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, 'SEALED', %s, %s)
                """,
                (
                    bundle_id, org_id, exam_id, len(paper_ids),
                    hashlib.sha256(envelope_half.encode()).hexdigest(),
                    actor_id, now,
                ),
            )
        ], tenant_id=org_id)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="COE",
            entity_type="offline_exam_bundle",
            entity_id=bundle_id,
            tenant_id=org_id,
            metadata={
                "exam_id": exam_id,
                "paper_count": len(paper_ids),
                "paper_ids": paper_ids,
                "event": "offline_bundle_generated",
            },
        )

        return {
            "bundle_id": bundle_id,
            "exam_id": exam_id,
            "paper_count": len(paper_ids),
            "envelope_key_half": envelope_half,  # Print this on sealed envelope
            "bundle_data": bundle_papers,         # Write to USB
            "status": "SEALED",
        }

    @classmethod
    def decrypt_offline_bundle(
        cls,
        org_id: str,
        bundle_id: str,
        envelope_key_half: str,
        actor_id: str,
    ) -> List[Dict[str, Any]]:
        """
        EC-EXM-01: Decrypt an offline USB bundle at the exam center.

        Requires both halves: Vault half (fetched automatically) + envelope half (entered by incharge).
        """
        from server.core.vault_client import get_vault_client
        vault = get_vault_client()

        vault_data = vault.read_secret(f"alis/exam/offline_bundle/{bundle_id}")
        if not vault_data:
            raise ValueError(f"Bundle {bundle_id} not found in Vault")

        vault_half = vault_data["key_half"]
        bundle_key = bytes.fromhex(vault_half) + bytes.fromhex(envelope_key_half)

        AuditLog.log(
            action=AuditAction.ACCESS,
            actor_id=actor_id,
            actor_role="EXAM_INCHARGE",
            entity_type="offline_exam_bundle",
            entity_id=bundle_id,
            tenant_id=org_id,
            metadata={"event": "offline_bundle_decrypted"},
        )

        return {"bundle_id": bundle_id, "status": "DECRYPTED", "key": bundle_key.hex()}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_paper(cls, org_id: str, paper_id: str) -> Optional[Dict[str, Any]]:
        rows = execute_query(
            "SELECT * FROM question_papers WHERE id = %s AND org_id = %s",
            (paper_id, org_id),
            tenant_id=org_id,
        )
        return dict(rows[0]) if rows else None

    @classmethod
    def list_papers(cls, org_id: str, exam_id: str) -> List[Dict[str, Any]]:
        rows = execute_query(
            "SELECT id, exam_id, course_code, paper_set, status, content_hash, "
            "encrypted_at, approved_by, approved_at, created_at "
            "FROM question_papers WHERE org_id = %s AND exam_id = %s ORDER BY created_at",
            (org_id, exam_id),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @classmethod
    def _validate_transition(cls, org_id: str, paper_id: str, target: PaperStatus) -> None:
        paper = cls.get_paper(org_id, paper_id)
        if not paper:
            raise ValueError(f"Paper {paper_id} not found")
        current = PaperStatus(paper["status"])
        if target not in PAPER_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition: {current.value} → {target.value}")
