"""Vector store backends for ALIS RAG pipeline (E03-S06)."""

from .pgvector_backend import PGVectorBackend

__all__ = ["PGVectorBackend"]
