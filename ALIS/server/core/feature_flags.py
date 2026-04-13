"""Feature Flag System — Institutional Granularity

MODULE: Core Infrastructure
LAYER: Layer 1 (Configuration-as-Data)
REFERENCE: ALIS-skills/references/architecture.md §12

Every feature that can be toggled per institution lives here.
Flags are DB-persisted and Redis-cached (TTL 300s).

Usage
─────
    from server.core.feature_flags import feature_flags

    # Boolean gate
    if not feature_flags.is_enabled("academics.ai_ppt_generation", tenant_id):
        return handle_manual_upload(course_id)

    # Config parameter from flag
    tier = feature_flags.get_config("ai.model_tier.drafting", tenant_id, default="medium")

    # Seed defaults for a new institution (call during onboarding)
    feature_flags.seed_defaults(org_id, actor_id=registrar_id)

Flag Key Convention (dot-notation)
───────────────────────────────────
  module.feature          →  "academics.ai_ppt_generation"
  ai.tier.dimension       →  "ai.model_tier.drafting"
  compliance.requirement  →  "compliance.dpdp_strict_mode"

Must Align With
───────────────
- architecture.md §12 (Feature Flags — Institutional Granularity)
- migration 0016 (tenant_feature_flags table)
- SKILL.md invariant 2: "Configuration is data, not code"
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.core.audit import AuditAction, AuditLog
from server.core.settings import settings
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Redis TTL for flag cache entries (seconds)
_CACHE_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Default flag definitions — seeded for every new institution
# Enabled defaults represent the safe/compliant baseline.
# ---------------------------------------------------------------------------

DEFAULT_FLAGS: dict[str, dict[str, Any]] = {
    # ── MODULE FLAGS ────────────────────────────────────────────────────────
    # Off until institution contracts the specific integration/hardware
    "admissions.digilocker_verification": {"enabled": False, "config": {}},
    "admissions.nta_score_import": {"enabled": False, "config": {}},
    "academics.ai_ppt_generation": {"enabled": False, "config": {}},
    "academics.ai_assignment_drafting": {"enabled": False, "config": {}},
    "examinations.online_proctoring": {"enabled": False, "config": {}},
    "examinations.qr_hall_entry": {"enabled": False, "config": {}},
    "examinations.question_paper_vault": {"enabled": False, "config": {}},
    "finance.emi_payment_plans": {"enabled": True, "config": {}},
    "finance.gst_auto_filing": {"enabled": False, "config": {}},
    "hr.cas_promotion_tracking": {"enabled": True, "config": {}},
    "regulatory.naac_evidence_collection": {"enabled": False, "config": {}},
    # ── AI CAPABILITY FLAGS ─────────────────────────────────────────────────
    # Tier values: "small" | "medium" | "large"
    # These are read by llm_router.py to select the correct model
    "ai.model_tier.extraction": {"enabled": True, "config": {"tier": "small"}},
    "ai.model_tier.drafting": {"enabled": True, "config": {"tier": "medium"}},
    "ai.model_tier.generation": {"enabled": True, "config": {"tier": "medium"}},
    "ai.model_tier.narrative": {"enabled": True, "config": {"tier": "large"}},
    "ai.local_inference_only": {"enabled": True, "config": {}},
    "ai.content_generation_enabled": {"enabled": True, "config": {}},
    # ── COMPLIANCE FLAGS ────────────────────────────────────────────────────
    # On by default — institutions must explicitly opt out (and document why)
    "compliance.dpdp_strict_mode": {"enabled": True, "config": {}},
    "compliance.ugc_fee_regulation_checks": {"enabled": True, "config": {}},
    "compliance.naac_evidence_collection": {"enabled": False, "config": {}},
}


def _get_redis():
    """Return a Redis client. Import deferred so tests can patch before import."""
    import redis as _redis_lib

    return _redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)


def _cache_key(org_id: str, flag_key: str) -> str:
    return f"alis:ff:{org_id}:{flag_key}"


class FeatureFlags:
    """Per-tenant feature flag accessor.

    All methods accept `tenant_id` as an explicit parameter so they can
    be called from both request-scoped code (where the ContextVar is set
    by TenantMiddleware) and from Celery tasks (no HTTP context).
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def is_enabled(flag_key: str, tenant_id: str, default: bool = False) -> bool:
        """Return True if the flag is enabled for `tenant_id`.

        Cache strategy:
          1. Redis cache hit → return immediately
          2. DB fallback → populate cache → return
          3. Redis unavailable → DB only (no cache write attempted)
        """
        # 1. Try Redis cache
        try:
            r = _get_redis()
            cached = r.get(_cache_key(tenant_id, flag_key))
            if cached is not None:
                data = json.loads(cached)
                return bool(data.get("enabled", default))
        except Exception as exc:
            logger.warning("feature_flags: Redis unavailable for is_enabled — %s", exc)

        # 2. DB fallback
        rows = execute_query(
            "SELECT enabled, config FROM tenant_feature_flags "
            "WHERE org_id = %s AND flag_key = %s",
            (tenant_id, flag_key),
            tenant_id=tenant_id,
        )
        if not rows:
            return default

        row = rows[0]
        enabled = bool(row["enabled"])

        # Populate cache
        try:
            r = _get_redis()
            r.setex(
                _cache_key(tenant_id, flag_key),
                _CACHE_TTL,
                json.dumps({"enabled": enabled, "config": row.get("config") or {}}),
            )
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        return enabled

    @staticmethod
    def get_config(flag_key: str, tenant_id: str, default: Any = None) -> Any:
        """Return the config dict/value for a flag, or `default` if the flag is
        absent or disabled.

        Example:
            tier = feature_flags.get_config("ai.model_tier.drafting", tid, "medium")
            # returns "medium" (from config["tier"]) if the flag is enabled
            # returns "medium" (the default) if the flag is off or not seeded
        """
        # 1. Try Redis cache
        try:
            r = _get_redis()
            cached = r.get(_cache_key(tenant_id, flag_key))
            if cached is not None:
                data = json.loads(cached)
                if not data.get("enabled"):
                    return default
                cfg = data.get("config")
                return cfg if cfg else default
        except Exception as exc:
            logger.warning("feature_flags: Redis unavailable for get_config — %s", exc)

        # 2. DB fallback
        rows = execute_query(
            "SELECT enabled, config FROM tenant_feature_flags "
            "WHERE org_id = %s AND flag_key = %s",
            (tenant_id, flag_key),
            tenant_id=tenant_id,
        )
        if not rows or not rows[0]["enabled"]:
            return default

        cfg = rows[0].get("config")
        return cfg if cfg else default

    @staticmethod
    def get_all(tenant_id: str) -> dict[str, dict[str, Any]]:
        """Return all flags for `tenant_id` as a dict keyed by flag_key."""
        rows = execute_query(
            "SELECT flag_key, enabled, config "
            "FROM tenant_feature_flags WHERE org_id = %s ORDER BY flag_key",
            (tenant_id,),
            tenant_id=tenant_id,
        )
        return {
            r["flag_key"]: {
                "enabled": bool(r["enabled"]),
                "config": r.get("config") or {},
            }
            for r in rows
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    def set_flag(
        flag_key: str,
        tenant_id: str,
        enabled: bool,
        config: dict[str, Any] | None = None,
        actor_id: str = "system",
    ) -> None:
        """Enable or disable a flag and optionally update its config.

        Uses INSERT … ON CONFLICT so it is safe to call idempotently.
        Invalidates Redis cache after write.
        """
        execute_transaction(
            [
                (
                    """
                    INSERT INTO tenant_feature_flags
                        (id, org_id, flag_key, enabled, config, updated_by, updated_at)
                    VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (org_id, flag_key) DO UPDATE
                        SET enabled    = EXCLUDED.enabled,
                            config     = EXCLUDED.config,
                            updated_by = EXCLUDED.updated_by,
                            updated_at = NOW()
                    """,
                    (tenant_id, flag_key, enabled, json.dumps(config or {}), actor_id),
                )
            ],
            tenant_id=tenant_id,
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="feature_flag",
            entity_id=flag_key,
            tenant_id=tenant_id,
            metadata={"source": "set_flag", "enabled": enabled},
        )

        # Invalidate cache
        try:
            _get_redis().delete(_cache_key(tenant_id, flag_key))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

    @staticmethod
    def seed_defaults(org_id: str, actor_id: str = "system") -> int:
        """Seed the default flag set for a new institution.

        Idempotent — skips flags that already exist.
        Returns the number of new flags created.
        """
        created = 0
        for flag_key, defaults in DEFAULT_FLAGS.items():
            existing = execute_query(
                "SELECT id FROM tenant_feature_flags WHERE org_id = %s AND flag_key = %s",
                (org_id, flag_key),
                tenant_id=org_id,
            )
            if existing:
                continue

            execute_transaction(
                [
                    (
                        """
                        INSERT INTO tenant_feature_flags
                            (id, org_id, flag_key, enabled, config, updated_by)
                        VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s)
                        """,
                        (
                            org_id,
                            flag_key,
                            defaults["enabled"],
                            json.dumps(defaults["config"]),
                            actor_id,
                        ),
                    )
                ],
                tenant_id=org_id,
            )
            AuditLog.log(
                action=AuditAction.CREATE,
                actor_id=actor_id,
                actor_role="system",
                entity_type="feature_flag",
                entity_id=flag_key,
                tenant_id=org_id,
                metadata={"source": "seed_defaults"},
            )
            created += 1

        logger.info(
            "feature_flags.seed_defaults: created %d flags for org %s", created, org_id
        )
        return created

    @staticmethod
    def invalidate(flag_key: str, tenant_id: str) -> None:
        """Explicitly invalidate the Redis cache entry for a flag.

        Call this after bulk flag updates that bypass set_flag().
        """
        try:
            _get_redis().delete(_cache_key(tenant_id, flag_key))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

    @staticmethod
    def invalidate_all(tenant_id: str) -> None:
        """Invalidate all cached flags for a tenant (e.g. after batch import)."""
        try:
            r = _get_redis()
            pattern = f"alis:ff:{tenant_id}:*"
            keys = list(r.scan_iter(pattern))
            if keys:
                r.delete(*keys)
        except Exception:
            pass  # noqa: S110 — intentionally suppressed


# Module-level singleton — import and use directly
feature_flags = FeatureFlags()
