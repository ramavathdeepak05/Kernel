"""
Institution Policy Store — E04-S10

Stores and retrieves configurable institution-level rules that drive the
autonomous admissions pipeline. Every institution can tune thresholds
(min academic %, entrance cutoffs, fee deadlines, etc.) without code changes.

Table: institution_policies
  org_id + key → UNIQUE constraint (one value per rule per org)
  value is JSONB — supports scalars, lists, and dicts
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Well-known policy keys — use these constants everywhere, never raw strings
# ---------------------------------------------------------------------------
class PolicyKey:
    # Eligibility thresholds
    MIN_ACADEMIC_PCT        = "admissions.eligibility.min_academic_percentage"
    REVIEW_BAND_LOWER       = "admissions.eligibility.review_band_lower"
    MIN_ENTRANCE_SCORE      = "admissions.eligibility.min_entrance_score"
    DOCS_REQUIRED_FOR_OFFER = "admissions.eligibility.docs_required_for_offer"

    # Counsellor
    MAX_COUNSELLOR_LOAD     = "admissions.counsellor.max_load"

    # Offer letter
    OFFER_VALIDITY_DAYS     = "admissions.offer_letter.validity_days"

    # Finance
    FEE_OVERDUE_GRACE_DAYS  = "finance.fee.overdue_grace_days"

    # Academics
    MIN_ATTENDANCE_PCT      = "academics.attendance.min_percentage"

    # Learning (in-house LMS)
    LEARNING_LATE_PENALTY_PCT = "learning.assignment.late_penalty_pct_default"
    LEARNING_MAX_LATE_DAYS    = "learning.assignment.max_late_days"
    LEARNING_AUTO_BEGIN_REVIEW = "learning.auto_begin_review"

    # Defaults (used when no DB row exists for an org)
    _DEFAULTS: dict[str, Any] = {
        MIN_ACADEMIC_PCT:          55.0,
        REVIEW_BAND_LOWER:         50.0,
        MIN_ENTRANCE_SCORE:        40.0,
        DOCS_REQUIRED_FOR_OFFER:   True,
        MAX_COUNSELLOR_LOAD:       30,
        OFFER_VALIDITY_DAYS:       30,
        FEE_OVERDUE_GRACE_DAYS:    7,
        MIN_ATTENDANCE_PCT:        75.0,
        LEARNING_LATE_PENALTY_PCT: 10.0,
        LEARNING_MAX_LATE_DAYS:    3,
        LEARNING_AUTO_BEGIN_REVIEW: False,
    }


class PolicyStore:
    """CRUD service for institution_policies."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, org_id: str, key: str) -> Any:
        """
        Return the value for a policy key.
        Falls back to PolicyKey._DEFAULTS if no row exists for this org.
        """
        rows = execute_query(
            "SELECT value FROM institution_policies WHERE org_id = %s AND key = %s AND is_active = TRUE",
            (org_id, key),
        )
        if rows:
            return rows[0]["value"]
        return PolicyKey._DEFAULTS.get(key)

    @classmethod
    def get_all(cls, org_id: str, category: Optional[str] = None) -> list[dict]:
        """Return all active policies for an org, optionally filtered by category."""
        if category:
            rows = execute_query(
                "SELECT * FROM institution_policies WHERE org_id = %s AND category = %s AND is_active = TRUE ORDER BY key",
                (org_id, category),
            )
        else:
            rows = execute_query(
                "SELECT * FROM institution_policies WHERE org_id = %s AND is_active = TRUE ORDER BY category, key",
                (org_id,),
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @classmethod
    def upsert(
        cls,
        org_id: str,
        key: str,
        value: Any,
        description: str = "",
        category: str = "general",
        actor_id: str = "system",
    ) -> dict:
        """Create or update a policy. Returns the stored row."""
        execute_transaction([
            (
                """
                INSERT INTO institution_policies
                    (org_id, key, value, description, category, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (org_id, key)
                DO UPDATE SET
                    value       = EXCLUDED.value,
                    description = EXCLUDED.description,
                    category    = EXCLUDED.category,
                    updated_by  = EXCLUDED.updated_by,
                    updated_at  = NOW()
                """,
                (org_id, key, json.dumps(value), description, category, actor_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="institution_policy",
            entity_id=f"{org_id}:{key}",
            org_id=org_id,
            module="E04-S10",
            metadata={"key": key, "value": value, "category": category},
        )

        return {"org_id": org_id, "key": key, "value": value, "category": category}

    @classmethod
    def deactivate(cls, org_id: str, key: str, actor_id: str = "system") -> None:
        """Soft-delete a policy (sets is_active=FALSE)."""
        rows = execute_query(
            "SELECT id FROM institution_policies WHERE org_id = %s AND key = %s",
            (org_id, key),
        )
        if not rows:
            raise NotFoundError(f"Policy not found: {key}")

        execute_transaction([
            (
                "UPDATE institution_policies SET is_active = FALSE, updated_by = %s, updated_at = NOW() WHERE org_id = %s AND key = %s",
                (actor_id, org_id, key),
            )
        ])

        AuditLog.log(
            action=AuditAction.DELETE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="institution_policy",
            entity_id=f"{org_id}:{key}",
            org_id=org_id,
            module="E04-S10",
            metadata={"key": key},
        )

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    @classmethod
    def seed_defaults(cls, org_id: str, actor_id: str = "system") -> int:
        """
        Insert all PolicyKey defaults for an org (skips keys that already exist).
        Called by the seed script and org-creation flow.
        Returns number of rows inserted.
        """
        _CATEGORY_MAP = {
            "admissions": [
                PolicyKey.MIN_ACADEMIC_PCT,
                PolicyKey.REVIEW_BAND_LOWER,
                PolicyKey.MIN_ENTRANCE_SCORE,
                PolicyKey.DOCS_REQUIRED_FOR_OFFER,
                PolicyKey.MAX_COUNSELLOR_LOAD,
                PolicyKey.OFFER_VALIDITY_DAYS,
            ],
            "finance":    [PolicyKey.FEE_OVERDUE_GRACE_DAYS],
            "academics":  [PolicyKey.MIN_ATTENDANCE_PCT],
        }
        count = 0
        for category, keys in _CATEGORY_MAP.items():
            for key in keys:
                existing = execute_query(
                    "SELECT id FROM institution_policies WHERE org_id = %s AND key = %s",
                    (org_id, key),
                )
                if not existing:
                    cls.upsert(
                        org_id=org_id,
                        key=key,
                        value=PolicyKey._DEFAULTS[key],
                        category=category,
                        actor_id=actor_id,
                    )
                    count += 1
        return count
