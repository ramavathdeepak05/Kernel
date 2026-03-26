"""Vector store backends for ALIS RAG pipeline (E03-S06)."""
from __future__ import annotations

from .pgvector_backend import PGVectorBackend

__all__ = ["PGVectorBackend"]
