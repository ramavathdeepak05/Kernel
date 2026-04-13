"""Shadow Mode Divergence Tracker — Nightly Celery Beat Task (§28)

Runs nightly at 02:00 (institution local time proxied as UTC+5:30 = 20:30 UTC).
For each org in shadow mode, compares ALIS computed attendance & fee totals
against the `staff_actuals` reference table populated by data-upload integrations,
then writes results to `shadow_mode_divergence_log` and evaluates the go-live gate.

Beat schedule entry (added in worker.py):
    "shadow-divergence-nightly": {
        "task": "server.tasks.shadow_divergence.run_shadow_divergence",
        "schedule": crontab(hour=20, minute=30),
    }
"""

from __future__ import annotations

import logging

from celery import shared_task
from server.core.shadow_mode import ShadowModeService
from server.db_service import execute_query

logger = logging.getLogger(__name__)


@shared_task(
    name="server.tasks.shadow_divergence.run_shadow_divergence",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def run_shadow_divergence(self):
    """Main entry point: runs divergence check for all shadow-mode orgs."""
    # Find all orgs currently in shadow mode
    orgs = execute_query(
        """
        SELECT DISTINCT org_id
        FROM tenant_feature_flags
        WHERE flag_key = 'shadow_mode.config'
          AND flag_value::jsonb->>'enabled' = 'true'
    """,
        (),
    )

    for row in orgs:
        org_id = row["org_id"]
        try:
            _check_org(org_id)
        except Exception as exc:
            logger.error("Shadow divergence check failed for org %s: %s", org_id, exc)


def _check_org(org_id: str) -> None:
    """Compute and record divergence metrics for one organisation."""
    # -----------------------------------------------------------------------
    # Attendance divergence
    # -----------------------------------------------------------------------
    # ALIS computed: average attendance % across all active sessions today
    alis_attn_rows = execute_query(
        """
        SELECT COALESCE(AVG(
            CASE WHEN total_students > 0
                 THEN present_count::float / total_students * 100
                 ELSE NULL
            END
        ), 0) AS avg_pct
        FROM (
            SELECT
                session_id,
                COUNT(*) FILTER (WHERE status = 'PRESENT') AS present_count,
                COUNT(*) FILTER (WHERE status NOT IN ('EXCUSED_DISRUPTION','EXCUSED_LATE_JOINER')) AS total_students
            FROM attendance_records
            WHERE org_id = %s
              AND marked_at >= CURRENT_DATE
            GROUP BY session_id
        ) s
    """,
        (org_id,),
    )

    alis_attn = float(alis_attn_rows[0]["avg_pct"] or 0) if alis_attn_rows else 0.0

    # Actual: from staff_actuals reference (uploaded by institution staff)
    actual_attn_rows = execute_query(
        """
        SELECT COALESCE(AVG(actual_value), 0) AS avg_pct
        FROM staff_actuals
        WHERE org_id = %s
          AND metric = 'attendance_pct'
          AND recorded_date = CURRENT_DATE
    """,
        (org_id,),
    )

    actual_attn = (
        float(actual_attn_rows[0]["avg_pct"] or 0) if actual_attn_rows else None
    )

    if actual_attn is not None:
        ShadowModeService.record_divergence(
            org_id=org_id,
            metric="attendance",
            alis_value=alis_attn,
            actual_value=actual_attn,
        )
        logger.info(
            "Org %s attendance: ALIS=%.2f%% actual=%.2f%%",
            org_id,
            alis_attn,
            actual_attn,
        )
    else:
        logger.debug("No actual attendance data for org %s today — skipping", org_id)

    # -----------------------------------------------------------------------
    # Fee collection divergence
    # -----------------------------------------------------------------------
    alis_fee_rows = execute_query(
        """
        SELECT COALESCE(SUM(amount_paid), 0) AS total_collected
        FROM student_invoices
        WHERE org_id = %s
          AND updated_at >= CURRENT_DATE
    """,
        (org_id,),
    )

    alis_fee = float(alis_fee_rows[0]["total_collected"] or 0) if alis_fee_rows else 0.0

    actual_fee_rows = execute_query(
        """
        SELECT COALESCE(SUM(actual_value), 0) AS total_collected
        FROM staff_actuals
        WHERE org_id = %s
          AND metric = 'fee_collected_inr'
          AND recorded_date = CURRENT_DATE
    """,
        (org_id,),
    )

    actual_fee = (
        float(actual_fee_rows[0]["total_collected"] or 0) if actual_fee_rows else None
    )

    if actual_fee is not None:
        ShadowModeService.record_divergence(
            org_id=org_id,
            metric="fee",
            alis_value=alis_fee,
            actual_value=actual_fee,
        )
        logger.info(
            "Org %s fee: ALIS=%.2f actual=%.2f",
            org_id,
            alis_fee,
            actual_fee,
        )
    else:
        logger.debug("No actual fee data for org %s today — skipping", org_id)

    # -----------------------------------------------------------------------
    # Evaluate go-live gate after recording
    # -----------------------------------------------------------------------
    result = ShadowModeService.check_go_live_gate(org_id)
    logger.info(
        "Org %s go-live gate: can_go_live=%s consecutive=%d/%d",
        org_id,
        result.can_go_live,
        result.consecutive_days_passing,
        result.required_days,
    )

    if result.can_go_live:
        logger.warning("ORG %s IS READY FOR GO-LIVE — notify SUPER_ADMIN", org_id)
        # Emit domain event — notification service picks this up
        from server.core.domain_events import DomainEvent, DomainEventBus

        DomainEventBus.publish(
            DomainEvent(
                event_type="shadow_mode.go_live_gate_passed",
                org_id=org_id,
                payload={
                    "consecutive_days_passing": result.consecutive_days_passing,
                    "required_days": result.required_days,
                },
            )
        )
