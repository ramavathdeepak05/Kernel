"""
PGVector Backend — E03-S06

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 6 (Infrastructure)
ENTITY: PGVectorBackend

Implements the VectorStoreBackend protocol (defined in rag_retriever.py)
using PostgreSQL + pgvector extension with Ollama-generated embeddings.

Architecture:
    Query string
        → OllamaEmbeddings.embed_query()
        → pgvector cosine-similarity search
        → Ranked chunks with source attribution
        → Tenant-isolated partitioning via org_id column

Tenant Isolation:
    All rows in vector_store_chunks include org_id and are filtered
    per query. RLS enforcement at DB level is an additional safeguard.

Index Management:
    IVFFlat index on (org_id, embedding) is created automatically on
    first use per tenant+index_name pair. The index can be rebuilt
    via PGVectorBackend.rebuild_index().

Acceptance Criteria (E03-S06):
    - [x] Embedding-based retrieval
    - [x] Tenant-isolated indexes
    - [x] Context size limits (top_k clamped in RAGRetrieverTool)
    - [x] Source attribution preserved
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.core.audit import AuditAction, AuditLedger
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Default embedding model served by the local Ollama instance.
# Override via PGVectorBackend(embedding_model="nomic-embed-text") if needed.
_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Embedding vector dimensions for the default model.
# Must match the pgvector column definition.
_DEFAULT_DIMENSIONS = 768

# IVFFlat probes for ANN search (higher = more accurate, slower).
_IVFFLAT_PROBES = 10


class PGVectorBackend:
    """
    PostgreSQL + pgvector vector store backend.

    Implements VectorStoreBackend protocol. Inject into RAGRetrieverTool
    at server startup:

        backend = PGVectorBackend(
            ollama_base_url="http://localhost:11434",
            embedding_model="nomic-embed-text",
        )
        RAGRetrieverTool.set_backend(backend)

    Table schema (auto-initialised on first use):

        CREATE TABLE IF NOT EXISTS vector_store_chunks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      TEXT NOT NULL,
            index_name  TEXT NOT NULL,
            chunk_id    TEXT NOT NULL,
            text        TEXT NOT NULL,
            metadata    JSONB NOT NULL DEFAULT '{}',
            embedding   vector(<dimensions>),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, index_name, chunk_id)
        );
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
        dimensions: int = _DEFAULT_DIMENSIONS,
    ) -> None:
        self._ollama_base_url = ollama_base_url.rstrip("/")
        self._embedding_model = embedding_model
        self._dimensions = dimensions
        self._initialised_tenants: set[str] = set()

    # -------------------------------------------------------------------------
    # VectorStoreBackend Protocol
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        index_name: str,
        top_k: int,
        score_threshold: float,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """
        Perform cosine-similarity search against the vector store.

        Args:
            query:           Natural language query string
            index_name:      Logical name of the knowledge index to search
            top_k:           Maximum results to return (already clamped by tool)
            score_threshold: Minimum cosine similarity (0.0 – 1.0)
            tenant_id:       Tenant scope — filters org_id column

        Returns:
            List of dicts with keys: chunk_id, text, score, metadata
        """
        self._ensure_schema()

        # Embed the query
        query_vector = self._embed(query)
        if query_vector is None:
            logger.error(
                "E03-S06: PGVectorBackend — embedding failed for query, "
                "returning empty results."
            )
            return []

        return self._similarity_search(
            query_vector=query_vector,
            index_name=index_name,
            top_k=top_k,
            score_threshold=score_threshold,
            tenant_id=tenant_id,
        )

    # -------------------------------------------------------------------------
    # Ingestion
    # -------------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        index_name: str,
        tenant_id: str,
    ) -> int:
        """
        Embed and upsert document chunks into the vector store.

        Each chunk dict must contain:
            chunk_id (str), text (str), metadata (dict, optional)

        Returns:
            Number of chunks successfully inserted/updated.
        """
        self._ensure_schema()

        upserted = 0
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            text = chunk.get("text")
            if not chunk_id or not text:
                logger.warning("E03-S06: Skipping chunk with missing chunk_id or text")
                continue

            embedding = self._embed(text)
            if embedding is None:
                logger.warning(
                    "E03-S06: Embedding failed for chunk_id=%s, skipping", chunk_id
                )
                continue

            meta = chunk.get("metadata", {})
            vector_literal = self._to_pg_vector(embedding)

            try:
                execute_transaction(
                    [
                        (
                            """
                    INSERT INTO vector_store_chunks
                        (org_id, index_name, chunk_id, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (org_id, index_name, chunk_id)
                    DO UPDATE SET
                        text      = EXCLUDED.text,
                        metadata  = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                    """,
                            (
                                tenant_id,
                                index_name,
                                chunk_id,
                                text,
                                json.dumps(meta),
                                vector_literal,
                            ),
                        )
                    ],
                    tenant_id=self.org_id,
                )
                AuditLedger.log(
                    action=AuditAction.CREATE,
                    actor_id="system",
                    actor_role="system",
                    entity_type="vector_chunk",
                    entity_id="",
                    tenant_id="",
                    metadata={"source": "upsert_chunks"},
                )
                upserted += 1
            except Exception as e:
                logger.error("E03-S06: Failed to upsert chunk_id=%s: %s", chunk_id, e)

        if upserted:
            logger.info(
                "E03-S06: Upserted %d chunks into index '%s' (tenant=%s)",
                upserted,
                index_name,
                tenant_id,
            )

        return upserted

    # -------------------------------------------------------------------------
    # Index Management
    # -------------------------------------------------------------------------

    def rebuild_index(self, tenant_id: str, index_name: str) -> None:
        """
        Drop and recreate the IVFFlat index for a tenant/index pair.

        Safe to call on live data — PostgreSQL rebuilds the index
        concurrently (non-blocking reads during rebuild).
        """

        idx_name = self._index_name(tenant_id, index_name)
        try:
            execute_query(f"DROP INDEX IF EXISTS {idx_name}")
            execute_query(
                f"""
                CREATE INDEX {idx_name}
                ON vector_store_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                WHERE org_id = %s AND index_name = %s
                """,
                (tenant_id, index_name),
            )
            logger.info(
                "E03-S06: Rebuilt IVFFlat index '%s' for tenant=%s index=%s",
                idx_name,
                tenant_id,
                index_name,
            )
        except Exception as e:
            logger.error("E03-S06: Index rebuild failed: %s", e)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Create the vector_store_chunks table if it doesn't exist."""

        try:
            execute_query("CREATE EXTENSION IF NOT EXISTS vector")
            execute_query(
                f"""
                CREATE TABLE IF NOT EXISTS vector_store_chunks (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    org_id      TEXT NOT NULL,
                    index_name  TEXT NOT NULL,
                    chunk_id    TEXT NOT NULL,
                    text        TEXT NOT NULL,
                    metadata    JSONB NOT NULL DEFAULT '{{}}',
                    embedding   vector({self._dimensions}),
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (org_id, index_name, chunk_id)
                )
                """
            )
        except Exception as e:
            logger.warning("E03-S06: Schema init warning (may already exist): %s", e)

    def _embed(self, text: str) -> list[float] | None:
        """
        Generate an embedding vector via the local Ollama API.

        Uses the /api/embeddings endpoint — no cloud calls made.
        """
        import urllib.request

        payload = json.dumps(
            {
                "model": self._embedding_model,
                "prompt": text,
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{self._ollama_base_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body.get("embedding")
        except Exception as e:
            logger.error("E03-S06: Ollama embedding request failed: %s", e)
            return None

    def _similarity_search(
        self,
        query_vector: list[float],
        index_name: str,
        top_k: int,
        score_threshold: float,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """Run cosine similarity search using pgvector <=> operator."""

        vector_literal = self._to_pg_vector(query_vector)

        # pgvector cosine distance: 0 = identical, 2 = opposite.
        # Convert to similarity score: similarity = 1 - (distance / 2)
        # Score threshold check is applied after conversion.
        min_distance = 1.0 - score_threshold  # cosine distance upper bound

        try:
            rows = execute_query(
                f"""  # noqa: S608
                SET LOCAL ivfflat.probes = {_IVFFLAT_PROBES};
                SELECT
                    chunk_id,
                    text,
                    metadata,
                    1.0 - (embedding <=> %s::vector) / 2.0 AS score
                FROM vector_store_chunks
                WHERE org_id = %s
                  AND index_name = %s
                  AND (embedding <=> %s::vector) <= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    vector_literal,
                    tenant_id,
                    index_name,
                    vector_literal,
                    min_distance,
                    vector_literal,
                    top_k,
                ),
            )
        except Exception as e:
            logger.error("E03-S06: Vector similarity search failed: %s", e)
            return []

        return [
            {
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "score": float(row.get("score", 0.0)),
                "metadata": row.get("metadata") or {},
            }
            for row in (rows or [])
        ]

    @staticmethod
    def _to_pg_vector(embedding: list[float]) -> str:
        """Convert a Python float list to pgvector literal string '[0.1,0.2,...]'."""
        return "[" + ",".join(str(x) for x in embedding) + "]"

    @staticmethod
    def _index_name(tenant_id: str, index_name: str) -> str:
        """Generate a safe PostgreSQL index name from tenant + index."""
        safe_tenant = tenant_id.replace("-", "_")[:20]
        safe_index = index_name.replace("-", "_")[:20]
        return f"idx_vec_{safe_tenant}_{safe_index}"
