"""NAAC Dashboard Service — read from regulatory_metrics

Builds NAAC SSR criterion summary views for the dashboard.
ALL data comes from regulatory_metrics — never from source module tables.

Criteria covered:
  C1 — Curricular Aspects
  C2 — Teaching-Learning & Evaluation
  C3 — Research, Innovations & Extension
  C4 — Infrastructure & Learning Resources
  C5 — Student Support & Progression
  C6 — Governance, Leadership & Management
  C7 — Institutional Values & Best Practices

Reference: ALIS-skills/references/architecture.md §5, §20
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from server.db_service import execute_query

logger = logging.getLogger(__name__)


class NAACService:

    @staticmethod
    def get_dashboard(org_id: str, academic_year: Optional[str] = None) -> Dict[str, Any]:
        """Return a full NAAC metric dashboard aggregated per criterion.

        academic_year: optional filter e.g. "2025-26"
        If omitted, returns current running totals (latest date per metric).
        """
        rows = execute_query(
            """
            SELECT DISTINCT ON (metric_key)
                metric_key,
                framework,
                metric_value,
                breakdown,
                metric_date
            FROM regulatory_metrics
            WHERE org_id = %s
              AND framework = 'NAAC'
            ORDER BY metric_key, metric_date DESC
            """,
            (org_id,),
            tenant_id=org_id,
        )

        # Organise by criterion
        criteria: Dict[str, Dict[str, Any]] = {
            f"criterion_{i}": {} for i in range(1, 8)
        }

        for row in rows:
            key: str = row["metric_key"]          # e.g. "naac.criterion_2.pass_percentage"
            parts = key.split(".")
            if len(parts) >= 3 and parts[0] == "naac":
                crit = parts[1]                   # "criterion_2"
                indicator = ".".join(parts[2:])   # "pass_percentage"
                if crit in criteria:
                    criteria[crit][indicator] = {
                        "value": float(row["metric_value"]) if row["metric_value"] is not None else None,
                        "breakdown": row.get("breakdown") or {},
                        "as_of": str(row["metric_date"]),
                    }

        return {
            "org_id": org_id,
            "framework": "NAAC",
            "academic_year": academic_year,
            "criteria": criteria,
        }

    @staticmethod
    def get_criterion_detail(
        org_id: str,
        criterion: int,
    ) -> Dict[str, Any]:
        """Return all metric rows for a specific NAAC criterion."""
        prefix = f"naac.criterion_{criterion}."
        rows = execute_query(
            """
            SELECT metric_key, metric_value, breakdown, metric_date
            FROM regulatory_metrics
            WHERE org_id = %s
              AND framework = 'NAAC'
              AND metric_key LIKE %s
            ORDER BY metric_key, metric_date DESC
            """,
            (org_id, f"{prefix}%"),
            tenant_id=org_id,
        )
        return {
            "criterion": criterion,
            "metrics": [dict(r) for r in rows],
        }

    @staticmethod
    def get_evidence_list(
        org_id: str,
        criterion: Optional[int] = None,
        academic_year: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return NAAC evidence items, optionally filtered."""
        conditions = ["org_id = %s"]
        params: list = [org_id]

        if criterion:
            conditions.append("criterion = %s")
            params.append(criterion)
        if academic_year:
            conditions.append("academic_year = %s")
            params.append(academic_year)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = " AND ".join(conditions)
        rows = execute_query(
            f"""
            SELECT id, criterion, indicator_key, evidence_type, title,
                   file_key, status, academic_year, created_at
            FROM naac_evidence
            WHERE {where}
            ORDER BY criterion, indicator_key
            """,
            tuple(params),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @staticmethod
    def add_evidence(
        org_id: str,
        criterion: int,
        indicator_key: str,
        title: str,
        academic_year: str,
        evidence_type: str = "DOCUMENT",
        file_key: Optional[str] = None,
        evidence_data: Optional[Dict[str, Any]] = None,
        collected_by: Optional[str] = None,
    ) -> str:
        """Insert a new NAAC evidence record. Returns the new record ID."""
        import json
        from server.db_service import execute_transaction

        new_id = None
        rows = execute_query(
            """
            INSERT INTO naac_evidence
                (id, org_id, criterion, indicator_key, title, academic_year,
                 evidence_type, file_key, evidence_data, collected_by)
            VALUES
                (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (org_id, criterion, indicator_key, title, academic_year,
             evidence_type, file_key, json.dumps(evidence_data or {}), collected_by),
            tenant_id=org_id,
        )
        return str(rows[0]["id"]) if rows else ""

    @staticmethod
    def compute_iqac_score(org_id: str) -> Dict[str, Any]:
        """Compute a weighted IQAC readiness score from live metrics.

        Weights are indicative — institutions calibrate via PolicyEngine
        once the attendance_eligibility-style NAAC scoring DSL is seeded.
        """
        rows = execute_query(
            """
            SELECT DISTINCT ON (metric_key)
                metric_key, metric_value
            FROM regulatory_metrics
            WHERE org_id = %s AND framework = 'NAAC'
            ORDER BY metric_key, metric_date DESC
            """,
            (org_id,),
            tenant_id=org_id,
        )
        metrics = {r["metric_key"]: r["metric_value"] for r in rows}

        # Indicative weights — replace with policy_engine.get_value() once DSL seeded
        scores: Dict[str, float] = {}

        pass_pct = metrics.get("naac.criterion_2.pass_percentage")
        if pass_pct is not None:
            scores["C2_pass_percentage"] = min(float(pass_pct) / 100.0, 1.0) * 30.0

        placement = metrics.get("naac.criterion_5.placement_count")
        enrollment = metrics.get("naac.criterion_1.total_enrollment")
        if placement is not None and enrollment and float(enrollment) > 0:
            placement_rate = float(placement) / float(enrollment)
            scores["C5_placement_rate"] = min(placement_rate, 1.0) * 20.0

        grievances = metrics.get("naac.criterion_6.grievance_resolved_count")
        if grievances is not None:
            scores["C6_grievances_resolved"] = min(float(grievances) / 10.0, 1.0) * 10.0

        total = sum(scores.values())
        return {
            "org_id": org_id,
            "iqac_readiness_score": round(total, 2),
            "max_possible": 60.0,
            "component_scores": scores,
            "note": "Indicative only. Calibrate weights via PolicyEngine DSL.",
        }
