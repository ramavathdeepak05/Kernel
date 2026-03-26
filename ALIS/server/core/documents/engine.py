"""
Template Engine
===============
Jinja2-based template rendering for document generation.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from .models import TemplateType


class TemplateEngine:
    """
    Handles loading and rendering of document templates.
    
    Uses Jinja2 with HTML templates stored in the templates directory.
    """
    
    # Base path for templates (relative to this file)
    TEMPLATES_DIR = Path(__file__).parent / "templates"
    
    # Template file mapping
    TEMPLATE_FILES: Dict[TemplateType, str] = {
        TemplateType.OFFER_LETTER: "offer_letter.html",
        TemplateType.HALL_TICKET: "hall_ticket.html",
        TemplateType.RECEIPT: "receipt.html",
        TemplateType.CERTIFICATE: "certificate.html",
        TemplateType.TRANSCRIPT: "transcript.html",
    }
    
    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the template engine.
        
        Args:
            templates_dir: Optional custom templates directory
        """
        self.templates_dir = templates_dir or self.TEMPLATES_DIR
        
        # Ensure templates directory exists
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja2 environment
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    
    def get_template_path(self, template_type: TemplateType) -> str:
        """
        Get the file path for a template type.
        
        Args:
            template_type: Type of document template
            
        Returns:
            Relative path to template file
            
        Raises:
            ValueError: If template type is not supported
        """
        if template_type not in self.TEMPLATE_FILES:
            raise ValueError(f"Unsupported template type: {template_type}")
        return self.TEMPLATE_FILES[template_type]
    
    def template_exists(self, template_type: TemplateType) -> bool:
        """
        Check if a template file exists.
        
        Args:
            template_type: Type of document template
            
        Returns:
            True if template file exists
        """
        try:
            template_path = self.get_template_path(template_type)
            full_path = self.templates_dir / template_path
            return full_path.exists()
        except ValueError:
            return False
    
    def render(self, template_type: TemplateType, context: Dict[str, Any]) -> str:
        """
        Render a template with the given context.
        
        Args:
            template_type: Type of document template
            context: Dictionary of variables for template rendering
            
        Returns:
            Rendered HTML string
            
        Raises:
            TemplateNotFound: If template file doesn't exist
            ValueError: If template type is not supported
        """
        template_path = self.get_template_path(template_type)
        
        try:
            template = self._env.get_template(template_path)
            return template.render(**context)
        except TemplateNotFound:
            raise TemplateNotFound(
                f"Template not found: {template_path}. "
                f"Ensure the file exists in {self.templates_dir}"
            )
    
    def validate_context(self, template_type: TemplateType, context: Dict[str, Any]) -> bool:
        """
        Validate that all required context variables are present.
        
        Args:
            template_type: Type of document template
            context: Dictionary of variables for template rendering
            
        Returns:
            True if all required variables are present
            
        Note:
            This is a basic validation. Templates should handle missing
            variables gracefully with defaults or clear error messages.
        """
        # Template-specific required fields
        required_fields: Dict[TemplateType, list] = {
            TemplateType.OFFER_LETTER: ["applicant_name", "program_name", "offer_date"],
            TemplateType.HALL_TICKET: ["student_name", "roll_number", "exam_name", "exam_date"],
            TemplateType.RECEIPT: ["student_name", "amount", "payment_date", "receipt_number"],
            TemplateType.CERTIFICATE: ["student_name", "certificate_type", "issue_date"],
            TemplateType.TRANSCRIPT: ["student_name", "roll_number", "courses"],
        }
        
        required = required_fields.get(template_type, [])
        missing = [field for field in required if field not in context]
        
        if missing:
            raise ValueError(f"Missing required context fields: {missing}")
        
        return True
