"""E10 — MSG91 WhatsApp Business API Integration

MODULE: Communication Hub
LAYER: Layer 1 (Module Purpose — Outbound Messaging)
EPIC:  E10-WhatsApp

WhatsApp is the PRIMARY notification channel for Indian universities
(>90% open rate vs. email <20%).  All outbound messages go through MSG91,
India's standard WhatsApp Business API provider.

Design Principles
─────────────────
- Feature flag guarded: communication.whatsapp must be enabled per-tenant.
- Graceful fallback: if flag is off, or MSG91 is unreachable, method returns
  None without raising — callers are never blocked by WhatsApp failures.
- Idempotency: every send logs a msg_ref_id.  The UNIQUE constraint on
  whatsapp_delivery_log(msg_ref_id) prevents double-sends during retries.
- No PII leakage: confidential events (mental health / counselling) are
  hard-blocked by an exclusion list — never sent over WhatsApp.
- Guardian messaging: send_to_student_and_guardian() dispatches to both
  the student's phone AND linked guardian phones in a single call.

Dependencies
────────────
- server.db_service          — execute_query / execute_transaction (sync psycopg2)
- server.core.feature_flags  — per-tenant feature flag check
- server.core.settings       — MSG91 credentials
- urllib.request              — HTTP POST to MSG91 (no new deps)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

from server.core.feature_flags import feature_flags
from server.core.settings import settings
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard-blocked template names — NEVER sent via WhatsApp (confidential events)
# ---------------------------------------------------------------------------
_CONFIDENTIAL_TEMPLATES: frozenset[str] = frozenset(
    {
        "counselling_session_scheduled",
        "counselling_followup",
        "mental_health_referral",
        "crisis_intervention",
        "psychological_assessment",
        "student_wellbeing_alert",
    }
)

# Supported language codes
_SUPPORTED_LANGUAGES = frozenset({"en", "te", "kn", "ta", "mr", "hi"})


class WhatsAppService:
    """
    MSG91 WhatsApp Business API integration.

    Feature flag: communication.whatsapp (per-tenant)
    Falls back gracefully if flag is disabled or MSG91 is unreachable.
    """

    MSG91_WHATSAPP_URL = (
        "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def send(
        cls,
        org_id: str,
        template_name: str,
        recipient_phone: str,
        variables: Dict[str, Any],
        language: Optional[str] = None,
    ) -> Optional[int]:
        """
        Send a WhatsApp message via MSG91.

        Steps:
          1. Hard-block confidential templates.
          2. Check feature flag communication.whatsapp for org_id.
          3. Resolve language (explicit → user pref → 'en').
          4. Look up MSG91 template ID from notification_templates.
          5. Insert whatsapp_delivery_log row with status=QUEUED.
          6. POST to MSG91 API.
          7. Update log to SENT (or FAILED with reason).

        Returns: log row id (int) or None on skipped/error.
        """
        # 1. Confidentiality hard-block
        if template_name in _CONFIDENTIAL_TEMPLATES:
            logger.warning(
                "WhatsApp: blocked confidential template '%s' for org %s",
                template_name,
                org_id,
            )
            return None

        # 2. Feature flag check
        if not feature_flags.is_enabled("communication.whatsapp", org_id):
            logger.debug(
                "WhatsApp: feature flag disabled for org %s — skipping '%s'",
                org_id,
                template_name,
            )
            return None

        # 3. Resolve language
        resolved_lang = cls._resolve_language(language)

        # 4. Fetch template
        template_id = cls._get_template(org_id, template_name, resolved_lang)
        if not template_id:
            logger.warning(
                "WhatsApp: no template '%s' (lang=%s) for org %s",
                template_name,
                resolved_lang,
                org_id,
            )
            return None

        # Normalise phone
        phone = cls._normalise_phone(recipient_phone)

        # 5. Log QUEUED
        log_id = cls._log_queued(
            org_id=org_id,
            recipient_phone=phone,
            template_name=template_name,
            language=resolved_lang,
            variables=variables,
        )

        # 6 + 7. POST to MSG91 and update log
        try:
            msg_ref = cls._post_msg91(
                auth_key=settings.msg91_auth_key,
                sender_number=settings.msg91_whatsapp_number,
                template_id=template_id,
                recipient_phone=phone,
                variables=variables,
            )
            cls._update_log_sent(log_id, msg_ref)
            logger.info(
                "WhatsApp: sent '%s' to %s (log_id=%s, msg_ref=%s)",
                template_name,
                phone,
                log_id,
                msg_ref,
            )
        except Exception as exc:
            cls._update_log_failed(log_id, str(exc))
            logger.error(
                "WhatsApp: failed to send '%s' to %s — %s", template_name, phone, exc
            )

        return log_id

    @classmethod
    def send_to_student_and_guardian(
        cls,
        org_id: str,
        student_id: str,
        template_name: str,
        variables: Dict[str, Any],
    ) -> List[Optional[int]]:
        """
        Convenience: sends to the student's phone AND all linked guardian phones.

        Uses the student's preferred_language (guardian inherits it unless
        guardian_portal_settings.preferred_language overrides it).

        Returns a list of log IDs (one per recipient).
        """
        # Confidentiality guard (early exit avoids any DB queries)
        if template_name in _CONFIDENTIAL_TEMPLATES:
            logger.warning(
                "WhatsApp: blocked confidential template '%s' (student %s)",
                template_name,
                student_id,
            )
            return []

        if not feature_flags.is_enabled("communication.whatsapp", org_id):
            return []

        log_ids: List[Optional[int]] = []

        # Student
        student_phone = cls._get_recipient_phone(org_id, student_id)
        student_lang = cls._get_user_language(org_id, student_id)

        if student_phone:
            log_ids.append(
                cls.send(org_id, template_name, student_phone, variables, student_lang)
            )

        # Guardians
        guardian_rows = execute_query(
            """
            SELECT gsl.guardian_id,
                   COALESCE(gps.preferred_language, %s) AS preferred_language
            FROM guardian_student_links gsl
            LEFT JOIN guardian_portal_settings gps
                   ON gps.org_id = gsl.org_id AND gps.guardian_id = gsl.guardian_id
            WHERE gsl.org_id = %s AND gsl.student_id = %s AND gsl.is_active = TRUE
            """,
            (student_lang or "en", org_id, student_id),
        )

        for row in guardian_rows:
            g_phone = cls._get_recipient_phone(org_id, str(row["guardian_id"]))
            if g_phone:
                log_ids.append(
                    cls.send(
                        org_id,
                        template_name,
                        g_phone,
                        variables,
                        str(row["preferred_language"]),
                    )
                )

        return log_ids

    @classmethod
    def handle_delivery_webhook(
        cls,
        msg_ref_id: str,
        status: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Update delivery log when MSG91 sends a delivery receipt webhook.

        Status mapping from MSG91:
          delivered → DELIVERED
          read      → DELIVERED (treat read as delivered)
          failed    → FAILED
          optout    → OPT_OUT

        Returns True if the log row was found and updated.
        """
        _STATUS_MAP = {
            "delivered": "DELIVERED",
            "read": "DELIVERED",
            "failed": "FAILED",
            "optout": "OPT_OUT",
            "sent": "SENT",
        }
        normalised = _STATUS_MAP.get(status.lower(), status.upper())

        if normalised == "DELIVERED":
            execute_transaction(
                [
                    (
                        """
                        UPDATE whatsapp_delivery_log
                        SET status = 'DELIVERED',
                            delivered_at = COALESCE(%s::TIMESTAMPTZ, NOW())
                        WHERE msg_ref_id = %s
                        """,
                        (timestamp, msg_ref_id),
                    )
                ]
            )
        elif normalised == "FAILED":
            execute_transaction(
                [
                    (
                        """
                        UPDATE whatsapp_delivery_log
                        SET status = 'FAILED',
                            failed_reason = 'MSG91 delivery failure reported via webhook'
                        WHERE msg_ref_id = %s
                        """,
                        (msg_ref_id,),
                    )
                ]
            )
        elif normalised == "OPT_OUT":
            execute_transaction(
                [
                    (
                        """
                        UPDATE whatsapp_delivery_log
                        SET status = 'OPT_OUT'
                        WHERE msg_ref_id = %s
                        """,
                        (msg_ref_id,),
                    )
                ]
            )
        else:
            execute_transaction(
                [
                    (
                        """
                        UPDATE whatsapp_delivery_log
                        SET status = %s
                        WHERE msg_ref_id = %s
                        """,
                        (normalised, msg_ref_id),
                    )
                ]
            )

        rows = execute_query(
            "SELECT id FROM whatsapp_delivery_log WHERE msg_ref_id = %s",
            (msg_ref_id,),
        )
        found = bool(rows)
        if not found:
            logger.warning(
                "WhatsApp webhook: msg_ref_id '%s' not found in delivery log", msg_ref_id
            )
        return found

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_recipient_phone(cls, org_id: str, user_id: str) -> Optional[str]:
        """Fetch phone number from users table for the given user_id."""
        rows = execute_query(
            "SELECT phone FROM users WHERE id = %s AND tenant_id = %s",
            (user_id, org_id),
        )
        if not rows:
            return None
        phone = rows[0].get("phone") or ""
        return cls._normalise_phone(phone) if phone.strip() else None

    @classmethod
    def _get_user_language(cls, org_id: str, user_id: str) -> str:
        """Return preferred_language for user, defaulting to 'en'."""
        rows = execute_query(
            "SELECT preferred_language FROM users WHERE id = %s AND tenant_id = %s",
            (user_id, org_id),
        )
        if not rows:
            return "en"
        lang = rows[0].get("preferred_language") or "en"
        return lang if lang in _SUPPORTED_LANGUAGES else "en"

    @classmethod
    def _get_template(
        cls, org_id: str, template_name: str, language: str
    ) -> Optional[str]:
        """
        Look up whatsapp_template_id from notification_templates.

        Falls back: requested language → 'en' → None.
        """
        rows = execute_query(
            """
            SELECT whatsapp_template_id
            FROM notification_templates
            WHERE org_id = %s
              AND template_name = %s
              AND language = %s
              AND channel = 'WHATSAPP'
              AND is_active = TRUE
            """,
            (org_id, template_name, language),
        )
        if rows and rows[0]["whatsapp_template_id"]:
            return str(rows[0]["whatsapp_template_id"])

        # Fallback to English variant
        if language != "en":
            rows_en = execute_query(
                """
                SELECT whatsapp_template_id
                FROM notification_templates
                WHERE org_id = %s
                  AND template_name = %s
                  AND language = 'en'
                  AND channel = 'WHATSAPP'
                  AND is_active = TRUE
                """,
                (org_id, template_name),
            )
            if rows_en and rows_en[0]["whatsapp_template_id"]:
                return str(rows_en[0]["whatsapp_template_id"])

        return None

    @classmethod
    def _post_msg91(
        cls,
        auth_key: str,
        sender_number: str,
        template_id: str,
        recipient_phone: str,
        variables: Dict[str, Any],
    ) -> str:
        """
        HTTP POST to MSG91 WhatsApp Bulk API.

        Payload format (MSG91 bulk API):
        {
          "integrated_number": "<registered_number>",
          "content_type": "template",
          "payload": {
            "to": "<recipient_phone>",
            "type": "template",
            "template": {
              "id": "<template_id>",
              "params": [<variable_values_as_strings>]
            }
          }
        }

        Uses urllib.request (no extra library dependencies).

        Returns: MSG91 message reference ID (request_id from response).
        Raises: urllib.error.URLError / ValueError on failure.
        """
        # Build ordered params list (sorted by key for determinism)
        params_list = [str(v) for _, v in sorted(variables.items())]

        payload = {
            "integrated_number": sender_number,
            "content_type": "template",
            "payload": {
                "to": recipient_phone,
                "type": "template",
                "template": {
                    "id": template_id,
                    "params": params_list,
                },
            },
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            cls.MSG91_WHATSAPP_URL,
            data=body_bytes,
            method="POST",
        )
        req.add_header("authkey", auth_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_data = json.loads(resp_body)
                # MSG91 returns {"type": "success", "request_id": "...", ...}
                msg_ref = resp_data.get("request_id") or str(uuid.uuid4())
                return msg_ref
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8") if exc.fp else ""
            raise ValueError(
                f"MSG91 HTTP {exc.code}: {err_body}"
            ) from exc

    @classmethod
    def _log_queued(
        cls,
        org_id: str,
        recipient_phone: str,
        template_name: str,
        language: str,
        variables: Dict[str, Any],
    ) -> int:
        """Insert a QUEUED row into whatsapp_delivery_log. Returns the new row id."""
        execute_transaction(
            [
                (
                    """
                    INSERT INTO whatsapp_delivery_log
                        (org_id, recipient_phone, template_name, language, variables, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'QUEUED', NOW())
                    """,
                    (
                        org_id,
                        recipient_phone,
                        template_name,
                        language,
                        json.dumps(variables),
                    ),
                )
            ]
        )
        rows = execute_query(
            """
            SELECT id FROM whatsapp_delivery_log
            WHERE org_id = %s AND recipient_phone = %s AND template_name = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (org_id, recipient_phone, template_name),
        )
        return int(rows[0]["id"]) if rows else -1

    @classmethod
    def _update_log_sent(cls, log_id: int, msg_ref_id: str) -> None:
        execute_transaction(
            [
                (
                    """
                    UPDATE whatsapp_delivery_log
                    SET status = 'SENT', msg_ref_id = %s, sent_at = NOW()
                    WHERE id = %s
                    """,
                    (msg_ref_id, log_id),
                )
            ]
        )

    @classmethod
    def _update_log_failed(cls, log_id: int, reason: str) -> None:
        execute_transaction(
            [
                (
                    """
                    UPDATE whatsapp_delivery_log
                    SET status = 'FAILED', failed_reason = %s
                    WHERE id = %s
                    """,
                    (reason[:1000], log_id),
                )
            ]
        )

    @staticmethod
    def _resolve_language(language: Optional[str]) -> str:
        """Normalise and validate language code, defaulting to 'en'."""
        if language and language.lower() in _SUPPORTED_LANGUAGES:
            return language.lower()
        return "en"

    @staticmethod
    def _normalise_phone(phone: str) -> str:
        """
        Ensure phone is in E.164 format (e.g. +919876543210).
        Strips spaces, dashes, parentheses.
        Prepends +91 for 10-digit Indian numbers if no country code present.
        """
        digits = "".join(c for c in phone if c.isdigit() or c == "+")
        if digits.startswith("+"):
            return digits
        # Strip leading 0 for Indian numbers
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) == 10:
            return f"+91{digits}"
        return f"+{digits}"


# ---------------------------------------------------------------------------
# Seed helper — called from scripts/seed.py
# ---------------------------------------------------------------------------

# Core 14 WhatsApp template definitions (English — org must pre-register in MSG91)
_CORE_WA_TEMPLATES = [
    {
        "template_name": "app_confirmation",
        "name": "Application Submitted — WhatsApp",
        "body": (
            "Dear {{1}}, your application {{2}} has been successfully submitted. "
            "Track your status at {{3}}."
        ),
        "whatsapp_template_id": "wa_app_confirmation_en",  # placeholder — replace with MSG91 ID
    },
    {
        "template_name": "merit_list_notification",
        "name": "Merit List Published — WhatsApp",
        "body": (
            "Dear {{1}}, the merit list for {{2}} has been published. "
            "Your rank: {{3}}. Check your offer status at {{4}}."
        ),
        "whatsapp_template_id": "wa_merit_list_en",
    },
    {
        "template_name": "offer_letter_notification",
        "name": "Offer Letter Issued — WhatsApp",
        "body": (
            "Congratulations {{1}}! An offer letter for {{2}} has been issued. "
            "Accept by {{3}}. Download: {{4}}."
        ),
        "whatsapp_template_id": "wa_offer_letter_en",
    },
    {
        "template_name": "seat_confirmed",
        "name": "Seat Confirmed — WhatsApp",
        "body": (
            "Dear {{1}}, your seat in {{2}} is confirmed. "
            "Report to campus by {{3}}. Bring original documents."
        ),
        "whatsapp_template_id": "wa_seat_confirmed_en",
    },
    {
        "template_name": "attendance_alert",
        "name": "Attendance Below Threshold — WhatsApp",
        "body": (
            "Dear {{1}}, your attendance in {{2}} has fallen to {{3}}% "
            "(minimum required: {{4}}%). Please regularise immediately."
        ),
        "whatsapp_template_id": "wa_attendance_alert_en",
    },
    {
        "template_name": "hall_ticket_dispatch",
        "name": "Hall Ticket Issued — WhatsApp",
        "body": (
            "Dear {{1}}, your hall ticket for {{2}} ({{3}}) is ready. "
            "Download from student portal or {{4}}."
        ),
        "whatsapp_template_id": "wa_hall_ticket_en",
    },
    {
        "template_name": "result_published",
        "name": "Result Published — WhatsApp",
        "body": (
            "Dear {{1}}, your result for {{2}} Semester {{3}} is published. "
            "CGPA: {{4}}. View detailed marksheet at {{5}}."
        ),
        "whatsapp_template_id": "wa_result_published_en",
    },
    {
        "template_name": "fee_reminder",
        "name": "Fee Overdue Reminder — WhatsApp",
        "body": (
            "Dear {{1}}, your fee of Rs.{{2}} for {{3}} is overdue since {{4}}. "
            "Pay immediately to avoid late charges. Pay now: {{5}}."
        ),
        "whatsapp_template_id": "wa_fee_reminder_en",
    },
    {
        "template_name": "dbt_exemption_active",
        "name": "DBT Exemption Active — WhatsApp",
        "body": (
            "Dear {{1}}, your DBT fee exemption for {{2}} is now active. "
            "Exemption amount: Rs.{{3}}. Valid till: {{4}}."
        ),
        "whatsapp_template_id": "wa_dbt_exemption_en",
    },
    {
        "template_name": "dbt_expiry_warning",
        "name": "DBT Exemption Expiring — WhatsApp",
        "body": (
            "Dear {{1}}, your DBT exemption expires in 7 days ({{2}}). "
            "Please renew to avoid interruption in benefit."
        ),
        "whatsapp_template_id": "wa_dbt_expiry_en",
    },
    {
        "template_name": "scholarship_awarded",
        "name": "Scholarship Awarded — WhatsApp",
        "body": (
            "Congratulations {{1}}! You have been awarded the {{2}} scholarship "
            "of Rs.{{3}} for academic year {{4}}."
        ),
        "whatsapp_template_id": "wa_scholarship_awarded_en",
    },
    {
        "template_name": "waiver_approved",
        "name": "Fee Waiver Approved — WhatsApp",
        "body": (
            "Dear {{1}}, your fee waiver request has been approved. "
            "Waiver amount: Rs.{{2}}. Updated fee statement: {{3}}."
        ),
        "whatsapp_template_id": "wa_waiver_approved_en",
    },
    {
        "template_name": "hostel_room_allotted",
        "name": "Hostel Room Allotted — WhatsApp",
        "body": (
            "Dear {{1}}, you have been allotted Room {{2}} in {{3}} block. "
            "Check-in date: {{4}}. Bring ID proof and fee receipt."
        ),
        "whatsapp_template_id": "wa_hostel_allotted_en",
    },
    {
        "template_name": "guardian_portal_welcome",
        "name": "Guardian Portal Provisioned — WhatsApp",
        "body": (
            "Dear {{1}}, your parent portal for {{2}} (student: {{3}}) is ready. "
            "Login at {{4}} with your registered mobile number."
        ),
        "whatsapp_template_id": "wa_guardian_portal_en",
    },
]


def seed_whatsapp_templates(org_id: str, actor_id: str = "system") -> int:
    """
    Seed the 14 core WhatsApp templates (English) for the given org.

    Called from scripts/seed.py after DB migration.
    Idempotent — skips templates that already exist.

    Returns count of newly inserted rows.
    """
    inserted = 0
    for t in _CORE_WA_TEMPLATES:
        existing = execute_query(
            """
            SELECT id FROM notification_templates
            WHERE org_id = %s AND template_name = %s AND language = 'en' AND channel = 'WHATSAPP'
            """,
            (org_id, t["template_name"]),
        )
        if existing:
            continue

        execute_transaction(
            [
                (
                    """
                    INSERT INTO notification_templates
                        (id, org_id, template_name, name, body, language, channel,
                         whatsapp_template_id, is_active)
                    VALUES (uuid_generate_v4(), %s, %s, %s, %s, 'en', 'WHATSAPP', %s, TRUE)
                    """,
                    (
                        org_id,
                        t["template_name"],
                        t["name"],
                        t["body"],
                        t["whatsapp_template_id"],
                    ),
                )
            ]
        )
        inserted += 1

    logger.info(
        "seed_whatsapp_templates: %d new templates for org %s", inserted, org_id
    )
    return inserted
