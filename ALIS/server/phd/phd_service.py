"""E15 — PhD / Doctoral Research Service

9-milestone lifecycle state machine for PhD scholars.
Supervisor load balancer (max scholars from policy).
DC meeting scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class PhDStatus(str, Enum):
    REGISTERED = "REGISTERED"
    COURSEWORK = "COURSEWORK"
    COMPREHENSIVE_EXAM = "COMPREHENSIVE_EXAM"
    PROPOSAL_SUBMITTED = "PROPOSAL_SUBMITTED"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    RESEARCH = "RESEARCH"
    THESIS_SUBMITTED = "THESIS_SUBMITTED"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    AWARDED = "AWARDED"
    WITHDRAWN = "WITHDRAWN"
    EXPELLED = "EXPELLED"


class MilestoneType(str, Enum):
    COURSEWORK_COMPLETE = "COURSEWORK_COMPLETE"
    QUALIFYING_EXAM = "QUALIFYING_EXAM"
    LITERATURE_REVIEW = "LITERATURE_REVIEW"
    SYNOPSIS_APPROVAL = "SYNOPSIS_APPROVAL"
    PROPOSAL_DEFENSE = "PROPOSAL_DEFENSE"
    DATA_COLLECTION = "DATA_COLLECTION"
    THESIS_DRAFT = "THESIS_DRAFT"
    PLAGIARISM_CHECK = "PLAGIARISM_CHECK"
    VIVA_VOCE = "VIVA_VOCE"


# Milestone → next PhDStatus mapping (None = no status change)
_MILESTONE_STATUS_MAP = {
    MilestoneType.COURSEWORK_COMPLETE: PhDStatus.COURSEWORK,
    MilestoneType.QUALIFYING_EXAM: PhDStatus.COMPREHENSIVE_EXAM,
    MilestoneType.LITERATURE_REVIEW: None,
    MilestoneType.SYNOPSIS_APPROVAL: PhDStatus.PROPOSAL_SUBMITTED,
    MilestoneType.PROPOSAL_DEFENSE: PhDStatus.PROPOSAL_APPROVED,
    MilestoneType.DATA_COLLECTION: PhDStatus.RESEARCH,
    MilestoneType.THESIS_DRAFT: None,
    MilestoneType.PLAGIARISM_CHECK: None,
    MilestoneType.VIVA_VOCE: PhDStatus.UNDER_EVALUATION,
}

# Statuses that block milestone completion
_TERMINAL_STATUSES = {
    PhDStatus.AWARDED,
    PhDStatus.WITHDRAWN,
    PhDStatus.EXPELLED,
}


class PhDService:
    @classmethod
    def register_scholar(
        cls,
        org_id: str,
        student_id: str,
        supervisor_id: str,
        program_id: str,
        research_area: str,
        co_supervisor_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict:
        # Check supervisor load
        max_scholars = policy_engine.get_value(
            "phd.supervisor_max_scholars", org_id, default=8
        )
        current_load = execute_query(
            """
            SELECT COUNT(*) AS cnt
            FROM phd_registrations
            WHERE org_id = %s
              AND supervisor_id = %s
              AND status NOT IN ('AWARDED', 'WITHDRAWN', 'EXPELLED')
            """,
            (org_id, supervisor_id),
        )
        load_count = current_load[0]["cnt"] if current_load else 0
        if load_count >= max_scholars:
            raise BusinessRuleViolation("Supervisor has reached maximum scholar load")

        phd_id = str(uuid4())
        now = datetime.now(timezone.utc)
        interval_months = policy_engine.get_value(
            "phd.dc_meeting_interval_months", org_id, default=6
        )
        first_dc_due = now + timedelta(days=interval_months * 30)

        ops = []

        # Insert registration
        ops.append(
            (
                """
            INSERT INTO phd_registrations
                (id, org_id, student_id, supervisor_id, co_supervisor_id,
                 program_id, research_area, status, registered_at,
                 next_dc_meeting_due, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    phd_id,
                    org_id,
                    student_id,
                    supervisor_id,
                    co_supervisor_id,
                    program_id,
                    research_area,
                    PhDStatus.REGISTERED.value,
                    now.isoformat(),
                    first_dc_due.isoformat(),
                    actor_id,
                ),
            )
        )

        # Create all 9 milestones as PENDING
        for milestone in MilestoneType:
            ops.append(
                (
                    """
                INSERT INTO phd_milestones
                    (id, phd_id, org_id, milestone_type, status, due_date)
                VALUES (%s, %s, %s, %s, 'PENDING', NULL)
                """,
                    (str(uuid4()), phd_id, org_id, milestone.value),
                )
            )

        execute_transaction(ops)
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="phd_scholar",
            entity_id="",
            tenant_id="",
            metadata={"source": "register_scholar"},
        )

        # Fire domain event
        event = DomainEvent(
            event_type="phd.registered",
            org_id=org_id,
            payload={
                "student_id": student_id,
                "supervisor_id": supervisor_id,
                "program_id": program_id,
            },
            entity_type="phd_registration",
            entity_id=phd_id,
        )
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(DomainEventBus.publish(event))
            else:
                loop.run_until_complete(DomainEventBus.publish(event))
        except RuntimeError:
            pass

        return cls.get_scholar(phd_id, org_id)

    @classmethod
    def complete_milestone(
        cls,
        phd_id: str,
        milestone_type: str,
        org_id: str,
        actor_id: str,
        notes: str | None = None,
    ) -> dict:
        # Fetch registration
        rows = execute_query(
            "SELECT * FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"PhD registration {phd_id} not found")
        reg = rows[0]

        current_status = PhDStatus(reg["status"])
        if current_status in _TERMINAL_STATUSES:
            raise BusinessRuleViolation(
                f"Cannot complete milestone: registration is in terminal status '{current_status.value}'"
            )

        # Fetch milestone
        milestone_rows = execute_query(
            """
            SELECT * FROM phd_milestones
            WHERE phd_id = %s AND org_id = %s AND milestone_type = %s
            """,
            (phd_id, org_id, milestone_type),
        )
        if not milestone_rows:
            raise NotFoundError(
                f"Milestone '{milestone_type}' not found for PhD {phd_id}"
            )

        now = datetime.now(timezone.utc).isoformat()
        mt = MilestoneType(milestone_type)
        next_status = _MILESTONE_STATUS_MAP.get(mt)

        ops = [
            (
                """
            UPDATE phd_milestones
            SET status = 'COMPLETED',
                completed_at = %s,
                completed_by = %s,
                notes = %s
            WHERE phd_id = %s AND org_id = %s AND milestone_type = %s
            """,
                (now, actor_id, notes, phd_id, org_id, milestone_type),
            )
        ]

        if next_status is not None:
            ops.append(
                (
                    """
                UPDATE phd_registrations
                SET status = %s, updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (next_status.value, now, phd_id, org_id),
                )
            )

        execute_transaction(ops)
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="phd_milestone",
            entity_id="",
            tenant_id="",
            metadata={"source": "complete_milestone"},
        )

        # Fire event
        event = DomainEvent(
            event_type="phd.milestone_completed",
            org_id=org_id,
            payload={
                "phd_id": phd_id,
                "milestone_type": milestone_type,
                "org_id": org_id,
            },
            entity_type="phd_milestone",
            entity_id=phd_id,
        )
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(DomainEventBus.publish(event))
            else:
                loop.run_until_complete(DomainEventBus.publish(event))
        except RuntimeError:
            pass

        updated = execute_query(
            """
            SELECT * FROM phd_milestones
            WHERE phd_id = %s AND org_id = %s AND milestone_type = %s
            """,
            (phd_id, org_id, milestone_type),
        )
        return updated[0] if updated else {}

    @classmethod
    def schedule_dc_meeting(
        cls,
        phd_id: str,
        org_id: str,
        scheduled_at_iso: str,
        committee_members: list,
        agenda: str,
        actor_id: str,
    ) -> dict:
        # Verify registration exists
        rows = execute_query(
            "SELECT id FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"PhD registration {phd_id} not found")

        meeting_id = str(uuid4())
        interval_months = policy_engine.get_value(
            "phd.dc_meeting_interval_months", org_id, default=6
        )
        scheduled_dt = datetime.fromisoformat(scheduled_at_iso.replace("Z", "+00:00"))
        next_due = scheduled_dt + timedelta(days=interval_months * 30)

        import json

        execute_transaction(
            [
                (
                    """
                INSERT INTO phd_dc_meetings
                    (id, phd_id, org_id, scheduled_at, committee_members,
                     agenda, status, next_meeting_due, created_by)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'SCHEDULED', %s, %s)
                """,
                    (
                        meeting_id,
                        phd_id,
                        org_id,
                        scheduled_at_iso,
                        json.dumps(committee_members),
                        agenda,
                        next_due.isoformat(),
                        actor_id,
                    ),
                ),
                (
                    """
                UPDATE phd_registrations
                SET next_dc_meeting_due = %s, updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        next_due.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                        phd_id,
                        org_id,
                    ),
                ),
            ]
        )
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="dc_meeting",
            entity_id="",
            tenant_id="",
            metadata={"source": "schedule_dc_meeting"},
        )

        result = execute_query(
            "SELECT * FROM phd_dc_meetings WHERE id = %s AND org_id = %s",
            (meeting_id, org_id),
        )
        return result[0] if result else {}

    @classmethod
    def record_dc_outcome(
        cls,
        meeting_id: str,
        org_id: str,
        outcome: str,
        minutes: str,
        actor_id: str,
    ) -> dict:
        rows = execute_query(
            "SELECT * FROM phd_dc_meetings WHERE id = %s AND org_id = %s",
            (meeting_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"DC meeting {meeting_id} not found")

        now = datetime.now(timezone.utc).isoformat()
        execute_transaction(
            [
                (
                    """
            UPDATE phd_dc_meetings
            SET held_at = %s,
                outcome = %s,
                minutes = %s,
                status = 'HELD',
                updated_by = %s
            WHERE id = %s AND org_id = %s
            """,
                    (now, outcome, minutes, actor_id, meeting_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="dc_meeting",
            entity_id="",
            tenant_id="",
            metadata={"source": "record_dc_outcome"},
        )

        if outcome == "CRITICAL":
            meeting = rows[0]
            event = DomainEvent(
                event_type="phd.dc_meeting_critical",
                org_id=org_id,
                payload={
                    "meeting_id": meeting_id,
                    "phd_id": meeting["phd_id"],
                    "outcome": outcome,
                },
                entity_type="phd_dc_meeting",
                entity_id=meeting_id,
            )
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(DomainEventBus.publish(event))
                else:
                    loop.run_until_complete(DomainEventBus.publish(event))
            except RuntimeError:
                pass

        updated = execute_query(
            "SELECT * FROM phd_dc_meetings WHERE id = %s AND org_id = %s",
            (meeting_id, org_id),
        )
        return updated[0] if updated else {}

    @classmethod
    def get_scholar(cls, phd_id: str, org_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"PhD registration {phd_id} not found")
        reg = dict(rows[0])

        milestones = execute_query(
            """
            SELECT * FROM phd_milestones
            WHERE phd_id = %s AND org_id = %s
            ORDER BY milestone_type
            """,
            (phd_id, org_id),
        )
        reg["milestones"] = [dict(m) for m in milestones]

        plagiarism = execute_query(
            """
            SELECT * FROM phd_plagiarism_reports
            WHERE phd_id = %s AND org_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phd_id, org_id),
        )
        reg["latest_plagiarism_report"] = dict(plagiarism[0]) if plagiarism else None

        dc_meeting = execute_query(
            """
            SELECT * FROM phd_dc_meetings
            WHERE phd_id = %s AND org_id = %s
            ORDER BY scheduled_at DESC
            LIMIT 1
            """,
            (phd_id, org_id),
        )
        reg["latest_dc_meeting"] = dict(dc_meeting[0]) if dc_meeting else None

        return reg

    @classmethod
    def list_scholars(
        cls,
        org_id: str,
        status: str | None = None,
        supervisor_id: str | None = None,
        program_id: str | None = None,
    ) -> list:
        conditions = ["pr.org_id = %s"]
        params: list = [org_id]

        if status:
            conditions.append("pr.status = %s")
            params.append(status)
        if supervisor_id:
            conditions.append("pr.supervisor_id = %s")
            params.append(supervisor_id)
        if program_id:
            conditions.append("pr.program_id = %s")
            params.append(program_id)

        where = " AND ".join(conditions)
        sql = f"""  # noqa: S608
            SELECT
                pr.*,
                COALESCE(su.name, pr.student_id::text)       AS student_name,
                COALESCE(sp.name, pr.supervisor_id::text)    AS supervisor_name,
                COALESCE(mc.completed_count, 0)::int         AS milestones_complete,
                COALESCE(mt.total_count, 9)::int             AS total_milestones
            FROM phd_registrations pr
            LEFT JOIN users su ON su.id = pr.student_id
            LEFT JOIN users sp ON sp.id = pr.supervisor_id
            LEFT JOIN (
                SELECT phd_id, COUNT(*) AS completed_count
                FROM phd_milestones WHERE status = 'COMPLETE'
                GROUP BY phd_id
            ) mc ON mc.phd_id = pr.id
            LEFT JOIN (
                SELECT phd_id, COUNT(*) AS total_count
                FROM phd_milestones GROUP BY phd_id
            ) mt ON mt.phd_id = pr.id
            WHERE {where}
            ORDER BY pr.created_at DESC
        """
        rows = execute_query(sql, tuple(params))
        return [dict(r) for r in rows]

    @classmethod
    def submit_thesis(
        cls,
        phd_id: str,
        org_id: str,
        thesis_document_url: str,
        examiner_1_id: str,
        examiner_2_id: str,
        external_examiner_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict:
        # Verify registration
        rows = execute_query(
            "SELECT * FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"PhD registration {phd_id} not found")

        # Check plagiarism status
        plag_rows = execute_query(
            """
            SELECT status FROM phd_plagiarism_reports
            WHERE phd_id = %s AND org_id = %s AND status = 'PASSED'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phd_id, org_id),
        )
        if not plag_rows:
            raise BusinessRuleViolation(
                "Thesis submission blocked: plagiarism check not passed"
            )

        now = datetime.now(timezone.utc).isoformat()
        submission_id = str(uuid4())

        execute_transaction(
            [
                (
                    """
                UPDATE phd_registrations
                SET status = %s, updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (PhDStatus.THESIS_SUBMITTED.value, now, phd_id, org_id),
                ),
                (
                    """
                INSERT INTO phd_thesis_submissions
                    (id, phd_id, org_id, thesis_document_url,
                     examiner_1_id, examiner_2_id, external_examiner_id,
                     status, submitted_at, submitted_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'SUBMITTED', %s, %s)
                """,
                    (
                        submission_id,
                        phd_id,
                        org_id,
                        thesis_document_url,
                        examiner_1_id,
                        examiner_2_id,
                        external_examiner_id,
                        now,
                        actor_id,
                    ),
                ),
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="phd_thesis",
            entity_id="",
            tenant_id="",
            metadata={"source": "submit_thesis"},
        )

        event = DomainEvent(
            event_type="phd.thesis_submitted",
            org_id=org_id,
            payload={
                "phd_id": phd_id,
                "org_id": org_id,
                "examiner_1_id": examiner_1_id,
                "examiner_2_id": examiner_2_id,
            },
            entity_type="phd_thesis_submission",
            entity_id=submission_id,
        )
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(DomainEventBus.publish(event))
            else:
                loop.run_until_complete(DomainEventBus.publish(event))
        except RuntimeError:
            pass

        result = execute_query(
            "SELECT * FROM phd_thesis_submissions WHERE id = %s AND org_id = %s",
            (submission_id, org_id),
        )
        return dict(result[0]) if result else {}

    @classmethod
    def award_degree(
        cls,
        phd_id: str,
        org_id: str,
        actor_id: str,
    ) -> dict:
        # Verify registration
        rows = execute_query(
            "SELECT * FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"PhD registration {phd_id} not found")

        # Check viva outcome: thesis submission must be approved (viva_outcome = 'PASS')
        thesis_rows = execute_query(
            """
            SELECT id FROM phd_thesis_submissions
            WHERE phd_id = %s AND org_id = %s AND viva_outcome = 'PASS'
            ORDER BY submitted_at DESC
            LIMIT 1
            """,
            (phd_id, org_id),
        )
        if not thesis_rows:
            raise BusinessRuleViolation(
                "Degree award blocked: viva voce has not been passed"
            )

        now = datetime.now(timezone.utc).isoformat()
        execute_transaction(
            [
                (
                    """
            UPDATE phd_registrations
            SET status = %s, awarded_at = %s, updated_at = %s
            WHERE id = %s AND org_id = %s
            """,
                    (PhDStatus.AWARDED.value, now, now, phd_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="phd_scholar",
            entity_id="",
            tenant_id="",
            metadata={"source": "award_degree"},
        )

        event = DomainEvent(
            event_type="phd.degree_awarded",
            org_id=org_id,
            payload={"phd_id": phd_id, "org_id": org_id},
            entity_type="phd_registration",
            entity_id=phd_id,
        )
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(DomainEventBus.publish(event))
            else:
                loop.run_until_complete(DomainEventBus.publish(event))
        except RuntimeError:
            pass

        updated = execute_query(
            "SELECT * FROM phd_registrations WHERE id = %s AND org_id = %s",
            (phd_id, org_id),
        )
        return dict(updated[0]) if updated else {}
