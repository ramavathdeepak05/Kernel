"""
ALIS AI Observability & Cost Controls — E03-S10

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 6 (System Logbook — read-only aggregation)
ENTITY: AIObservabilityService

Aggregates AI usage metrics from the immutable audit ledger.
All metrics are derived from AI_INVOCATION, GUARDRAIL_*, HITL_*,
and AGENT_EXECUTION audit entries.

No additional tables are written — observability is a pure read
projection over the existing audit ledger. This preserves the
append-only invariant (Layer 4) and avoids dual-write consistency issues.

Acceptance Criteria (E03-S10):
    - [x] Invocation counts
    - [x] Latency tracking
    - [x] Failure rates
    - [x] Model usage metrics
    - [x] No user-visible telemetry leakage
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Actions we aggregate for AI observability
_AI_ACTIONS = (
    "ai_invocation",
    "guardrail_blocked",
    "guardrail_warning",
    "hitl_review_required",
    "hitl_escalated",
    "hitl_auto_proceed",
    "agent_execution",
    "ai_prompt_injection",
    "ai_schema_rejected",
)


# =============================================================================
# METRICS MODELS
# =============================================================================

@dataclass
class InvocationMetrics:
    """
    Aggregated AI invocation metrics for a tenant over a time window.

    All numeric fields are computed from the audit ledger — not stored.
    The tenant_id field is NEVER included in API responses to prevent
    cross-tenant information leakage.
    """
    window_start: datetime
    window_end: datetime

    # Volume
    total_invocations: int = 0
    successful_invocations: int = 0
    failed_invocations: int = 0

    # Latency (ms) — derived from metadata.latency_ms in audit entries
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    # Failure rate (0.0 – 1.0)
    failure_rate: float = 0.0

    # Guardrails
    guardrail_blocks: int = 0
    guardrail_warnings: int = 0

    # HITL routing
    hitl_reviews: int = 0
    hitl_escalations: int = 0
    hitl_auto_proceeds: int = 0

    # Model usage breakdown  { model_name: count }
    model_usage: Dict[str, int] = field(default_factory=dict)

    # Prompt injection attempts
    injection_attempts: int = 0

    # Schema rejections
    schema_rejections: int = 0

    # Agent executions
    agent_executions: int = 0


@dataclass
class ModelMetrics:
    """Per-model usage breakdown."""
    model_name: str
    invocation_count: int
    avg_latency_ms: float
    failure_count: int


# =============================================================================
# OBSERVABILITY SERVICE
# =============================================================================

class AIObservabilityService:
    """
    Read-only metrics aggregation service for AI operations.

    Derives all metrics from the audit ledger — no separate metrics store.

    Usage:
        metrics = AIObservabilityService.get_metrics(
            tenant_id="org-123",
            window_hours=24,
        )
    """

    @classmethod
    def get_metrics(
        cls,
        tenant_id: str,
        window_hours: int = 24,
        module: Optional[str] = None,
    ) -> InvocationMetrics:
        """
        Aggregate AI metrics for a tenant over the specified time window.

        Args:
            tenant_id:    Tenant to scope metrics to
            window_hours: Look-back window in hours (default 24)
            module:       Optional module filter (M1, M2, …)

        Returns:
            InvocationMetrics — does NOT include tenant_id to prevent leakage
        """
        from server.db_service import execute_query

        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(hours=window_hours)

        # Build the query — fetch all AI-related audit rows for the window
        action_placeholders = ", ".join(["%s"] * len(_AI_ACTIONS))
        params: list = [tenant_id, window_start, window_end, *_AI_ACTIONS]

        module_clause = ""
        if module:
            module_clause = "AND module = %s"
            params.append(module)

        sql = f"""
            SELECT
                action,
                success,
                metadata,
                timestamp
            FROM audit_ledger
            WHERE tenant_id = %s
              AND timestamp >= %s
              AND timestamp <= %s
              AND action IN ({action_placeholders})
              {module_clause}
            ORDER BY timestamp ASC
        """

        try:
            rows = execute_query(sql, tuple(params))
        except Exception as e:
            logger.error("E03-S10: Failed to query audit ledger for metrics: %s", e)
            rows = []

        return cls._aggregate(rows, window_start, window_end)

    @classmethod
    def get_model_breakdown(
        cls,
        tenant_id: str,
        window_hours: int = 24,
    ) -> List[ModelMetrics]:
        """
        Return per-model invocation breakdown for a tenant.

        Args:
            tenant_id:    Tenant to scope metrics to
            window_hours: Look-back window in hours

        Returns:
            List of ModelMetrics, sorted by invocation count descending
        """
        metrics = cls.get_metrics(tenant_id=tenant_id, window_hours=window_hours)

        result = []
        for model_name, count in metrics.model_usage.items():
            result.append(ModelMetrics(
                model_name=model_name,
                invocation_count=count,
                avg_latency_ms=metrics.avg_latency_ms,  # approximation
                failure_count=0,  # per-model failures require richer data
            ))

        return sorted(result, key=lambda m: m.invocation_count, reverse=True)

    # -------------------------------------------------------------------------
    # Private aggregation
    # -------------------------------------------------------------------------

    @classmethod
    def _aggregate(
        cls,
        rows: List[Dict[str, Any]],
        window_start: datetime,
        window_end: datetime,
    ) -> InvocationMetrics:
        """Compute InvocationMetrics from raw audit rows."""
        metrics = InvocationMetrics(
            window_start=window_start,
            window_end=window_end,
        )

        latencies: List[float] = []

        for row in rows:
            action = row.get("action", "")
            success = row.get("success", True)
            meta: Dict[str, Any] = row.get("metadata") or {}

            if action == "ai_invocation":
                metrics.total_invocations += 1
                if success:
                    metrics.successful_invocations += 1
                else:
                    metrics.failed_invocations += 1

                latency = _safe_float(meta.get("latency_ms"))
                if latency is not None:
                    latencies.append(latency)

                model = meta.get("model")
                if model:
                    metrics.model_usage[model] = (
                        metrics.model_usage.get(model, 0) + 1
                    )

            elif action == "guardrail_blocked":
                metrics.guardrail_blocks += 1

            elif action == "guardrail_warning":
                metrics.guardrail_warnings += 1

            elif action == "hitl_review_required":
                metrics.hitl_reviews += 1

            elif action == "hitl_escalated":
                metrics.hitl_escalations += 1

            elif action == "hitl_auto_proceed":
                metrics.hitl_auto_proceeds += 1

            elif action == "ai_prompt_injection":
                metrics.injection_attempts += 1

            elif action == "ai_schema_rejected":
                metrics.schema_rejections += 1

            elif action == "agent_execution":
                metrics.agent_executions += 1

        # Derived aggregates
        if metrics.total_invocations > 0:
            metrics.failure_rate = (
                metrics.failed_invocations / metrics.total_invocations
            )

        if latencies:
            metrics.avg_latency_ms = sum(latencies) / len(latencies)
            metrics.max_latency_ms = max(latencies)
            metrics.p95_latency_ms = _percentile(latencies, 95)

        return metrics


# =============================================================================
# HELPERS
# =============================================================================

def _safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: List[float], pct: int) -> float:
    """Compute the Nth percentile of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * pct / 100) - 1)
    return sorted_vals[idx]
