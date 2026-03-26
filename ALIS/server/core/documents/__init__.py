"""
ALIS Document Generation Service
================================
Centralized service for generating official PDF documents.

Part of E02 - Shared Services.
"""
from __future__ import annotations
from .service import DocumentService
from .models import (
    TemplateType,
    DocumentTemplate,
    GeneratedDocument,
    DocumentGenerationRequest,
)

__all__ = [
    "DocumentService",
    "TemplateType",
    "DocumentTemplate",
    "GeneratedDocument",
    "DocumentGenerationRequest",
]
