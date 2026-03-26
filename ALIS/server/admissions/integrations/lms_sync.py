"""
P14 — LMS Account Sync Integration

Creates and manages student accounts in the institution's Learning Management
System (LMS). Supports Moodle REST API (the most widely deployed open-source LMS).

The sync flow (triggered by EnrollmentProvisioningService.provision_lms()):
  1. Create Moodle user account (username derived from roll number)
  2. Set temporary password (student must change on first login)
  3. Enroll student in their program's cohort / course category
  4. Return the Moodle user ID as lms_account_id

When not configured (settings.lms_enabled == False), returns a stubbed result
so enrollment provisioning can continue without blocking on LMS.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LMSUser:
    lms_id: str             # Moodle user ID (int as str)
    username: str
    email: str
    full_name: str
    temp_password: str      # Initial password — must be changed on first login


@dataclass
class LMSSyncResult:
    success: bool
    user: Optional[LMSUser] = None
    error: Optional[str] = None
    is_stub: bool = False   # True when running without real LMS (dev mode)


def _generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password meeting common LMS requirements."""
    alphabet = string.ascii_letters + string.digits + "!@#$"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each required character class
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$" for c in pwd)
        ):
            return pwd


class LMSSyncClient:
    """
    Client for Moodle's Web Services REST API.

    Moodle REST API pattern:
        POST {base_url}/webservice/rest/server.php
        params: wstoken=TOKEN, wsfunction=FUNCTION, moodlewsrestformat=json, ...

    Usage:
        client = LMSSyncClient()
        if not client.is_enabled():
            return LMSSyncResult(success=True, is_stub=True, ...)

        result = client.create_student(
            roll_number="CS-2025-0001",
            email="jdoe@university.edu",
            full_name="John Doe",
            program="Computer Science",
        )
    """

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings

    def is_enabled(self) -> bool:
        return self._settings.lms_enabled

    def create_student(
        self,
        roll_number: str,
        email: str,
        full_name: str,
        program: str,
    ) -> LMSSyncResult:
        """
        Create a new student user in Moodle and enroll in the program cohort.

        Returns LMSSyncResult. On success, user.lms_id is the Moodle user ID
        to store as lms_account_id in enrollment_provisioning.
        """
        if not self.is_enabled():
            # Stub response for dev / non-LMS institutions
            stub_id = f"STUB-{roll_number}"
            logger.info("LMS: stub mode — returning fake account [id=%s]", stub_id)
            return LMSSyncResult(
                success=True,
                user=LMSUser(
                    lms_id=stub_id,
                    username=self._username(roll_number),
                    email=email,
                    full_name=full_name,
                    temp_password=_generate_temp_password(),
                ),
                is_stub=True,
            )

        username = self._username(roll_number)
        temp_password = _generate_temp_password()

        try:
            # Step 1: Create user
            user_data = self._call("core_user_create_users", {
                "users[0][username]": username,
                "users[0][password]": temp_password,
                "users[0][firstname]": full_name.split()[0],
                "users[0][lastname]": " ".join(full_name.split()[1:]) or full_name,
                "users[0][email]": email,
                "users[0][auth]": "manual",
                "users[0][idnumber]": roll_number,
                "users[0][lang]": "en",
            })
            moodle_user_id = str(user_data[0]["id"])

            # Step 2: Enroll in default course category cohort (program-level)
            self._call("core_cohort_add_cohort_members", {
                "members[0][cohorttype][type]": "name",
                "members[0][cohorttype][value]": program,
                "members[0][usertype][type]": "id",
                "members[0][usertype][value]": moodle_user_id,
            })

            logger.info("LMS: student created [id=%s, username=%s]", moodle_user_id, username)
            return LMSSyncResult(
                success=True,
                user=LMSUser(
                    lms_id=moodle_user_id,
                    username=username,
                    email=email,
                    full_name=full_name,
                    temp_password=temp_password,
                ),
            )

        except Exception as exc:
            logger.error("LMS: create_student failed [roll=%s] — %s", roll_number, exc)
            return LMSSyncResult(success=False, error=str(exc))

    def deactivate_student(self, lms_account_id: str) -> bool:
        """Suspend a Moodle user (e.g. on admission cancellation)."""
        if not self.is_enabled() or lms_account_id.startswith("STUB-"):
            return True

        try:
            self._call("core_user_update_users", {
                "users[0][id]": lms_account_id,
                "users[0][suspended]": "1",
            })
            logger.info("LMS: user deactivated [id=%s]", lms_account_id)
            return True
        except Exception as exc:
            logger.error("LMS: deactivate failed [id=%s] — %s", lms_account_id, exc)
            return False

    def _call(self, function: str, extra_params: Dict[str, Any]) -> Any:
        """Make a Moodle REST API call."""
        import httpx
        base_url = self._settings.lms_base_url
        token = self._settings.lms_api_token
        timeout = self._settings.lms_timeout_seconds

        params = {
            "wstoken": token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **extra_params,
        }
        resp = httpx.post(
            f"{base_url}/webservice/rest/server.php",
            data=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()

        # Moodle returns {"exception": ..., "errorcode": ...} on error
        if isinstance(result, dict) and "exception" in result:
            raise RuntimeError(f"Moodle error: {result.get('message', result['exception'])}")

        return result

    @staticmethod
    def _username(roll_number: str) -> str:
        """Derive Moodle username from roll number: CS-2025-0001 → cs2025001."""
        return roll_number.lower().replace("-", "")
