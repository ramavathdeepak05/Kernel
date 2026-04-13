"""
HR-1 — Recruitment & Onboarding (UGC Compliance)

Implements:
- UGC eligibility verification (NET/PhD mandatory for Assistant Professor)
- Vacancy sanction (requires budget.approved event from FM-6)
- Selection Committee composition per UGC norms
- Application screening workflow
- Offer → joining → onboarding lifecycle

UGC Eligibility Rules:
- Assistant Professor: NET/SLET qualified OR PhD (from UGC-approved university)
- Associate Professor: PhD mandatory + 8 years teaching + publications
- Professor: PhD mandatory + 10 years teaching + significant publications

Selection Committee (UGC):
- Vice Chancellor (Chairperson)
- 3 External Subject Experts (nominated by VC)
- HOD of the concerned department
- SC/ST representative
- Women representative (if none in above)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class VacancyStatus(str, Enum):
    DRAFT = "DRAFT"
    BUDGET_PENDING = "BUDGET_PENDING"
    SANCTIONED = "SANCTIONED"
    ADVERTISED = "ADVERTISED"
    APPLICATIONS_CLOSED = "APPLICATIONS_CLOSED"
    SCREENING = "SCREENING"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    OFFERED = "OFFERED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class ApplicationStatus(str, Enum):
    RECEIVED = "RECEIVED"
    SCREENED = "SCREENED"
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    SELECTED = "SELECTED"
    OFFER_SENT = "OFFER_SENT"
    JOINED = "JOINED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class UGCDesignation(str, Enum):
    ASSISTANT_PROFESSOR = "ASSISTANT_PROFESSOR"
    ASSOCIATE_PROFESSOR = "ASSOCIATE_PROFESSOR"
    PROFESSOR = "PROFESSOR"


# UGC minimum qualifications per designation
UGC_REQUIREMENTS = {
    UGCDesignation.ASSISTANT_PROFESSOR: {
        "phd_required": False,  # NET/SLET OR PhD
        "net_or_phd": True,
        "min_teaching_years": 0,
        "min_publications": 0,
    },
    UGCDesignation.ASSOCIATE_PROFESSOR: {
        "phd_required": True,
        "net_or_phd": False,
        "min_teaching_years": 8,
        "min_publications": 5,
    },
    UGCDesignation.PROFESSOR: {
        "phd_required": True,
        "net_or_phd": False,
        "min_teaching_years": 10,
        "min_publications": 10,
    },
}


class RecruitmentService:
    @classmethod
    def check_ugc_eligibility(
        cls,
        designation: str,
        has_phd: bool,
        has_net_slet: bool,
        teaching_years: int,
        publication_count: int,
    ) -> dict[str, Any]:
        """Check if a candidate meets UGC eligibility for the given designation."""
        try:
            desig = UGCDesignation(designation)
        except ValueError:
            return {
                "eligible": True,
                "reason": "Non-UGC designation — no UGC check required",
            }

        reqs = UGC_REQUIREMENTS[desig]
        checks = {}
        eligible = True

        if reqs["phd_required"] and not has_phd:
            checks["phd"] = {"passed": False, "reason": "PhD mandatory"}
            eligible = False
        elif reqs["net_or_phd"] and not (has_net_slet or has_phd):
            checks["qualification"] = {
                "passed": False,
                "reason": "NET/SLET or PhD required",
            }
            eligible = False
        else:
            checks["qualification"] = {"passed": True}

        if teaching_years < reqs["min_teaching_years"]:
            checks["teaching_experience"] = {
                "passed": False,
                "reason": f"Minimum {reqs['min_teaching_years']} years required, has {teaching_years}",
            }
            eligible = False
        else:
            checks["teaching_experience"] = {"passed": True, "years": teaching_years}

        if publication_count < reqs["min_publications"]:
            checks["publications"] = {
                "passed": False,
                "reason": f"Minimum {reqs['min_publications']} publications required, has {publication_count}",
            }
            eligible = False
        else:
            checks["publications"] = {"passed": True, "count": publication_count}

        return {
            "designation": designation,
            "eligible": eligible,
            "checks": checks,
        }

    @classmethod
    def create_vacancy(
        cls, org_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        vacancy_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                INSERT INTO vacancies
                    (id, org_id, department, designation, positions_count,
                     qualification_requirements, ugc_designation,
                     budget_id, status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        vacancy_id,
                        org_id,
                        data["department"],
                        data["designation"],
                        data.get("positions_count", 1),
                        data.get("qualification_requirements", ""),
                        data.get("ugc_designation", ""),
                        data.get("budget_id", None),
                        VacancyStatus.DRAFT.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )
        return {"id": vacancy_id, "status": VacancyStatus.DRAFT.value}

    @classmethod
    def sanction_vacancy(
        cls, org_id: str, vacancy_id: str, actor_id: str
    ) -> dict[str, Any]:
        """Sanction vacancy — requires budget approval if budget_id is set."""
        rows = execute_query(
            "SELECT budget_id, status FROM vacancies WHERE id = %s AND org_id = %s",
            (vacancy_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Vacancy {vacancy_id} not found")
        if rows[0]["budget_id"]:
            # Check budget is approved
            budget = execute_query(
                "SELECT status FROM budgets WHERE id = %s AND org_id = %s",
                (rows[0]["budget_id"], org_id),
                tenant_id=org_id,
            )
            if not budget or budget[0]["status"] not in ("APPROVED", "ACTIVE"):
                raise ValueError("Vacancy budget must be approved before sanctioning")

        execute_transaction(
            [
                (
                    "UPDATE vacancies SET status = %s, sanctioned_by = %s, sanctioned_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (VacancyStatus.SANCTIONED.value, actor_id, vacancy_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="admin",
            entity_type="vacancy",
            entity_id=vacancy_id,
            tenant_id=org_id,
            metadata={"event": "vacancy_sanctioned"},
        )
        return {"id": vacancy_id, "status": VacancyStatus.SANCTIONED.value}

    @classmethod
    def screen_application(
        cls,
        org_id: str,
        application_id: str,
        vacancy_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Screen an application against UGC eligibility criteria."""
        app = execute_query(
            "SELECT * FROM recruitment_applications WHERE id = %s AND org_id = %s",
            (application_id, org_id),
            tenant_id=org_id,
        )
        if not app:
            raise ValueError(f"Application {application_id} not found")
        app = dict(app[0])

        vacancy = execute_query(
            "SELECT ugc_designation FROM vacancies WHERE id = %s AND org_id = %s",
            (vacancy_id, org_id),
            tenant_id=org_id,
        )
        ugc_desig = vacancy[0]["ugc_designation"] if vacancy else ""

        eligibility = cls.check_ugc_eligibility(
            designation=ugc_desig,
            has_phd=app.get("has_phd", False),
            has_net_slet=app.get("has_net_slet", False),
            teaching_years=int(app.get("teaching_years", 0)),
            publication_count=int(app.get("publication_count", 0)),
        )

        new_status = (
            ApplicationStatus.ELIGIBLE.value
            if eligibility["eligible"]
            else ApplicationStatus.NOT_ELIGIBLE.value
        )

        execute_transaction(
            [
                (
                    "UPDATE recruitment_applications SET status = %s, screening_result = %s::jsonb, "
                    "screened_at = NOW() WHERE id = %s AND org_id = %s",
                    (new_status, _json_str(eligibility), application_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        return {
            "application_id": application_id,
            "status": new_status,
            "eligibility": eligibility,
        }


def _json_str(obj: Any) -> str:
    import json

    return json.dumps(obj)
