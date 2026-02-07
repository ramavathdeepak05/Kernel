"""
ALIS Notification Channels - E02-S03

MODULE: Shared Services
LAYER: Layer 2 (Channel Abstraction)

This module implements the pluggable channel architecture for notifications.
Each channel (Email, SMS, WhatsApp) implements the BaseChannel interface.

Must Align With:
- Shared Services only (no domain logic)
- Layer 6 (Resilience) - Channels report success/failure, don't crash

Blueprint: Rule Engine pattern (deterministic send behavior)
"""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import logging

from ..config import ConfigRegistry


logger = logging.getLogger(__name__)


# --- Channel Result ---

@dataclass
class ChannelResult:
    """Result of a channel send operation."""
    success: bool
    error_message: Optional[str] = None
    provider_response: Optional[str] = None


# --- Base Channel (Abstract) ---

class BaseChannel(ABC):
    """
    Abstract base class for all notification channels.
    
    Subclasses must implement:
    - send(): Actually dispatch the notification
    - is_enabled(): Check if channel is enabled in config
    """
    
    @abstractmethod
    def send(
        self,
        recipient: str,
        subject: Optional[str],
        body: str
    ) -> ChannelResult:
        """
        Send a notification via this channel.
        
        Args:
            recipient: Email address or phone number
            subject: Subject line (for email) or None
            body: Message body
            
        Returns:
            ChannelResult indicating success/failure
        """
        pass
    
    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this channel is enabled in configuration."""
        pass


# --- Email Channel ---

class EmailChannel(BaseChannel):
    """
    Email notification channel.
    
    Currently implements a mock/logging sender for development.
    Production: Replace with SMTP implementation.
    """
    
    def send(
        self,
        recipient: str,
        subject: Optional[str],
        body: str
    ) -> ChannelResult:
        """Send email notification."""
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                error_message="Email channel is disabled"
            )
        
        try:
            # TODO: Replace with actual SMTP implementation
            # smtp_host = ConfigRegistry.get(ConfigRegistry.NOTIFICATION_EMAIL_SMTP_HOST)
            # smtp_port = ConfigRegistry.get(ConfigRegistry.NOTIFICATION_EMAIL_SMTP_PORT)
            
            # For now, log the email (development mode)
            logger.info(
                f"[EMAIL] To: {recipient} | Subject: {subject} | Body: {body[:100]}..."
            )
            
            return ChannelResult(
                success=True,
                provider_response="LOGGED (dev mode)"
            )
            
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send to {recipient}: {str(e)}")
            return ChannelResult(
                success=False,
                error_message=str(e)
            )
    
    def is_enabled(self) -> bool:
        """Check if email is enabled in config."""
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_EMAIL_ENABLED,
            default=True
        )


# --- SMS Channel ---

class SMSChannel(BaseChannel):
    """
    SMS notification channel.
    
    Pluggable: Implement provider-specific logic here.
    """
    
    def send(
        self,
        recipient: str,
        subject: Optional[str],  # Ignored for SMS
        body: str
    ) -> ChannelResult:
        """Send SMS notification."""
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                error_message="SMS channel is disabled"
            )
        
        try:
            # TODO: Integrate with SMS provider (e.g., Twilio, AWS SNS)
            logger.info(f"[SMS] To: {recipient} | Body: {body[:160]}")
            
            return ChannelResult(
                success=True,
                provider_response="LOGGED (dev mode)"
            )
            
        except Exception as e:
            logger.error(f"[SMS] Failed to send to {recipient}: {str(e)}")
            return ChannelResult(
                success=False,
                error_message=str(e)
            )
    
    def is_enabled(self) -> bool:
        """Check if SMS is enabled in config."""
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_SMS_ENABLED,
            default=False
        )


# --- WhatsApp Channel ---

class WhatsAppChannel(BaseChannel):
    """
    WhatsApp notification channel.
    
    Pluggable: Integrate with WhatsApp Business API.
    """
    
    def send(
        self,
        recipient: str,
        subject: Optional[str],  # Ignored for WhatsApp
        body: str
    ) -> ChannelResult:
        """Send WhatsApp notification."""
        if not self.is_enabled():
            return ChannelResult(
                success=False,
                error_message="WhatsApp channel is disabled"
            )
        
        try:
            # TODO: Integrate with WhatsApp Business API
            logger.info(f"[WHATSAPP] To: {recipient} | Body: {body[:500]}")
            
            return ChannelResult(
                success=True,
                provider_response="LOGGED (dev mode)"
            )
            
        except Exception as e:
            logger.error(f"[WHATSAPP] Failed to send to {recipient}: {str(e)}")
            return ChannelResult(
                success=False,
                error_message=str(e)
            )
    
    def is_enabled(self) -> bool:
        """Check if WhatsApp is enabled in config."""
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_WHATSAPP_ENABLED,
            default=False
        )


# --- Channel Factory ---

def get_channel(channel_type: str) -> Optional[BaseChannel]:
    """
    Factory function to get a channel instance by type.
    
    Args:
        channel_type: "EMAIL", "SMS", or "WHATSAPP"
        
    Returns:
        BaseChannel instance or None if invalid type
    """
    channels = {
        "EMAIL": EmailChannel,
        "SMS": SMSChannel,
        "WHATSAPP": WhatsAppChannel,
    }
    
    channel_class = channels.get(channel_type.upper())
    if channel_class:
        return channel_class()
    return None
