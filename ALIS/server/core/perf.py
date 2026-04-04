"""
ALIS Performance Optimization Layer — Critical Path Acceleration

This module implements the core performance optimizations without changing
enforcement logic. The principle:

    "Make enforcement cheap, parallel, and off the critical path —
     without changing who enforces what."

Components:
  1. ParallelPreChecks — Run RBAC + locks concurrently (asyncio.gather)
  2. AsyncAuditWriter — Move NON-CRITICAL audit writes off the request latency path
  3. RedisCache — Acceleration layer for read-heavy lookups
  4. AIResultCache — Cache deterministic AI outputs (eligibility, doc verification)
  5. DeferredEventPublisher — DB-only event write in request path

Hard Constraints Preserved:
  - Audit integrity: CRITICAL audits still synchronous; async entries have
    sync fallback if Redis is unavailable; hash chain maintained by worker
  - Tenant isolation: all caches keyed by tenant_id
  - AI governance: gateway remains single entry point
  - State machines: transitions still validated synchronously in DB transaction
  - Global locks: checked before DB write (just in parallel with RBAC)
  - RBAC: cache is deny-only (allowed=True is NEVER cached to prevent stale grants)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# REDIS CONNECTION — lazy singleton with retry on failure
# =============================================================================

_redis_client = None
_redis_lock = threading.Lock()
_redis_last_attempt: float = 0.0
_REDIS_RETRY_INTERVAL = 5.0  # seconds between connection attempts after failure


def _get_redis():
    """
    Get a Redis connection singleton, or None if unavailable.

    Retries connection after _REDIS_RETRY_INTERVAL seconds if previously failed,
    so a Redis restart during runtime is recovered automatically.
    """
    global _redis_client, _redis_last_attempt

    if _redis_client is not None:
        return _redis_client

    # Rate-limit connection attempts to avoid hammering a dead Redis
    now = time.monotonic()
    if now - _redis_last_attempt < _REDIS_RETRY_INTERVAL:
        return None

    with _redis_lock:
        # Double-check after acquiring lock
        if _redis_client is not None:
            return _redis_client
        if time.monotonic() - _redis_last_attempt < _REDIS_RETRY_INTERVAL:
            return None

        _redis_last_attempt = time.monotonic()
        try:
            import redis as redis_lib
            from server.core.settings import settings
            client = redis_lib.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            client.ping()
            _redis_client = client
            return _redis_client
        except Exception as e:
            logger.warning("perf._get_redis: Redis unavailable: %s", e)
            return None


# =============================================================================
# 1. PARALLEL PRE-CHECKS — Run RBAC + locks concurrently
# =============================================================================

class PreCheckResult:
    """Aggregated result of parallel pre-flight checks."""

    def __init__(self) -> None:
        self.allowed: bool = True
        self.rbac_ok: bool = True
        self.locks_ok: bool = True
        self.reasons: List[str] = []
        self._lock = threading.Lock()

    def deny(self, source: str, reason: str) -> None:
        """Thread-safe deny — may be called from multiple executor threads."""
        with self._lock:
            self.allowed = False
            self.reasons.append(f"[{source}] {reason}")
            if source == "rbac":
                self.rbac_ok = False
            elif source == "locks":
                self.locks_ok = False


async def parallel_pre_checks(
    *,
    actor_role: str,
    required_permission: str,
    org_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> PreCheckResult:
    """
    Run RBAC and global lock checks concurrently via asyncio.gather.

    Same enforcement logic — different execution order:
      Before: RBAC → locks (serial, ~10-15ms each = ~20-30ms)
      After:  asyncio.gather(RBAC, locks) (~10-15ms total)

    Sync checks run in the thread pool executor to avoid blocking the event loop.

    RBAC caching policy: ONLY cache denials (TTL 30s).
    Allowed results are NEVER cached to prevent stale permission grants.
    """
    result = PreCheckResult()
    loop = asyncio.get_running_loop()

    def _check_rbac_sync() -> None:
        # Check Redis cache for DENY-only results
        cache_key = f"rbac_deny:{tenant_id}:{actor_role}:{required_permission}"
        r = _get_redis()
        if r is not None:
            try:
                cached = r.get(f"alis:cache:{cache_key}")
                if cached is not None:
                    data = json.loads(cached)
                    # Only denials are cached — if we find a cached entry it's a deny
                    result.deny("rbac", data.get("reason", "Permission denied (cached)"))
                    return
            except Exception:
                pass

        from server.core.rbac import verify_access, Role, Permission
        try:
            role_enum = Role(actor_role)
        except ValueError:
            result.deny("rbac", f"Unknown role: {actor_role}")
            return

        try:
            perm_enum = Permission(required_permission)
        except ValueError:
            result.deny("rbac", f"Unknown permission: {required_permission}")
            return

        access = verify_access(role_enum, perm_enum)

        if not access.allowed:
            result.deny("rbac", access.reason or "Permission denied")
            # Cache the DENIAL for 30s — safe because a deny→allow change
            # (granting a new permission) is rare and 30s delay is acceptable
            if r is not None:
                try:
                    r.setex(
                        f"alis:cache:{cache_key}", 30,
                        json.dumps({"reason": access.reason or "Permission denied"}),
                    )
                except Exception:
                    pass
        # If allowed: do NOT cache — avoids stale grants after permission revocation

    def _check_locks_sync() -> None:
        if not org_id or not entity_id:
            return
        from server.core.locks import GlobalLockRegistry
        lock_result = GlobalLockRegistry.check_all_locks(entity_id, {"org_id": org_id})
        if lock_result.is_locked:
            for reason in lock_result.reasons:
                result.deny("locks", reason)

    futures = [loop.run_in_executor(None, _check_rbac_sync)]
    if org_id and entity_id:
        futures.append(loop.run_in_executor(None, _check_locks_sync))

    gathered = await asyncio.gather(*futures, return_exceptions=True)

    # Fail closed: if any check raised an uncaught exception, deny access
    for i, r in enumerate(gathered):
        if isinstance(r, Exception):
            logger.error("parallel_pre_checks: check %d raised: %s", i, r)
            result.deny("internal", f"Pre-check error: {r}")

    return result


# =============================================================================
# 2. ASYNC AUDIT WRITER — Move NON-CRITICAL audit off the request latency path
# =============================================================================

# Actions that MUST be written synchronously (immediate durability required)
_CRITICAL_AUDIT_ACTIONS = frozenset({
    "state_transition", "login", "logout", "session_revoked",
    "override_requested", "override_approved", "override_rejected", "override_executed",
    "lockdown_activated", "lockdown_deactivated",
    "escalation_requested", "escalation_granted",
    "dual_control_requested", "dual_control_completed",
    "hard_delete", "password_changed", "password_reset_completed",
    "policy_approved", "policy_activated",
})


class AsyncAuditWriter:
    """
    Two-phase audit for NON-CRITICAL actions only.

    Phase A (in request — <1ms): LPUSH to Redis list `alis:audit:pending`
    Phase B (Celery worker — every 2s): RPOP → AuditLedger.log() with hash chain

    CRITICAL actions (state transitions, login, overrides, lockdown) are ALWAYS
    written synchronously via AuditLedger.log() — never deferred.

    Fallback: If Redis is unavailable, enqueue returns False and the caller
    should use AuditLedger.log() directly.
    """

    @staticmethod
    def is_critical(action: str) -> bool:
        """Check if an audit action requires immediate synchronous persistence."""
        return action in _CRITICAL_AUDIT_ACTIONS

    @staticmethod
    def enqueue_sync(
        action: str,
        actor_id: str,
        actor_role: str = "unknown",
        entity_type: str = "",
        entity_id: str = "",
        tenant_id: str = "SYSTEM",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Enqueue a NON-CRITICAL audit entry for async persistence.
        Returns True if enqueued to Redis, False if Redis unavailable or action is critical.
        """
        if AsyncAuditWriter.is_critical(action):
            return False  # Caller must use synchronous AuditLedger.log()

        entry = {
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "tenant_id": tenant_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            r = _get_redis()
            if r is None:
                return False
            r.lpush("alis:audit:pending", json.dumps(entry))
            return True
        except Exception as e:
            logger.warning("AsyncAuditWriter: Redis enqueue failed: %s", e)
            return False

    @staticmethod
    def drain_batch(batch_size: int = 100) -> int:
        """
        Drain pending audit entries from Redis and persist to DB.
        Called by Celery beat task (every 2 seconds).
        Returns number of entries persisted.
        """
        from server.core.audit import AuditLedger, AuditAction

        r = _get_redis()
        if r is None:
            return 0

        persisted = 0
        for _ in range(batch_size):
            raw = r.rpop("alis:audit:pending")
            if raw is None:
                break

            try:
                entry = json.loads(raw)
                action_str = entry.get("action", "create")
                try:
                    action_enum = AuditAction(action_str)
                except ValueError:
                    logger.warning("AsyncAuditWriter: unknown action '%s', recording as CREATE", action_str)
                    action_enum = AuditAction.CREATE

                AuditLedger.log(
                    action=action_enum,
                    actor_id=entry.get("actor_id", "unknown"),
                    actor_role=entry.get("actor_role"),
                    entity_type=entry.get("entity_type", ""),
                    entity_id=entry.get("entity_id", ""),
                    tenant_id=entry.get("tenant_id"),
                    metadata=entry.get("metadata"),
                )
                persisted += 1
            except Exception as e:
                logger.error(
                    "AsyncAuditWriter: failed to persist entry: %s (data: %s)",
                    e, str(raw)[:200],
                )
                try:
                    r.lpush("alis:audit:retry", raw)
                except Exception:
                    pass

        return persisted


# =============================================================================
# 3. REDIS CACHE — Read acceleration (sync, thread-safe via redis-py)
# =============================================================================

class RedisCache:
    """
    General-purpose Redis cache. All methods synchronous.

    Key prefix: alis:cache:{user_key}
    """

    @staticmethod
    def get(key: str) -> Optional[Dict[str, Any]]:
        try:
            r = _get_redis()
            if r is None:
                return None
            raw = r.get(f"alis:cache:{key}")
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    def set(key: str, value: Dict[str, Any], ttl: int = 60) -> bool:
        try:
            r = _get_redis()
            if r is None:
                return False
            r.setex(f"alis:cache:{key}", ttl, json.dumps(value))
            return True
        except Exception:
            return False

    @staticmethod
    def invalidate(key: str) -> bool:
        try:
            r = _get_redis()
            if r is None:
                return False
            r.delete(f"alis:cache:{key}")
            return True
        except Exception:
            return False


# =============================================================================
# 4. AI RESULT CACHE — Deduplicate deterministic AI calls
# =============================================================================

class AIResultCache:
    """
    Cache deterministic AI outputs to avoid redundant LLM calls.

    Only caches extraction/classification/verification (deterministic).
    Does NOT cache generation or reasoning (non-deterministic).
    """

    _CACHEABLE_TASKS = frozenset({"extraction", "classification", "verification"})

    @classmethod
    def get_cached(cls, tenant_id: str, task_class: str, input_data: str, model_version: str) -> Optional[Dict[str, Any]]:
        if task_class not in cls._CACHEABLE_TASKS:
            return None
        return RedisCache.get(f"ai:{cls._make_key(tenant_id, task_class, input_data, model_version)}")

    @classmethod
    def set_cached(cls, tenant_id: str, task_class: str, input_data: str, model_version: str, result: Dict[str, Any], ttl: int = 300) -> bool:
        if task_class not in cls._CACHEABLE_TASKS:
            return False
        return RedisCache.set(f"ai:{cls._make_key(tenant_id, task_class, input_data, model_version)}", result, ttl=ttl)

    @staticmethod
    def _make_key(tenant_id: str, task_class: str, input_data: str, model_version: str) -> str:
        return f"{tenant_id}:{task_class}:{hashlib.sha256(input_data.encode()).hexdigest()[:16]}:{model_version}"


# =============================================================================
# 5. DOMAIN EVENT DECOUPLING — Write-only in request path
# =============================================================================

class DeferredEventPublisher:
    """
    Stage 1: Write event to domain_events table only (in request path).
    Stage 2: perf_tasks.dispatch_pending_events polls every 3s and dispatches.
    """

    @staticmethod
    def publish_deferred(event) -> str:
        """Persist event to DB without Celery dispatch. Returns event ID."""
        from server.db_service import execute_transaction
        execute_transaction([
            (
                """
                INSERT INTO domain_events
                    (id, org_id, event_type, entity_type, entity_id,
                     payload, actor_id, correlation_id, status, published_at,
                     retry_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, 0)
                """,
                (
                    event.id, event.org_id, event.event_type, event.entity_type,
                    event.entity_id, json.dumps(event.payload), event.actor_id,
                    event.correlation_id, event.published_at,
                ),
            )
        ])
        logger.info("DeferredEventPublisher: persisted %s [%s/%s]",
                     event.event_type, event.entity_type, event.entity_id)
        return event.id


# =============================================================================
# 6. VAULT WARM-UP — Prefetch tenant secrets at startup
# =============================================================================

async def warm_vault_cache() -> int:
    """
    Prefetch non-critical secrets at startup so first requests don't hit Vault cold.
    vault_client.py's _SecretCache caches the results internally.
    """
    loop = asyncio.get_running_loop()

    def _warm_sync() -> int:
        try:
            from server.core.vault_client import get_vault_client
            vault = get_vault_client()
            if not vault._is_available():
                logger.info("Vault warm-up skipped — Vault unavailable.")
                return 0
            cached = 0
            for path in ["alis/razorpay_webhook", "alis/msg91_key", "alis/smtp_password"]:
                try:
                    vault.get_secret(path)
                    cached += 1
                except Exception:
                    pass
            logger.info("Vault warm-up: %d secrets prefetched.", cached)
            return cached
        except Exception as e:
            logger.warning("Vault warm-up failed: %s", e)
            return 0

    return await loop.run_in_executor(None, _warm_sync)


# =============================================================================
# 7. MIDDLEWARE SHORT-CIRCUIT
# =============================================================================

_READ_ONLY_PATHS = frozenset({"/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"})


def is_lightweight_request(method: str, path: str) -> bool:
    """True for probes/metrics/docs that can skip detailed request logging."""
    return path in _READ_ONLY_PATHS
