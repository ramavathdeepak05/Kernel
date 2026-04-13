"""
ALIS Document Generation Service
================================
Centralized service for generating official PDF documents.

Part of E02 - Shared Services.
"""

from __future__ import annotations

from .models import (
    DocumentGenerationRequest,
    DocumentTemplate,
    GeneratedDocument,
    TemplateType,
)
from .service import DocumentService

__all__ = [
    "DocumentService",
    "TemplateType",
    "DocumentTemplate",
    "GeneratedDocument",
    "DocumentGenerationRequest",
]
