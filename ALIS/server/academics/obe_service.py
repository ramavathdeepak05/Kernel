"""E20 — OBE / CO-PO Mapping Service

CO-PO mapping (M,L,H weights), attainment calculation per course per semester,
gap analysis, NBA/NAAC OBE report generation.
All thresholds from policy_engine (R1).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class COPOStrength(str, Enum):
    H = "H"
    M = "M"
    L = "L"


_STRENGTH_WEIGHTS: dict[str, int] = {
    COPOStrength.H: 3,
    COPOStrength.M: 2,
    COPOStrength.L: 1,
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OBEService:
    # ------------------------------------------------------------------
    # Program Outcomes
    # ------------------------------------------------------------------

    @classmethod
    def create_program_outcome(
        cls,
        org_id: str,
        program_id: str,
        code: str,
        description: str,
        domain: str | None = None,
        nba_mapping: str | None = None,
    ) -> dict:
        """Create a Program Outcome (PO). ON CONFLICT DO NOTHING on org+program+code."""
        po_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO program_outcomes
                    (id, org_id, program_id, code, description, domain, nba_mapping, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (org_id, program_id, code) DO NOTHING
                """,
                    (po_id, org_id, program_id, code, description, domain, nba_mapping),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="program_outcome",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "create_program_outcome"},
        )
        rows = execute_query(
            "SELECT * FROM program_outcomes WHERE org_id = %s AND program_id = %s AND code = %s",
            (org_id, program_id, code),
        )
        return (
            rows[0]
            if rows
            else {
                "id": po_id,
                "org_id": org_id,
                "program_id": program_id,
                "code": code,
                "description": description,
            }
        )

    # ------------------------------------------------------------------
    # Course Outcomes
    # ------------------------------------------------------------------

    @classmethod
    def create_course_outcome(
        cls,
        org_id: str,
        course_id: str,
        code: str,
        description: str,
        bloom_level: str | None = None,
    ) -> dict:
        """Create a Course Outcome (CO)."""
        co_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO course_outcomes
                    (id, org_id, course_id, code, description, bloom_level, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                    (co_id, org_id, course_id, code, description, bloom_level),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="course_outcome",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "create_course_outcome"},
        )
        rows = execute_query(
            "SELECT * FROM course_outcomes WHERE id = %s AND org_id = %s",
            (co_id, org_id),
        )
        return (
            rows[0]
            if rows
            else {
                "id": co_id,
                "org_id": org_id,
                "course_id": course_id,
                "code": code,
                "description": description,
            }
        )

    # ------------------------------------------------------------------
    # CO-PO Mapping
    # ------------------------------------------------------------------

    @classmethod
    def map_co_to_po(
        cls,
        org_id: str,
        course_id: str,
        co_id: str,
        po_id: str,
        strength: str,
        justification: str | None = None,
    ) -> dict:
        """Map a CO to a PO with H/M/L strength. Upserts on (co_id, po_id)."""
        if strength not in ("H", "M", "L"):
            raise BusinessRuleViolation(
                f"CO-PO strength must be one of H, M, L — got '{strength}'",
                code="OBE_INVALID_STRENGTH",
            )
        mapping_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO co_po_mapping
                    (id, org_id, course_id, co_id, po_id, strength, justification, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (co_id, po_id)
                DO UPDATE SET
                    strength = EXCLUDED.strength,
                    justification = EXCLUDED.justification,
                    updated_at = NOW()
                """,
                    (
                        mapping_id,
                        org_id,
                        course_id,
                        co_id,
                        po_id,
                        strength,
                        justification,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="map_co_to_po",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "map_co_to_po"},
        )
        rows = execute_query(
            "SELECT * FROM co_po_mapping WHERE co_id = %s AND po_id = %s",
            (co_id, po_id),
        )
        return (
            rows[0]
            if rows
            else {
                "id": mapping_id,
                "org_id": org_id,
                "course_id": course_id,
                "co_id": co_id,
                "po_id": po_id,
                "strength": strength,
                "justification": justification,
            }
        )

    # ------------------------------------------------------------------
    # Assessment Rubrics
    # ------------------------------------------------------------------

    @classmethod
    def set_assessment_rubric(
        cls,
        org_id: str,
        course_id: str,
        assessment_type: str,
        co_id: str,
        max_marks: float,
        co_weight_pct: float = 100,
    ) -> dict:
        """Define how an assessment type contributes to a CO's attainment."""
        rubric_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO assessment_rubrics
                    (id, org_id, course_id, assessment_type, co_id,
                     max_marks, co_weight_pct, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                    (
                        rubric_id,
                        org_id,
                        course_id,
                        assessment_type,
                        co_id,
                        max_marks,
                        co_weight_pct,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="assessment_rubric",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "set_assessment_rubric"},
        )
        rows = execute_query(
            "SELECT * FROM assessment_rubrics WHERE id = %s AND org_id = %s",
            (rubric_id, org_id),
        )
        return (
            rows[0]
            if rows
            else {
                "id": rubric_id,
                "org_id": org_id,
                "course_id": course_id,
                "assessment_type": assessment_type,
                "co_id": co_id,
                "max_marks": max_marks,
                "co_weight_pct": co_weight_pct,
            }
        )

    # ------------------------------------------------------------------
    # Attainment Computation
    # ------------------------------------------------------------------

    @classmethod
    def compute_attainment(
        cls,
        org_id: str,
        program_id: str,
        course_id: str,
        semester_id: str,
        actor_id: str,
    ) -> list:
        """
        Compute CO-PO attainment for a course in a semester.

        Uses policy_engine for the attainment threshold (R1).
        Inserts/updates attainment_records with policy_version_id (R12).
        If no assessment data is available, records placeholder (0/0/0%).
        """
        attainment_threshold_pct = policy_engine.get_value(
            "obe.attainment_threshold_pct", org_id, default=60
        )

        # Resolve policy_version_id (R12)
        pv_rows = execute_query(
            "SELECT id FROM tenant_policies WHERE org_id = %s AND status = 'APPROVED' ORDER BY created_at DESC LIMIT 1",
            (org_id,),
        )
        policy_version_id = pv_rows[0]["id"] if pv_rows else None

        # Get CO-PO mappings for this course
        mappings = execute_query(
            """
            SELECT co.id AS co_id, co.code AS co_code,
                   po.id AS po_id, po.code AS po_code,
                   cpm.strength
            FROM co_po_mapping cpm
            JOIN course_outcomes co ON co.id = cpm.co_id
            JOIN program_outcomes po ON po.id = cpm.po_id
            WHERE co.course_id = %s AND co.org_id = %s
            """,
            (course_id, org_id),
        )

        results = []
        ops: list[tuple] = []

        for m in mappings:
            co_id = m["co_id"]
            po_id = m["po_id"]
            strength = m["strength"]
            strength_weight = _STRENGTH_WEIGHTS.get(strength, 1)

            # Count students who attained the threshold for this CO
            assessment_rows = execute_query(
                """
                SELECT
                    COUNT(DISTINCT sr.student_id) AS students_assessed,
                    COUNT(DISTINCT CASE
                        WHEN sr.marks_obtained >= (ar.max_marks * %s / 100.0)
                        THEN sr.student_id
                    END) AS students_attained
                FROM assessment_rubrics ar
                JOIN student_results sr
                    ON sr.assessment_type = ar.assessment_type
                   AND sr.course_id = ar.course_id
                   AND sr.semester_id = %s
                WHERE ar.co_id = %s AND ar.course_id = %s AND ar.org_id = %s
                """,
                (attainment_threshold_pct, semester_id, co_id, course_id, org_id),
            )

            if assessment_rows and assessment_rows[0]["students_assessed"]:
                students_assessed = int(assessment_rows[0]["students_assessed"])
                students_attained = int(assessment_rows[0]["students_attained"])
                attainment_pct = (students_attained / students_assessed) * 100
            else:
                students_assessed = 0
                students_attained = 0
                attainment_pct = 0.0

            weighted_attainment = attainment_pct * strength_weight / 3.0

            record_id = str(uuid4())
            ops.append(
                (
                    """
                INSERT INTO attainment_records
                    (id, org_id, program_id, course_id, semester_id,
                     co_id, po_id, strength, strength_weight,
                     students_assessed, students_attained,
                     attainment_pct, weighted_attainment,
                     policy_version_id, computed_at)
                VALUES (%s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, NOW())
                ON CONFLICT (course_id, semester_id, co_id, po_id)
                DO UPDATE SET
                    students_assessed  = EXCLUDED.students_assessed,
                    students_attained  = EXCLUDED.students_attained,
                    attainment_pct     = EXCLUDED.attainment_pct,
                    weighted_attainment= EXCLUDED.weighted_attainment,
                    policy_version_id  = EXCLUDED.policy_version_id,
                    computed_at        = NOW()
                """,
                    (
                        record_id,
                        org_id,
                        program_id,
                        course_id,
                        semester_id,
                        co_id,
                        po_id,
                        strength,
                        strength_weight,
                        students_assessed,
                        students_attained,
                        attainment_pct,
                        weighted_attainment,
                        policy_version_id,
                    ),
                )
            )

            results.append(
                {
                    "co_id": co_id,
                    "co_code": m["co_code"],
                    "po_id": po_id,
                    "po_code": m["po_code"],
                    "strength": strength,
                    "students_assessed": students_assessed,
                    "students_attained": students_attained,
                    "attainment_pct": round(attainment_pct, 2),
                    "weighted_attainment": round(weighted_attainment, 2),
                    "policy_version_id": policy_version_id,
                }
            )

        if ops:
            execute_transaction(ops)

            AuditLog.log(
                action=AuditAction.UPDATE,
                actor_id=actor_id,
                actor_role="system",
                entity_type="compute_attainment",
                entity_id=record_id,
                tenant_id=org_id,
                metadata={"source": "compute_attainment"},
            )

        return results

    # ------------------------------------------------------------------
    # CO-PO Matrix
    # ------------------------------------------------------------------

    @classmethod
    def get_co_po_matrix(cls, org_id: str, course_id: str) -> dict:
        """Return the CO-PO correlation matrix for a course."""
        rows = execute_query(
            """
            SELECT co.id AS co_id, co.code AS co_code, co.description AS co_description,
                   po.id AS po_id, po.code AS po_code, cpm.strength
            FROM co_po_mapping cpm
            JOIN course_outcomes co ON co.id = cpm.co_id
            JOIN program_outcomes po ON po.id = cpm.po_id
            WHERE co.course_id = %s AND co.org_id = %s
            ORDER BY co.code, po.code
            """,
            (course_id, org_id),
        )

        # Group by CO
        co_map: dict[str, Any] = {}
        for r in rows:
            cid = r["co_id"]
            if cid not in co_map:
                co_map[cid] = {
                    "co_id": cid,
                    "co_code": r["co_code"],
                    "description": r["co_description"],
                    "po_mappings": [],
                }
            co_map[cid]["po_mappings"].append(
                {
                    "po_id": r["po_id"],
                    "po_code": r["po_code"],
                    "strength": r["strength"],
                }
            )

        return {
            "course_id": course_id,
            "outcomes": list(co_map.values()),
        }

    # ------------------------------------------------------------------
    # Attainment Report
    # ------------------------------------------------------------------

    @classmethod
    def get_attainment_report(cls, org_id: str, program_id: str) -> dict:
        """Aggregate CO-PO attainment across all courses for a program."""
        target_pct = policy_engine.get_value(
            "obe.po_attainment_target", org_id, default=70
        )

        rows = execute_query(
            """
            SELECT ar.po_id, po.code AS po_code,
                   AVG(ar.attainment_pct) AS avg_attainment_pct
            FROM attainment_records ar
            JOIN program_outcomes po ON po.id = ar.po_id
            WHERE ar.program_id = %s AND ar.org_id = %s
            GROUP BY ar.po_id, po.code
            ORDER BY po.code
            """,
            (program_id, org_id),
        )

        po_attainment = [
            {
                "po_id": r["po_id"],
                "po_code": r["po_code"],
                "avg_attainment_pct": round(float(r["avg_attainment_pct"]), 2),
                "target_pct": target_pct,
            }
            for r in rows
        ]

        return {
            "program_id": program_id,
            "po_attainment": po_attainment,
        }

    # ------------------------------------------------------------------
    # Gap Analysis
    # ------------------------------------------------------------------

    @classmethod
    def get_gap_analysis(cls, org_id: str, program_id: str) -> list:
        """
        Compare each PO's average attainment against the target threshold.
        Returns a list of {po_code, attainment_pct, target_pct, gap_pct, status}.
        """
        report = cls.get_attainment_report(org_id, program_id)
        gaps = []
        for entry in report["po_attainment"]:
            attainment = entry["avg_attainment_pct"]
            target = entry["target_pct"]
            gap = target - attainment
            gaps.append(
                {
                    "po_id": entry["po_id"],
                    "po_code": entry["po_code"],
                    "attainment_pct": attainment,
                    "target_pct": target,
                    "gap_pct": round(gap, 2),
                    "status": "MET" if attainment >= target else "GAP",
                }
            )
        return gaps
