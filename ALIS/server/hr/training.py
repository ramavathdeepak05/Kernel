"""
HR-5 — Training & Development

Implements:
- UGC mandatory training types: Orientation (new faculty), Refresher (every 3 yrs), FDP
- Training program CRUD and enrollment
- 90-day advance reminder for Refresher deadline
- Training effectiveness assessment 3 months post-training
- Training completion → CAS/promotion eligibility update

State Machine:
    Program: PLANNED → OPEN → IN_PROGRESS → COMPLETED → ASSESSED
    Enrollment: REGISTERED → ATTENDED → COMPLETED → CERTIFICATE_ISSUED
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class TrainingType(str, Enum):
    ORIENTATION = "ORIENTATION"     # UGC mandatory for new faculty
    REFRESHER = "REFRESHER"         # UGC mandatory every 3 years
    FDP = "FDP"                     # Faculty Development Programme
    WORKSHOP = "WORKSHOP"
    SEMINAR = "SEMINAR"
    CERTIFICATION = "CERTIFICATION"
    ONLINE = "ONLINE"


class ProgramStatus(str, Enum):
    PLANNED = "PLANNED"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ASSESSED = "ASSESSED"
    CANCELLED = "CANCELLED"


class EnrollmentStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ATTENDED = "ATTENDED"
    COMPLETED = "COMPLETED"
    CERTIFICATE_ISSUED = "CERTIFICATE_ISSUED"
    DROPPED = "DROPPED"


class TrainingService:

    @classmethod
    def create_program(cls, org_id: str, data: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
        program_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO training_programs
                    (id, org_id, title, training_type, description, start_date, end_date,
                     duration_days, max_participants, venue, organizer, status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    program_id, org_id, data["title"],
                    data.get("training_type", TrainingType.FDP.value),
                    data.get("description", ""), data.get("start_date"),
                    data.get("end_date"), data.get("duration_days", 1),
                    data.get("max_participants", 50), data.get("venue", ""),
                    data.get("organizer", ""), ProgramStatus.PLANNED.value,
                    actor_id, now,
                ),
            )
        ], tenant_id=org_id)

        return {"id": program_id, "status": ProgramStatus.PLANNED.value}

    @classmethod
    def enroll(cls, org_id: str, program_id: str, staff_id: str, actor_id: str) -> Dict[str, Any]:
        enrollment_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                """
                INSERT INTO training_enrollments
                    (id, org_id, program_id, staff_id, status, enrolled_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (enrollment_id, org_id, program_id, staff_id,
                 EnrollmentStatus.REGISTERED.value, now),
            )
        ], tenant_id=org_id)
        return {"id": enrollment_id, "status": EnrollmentStatus.REGISTERED.value}

    @classmethod
    def mark_completed(cls, org_id: str, enrollment_id: str, actor_id: str) -> Dict[str, Any]:
        execute_transaction([
            ("UPDATE training_enrollments SET status = %s, completed_at = NOW() "
             "WHERE id = %s AND org_id = %s",
             (EnrollmentStatus.COMPLETED.value, enrollment_id, org_id))
        ], tenant_id=org_id)

        # Publish event for CAS/promotion eligibility
        rows = execute_query(
            "SELECT staff_id, program_id FROM training_enrollments WHERE id = %s AND org_id = %s",
            (enrollment_id, org_id), tenant_id=org_id,
        )
        if rows:
            DomainEventBus.publish(DomainEvent(
                event_type="training.completed",
                org_id=org_id,
                payload={
                    "enrollment_id": enrollment_id,
                    "staff_id": str(rows[0]["staff_id"]),
                    "program_id": str(rows[0]["program_id"]),
                },
                actor_id=actor_id,
            ))

        return {"id": enrollment_id, "status": EnrollmentStatus.COMPLETED.value}

    @classmethod
    def check_refresher_due(cls, org_id: str) -> List[Dict[str, Any]]:
        """
        UGC mandate: Refresher Course every 3 years.
        Returns staff members whose refresher is due within 90 days.
        """
        rows = execute_query(
            """
            SELECT s.id AS staff_id, s.name, s.department,
                   MAX(te.completed_at) AS last_refresher
            FROM staff_profiles s
            LEFT JOIN training_enrollments te
                ON te.staff_id = s.id AND te.org_id = s.org_id AND te.status = 'COMPLETED'
            LEFT JOIN training_programs tp
                ON tp.id = te.program_id AND tp.training_type = 'REFRESHER'
            WHERE s.org_id = %s AND s.status = 'ACTIVE'
            GROUP BY s.id, s.name, s.department
            HAVING MAX(te.completed_at) IS NULL
                OR MAX(te.completed_at) < NOW() - INTERVAL '3 years' + INTERVAL '90 days'
            ORDER BY last_refresher NULLS FIRST
            """,
            (org_id,), tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @classmethod
    def schedule_effectiveness_assessment(cls, org_id: str, program_id: str) -> None:
        """
        Schedule a training effectiveness assessment 3 months after completion.
        Called by beat task or event handler.
        """
        rows = execute_query(
            "SELECT id, end_date FROM training_programs WHERE id = %s AND org_id = %s AND status = 'COMPLETED'",
            (program_id, org_id), tenant_id=org_id,
        )
        if not rows:
            return

        end_date = rows[0]["end_date"]
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)

        assessment_date = end_date + timedelta(days=90)

        execute_transaction([
            (
                """
                INSERT INTO training_assessments
                    (id, org_id, program_id, assessment_type, scheduled_date, status, created_at)
                VALUES (%s, %s, %s, 'EFFECTIVENESS', %s, 'SCHEDULED', NOW())
                ON CONFLICT (org_id, program_id, assessment_type) DO NOTHING
                """,
                (str(uuid4()), org_id, program_id, assessment_date),
            )
        ], tenant_id=org_id)

    @classmethod
    def list_programs(cls, org_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = execute_query(
                "SELECT * FROM training_programs WHERE org_id = %s AND status = %s ORDER BY start_date",
                (org_id, status), tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT * FROM training_programs WHERE org_id = %s ORDER BY start_date DESC",
                (org_id,), tenant_id=org_id,
            )
        return [dict(r) for r in rows]
