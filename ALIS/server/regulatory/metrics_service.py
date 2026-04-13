"""Regulatory Metrics Service — upsert and query the regulatory_metrics table

This is the only write path into regulatory_metrics.
All upserts go through RegulatoryMetricsService.record() — never direct SQL.

CRITICAL: This module must NEVER call or import from any other business module.
It only reads from and writes to regulatory_metrics.
Cross-module data flows via domain events → event_handlers → record().
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class RegulatoryMetricsService:
    @staticmethod
    def record(
        org_id: str,
        metric_key: str,
        metric_value: float | None,
        framework: str = "NAAC",
        breakdown: dict[str, Any] | None = None,
        metric_date: date | None = None,
        source_event: str | None = None,
        source_event_id: str | None = None,
    ) -> None:
        """Upsert a single metric value for today (or metric_date).

        Uses INSERT … ON CONFLICT DO UPDATE so it is safe to call
        idempotently from re-run Celery event handlers.
        """
        import json

        target_date = metric_date or date.today()
        breakdown_json = json.dumps(breakdown or {})

        execute_transaction(
            AuditLog.log(
                action=AuditAction.CREATE,
                actor_id="system",
                actor_role="system",
                entity_type="metric",
                entity_id="",
                tenant_id="",
                metadata={"source": "record"},
            )[
                (
                    """
                    INSERT INTO regulatory_metrics
                        (id, org_id, metric_key, framework, metric_value,
                         breakdown, metric_date, source_event, source_event_id, updated_at)
                    VALUES
                        (uuid_generate_v4(), %s, %s, %s, %s,
                         %s, %s, %s, %s, NOW())
                    ON CONFLICT (org_id, metric_key, metric_date) DO UPDATE
                        SET metric_value   = EXCLUDED.metric_value,
                            breakdown      = EXCLUDED.breakdown,
                            source_event   = EXCLUDED.source_event,
                            source_event_id = EXCLUDED.source_event_id,
                            updated_at     = NOW()
                    """,
                    (
                        org_id,
                        metric_key,
                        framework,
                        metric_value,
                        breakdown_json,
                        target_date,
                        source_event,
                        source_event_id,
                    ),
                )
            ],
            tenant_id=org_id,
        )

    @staticmethod
    def increment(
        org_id: str,
        metric_key: str,
        delta: float = 1.0,
        framework: str = "NAAC",
        metric_date: date | None = None,
        source_event: str | None = None,
        source_event_id: str | None = None,
    ) -> None:
        """Atomically increment a counter metric.

        If no row exists yet, inserts with metric_value = delta.
        """
        target_date = metric_date or date.today()

        execute_transaction(
            [
                (
                    """
                    INSERT INTO regulatory_metrics
                        (id, org_id, metric_key, framework, metric_value,
                         metric_date, source_event, source_event_id, updated_at)
                    VALUES
                        (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (org_id, metric_key, metric_date) DO UPDATE
                        SET metric_value   = regulatory_metrics.metric_value + %s,
                            source_event   = EXCLUDED.source_event,
                            source_event_id = EXCLUDED.source_event_id,
                            updated_at     = NOW()
                    """,
                    (
                        org_id,
                        metric_key,
                        framework,
                        delta,
                        target_date,
                        source_event,
                        source_event_id,
                        delta,  # second use: the increment delta in DO UPDATE
                    ),
                )
            ],
            tenant_id=org_id,
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="metric",
            entity_id="",
            tenant_id="",
            metadata={"source": "increment"},
        )

    @staticmethod
    def get_metric(
        org_id: str,
        metric_key: str,
        metric_date: date | None = None,
    ) -> dict[str, Any] | None:
        """Return the metric row for a specific date (defaults to today)."""
        target_date = metric_date or date.today()
        rows = execute_query(
            """
            SELECT metric_key, framework, metric_value, breakdown, metric_date, updated_at
            FROM regulatory_metrics
            WHERE org_id = %s AND metric_key = %s AND metric_date = %s
            """,
            (org_id, metric_key, target_date),
            tenant_id=org_id,
        )
        return dict(rows[0]) if rows else None

    @staticmethod
    def get_latest(
        org_id: str,
        framework: str = "NAAC",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return the most recent value for each metric under a framework."""
        rows = execute_query(
            """
            SELECT DISTINCT ON (metric_key)
                metric_key, framework, metric_value, breakdown, metric_date, updated_at
            FROM regulatory_metrics
            WHERE org_id = %s AND framework = %s
            ORDER BY metric_key, metric_date DESC
            LIMIT %s
            """,
            (org_id, framework, limit),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @staticmethod
    def get_trend(
        org_id: str,
        metric_key: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return daily values for a metric over the past N days."""
        rows = execute_query(
            """
            SELECT metric_key, metric_value, breakdown, metric_date
            FROM regulatory_metrics
            WHERE org_id = %s
              AND metric_key = %s
              AND metric_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY metric_date ASC
            """,
            (org_id, metric_key, days),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]
