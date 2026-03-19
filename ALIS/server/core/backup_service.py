"""Backup + Disaster Recovery Orchestration (§32)

Orchestrates pg_dump, MinIO backup verification, and alerting.
Fires platform.backup_failed domain event on failure.
Beat schedule: daily at 03:00 UTC (add to worker.py separately).
"""

import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class BackupService:
    """Orchestrates pg_dump backups, MinIO upload, and verification."""

    def run_daily_backup(self, org_id_for_alert: str = "") -> dict:
        """Run pg_dump, upload to MinIO, and record in backup_log.

        Returns a dict with status, filename, and uploaded flag.
        Fires platform.backup_failed domain event on pg_dump failure.
        """
        db_url = os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/alis"
        )

        # Parse connection URL
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip("/")
        db_host = parsed.hostname or "localhost"
        db_port = str(parsed.port or 5432)
        db_user = parsed.username or "postgres"
        db_password = parsed.password or ""

        now_utc = datetime.now(timezone.utc)
        dump_filename = f"alis_backup_{now_utc.strftime('%Y%m%d_%H%M%S')}.sql.gz"
        dump_path = f"/tmp/{dump_filename}"

        cmd = [
            "pg_dump",
            "--no-password",
            "--format=custom",
            "--compress=9",
            f"--file={dump_path}",
            db_name,
        ]
        env = {
            **os.environ,
            "PGPASSWORD": db_password,
            "PGHOST": db_host,
            "PGPORT": db_port,
            "PGUSER": db_user,
        }

        started_at = datetime.now(timezone.utc)

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=3600
        )

        if result.returncode != 0:
            logger.error(
                "pg_dump failed (rc=%s): %s", result.returncode, result.stderr[:500]
            )
            event = DomainEvent(
                event_type="platform.backup_failed",
                org_id=org_id_for_alert or "",
                payload={
                    "filename": dump_filename,
                    "error": result.stderr[:500],
                    "timestamp": now_utc.isoformat(),
                },
            )
            DomainEventBus.publish(event)
            return {"status": "FAILED", "error": result.stderr[:500]}

        # Upload to MinIO
        uploaded = False
        try:
            from server.fs_service import upload_backup  # noqa: PLC0415

            upload_backup(dump_path, dump_filename)
            uploaded = True
        except Exception as e:
            logger.warning("MinIO upload failed: %s", e)
            uploaded = False

        # Determine file size (best-effort)
        try:
            size_bytes = os.path.getsize(dump_path)
        except OSError:
            size_bytes = 0

        # Record in backup_log (table may not exist yet — swallow gracefully)
        record_id = str(uuid.uuid4())
        try:
            execute_transaction(
                [
                    (
                        """
                        INSERT INTO backup_log
                            (id, filename, size_bytes, started_at, completed_at, status, uploaded_to_minio)
                        VALUES (%s, %s, %s, %s, NOW(), 'SUCCESS', %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            record_id,
                            dump_filename,
                            size_bytes,
                            started_at,
                            uploaded,
                        ),
                    )
                ]
            )
        except Exception as e:
            logger.warning("Could not record backup in backup_log: %s", e)

        logger.info("Backup complete: %s (uploaded=%s)", dump_filename, uploaded)
        return {
            "status": "SUCCESS",
            "filename": dump_filename,
            "uploaded": uploaded,
        }

    def verify_latest_backup(self, org_id: str) -> dict:
        """Check that a recent successful backup exists.

        Fires platform.backup_stale if no backup within 25 hours.
        Returns last_backup timestamp, filename, and hours_ago.
        """
        rows = execute_query(
            """
            SELECT filename, completed_at, status
            FROM backup_log
            WHERE status = 'SUCCESS'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (),
        )

        now_utc = datetime.now(timezone.utc)

        if not rows:
            logger.warning("No successful backup found in backup_log.")
            event = DomainEvent(
                event_type="platform.backup_stale",
                org_id=org_id,
                payload={"reason": "no_backup_record", "timestamp": now_utc.isoformat()},
            )
            DomainEventBus.publish(event)
            return {"last_backup": None, "filename": None, "hours_ago": None}

        row = rows[0]
        filename = row["filename"]
        completed_at = row["completed_at"]

        # completed_at may be a datetime or a string depending on the DB adapter
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        # Ensure timezone-aware for arithmetic
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)

        hours_ago = (now_utc - completed_at).total_seconds() / 3600

        if hours_ago > 25:
            logger.warning(
                "Last backup is %.1f hours old — firing backup_stale event.", hours_ago
            )
            event = DomainEvent(
                event_type="platform.backup_stale",
                org_id=org_id,
                payload={
                    "filename": filename,
                    "hours_ago": round(hours_ago, 2),
                    "timestamp": now_utc.isoformat(),
                },
            )
            DomainEventBus.publish(event)

        return {
            "last_backup": completed_at.isoformat(),
            "filename": filename,
            "hours_ago": round(hours_ago, 2),
        }
