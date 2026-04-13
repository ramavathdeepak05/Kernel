"""
P14 — SMS Gateway Integration

Sends OTP codes, status updates, and time-sensitive reminders to applicants
via SMS. Supports MSG91 (dominant in India) and Twilio (international fallback).

The flow:
  1. Configure provider credentials in settings
  2. Call send_otp() for phone verification during application
  3. Call verify_otp() to confirm the code
  4. Call send_sms() for status notifications and reminders

All HTTP calls are isolated in this module. The rest of ALIS never touches
the SMS provider directly — it calls this client and receives plain dicts.

When not configured (settings.sms_gateway_enabled == False), all methods
return failures gracefully so the workflow can proceed without SMS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# PROVIDER ENUM
# =============================================================================


class SMSProvider(str, Enum):
    MSG91 = "MSG91"
    TWILIO = "TWILIO"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SMSResult:
    """Result of sending a single SMS."""

    success: bool
    message_id: str | None = None
    provider: str = ""
    phone: str = ""
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OTPSendResult:
    """Result of sending an OTP."""

    success: bool
    request_id: str | None = None  # Provider's OTP session ID
    provider: str = ""
    phone: str = ""
    error: str | None = None


@dataclass
class OTPVerifyResult:
    """Result of verifying an OTP."""

    is_valid: bool
    phone: str = ""
    error: str | None = None


@dataclass
class BulkSMSResult:
    """Result of sending bulk SMS."""

    total: int = 0
    sent: int = 0
    failed: int = 0
    results: list[SMSResult] = field(default_factory=list)


# =============================================================================
# SMS GATEWAY CLIENT
# =============================================================================


class SMSGatewayClient:
    """
    Unified client for SMS operations.

    Usage:
        client = SMSGatewayClient()
        if not client.is_enabled():
            logger.warning("SMS not configured — skipping notification")
            return

        # Send OTP
        otp_result = client.send_otp(phone="+919876543210")

        # Verify OTP
        verify = client.verify_otp(
            phone="+919876543210",
            otp="123456",
            request_id=otp_result.request_id,
        )

        # Send transactional SMS
        sms_result = client.send_sms(
            phone="+919876543210",
            message="Your application APP-2025-000123 has been submitted.",
            template_id="admissions_submitted",
        )

        # Bulk SMS for batch notifications
        bulk = client.send_bulk(
            recipients=[
                {"phone": "+919876543210", "message": "Offer deadline in 3 days"},
                {"phone": "+919876543211", "message": "Offer deadline in 3 days"},
            ],
            template_id="offer_reminder_t3",
        )
    """

    def __init__(self) -> None:
        from server.core.settings import settings

        self._settings = settings
        self._provider = getattr(settings, "sms_provider", "MSG91").upper()

    def is_enabled(self) -> bool:
        return getattr(self._settings, "sms_gateway_enabled", False)

    @property
    def provider(self) -> str:
        return self._provider

    # -------------------------------------------------------------------------
    # SEND OTP
    # -------------------------------------------------------------------------

    def send_otp(
        self,
        phone: str,
        otp_length: int = 6,
        expiry_minutes: int = 10,
    ) -> OTPSendResult:
        """
        Send a one-time password to a phone number.

        Args:
            phone: Phone number with country code (e.g. +919876543210)
            otp_length: Number of digits in OTP (default 6)
            expiry_minutes: OTP validity in minutes (default 10)
        """
        if not self.is_enabled():
            return OTPSendResult(
                success=False, phone=phone, error="SMS gateway not configured"
            )

        if self._provider == SMSProvider.MSG91:
            return self._msg91_send_otp(phone, otp_length, expiry_minutes)
        if self._provider == SMSProvider.TWILIO:
            return self._twilio_send_otp(phone, otp_length, expiry_minutes)
        return OTPSendResult(
            success=False, phone=phone, error=f"Unknown provider: {self._provider}"
        )

    def _msg91_send_otp(
        self, phone: str, otp_length: int, expiry_minutes: int
    ) -> OTPSendResult:
        import httpx

        auth_key = self._settings.msg91_auth_key
        template_id = getattr(self._settings, "msg91_otp_template_id", "")
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.post(
                "https://control.msg91.com/api/v5/otp",
                headers={"authkey": auth_key},
                json={
                    "mobile": phone.lstrip("+"),
                    "template_id": template_id,
                    "otp_length": otp_length,
                    "otp_expiry": expiry_minutes,
                },
                timeout=timeout,
            )
            data = resp.json()
            if data.get("type") == "success":
                logger.info("MSG91: OTP sent to %s***", phone[:6])
                return OTPSendResult(
                    success=True,
                    request_id=data.get("request_id", ""),
                    provider=SMSProvider.MSG91,
                    phone=phone,
                )
            logger.warning("MSG91: OTP send failed — %s", data.get("message"))
            return OTPSendResult(
                success=False,
                provider=SMSProvider.MSG91,
                phone=phone,
                error=data.get("message", "Unknown MSG91 error"),
            )
        except Exception as exc:
            logger.error("MSG91: OTP send exception — %s", exc)
            return OTPSendResult(
                success=False, provider=SMSProvider.MSG91, phone=phone, error=str(exc)
            )

    def _twilio_send_otp(
        self, phone: str, otp_length: int, expiry_minutes: int
    ) -> OTPSendResult:
        import httpx

        account_sid = self._settings.twilio_account_sid
        auth_token = self._settings.twilio_auth_token
        verify_sid = self._settings.twilio_verify_service_sid
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.post(
                f"https://verify.twilio.com/v2/Services/{verify_sid}/Verifications",
                auth=(account_sid, auth_token),
                data={"To": phone, "Channel": "sms"},
                timeout=timeout,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                logger.info("Twilio: OTP sent to %s***", phone[:6])
                return OTPSendResult(
                    success=True,
                    request_id=data.get("sid", ""),
                    provider=SMSProvider.TWILIO,
                    phone=phone,
                )
            logger.warning("Twilio: OTP send failed — %s", data.get("message"))
            return OTPSendResult(
                success=False,
                provider=SMSProvider.TWILIO,
                phone=phone,
                error=data.get("message", "Unknown Twilio error"),
            )
        except Exception as exc:
            logger.error("Twilio: OTP send exception — %s", exc)
            return OTPSendResult(
                success=False, provider=SMSProvider.TWILIO, phone=phone, error=str(exc)
            )

    # -------------------------------------------------------------------------
    # VERIFY OTP
    # -------------------------------------------------------------------------

    def verify_otp(
        self,
        phone: str,
        otp: str,
        request_id: str | None = None,
    ) -> OTPVerifyResult:
        """
        Verify an OTP entered by the user.
        """
        if not self.is_enabled():
            return OTPVerifyResult(
                is_valid=False, phone=phone, error="SMS not configured"
            )

        if self._provider == SMSProvider.MSG91:
            return self._msg91_verify_otp(phone, otp)
        if self._provider == SMSProvider.TWILIO:
            return self._twilio_verify_otp(phone, otp)
        return OTPVerifyResult(
            is_valid=False, phone=phone, error=f"Unknown provider: {self._provider}"
        )

    def _msg91_verify_otp(self, phone: str, otp: str) -> OTPVerifyResult:
        import httpx

        auth_key = self._settings.msg91_auth_key
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.get(
                "https://control.msg91.com/api/v5/otp/verify",
                headers={"authkey": auth_key},
                params={"mobile": phone.lstrip("+"), "otp": otp},
                timeout=timeout,
            )
            data = resp.json()
            is_valid = data.get("type") == "success"
            if is_valid:
                logger.info("MSG91: OTP verified for %s***", phone[:6])
            else:
                logger.warning("MSG91: OTP verification failed for %s***", phone[:6])
            return OTPVerifyResult(
                is_valid=is_valid,
                phone=phone,
                error=None if is_valid else data.get("message", "Invalid OTP"),
            )
        except Exception as exc:
            logger.error("MSG91: OTP verify exception — %s", exc)
            return OTPVerifyResult(is_valid=False, phone=phone, error=str(exc))

    def _twilio_verify_otp(self, phone: str, otp: str) -> OTPVerifyResult:
        import httpx

        account_sid = self._settings.twilio_account_sid
        auth_token = self._settings.twilio_auth_token
        verify_sid = self._settings.twilio_verify_service_sid
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.post(
                f"https://verify.twilio.com/v2/Services/{verify_sid}/VerificationCheck",
                auth=(account_sid, auth_token),
                data={"To": phone, "Code": otp},
                timeout=timeout,
            )
            data = resp.json()
            is_valid = data.get("status") == "approved"
            if is_valid:
                logger.info("Twilio: OTP verified for %s***", phone[:6])
            else:
                logger.warning("Twilio: OTP verification failed for %s***", phone[:6])
            return OTPVerifyResult(
                is_valid=is_valid,
                phone=phone,
                error=None if is_valid else "Invalid OTP",
            )
        except Exception as exc:
            logger.error("Twilio: OTP verify exception — %s", exc)
            return OTPVerifyResult(is_valid=False, phone=phone, error=str(exc))

    # -------------------------------------------------------------------------
    # SEND TRANSACTIONAL SMS
    # -------------------------------------------------------------------------

    def send_sms(
        self,
        phone: str,
        message: str,
        template_id: str | None = None,
    ) -> SMSResult:
        """
        Send a single transactional SMS.

        In India, DLT-registered template IDs are mandatory for transactional SMS.
        """
        if not self.is_enabled():
            return SMSResult(success=False, phone=phone, error="SMS not configured")

        if self._provider == SMSProvider.MSG91:
            return self._msg91_send_sms(phone, message, template_id)
        if self._provider == SMSProvider.TWILIO:
            return self._twilio_send_sms(phone, message)
        return SMSResult(
            success=False, phone=phone, error=f"Unknown provider: {self._provider}"
        )

    def _msg91_send_sms(
        self, phone: str, message: str, template_id: str | None
    ) -> SMSResult:
        import httpx

        auth_key = self._settings.msg91_auth_key
        getattr(self._settings, "msg91_sender_id", "ALISUN")
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.post(
                "https://control.msg91.com/api/v5/flow/",
                headers={"authkey": auth_key},
                json={
                    "template_id": template_id or "",
                    "recipients": [{"mobiles": phone.lstrip("+"), "message": message}],
                },
                timeout=timeout,
            )
            data = resp.json()
            success = data.get("type") == "success"
            logger.info(
                "MSG91: SMS %s to %s***", "sent" if success else "failed", phone[:6]
            )
            return SMSResult(
                success=success,
                message_id=data.get("request_id"),
                provider=SMSProvider.MSG91,
                phone=phone,
                error=None if success else data.get("message"),
                raw=data,
            )
        except Exception as exc:
            logger.error("MSG91: SMS send exception — %s", exc)
            return SMSResult(
                success=False, provider=SMSProvider.MSG91, phone=phone, error=str(exc)
            )

    def _twilio_send_sms(self, phone: str, message: str) -> SMSResult:
        import httpx

        account_sid = self._settings.twilio_account_sid
        auth_token = self._settings.twilio_auth_token
        from_number = self._settings.twilio_from_number
        timeout = getattr(self._settings, "sms_timeout_seconds", 10)

        try:
            resp = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={"To": phone, "From": from_number, "Body": message},
                timeout=timeout,
            )
            data = resp.json()
            success = resp.status_code in (200, 201)
            logger.info(
                "Twilio: SMS %s to %s***", "sent" if success else "failed", phone[:6]
            )
            return SMSResult(
                success=success,
                message_id=data.get("sid"),
                provider=SMSProvider.TWILIO,
                phone=phone,
                error=None if success else data.get("message"),
                raw=data,
            )
        except Exception as exc:
            logger.error("Twilio: SMS send exception — %s", exc)
            return SMSResult(
                success=False, provider=SMSProvider.TWILIO, phone=phone, error=str(exc)
            )

    # -------------------------------------------------------------------------
    # BULK SMS
    # -------------------------------------------------------------------------

    def send_bulk(
        self,
        recipients: list[dict[str, str]],
        template_id: str | None = None,
    ) -> BulkSMSResult:
        """
        Send SMS to multiple recipients.

        Args:
            recipients: List of dicts with "phone" and "message" keys
            template_id: DLT template ID (required for MSG91 in India)
        """
        if not self.is_enabled():
            return BulkSMSResult(total=len(recipients))

        results = []
        for r in recipients:
            result = self.send_sms(
                phone=r["phone"],
                message=r["message"],
                template_id=template_id,
            )
            results.append(result)

        sent = sum(1 for r in results if r.success)
        return BulkSMSResult(
            total=len(recipients),
            sent=sent,
            failed=len(recipients) - sent,
            results=results,
        )
