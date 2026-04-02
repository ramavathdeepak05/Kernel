"""
Usage Store — S4

Writes usage events emitted by the data plane and AI service to the
`cp_usage_events` table, and aggregates them into period summaries.

All quantities are decimal-safe (stored as NUMERIC in Postgres).

Usage events are immutable once written — never updated, only appended.
Aggregation queries sum over the period on the fly (no pre-aggregation table
needed at current scale; add materialised view at 10M+ events/month).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Optional

from control_plane.billing_models import UsageEventType, UsageSummary

logger = logging.getLogger(__name__)


class UsageStore:
    """
    Records and aggregates tenant usage events.

    Uses the control plane DB (cp_usage_events table).
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        tenant_id: str,
        event_type: UsageEventType,
        quantity: Decimal,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Append a usage event. Returns the new row ID.

        Callers must supply validated inputs; no quota checks here —
        the BillingEngine applies quotas at invoice-time.
        """
        import json
        from control_plane import db

        db.execute(
            """
            INSERT INTO cp_usage_events (tenant_id, event_type, quantity, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (tenant_id, event_type.value, str(quantity), json.dumps(metadata or {})),
        )
        # RETURNING is consumed by execute(); use lastval for the ID
        rows = db.query("SELECT lastval() AS id")
        return rows[0]["id"] if rows else -1

    # ------------------------------------------------------------------
    # Read — period aggregation
    # ------------------------------------------------------------------

    def get_summary(self, tenant_id: str, period: str) -> UsageSummary:
        """
        Return aggregated usage for `tenant_id` in `period` ("YYYY-MM").

        - ai_tokens: SUM of all ai_tokens events
        - api_calls: SUM of all api_calls events
        - storage_gb: MAX snapshot (we bill peak storage, not average)
        - active_users: MAX snapshot (we bill peak MAU in the month)
        """
        from control_plane import db

        year, month = period.split("-")
        period_start = f"{year}-{month}-01"
        # Postgres: first day of next month
        period_end_expr = "DATE_TRUNC('month', %s::date) + INTERVAL '1 month'"

        rows = db.query(
            f"""
            SELECT
                event_type,
                SUM(quantity::numeric)  AS total,
                MAX(quantity::numeric)  AS peak
            FROM cp_usage_events
            WHERE tenant_id = %s
              AND recorded_at >= %s::date
              AND recorded_at <  {period_end_expr}
            GROUP BY event_type
            """,
            (tenant_id, period_start, period_start),
        )

        summary = UsageSummary(tenant_id=tenant_id, period=period)
        for row in rows:
            et = row["event_type"]
            if et == UsageEventType.AI_TOKENS.value:
                summary.ai_tokens = int(row["total"] or 0)
            elif et == UsageEventType.API_CALLS.value:
                summary.api_calls = int(row["total"] or 0)
            elif et == UsageEventType.STORAGE_GB.value:
                summary.storage_gb = Decimal(str(row["peak"] or "0"))
            elif et == UsageEventType.ACTIVE_USERS.value:
                summary.active_users = int(row["peak"] or 0)
        return summary

    def list_events(
        self,
        tenant_id: str,
        period: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list:
        """Return raw usage event rows for auditing / debugging."""
        from control_plane import db

        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]

        if period:
            year, month = period.split("-")
            period_start = f"{year}-{month}-01"
            conditions.append("recorded_at >= %s::date")
            conditions.append(
                "recorded_at < DATE_TRUNC('month', %s::date) + INTERVAL '1 month'"
            )
            params += [period_start, period_start]

        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)

        where = " AND ".join(conditions)
        params += [limit, offset]

        return db.query(
            f"""
            SELECT id, tenant_id, event_type, quantity, metadata, recorded_at
            FROM cp_usage_events
            WHERE {where}
            ORDER BY recorded_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
