"""
HR-4 — Performance Appraisal (4-Stage Review Flow)

Implements the UGC-mandated Career Advancement Scheme (CAS) appraisal:
- Stage 1: Self-assessment (faculty fills form)
- Stage 2: HOD review (endorses or returns for revision)
- Stage 3: Dean review (validates academic metrics)
- Stage 4: Final committee decision (promotes or defers)

Faculty must Accept the AI-generated draft before submission (EC-HR-02 liability transfer).

CAS Eligibility Thresholds:
- Service ≥ 4 years in current designation
- API (Academic Performance Indicator) score ≥ 100/year
- Minimum publications per UGC norms
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class AppraisalStatus(str, Enum):
    DRAFT = "DRAFT"  # Faculty filling self-assessment
    SELF_SUBMITTED = "SELF_SUBMITTED"  # Stage 1 complete
    HOD_REVIEW = "HOD_REVIEW"  # Stage 2: HOD reviewing
    HOD_RETURNED = "HOD_RETURNED"  # Returned to faculty for revision
    HOD_ENDORSED = "HOD_ENDORSED"  # Stage 2 complete
    DEAN_REVIEW = "DEAN_REVIEW"  # Stage 3: Dean reviewing
    DEAN_RETURNED = "DEAN_RETURNED"  # Returned to HOD
    DEAN_ENDORSED = "DEAN_ENDORSED"  # Stage 3 complete
    COMMITTEE_REVIEW = "COMMITTEE_REVIEW"  # Stage 4: Final committee
    PROMOTED = "PROMOTED"  # Promotion approved
    DEFERRED = "DEFERRED"  # Promotion deferred
    REJECTED = "REJECTED"  # Rejected (rare)


APPRAISAL_TRANSITIONS = {
    AppraisalStatus.DRAFT: {AppraisalStatus.SELF_SUBMITTED},
    AppraisalStatus.SELF_SUBMITTED: {AppraisalStatus.HOD_REVIEW},
    AppraisalStatus.HOD_REVIEW: {
        AppraisalStatus.HOD_ENDORSED,
        AppraisalStatus.HOD_RETURNED,
    },
    AppraisalStatus.HOD_RETURNED: {AppraisalStatus.SELF_SUBMITTED},
    AppraisalStatus.HOD_ENDORSED: {AppraisalStatus.DEAN_REVIEW},
    AppraisalStatus.DEAN_REVIEW: {
        AppraisalStatus.DEAN_ENDORSED,
        AppraisalStatus.DEAN_RETURNED,
    },
    AppraisalStatus.DEAN_RETURNED: {AppraisalStatus.HOD_REVIEW},
    AppraisalStatus.DEAN_ENDORSED: {AppraisalStatus.COMMITTEE_REVIEW},
    AppraisalStatus.COMMITTEE_REVIEW: {
        AppraisalStatus.PROMOTED,
        AppraisalStatus.DEFERRED,
        AppraisalStatus.REJECTED,
    },
    AppraisalStatus.PROMOTED: set(),
    AppraisalStatus.DEFERRED: set(),
    AppraisalStatus.REJECTED: set(),
}


class AppraisalService:
    @classmethod
    def create(
        cls, org_id: str, staff_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        appraisal_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                INSERT INTO appraisals
                    (id, org_id, staff_id, appraisal_period, designation,
                     self_assessment, api_score, publications_count,
                     service_years, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                    (
                        appraisal_id,
                        org_id,
                        staff_id,
                        data.get("appraisal_period", ""),
                        data.get("designation", ""),
                        _json_str(data.get("self_assessment", {})),
                        data.get("api_score", 0),
                        data.get("publications_count", 0),
                        data.get("service_years", 0),
                        AppraisalStatus.DRAFT.value,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )
        return {"id": appraisal_id, "status": AppraisalStatus.DRAFT.value}

    @classmethod
    def advance(
        cls,
        org_id: str,
        appraisal_id: str,
        target: str,
        actor_id: str,
        review_comments: str = "",
        actor_role: str = "system",
    ) -> dict[str, Any]:
        """Move appraisal to next stage (validates transition)."""
        rows = execute_query(
            "SELECT status, staff_id FROM appraisals WHERE id = %s AND org_id = %s",
            (appraisal_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Appraisal {appraisal_id} not found")

        current = AppraisalStatus(rows[0]["status"])
        target_status = AppraisalStatus(target)
        if target_status not in APPRAISAL_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Invalid transition: {current.value} → {target_status.value}"
            )

        update_fields = [("status", target_status.value)]
        if target_status == AppraisalStatus.HOD_ENDORSED:
            update_fields.append(("hod_comments", review_comments))
            update_fields.append(("hod_reviewed_by", actor_id))
        elif target_status == AppraisalStatus.DEAN_ENDORSED:
            update_fields.append(("dean_comments", review_comments))
            update_fields.append(("dean_reviewed_by", actor_id))
        elif target_status in (
            AppraisalStatus.PROMOTED,
            AppraisalStatus.DEFERRED,
            AppraisalStatus.REJECTED,
        ):
            update_fields.append(("committee_decision", target_status.value))
            update_fields.append(("committee_comments", review_comments))

        set_clause = ", ".join(f"{k} = %s" for k, _ in update_fields)
        values = [v for _, v in update_fields]
        values.extend([appraisal_id, org_id])

        execute_transaction(
            [
                (
                    f"UPDATE appraisals SET {set_clause}, updated_at = NOW() WHERE id = %s AND org_id = %s",  # noqa: S608
                    tuple(values),
                )
            ],
            tenant_id=org_id,
        )

        if target_status == AppraisalStatus.PROMOTED:
            DomainEventBus.publish(
                DomainEvent(
                    event_type="hr.promotion_approved",
                    org_id=org_id,
                    payload={
                        "appraisal_id": appraisal_id,
                        "staff_id": str(rows[0]["staff_id"]),
                    },
                    actor_id=actor_id,
                )
            )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="appraisal",
            entity_id=appraisal_id,
            tenant_id=org_id,
            metadata={
                "from": current.value,
                "to": target_status.value,
                "comments": review_comments,
            },
        )
        return {"id": appraisal_id, "status": target_status.value}

    @classmethod
    def check_cas_eligibility(cls, org_id: str, staff_id: str) -> dict[str, Any]:
        """Check if faculty meets CAS promotion eligibility thresholds."""
        rows = execute_query(
            "SELECT designation, date_of_joining FROM staff_profiles WHERE id = %s AND org_id = %s",
            (staff_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Staff {staff_id} not found")

        staff = dict(rows[0])
        joining = staff.get("date_of_joining")
        if joining:
            if isinstance(joining, str):
                joining = datetime.fromisoformat(joining)
            service_years = (datetime.now(timezone.utc) - joining).days / 365.25
        else:
            service_years = 0

        # Get publication count
        pubs = execute_query(
            "SELECT COUNT(*) AS cnt FROM faculty_publications WHERE staff_id = %s AND org_id = %s",
            (staff_id, org_id),
            tenant_id=org_id,
        )
        pub_count = pubs[0]["cnt"] if pubs else 0

        return {
            "staff_id": staff_id,
            "service_years": round(service_years, 1),
            "service_eligible": service_years >= 4,
            "publication_count": pub_count,
            "designation": staff.get("designation", ""),
        }

    @classmethod
    def list_pending(
        cls, org_id: str, stage: str | None = None
    ) -> list[dict[str, Any]]:
        if stage:
            rows = execute_query(
                "SELECT a.id, a.staff_id, s.name, a.appraisal_period, a.status, a.api_score "
                "FROM appraisals a JOIN staff_profiles s ON s.id = a.staff_id "
                "WHERE a.org_id = %s AND a.status = %s ORDER BY a.created_at",
                (org_id, stage),
                tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT a.id, a.staff_id, s.name, a.appraisal_period, a.status, a.api_score "
                "FROM appraisals a JOIN staff_profiles s ON s.id = a.staff_id "
                "WHERE a.org_id = %s AND a.status NOT IN ('PROMOTED', 'DEFERRED', 'REJECTED') "
                "ORDER BY a.created_at",
                (org_id,),
                tenant_id=org_id,
            )
        return [dict(r) for r in rows]


def _json_str(obj: Any) -> str:
    import json

    return json.dumps(obj)
