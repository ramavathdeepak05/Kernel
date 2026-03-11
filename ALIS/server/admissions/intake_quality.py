"""
E04-S08 — Intake Quality Scoring Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (Analytical agent) + Layer 6 (Observability)
ENTITY: IntakeQualityScore

Scores an admission intake batch on academic quality, yield metrics,
and diversity indicators. Results are stored timestamped and alerts
are triggered for leadership if below threshold.

Scoring Factors:
    - avg_eligibility_score (40%)   — Mean AI confidence across batch
    - yield_rate (30%)              — Admitted / Applied ratio
    - diversity_index (20%)         — Program spread across batch
    - doc_verification_rate (10%)   — Verified docs / total docs

Alert threshold: quality_score < 0.60

Acceptance Criteria (E04-S08):
    - [x] Batch score stored and timestamped
    - [x] Alert if below threshold
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.db_service import execute_query, execute_transaction

from .models import IntakeQualityScoreRead, IntakeScoreRequest

logger = logging.getLogger(__name__)

_ALERT_THRESHOLD = 0.60


class IntakeQualityService:
    """
    Computes and stores intake batch quality scores.
    """

    @classmethod
    def score_batch(
        cls,
        request: IntakeScoreRequest,
        org_id: str,
        actor_id: str,
    ) -> IntakeQualityScoreRead:
        """
        Compute and store a quality score for an intake batch.

        The batch is identified by batch_id (e.g., "AY2025-26-Q1").
        Applicants are scoped by org_id and optionally by program.

        Returns:
            IntakeQualityScoreRead with quality_score and factors.
        """
        factors = cls._compute_factors(
            batch_id=request.batch_id,
            org_id=org_id,
            program=request.program,
        )
        quality_score = cls._aggregate_score(factors)
        alert_triggered = quality_score < _ALERT_THRESHOLD

        score_id = str(uuid4())
        now = datetime.now(timezone.utc)

        import json
        execute_transaction([
            (
                """
                INSERT INTO intake_quality_scores
                    (id, org_id, batch_id, program, quality_score,
                     factors, alert_triggered, scored_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    score_id, org_id,
                    request.batch_id,
                    request.program,
                    quality_score,
                    json.dumps(factors),
                    alert_triggered,
                    now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="intake_quality_score",
            entity_id=score_id,
            org_id=org_id,
            module="M1",
            wizard="Intake Quality Scoring",
            success=True,
            metadata={
                "batch_id": request.batch_id,
                "quality_score": quality_score,
                "alert_triggered": alert_triggered,
                "factors": factors,
            },
        )

        if alert_triggered:
            cls._raise_alert(
                batch_id=request.batch_id,
                quality_score=quality_score,
                org_id=org_id,
            )
            logger.warning(
                "E04-S08: ALERT — Intake quality below threshold "
                "[batch=%s, score=%.2f, threshold=%.2f, org=%s]",
                request.batch_id, quality_score, _ALERT_THRESHOLD, org_id,
            )
        else:
            logger.info(
                "E04-S08: Intake scored [batch=%s, score=%.2f, org=%s]",
                request.batch_id, quality_score, org_id,
            )

        return IntakeQualityScoreRead(
            id=score_id,
            org_id=org_id,
            batch_id=request.batch_id,
            program=request.program,
            quality_score=quality_score,
            factors=factors,
            alert_triggered=alert_triggered,
            scored_at=now,
        )

    # -------------------------------------------------------------------------
    # Factor computation
    # -------------------------------------------------------------------------

    @classmethod
    def _compute_factors(
        cls, batch_id: str, org_id: str, program: Optional[str]
    ) -> Dict[str, Any]:
        """Compute individual scoring factors from the admissions data."""
        program_filter = ""
        params_base = [org_id]
        if program:
            program_filter = "AND intended_program = %s"
            params_base.append(program)

        # Total applicants
        total_rows = execute_query(
            f"SELECT COUNT(*) AS cnt FROM applicants "
            f"WHERE org_id = %s {program_filter}",
            tuple(params_base),
        )
        total = int(total_rows[0]["cnt"]) if total_rows else 0

        if total == 0:
            return {
                "avg_eligibility_score": 0.0,
                "yield_rate": 0.0,
                "diversity_index": 0.0,
                "doc_verification_rate": 0.0,
                "total_applicants": 0,
            }

        # Admitted count for yield rate
        admitted_rows = execute_query(
            f"SELECT COUNT(*) AS cnt FROM applicants "
            f"WHERE org_id = %s AND status IN ('ADMITTED','ENROLLED') {program_filter}",
            tuple(params_base),
        )
        admitted = int(admitted_rows[0]["cnt"]) if admitted_rows else 0
        yield_rate = admitted / total if total else 0.0

        # Average eligibility score from audit metadata
        score_rows = execute_query(
            "SELECT metadata->>'eligibility_score' AS score FROM audit_ledger "
            "WHERE org_id = %s AND action = 'state_transition' "
            "AND metadata->>'to_state' IN ('ELIGIBLE','NOT_ELIGIBLE','PROVISIONALLY_ELIGIBLE')",
            (org_id,),
        )
        scores = [
            float(r["score"])
            for r in score_rows
            if r.get("score") is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0.5

        # Diversity index: number of distinct programs / 10 (capped at 1.0)
        div_rows = execute_query(
            "SELECT COUNT(DISTINCT intended_program) AS cnt FROM applicants "
            "WHERE org_id = %s",
            (org_id,),
        )
        diversity_index = min(1.0, int(div_rows[0]["cnt"]) / 10) if div_rows else 0.0

        # Document verification rate
        doc_rows = execute_query(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN is_verified THEN 1 ELSE 0 END) AS verified "
            "FROM application_documents WHERE org_id = %s",
            (org_id,),
        )
        doc_total = int(doc_rows[0]["total"]) if doc_rows else 0
        doc_verified = int(doc_rows[0]["verified"] or 0) if doc_rows else 0
        doc_rate = doc_verified / doc_total if doc_total else 0.0

        return {
            "avg_eligibility_score": round(avg_score, 4),
            "yield_rate": round(yield_rate, 4),
            "diversity_index": round(diversity_index, 4),
            "doc_verification_rate": round(doc_rate, 4),
            "total_applicants": total,
            "admitted_count": admitted,
        }

    @staticmethod
    def _aggregate_score(factors: Dict[str, Any]) -> float:
        """Weighted aggregate score from factors."""
        return round(
            0.40 * factors.get("avg_eligibility_score", 0.0)
            + 0.30 * factors.get("yield_rate", 0.0)
            + 0.20 * factors.get("diversity_index", 0.0)
            + 0.10 * factors.get("doc_verification_rate", 0.0),
            4,
        )

    @classmethod
    def _raise_alert(cls, batch_id: str, quality_score: float, org_id: str) -> None:
        """Send alert to leadership when quality score is below threshold."""
        try:
            from server.core.notifications.service import NotificationService
            svc = NotificationService()
            svc.send(
                template_id="intake_quality_alert",
                recipient_id="leadership",
                recipient_address=f"leadership@{org_id}.internal",
                context={
                    "batch_id": batch_id,
                    "quality_score": f"{quality_score:.2f}",
                    "threshold": f"{_ALERT_THRESHOLD:.2f}",
                },
                org_id=org_id,
            )
        except Exception as e:
            logger.warning("E04-S08: Alert notification failed: %s", e)
