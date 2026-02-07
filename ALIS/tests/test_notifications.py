"""
E02-S03 Notification Dispatcher - Verification Tests

This script verifies the notification dispatcher implementation
meets the acceptance criteria from the JIRA task.

Run with: python -m pytest tests/test_notifications.py -v
"""

import pytest
from datetime import datetime

# Import notification components
from server.core.models import (
    NotificationStatus,
    NotificationChannel,
    NotificationLog,
)
from server.core.config import ConfigRegistry, ConfigCategory
from server.core.notifications import (
    NotificationDispatcher,
    TemplateRegistry,
    EmailChannel,
    SMSChannel,
    WhatsAppChannel,
    get_channel,
    get_dispatcher,
)


class TestNotificationModels:
    """Test notification data models."""
    
    def test_notification_status_enum(self):
        """Verify NotificationStatus enum values exist."""
        assert NotificationStatus.PENDING == "PENDING"
        assert NotificationStatus.SENT == "SENT"
        assert NotificationStatus.FAILED == "FAILED"
        assert NotificationStatus.RETRYING == "RETRYING"
    
    def test_notification_channel_enum(self):
        """Verify NotificationChannel enum values exist."""
        assert NotificationChannel.EMAIL == "EMAIL"
        assert NotificationChannel.SMS == "SMS"
        assert NotificationChannel.WHATSAPP == "WHATSAPP"
    
    def test_notification_log_creation(self):
        """Verify NotificationLog can be created."""
        log = NotificationLog(
            recipient_id="user-123",
            recipient_address="test@example.com",
            template_id="welcome_email",
            channel=NotificationChannel.EMAIL,
        )
        assert log.id is not None
        assert log.status == NotificationStatus.PENDING
        assert log.retry_count == 0


class TestNotificationConfig:
    """Test notification configuration."""
    
    def test_notification_category_exists(self):
        """Verify NOTIFICATION category in ConfigCategory."""
        assert ConfigCategory.NOTIFICATION == "notification"
    
    def test_notification_config_keys_exist(self):
        """Verify notification config keys are registered."""
        assert hasattr(ConfigRegistry, "NOTIFICATION_EMAIL_ENABLED")
        assert hasattr(ConfigRegistry, "NOTIFICATION_SMS_ENABLED")
        assert hasattr(ConfigRegistry, "NOTIFICATION_MAX_RETRIES")
    
    def test_email_enabled_by_default(self):
        """Verify email is enabled by default."""
        value = ConfigRegistry.get(ConfigRegistry.NOTIFICATION_EMAIL_ENABLED)
        assert value is True


class TestNotificationChannels:
    """Test notification channel implementations."""
    
    def test_get_channel_email(self):
        """Verify EmailChannel can be retrieved."""
        channel = get_channel("EMAIL")
        assert channel is not None
        assert isinstance(channel, EmailChannel)
    
    def test_get_channel_sms(self):
        """Verify SMSChannel can be retrieved."""
        channel = get_channel("SMS")
        assert isinstance(channel, SMSChannel)
    
    def test_get_channel_whatsapp(self):
        """Verify WhatsAppChannel can be retrieved."""
        channel = get_channel("WHATSAPP")
        assert isinstance(channel, WhatsAppChannel)
    
    def test_get_channel_invalid(self):
        """Verify invalid channel returns None."""
        channel = get_channel("INVALID")
        assert channel is None
    
    def test_email_channel_send(self):
        """Verify EmailChannel can send (dev mode logs)."""
        channel = EmailChannel()
        result = channel.send(
            recipient="test@example.com",
            subject="Test Subject",
            body="Test body content",
        )
        # In dev mode, should succeed (just logs)
        assert result.success is True


class TestTemplateRegistry:
    """Test template management."""
    
    def test_default_templates_loaded(self):
        """Verify default templates are registered."""
        template = TemplateRegistry.get(TemplateRegistry.WELCOME_EMAIL)
        assert template is not None
        assert template.id == "welcome_email"
    
    def test_template_render(self):
        """Verify template rendering works."""
        subject, body = TemplateRegistry.render(
            TemplateRegistry.WELCOME_EMAIL,
            {
                "name": "John Doe",
                "username": "johndoe",
                "org_name": "Test Org",
            }
        )
        assert "John Doe" in subject
        assert "johndoe" in body
        assert "Test Org" in body
    
    def test_template_not_found(self):
        """Verify ValueError for unknown template."""
        with pytest.raises(ValueError):
            TemplateRegistry.render("nonexistent_template", {})


class TestNotificationDispatcher:
    """Test the main dispatcher service."""
    
    def test_dispatcher_singleton(self):
        """Verify get_dispatcher returns singleton."""
        d1 = get_dispatcher()
        d2 = get_dispatcher()
        assert d1 is d2
    
    def test_send_notification_success(self):
        """Verify successful notification send."""
        dispatcher = NotificationDispatcher()
        results = dispatcher.send(
            template_id=TemplateRegistry.WELCOME_EMAIL,
            recipient_id="user-001",
            recipient_address="user@example.com",
            context={
                "name": "Test User",
                "username": "testuser",
                "org_name": "ALIS Test",
            },
            channels=[NotificationChannel.EMAIL],
        )
        
        assert len(results) == 1
        log = results[0]
        assert log.status == NotificationStatus.SENT
        assert log.recipient_address == "user@example.com"
        assert log.template_id == TemplateRegistry.WELCOME_EMAIL
    
    def test_send_notification_invalid_template(self):
        """Verify handling of invalid template."""
        dispatcher = NotificationDispatcher()
        results = dispatcher.send(
            template_id="invalid_template_xyz",
            recipient_id="user-001",
            recipient_address="user@example.com",
            context={},
        )
        
        assert len(results) == 1
        log = results[0]
        assert log.status == NotificationStatus.FAILED
        assert "not found" in log.error_message.lower()
    
    def test_retry_failed_notification(self):
        """Verify retry mechanism works."""
        dispatcher = NotificationDispatcher()
        
        # First send with invalid template (will fail)
        results = dispatcher.send(
            template_id="invalid_xyz",
            recipient_id="user-retry",
            recipient_address="retry@example.com",
            context={},
        )
        log = results[0]
        assert log.status == NotificationStatus.FAILED
        
        # Retry should still fail (same template issue)
        retried = dispatcher.retry_failed(log.id)
        assert retried.retry_count == 1
    
    def test_get_failed_logs(self):
        """Verify failed logs retrieval."""
        dispatcher = NotificationDispatcher()
        
        # Create a failed notification
        dispatcher.send(
            template_id="nonexistent",
            recipient_id="user-failed",
            recipient_address="fail@example.com",
            context={},
        )
        
        failed = dispatcher.get_failed_logs()
        # Should have at least one failed log
        assert len(failed) >= 1


class TestAcceptanceCriteria:
    """
    Verify all JIRA acceptance criteria are met.
    
    From E02-S03:
    - [x] Template-based notifications
    - [x] Channel abstraction
    - [x] Retry & failure handling
    - [x] Delivery status tracking
    - [x] No direct notifications from modules
    """
    
    def test_template_based_notifications(self):
        """AC: Template-based notifications."""
        # Templates exist and can be rendered
        template = TemplateRegistry.get(TemplateRegistry.WELCOME_EMAIL)
        assert template is not None
        subject, body = template.render({"name": "Test", "username": "t", "org_name": "O"})
        assert len(subject) > 0
        assert len(body) > 0
    
    def test_channel_abstraction(self):
        """AC: Channel abstraction."""
        # Multiple channels implement same interface
        email = get_channel("EMAIL")
        sms = get_channel("SMS")
        whatsapp = get_channel("WHATSAPP")
        
        # All have send() and is_enabled() methods
        assert hasattr(email, "send")
        assert hasattr(email, "is_enabled")
        assert hasattr(sms, "send")
        assert hasattr(whatsapp, "send")
    
    def test_retry_and_failure_handling(self):
        """AC: Retry & failure handling."""
        dispatcher = NotificationDispatcher()
        
        # Send with bad template -> FAILED
        results = dispatcher.send(
            template_id="bad",
            recipient_id="test",
            recipient_address="test@test.com",
            context={},
        )
        assert results[0].status == NotificationStatus.FAILED
        
        # Retry increments counter
        original_count = results[0].retry_count
        dispatcher.retry_failed(results[0].id)
        assert dispatcher.get_log(results[0].id).retry_count == original_count + 1
    
    def test_delivery_status_tracking(self):
        """AC: Delivery status tracking."""
        dispatcher = NotificationDispatcher()
        
        results = dispatcher.send(
            template_id=TemplateRegistry.WELCOME_EMAIL,
            recipient_id="track-test",
            recipient_address="track@example.com",
            context={"name": "T", "username": "t", "org_name": "O"},
        )
        
        log = results[0]
        
        # Status is tracked
        assert log.status in [NotificationStatus.SENT, NotificationStatus.FAILED]
        
        # Can retrieve by ID
        retrieved = dispatcher.get_log(log.id)
        assert retrieved is not None
        assert retrieved.id == log.id
    
    def test_no_direct_module_notifications(self):
        """AC: No direct notifications from modules."""
        # This is an architectural constraint verified by code structure.
        # Modules import from server.core.notifications, not from channels directly.
        # The dispatcher is the only public API.
        from server.core.notifications import get_dispatcher, NotificationDispatcher
        
        dispatcher = get_dispatcher()
        assert isinstance(dispatcher, NotificationDispatcher)
        
        # Modules use dispatcher.send(), not channel.send() directly
        # This is enforced by the package structure.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
