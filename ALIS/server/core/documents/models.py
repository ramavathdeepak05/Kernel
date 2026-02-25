"""
Document Generation Models
==========================
Pydantic models for document templates and generated documents.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class TemplateType(str, Enum):
    """Supported document template types."""
    OFFER_LETTER = "offer_letter"
    HALL_TICKET = "hall_ticket"
    RECEIPT = "receipt"
    CERTIFICATE = "certificate"
    TRANSCRIPT = "transcript"


class DocumentTemplate(BaseModel):
    """
    Represents a versioned document template.
    
    Templates are HTML/CSS files rendered with Jinja2.
    """
    template_id: str = Field(..., description="Unique template identifier")
    template_type: TemplateType = Field(..., description="Type of document")
    version: int = Field(default=1, ge=1, description="Template version number")
    name: str = Field(..., description="Human-readable template name")
    file_path: str = Field(..., description="Path to template file relative to templates dir")
    is_active: bool = Field(default=True, description="Whether template is currently active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        frozen = True  # Immutable after creation


class DocumentGenerationRequest(BaseModel):
    """
    Request to generate a document.
    
    Contains template reference and dynamic data context.
    """
    template_type: TemplateType = Field(..., description="Type of document to generate")
    context: Dict[str, Any] = Field(..., description="Dynamic data for template rendering")
    requested_by: str = Field(..., description="User ID requesting generation")
    entity_id: Optional[str] = Field(None, description="Related entity ID (student_id, etc.)")
    entity_type: Optional[str] = Field(None, description="Related entity type")


class GeneratedDocument(BaseModel):
    """
    Represents an immutable generated document.
    
    Once created, the document cannot be modified.
    """
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(..., description="Template used for generation")
    template_version: int = Field(..., description="Template version at time of generation")
    file_path: str = Field(..., description="Absolute path to generated PDF")
    file_hash: str = Field(..., description="SHA-256 hash of generated file")
    entity_id: Optional[str] = Field(None, description="Related entity ID")
    entity_type: Optional[str] = Field(None, description="Related entity type")
    generated_by: str = Field(..., description="User ID who generated the document")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        frozen = True  # Immutable after creation
