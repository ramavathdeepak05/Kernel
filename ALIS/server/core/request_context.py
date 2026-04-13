"""
ALIS Request Context — Request-scoped state for performance optimizations.

Provides a ContextVar-based RequestContext that tracks:
  - tenant_id: current tenant
  - has_write: whether a write has occurred in this request
  - last_write_at: monotonic timestamp of the last write
  - consistency_mode: "strong" (primary only) or "eventual" (replica OK)

Used by:
  - db_service.py: smart read/write routing
  - perf.py: parallel pre-checks
  - backpressure middleware

Thread-safety:
  ContextVar is coroutine-safe and thread-local by default.
  Each FastAPI request handler gets its own context.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass

# Request-scoped context — set by middleware, read by db_service
_request_ctx: ContextVar[RequestContext] = ContextVar("_request_ctx")


@dataclass
class RequestContext:
    """Request-scoped state for smart DB routing and optimization."""

    tenant_id: str = ""
    has_write: bool = False
    last_write_at: float = 0.0  # time.monotonic() of last write
    consistency_mode: str = "strong"  # "strong" | "eventual"

    def mark_write(self) -> None:
        """Call after any DB write (execute_transaction) in this request."""
        self.has_write = True
        self.last_write_at = time.monotonic()

    def should_use_replica(self, stickiness_seconds: float = 2.0) -> bool:
        """
        Determine if a read query can safely use the replica.

        Returns False (use primary) when:
          - consistency_mode is "strong"
          - A write has occurred in this request AND we're within stickiness window
          - No replica is configured (checked by caller)
        """
        if self.consistency_mode == "strong":
            return False
        if self.has_write:
            elapsed = time.monotonic() - self.last_write_at
            if elapsed < stickiness_seconds:
                return False
        return True


def get_request_context() -> RequestContext:
    """Get the current request context, or a default (strong consistency)."""
    try:
        return _request_ctx.get()
    except LookupError:
        return RequestContext(consistency_mode="strong")


def set_request_context(ctx: RequestContext) -> None:
    """Set the request context for the current coroutine/thread."""
    _request_ctx.set(ctx)
