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

@celery_app.task(name="ai_tasks.upsert_counsellor_embedding", bind=True, max_retries=2, default_retry_delay=30)
def upsert_counsellor_embedding(self, org_id: str, counsellor_id: str, profile_text: str) -> dict:
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
    from server.db_service import execute_transaction

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
        execute_transaction([
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
        ])

        logger.info(
            "P0-S10: Counsellor embedding upserted — org=%s counsellor=%s dims=%d",
            org_id, counsellor_id, len(embedding),
        )
        return {"status": "ok", "counsellor_id": counsellor_id, "dims": len(embedding)}

    except httpx.HTTPError as exc:
        logger.warning("P0-S10: Ollama embed request failed: %s — retrying", exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error("P0-S10: Embedding ETL failed for counsellor %s: %s", counsellor_id, exc)
        raise self.retry(exc=exc)


# =============================================================================
# E04 — Async document verification
# =============================================================================

@celery_app.task(name="ai_tasks.verify_document_async", bind=True, max_retries=3, default_retry_delay=30)
def verify_document_async(self, org_id: str, document_id: str, applicant_id: str) -> dict:
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
    from server.db_service import execute_query

    try:
        rows = execute_query(
            """
            SELECT doc_type, COALESCE(confidence_score, 0.7) AS ocr_confidence
            FROM application_documents
            WHERE id = %s AND org_id = %s
            """,
            (document_id, org_id),
        )
        if not rows:
            logger.error("verify_document_async: document %s not found in org %s", document_id, org_id)
            return {"status": "not_found", "document_id": document_id}

        doc_type       = rows[0]["doc_type"]
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
        logger.exception("verify_document_async failed for doc=%s: %s", document_id, exc)
        raise self.retry(exc=exc)
