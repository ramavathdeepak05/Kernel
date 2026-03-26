"""NIRF Data Service — compute and serve NIRF submission data

Reads from regulatory_metrics to produce the 5 NIRF parameter groups:
  TLR  — Teaching, Learning & Resources
  RPC  — Research & Professional Practice
  GO   — Graduation Outcomes
  OI   — Outreach & Inclusivity
  PERCEPTION — Peer & Employer Perception (manual input required)

Reference: ALIS-skills/references/architecture.md §5
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class NIRFService:

    @staticmethod
    def compute_submission(org_id: str, submission_year: int) -> Dict[str, Any]:
        """Compute NIRF parameter data from regulatory_metrics for submission_year.

        Writes results into nirf_data rows (one per parameter group).
        Returns the full submission dict.
        """
        # Pull latest NIRF metrics
        rows = execute_query(
            """
            SELECT DISTINCT ON (metric_key)
                metric_key, metric_value, breakdown
            FROM regulatory_metrics
            WHERE org_id = %s AND framework = 'NIRF'
            ORDER BY metric_key, metric_date DESC
            """,
            (org_id,),
            tenant_id=org_id,
        )
        metrics = {r["metric_key"]: r["metric_value"] for r in rows}
        breakdowns = {r["metric_key"]: r.get("breakdown") or {} for r in rows}

        # Build parameter group data
        tlr = NIRFService._build_tlr(metrics, breakdowns)
        rpc = NIRFService._build_rpc(metrics, breakdowns)
        go  = NIRFService._build_go(metrics, breakdowns)
        oi  = NIRFService._build_oi(metrics, breakdowns)

        groups = {
            "TLR": tlr,
            "RPC": rpc,
            "GO":  go,
            "OI":  oi,
        }

        import json
        for group, data in groups.items():
            execute_transaction(
                [
                    (
                        """
                        INSERT INTO nirf_data
                            (id, org_id, submission_year, parameter_group, data, computed_at, status)
                        VALUES
                            (uuid_generate_v4(), %s, %s, %s, %s, NOW(), 'DRAFT')
                        ON CONFLICT (org_id, submission_year, parameter_group) DO UPDATE
                            SET data = EXCLUDED.data,
                                computed_at = NOW(),
                                status = 'DRAFT',
                                updated_at = NOW()
                        """,
                        (org_id, submission_year, group, json.dumps(data)),
                    )
                ],
                tenant_id=org_id,
            )

        return {
            "org_id": org_id,
            "submission_year": submission_year,
            "status": "DRAFT",
            "parameters": groups,
        }

    @staticmethod
    def get_submission(org_id: str, submission_year: int) -> List[Dict[str, Any]]:
        """Return existing NIRF data rows for a submission year."""
        rows = execute_query(
            """
            SELECT parameter_group, data, status, computed_at
            FROM nirf_data
            WHERE org_id = %s AND submission_year = %s
            ORDER BY parameter_group
            """,
            (org_id, submission_year),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Parameter builders — map metric keys to NIRF field names
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tlr(metrics: dict, breakdowns: dict) -> Dict[str, Any]:
        """TLR: Teaching, Learning & Resources"""
        return {
            "pass_percentage": float(metrics.get("nirf.tlr.pass_percentage", 0) or 0),
            "faculty_with_phd": float(
                metrics.get("naac.criterion_2.faculty_phd_count", 0) or 0
            ),
            "total_faculty": float(
                metrics.get("naac.criterion_2.faculty_total_count", 0) or 0
            ),
            "library_holdings": float(
                metrics.get("naac.criterion_4.library_holdings_count", 0) or 0
            ),
        }

    @staticmethod
    def _build_rpc(metrics: dict, breakdowns: dict) -> Dict[str, Any]:
        """RPC: Research & Professional Practice"""
        return {
            "publications": float(
                metrics.get("naac.criterion_3.research_publications_count", 0) or 0
            ),
            "fdp_completed": float(
                metrics.get("naac.criterion_3.fdp_count", 0) or 0
            ),
        }

    @staticmethod
    def _build_go(metrics: dict, breakdowns: dict) -> Dict[str, Any]:
        """GO: Graduation Outcomes"""
        return {
            "placement_count": float(
                metrics.get("nirf.go.placement_count", 0) or 0
            ),
            "students_receiving_aid": float(
                metrics.get("nirf.go.students_receiving_financial_aid", 0) or 0
            ),
            "total_enrollment": float(
                metrics.get("naac.criterion_1.total_enrollment", 0) or 0
            ),
        }

    @staticmethod
    def _build_oi(metrics: dict, breakdowns: dict) -> Dict[str, Any]:
        """OI: Outreach & Inclusivity"""
        total = float(metrics.get("naac.criterion_1.total_enrollment", 0) or 0)
        return {
            "total_enrollment": total,
            "attrition_count": float(
                metrics.get("naac.criterion_1.attrition_count", 0) or 0
            ),
        }
