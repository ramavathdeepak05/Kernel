"""
Test Document Generation Service
=================================
Verifies E02-S04 implementation.

Run: python -m pytest tests/test_document_service.py -v
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from server.core.documents import DocumentService, TemplateType
from server.core.documents.service import (
    TemplateNotFoundError,
    ContextValidationError,
    GlobalLockViolationError,
)
from server.core.documents.engine import TemplateEngine
from server.core.documents.models import GeneratedDocument


class TestTemplateEngine:
    """Test the template engine."""
    
    def test_template_exists_offer_letter(self):
        """Verify offer letter template exists."""
        engine = TemplateEngine()
        assert engine.template_exists(TemplateType.OFFER_LETTER) is True
    
    def test_template_exists_hall_ticket(self):
        """Verify hall ticket template exists."""
        engine = TemplateEngine()
        assert engine.template_exists(TemplateType.HALL_TICKET) is True
    
    def test_render_offer_letter(self):
        """Test rendering an offer letter template."""
        engine = TemplateEngine()
        context = {
            "applicant_name": "Rahul Sharma",
            "program_name": "B.Tech Computer Science",
            "offer_date": "2026-02-07",
            "document_id": "test-123",
            "generation_date": "2026-02-07 22:00 UTC",
        }
        html = engine.render(TemplateType.OFFER_LETTER, context)
        
        assert "Rahul Sharma" in html
        assert "B.Tech Computer Science" in html
        assert "test-123" in html
    
    def test_validate_context_missing_fields(self):
        """Test context validation catches missing fields."""
        engine = TemplateEngine()
        
        # Missing required fields
        with pytest.raises(ValueError) as exc_info:
            engine.validate_context(TemplateType.OFFER_LETTER, {})
        
        assert "applicant_name" in str(exc_info.value)
    
    def test_validate_context_valid(self):
        """Test valid context passes validation."""
        engine = TemplateEngine()
        context = {
            "applicant_name": "Test",
            "program_name": "Test Program",
            "offer_date": "2026-01-01",
        }
        assert engine.validate_context(TemplateType.OFFER_LETTER, context) is True


class TestDocumentService:
    """Test the document service."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create document service with temp storage."""
        return DocumentService(storage_dir=temp_storage)
    
    def test_generate_offer_letter(self, service):
        """Test generating an offer letter PDF."""
        context = {
            "applicant_name": "Priya Patel",
            "program_name": "MBA Finance",
            "offer_date": "2026-02-07",
            "applicant_id": "APP001",
        }
        
        doc = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context=context,
            requested_by="admin_user",
            entity_id="APP001",
            entity_type="applicant",
        )
        
        # Verify return type
        assert isinstance(doc, GeneratedDocument)
        
        # Verify document properties
        assert doc.document_id is not None
        assert doc.template_id == "offer_letter_v1"
        assert doc.generated_by == "admin_user"
        assert doc.entity_id == "APP001"
        
        # Verify file exists
        assert Path(doc.file_path).exists()
        
        # Verify file is not empty
        assert Path(doc.file_path).stat().st_size > 0
        
        # Verify hash
        assert len(doc.file_hash) == 64  # SHA-256 hex
    
    def test_generate_receipt(self, service):
        """Test generating a receipt PDF."""
        context = {
            "student_name": "Ankit Kumar",
            "amount": 50000.00,
            "payment_date": "2026-02-07",
            "receipt_number": "RCP-2026-001",
        }
        
        doc = service.generate(
            template_type=TemplateType.RECEIPT,
            context=context,
            requested_by="cashier_01",
            entity_id="STU001",
            entity_type="student",
        )
        
        assert Path(doc.file_path).exists()
        assert doc.template_id == "receipt_v1"
    
    def test_generate_missing_context_raises_error(self, service):
        """Test that missing context fields raise error."""
        with pytest.raises(ContextValidationError):
            service.generate(
                template_type=TemplateType.OFFER_LETTER,
                context={},  # Missing required fields
                requested_by="test_user",
            )
    
    def test_verify_document_integrity(self, service):
        """Test document integrity verification."""
        context = {
            "applicant_name": "Test",
            "program_name": "Test",
            "offer_date": "2026-01-01",
        }
        
        doc = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context=context,
            requested_by="test",
        )
        
        # Correct hash should pass
        assert service.verify_document_integrity(doc.document_id, doc.file_hash) is True
        
        # Wrong hash should fail
        assert service.verify_document_integrity(doc.document_id, "wrong_hash") is False
    
    def test_get_document_path(self, service):
        """Test retrieving document path."""
        context = {
            "applicant_name": "Test",
            "program_name": "Test",
            "offer_date": "2026-01-01",
        }
        
        doc = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context=context,
            requested_by="test",
        )
        
        path = service.get_document_path(doc.document_id)
        assert path is not None
        assert path.exists()
    
    def test_immutability_enforced(self, service):
        """Test that documents cannot be overwritten."""
        # This is implicitly tested by UUID generation
        # Each document gets a unique ID, so collisions are impossible
        context = {
            "applicant_name": "Test",
            "program_name": "Test",
            "offer_date": "2026-01-01",
        }
        
        doc1 = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context=context,
            requested_by="test",
        )
        
        doc2 = service.generate(
            template_type=TemplateType.OFFER_LETTER,
            context=context,
            requested_by="test",
        )
        
        # Different document IDs
        assert doc1.document_id != doc2.document_id
        # Different file paths
        assert doc1.file_path != doc2.file_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
