"""
AI background tasks — P0-S10

Celery tasks for AI workloads: embedding ETL, document OCR, async LLM inference.
"""

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
# E04 — Async document verification (stub — implemented in E04)
# =============================================================================

@celery_app.task(name="ai_tasks.verify_document_async", bind=True, max_retries=2)
def verify_document_async(self, org_id: str, document_id: str, applicant_id: str) -> dict:
    """
    Run AI document verification asynchronously.
    Full implementation tied to E04 document_verification.py.
    """
    raise NotImplementedError("E04: Async document verification not yet implemented")
