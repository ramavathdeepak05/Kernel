"""EC-SS-01 — Grievance Spike Anomaly Detector

Evaluates each new grievance submission to detect coordinated spikes.
All thresholds from policy_engine (R1 — no literals).

Policy keys
───────────
grievance.spike_window_hours         default 24
grievance.spike_multiplier           default 3.0  (current vs rolling avg)
grievance.spike_min_count            default 5    (minimum to trigger)
grievance.invigilator_blackout_hours default 48   (during exam window)

Anonymous complaints are capped at ROUTINE / SERIOUS (never CRITICAL).
Identical text within 30 min from different users → COORDINATED_COMPLAINT_FLAG.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class GrievanceAnomalyDetector:
    @classmethod
    def evaluate(
        cls,
        org_id: str,
        respondent_id: str,
        grievance_id: str,
        is_anonymous: bool,
        grievance_text: str,
        _submitter_id: str | None,
        severity: str,
    ) -> dict:
        """Evaluate a new grievance for anomaly conditions.

        Returns: {anomaly_detected, action, flags}
        """
        now = datetime.now(timezone.utc)
        flags = []

        # R1 — all thresholds from policy engine
        window_hours = int(
            policy_engine.get_value("grievance.spike_window_hours", org_id, 24)
        )
        spike_multiplier = float(
            policy_engine.get_value("grievance.spike_multiplier", org_id, 3.0)
        )
        spike_min_count = int(
            policy_engine.get_value("grievance.spike_min_count", org_id, 5)
        )
        invigilator_blackout_hours = int(
            policy_engine.get_value("grievance.invigilator_blackout_hours", org_id, 48)
        )

        # ---------------------------------------------------------------
        # 1. Anonymous severity cap
        # ---------------------------------------------------------------
        if is_anonymous and severity == "CRITICAL":
            execute_transaction(
                [
                    (
                        """
                UPDATE grievances SET severity = 'SERIOUS' WHERE id = %s AND org_id = %s
            """,
                        (grievance_id, org_id),
                    )
                ]
            )
            flags.append("ANONYMOUS_SEVERITY_CAPPED")
            severity = "SERIOUS"

        # ---------------------------------------------------------------
        # 2. Coordinated complaint detection
        # ---------------------------------------------------------------
        coord_window = now - timedelta(minutes=30)
        if grievance_text and len(grievance_text) > 20:
            duplicate_check = execute_query(
                """
                SELECT COUNT(*) AS cnt
                FROM grievances
                WHERE org_id = %s
                  AND respondent_id = %s
                  AND created_at >= %s
                  AND id != %s
                  AND similarity(description, %s) > 0.9
            """,
                (org_id, respondent_id, coord_window, grievance_id, grievance_text),
            )

            if duplicate_check and int(duplicate_check[0].get("cnt", 0)) >= 2:
                flags.append("COORDINATED_COMPLAINT_FLAG")

        # ---------------------------------------------------------------
        # 3. Invigilator complaint during exam blackout
        # ---------------------------------------------------------------
        blackout_start = now - timedelta(hours=invigilator_blackout_hours)
        exam_active = execute_query(
            """
            SELECT 1 FROM exam_schedules
            WHERE org_id = %s AND exam_date BETWEEN %s AND %s
            LIMIT 1
        """,
            (org_id, blackout_start, now + timedelta(hours=invigilator_blackout_hours)),
        )

        if exam_active and respondent_id:
            invigilator_check = execute_query(
                """
                SELECT 1 FROM exam_invigilators WHERE user_id = %s AND org_id = %s LIMIT 1
            """,
                (respondent_id, org_id),
            )
            if invigilator_check:
                flags.append("INVIGILATOR_EXAM_BLACKOUT")
                # Route to pending — will be reviewed after exam window
                execute_transaction(
                    [
                        (
                            """
                    UPDATE grievances
                    SET status = 'EXAM_BLACKOUT_HOLD', updated_at = NOW()
                    WHERE id = %s AND org_id = %s
                """,
                            (grievance_id, org_id),
                        )
                    ]
                )

                return {
                    "anomaly_detected": False,
                    "action": "EXAM_BLACKOUT_HOLD",
                    "flags": flags,
                }

        # ---------------------------------------------------------------
        # 4. Spike detection
        # ---------------------------------------------------------------
        window_start = now - timedelta(hours=window_hours)

        # Current window count
        current_rows = execute_query(
            """
            SELECT COUNT(*) AS cnt
            FROM grievances
            WHERE org_id = %s AND respondent_id = %s AND created_at >= %s
        """,
            (org_id, respondent_id, window_start),
        )
        current_count = int(current_rows[0]["cnt"] or 0) if current_rows else 0

        # Rolling average (prior 5 windows)
        prior_avg_rows = execute_query(
            """
            SELECT AVG(cnt) AS avg_cnt FROM (
                SELECT COUNT(*) AS cnt
                FROM grievances
                WHERE org_id = %s AND respondent_id = %s
                  AND created_at BETWEEN %s AND %s
                GROUP BY DATE_TRUNC('hour', created_at)
                LIMIT 120  -- up to 5 * 24 windows
            ) sub
        """,
            (
                org_id,
                respondent_id,
                now - timedelta(hours=window_hours * 6),
                window_start,
            ),
        )
        rolling_avg = float(prior_avg_rows[0]["avg_cnt"] or 0) if prior_avg_rows else 0

        spike_threshold = max(spike_min_count, rolling_avg * spike_multiplier)
        anomaly_detected = current_count >= spike_threshold

        if anomaly_detected:
            log_id = str(uuid.uuid4())
            execute_transaction(
                [
                    (
                        """
                INSERT INTO grievance_anomaly_log
                    (id, org_id, window_start, window_end, count, threshold, outcome)
                VALUES (%s, %s, %s, %s, %s, %s, 'DEAN_REVIEW_QUEUED')
                """,
                        (
                            log_id,
                            org_id,
                            window_start,
                            now,
                            current_count,
                            round(spike_threshold, 1),
                        ),
                    ),
                    # Halt normal routing for ALL pending grievances against this respondent
                    (
                        """
                UPDATE grievances
                SET status = 'ANOMALY_HOLD'
                WHERE org_id = %s
                  AND respondent_id = %s
                  AND status IN ('PENDING', 'OPEN')
                """,
                        (org_id, respondent_id),
                    ),
                ]
            )

            AuditLog.log(
                org_id=org_id,
                actor_id="system",
                action=AuditAction.CREATED,
                resource_type="grievance_anomaly",
                resource_id=log_id,
                detail={
                    "respondent_id": respondent_id,
                    "count": current_count,
                    "threshold": round(spike_threshold, 1),
                    "flags": flags,
                },
            )

            DomainEventBus.publish(
                DomainEvent(
                    event_type="student_services.grievance_anomaly_detected",
                    org_id=org_id,
                    payload={
                        "log_id": log_id,
                        "respondent_id": respondent_id,
                        "count": current_count,
                        "threshold": round(spike_threshold, 1),
                        "flags": flags,
                        "template_key": "GRIEVANCE_ANOMALY_DEAN_ALERT",
                    },
                )
            )

            logger.warning(
                "Grievance spike detected: org=%s respondent=%s count=%d threshold=%.1f",
                org_id,
                respondent_id,
                current_count,
                spike_threshold,
            )

        return {
            "anomaly_detected": anomaly_detected,
            "action": "DEAN_REVIEW_QUEUED" if anomaly_detected else "NORMAL_ROUTING",
            "current_count": current_count,
            "spike_threshold": round(spike_threshold, 1) if anomaly_detected else None,
            "flags": flags,
        }

    @classmethod
    def get_anomaly_queue(cls, org_id: str) -> list:
        """Dean-only: list all active anomaly holds."""
        return execute_query(
            """
            SELECT l.id, l.window_start, l.window_end, l.count, l.threshold, l.outcome,
                   COUNT(g.id) AS grievances_on_hold
            FROM grievance_anomaly_log l
            LEFT JOIN grievances g ON g.org_id = l.org_id AND g.status = 'ANOMALY_HOLD'
            WHERE l.org_id = %s
            GROUP BY l.id, l.window_start, l.window_end, l.count, l.threshold, l.outcome
            ORDER BY l.window_end DESC
            LIMIT 50
        """,
            (org_id,),
        )
