"""
P14 — Email Provisioning Integration

Creates university email accounts for newly enrolled students via:
  - Google Workspace Admin SDK (Directory API)
  - Microsoft 365 (Microsoft Graph API)

The provisioning flow (triggered by EnrollmentProvisioningService.provision_email()):
  1. Derive username from roll number / name
  2. Create account in Google Workspace or Microsoft 365
  3. Set temporary password
  4. Return the assigned university_email address

When email_provider is empty / not configured, returns a stub result
so enrollment provisioning continues without blocking.

Provider selection is via settings.email_provider:
  "GOOGLE"    → Google Workspace Admin SDK
  "MICROSOFT" → Microsoft Graph API
  ""          → Stub (dev / SMTP-only institutions)
"""

from __future__ import annotations

import logging
import re
import secrets
import string
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailProvisionResult:
    success: bool
    university_email: Optional[str] = None
    temp_password: Optional[str] = None
    provider: str = ""          # GOOGLE | MICROSOFT | STUB
    error: Optional[str] = None


def _temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%" for c in pwd)
        ):
            return pwd


def _derive_username(full_name: str, roll_number: str) -> str:
    """
    Derive email username from name + roll number.
    e.g. "Priya Sharma" + "CS-2025-0001" → "priya.sharma.cs25001"
    """
    parts = full_name.lower().split()
    name_part = ".".join(parts[:2]) if len(parts) >= 2 else parts[0]
    # Shorten roll: CS-2025-0001 → cs250001
    roll_part = re.sub(r"[^a-z0-9]", "", roll_number.lower())[-6:]
    return f"{name_part}.{roll_part}"


class EmailProvisionClient:
    """
    Unified email provisioning client — delegates to Google or Microsoft
    based on settings.email_provider.

    Usage:
        client = EmailProvisionClient()
        result = client.create_student_email(
            full_name="Priya Sharma",
            roll_number="CS-2025-0001",
        )
        if result.success:
            university_email = result.university_email
    """

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings

    def is_enabled(self) -> bool:
        return self._settings.email_provision_enabled

    def create_student_email(
        self,
        full_name: str,
        roll_number: str,
    ) -> EmailProvisionResult:
        """
        Create a university email account for a newly enrolled student.

        Returns EmailProvisionResult with the assigned university_email and
        temp_password that the student must change on first login.
        """
        provider = self._settings.email_provider

        if provider == "GOOGLE":
            return self._create_google(full_name, roll_number)
        elif provider == "MICROSOFT":
            return self._create_microsoft(full_name, roll_number)
        else:
            return self._create_stub(full_name, roll_number)

    def suspend_student_email(self, university_email: str) -> bool:
        """Suspend/disable the email account (e.g. on cancellation)."""
        provider = self._settings.email_provider
        if not self.is_enabled():
            return True

        try:
            if provider == "GOOGLE":
                return self._suspend_google(university_email)
            elif provider == "MICROSOFT":
                return self._suspend_microsoft(university_email)
        except Exception as exc:
            logger.error("EmailProvision: suspend failed [%s] — %s", university_email, exc)
        return False

    # -------------------------------------------------------------------------
    # Google Workspace
    # -------------------------------------------------------------------------

    def _create_google(self, full_name: str, roll_number: str) -> EmailProvisionResult:
        domain = self._settings.google_domain
        if not domain:
            return EmailProvisionResult(success=False, error="google_domain not configured.", provider="GOOGLE")

        username = _derive_username(full_name, roll_number)
        email = f"{username}@{domain}"
        password = _temp_password()
        parts = full_name.split()

        try:
            service = self._google_directory_service()
            user_body = {
                "primaryEmail": email,
                "name": {
                    "givenName": parts[0],
                    "familyName": " ".join(parts[1:]) if len(parts) > 1 else parts[0],
                },
                "password": password,
                "changePasswordAtNextLogin": True,
                "orgUnitPath": "/Students",
            }
            service.users().insert(body=user_body).execute()
            logger.info("Google Workspace: created email [%s]", email)
            return EmailProvisionResult(
                success=True,
                university_email=email,
                temp_password=password,
                provider="GOOGLE",
            )
        except Exception as exc:
            logger.error("Google Workspace: create failed — %s", exc)
            return EmailProvisionResult(success=False, error=str(exc), provider="GOOGLE")

    def _suspend_google(self, email: str) -> bool:
        service = self._google_directory_service()
        service.users().patch(userKey=email, body={"suspended": True}).execute()
        return True

    def _google_directory_service(self):
        """Build Google Admin SDK Directory service from service account JSON."""
        import json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_info = json.loads(self._settings.google_service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/admin.directory.user"],
            subject=self._settings.google_admin_email,
        )
        return build("admin", "directory_v1", credentials=credentials, cache_discovery=False)

    # -------------------------------------------------------------------------
    # Microsoft 365 (Graph API)
    # -------------------------------------------------------------------------

    def _create_microsoft(self, full_name: str, roll_number: str) -> EmailProvisionResult:
        domain = self._settings.ms_domain
        if not domain:
            return EmailProvisionResult(success=False, error="ms_domain not configured.", provider="MICROSOFT")

        username = _derive_username(full_name, roll_number)
        email = f"{username}@{domain}"
        password = _temp_password()
        parts = full_name.split()

        try:
            token = self._ms_access_token()
            import httpx
            resp = httpx.post(
                "https://graph.microsoft.com/v1.0/users",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "accountEnabled": True,
                    "displayName": full_name,
                    "givenName": parts[0],
                    "surname": " ".join(parts[1:]) if len(parts) > 1 else "",
                    "mailNickname": username,
                    "userPrincipalName": email,
                    "passwordProfile": {
                        "forceChangePasswordNextSignIn": True,
                        "password": password,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Microsoft 365: created email [%s]", email)
            return EmailProvisionResult(
                success=True,
                university_email=email,
                temp_password=password,
                provider="MICROSOFT",
            )
        except Exception as exc:
            logger.error("Microsoft 365: create failed — %s", exc)
            return EmailProvisionResult(success=False, error=str(exc), provider="MICROSOFT")

    def _suspend_microsoft(self, email: str) -> bool:
        token = self._ms_access_token()
        import httpx
        resp = httpx.patch(
            f"https://graph.microsoft.com/v1.0/users/{email}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"accountEnabled": False},
            timeout=30,
        )
        resp.raise_for_status()
        return True

    def _ms_access_token(self) -> str:
        """Acquire Microsoft 365 access token via client credentials flow."""
        import httpx
        s = self._settings
        resp = httpx.post(
            f"https://login.microsoftonline.com/{s.ms_tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": s.ms_client_id,
                "client_secret": s.ms_client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # -------------------------------------------------------------------------
    # Stub (dev / SMTP-only)
    # -------------------------------------------------------------------------

    def _create_stub(self, full_name: str, roll_number: str) -> EmailProvisionResult:
        """Return a fake email for dev/test environments."""
        username = _derive_username(full_name, roll_number)
        email = f"{username}@university.local"
        logger.info("EmailProvision: stub mode — returning fake email [%s]", email)
        return EmailProvisionResult(
            success=True,
            university_email=email,
            temp_password="Stub@123456",
            provider="STUB",
        )
