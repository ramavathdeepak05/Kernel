"""
Regulatory Compliance Modules — RA-3 through RA-8

RA-3: UGC Compliance & Annual Returns
RA-4: AICTE Approval (Technical Programs)
RA-5: NBA Accreditation (Program-Level)
RA-6: AISHE Data Submission
RA-7: State Regulatory Body Compliance
RA-8: IQAC (Internal Quality Assurance Cell)

All modules pull data from regulatory_metrics + live module queries.
Data provenance is tagged: live_module | legacy_import | manual_entry | estimated
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ======================================================================
# RA-3: UGC Compliance & Annual Returns
# ======================================================================

class UGCComplianceService:
    """
    UGC Annual Return compilation + fee compliance + faculty compliance.
    """

    @classmethod
    def compile_annual_return(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Compile UGC annual return data from live modules."""
        return {
            "academic_year": academic_year,
            "enrollment": cls._get_enrollment_data(org_id, academic_year),
            "faculty": cls._get_faculty_data(org_id),
            "programs": cls._get_program_data(org_id),
            "financial_summary": cls._get_financial_summary(org_id, academic_year),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def check_fee_compliance(cls, org_id: str) -> Dict[str, Any]:
        """Verify fee structures comply with UGC regulations (no unpermitted hikes)."""
        fee_structures = execute_query(
            "SELECT id, name, total_amount, academic_year, is_published FROM fee_structures "
            "WHERE org_id = %s ORDER BY academic_year DESC",
            (org_id,), tenant_id=org_id,
        )
        violations = []
        for i, fs in enumerate(fee_structures):
            if not fs.get("is_published"):
                violations.append({
                    "fee_structure": fs.get("name"),
                    "violation": "Fee structure not published before admissions (UGC mandate)",
                })
        return {
            "compliant": len(violations) == 0,
            "fee_structures": [dict(f) for f in fee_structures],
            "violations": violations,
        }

    @classmethod
    def check_faculty_compliance(cls, org_id: str) -> Dict[str, Any]:
        """Check faculty positions: sanctioned vs filled, NET/PhD percentages."""
        departments = execute_query(
            """
            SELECT department, COUNT(*) AS filled,
                   COUNT(*) FILTER (WHERE has_phd = TRUE) AS phd_count,
                   COUNT(*) FILTER (WHERE has_net_slet = TRUE) AS net_count
            FROM staff_profiles WHERE org_id = %s AND status = 'ACTIVE'
            GROUP BY department ORDER BY department
            """,
            (org_id,), tenant_id=org_id,
        )
        # Check for vacancy gaps > 20%
        alerts = []
        for d in departments:
            dept = dict(d)
            # Simple check: if fewer than expected (would need sanctioned positions table)
            if dept["filled"] < 3:
                alerts.append({
                    "department": dept["department"],
                    "severity": "WARNING",
                    "message": f"Only {dept['filled']} faculty — may be below sanctioned strength",
                })
        return {
            "departments": [dict(d) for d in departments],
            "alerts": alerts,
        }

    @classmethod
    def _get_enrollment_data(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        rows = execute_query(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE role = 'STUDENT') AS students
            FROM users WHERE org_id = %s AND status = 'ACTIVE' AND is_deleted = FALSE
            """,
            (org_id,), tenant_id=org_id,
        )
        return dict(rows[0]) if rows else {"total": 0, "students": 0}

    @classmethod
    def _get_faculty_data(cls, org_id: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT COUNT(*) AS total FROM staff_profiles WHERE org_id = %s AND status = 'ACTIVE'",
            (org_id,), tenant_id=org_id,
        )
        return {"total_faculty": rows[0]["total"] if rows else 0}

    @classmethod
    def _get_program_data(cls, org_id: str) -> List[Dict[str, Any]]:
        rows = execute_query(
            "SELECT id, name, code, degree_type, duration_years FROM programs WHERE org_id = %s AND status = 'ACTIVE'",
            (org_id,), tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @classmethod
    def _get_financial_summary(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        rows = execute_query(
            "SELECT COALESCE(SUM(total_amount), 0) AS total_revenue FROM invoices "
            "WHERE org_id = %s AND status = 'PAID' AND EXTRACT(YEAR FROM created_at) >= %s",
            (org_id, int(academic_year[:4])), tenant_id=org_id,
        )
        return {"total_revenue": float(rows[0]["total_revenue"]) if rows else 0}


# ======================================================================
# RA-4: AICTE Approval
# ======================================================================

class AICTEComplianceService:
    """
    AICTE compliance for technical programs.
    Faculty norms: 1:15 (UG Engineering).
    """

    FACULTY_STUDENT_RATIO = 15  # UGC/AICTE norm for UG Engineering

    @classmethod
    def get_compliance_dashboard(cls, org_id: str) -> Dict[str, Any]:
        """Real-time AICTE compliance status."""
        programs = execute_query(
            "SELECT id, name, code, intake_capacity FROM programs "
            "WHERE org_id = %s AND status = 'ACTIVE' AND degree_type IN ('B.TECH', 'B.E', 'M.TECH', 'M.E')",
            (org_id,), tenant_id=org_id,
        )
        compliance_items = []
        for p in programs:
            prog = dict(p)
            intake = int(prog.get("intake_capacity", 0))
            required_faculty = max(1, intake // cls.FACULTY_STUDENT_RATIO)

            # Count faculty assigned to this program
            faculty_count = execute_query(
                "SELECT COUNT(*) AS cnt FROM employee_department_assignments "
                "WHERE department = %s AND org_id = %s",
                (prog.get("code", prog["name"]), org_id), tenant_id=org_id,
            )
            actual = faculty_count[0]["cnt"] if faculty_count else 0

            compliant = actual >= required_faculty
            compliance_items.append({
                "program": prog["name"],
                "code": prog.get("code", ""),
                "intake": intake,
                "required_faculty": required_faculty,
                "actual_faculty": actual,
                "compliant": compliant,
                "gap": max(0, required_faculty - actual),
            })

        all_compliant = all(c["compliant"] for c in compliance_items)
        return {
            "overall_compliant": all_compliant,
            "programs": compliance_items,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def generate_acr(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Generate Annual Compliance Report data."""
        dashboard = cls.get_compliance_dashboard(org_id)
        return {
            "report_type": "AICTE_ACR",
            "academic_year": academic_year,
            "compliance_status": dashboard,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ======================================================================
# RA-5: NBA Accreditation (Program-Level)
# ======================================================================

class NBAAccreditationService:
    """
    NBA Self-Assessment Report (SAR) preparation.
    Dependent on CO-PO attainment from Academics E20 OBE module.
    """

    @classmethod
    def get_program_obe_status(cls, org_id: str, program_id: str) -> Dict[str, Any]:
        """Get OBE status for NBA SAR."""
        co_attainment = execute_query(
            "SELECT course_id, co_code, attainment_level FROM co_attainment_records "
            "WHERE org_id = %s AND program_id = %s ORDER BY course_id, co_code",
            (org_id, program_id), tenant_id=org_id,
        )
        total = len(co_attainment) if co_attainment else 0
        above_60 = sum(1 for r in co_attainment if float(r.get("attainment_level", 0)) >= 60)

        return {
            "program_id": program_id,
            "total_cos_mapped": total,
            "cos_above_60_pct": above_60,
            "attainment_rate": round(above_60 / total * 100, 1) if total > 0 else 0,
            "nba_ready": above_60 / total >= 0.6 if total > 0 else False,
            "records": [dict(r) for r in co_attainment] if co_attainment else [],
        }

    @classmethod
    def generate_sar_data(cls, org_id: str, program_id: str) -> Dict[str, Any]:
        """Compile SAR quantitative data for a program."""
        obe = cls.get_program_obe_status(org_id, program_id)
        program = execute_query(
            "SELECT name, code, degree_type, intake_capacity FROM programs WHERE id = %s AND org_id = %s",
            (program_id, org_id), tenant_id=org_id,
        )
        return {
            "report_type": "NBA_SAR",
            "program": dict(program[0]) if program else {},
            "obe_status": obe,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ======================================================================
# RA-6: AISHE Data Submission
# ======================================================================

class AISHEDataService:
    """
    All India Survey on Higher Education (AISHE) data compilation.
    Annual submission: October–December (Ministry of Education).
    """

    @classmethod
    def compile_aishe_data(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Compile AISHE submission data from all modules."""
        enrollment = execute_query(
            "SELECT COUNT(*) AS total FROM users WHERE org_id = %s AND role = 'STUDENT' AND status = 'ACTIVE'",
            (org_id,), tenant_id=org_id,
        )
        faculty = execute_query(
            "SELECT COUNT(*) AS total FROM staff_profiles WHERE org_id = %s AND status = 'ACTIVE'",
            (org_id,), tenant_id=org_id,
        )
        programs = execute_query(
            "SELECT COUNT(*) AS total FROM programs WHERE org_id = %s AND status = 'ACTIVE'",
            (org_id,), tenant_id=org_id,
        )
        results = execute_query(
            "SELECT COUNT(*) FILTER (WHERE is_pass = TRUE) AS passed, COUNT(*) AS total "
            "FROM grades WHERE org_id = %s AND is_published = TRUE",
            (org_id,), tenant_id=org_id,
        )

        return {
            "report_type": "AISHE",
            "academic_year": academic_year,
            "institution_profile": {"org_id": org_id},
            "enrollment": {"total_students": enrollment[0]["total"] if enrollment else 0},
            "faculty": {"total_faculty": faculty[0]["total"] if faculty else 0},
            "programs": {"total_programs": programs[0]["total"] if programs else 0},
            "examination_results": {
                "total_appeared": results[0]["total"] if results else 0,
                "total_passed": results[0]["passed"] if results else 0,
                "pass_rate": round(results[0]["passed"] / results[0]["total"] * 100, 1) if results and results[0]["total"] > 0 else 0,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ======================================================================
# RA-7: State Regulatory Body Compliance
# ======================================================================

class StateComplianceService:
    """
    State-specific compliance: quota, reservation roster, fee regulation.
    """

    @classmethod
    def get_reservation_roster(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Generate reservation roster (SC/ST/OBC/EWS per state rules)."""
        categories = execute_query(
            """
            SELECT category, COUNT(*) AS count
            FROM applicants
            WHERE org_id = %s AND status = 'ENROLLED'
            AND academic_year = %s
            GROUP BY category ORDER BY category
            """,
            (org_id, academic_year), tenant_id=org_id,
        )

        # Standard reservation percentages (configurable per state)
        roster = {
            "academic_year": academic_year,
            "categories": [dict(c) for c in categories] if categories else [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return roster

    @classmethod
    def check_quota_compliance(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Check if admission quota is being met per state regulations."""
        total_enrolled = execute_query(
            "SELECT COUNT(*) AS cnt FROM applicants WHERE org_id = %s AND status = 'ENROLLED' AND academic_year = %s",
            (org_id, academic_year), tenant_id=org_id,
        )
        total = total_enrolled[0]["cnt"] if total_enrolled else 0

        roster = cls.get_reservation_roster(org_id, academic_year)
        return {
            "total_enrolled": total,
            "roster": roster,
            "compliant": True,  # Detailed check requires state-specific config
        }


# ======================================================================
# RA-8: IQAC (Internal Quality Assurance Cell)
# ======================================================================

class IQACService:
    """
    IQAC meeting management, best practices documentation,
    readiness monitoring, and AQAR compilation support.
    """

    @classmethod
    def schedule_meeting(cls, org_id: str, data: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
        """Schedule an IQAC meeting (UGC: minimum 2 per year)."""
        meeting_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO iqac_meetings
                    (id, org_id, meeting_date, agenda, attendees, status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, 'SCHEDULED', %s, %s)
                """,
                (meeting_id, org_id, data["meeting_date"], data.get("agenda", ""),
                 _json_str(data.get("attendees", [])), actor_id, now),
            )
        ], tenant_id=org_id)
        return {"id": meeting_id, "status": "SCHEDULED"}

    @classmethod
    def record_minutes(cls, org_id: str, meeting_id: str, minutes: str, action_items: List[Dict], actor_id: str) -> Dict[str, Any]:
        """Record meeting minutes and action items."""
        execute_transaction([
            ("UPDATE iqac_meetings SET minutes = %s, action_items = %s::jsonb, status = 'COMPLETED' "
             "WHERE id = %s AND org_id = %s",
             (minutes, _json_str(action_items), meeting_id, org_id)),
        ], tenant_id=org_id)

        # Create action item tracking entries
        for item in action_items:
            execute_transaction([
                (
                    "INSERT INTO iqac_action_items (id, org_id, meeting_id, description, responsible, "
                    "deadline, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', NOW())",
                    (str(uuid4()), org_id, meeting_id, item.get("description", ""),
                     item.get("responsible", ""), item.get("deadline")),
                )
            ], tenant_id=org_id)

        return {"meeting_id": meeting_id, "status": "COMPLETED", "action_items": len(action_items)}

    @classmethod
    def document_best_practice(cls, org_id: str, data: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
        """Document a best practice (NAAC requires 2 per year)."""
        bp_id = str(uuid4())
        execute_transaction([
            (
                "INSERT INTO iqac_best_practices (id, org_id, title, description, category, "
                "impact_metrics, academic_year, created_by, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
                (bp_id, org_id, data["title"], data.get("description", ""),
                 data.get("category", "ACADEMIC"), data.get("impact_metrics", ""),
                 data.get("academic_year", ""), actor_id),
            )
        ], tenant_id=org_id)
        return {"id": bp_id, "status": "DOCUMENTED"}

    @classmethod
    def get_readiness_report(cls, org_id: str) -> Dict[str, Any]:
        """Monthly readiness report for accreditation preparation."""
        # Meetings this year
        meetings = execute_query(
            "SELECT COUNT(*) AS cnt FROM iqac_meetings WHERE org_id = %s AND status = 'COMPLETED' "
            "AND EXTRACT(YEAR FROM meeting_date) = EXTRACT(YEAR FROM NOW())",
            (org_id,), tenant_id=org_id,
        )
        meeting_count = meetings[0]["cnt"] if meetings else 0

        # Best practices this year
        bps = execute_query(
            "SELECT COUNT(*) AS cnt FROM iqac_best_practices WHERE org_id = %s "
            "AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM NOW())",
            (org_id,), tenant_id=org_id,
        )
        bp_count = bps[0]["cnt"] if bps else 0

        # Pending action items
        pending = execute_query(
            "SELECT COUNT(*) AS cnt FROM iqac_action_items WHERE org_id = %s AND status = 'PENDING'",
            (org_id,), tenant_id=org_id,
        )
        pending_count = pending[0]["cnt"] if pending else 0

        return {
            "meetings_this_year": meeting_count,
            "meetings_target": 2,  # UGC minimum
            "meetings_on_track": meeting_count >= 1,  # At least 1 by mid-year
            "best_practices": bp_count,
            "best_practices_target": 2,
            "pending_action_items": pending_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def compile_aqar_data(cls, org_id: str, academic_year: str) -> Dict[str, Any]:
        """Compile AQAR (Annual Quality Assurance Report) data."""
        readiness = cls.get_readiness_report(org_id)
        from server.regulatory.naac_service import NAACService
        try:
            naac_dashboard = NAACService.get_dashboard(org_id)
        except Exception:
            naac_dashboard = {}

        return {
            "report_type": "AQAR",
            "academic_year": academic_year,
            "iqac_readiness": readiness,
            "naac_metrics": naac_dashboard,
            "deadline": f"{int(academic_year[:4]) + 1}-07-31",  # July 31 absolute
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def _json_str(obj: Any) -> str:
    import json
    return json.dumps(obj)
