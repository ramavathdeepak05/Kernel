"""
AI background tasks — P0-S10

Celery tasks for AI workloads: embedding ETL, document OCR, async LLM inference.
"""

from __future__ import annotations

import logging

import httpx
from server.worker import celery_app

logger = logging.getLogger(__name__)


# =============================================================================
# P0-S10 — Counsellor embedding ETL
# =============================================================================


@celery_app.task(
    name="ai_tasks.upsert_counsellor_embedding",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def upsert_counsellor_embedding(
    self, org_id: str, counsellor_id: str, profile_text: str
) -> dict:
    """
    Generate a text embedding for a counsellor profile and upsert into
    the `counsellor_embeddings` PGVector table.

    Triggered on:
    - Counsellor account creation (role=COUNSELLOR)
    - Counsellor profile update (metadata changed)

    Args:
        org_id: Tenant identifier
        counsellor_id: User ID of the counsellor
        profile_text: Plain-text description of the counsellor's profile
                      (name, specializations, bio, programs handled, etc.)
    """
    from server.core.settings import settings
    from server.db_service import execute_system_transaction

    try:
        # ----------------------------------------------------------------
        # 1. Generate embedding via Ollama nomic-embed-text
        # ----------------------------------------------------------------
        response = httpx.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embed_model, "input": profile_text},
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        # nomic-embed-text returns {"embeddings": [[...]]}, single input → first element
        embedding: list[float] = data["embeddings"][0]

        # Postgres vector literal: '[0.1, 0.2, ...]'
        vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        # ----------------------------------------------------------------
        # 2. Upsert into counsellor_embeddings (conflict on org_id + counsellor_id)
        # ----------------------------------------------------------------
        execute_system_transaction(
            [
                (
                    """
                INSERT INTO counsellor_embeddings
                    (org_id, counsellor_id, profile_text, embedding)
                VALUES (%s, %s, %s, %s::vector)
                ON CONFLICT (org_id, counsellor_id)
                DO UPDATE SET
                    profile_text = EXCLUDED.profile_text,
                    embedding    = EXCLUDED.embedding,
                    created_at   = NOW()
                """,
                    (org_id, counsellor_id, profile_text, vector_literal),
                )
            ]
        )

        logger.info(
            "P0-S10: Counsellor embedding upserted — org=%s counsellor=%s dims=%d",
            org_id,
            counsellor_id,
            len(embedding),
        )
        return {"status": "ok", "counsellor_id": counsellor_id, "dims": len(embedding)}

    except httpx.HTTPError as exc:
        logger.warning("P0-S10: Ollama embed request failed: %s — retrying", exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error(
            "P0-S10: Embedding ETL failed for counsellor %s: %s", counsellor_id, exc
        )
        raise self.retry(exc=exc)


# =============================================================================
# E04 — Async document verification
# =============================================================================


@celery_app.task(
    name="ai_tasks.verify_document_async",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def verify_document_async(
    self, org_id: str, document_id: str, applicant_id: str
) -> dict:
    """
    Async wrapper for ForgeryDetectionService.evaluate_document().

    Tier routing:
      ACADEMIC_CERTIFICATE docs  → DIGILOCKER_API queue
      OCR confidence < threshold → MANUAL_FORENSIC queue
      Otherwise                  → MANUAL_OFFICER queue

    The task fetches doc_type from DB; OCR confidence defaults to 0.7
    (routes to MANUAL_OFFICER) unless already stored on the document record.
    """
    from server.admissions.forgery_detection import ForgeryDetectionService
    from server.db_service import execute_system_query

    try:
        rows = execute_system_query(
            """
            SELECT doc_type, COALESCE(confidence_score, 0.7) AS ocr_confidence
            FROM application_documents
            WHERE id = %s AND org_id = %s
            """,
            (document_id, org_id),
        )
        if not rows:
            logger.error(
                "verify_document_async: document %s not found in org %s",
                document_id,
                org_id,
            )
            return {"status": "not_found", "document_id": document_id}

        doc_type = rows[0]["doc_type"]
        ocr_confidence = float(rows[0]["ocr_confidence"])

        result = ForgeryDetectionService.evaluate_document(
            org_id=org_id,
            document_id=document_id,
            doc_type=doc_type,
            ocr_confidence=ocr_confidence,
            actor_id=applicant_id,
        )

        logger.info(
            "verify_document_async: doc=%s method=%s queue=%s",
            document_id,
            result.get("verification_method"),
            result.get("review_queue"),
        )
        return {"status": "ok", **result}

    except Exception as exc:
        logger.exception(
            "verify_document_async failed for doc=%s: %s", document_id, exc
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="ai_tasks.run_document_verification",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_document_verification(
    self, tenant_id: str, doc_id: str, file_path: str, doc_type: str, actor_id: str
) -> None:
    """
    Run AI-based verification on a document in the background.
    """
    from datetime import datetime, timezone

    from server.core.ai_gateway import AIGateway, AIGatewayContext
    from server.core.audit import AuditAction, AuditLog
    from server.core.rbac import Role
    from server.db_service import execute_system_transaction

    org_id = tenant_id
    context = AIGatewayContext(
        actor_id="document_verifier_v1",
        actor_role=Role.SYSTEM,
        actor_type="ai_agent",
        org_id=org_id,
        module="M1",
        wizard="Document Verification",
    )

    try:
        with open(file_path, "rb") as f:
            content_sample = f.read(4096)
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
        is_verified = "VERIFIED" in vo.decision.upper() and vo.confidence_score >= 0.6
        detail = vo.reasoning or vo.decision

    now = datetime.now(timezone.utc)
    execute_system_transaction(
        [
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
                    "AI_AUTO",  # hardcoding to match DocumentVerificationMethod.AI_AUTO
                    detail[:500],
                    "ai_agent:document_verifier_v1",
                    now,
                    doc_id,
                    org_id,
                ),
            )
        ]
    )

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
            "method": "AI_AUTO",
            "detail": detail,
        },
    )
