"""
Moodle LMS Integration Service — P14

Provisions students in Moodle and syncs grades back to ALIS.

Moodle REST API uses a single endpoint for all operations:
    POST {lms_base_url}/webservice/rest/server.php
    form params: wstoken, moodlewsrestformat=json, wsfunction, <function params>

This service is activated by the student.enrolled domain event and can also
be triggered manually via the integrations API.

Feature-gated per tenant via: integrations.lms_enabled (tenant_feature_flags)
Settings-gated globally via:  settings.lms_base_url + settings.lms_api_token
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Moodle function name constants
# ---------------------------------------------------------------------------
_FN_CREATE_USERS   = "core_user_create_users"
_FN_UPDATE_USERS   = "core_user_update_users"
_FN_ENROL_USERS    = "core_enrol_manual_enrol_users"
_FN_GET_USERS      = "core_user_get_users"
_FN_GET_COURSES    = "core_course_get_courses"
_FN_GET_GRADES     = "gradereport_user_get_grade_items"

_SKIPPED = {"status": "skipped", "reason": "LMS not configured"}


class MoodleLMSService:
    """
    Unified client for Moodle LMS provisioning operations.

    All public methods are safe to call when LMS is not configured — they
    return a {"status": "skipped", "reason": "..."} dict instead of raising.
    """

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def is_enabled(self) -> bool:
        """Return True if LMS_BASE_URL and LMS_API_TOKEN are configured."""
        return bool(self._settings.lms_base_url and self._settings.lms_api_token)

    def provision_student(
        self,
        org_id: str,
        student_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Create or update a student account in Moodle.

        Called automatically on the student.enrolled domain event.
        Also reachable via POST /api/v1/integrations/lms/provision/{student_id}.

        If the student's Moodle username already exists (core_user_get_users
        returns a hit) the account is updated rather than duplicated.

        On success:
          - Writes an audit_ledger entry
          - Fires the lms.student_provisioned domain event
        """
        if not self._check_enabled(org_id):
            return _SKIPPED

        student = self._fetch_student(org_id, student_id)
        if not student:
            logger.error("lms_service.provision_student: student %s not found in org %s", student_id, org_id)
            return {"status": "error", "reason": "student not found"}

        username = self._moodle_username(student)
        email    = student.get("email", "")
        fullname = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()

        # --- Check whether account already exists in Moodle ---
        existing = self._get_moodle_user(username)
        if existing:
            moodle_user_id = existing.get("id")
            self._call_moodle(
                _FN_UPDATE_USERS,
                {
                    "users[0][id]":        moodle_user_id,
                    "users[0][email]":     email,
                    "users[0][firstname]": student.get("first_name", ""),
                    "users[0][lastname]":  student.get("last_name", ""),
                },
            )
            action = "updated"
        else:
            resp = self._call_moodle(
                _FN_CREATE_USERS,
                {
                    "users[0][username]":  username,
                    "users[0][password]":  self._temp_password(student),
                    "users[0][firstname]": student.get("first_name", ""),
                    "users[0][lastname]":  student.get("last_name", ""),
                    "users[0][email]":     email,
                },
            )
            moodle_user_id = resp[0].get("id") if isinstance(resp, list) and resp else None
            action = "created"

        # --- Audit entry ---
        self._write_audit(
            org_id=org_id,
            actor_id=actor_id,
            action=f"lms.student_{action}",
            entity_type="student",
            entity_id=student_id,
            detail={"moodle_user_id": moodle_user_id, "username": username},
        )

        # --- Domain event ---
        self._publish_event(
            org_id=org_id,
            event_type="lms.student_provisioned",
            entity_id=student_id,
            actor_id=actor_id,
            payload={
                "moodle_user_id": moodle_user_id,
                "username": username,
                "action": action,
            },
        )

        logger.info(
            "lms_service.provision_student: student=%s moodle_id=%s action=%s",
            student_id, moodle_user_id, action,
        )
        return {
            "status": "ok",
            "action": action,
            "student_id": student_id,
            "moodle_user_id": moodle_user_id,
            "username": username,
        }

    def enrol_in_courses(
        self,
        org_id: str,
        student_id: str,
        course_ids: List[str],
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Enrol the student in the given Moodle course IDs.

        course_ids is a list of Moodle internal course IDs (integers stored
        as strings). The caller is responsible for resolving ALIS course
        records to Moodle course IDs before calling this method.
        """
        if not self._check_enabled(org_id):
            return _SKIPPED

        student = self._fetch_student(org_id, student_id)
        if not student:
            return {"status": "error", "reason": "student not found"}

        username = self._moodle_username(student)
        moodle_user = self._get_moodle_user(username)
        if not moodle_user:
            return {"status": "error", "reason": "moodle account not provisioned yet; call provision_student first"}

        moodle_user_id = moodle_user["id"]
        params: Dict[str, Any] = {}
        for idx, course_id in enumerate(course_ids):
            params[f"enrolments[{idx}][roleid]"]   = 5   # student role (Moodle default)
            params[f"enrolments[{idx}][userid]"]   = moodle_user_id
            params[f"enrolments[{idx}][courseid]"] = int(course_id)

        self._call_moodle(_FN_ENROL_USERS, params)

        self._write_audit(
            org_id=org_id,
            actor_id=actor_id,
            action="lms.courses_enrolled",
            entity_type="student",
            entity_id=student_id,
            detail={"course_ids": course_ids, "moodle_user_id": moodle_user_id},
        )

        logger.info(
            "lms_service.enrol_in_courses: student=%s courses=%s",
            student_id, course_ids,
        )
        return {
            "status": "ok",
            "student_id": student_id,
            "moodle_user_id": moodle_user_id,
            "enrolled_courses": course_ids,
        }

    def sync_grades_to_alis(
        self,
        org_id: str,
        student_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch grade data from Moodle for a student and persist it in the
        lms_grade_sync table in ALIS.

        Called by the weekly sync_lms_grades Celery task, but can also be
        triggered on demand (e.g. before generating a transcript).
        """
        if not self._check_enabled(org_id):
            return _SKIPPED

        student = self._fetch_student(org_id, student_id)
        if not student:
            return {"status": "error", "reason": "student not found"}

        username = self._moodle_username(student)
        moodle_user = self._get_moodle_user(username)
        if not moodle_user:
            return {"status": "skipped", "reason": "no moodle account"}

        moodle_user_id = moodle_user["id"]

        # Fetch grades for all courses the student is enrolled in
        grade_data = self._call_moodle(
            _FN_GET_GRADES,
            {"userid": moodle_user_id},
        )

        grades: List[Dict[str, Any]] = []
        if isinstance(grade_data, dict):
            for item in grade_data.get("usergrades", []):
                for grade_item in item.get("gradeitems", []):
                    grades.append({
                        "course_id":   item.get("courseid"),
                        "course_name": item.get("coursefullname"),
                        "item_name":   grade_item.get("itemname"),
                        "grade":       grade_item.get("graderaw"),
                        "grade_max":   grade_item.get("grademax"),
                        "grade_min":   grade_item.get("grademin"),
                        "percentage":  grade_item.get("percentageformatted"),
                    })

        # Upsert into ALIS (lms_grade_sync table created by migration 0014+)
        from server.db_service import execute_transaction
        import json as _json
        execute_transaction([
            (
                """
                INSERT INTO lms_grade_sync (org_id, student_id, moodle_user_id, grades, synced_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (org_id, student_id) DO UPDATE
                    SET moodle_user_id = EXCLUDED.moodle_user_id,
                        grades         = EXCLUDED.grades,
                        synced_at      = EXCLUDED.synced_at
                """,
                (org_id, student_id, moodle_user_id, _json.dumps(grades)),
            )
        ])

        logger.info(
            "lms_service.sync_grades_to_alis: student=%s grade_items=%d",
            student_id, len(grades),
        )
        return {
            "status": "ok",
            "student_id": student_id,
            "moodle_user_id": moodle_user_id,
            "grade_items_synced": len(grades),
        }

    def deprovision_student(
        self,
        org_id: str,
        student_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Suspend the student's Moodle account on graduation or withdrawal.

        Moodle does not expose a delete-user endpoint via the web service by
        default; suspension (auth=nologin) is the safe and reversible option.
        """
        if not self._check_enabled(org_id):
            return _SKIPPED

        student = self._fetch_student(org_id, student_id)
        if not student:
            return {"status": "error", "reason": "student not found"}

        username = self._moodle_username(student)
        moodle_user = self._get_moodle_user(username)
        if not moodle_user:
            return {"status": "skipped", "reason": "no moodle account found"}

        moodle_user_id = moodle_user["id"]
        self._call_moodle(
            _FN_UPDATE_USERS,
            {
                "users[0][id]":       moodle_user_id,
                "users[0][suspended]": 1,   # 1 = suspended, 0 = active
            },
        )

        self._write_audit(
            org_id=org_id,
            actor_id=actor_id,
            action="lms.student_deprovisioned",
            entity_type="student",
            entity_id=student_id,
            detail={"moodle_user_id": moodle_user_id},
        )

        self._publish_event(
            org_id=org_id,
            event_type="lms.student_deprovisioned",
            entity_id=student_id,
            actor_id=actor_id,
            payload={"moodle_user_id": moodle_user_id},
        )

        logger.info("lms_service.deprovision_student: student=%s moodle_id=%s suspended", student_id, moodle_user_id)
        return {
            "status": "ok",
            "action": "suspended",
            "student_id": student_id,
            "moodle_user_id": moodle_user_id,
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _check_enabled(self, org_id: str) -> bool:
        """Return False (and log a warning) when LMS is not configured or feature-flagged off."""
        if not self.is_enabled():
            logger.warning("lms_service: LMS not configured (LMS_BASE_URL / LMS_API_TOKEN missing)")
            return False
        # Per-tenant feature flag check
        try:
            from server.core.feature_flags import feature_flags
            if not feature_flags.is_enabled("integrations.lms_enabled", org_id):
                logger.info("lms_service: LMS feature flag disabled for org=%s", org_id)
                return False
        except Exception:
            # Feature flags unavailable (e.g. test environment) — allow through
            pass
        return True

    def _call_moodle(self, wsfunction: str, extra_params: Optional[Dict[str, Any]] = None) -> Any:
        """
        POST to the Moodle web service endpoint.

        All Moodle REST calls use a single URL with form-encoded parameters.
        Returns the parsed JSON response (list or dict depending on function).
        Raises on HTTP errors or Moodle-level exception responses.
        """
        import httpx

        url = f"{self._settings.lms_base_url.rstrip('/')}/webservice/rest/server.php"
        params: Dict[str, Any] = {
            "wstoken":             self._settings.lms_api_token,
            "moodlewsrestformat":  "json",
            "wsfunction":          wsfunction,
        }
        if extra_params:
            params.update(extra_params)

        timeout = getattr(self._settings, "lms_timeout_seconds", 30)
        try:
            resp = httpx.post(url, data=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("lms_service._call_moodle: wsfunction=%s error=%s", wsfunction, exc)
            raise

        # Moodle returns {"exception": "...", "message": "..."} on errors
        if isinstance(data, dict) and "exception" in data:
            logger.error(
                "lms_service._call_moodle: Moodle exception for %s — %s: %s",
                wsfunction, data.get("exception"), data.get("message"),
            )
            raise RuntimeError(f"Moodle error [{wsfunction}]: {data.get('message')}")

        return data

    def _get_moodle_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Look up a Moodle user by username. Returns the user dict or None."""
        try:
            resp = self._call_moodle(
                _FN_GET_USERS,
                {"criteria[0][key]": "username", "criteria[0][value]": username},
            )
            users: List[Dict[str, Any]] = resp.get("users", []) if isinstance(resp, dict) else []
            return users[0] if users else None
        except Exception as exc:
            logger.warning("lms_service._get_moodle_user: failed for username=%s — %s", username, exc)
            return None

    def _fetch_student(self, org_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        """Fetch student row from ALIS DB."""
        from server.db_service import execute_query
        rows = execute_query(
            """
            SELECT id, org_id, roll_number, email, first_name, last_name, status
            FROM students
            WHERE id = %s AND org_id = %s
            """,
            (student_id, org_id),
        )
        return dict(rows[0]) if rows else None

    @staticmethod
    def _moodle_username(student: Dict[str, Any]) -> str:
        """Derive the canonical Moodle username from the student record."""
        roll = student.get("roll_number") or student.get("id", "")
        return f"student_{str(roll).lower()}"

    @staticmethod
    def _temp_password(student: Dict[str, Any]) -> str:
        """
        Generate an initial password for new Moodle accounts.

        Format: Alis@<roll_number> — forces a password change on first login
        via Moodle's forced-password-change policy.  This value is never
        persisted in ALIS; the student resets it via Moodle's forgot-password
        flow or the institution's SSO.
        """
        roll = student.get("roll_number") or student.get("id", "default")
        return f"Alis@{roll}"

    def _write_audit(
        self,
        org_id: str,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        detail: Dict[str, Any],
    ) -> None:
        """Append an immutable record to audit_ledger."""
        import json as _json
        from server.db_service import execute_transaction
        try:
            execute_transaction([
                (
                    """
                    INSERT INTO audit_ledger
                        (org_id, actor_id, action, entity_type, entity_id, detail, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (org_id, actor_id, action, entity_type, entity_id, _json.dumps(detail)),
                )
            ])
        except Exception as exc:
            # Audit failures must never abort the main flow
            logger.error("lms_service._write_audit: failed — %s", exc)

    def _publish_event(
        self,
        org_id: str,
        event_type: str,
        entity_id: str,
        actor_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Fire a domain event via the event bus."""
        try:
            from server.core.domain_events import DomainEvent, DomainEventBus
            DomainEventBus.publish(DomainEvent(
                event_type=event_type,
                entity_type="student",
                entity_id=entity_id,
                org_id=org_id,
                payload=payload,
                actor_id=actor_id,
            ))
        except Exception as exc:
            # Event publish failures must not abort provisioning
            logger.error("lms_service._publish_event: failed to publish %s — %s", event_type, exc)
