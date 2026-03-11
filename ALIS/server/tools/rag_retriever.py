"""
RAGRetrieverTool — E03-S05

Retrieval-Augmented Generation (RAG) tool. Performs semantic search
over a configured vector store and returns ranked document chunks
for AI context injection.

This tool implements the RAG pipeline defined in ALIS Blueprint
Section 13 (RAG Architecture). All RAG access MUST go through this
tool — no agent may call the vector store directly.

Architecture:
    Query → Embedding → VectorStore.search() → Ranked Chunks → ToolOutputSchema

Input schema:
    {
        "query": str,              # Natural language query
        "index_name": str,         # Vector index to search (e.g. "policies", "syllabi")
        "top_k": int,              # Max results to return (default: 5, max: 20)
        "score_threshold": float   # Min similarity score (default: 0.0, range: 0-1)
    }

Output data keys:
    {
        "query": str,
        "index_name": str,
        "chunks": [
            {
                "chunk_id": str,
                "text": str,
                "score": float,
                "metadata": dict
            },
            ...
        ],
        "total_retrieved": int
    }

Vector Store Backend:
    Injected via RAGRetrieverTool.set_backend(). Default is a stub that
    returns empty results. In production, inject a QdrantBackend or
    PGVectorBackend instance.
"""

from typing import Any, ClassVar, Dict, List, Optional, Protocol, runtime_checkable

from server.core.tool_registry import BaseTool, ToolOutputSchema
from server.core.exceptions import ToolSchemaViolationError


# =============================================================================
# VECTOR STORE BACKEND PROTOCOL
# =============================================================================

@runtime_checkable
class VectorStoreBackend(Protocol):
    """
    Protocol for vector store backends.

    Implement this protocol for Qdrant, PGVector, or any other
    vector store. Inject via RAGRetrieverTool.set_backend().
    """

    def search(
        self,
        query: str,
        index_name: str,
        top_k: int,
        score_threshold: float,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search.

        Args:
            query:           Natural language query string
            index_name:      Target vector index name
            top_k:           Maximum number of results
            score_threshold: Minimum similarity score (0.0 - 1.0)
            tenant_id:       Tenant scope for data isolation

        Returns:
            List of dicts, each with:
                chunk_id (str), text (str), score (float), metadata (dict)
        """
        ...  # pragma: no cover


class _StubVectorBackend:
    """
    Stub backend used when no real vector store is configured.
    Returns empty results. Replace with QdrantBackend in production.
    """

    def search(
        self,
        query: str,
        index_name: str,
        top_k: int,
        score_threshold: float,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        import logging
        logging.getLogger(__name__).warning(
            "RAGRetrieverTool: No vector backend configured — "
            "returning empty results. Inject a backend via "
            "RAGRetrieverTool.set_backend()."
        )
        return []


# =============================================================================
# RAG RETRIEVER TOOL
# =============================================================================

class RAGRetrieverTool(BaseTool):
    """
    Semantic search tool using the configured vector store backend.

    RAG is implemented through this tool per E03-S05 and Blueprint B
    Section 13. Agents that need institutional knowledge (policies,
    syllabi, research papers) must use this tool — no direct vector
    store access is permitted.

    Backend injection:
        RAGRetrieverTool.set_backend(QdrantBackend(...))
    """

    tool_id: ClassVar[str] = "tool.rag.retriever"
    version: ClassVar[int] = 1
    description: ClassVar[str] = (
        "Performs semantic search over institutional knowledge indexes "
        "(policies, syllabi, research) and returns ranked text chunks "
        "for RAG context injection."
    )
    read_only: ClassVar[bool] = True

    _MAX_TOP_K: ClassVar[int] = 20
    _DEFAULT_TOP_K: ClassVar[int] = 5
    _DEFAULT_SCORE_THRESHOLD: ClassVar[float] = 0.0

    # Class-level backend (injected at startup)
    _backend: ClassVar[VectorStoreBackend] = _StubVectorBackend()

    @classmethod
    def set_backend(cls, backend: VectorStoreBackend) -> None:
        """
        Inject a vector store backend.

        Call this once during server startup:
            RAGRetrieverTool.set_backend(QdrantBackend(url="http://localhost:6333"))
        """
        cls._backend = backend

    def execute(
        self,
        input_data: Dict[str, Any],
        tenant_id: str,
    ) -> ToolOutputSchema:
        """
        Execute semantic search.

        Args:
            input_data: Must contain "query" (str) and "index_name" (str).
                        Optional: "top_k" (int), "score_threshold" (float).
            tenant_id:  Tenant scope for data isolation.

        Returns:
            ToolOutputSchema with ranked chunks in data["chunks"].

        Raises:
            ToolSchemaViolationError: If required inputs are missing.
        """
        query = input_data.get("query")
        if not query or not isinstance(query, str):
            raise ToolSchemaViolationError(
                message="RAGRetrieverTool requires 'query' (str) in input_data.",
                details={"received_keys": list(input_data.keys())},
            )

        index_name = input_data.get("index_name")
        if not index_name or not isinstance(index_name, str):
            raise ToolSchemaViolationError(
                message="RAGRetrieverTool requires 'index_name' (str) in input_data.",
                details={"received_keys": list(input_data.keys())},
            )

        # Clamp top_k to safe range
        top_k = int(input_data.get("top_k", self._DEFAULT_TOP_K))
        top_k = max(1, min(top_k, self._MAX_TOP_K))

        score_threshold = float(
            input_data.get("score_threshold", self._DEFAULT_SCORE_THRESHOLD)
        )
        score_threshold = max(0.0, min(1.0, score_threshold))

        # Execute search via injected backend
        chunks = self._backend.search(
            query=query,
            index_name=index_name,
            top_k=top_k,
            score_threshold=score_threshold,
            tenant_id=tenant_id,
        )

        # Normalise chunk format
        normalised = [
            {
                "chunk_id": str(c.get("chunk_id", "")),
                "text": str(c.get("text", "")),
                "score": float(c.get("score", 0.0)),
                "metadata": c.get("metadata", {}),
            }
            for c in chunks
            if isinstance(c, dict)
        ]

        return ToolOutputSchema(
            tool_id=self.tool_id,
            tool_version=self.version,
            data={
                "query": query,
                "index_name": index_name,
                "chunks": normalised,
                "total_retrieved": len(normalised),
            },
            source=f"vector_store:{index_name}",
        )
