"""
ALIS Partition Management Tasks

Celery Beat tasks for maintaining partitioned tables:
  1. Create future partitions before they're needed
  2. Drop expired domain_events partitions (> 30 days)
  3. Detach old audit_ledger partitions (> 2 years) for archival
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from server.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="server.tasks.partition_mgmt.create_future_partitions", queue="default"
)
def create_future_partitions() -> dict:
    """
    Create future partitions for audit_ledger (monthly) and domain_events (weekly).

    Runs weekly via Beat. Ensures partitions exist for the next period so
    INSERTs never fail due to missing partition.

    audit_ledger: creates next 3 months
    domain_events: creates next 4 weeks
    """
    from server.db_service import execute_system_query, execute_system_transaction

    created = []

    # --- audit_ledger: next 3 months ---
    now = datetime.utcnow()
    for offset in range(1, 4):
        m = now.month + offset
        y = now.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        nm = m + 1
        ny = y
        if nm > 12:
            nm = 1
            ny = y + 1

        part_name = f"audit_ledger_y{y}m{m:02d}"
        from_date = f"{y}-{m:02d}-01"
        to_date = f"{ny}-{nm:02d}-01"

        # Check if partition already exists
        existing = execute_system_query(
            "SELECT 1 FROM pg_class WHERE relname = %s",
            (part_name,),
        )
        if not existing:
            try:
                execute_system_transaction(
                    [
                        (
                            f"CREATE TABLE IF NOT EXISTS {part_name} "
                            f"PARTITION OF audit_ledger "
                            f"FOR VALUES FROM ('{from_date}') TO ('{to_date}')",
                            None,
                        )
                    ]
                )
                created.append(part_name)
                logger.info("Created partition: %s", part_name)
            except Exception as e:
                logger.warning("Failed to create partition %s: %s", part_name, e)

    # --- domain_events: next 4 weeks ---
    today = now.date()
    # Find next Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    for i in range(4):
        week_start = next_monday + timedelta(weeks=i)
        week_end = week_start + timedelta(weeks=1)
        iso = week_start.isocalendar()
        part_name = f"domain_events_w{iso[0]}w{iso[1]:02d}"

        existing = execute_system_query(
            "SELECT 1 FROM pg_class WHERE relname = %s",
            (part_name,),
        )
        if not existing:
            try:
                execute_system_transaction(
                    [
                        (
                            f"CREATE TABLE IF NOT EXISTS {part_name} "
                            f"PARTITION OF domain_events "
                            f"FOR VALUES FROM ('{week_start.isoformat()}') TO ('{week_end.isoformat()}')",
                            None,
                        )
                    ]
                )
                created.append(part_name)
                logger.info("Created partition: %s", part_name)
            except Exception as e:
                logger.warning("Failed to create partition %s: %s", part_name, e)

    return {"created": created}


@celery_app.task(
    name="server.tasks.partition_mgmt.drop_expired_event_partitions", queue="default"
)
def drop_expired_event_partitions(retention_days: int = 30) -> dict:
    """
    Drop domain_events partitions older than retention_days.

    Events are short-lived — once processed, the state is materialized
    in the target tables. Old event records are safe to delete.

    Runs weekly via Beat.
    """
    from server.db_service import execute_system_query, execute_system_transaction

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    dropped = []

    # Find all domain_events child partitions
    partitions = execute_system_query(
        """
        SELECT c.relname AS partition_name,
               pg_get_expr(c.relpartbound, c.oid) AS bounds
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'domain_events'
          AND c.relkind = 'r'
        ORDER BY c.relname
        """,
        None,
    )

    for part in partitions:
        part_name = part["partition_name"]
        bounds = part.get("bounds", "")
        # Parse upper bound from bounds string: FOR VALUES FROM ('2026-01-06') TO ('2026-01-13')
        try:
            # Extract the TO date
            to_idx = bounds.index("TO ('") + 5
            to_end = bounds.index("')", to_idx)
            to_date_str = bounds[to_idx:to_end]
            to_date = datetime.fromisoformat(to_date_str)

            if to_date < cutoff:
                execute_system_transaction(
                    [
                        (
                            f"DROP TABLE IF EXISTS {part_name}",
                            None,
                        )
                    ]
                )
                dropped.append(part_name)
                logger.info(
                    "Dropped expired partition: %s (upper bound: %s)",
                    part_name,
                    to_date_str,
                )
        except (ValueError, IndexError) as e:
            logger.debug("Could not parse bounds for %s: %s", part_name, e)

    return {"dropped": dropped}


@celery_app.task(
    name="server.tasks.partition_mgmt.detach_old_audit_partitions", queue="default"
)
def detach_old_audit_partitions(retention_years: int = 2) -> dict:
    """
    Detach audit_ledger partitions older than retention_years.

    Detached partitions remain as standalone tables and can be:
      - Exported to S3/MinIO cold storage via pg_dump
      - Dropped after export confirmation

    Does NOT drop the partition — only detaches from the partitioned table.
    A separate backup step should export before manual DROP.

    Runs monthly via Beat.
    """
    from server.db_service import execute_system_query, execute_system_transaction

    cutoff = datetime.utcnow() - timedelta(days=retention_years * 365)
    detached = []

    partitions = execute_system_query(
        """
        SELECT c.relname AS partition_name,
               pg_get_expr(c.relpartbound, c.oid) AS bounds
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'audit_ledger'
          AND c.relkind = 'r'
        ORDER BY c.relname
        """,
        None,
    )

    for part in partitions:
        part_name = part["partition_name"]
        bounds = part.get("bounds", "")
        try:
            to_idx = bounds.index("TO ('") + 5
            to_end = bounds.index("')", to_idx)
            to_date_str = bounds[to_idx:to_end]
            to_date = datetime.fromisoformat(to_date_str)

            if to_date < cutoff:
                execute_system_transaction(
                    [
                        (
                            f"ALTER TABLE audit_ledger DETACH PARTITION {part_name}",
                            None,
                        )
                    ]
                )
                detached.append(part_name)
                logger.info(
                    "Detached audit partition: %s (upper bound: %s). "
                    "Export to cold storage then DROP manually.",
                    part_name,
                    to_date_str,
                )
        except (ValueError, IndexError) as e:
            logger.debug("Could not parse bounds for %s: %s", part_name, e)

    return {"detached": detached}
