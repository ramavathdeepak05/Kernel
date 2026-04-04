"""
TA Assignment Service

Implements delegated attendance authority:
  - Faculty assigns ONE OR MORE students as TAs for a course (semester-long) or a specific session.
  - Multiple TAs can be active simultaneously — adding a new TA does NOT revoke existing ones.
  - Faculty can revoke individual TAs at any time via assignment ID.
  - Scope is chosen by faculty at assignment time: COURSE (all sessions) or SESSION (one session).
  - TA must be an enrolled student in the course (enrollment check enforced at assignment).
  - All changes emit domain events that trigger WhatsApp/SMS notifications.
  - Audit trail: attendance sessions record initiated_by (TA) + on_behalf_of (faculty).

Authorization hierarchy (checked in order):
  1. User is the course faculty → allow
  2. User has active course-level TA for this course → allow
  3. User has active session-level TA for this specific session → allow
  4. → 403
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from server.db_service import execute_query, execute_transaction
from server.core.domain_events import DomainEventBus
from server.core.state_registry import StateRegistry

logger = logging.getLogger(__name__)


class _TAStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


# Register TA assignment state machine: ACTIVE is the only state that can
# transition to REVOKED (terminal state — cannot be un-revoked).
StateRegistry.register_entity(
    "ta_assignment",
    {_TAStatus.ACTIVE: {_TAStatus.REVOKED}},
)


def _revoke_ta(table: str, where_col: str, where_val: str, actor_id: str) -> None:
    """Validate ACTIVE→REVOKED through StateRegistry then write the transition."""
    result = StateRegistry.validate_transition(
        "ta_assignment", _TAStatus.ACTIVE, _TAStatus.REVOKED
    )
    if not result.allowed:
        raise ValueError(result.reason)
    new_status = _TAStatus.REVOKED.value
    from server.db_service import safe_identifier
    execute_transaction([(
        f"UPDATE {safe_identifier(table)} SET status=%s, revoked_at=NOW(), revoked_by=%s WHERE {safe_identifier(where_col)}=%s AND status=%s",
        (new_status, actor_id, where_val, _TAStatus.ACTIVE.value),
    )])


class TAAssignmentService:

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_student(tenant_id: str, identifier: str) -> dict:
        """Resolve student by ID or email. Raises ValueError if not found."""
        rows = execute_query(
            """
            SELECT s.id AS student_id, u.full_name, u.email,
                   u.phone, u.whatsapp_number, s.roll_number
            FROM students s
            JOIN users u ON u.id = s.user_id
            WHERE s.tenant_id = $1
              AND (s.id::text = $2 OR u.email = $2 OR s.roll_number = $2)
            LIMIT 1
            """,
            (tenant_id, identifier),
        )
        if not rows:
            raise ValueError(f"Student not found: {identifier}")
        return dict(rows[0])

    @staticmethod
    def _get_course(tenant_id: str, course_id: str) -> dict:
        rows = execute_query(
            "SELECT id, code, name, faculty_id FROM courses WHERE id=$1 AND tenant_id=$2",
            (course_id, tenant_id),
        )
        if not rows:
            raise ValueError(f"Course {course_id} not found")
        return dict(rows[0])

    @staticmethod
    def _get_faculty_name(faculty_id: str) -> str:
        rows = execute_query(
            "SELECT full_name FROM users WHERE id=$1", (faculty_id,)
        )
        return rows[0]["full_name"] if rows else "Faculty"

    # ── course-level TA ──────────────────────────────────────────────────────

    @staticmethod
    def _check_enrollment(course_id: str, student_id: str) -> None:
        """Raise ValueError if student is not actively enrolled in the course."""
        rows = execute_query(
            """
            SELECT 1 FROM course_enrollments
            WHERE course_id=$1 AND student_id=$2 AND status='ACTIVE'
            """,
            (course_id, student_id),
        )
        if not rows:
            raise ValueError(
                "Student must be actively enrolled in this course to be assigned as TA"
            )

    @staticmethod
    def assign_course_ta(
        tenant_id: str,
        course_id: str,
        faculty_id: str,
        student_identifier: str,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Assign a student as course-level TA (semester-long, all sessions).
        Multiple TAs can be active simultaneously — existing TAs are NOT revoked.
        Student must be enrolled in the course.
        student_identifier: student UUID, roll number, or email.
        """
        course = TAAssignmentService._get_course(tenant_id, course_id)

        if str(course["faculty_id"]) != str(faculty_id):
            raise PermissionError("Only the course faculty can assign a TA")

        student = TAAssignmentService._resolve_student(tenant_id, student_identifier)
        student_id = student["student_id"]

        # Enrollment check — TA must be enrolled in the course
        TAAssignmentService._check_enrollment(course_id, student_id)

        # Prevent duplicate active assignment for the same student
        already = execute_query(
            """
            SELECT id FROM course_ta_assignments
            WHERE course_id=$1 AND student_id=$2 AND status='ACTIVE'
            """,
            (course_id, student_id),
        )
        if already:
            raise ValueError("This student is already an active TA for this course")

        execute_transaction([(
            """
            INSERT INTO course_ta_assignments
                (tenant_id, course_id, faculty_id, student_id, assigned_by, notes)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            (tenant_id, course_id, faculty_id, student_id, faculty_id, notes),
        )])

        new_row = execute_query(
            """
            SELECT id FROM course_ta_assignments
            WHERE course_id=$1 AND student_id=$2 AND status='ACTIVE'
            ORDER BY assigned_at DESC LIMIT 1
            """,
            (course_id, student_id),
        )
        assignment_id = str(new_row[0]["id"]) if new_row else None
        faculty_name = TAAssignmentService._get_faculty_name(faculty_id)

        DomainEventBus.publish(
            "attendance.ta_assigned",
            {
                "assignment_id": assignment_id,
                "scope": "COURSE",
                "tenant_id": tenant_id,
                "course_id": course_id,
                "course_code": course["code"],
                "course_name": course["name"],
                "faculty_id": faculty_id,
                "faculty_name": faculty_name,
                "student_id": student_id,
                "student_name": student["full_name"],
                "phone": student.get("whatsapp_number") or student.get("phone"),
            },
        )

        logger.info(
            "course_ta_assigned course=%s student=%s by_faculty=%s",
            course_id, student_id, faculty_id,
        )
        return {
            "assignment_id": assignment_id,
            "scope": "COURSE",
            "course_id": course_id,
            "course_code": course["code"],
            "student_id": student_id,
            "student_name": student["full_name"],
            "roll_number": student.get("roll_number"),
            "status": "ACTIVE",
        }

    @staticmethod
    def revoke_course_ta(
        tenant_id: str,
        course_id: str,
        assignment_id: str,
        faculty_id: str,
    ) -> dict:
        """Revoke a course-level TA assignment."""
        rows = execute_query(
            """
            SELECT cta.*, u.full_name, u.phone, u.whatsapp_number,
                   c.code AS course_code, c.name AS course_name
            FROM course_ta_assignments cta
            JOIN students s ON s.id = cta.student_id
            JOIN users u ON u.id = s.user_id
            JOIN courses c ON c.id = cta.course_id
            WHERE cta.id=$1 AND cta.course_id=$2 AND cta.status='ACTIVE'
            """,
            (assignment_id, course_id),
        )
        if not rows:
            raise ValueError("Active TA assignment not found")

        row = rows[0]
        if str(row["faculty_id"]) != str(faculty_id):
            raise PermissionError("Only the assigning faculty can revoke this TA")

        _revoke_ta("course_ta_assignments", "id", assignment_id, faculty_id)

        DomainEventBus.publish(
            "attendance.ta_revoked",
            {
                "scope": "COURSE",
                "tenant_id": tenant_id,
                "course_id": course_id,
                "course_code": row["course_code"],
                "course_name": row["course_name"],
                "student_id": str(row["student_id"]),
                "phone": row.get("whatsapp_number") or row.get("phone"),
                "revoked_by": faculty_id,
            },
        )

        return {"assignment_id": assignment_id, "status": "REVOKED"}

    @staticmethod
    def list_course_tas(tenant_id: str, course_id: str, faculty_id: str) -> list:
        """List all active course-level TAs for a course."""
        rows = execute_query(
            """
            SELECT cta.id, cta.status, cta.assigned_at, cta.notes,
                   s.id AS student_id, s.roll_number,
                   u.full_name, u.email
            FROM course_ta_assignments cta
            JOIN students s ON s.id = cta.student_id
            JOIN users u ON u.id = s.user_id
            WHERE cta.course_id=$1 AND cta.tenant_id=$2 AND cta.status='ACTIVE'
            ORDER BY cta.assigned_at DESC
            """,
            (course_id, tenant_id),
        )
        return [dict(r) for r in rows]

    # ── session-level TA ─────────────────────────────────────────────────────

    @staticmethod
    def assign_session_ta(
        tenant_id: str,
        course_id: str,
        session_ref: str,
        session_type: str,
        faculty_id: str,
        student_identifier: str,
    ) -> dict:
        """
        Assign a TA for one specific attendance session.
        Multiple TAs can be active for the same session — existing ones are NOT revoked.
        Student must be enrolled in the course.
        """
        course = TAAssignmentService._get_course(tenant_id, course_id)
        if str(course["faculty_id"]) != str(faculty_id):
            raise PermissionError("Only the course faculty can assign a session TA")

        student = TAAssignmentService._resolve_student(tenant_id, student_identifier)
        student_id = student["student_id"]

        # Enrollment check
        TAAssignmentService._check_enrollment(course_id, student_id)

        # Prevent duplicate active assignment for same student + session
        already = execute_query(
            """
            SELECT id FROM session_ta_assignments
            WHERE session_ref=$1 AND student_id=$2 AND status='ACTIVE'
            """,
            (session_ref, student_id),
        )
        if already:
            raise ValueError("This student is already an active TA for this session")

        execute_transaction([(
            """
            INSERT INTO session_ta_assignments
                (tenant_id, course_id, session_ref, session_type,
                 faculty_id, student_id, assigned_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            (tenant_id, course_id, session_ref, session_type,
             faculty_id, student_id, faculty_id),
        )])

        faculty_name = TAAssignmentService._get_faculty_name(faculty_id)

        DomainEventBus.publish(
            "attendance.ta_assigned",
            {
                "scope": "SESSION",
                "tenant_id": tenant_id,
                "course_id": course_id,
                "course_code": course["code"],
                "course_name": course["name"],
                "session_ref": session_ref,
                "session_type": session_type,
                "faculty_id": faculty_id,
                "faculty_name": faculty_name,
                "student_id": student_id,
                "student_name": student["full_name"],
                "phone": student.get("whatsapp_number") or student.get("phone"),
            },
        )

        return {
            "scope": "SESSION",
            "session_ref": session_ref,
            "student_id": student_id,
            "student_name": student["full_name"],
            "status": "ACTIVE",
        }

    @staticmethod
    def revoke_session_ta(
        tenant_id: str,
        session_ref: str,
        faculty_id: str,
    ) -> dict:
        """Revoke all active TAs for a specific session."""
        _revoke_ta("session_ta_assignments", "session_ref", session_ref, faculty_id)
        return {"session_ref": session_ref, "status": "REVOKED"}

    # ── authorization ─────────────────────────────────────────────────────────

    @staticmethod
    def is_authorized(
        user_id: str,
        course_id: str,
        tenant_id: str,
        session_ref: Optional[str] = None,
    ) -> bool:
        """
        Check if user is authorized to take attendance for a course/session.
        Returns True if user is faculty, active course TA, or active session TA.
        """
        # 1. Faculty check
        faculty_rows = execute_query(
            "SELECT 1 FROM courses WHERE id=$1 AND faculty_id=$2 AND tenant_id=$3",
            (course_id, user_id, tenant_id),
        )
        if faculty_rows:
            return True

        # 2. Course-level TA check
        course_ta_rows = execute_query(
            """
            SELECT 1 FROM course_ta_assignments
            WHERE course_id=$1 AND student_id=$2 AND tenant_id=$3 AND status='ACTIVE'
            """,
            (course_id, user_id, tenant_id),
        )
        if course_ta_rows:
            return True

        # 3. Session-level TA check
        if session_ref:
            session_ta_rows = execute_query(
                """
                SELECT 1 FROM session_ta_assignments
                WHERE session_ref=$1 AND student_id=$2 AND status='ACTIVE'
                """,
                (session_ref, user_id),
            )
            if session_ta_rows:
                return True

        return False

    @staticmethod
    def get_ta_courses(student_id: str, tenant_id: str) -> list:
        """
        Get all courses where this student is an active TA.
        Used by the mobile/desktop app to show TA's assignable courses.
        """
        rows = execute_query(
            """
            SELECT DISTINCT c.id AS course_id, c.code, c.name,
                   c.faculty_id,
                   u.full_name AS faculty_name,
                   cta.assigned_at,
                   cta.id AS assignment_id,
                   'COURSE' AS scope
            FROM course_ta_assignments cta
            JOIN courses c ON c.id = cta.course_id
            JOIN users u ON u.id = c.faculty_id
            WHERE cta.student_id=$1 AND cta.tenant_id=$2 AND cta.status='ACTIVE'
            ORDER BY cta.assigned_at DESC
            """,
            (student_id, tenant_id),
        )
        return [dict(r) for r in rows]
