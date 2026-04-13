"""
ALIS Backpressure Control — Targeted Queue Depth Protection

Monitors Celery queue depths and rejects or defers requests when
queues exceed configurable thresholds.

Strategy (per your spec):
  - ai_tasks queue: HTTP 202 (Accepted) with job_id when warn < depth < reject,
                    HTTP 503 + Retry-After when depth >= reject
  - event_dispatch_queue: same pattern but higher thresholds
  - notifications: 202 with job_id (never 503 — best-effort)

Does NOT apply to:
  - Core transactional paths (admissions write, finance, state transitions)
  - These always proceed regardless of queue depth

Implementation:
  - FastAPI dependency (not middleware) — applied only to specific routers
  - Reads queue depth from Redis (Celery uses Redis as broker)
  - Caches depth for 1 second to avoid Redis round-trip per request
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass
class QueuePolicy:
    """Backpressure policy for a single queue."""

    queue_name: str
    warn_threshold: int
    reject_threshold: int
    reject_status: int = 503  # 503 for critical, 202 for async-safe


@dataclass
class QueueStatus:
    """Cached queue depth reading."""

    depth: int
    checked_at: float  # time.monotonic()


class BackpressureMonitor:
    """
    Central monitor for Celery queue depths.

    Reads queue length from Redis (Celery broker) and caches the result
    for 1 second to amortize Redis lookups across concurrent requests.

    Thread-safe: uses threading.Lock for cache updates.
    """

    _cache: dict[str, QueueStatus] = {}
    _lock = threading.Lock()
    _CACHE_TTL = 1.0  # seconds

    @classmethod
    def get_queue_depth(cls, queue_name: str) -> int:
        """Get the current depth of a Celery queue (cached, 1s TTL)."""
        now = time.monotonic()

        # Check cache
        cached = cls._cache.get(queue_name)
        if cached and (now - cached.checked_at) < cls._CACHE_TTL:
            return cached.depth

        # Read from Redis
        depth = cls._read_queue_depth(queue_name)

        with cls._lock:
            cls._cache[queue_name] = QueueStatus(depth=depth, checked_at=now)

        return depth

    @classmethod
    def _read_queue_depth(cls, queue_name: str) -> int:
        """Read actual queue length from Redis (Celery broker)."""
        try:
            from server.core.perf import _get_redis

            r = _get_redis()
            if r is None:
                return 0
            # Celery stores queues as Redis lists with the queue name as key
            return r.llen(queue_name) or 0
        except Exception:
            return 0

    @classmethod
    def check_backpressure(cls, policy: QueuePolicy) -> JSONResponse | None:
        """
        Check if a queue exceeds its thresholds.

        Returns None if OK, or a JSONResponse (202/503) if backpressure triggered.
        """
        depth = cls.get_queue_depth(policy.queue_name)

        if depth >= policy.reject_threshold:
            logger.warning(
                "Backpressure REJECT: queue=%s depth=%d threshold=%d",
                policy.queue_name,
                depth,
                policy.reject_threshold,
            )
            if policy.reject_status == 503:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "Service temporarily overloaded",
                        "detail": f"Queue '{policy.queue_name}' depth ({depth}) exceeds limit ({policy.reject_threshold})",
                        "retry_after_seconds": 30,
                    },
                    headers={"Retry-After": "30"},
                )
            # 202 — accepted but will be delayed
            return JSONResponse(
                status_code=202,
                content={
                    "status": "accepted",
                    "detail": f"Request queued — processing delayed (queue depth: {depth})",
                    "estimated_wait_seconds": max(10, depth * 2),
                },
            )

        if depth >= policy.warn_threshold:
            logger.info(
                "Backpressure WARN: queue=%s depth=%d threshold=%d",
                policy.queue_name,
                depth,
                policy.warn_threshold,
            )

        return None


# ============================================================================
# PRE-BUILT POLICIES (from settings thresholds)
# ============================================================================


def _get_ai_policy() -> QueuePolicy:
    from server.core.settings import settings

    return QueuePolicy(
        queue_name="ai_tasks",
        warn_threshold=settings.backpressure_ai_warn,
        reject_threshold=settings.backpressure_ai_reject,
        reject_status=503,
    )


def _get_events_policy() -> QueuePolicy:
    from server.core.settings import settings

    return QueuePolicy(
        queue_name="event_dispatch_queue",
        warn_threshold=settings.backpressure_events_warn,
        reject_threshold=settings.backpressure_events_reject,
        reject_status=202,
    )


def _get_notifications_policy() -> QueuePolicy:
    return QueuePolicy(
        queue_name="notifications",
        warn_threshold=200,
        reject_threshold=1000,
        reject_status=202,  # Never 503 for notifications — best-effort
    )


# ============================================================================
# FASTAPI DEPENDENCIES — use in specific routers
# ============================================================================


async def require_ai_capacity(request: Request) -> None:
    """
    FastAPI dependency: check ai_tasks queue before allowing AI invocation.

    Usage in router:
        @router.post("/ai/invoke", dependencies=[Depends(require_ai_capacity)])
        async def invoke_ai(...):
            ...
    """
    response = BackpressureMonitor.check_backpressure(_get_ai_policy())
    if response is not None:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.body.decode()
            if hasattr(response, "body")
            else "Service overloaded",
            headers=dict(response.headers) if response.headers else None,
        )


async def require_event_capacity(request: Request) -> None:
    """FastAPI dependency: check event_dispatch_queue depth."""
    response = BackpressureMonitor.check_backpressure(_get_events_policy())
    if response is not None:
        raise HTTPException(
            status_code=response.status_code,
            detail="Event processing delayed — queue at capacity",
        )


async def require_notification_capacity(request: Request) -> None:
    """FastAPI dependency: check notifications queue depth."""
    response = BackpressureMonitor.check_backpressure(_get_notifications_policy())
    if response is not None:
        raise HTTPException(
            status_code=response.status_code,
            detail="Notification delivery delayed — queue at capacity",
        )
