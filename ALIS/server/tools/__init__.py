"""
ALIS Tool Implementations — E03-S05

All tools are registered here at import time.
Import this module during server startup to ensure tools are available.

Registered tools:
    tool.policy.lookup        — PolicyLookupTool
    tool.rag.retriever        — RAGRetrieverTool (PGVector backend injected)
    tool.rubric.validator     — RubricValidatorTool
    tool.scoring.structured   — StructuredScoringTool
"""
from __future__ import annotations

import logging
import os

from server.core.tool_registry import ToolRegistry

from .policy_lookup import PolicyLookupTool
from .rag_retriever import RAGRetrieverTool
from .rubric_validator import RubricValidatorTool
from .structured_scoring import StructuredScoringTool

logger = logging.getLogger(__name__)


def register_all_tools() -> None:
    """
    Register all ALIS tools into the ToolRegistry.

    Also injects the PGVectorBackend into RAGRetrieverTool (E03-S06)
    when the database is available. Falls back to the stub backend
    (returns empty results) if pgvector is not yet configured.
    """
    ToolRegistry.register(PolicyLookupTool())
    ToolRegistry.register(RAGRetrieverTool())
    ToolRegistry.register(RubricValidatorTool())
    ToolRegistry.register(StructuredScoringTool())

    # --- E03-S06: Inject PGVector backend into RAGRetrieverTool ---
    _inject_pgvector_backend()


def _inject_pgvector_backend() -> None:
    """
    Inject PGVectorBackend into RAGRetrieverTool.

    Uses the Ollama base URL from ConfigRegistry. If injection fails
    (e.g., during unit tests without a DB), the stub backend is kept
    and a warning is logged.
    """
    try:
        from server.core.config import ConfigRegistry
        from .backends.pgvector_backend import PGVectorBackend

        ollama_url = ConfigRegistry.get(
            ConfigRegistry.LLM_BASE_URL,
            "http://localhost:11434",
        )
        embedding_model = ConfigRegistry.get(
            "ai.embedding_model",
            "nomic-embed-text",
        )

        backend = PGVectorBackend(
            ollama_base_url=ollama_url,
            embedding_model=embedding_model,
        )
        RAGRetrieverTool.set_backend(backend)
        logger.info(
            "E03-S06: PGVectorBackend injected into RAGRetrieverTool "
            "(model=%s, ollama=%s)",
            embedding_model, ollama_url,
        )
    except Exception as e:
        logger.warning(
            "E03-S06: PGVectorBackend injection failed — using stub backend. "
            "RAG will return empty results until resolved. Error: %s", e,
        )


__all__ = [
    "PolicyLookupTool",
    "RAGRetrieverTool",
    "RubricValidatorTool",
    "StructuredScoringTool",
    "register_all_tools",
]
