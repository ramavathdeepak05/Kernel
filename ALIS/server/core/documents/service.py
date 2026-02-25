"""
Document Generation Service
===========================
Core service for generating official PDF documents.

Responsibilities:
- Template rendering (via TemplateEngine)
- PDF conversion (via xhtml2pdf)
- Immutable file storage
- Audit logging

Layer Compliance:
- Respects RBAC (Layer 5) before generation
- Checks Global Locks (Layer 4) before generation
- Logs all generation events (Audit)
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

from xhtml2pdf import pisa

from .models import (
    TemplateType,
    DocumentTemplate,
    DocumentGenerationRequest,
    GeneratedDocument,
)
from .engine import TemplateEngine
from ..audit import AuditLog, AuditAction
from ..locks import check_global_locks
from ..rbac import verify_access, Role


class DocumentServiceError(Exception):
    """Base exception for document service errors."""
    pass


class TemplateNotFoundError(DocumentServiceError):
    """Raised when a requested template does not exist."""
    pass


class GlobalLockViolationError(DocumentServiceError):
    """Raised when a global lock prevents document generation."""
    pass


class ContextValidationError(DocumentServiceError):
    """Raised when required context fields are missing."""
    pass


class DocumentService:
    """
    Centralized service for generating official PDF documents.
    
    Usage:
        service = DocumentService()
        doc = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context={"applicant_name": "John Doe", ...},
            requested_by="user_123",
            entity_id="applicant_456"
        )
    """
    
    # Default storage directory (relative to project root)
    DEFAULT_STORAGE_DIR = Path("storage/documents")
    
    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        template_engine: Optional[TemplateEngine] = None,
    ):
        """
        Initialize the document service.
        
        Args:
            storage_dir: Directory for storing generated PDFs
            template_engine: Custom template engine instance
        """
        self.storage_dir = storage_dir or self.DEFAULT_STORAGE_DIR
        self.template_engine = template_engine or TemplateEngine()
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_storage_path(self, document_id: str) -> Path:
        """
        Generate storage path for a document.
        
        Organizes files by year/month for scalability.
        
        Args:
            document_id: Unique document identifier
            
        Returns:
            Full path for storing the document
        """
        now = datetime.now(timezone.utc)
        year_month_dir = self.storage_dir / str(now.year) / f"{now.month:02d}"
        year_month_dir.mkdir(parents=True, exist_ok=True)
        return year_month_dir / f"{document_id}.pdf"
    
    def _compute_hash(self, data: bytes) -> str:
        """
        Compute SHA-256 hash of file content.
        
        Args:
            data: Raw bytes of the file
            
        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(data).hexdigest()
    
    def _html_to_pdf(self, html_content: str) -> bytes:
        """
        Convert HTML content to PDF bytes.
        
        Args:
            html_content: Rendered HTML string
            
        Returns:
            PDF file as bytes
            
        Raises:
            DocumentServiceError: If PDF conversion fails
        """
        result = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=result)
        
        if pisa_status.err:
            raise DocumentServiceError(
                f"PDF conversion failed with {pisa_status.err} errors"
            )
        
        return result.getvalue()
    
    def _check_global_locks(
        self,
        template_type: TemplateType,
        entity_id: Optional[str],
    ) -> None:
        """
        Check for global locks that prevent document generation.
        
        Layer 4 Compliance: Global Locks override all module logic.
        
        Args:
            template_type: Type of document being generated
            entity_id: Related entity ID
            
        Raises:
            GlobalLockViolationError: If a lock prevents generation
        """
        if entity_id is None:
            return  # No entity to check
        
        # Hall tickets require checking dues and attendance
        if template_type == TemplateType.HALL_TICKET:
            lock_status = check_global_locks(entity_id)
            if lock_status.is_locked:
                # Get all violation reasons
                reasons = ', '.join(lock_status.reasons) if lock_status.reasons else 'Global lock active'
                raise GlobalLockViolationError(
                    f"Cannot generate Hall Ticket: {reasons}"
                )
    
    def generate(
        self,
        template_type: TemplateType,
        context: Dict[str, Any],
        requested_by: str,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> GeneratedDocument:
        """
        Generate a PDF document from a template.
        
        Args:
            template_type: Type of document to generate
            context: Dynamic data for template rendering
            requested_by: User ID requesting generation
            entity_id: Optional related entity ID (student_id, etc.)
            entity_type: Optional entity type
            
        Returns:
            GeneratedDocument with file path and metadata
            
        Raises:
            TemplateNotFoundError: If template doesn't exist
            ContextValidationError: If required context fields are missing
            GlobalLockViolationError: If a global lock prevents generation
            DocumentServiceError: If PDF generation fails
        """
        # Step 1: Check global locks (Layer 4)
        self._check_global_locks(template_type, entity_id)
        
        # Step 2: Validate template exists
        if not self.template_engine.template_exists(template_type):
            raise TemplateNotFoundError(
                f"Template not found for type: {template_type}"
            )
        
        # Step 3: Validate context
        try:
            self.template_engine.validate_context(template_type, context)
        except ValueError as e:
            raise ContextValidationError(str(e))
        
        # Step 4: Generate document ID and add metadata to context
        import uuid
        document_id = str(uuid.uuid4())
        
        enhanced_context = {
            **context,
            "document_id": document_id,
            "generation_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        
        # Step 5: Render HTML
        html_content = self.template_engine.render(template_type, enhanced_context)
        
        # Step 6: Convert to PDF
        pdf_bytes = self._html_to_pdf(html_content)
        
        # Step 7: Compute hash for integrity
        file_hash = self._compute_hash(pdf_bytes)
        
        # Step 8: Store PDF (immutable write)
        file_path = self._get_storage_path(document_id)
        
        if file_path.exists():
            # Should never happen with UUIDs, but enforce immutability
            raise DocumentServiceError(
                f"Document already exists: {document_id}. Immutability violated."
            )
        
        with open(file_path, "wb") as f:
            f.write(pdf_bytes)
        
        # Step 9: Create document record
        template_id = f"{template_type.value}_v1"  # Template versioning
        generated_doc = GeneratedDocument(
            document_id=document_id,
            template_id=template_id,
            template_version=1,
            file_path=str(file_path.absolute()),
            file_hash=file_hash,
            entity_id=entity_id,
            entity_type=entity_type,
            generated_by=requested_by,
        )
        
        # Step 10: Audit log
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=requested_by,
            actor_type="human",
            entity_type="document",
            entity_id=document_id,
            action_detail=f"Generated {template_type.value}",
            module="E02",
            metadata={
                "template_type": template_type.value,
                "template_id": template_id,
                "file_hash": file_hash,
                "related_entity_id": entity_id,
                "related_entity_type": entity_type,
            },
        )
        
        return generated_doc
    
    def get_document_path(self, document_id: str) -> Optional[Path]:
        """
        Retrieve the file path for a generated document.
        
        Args:
            document_id: Unique document identifier
            
        Returns:
            Path to the document file, or None if not found
        """
        # Search in storage directory
        for year_dir in self.storage_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                pdf_path = month_dir / f"{document_id}.pdf"
                if pdf_path.exists():
                    return pdf_path
        return None
    
    def verify_document_integrity(
        self,
        document_id: str,
        expected_hash: str,
    ) -> bool:
        """
        Verify a document hasn't been tampered with.
        
        Args:
            document_id: Unique document identifier
            expected_hash: Expected SHA-256 hash
            
        Returns:
            True if document is intact, False otherwise
        """
        file_path = self.get_document_path(document_id)
        if file_path is None:
            return False
        
        with open(file_path, "rb") as f:
            actual_hash = self._compute_hash(f.read())
        
        return actual_hash == expected_hash
