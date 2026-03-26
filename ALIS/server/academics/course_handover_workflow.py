"""EC-ACA-02 — Faculty Attrition: Course Handover Workflow

Triggered when a faculty member's separation is initiated during an active
semester.  Must run BEFORE LMS access is revoked (to allow package generation).

Approval chain stored in workflow_definitions — not hardcoded (R2).
SLA stored as absolute TIMESTAMPTZ deadline (R3).

Steps
─────
1. Snapshot CourseHandoverPackage (completed/remaining units, pending assessments)
2. Transition affected courses → INSTRUCTOR_MISSING
3. Transfer LMS ownership to HOD
4. Freeze pending IA auto-releases
5. Assign temporary substitute via workflow approval queue (SLA from policy)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class CourseHandoverPackage(BaseModel):
    faculty_id: str
    course_id: str
    course_code: str
    completed_units: int
    remaining_units: int
    pending_assessments: list
    materials_location: Optional[str]


class CourseHandoverWorkflow:

    @classmethod
    def trigger(cls, faculty_id: str, org_id: str, actor_id: str) -> dict:
        """Trigger the full course handover for a departing faculty member.

        Called by separation.initiated event handler — must run before LMS revocation.
        """
        # SLA: read from policy, store as absolute deadline (R3)
        from datetime import timedelta
        sla_hours = int(policy_engine.get_value(
            "academics.course_handover_sla_hours", org_id, 48
        ))
        sla_deadline = datetime.now(timezone.utc) + timedelta(hours=sla_hours)

        # 1. Find all active courses for this faculty member
        courses = execute_query("""
            SELECT c.id, c.course_code, c.title, c.department_id
            FROM course_assignments ca
            JOIN courses c ON c.id = ca.course_id
            WHERE ca.faculty_id = %s
              AND ca.org_id = %s
              AND ca.status = 'ACTIVE'
        """, (faculty_id, org_id))

        if not courses:
            logger.info("No active courses found for faculty %s", faculty_id)
            return {"faculty_id": faculty_id, "courses_affected": 0}

        handover_id = str(uuid.uuid4())
        packages = []
        ops = []

        for course in courses:
            course_id = str(course["id"])

            # Snapshot package
            package = cls._build_package(faculty_id, course_id, org_id, course)
            packages.append(package.model_dump())

            # 2. Transition course → INSTRUCTOR_MISSING
            ops.append(("""
                UPDATE course_assignments
                SET status = 'INSTRUCTOR_MISSING', updated_at = NOW()
                WHERE course_id = %s AND faculty_id = %s AND org_id = %s
            """, (course_id, faculty_id, org_id)))

            # 4. Freeze pending IA auto-releases for this course
            ops.append(("""
                UPDATE assessment_schedules
                SET auto_release_frozen = TRUE
                WHERE course_id = %s AND org_id = %s AND status = 'SCHEDULED'
            """, (course_id, org_id)))

        # 5. Create approval workflow task for substitute assignment (R2 — no hardcoded chain)
        import json
        ops.append(("""
            INSERT INTO workflow_tasks
                (id, org_id, workflow_type, resource_id, status, created_by,
                 payload, sla_deadline, created_at)
            VALUES (%s, %s, 'COURSE_HANDOVER_SUBSTITUTE', %s, 'PENDING_APPROVAL',
                    %s, %s, %s, NOW())
        """, (
            handover_id, org_id, faculty_id, actor_id,
            json.dumps({
                "faculty_id": faculty_id,
                "courses": [str(c["id"]) for c in courses],
                "packages": packages,
                "sla_hours": sla_hours,
            }),
            sla_deadline,
        )))

        if ops:
            execute_transaction(ops)

        # 3. Transfer LMS ownership to HOD (via domain event — LMS service handles it)
        DomainEventBus.publish(DomainEvent(
            event_type="academics.faculty_lms_transfer_to_hod",
            org_id=org_id,
            payload={
                "faculty_id": faculty_id,
                "course_ids": [str(c["id"]) for c in courses],
                "handover_task_id": handover_id,
            },
        ))

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="course_handover",
            resource_id=handover_id,
            detail={
                "faculty_id": faculty_id,
                "courses_affected": len(courses),
                "sla_deadline": sla_deadline.isoformat(),
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="academics.course_handover_initiated",
            org_id=org_id,
            payload={
                "handover_task_id": handover_id,
                "faculty_id": faculty_id,
                "courses_affected": len(courses),
                "sla_deadline": sla_deadline.isoformat(),
                "packages": packages,
            },
        ))

        logger.info(
            "Course handover triggered for faculty %s: %d courses, SLA %s",
            faculty_id, len(courses), sla_deadline.isoformat(),
        )

        return {
            "handover_task_id": handover_id,
            "faculty_id": faculty_id,
            "courses_affected": len(courses),
            "sla_deadline": sla_deadline.isoformat(),
            "packages": packages,
        }

    @classmethod
    def _build_package(
        cls,
        faculty_id: str,
        course_id: str,
        org_id: str,
        course: dict,
    ) -> CourseHandoverPackage:
        """Snapshot the handover package for a single course."""
        units = execute_query("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                COUNT(*) FILTER (WHERE status != 'COMPLETED') AS remaining
            FROM course_units
            WHERE course_id = %s AND org_id = %s
        """, (course_id, org_id))

        completed = int(units[0]["completed"] or 0) if units else 0
        remaining = int(units[0]["remaining"] or 0) if units else 0

        assessments = execute_query("""
            SELECT id, title, due_date, status
            FROM assessments
            WHERE course_id = %s AND org_id = %s AND status IN ('PENDING', 'DRAFT')
        """, (course_id, org_id))

        return CourseHandoverPackage(
            faculty_id=faculty_id,
            course_id=course_id,
            course_code=str(course.get("course_code", "")),
            completed_units=completed,
            remaining_units=remaining,
            pending_assessments=[dict(a) for a in assessments],
            materials_location=f"lms://course/{course_id}/materials",
        )
