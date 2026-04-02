"""
P14 — LMS Account Sync Integration — REPLACED BY IN-HOUSE LMS (P40)

Moodle account provisioning during enrollment is no longer needed.
ALIS now manages course materials, assignments, and student submissions
natively via the in-house Learning module.

For enrollment provisioning: the provision_lms() step generates an
ALIS-internal account ID (format: alis-lms-{roll_number}) and sets
lms_status='DONE' without any external API call.

This module is retained as a tombstone to preserve import stability.
Superseded by: server.academics.learning_service
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LMSUser:
    lms_id: str
    username: str
    email: str
    full_name: str
    temp_password: str


@dataclass
class LMSSyncResult:
    success: bool
    user: Optional[LMSUser] = None
    error: Optional[str] = None
    is_stub: bool = True


class LMSSyncClient:
    """Tombstone — replaced by in-house LMS (P40). Always returns is_stub=True."""

    def is_enabled(self) -> bool:
        return False

    def create_student(self, roll_number: str, email: str, full_name: str, program: str) -> LMSSyncResult:
        logger.info("LMSSyncClient: in-house LMS active — no external account provisioning needed")
        return LMSSyncResult(success=True, is_stub=True)

    def deactivate_student(self, lms_account_id: str) -> bool:
        return True
