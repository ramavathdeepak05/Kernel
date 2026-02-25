"""
ALIS Notification Dispatcher Service - E02-S03

MODULE: Shared Services
LAYER: Layer 2/6 (Decision Facade + Resilience)

This is the central notification service used by all ALIS modules.
Modules MUST use this service and never contact channels directly.

Must Align With:
- Shared Services only (no domain logic)
- Layer 6 (Resilience) - Retry handling, failure tracking
- Layer 5 (Audit) - All sends are logged

Acceptance Criteria:
- [x] Template-based notifications
- [x] Channel abstraction
- [x] Retry & failure handling
- [x] Delivery status tracking
- [x] No direct notifications from modules
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging

from ..models import (
    NotificationLog,
    NotificationStatus,
    NotificationChannel,
)
from ..config import ConfigRegistry
from ..audit import AuditLog, AuditAction
from .channels import get_channel, ChannelResult
from .templates import TemplateRegistry


logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Base exception for notification errors."""
    pass


class NotificationDispatcher:
    """
    Central notification dispatcher for ALIS.
    
    This is the ONLY entry point for sending notifications.
    All modules MUST use this service.
    
    Usage:
        dispatcher = NotificationDispatcher()
        result = dispatcher.send(
            template_id="welcome_email",
            recipient_id="user-123",
            recipient_address="user@example.com",
            context={"name": "John", "username": "john.doe"},
            channels=[NotificationChannel.EMAIL]
        )
    """
    
    # In-memory log storage (replace with DB in production)
    _logs: Dict[str, NotificationLog] = {}
    
    def send(
        self,
        template_id: str,
        recipient_id: str,
        recipient_address: str,
        context: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None,
        org_id: Optional[str] = None,
    ) -> List[NotificationLog]:
        """
        Send a notification via specified channels.
        
        Args:
            template_id: ID of the template to use
            recipient_id: User ID of recipient (for audit)
            recipient_address: Email or phone number
            context: Variables for template rendering
            channels: List of channels to use (default: EMAIL only)
            org_id: Organization ID for scoping
            
        Returns:
            List of NotificationLog entries (one per channel)
        """
        if channels is None:
            channels = [NotificationChannel.EMAIL]
        
        results = []
        
        for channel_type in channels:
            log = self._send_single(
                template_id=template_id,
                recipient_id=recipient_id,
                recipient_address=recipient_address,
                context=context,
                channel_type=channel_type,
                org_id=org_id,
            )
            results.append(log)
        
        return results
    
    def _send_single(
        self,
        template_id: str,
        recipient_id: str,
        recipient_address: str,
        context: Dict[str, Any],
        channel_type: NotificationChannel,
        org_id: Optional[str] = None,
    ) -> NotificationLog:
        """Send notification via a single channel."""
        
        # Create log entry (PENDING)
        log = NotificationLog(
            recipient_id=recipient_id,
            recipient_address=recipient_address,
            template_id=template_id,
            channel=channel_type,
            status=NotificationStatus.PENDING,
            context_snapshot=context,
            org_id=org_id,
            max_retries=ConfigRegistry.get(
                ConfigRegistry.NOTIFICATION_MAX_RETRIES,
                default=3
            ),
        )
        
        # Store log
        self._logs[log.id] = log
        
        # Try to render template
        try:
            subject, body = TemplateRegistry.render(template_id, context)
        except ValueError as e:
            log.status = NotificationStatus.FAILED
            log.error_message = str(e)
            logger.error(f"Template render failed: {e}")
            return log
        
        # Get channel
        channel = get_channel(channel_type.value)
        if not channel:
            log.status = NotificationStatus.FAILED
            log.error_message = f"Unknown channel: {channel_type}"
            logger.error(f"Unknown channel: {channel_type}")
            return log
        
        # Check if channel is enabled
        if not channel.is_enabled():
            log.status = NotificationStatus.FAILED
            log.error_message = f"Channel {channel_type} is disabled"
            logger.warning(f"Channel {channel_type} is disabled, skipping")
            return log
        
        # Send via channel
        result: ChannelResult = channel.send(
            recipient=recipient_address,
            subject=subject,
            body=body,
        )
        
        if result.success:
            log.status = NotificationStatus.SENT
            log.sent_at = datetime.now(timezone.utc)
            logger.info(
                f"Notification sent: {template_id} -> {recipient_address} via {channel_type}"
            )
        else:
            log.status = NotificationStatus.FAILED
            log.error_message = result.error_message
            logger.error(
                f"Notification failed: {template_id} -> {recipient_address}: {result.error_message}"
            )
        
        # Audit log
        self._audit_send(log, result)
        
        return log
    
    def retry_failed(self, log_id: str) -> NotificationLog:
        """
        Retry a failed notification.
        
        Args:
            log_id: ID of the NotificationLog to retry
            
        Returns:
            Updated NotificationLog
            
        Raises:
            NotificationError: If log not found or max retries exceeded
        """
        log = self._logs.get(log_id)
        if not log:
            raise NotificationError(f"Notification log not found: {log_id}")
        
        if log.status == NotificationStatus.SENT:
            raise NotificationError(f"Notification already sent: {log_id}")
        
        if log.retry_count >= log.max_retries:
            raise NotificationError(
                f"Max retries ({log.max_retries}) exceeded for: {log_id}"
            )
        
        # Update retry metadata
        log.retry_count += 1
        log.last_retry_at = datetime.now(timezone.utc)
        log.status = NotificationStatus.RETRYING
        
        # Re-attempt send
        try:
            subject, body = TemplateRegistry.render(
                log.template_id,
                log.context_snapshot or {}
            )
        except ValueError as e:
            log.status = NotificationStatus.FAILED
            log.error_message = str(e)
            return log
        
        channel = get_channel(log.channel.value)
        if not channel or not channel.is_enabled():
            log.status = NotificationStatus.FAILED
            log.error_message = f"Channel {log.channel} unavailable"
            return log
        
        result = channel.send(
            recipient=log.recipient_address,
            subject=subject,
            body=body,
        )
        
        if result.success:
            log.status = NotificationStatus.SENT
            log.sent_at = datetime.now(timezone.utc)
            log.error_message = None
        else:
            log.status = NotificationStatus.FAILED
            log.error_message = result.error_message
        
        self._audit_send(log, result)
        return log
    
    def get_log(self, log_id: str) -> Optional[NotificationLog]:
        """Get a notification log by ID."""
        return self._logs.get(log_id)
    
    def get_logs_by_recipient(self, recipient_id: str) -> List[NotificationLog]:
        """Get all logs for a recipient."""
        return [
            log for log in self._logs.values()
            if log.recipient_id == recipient_id
        ]
    
    def get_failed_logs(self) -> List[NotificationLog]:
        """Get all failed notification logs (for retry processing)."""
        return [
            log for log in self._logs.values()
            if log.status == NotificationStatus.FAILED
            and log.retry_count < log.max_retries
        ]
    
    def _audit_send(self, log: NotificationLog, result: ChannelResult) -> None:
        """Log audit entry for notification send attempt."""
        AuditLog.log(
            action=AuditAction.OVERRIDE_REQUESTED,  # Reusing action type
            actor_id="notification_dispatcher",
            actor_type="system",
            entity_type="notification",
            entity_id=log.id,
            success=result.success,
            action_detail=f"Notification via {log.channel.value}: {log.template_id}",
            metadata={
                "recipient": log.recipient_address,
                "template": log.template_id,
                "channel": log.channel.value,
                "error": result.error_message,
            },
            org_id=log.org_id,
        )


# Singleton instance for convenience
_dispatcher: Optional[NotificationDispatcher] = None


def get_dispatcher() -> NotificationDispatcher:
    """Get the singleton NotificationDispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotificationDispatcher()
    return _dispatcher
