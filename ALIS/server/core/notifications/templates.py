"""
ALIS Notification Templates - E02-S03

MODULE: Shared Services
LAYER: Layer 2 (Template Management)

This module manages notification templates with variable substitution.
Templates are stored in a registry and rendered with context data.

Must Align With:
- Policy configurable (templates can be updated)
- No domain logic (templates are content only)
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from string import Template
import logging


logger = logging.getLogger(__name__)


# --- Template Definition ---

@dataclass
class NotificationTemplate:
    """
    A notification template with subject and body.
    
    Uses Python's string.Template for safe substitution.
    Variables are specified as $variable or ${variable}.
    """
    id: str
    name: str
    subject_template: str  # For email; can be empty for SMS/WhatsApp
    body_template: str
    description: Optional[str] = None
    
    def render(self, context: Dict[str, Any]) -> Tuple[str, str]:
        """
        Render the template with the given context.
        
        Args:
            context: Dictionary of variable values
            
        Returns:
            Tuple of (rendered_subject, rendered_body)
        """
        try:
            subject = Template(self.subject_template).safe_substitute(context)
            body = Template(self.body_template).safe_substitute(context)
            return subject, body
        except Exception as e:
            logger.error(f"Template render failed for {self.id}: {str(e)}")
            raise ValueError(f"Failed to render template {self.id}: {str(e)}")


# --- Template Registry ---

class TemplateRegistry:
    """
    Central registry for notification templates.
    
    Provides CRUD operations for templates and seeded defaults.
    """
    
    _templates: Dict[str, NotificationTemplate] = {}
    
    # Pre-defined template IDs
    WELCOME_EMAIL = "welcome_email"
    PASSWORD_RESET = "password_reset"
    WORKFLOW_APPROVED = "workflow_approved"
    WORKFLOW_REJECTED = "workflow_rejected"
    GENERIC_ALERT = "generic_alert"
    
    @classmethod
    def initialize_defaults(cls) -> None:
        """Seed default templates."""
        defaults = [
            NotificationTemplate(
                id=cls.WELCOME_EMAIL,
                name="Welcome Email",
                subject_template="Welcome to ALIS, $name!",
                body_template="""Dear $name,

Welcome to the ALIS platform. Your account has been successfully created.

Username: $username
Organization: $org_name

Please log in to complete your profile setup.

Best regards,
ALIS System""",
                description="Sent when a new user is created"
            ),
            NotificationTemplate(
                id=cls.PASSWORD_RESET,
                name="Password Reset",
                subject_template="Password Reset Request",
                body_template="""Dear $name,

A password reset was requested for your ALIS account.

If you did not request this, please ignore this message.

To reset your password, use the following code: $reset_code

This code expires in $expiry_minutes minutes.

Best regards,
ALIS System""",
                description="Sent for password reset requests"
            ),
            NotificationTemplate(
                id=cls.WORKFLOW_APPROVED,
                name="Workflow Approved",
                subject_template="[$workflow_type] Approved",
                body_template="""Dear $name,

Your request has been approved.

Workflow: $workflow_type
Reference: $workflow_id
Approved by: $approver_name

Best regards,
ALIS System""",
                description="Sent when a workflow is approved"
            ),
            NotificationTemplate(
                id=cls.WORKFLOW_REJECTED,
                name="Workflow Rejected",
                subject_template="[$workflow_type] Rejected",
                body_template="""Dear $name,

Your request has been rejected.

Workflow: $workflow_type
Reference: $workflow_id
Rejected by: $rejector_name
Reason: $reason

Best regards,
ALIS System""",
                description="Sent when a workflow is rejected"
            ),
            NotificationTemplate(
                id=cls.GENERIC_ALERT,
                name="Generic Alert",
                subject_template="ALIS Alert: $title",
                body_template="""$message""",
                description="Generic alert template"
            ),
        ]
        
        for template in defaults:
            if template.id not in cls._templates:
                cls._templates[template.id] = template
    
    @classmethod
    def get(cls, template_id: str) -> Optional[NotificationTemplate]:
        """Get a template by ID."""
        return cls._templates.get(template_id)
    
    @classmethod
    def register(cls, template: NotificationTemplate) -> None:
        """Register a new template or update existing."""
        cls._templates[template.id] = template
        logger.info(f"Template registered: {template.id}")
    
    @classmethod
    def list_all(cls) -> Dict[str, NotificationTemplate]:
        """Get all registered templates."""
        return cls._templates.copy()
    
    @classmethod
    def render(
        cls,
        template_id: str,
        context: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Convenience method to get and render a template.
        
        Args:
            template_id: ID of the template
            context: Variables for substitution
            
        Returns:
            Tuple of (subject, body)
            
        Raises:
            ValueError: If template not found
        """
        template = cls.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")
        return template.render(context)


# Initialize defaults on module load
TemplateRegistry.initialize_defaults()
