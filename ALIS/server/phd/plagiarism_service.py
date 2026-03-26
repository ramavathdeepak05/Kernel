"""E15 — PhD Plagiarism Check Service

Drillbit API integration (drillbit.in — India's academic plagiarism checker).
Threshold from policy_engine (R1).
Domain event on pass/fail.

Flow:
  1. submit_check() — inserts PENDING record, POSTs file to Drillbit if enabled,
     stores drillbit_submission_id for polling.
  2. poll_result()  — called by Celery beat every 5 minutes; GETs status from
     Drillbit and calls record_result() when COMPLETE.
  3. record_result() — writes similarity_pct + PASSED/FAILED, fires domain event.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional
from uuid import uuid4

import httpx
from minio import Minio
from minio.error import S3Error

from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import NotFoundError
from server.core.policy_engine import policy_engine
from server.core.settings import settings
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _minio_client() -> Minio:
    """Return a configured MinIO client."""
    endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
    secure = settings.minio_endpoint.startswith("https://")
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def _fetch_file_bytes(document_url: str) -> tuple[bytes, str]:
    """Fetch file bytes from MinIO.

    ``document_url`` is stored as the MinIO object key (path) in
    ``phd_plagiarism_reports.document_url``.  Falls back to an HTTP GET for
    pre-signed or external URLs.

    Returns ``(file_bytes, filename)``.
    """
    # If it looks like a MinIO object key (no scheme), fetch directly.
    if not document_url.startswith("http://") and not document_url.startswith("https://"):
        try:
            client = _minio_client()
            response = client.get_object(settings.minio_bucket, document_url)
            file_bytes = response.read()
            filename = os.path.basename(document_url)
            return file_bytes, filename
        except S3Error as exc:
            logger.warning("MinIO fetch failed for %s: %s — trying HTTP", document_url, exc)

    # Fall back: treat as a pre-signed URL or public URL.
    with httpx.Client(timeout=settings.drillbit_timeout_seconds) as client:
        resp = client.get(document_url)
        resp.raise_for_status()
        filename = document_url.rstrip("/").split("/")[-1] or "thesis.pdf"
        return resp.content, filename


def _drillbit_headers() -> dict:
    return {"Authorization": f"Bearer {settings.drillbit_api_key}"}


def _publish_event(event: DomainEvent) -> None:
    """Fire-and-forget domain event (works inside sync Celery tasks too)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(DomainEventBus.publish(event))
        else:
            loop.run_until_complete(DomainEventBus.publish(event))
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PlagiarismService:

    @classmethod
    def submit_check(
        cls,
        phd_id: str,
        org_id: str,
        document_url: str,
        actor_id: str,
    ) -> dict:
        """Insert a PENDING plagiarism report and, if Drillbit is enabled,
        submit the thesis file to the Drillbit API.

        The returned dict always contains the DB record.  When Drillbit is
        enabled, ``drillbit_submission_id`` is populated; the Celery polling
        task will later call ``poll_result()`` to fetch the score.
        """
        threshold = policy_engine.get_value(
            "phd.plagiarism_max_pct", org_id, default=25
        )

        report_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        drillbit_submission_id: Optional[str] = None

        # ------------------------------------------------------------------
        # Attempt Drillbit submission when the integration is enabled
        # ------------------------------------------------------------------
        if settings.drillbit_enabled:
            try:
                file_bytes, filename = _fetch_file_bytes(document_url)

                # Resolve author name from phd_registrations → users join
                author_rows = execute_query(
                    """
                    SELECT u.full_name
                    FROM phd_registrations pr
                    JOIN users u ON u.id = pr.student_id
                    WHERE pr.id = %s AND pr.org_id = %s
                    LIMIT 1
                    """,
                    (phd_id, org_id),
                )
                author = author_rows[0]["full_name"] if author_rows else "Unknown Author"

                content_type = (
                    "application/pdf"
                    if filename.lower().endswith(".pdf")
                    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

                with httpx.Client(timeout=settings.drillbit_timeout_seconds) as http:
                    resp = http.post(
                        f"{settings.drillbit_base_url}/submissions",
                        headers=_drillbit_headers(),
                        files={"file": (filename, BytesIO(file_bytes), content_type)},
                        data={
                            "title": f"PhD Thesis — {phd_id}",
                            "author": author,
                            "exclude_quotes": "true",
                            "exclude_bibliography": "true",
                        },
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    drillbit_submission_id = payload.get("submission_id")
                    logger.info(
                        "Drillbit submission accepted: submission_id=%s, phd_id=%s, estimated_minutes=%s",
                        drillbit_submission_id,
                        phd_id,
                        payload.get("estimated_minutes"),
                    )
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Drillbit API HTTP error for phd_id=%s: %s %s",
                    phd_id, exc.response.status_code, exc.response.text,
                )
            except httpx.RequestError as exc:
                logger.error(
                    "Drillbit API request error for phd_id=%s: %s", phd_id, exc
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unexpected error submitting to Drillbit for phd_id=%s: %s", phd_id, exc
                )
        else:
            logger.warning(
                "Drillbit integration disabled (DRILLBIT_API_KEY not set). "
                "Report %s will remain PENDING until integration is configured.",
                report_id,
            )

        # ------------------------------------------------------------------
        # Persist the PENDING report (with or without submission_id)
        # ------------------------------------------------------------------
        execute_transaction([(
            """
            INSERT INTO phd_plagiarism_reports
                (id, phd_id, org_id, document_url, status,
                 threshold_pct, provider, submitted_by, created_at,
                 drillbit_submission_id)
            VALUES (%s, %s, %s, %s, 'PENDING', %s, 'DRILLBIT', %s, %s, %s)
            """,
            (
                report_id, phd_id, org_id, document_url,
                threshold, actor_id, now, drillbit_submission_id,
            ),
        )])

        # Fire domain event
        event = DomainEvent(
            event_type="phd.plagiarism_check_submitted",
            org_id=org_id,
            payload={
                "report_id": report_id,
                "phd_id": phd_id,
                "document_url": document_url,
                "threshold_pct": threshold,
                "drillbit_enabled": settings.drillbit_enabled,
                "drillbit_submission_id": drillbit_submission_id,
            },
            entity_type="phd_plagiarism_report",
            entity_id=report_id,
        )
        _publish_event(event)

        result = execute_query(
            "SELECT * FROM phd_plagiarism_reports WHERE id = %s AND org_id = %s",
            (report_id, org_id),
        )
        return dict(result[0]) if result else {}

    @classmethod
    def poll_result(
        cls,
        drillbit_submission_id: str,
        org_id: str,
    ) -> dict:
        """Poll Drillbit for the status of a previously submitted report.

        Called by the Celery beat task ``poll_drillbit_results`` every 5 minutes.

        Returns a dict with at minimum ``{"status": "<DRILLBIT_STATUS>"}`` so the
        caller can log progress.  When Drillbit returns COMPLETE, ``record_result``
        is called and the full DB row is returned.
        """
        if not settings.drillbit_enabled:
            logger.warning("poll_result called but Drillbit integration is disabled.")
            return {"status": "DISABLED"}

        # Look up the local report by submission_id so we have report_id + phd_id.
        rows = execute_query(
            """
            SELECT id, phd_id, org_id, status
            FROM phd_plagiarism_reports
            WHERE drillbit_submission_id = %s AND org_id = %s
            LIMIT 1
            """,
            (drillbit_submission_id, org_id),
        )
        if not rows:
            logger.warning(
                "poll_result: no local report found for drillbit_submission_id=%s org_id=%s",
                drillbit_submission_id, org_id,
            )
            return {"status": "NOT_FOUND"}

        local_report = rows[0]
        report_id = local_report["id"]

        # Do NOT re-poll already completed/failed reports.
        if local_report["status"] not in ("PENDING",):
            return {"status": local_report["status"]}

        try:
            with httpx.Client(timeout=settings.drillbit_timeout_seconds) as http:
                resp = http.get(
                    f"{settings.drillbit_base_url}/submissions/{drillbit_submission_id}",
                    headers=_drillbit_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Drillbit poll HTTP error for submission_id=%s: %s %s",
                drillbit_submission_id, exc.response.status_code, exc.response.text,
            )
            return {"status": "POLL_ERROR", "detail": str(exc)}
        except httpx.RequestError as exc:
            logger.error(
                "Drillbit poll request error for submission_id=%s: %s",
                drillbit_submission_id, exc,
            )
            return {"status": "POLL_ERROR", "detail": str(exc)}

        drillbit_status = data.get("status", "UNKNOWN")
        logger.info(
            "Drillbit poll: submission_id=%s status=%s",
            drillbit_submission_id, drillbit_status,
        )

        if drillbit_status != "COMPLETE":
            # Still queued or processing — nothing to record yet.
            return {"status": drillbit_status}

        # COMPLETE — extract scores and persist.
        similarity_score: float = float(data.get("similarity_score", 0.0))
        report_url: Optional[str] = data.get("report_url")
        details: Optional[dict] = data.get("details")

        # Persist the extra fields (report_url, similarity_details) before
        # calling record_result so they are available in the final row.
        if report_url or details:
            import json
            execute_transaction([(
                """
                UPDATE phd_plagiarism_reports
                SET report_url = %s,
                    similarity_details = %s
                WHERE id = %s AND org_id = %s
                """,
                (report_url, json.dumps(details) if details else None, report_id, org_id),
            )])

        # Delegate status/event logic to record_result (single source of truth).
        # Use a system actor UUID (zeros) since this is an automated task.
        system_actor = "00000000-0000-0000-0000-000000000000"
        return cls.record_result(
            report_id=report_id,
            org_id=org_id,
            similarity_pct=similarity_score,
            actor_id=system_actor,
        )

    @classmethod
    def record_result(
        cls,
        report_id: str,
        org_id: str,
        similarity_pct: float,
        actor_id: str,
    ) -> dict:
        rows = execute_query(
            "SELECT * FROM phd_plagiarism_reports WHERE id = %s AND org_id = %s",
            (report_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Plagiarism report {report_id} not found")
        report = rows[0]
        phd_id = report["phd_id"]

        # Re-read threshold from policy (R1 — always use current policy value)
        threshold = policy_engine.get_value(
            "phd.plagiarism_max_pct", org_id, default=25
        )
        # Capture policy version for R12
        policy_version_id = (
            policy_engine.get_version_id("phd.plagiarism_max_pct", org_id)
            if hasattr(policy_engine, "get_version_id")
            else None
        )

        status = "PASSED" if similarity_pct <= threshold else "FAILED"
        now = datetime.now(timezone.utc).isoformat()

        execute_transaction([(
            """
            UPDATE phd_plagiarism_reports
            SET similarity_pct = %s,
                status = %s,
                checked_at = %s,
                policy_version_id = %s,
                threshold_pct = %s,
                checked_by = %s
            WHERE id = %s AND org_id = %s
            """,
            (
                similarity_pct, status, now, policy_version_id,
                threshold, actor_id, report_id, org_id,
            ),
        )])

        # Fire pass/fail event
        event_type = (
            "phd.plagiarism_passed" if status == "PASSED" else "phd.plagiarism_failed"
        )
        payload = {
            "phd_id": phd_id,
            "report_id": report_id,
            "similarity_pct": similarity_pct,
            "threshold_pct": threshold,
        }
        event = DomainEvent(
            event_type=event_type,
            org_id=org_id,
            payload=payload,
            entity_type="phd_plagiarism_report",
            entity_id=report_id,
        )
        _publish_event(event)

        updated = execute_query(
            "SELECT * FROM phd_plagiarism_reports WHERE id = %s AND org_id = %s",
            (report_id, org_id),
        )
        return dict(updated[0]) if updated else {}

    @classmethod
    def get_latest_report(
        cls,
        phd_id: str,
        org_id: str,
    ) -> Optional[dict]:
        rows = execute_query(
            """
            SELECT * FROM phd_plagiarism_reports
            WHERE phd_id = %s AND org_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phd_id, org_id),
        )
        return dict(rows[0]) if rows else None
