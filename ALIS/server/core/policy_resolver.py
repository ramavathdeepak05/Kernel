"""
ALIS Policy Resolver Middleware — E00-S10

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Layer 3 (Deterministic Decision Binding) + Layer 4 (Non-Bypassable Enforcement) +
       Layer 6 (Decision Audit Linkage)
ENTITY: PolicyResolver

This module implements the Policy Resolver middleware layer required by E00-S10.
It ensures that:
  1. Every rule execution resolves the correct active policy version
     before any institutional decision is made.
  2. If no active policy version exists for the requested type and date,
     execution is blocked (Layer 4 — non-bypassable enforcement).
  3. Resolved policies are cached safely with a TTL to avoid
     hitting the database on every request.
  4. The policy_version_used is attached to the request context so
     that every decision event can log it (Layer 6 — decision audit linkage).

Architecture:
─────────────
  PolicyResolverCache     — Thread-safe, TTL-based in-memory cache for active policies.
  RequirePolicy           — FastAPI Dependency (parameterized callable) that injects
                            the resolved policy into endpoint handlers.
  resolve_policy_for_rule — Standalone function for Rule Engine / ILL invocations
                            outside of HTTP request context.

Usage (FastAPI endpoint):
    from server.core.policy_resolver import RequirePolicy

    @router.post("/evaluate")
    async def evaluate_student(
        body: EvalRequest,
        policy: dict = Depends(RequirePolicy("attendance_threshold")),
    ):
        # `policy` is guaranteed to be a valid, ACTIVATED policy dict.
        # policy["id"], policy["version"], policy["parameters"] are available.
        ...

Usage (Rule Engine / ILL — non-HTTP context):
    from server.core.policy_resolver import resolve_policy_for_rule

    policy = resolve_policy_for_rule(
        policy_type="grading_cutoff",
        tenant_id="tenant_001",
        decision_date=datetime(2027, 3, 15, tzinfo=timezone.utc),
    )

Must Align With:
  - E00-S09: Policy Governance & Registry (source of truth)
  - ALIS Logic Layer v1.0, Section 9 (Policy Binding)
  - ALIS Logic Layer v1.0, Section 10 (Execution Flow, step 3)
  - ALIS Default Governance Posture v1.0 (strict by default)

Hard Constraints:
  - No module may access raw policy_registry DB table directly.
  - All policy access MUST go through this resolver.
  - If policy resolution fails, the operation MUST be blocked.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from .audit import AuditLog, AuditAction

logger = logging.getLogger(__name__)


# ============================================================================
# POLICY RESOLVER CACHE  (Thread-Safe, TTL-Based)
# ============================================================================

class PolicyResolverCache:
    """
    Thread-safe in-memory cache for resolved active policies.

    Keyed by (tenant_id, policy_type).  Each entry stores:
      - The resolved policy dict (from PolicyService.get_active_policy_by_type)
      - The timestamp when the entry was cached

    Entries expire after `ttl_seconds` (default: 300s = 5 minutes).
    Cache invalidation also occurs on PolicyActivated events via `invalidate()`.

    Thread Safety:
      Uses a threading.Lock to protect concurrent reads/writes.
      This is safe for FastAPI's threaded worker model.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._ttl_seconds = ttl_seconds
        self._cache: Dict[Tuple[str, str], Tuple[Dict[str, Any], datetime]] = {}
        self._lock = threading.Lock()

    def get(
        self,
        tenant_id: str,
        policy_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached policy if it exists and has not expired.

        Returns:
            The cached policy dict, or None if not cached / expired.
        """
        key = (tenant_id, policy_type)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            policy, cached_at = entry
            elapsed = (datetime.now(timezone.utc) - cached_at).total_seconds()

            if elapsed > self._ttl_seconds:
                # Expired — remove and return None
                del self._cache[key]
                logger.debug(
                    "Cache expired [tenant=%s type=%s elapsed=%.1fs]",
                    tenant_id, policy_type, elapsed,
                )
                return None

            return policy

    def put(
        self,
        tenant_id: str,
        policy_type: str,
        policy: Dict[str, Any],
    ) -> None:
        """
        Store a resolved policy in the cache.
        """
        key = (tenant_id, policy_type)
        with self._lock:
            self._cache[key] = (policy, datetime.now(timezone.utc))
        logger.debug(
            "Cache stored [tenant=%s type=%s version=%s]",
            tenant_id, policy_type, policy.get("version"),
        )

    def invalidate(
        self,
        tenant_id: str,
        policy_type: Optional[str] = None,
    ) -> int:
        """
        Invalidate cached entries.

        If policy_type is given, invalidates only that specific entry.
        If policy_type is None, invalidates ALL entries for the tenant.

        Returns:
            Number of entries invalidated.
        """
        count = 0
        with self._lock:
            if policy_type:
                key = (tenant_id, policy_type)
                if key in self._cache:
                    del self._cache[key]
                    count = 1
            else:
                keys_to_remove = [
                    k for k in self._cache if k[0] == tenant_id
                ]
                for k in keys_to_remove:
                    del self._cache[k]
                    count += 1

        if count:
            logger.info(
                "Cache invalidated [tenant=%s type=%s entries=%d]",
                tenant_id, policy_type or "*", count,
            )
        return count

    def clear(self) -> None:
        """Clear the entire cache (used in testing)."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Return the number of entries in the cache."""
        with self._lock:
            return len(self._cache)


# Global singleton cache instance
_resolver_cache = PolicyResolverCache()


def get_resolver_cache() -> PolicyResolverCache:
    """Return the global PolicyResolverCache singleton."""
    return _resolver_cache


# ============================================================================
# CORE RESOLUTION LOGIC
# ============================================================================

def resolve_policy_for_rule(
    policy_type: str,
    tenant_id: str,
    decision_date: Optional[datetime] = None,
    actor_id: str = "system",
    actor_role: str = "system",
) -> Dict[str, Any]:
    """
    Resolve the active policy for a given type and tenant.

    This is the primary entry point for Rule Engine and ILL invocations
    that occur outside the HTTP request context (e.g., background jobs,
    event handlers, agent workflows).

    Flow:
      1. Check the in-memory cache.
      2. On cache miss, query PolicyService.get_active_policy_by_type.
      3. If found, cache the result and return it.
      4. If NOT found, raise PolicyResolutionError (Layer 4 — block execution).

    Args:
        policy_type:    The policy category to resolve (e.g., 'attendance_threshold').
        tenant_id:      The tenant scope for the query.
        decision_date:  The date for temporal resolution. Defaults to now (UTC).
        actor_id:       Actor performing the resolution (for audit on failure).
        actor_role:     Role of the actor (for audit on failure).

    Returns:
        Dict containing the full policy record including 'id', 'version',
        'parameters', 'content_hash', 'effective_from', etc.

    Raises:
        PolicyResolutionError: If no active policy exists for the given
                               type/tenant/date combination.
    """
    from .exceptions import PolicyResolutionError
    from .policy_service import PolicyService

    ref_date = decision_date or datetime.now(timezone.utc)
    cache = get_resolver_cache()

    # 1. Check cache (only for current-time queries to keep cache simple)
    if decision_date is None:
        cached = cache.get(tenant_id, policy_type)
        if cached is not None:
            logger.debug(
                "Policy resolved from cache [type=%s tenant=%s version=%s]",
                policy_type, tenant_id, cached.get("version"),
            )
            return cached

    # 2. Query PolicyService (DB lookup)
    policy = PolicyService.get_active_policy_by_type(
        policy_type=policy_type,
        tenant_id=tenant_id,
        as_of_date=ref_date,
    )

    # 3. Block if no active policy (Layer 4 — non-bypassable)
    if policy is None:
        # Audit the failure
        AuditLog.log(
            action=AuditAction.ACCESS_DENIED,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="policy_resolver",
            entity_id=policy_type,
            tenant_id=tenant_id,
            metadata={
                "reason": "No active policy found",
                "policy_type": policy_type,
                "decision_date": str(ref_date),
            },
        )

        raise PolicyResolutionError(
            message=(
                f"No active policy found for type '{policy_type}' "
                f"as of {ref_date.isoformat()}. "
                f"Execution blocked — Layer 4 enforcement."
            ),
            details={
                "policy_type": policy_type,
                "tenant_id": tenant_id,
                "decision_date": str(ref_date),
            },
        )

    # 4. Cache the result (only for current-time queries)
    if decision_date is None:
        cache.put(tenant_id, policy_type, policy)

    logger.info(
        "Policy resolved [type=%s tenant=%s version=%s id=%s]",
        policy_type, tenant_id, policy.get("version"), policy.get("id"),
    )

    return policy


# ============================================================================
# FASTAPI DEPENDENCY — RequirePolicy
# ============================================================================

class RequirePolicy:
    """
    Parameterized FastAPI Dependency for Policy Resolution.

    This callable class acts as the "middleware" for E00-S10.  It is
    injected into any FastAPI endpoint that requires a resolved policy
    before executing a rule or institutional decision.

    Usage:
        @router.post("/evaluate")
        async def evaluate(
            body: EvalRequest,
            policy: dict = Depends(RequirePolicy("attendance_threshold")),
        ):
            # `policy` is guaranteed to be active and valid.
            version = policy["version"]
            params = policy["parameters"]
            ...

    Behavior:
      - Resolves the active policy for the given type and tenant.
      - Attaches `policy_version_used` to `request.state` for downstream
        audit logging (Layer 6).
      - On resolution failure, returns HTTP 428 (Precondition Required)
        to indicate that the required policy is missing.
    """

    def __init__(self, policy_type: str):
        """
        Args:
            policy_type: The policy category to resolve
                         (e.g., 'attendance_threshold', 'grading_cutoff').
        """
        self.policy_type = policy_type

    async def __call__(self, request: Any = None) -> Dict[str, Any]:
        """
        FastAPI dependency callable.

        Extracts tenant_id from request context and resolves the policy.

        Args:
            request: The FastAPI Request object (injected automatically).

        Returns:
            The resolved policy dict.

        Raises:
            HTTPException(428): If no active policy is found.
        """
        from fastapi import HTTPException, Request

        # If called from FastAPI dependency injection, `request` is a Request
        # object. Extract tenant_id and actor info from it.
        tenant_id = "default_tenant"
        actor_id = "unknown"
        actor_role = "unknown"
        decision_date = None

        if request is not None and hasattr(request, "state"):
            # Try to get tenant_id from request.state (set by TenantMiddleware)
            tenant_id = getattr(request.state, "tenant_id", None) or tenant_id

            # Try X-Tenant-ID header as fallback
            if tenant_id == "default_tenant" and hasattr(request, "headers"):
                tenant_id = request.headers.get("x-tenant-id", "default_tenant")

            # Extract actor info if available
            actor_id = getattr(request.state, "actor_id", "unknown")
            actor_role = getattr(request.state, "actor_role", "unknown")

            # Check for explicit decision_date in query params
            if hasattr(request, "query_params"):
                date_param = request.query_params.get("decision_date")
                if date_param:
                    try:
                        decision_date = datetime.fromisoformat(date_param)
                    except (ValueError, TypeError):
                        pass  # Use current time

        try:
            policy = resolve_policy_for_rule(
                policy_type=self.policy_type,
                tenant_id=tenant_id,
                decision_date=decision_date,
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except Exception as e:
            # Convert PolicyResolutionError to HTTP 428 Precondition Required
            logger.warning(
                "Policy resolution failed for endpoint [type=%s tenant=%s]: %s",
                self.policy_type, tenant_id, str(e),
            )
            raise HTTPException(
                status_code=428,
                detail={
                    "error": "Policy resolution failed",
                    "code": "ERR_E00S10_NO_ACTIVE_POLICY",
                    "policy_type": self.policy_type,
                    "message": str(e),
                },
            )

        # Attach policy version to request.state for audit linkage (Layer 6)
        if request is not None and hasattr(request, "state"):
            request.state.policy_version_used = {
                "policy_id": policy.get("id"),
                "policy_type": policy.get("policy_type"),
                "version": policy.get("version"),
                "content_hash": policy.get("content_hash"),
            }

        return policy


# ============================================================================
# CONVENIENCE: Build a Policy Context dict for ILL / Rule Engine
# ============================================================================

def build_policy_context(policy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a read-only policy context dict for ILL consumption.

    As defined in ALIS Logic Layer v1.0, Section 9:
      "ILL receives policy_context as read-only input."

    This function extracts the fields the ILL needs and freezes them
    into a simple dictionary.

    Args:
        policy: The full policy dict from the resolver.

    Returns:
        A dict containing only the fields ILL / Rule Engine should see:
          - policy_id
          - policy_type
          - version
          - parameters (the structured thresholds / ranges)
          - content_hash
          - effective_from
          - effective_to
    """
    return {
        "policy_id": policy.get("id"),
        "policy_type": policy.get("policy_type"),
        "version": policy.get("version"),
        "parameters": policy.get("parameters", {}),
        "content_hash": policy.get("content_hash"),
        "effective_from": str(policy.get("effective_from")),
        "effective_to": str(policy.get("effective_to")),
    }
"""
ALIS Policy Resolver Middleware — E00-S10
"""
