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

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import ConfigRegistry

logger = logging.getLogger(__name__)


def _normalise_e164(phone: str) -> str:
    """Normalise a phone number to E.164 format (e.g. +919876543210)."""
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+91{digits}"
    return f"+{digits}"


# --- Channel Result ---


@dataclass
class ChannelResult:
    """Result of a channel send operation."""

    success: bool
    error_message: str | None = None
    provider_response: str | None = None


# --- Base Channel (Abstract) ---


class BaseChannel(ABC):
    """
    Abstract base class for all notification channels.

    Subclasses must implement:
    - send(): Actually dispatch the notification
    - is_enabled(): Check if channel is enabled in config
    """

    @abstractmethod
    def send(self, recipient: str, subject: str | None, body: str) -> ChannelResult:
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
        subject: str | None,
        body: str,
    ) -> ChannelResult:
        """Send email via SMTP (reads credentials from Pydantic Settings)."""
        if not self.is_enabled():
            return ChannelResult(
                success=False, error_message="Email channel is disabled"
            )

        from server.core.settings import settings

        # In development with no SMTP host set, fall back to console logging
        if (
            not settings.smtp_host
            or settings.smtp_host == "localhost"
            and not settings.smtp_user
        ):
            logger.info(
                "[EMAIL-DEV] To: %s | Subject: %s | %s...",
                recipient,
                subject,
                body[:120],
            )
            return ChannelResult(success=True, provider_response="LOGGED (dev mode)")

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            msg["To"] = recipient
            msg["Subject"] = subject or ""
            msg.attach(
                MIMEText(body, "html" if body.lstrip().startswith("<") else "plain")
            )

            if settings.smtp_use_tls:
                server = smtplib.SMTP(
                    settings.smtp_host, settings.smtp_port, timeout=15
                )
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(
                    settings.smtp_host, settings.smtp_port, timeout=15
                )

            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)

            server.sendmail(settings.smtp_from_email, [recipient], msg.as_string())
            server.quit()

            logger.info("[EMAIL] Sent to %s | Subject: %s", recipient, subject)
            return ChannelResult(success=True, provider_response="SMTP OK")

        except smtplib.SMTPException as exc:
            logger.error("[EMAIL] SMTP error sending to %s: %s", recipient, exc)
            return ChannelResult(success=False, error_message=str(exc))
        except Exception as exc:
            logger.error("[EMAIL] Unexpected error sending to %s: %s", recipient, exc)
            return ChannelResult(success=False, error_message=str(exc))

    def is_enabled(self) -> bool:
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_EMAIL_ENABLED, default=True
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
        subject: str | None,  # Ignored for SMS
        body: str,
        **kwargs,
    ) -> ChannelResult:
        """Send SMS via MSG91 or Twilio (delegates to SMSGatewayClient)."""
        if not self.is_enabled():
            return ChannelResult(success=False, error_message="SMS channel is disabled")

        try:
            from server.admissions.integrations.sms_gateway import SMSGatewayClient

            client = SMSGatewayClient()
            result = client.send_sms(
                phone=_normalise_e164(recipient),
                message=body[:160],
                template_id=kwargs.get("template_id"),
            )
            if result.success:
                logger.info("[SMS] Sent to %s via %s", recipient, result.provider)
                return ChannelResult(success=True, provider_response=result.message_id)
            logger.warning("[SMS] Failed to send to %s: %s", recipient, result.error)
            return ChannelResult(success=False, error_message=result.error)

        except Exception as exc:
            logger.error("[SMS] Unexpected error sending to %s: %s", recipient, exc)
            return ChannelResult(success=False, error_message=str(exc))

    def is_enabled(self) -> bool:
        """Check if SMS is enabled in config."""
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_SMS_ENABLED, default=False
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
        subject: str | None,  # Ignored for WhatsApp
        body: str,
        **kwargs,
    ) -> ChannelResult:
        """Send WhatsApp message via Meta Graph API (text message type)."""
        if not self.is_enabled():
            return ChannelResult(
                success=False, error_message="WhatsApp channel is disabled"
            )

        from server.core.settings import settings

        phone_number_id = settings.whatsapp_phone_number_id
        access_token = settings.whatsapp_access_token
        if not phone_number_id or not access_token:
            logger.warning("[WHATSAPP] Not configured — skipping send to %s", recipient)
            return ChannelResult(success=False, error_message="WhatsApp not configured")

        try:
            import httpx

            phone = _normalise_e164(recipient)
            url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"body": body},
            }
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=getattr(settings, "whatsapp_timeout_seconds", 10),
            )
            resp.raise_for_status()
            msg_id = resp.json().get("messages", [{}])[0].get("id", "")
            logger.info("[WHATSAPP] Sent to %s | msg_id=%s", phone, msg_id)
            return ChannelResult(success=True, provider_response=msg_id)

        except Exception as exc:
            logger.error("[WHATSAPP] Failed to send to %s: %s", recipient, exc)
            return ChannelResult(success=False, error_message=str(exc))

    def is_enabled(self) -> bool:
        """Check if WhatsApp is enabled in config."""
        return ConfigRegistry.get(
            ConfigRegistry.NOTIFICATION_WHATSAPP_ENABLED, default=False
        )


# --- Channel Factory ---


def get_channel(channel_type: str) -> BaseChannel | None:
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
