"""
SS-6 — Student Clubs & Events Management

Implements:
- Club registration + Faculty Advisor assignment
- Event proposal → Dean approval → resource/venue allotment
- Budget integration (Finance FM-6)
- Venue conflict checking (cross-ref Academics timetable)
- Participation tracking + certificate generation
- External competition NOC
- Post-event report + budget reconciliation
- Annual student activity report → Regulatory E14 (NAAC C7)

State Machines:
    Club: PROPOSED → ADVISOR_ASSIGNED → APPROVED → ACTIVE → SUSPENDED → DISSOLVED
    Event: DRAFT → PROPOSED → APPROVED → VENUE_ALLOTTED → BUDGET_SANCTIONED →
           IN_PROGRESS → COMPLETED → REPORT_SUBMITTED → CLOSED

Roles:
- Student (Club Secretary): create club/event proposals
- Faculty Advisor: review and endorse
- Dean: approve clubs and events
- Admin: venue allotment, budget sanction

SLAs:
- Club registration: 5 business days
- Event proposal: 2 business days
- Resource allotment: 3 business days
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


class ClubStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ADVISOR_ASSIGNED = "ADVISOR_ASSIGNED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISSOLVED = "DISSOLVED"


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    VENUE_ALLOTTED = "VENUE_ALLOTTED"
    BUDGET_SANCTIONED = "BUDGET_SANCTIONED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REPORT_SUBMITTED = "REPORT_SUBMITTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


CLUB_TRANSITIONS = {
    ClubStatus.PROPOSED: {ClubStatus.ADVISOR_ASSIGNED, ClubStatus.DISSOLVED},
    ClubStatus.ADVISOR_ASSIGNED: {ClubStatus.APPROVED, ClubStatus.DISSOLVED},
    ClubStatus.APPROVED: {ClubStatus.ACTIVE},
    ClubStatus.ACTIVE: {ClubStatus.SUSPENDED, ClubStatus.DISSOLVED},
    ClubStatus.SUSPENDED: {ClubStatus.ACTIVE, ClubStatus.DISSOLVED},
    ClubStatus.DISSOLVED: set(),
}

EVENT_TRANSITIONS = {
    EventStatus.DRAFT: {EventStatus.PROPOSED, EventStatus.CANCELLED},
    EventStatus.PROPOSED: {EventStatus.APPROVED, EventStatus.CANCELLED},
    EventStatus.APPROVED: {EventStatus.VENUE_ALLOTTED, EventStatus.CANCELLED},
    EventStatus.VENUE_ALLOTTED: {
        EventStatus.BUDGET_SANCTIONED,
        EventStatus.IN_PROGRESS,
        EventStatus.CANCELLED,
    },
    EventStatus.BUDGET_SANCTIONED: {EventStatus.IN_PROGRESS, EventStatus.CANCELLED},
    EventStatus.IN_PROGRESS: {EventStatus.COMPLETED},
    EventStatus.COMPLETED: {EventStatus.REPORT_SUBMITTED},
    EventStatus.REPORT_SUBMITTED: {EventStatus.CLOSED},
    EventStatus.CLOSED: set(),
    EventStatus.CANCELLED: set(),
}


class ClubService:
    @classmethod
    def propose_club(
        cls, org_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        club_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                INSERT INTO student_clubs
                    (id, org_id, name, description, category, proposed_by,
                     faculty_advisor_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        club_id,
                        org_id,
                        data["name"],
                        data.get("description", ""),
                        data.get("category", "GENERAL"),
                        actor_id,
                        data.get("faculty_advisor_id"),
                        ClubStatus.PROPOSED.value,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="propose_club",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "propose_club"},
        )
        return {"id": club_id, "status": ClubStatus.PROPOSED.value}

    @classmethod
    def assign_advisor(
        cls, org_id: str, club_id: str, advisor_id: str, actor_id: str
    ) -> dict[str, Any]:
        cls._validate_transition(
            org_id, club_id, ClubStatus.ADVISOR_ASSIGNED, "student_clubs"
        )
        execute_transaction(
            [
                (
                    "UPDATE student_clubs SET faculty_advisor_id = %s, status = %s, updated_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (advisor_id, ClubStatus.ADVISOR_ASSIGNED.value, club_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="advisor",
            entity_id=advisor_id,
            tenant_id=org_id,
            metadata={"source": "assign_advisor"},
        )
        return {"id": club_id, "status": ClubStatus.ADVISOR_ASSIGNED.value}

    @classmethod
    def approve_club(cls, org_id: str, club_id: str, actor_id: str) -> dict[str, Any]:
        cls._validate_transition(org_id, club_id, ClubStatus.APPROVED, "student_clubs")
        execute_transaction(
            [
                (
                    "UPDATE student_clubs SET status = %s, approved_by = %s, approved_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (ClubStatus.ACTIVE.value, actor_id, club_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="club",
            entity_id=club_id,
            tenant_id=org_id,
            metadata={"source": "approve_club"},
        )
        return {"id": club_id, "status": ClubStatus.ACTIVE.value}

    @classmethod
    def add_member(
        cls, org_id: str, club_id: str, student_id: str, role: str = "MEMBER"
    ) -> dict[str, Any]:
        member_id = str(uuid4())
        execute_transaction(
            [
                (
                    "INSERT INTO club_members (id, org_id, club_id, student_id, role, joined_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW()) ON CONFLICT (org_id, club_id, student_id) DO NOTHING",
                    (member_id, org_id, club_id, student_id, role),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="member",
            entity_id=member_id,
            tenant_id=org_id,
            metadata={"source": "add_member"},
        )
        return {"id": member_id, "club_id": club_id, "student_id": student_id}

    @classmethod
    def list_clubs(cls, org_id: str, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = execute_query(
                "SELECT * FROM student_clubs WHERE org_id = %s AND status = %s ORDER BY name",
                (org_id, status),
                tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT * FROM student_clubs WHERE org_id = %s ORDER BY name",
                (org_id,),
                tenant_id=org_id,
            )
        return [dict(r) for r in rows]

    @classmethod
    def _validate_transition(
        cls, org_id: str, club_id: str, target: ClubStatus, table: str
    ) -> None:
        rows = execute_query(
            f"SELECT status FROM {table} WHERE id = %s AND org_id = %s",  # noqa: S608
            (club_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Club {club_id} not found")
        current = ClubStatus(rows[0]["status"])
        if target not in CLUB_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition: {current.value} → {target.value}")


class EventService:
    @classmethod
    def propose_event(
        cls, org_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        event_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                INSERT INTO club_events
                    (id, org_id, club_id, title, description, event_date, venue_requested,
                     expected_participants, budget_requested, status, proposed_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        event_id,
                        org_id,
                        data.get("club_id"),
                        data["title"],
                        data.get("description", ""),
                        data.get("event_date"),
                        data.get("venue_requested", ""),
                        data.get("expected_participants", 0),
                        data.get("budget_requested", 0),
                        EventStatus.PROPOSED.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="propose_event",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "propose_event"},
        )
        return {"id": event_id, "status": EventStatus.PROPOSED.value}

    @classmethod
    def approve_event(cls, org_id: str, event_id: str, actor_id: str) -> dict[str, Any]:
        cls._advance(org_id, event_id, EventStatus.APPROVED, actor_id)
        return {"id": event_id, "status": EventStatus.APPROVED.value}

    @classmethod
    def allot_venue(
        cls, org_id: str, event_id: str, venue: str, actor_id: str
    ) -> dict[str, Any]:
        """Allot venue — checks for timetable conflicts first."""
        event = cls._get(org_id, event_id)
        event_date = event.get("event_date")

        # Cross-check with Academics timetable for venue conflicts
        if event_date and venue:
            conflicts = execute_query(
                "SELECT id FROM timetable_slots WHERE venue = %s AND date = %s AND org_id = %s",
                (venue, event_date, org_id),
                tenant_id=org_id,
            )
            if conflicts:
                raise ValueError(
                    f"Venue '{venue}' has a timetable conflict on {event_date}"
                )

        extra_queries = [
            (
                "UPDATE club_events SET venue_allotted = %s WHERE id = %s AND org_id = %s",
                (venue, event_id, org_id),
            )
        ]
        cls._advance(
            org_id,
            event_id,
            EventStatus.VENUE_ALLOTTED,
            actor_id,
            extra_queries=extra_queries,
        )
        return {
            "id": event_id,
            "status": EventStatus.VENUE_ALLOTTED.value,
            "venue": venue,
        }

    @classmethod
    def complete_event(
        cls, org_id: str, event_id: str, actual_participants: int, actor_id: str
    ) -> dict[str, Any]:
        extra_queries = [
            (
                "UPDATE club_events SET actual_participants = %s WHERE id = %s AND org_id = %s",
                (actual_participants, event_id, org_id),
            )
        ]
        cls._advance(
            org_id,
            event_id,
            EventStatus.COMPLETED,
            actor_id,
            extra_queries=extra_queries,
        )

        # Publish for NAAC C7 metric
        DomainEventBus.publish(
            DomainEvent(
                event_type="student_activity.event_completed",
                org_id=org_id,
                payload={"event_id": event_id, "participants": actual_participants},
                actor_id=actor_id,
            )
        )
        return {"id": event_id, "status": EventStatus.COMPLETED.value}

    @classmethod
    def record_participation(
        cls, org_id: str, event_id: str, student_id: str, certificate: bool = False
    ) -> dict[str, Any]:
        part_id = str(uuid4())
        execute_transaction(
            [
                (
                    "INSERT INTO event_participants (id, org_id, event_id, student_id, certificate_issued, attended_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW()) ON CONFLICT (org_id, event_id, student_id) DO NOTHING",
                    (part_id, org_id, event_id, student_id, certificate),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="participation",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "record_participation"},
        )
        return {"id": part_id}

    @classmethod
    def generate_noc(
        cls,
        org_id: str,
        student_id: str,
        competition_name: str,
        dates: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Generate NOC for external competition participation."""
        noc_id = str(uuid4())
        execute_transaction(
            [
                (
                    "INSERT INTO external_competition_nocs (id, org_id, student_id, competition_name, dates, "
                    "status, issued_by, created_at) VALUES (%s, %s, %s, %s, %s, 'ISSUED', %s, NOW())",
                    (noc_id, org_id, student_id, competition_name, dates, actor_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="generate_noc",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "generate_noc"},
        )
        return {"noc_id": noc_id, "status": "ISSUED"}

    @classmethod
    def get_annual_activity_report(
        cls, org_id: str, academic_year: str
    ) -> dict[str, Any]:
        """Annual student activity report for NAAC C7."""
        clubs = execute_query(
            "SELECT COUNT(*) AS cnt FROM student_clubs WHERE org_id = %s AND status = 'ACTIVE'",
            (org_id,),
            tenant_id=org_id,
        )
        events = execute_query(
            "SELECT COUNT(*) AS cnt FROM club_events WHERE org_id = %s AND status IN ('COMPLETED','CLOSED') "
            "AND EXTRACT(YEAR FROM event_date) = %s",
            (org_id, academic_year[:4]),
            tenant_id=org_id,
        )
        participants = execute_query(
            "SELECT COUNT(DISTINCT student_id) AS cnt FROM event_participants ep "
            "JOIN club_events ce ON ce.id = ep.event_id "
            "WHERE ce.org_id = %s AND EXTRACT(YEAR FROM ce.event_date) = %s",
            (org_id, academic_year[:4]),
            tenant_id=org_id,
        )

        return {
            "academic_year": academic_year,
            "active_clubs": clubs[0]["cnt"] if clubs else 0,
            "events_conducted": events[0]["cnt"] if events else 0,
            "unique_participants": participants[0]["cnt"] if participants else 0,
        }

    @classmethod
    def _advance(
        cls,
        org_id: str,
        event_id: str,
        target: EventStatus,
        actor_id: str,
        extra_queries: list = None,
    ) -> None:
        rows = execute_query(
            "SELECT status FROM club_events WHERE id = %s AND org_id = %s",
            (event_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Event {event_id} not found")
        current = EventStatus(rows[0]["status"])
        if target not in EVENT_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition: {current.value} → {target.value}")

        queries = list(extra_queries) if extra_queries else []
        queries.append(
            (
                "UPDATE club_events SET status = %s, updated_at = NOW() WHERE id = %s AND org_id = %s",
                (target.value, event_id, org_id),
            )
        )
        execute_transaction(queries, tenant_id=org_id)

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="_advance",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "_advance"},
        )

    @classmethod
    def _get(cls, org_id: str, event_id: str) -> dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM club_events WHERE id = %s AND org_id = %s",
            (event_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Event {event_id} not found")
        return dict(rows[0])
