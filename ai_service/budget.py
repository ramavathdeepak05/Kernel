"""
Token Budget Tracker — S3

Tracks per-tenant monthly token usage in Redis and enforces plan limits.

Redis key: alis:ai:budget:{tenant_id}:{YYYY-MM}  →  integer (tokens used)
TTL: 35 days (covers full month + 5-day grace)

All operations are fire-and-forget in the hot path — budget enforcement
degrades gracefully if Redis is unavailable (allows request through with log).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_BUDGET_PREFIX = "alis:ai:budget:"
_TTL_SECONDS = 35 * 86400  # 35 days


def _get_redis():
    from ai_service.settings import settings
    import redis
    return redis.from_url(settings.redis_url, decode_responses=True)


def _budget_key(tenant_id: str) -> str:
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"{_BUDGET_PREFIX}{tenant_id}:{ym}"


def _plan_limit(plan: str) -> int:
    from ai_service.settings import settings
    limits = {
        "starter":    settings.budget_starter_monthly_tokens,
        "growth":     settings.budget_growth_monthly_tokens,
        "enterprise": settings.budget_enterprise_monthly_tokens,
    }
    return limits.get(plan, settings.budget_starter_monthly_tokens)


def get_usage(tenant_id: str) -> int:
    """Return tokens used this month. Returns 0 on Redis error."""
    try:
        r = _get_redis()
        val = r.get(_budget_key(tenant_id))
        return int(val) if val else 0
    except Exception as exc:
        logger.warning("BudgetTracker.get_usage failed for tenant=%s: %s", tenant_id, exc)
        return 0


def check_budget(tenant_id: str, plan: str, requested_tokens: int) -> tuple[bool, int, int]:
    """
    Check if tenant has sufficient budget for `requested_tokens`.

    Returns (allowed, used, limit).
    Fails open on Redis error (allows the request through).
    """
    try:
        used = get_usage(tenant_id)
        limit = _plan_limit(plan)
        return (used + requested_tokens) <= limit, used, limit
    except Exception as exc:
        logger.warning("BudgetTracker.check_budget failed, failing open: %s", exc)
        return True, 0, _plan_limit(plan)


def record_usage(tenant_id: str, tokens_used: int) -> None:
    """
    Atomically increment the monthly token counter.
    Fire-and-forget — errors are logged but do not fail the request.
    """
    try:
        r = _get_redis()
        key = _budget_key(tenant_id)
        pipe = r.pipeline()
        pipe.incrby(key, tokens_used)
        pipe.expire(key, _TTL_SECONDS)
        pipe.execute()
    except Exception as exc:
        logger.warning("BudgetTracker.record_usage failed for tenant=%s: %s", tenant_id, exc)


def reset_usage(tenant_id: str) -> None:
    """Reset the current month's usage (admin operation)."""
    try:
        _get_redis().delete(_budget_key(tenant_id))
    except Exception as exc:
        logger.warning("BudgetTracker.reset_usage failed: %s", exc)
