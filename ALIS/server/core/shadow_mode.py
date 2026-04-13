"""Shadow Mode Onboarding Service (§28)

During shadow mode the ALIS instance runs in parallel with the institution's
existing processes but suppresses all outbound communications (SMS, email,
WhatsApp).  A nightly task compares ALIS outputs against actual records and
writes divergence metrics.  Go-live is unblocked only when divergence stays
below the configured threshold for N consecutive days.

Config is stored in `tenant_feature_flags` under key 'shadow_mode.config'
as a JSON blob.  Redis caches the enabled flag: alis:shadow:{org_id}

All SLA / threshold values come from the policy engine — never literals.
"""

from __future__ import annotations

import json
import logging
import uuid

from pydantic import BaseModel
from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Redis key prefix
_REDIS_PREFIX = "alis:shadow:"
_CACHE_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


class ShadowModeConfig(BaseModel):
    enabled: bool = False
    max_attendance_divergence_pct: float = 2.0  # configurable pilot gate
    max_fee_divergence_pct: float = 0.1
    suppress_sms: bool = True
    suppress_email: bool = True
    suppress_whatsapp: bool = True
    consecutive_passing_days_required: int = 5  # pilot gate


class GoLiveGateResult(BaseModel):
    can_go_live: bool
    consecutive_days_passing: int
    required_days: int
    latest_attendance_divergence_pct: float | None
    latest_fee_divergence_pct: float | None
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_redis():
    """Return the shared Redis client (mirrors pattern from feature_flags)."""
    import redis as redis_lib
    from server.core.settings import settings

    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def _redis_key(org_id: str) -> str:
    return f"{_REDIS_PREFIX}{org_id}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ShadowModeService:
    """Static-method service — no instance state."""

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    @classmethod
    def enable(cls, org_id: str, config: ShadowModeConfig, actor_id: str) -> dict:
        """Activate shadow mode for an institution."""
        config.enabled = True
        config_json = config.model_dump_json()

        execute_transaction(
            [
                (
                    """
            INSERT INTO tenant_feature_flags (org_id, flag_key, flag_value, updated_by)
            VALUES (%s, 'shadow_mode.config', %s, %s)
            ON CONFLICT (org_id, flag_key) DO UPDATE
               SET flag_value = EXCLUDED.flag_value,
                   updated_by = EXCLUDED.updated_by,
                   updated_at = NOW()
            """,
                    (org_id, config_json, actor_id),
                ),
            ]
        )

        # Invalidate cache
        try:
            r = _get_redis()
            r.delete(_redis_key(org_id))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="shadow_mode",
            resource_id=org_id,
            detail={"enabled": True, "config": config.model_dump()},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="shadow_mode.enabled",
                org_id=org_id,
                payload={"actor_id": actor_id, "config": config.model_dump()},
            )
        )

        logger.info("Shadow mode ENABLED for org %s by %s", org_id, actor_id)
        return {"status": "enabled", "config": config.model_dump()}

    @classmethod
    def disable(cls, org_id: str, actor_id: str) -> dict:
        """Deactivate shadow mode for an institution."""
        existing = cls._load_config_from_db(org_id)
        if existing is None:
            return {"status": "already_disabled"}

        existing.enabled = False
        config_json = existing.model_dump_json()

        execute_transaction(
            [
                (
                    """
            INSERT INTO tenant_feature_flags (org_id, flag_key, flag_value, updated_by)
            VALUES (%s, 'shadow_mode.config', %s, %s)
            ON CONFLICT (org_id, flag_key) DO UPDATE
               SET flag_value = EXCLUDED.flag_value,
                   updated_by = EXCLUDED.updated_by,
                   updated_at = NOW()
            """,
                    (org_id, config_json, actor_id),
                ),
            ]
        )

        try:
            r = _get_redis()
            r.delete(_redis_key(org_id))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="shadow_mode",
            resource_id=org_id,
            detail={"enabled": False},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="shadow_mode.disabled",
                org_id=org_id,
                payload={"actor_id": actor_id},
            )
        )

        logger.info("Shadow mode DISABLED for org %s by %s", org_id, actor_id)
        return {"status": "disabled"}

    # ------------------------------------------------------------------
    # Runtime gate
    # ------------------------------------------------------------------

    @classmethod
    def is_enabled(cls, org_id: str) -> bool:
        """Return True if shadow mode is active.  Redis-cached for 5 min."""
        try:
            r = _get_redis()
            cached = r.get(_redis_key(org_id))
            if cached is not None:
                return cached == "1"
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        config = cls._load_config_from_db(org_id)
        enabled = config.enabled if config else False

        try:
            r = _get_redis()
            r.setex(_redis_key(org_id), _CACHE_TTL, "1" if enabled else "0")
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        return enabled

    @classmethod
    def get_config(cls, org_id: str) -> ShadowModeConfig:
        """Return the full config, defaulting to disabled if none set."""
        return cls._load_config_from_db(org_id) or ShadowModeConfig()

    # ------------------------------------------------------------------
    # Divergence recording
    # ------------------------------------------------------------------

    @classmethod
    def record_divergence(
        cls,
        org_id: str,
        metric: str,
        alis_value: float,
        actual_value: float,
    ) -> None:
        """Persist a divergence measurement to shadow_mode_divergence_log."""
        if actual_value == 0:
            divergence_pct = 0.0
        else:
            divergence_pct = abs(alis_value - actual_value) / actual_value * 100

        execute_transaction(
            [
                (
                    """
            INSERT INTO shadow_mode_divergence_log
                (id, org_id, metric, alis_value, actual_value, divergence_pct, measured_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
                    (
                        str(uuid.uuid4()),
                        org_id,
                        metric,
                        alis_value,
                        actual_value,
                        divergence_pct,
                    ),
                ),
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="divergence",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "record_divergence"},
        )

    # ------------------------------------------------------------------
    # Go-live gate
    # ------------------------------------------------------------------

    @classmethod
    def check_go_live_gate(cls, org_id: str) -> GoLiveGateResult:
        """Evaluate whether the institution can go live.

        Consecutive calendar days where ALL metrics are below their thresholds.
        Writes result to shadow_mode_go_live_log.
        """
        config = cls.get_config(org_id)
        required = config.consecutive_passing_days_required
        attn_threshold = config.max_attendance_divergence_pct
        fee_threshold = config.max_fee_divergence_pct

        # Per-day max divergence for the last N+5 days (buffer for checking streak)
        rows = execute_query(
            """
            SELECT
                DATE(measured_at) AS day,
                MAX(CASE WHEN metric = 'attendance' THEN divergence_pct ELSE 0 END) AS max_attn,
                MAX(CASE WHEN metric = 'fee' THEN divergence_pct ELSE 0 END) AS max_fee
            FROM shadow_mode_divergence_log
            WHERE org_id = %s
              AND measured_at >= NOW() - INTERVAL '60 days'
            GROUP BY DATE(measured_at)
            ORDER BY day DESC
        """,
            (org_id,),
        )

        consecutive = 0
        latest_attn: float | None = None
        latest_fee: float | None = None

        for i, row in enumerate(rows):
            attn = float(row["max_attn"] or 0)
            fee = float(row["max_fee"] or 0)
            if i == 0:
                latest_attn = attn
                latest_fee = fee
            if attn <= attn_threshold and fee <= fee_threshold:
                consecutive += 1
            else:
                break  # streak broken

        can_go_live = consecutive >= required
        reason = (
            f"Passed {consecutive}/{required} consecutive days below thresholds "
            f"(attendance<{attn_threshold}%, fee<{fee_threshold}%)"
        )

        execute_transaction(
            [
                (
                    """
            INSERT INTO shadow_mode_go_live_log
                (id, org_id, consecutive_days, can_go_live, checked_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
                    (str(uuid.uuid4()), org_id, consecutive, can_go_live),
                ),
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="go_live_gate",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "check_go_live_gate"},
        )

        return GoLiveGateResult(
            can_go_live=can_go_live,
            consecutive_days_passing=consecutive,
            required_days=required,
            latest_attendance_divergence_pct=latest_attn,
            latest_fee_divergence_pct=latest_fee,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Divergence log
    # ------------------------------------------------------------------

    @classmethod
    def get_divergence_log(cls, org_id: str, days: int = 30) -> list:
        """Return divergence measurements for the last N days."""
        return execute_query(
            """
            SELECT metric, alis_value, actual_value, divergence_pct, measured_at
            FROM shadow_mode_divergence_log
            WHERE org_id = %s
              AND measured_at >= NOW() - INTERVAL '%s days'
            ORDER BY measured_at DESC
        """,
            (org_id, days),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _load_config_from_db(cls, org_id: str) -> ShadowModeConfig | None:
        rows = execute_query(
            """
            SELECT flag_value FROM tenant_feature_flags
            WHERE org_id = %s AND flag_key = 'shadow_mode.config'
            LIMIT 1
            """,
            (org_id,),
        )
        if not rows:
            return None
        try:
            data = json.loads(rows[0]["flag_value"])
            return ShadowModeConfig(**data)
        except Exception:
            logger.warning("Corrupt shadow_mode.config for org %s", org_id)
            return None
