"""
In-house Learning Management Service — P40 (replaces Moodle LMS stub)

Three service groups:
  CourseMaterialService — faculty uploads + AI-generated content per course
                          State: DRAFT → PUBLISHED → ARCHIVED
  AssignmentService     — coursework tasks linked to course outcomes
                          State: DRAFT → PUBLISHED → CLOSED → ARCHIVED
  SubmissionService     — student submissions with full grading lifecycle
                          State: DRAFT → SUBMITTED → UNDER_REVIEW → GRADED → RETURNED

Design:
  - All state transitions validated via StateRegistry (Layer 3 invariant)
  - Domain events published on significant transitions
  - Grade attainment fed back to OBE module via domain event
  - Late-penalty policy read from PolicyStore per org (never hardcoded)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import NotFoundError
from server.core.policy_store import PolicyKey, PolicyStore
from server.core.state_registry import StateRegistry
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine registrations (Layer 3)
# ---------------------------------------------------------------------------
StateRegistry.register_entity(
    "course_material",
    {
        "DRAFT": {"PUBLISHED"},
        "PUBLISHED": {"ARCHIVED"},
        "ARCHIVED": set(),
    },
)
StateRegistry.register_entity(
    "assignment",
    {
        "DRAFT": {"PUBLISHED"},
        "PUBLISHED": {"CLOSED"},
        "CLOSED": {"ARCHIVED"},
        "ARCHIVED": set(),
    },
)
StateRegistry.register_entity(
    "assignment_submission",
    {
        "DRAFT": {"SUBMITTED"},
        "SUBMITTED": {"UNDER_REVIEW"},
        "UNDER_REVIEW": {"GRADED"},
        "GRADED": {"RETURNED"},
        "RETURNED": set(),
    },
)

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


# ---------------------------------------------------------------------------
# CourseMaterialService
# ---------------------------------------------------------------------------


class CourseMaterialService:
    """CRUD + lifecycle for course materials (lecture notes, quizzes, etc.)."""

    @staticmethod
    def create_material(
        org_id: str,
        course_id: str,
        faculty_id: str,
        title: str,
        material_type: str,
        content_body: str | None = None,
        file_url: str | None = None,
        co_id: str | None = None,
        week_number: int | None = None,
        is_ai_generated: bool = False,
        ai_prompt_name: str | None = None,
        ai_prompt_version: int | None = None,
    ) -> dict[str, Any]:
        """Insert a DRAFT material. Faculty must be assigned to the course."""
        _assert_faculty_owns_course(org_id, course_id, faculty_id)

        valid_types = {
            "LECTURE_NOTES",
            "LESSON_PLAN",
            "QUIZ",
            "ASSIGNMENT_BRIEF",
            "REFERENCE",
            "VIDEO_LINK",
            "OTHER",
        }
        if material_type not in valid_types:
            raise ValueError(f"material_type must be one of {valid_types}")

        mid = str(uuid4())
        now = _NOW()
        execute_transaction(
            [
                (
                    """
                INSERT INTO course_materials
                    (id, org_id, course_id, co_id, title, material_type,
                     content_body, file_url, is_ai_generated, ai_prompt_name,
                     ai_prompt_version, status, visible_to_students,
                     week_number, created_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',FALSE,%s,%s,%s)
                """,
                    (
                        mid,
                        org_id,
                        course_id,
                        co_id,
                        title,
                        material_type,
                        content_body,
                        file_url,
                        is_ai_generated,
                        ai_prompt_name,
                        ai_prompt_version,
                        week_number,
                        faculty_id,
                        now,
                    ),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.ENTITY_CREATED,
            actor_id=faculty_id,
            entity_type="course_material",
            entity_id=mid,
            org_id=org_id,
            metadata={"title": title, "type": material_type, "ai": is_ai_generated},
        )
        return _fetch_material(org_id, mid)

    @staticmethod
    def publish_material(
        org_id: str,
        material_id: str,
        faculty_id: str,
    ) -> dict[str, Any]:
        """DRAFT → PUBLISHED. Sets visible_to_students=TRUE."""
        row = _get_material_or_404(org_id, material_id)
        result = StateRegistry.validate_transition(
            "course_material", row["status"], "PUBLISHED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        now = _NOW()
        execute_transaction(
            [
                (
                    """
                UPDATE course_materials
                SET status='PUBLISHED', visible_to_students=TRUE,
                    published_at=%s, updated_at=%s
                WHERE id=%s AND org_id=%s
                """,
                    (now, now, material_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=faculty_id,
            entity_type="course_material",
            entity_id=material_id,
            org_id=org_id,
            metadata={"status": "PUBLISHED"},
        )
        DomainEventBus.publish(
            DomainEvent(
                event_type="course_material.published",
                org_id=org_id,
                entity_type="course_material",
                entity_id=material_id,
                actor_id=faculty_id,
                payload={
                    "material_id": material_id,
                    "course_id": str(row["course_id"]),
                    "title": row["title"],
                    "material_type": row["material_type"],
                    "week_number": row["week_number"],
                    "is_ai_generated": row["is_ai_generated"],
                },
            )
        )
        return _fetch_material(org_id, material_id)

    @staticmethod
    def archive_material(
        org_id: str,
        material_id: str,
        faculty_id: str,
    ) -> dict[str, Any]:
        """PUBLISHED → ARCHIVED. Hides from students."""
        row = _get_material_or_404(org_id, material_id)
        result = StateRegistry.validate_transition(
            "course_material", row["status"], "ARCHIVED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        now = _NOW()
        execute_transaction(
            [
                (
                    """
                UPDATE course_materials
                SET status='ARCHIVED', visible_to_students=FALSE, updated_at=%s
                WHERE id=%s AND org_id=%s
                """,
                    (now, material_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=faculty_id,
            entity_type="course_material",
            entity_id=material_id,
            org_id=org_id,
            metadata={"status": "ARCHIVED"},
        )
        return _fetch_material(org_id, material_id)

    @staticmethod
    def list_materials(
        org_id: str,
        course_id: str,
        actor_role: str,
        week_number: int | None = None,
        material_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Faculty see DRAFT+PUBLISHED. Students see PUBLISHED only."""
        is_student = actor_role.upper() == "STUDENT"
        filters = ["org_id=%s", "course_id=%s"]
        params: list = [org_id, course_id]

        if is_student:
            filters.append("status='PUBLISHED'")
            filters.append("visible_to_students=TRUE")
        else:
            filters.append("status != 'ARCHIVED'")

        if week_number is not None:
            filters.append("week_number=%s")
            params.append(week_number)
        if material_type:
            filters.append("material_type=%s")
            params.append(material_type)

        where = " AND ".join(filters)
        return execute_query(
            f"SELECT * FROM course_materials WHERE {where} ORDER BY week_number NULLS LAST, created_at",  # noqa: S608
            tuple(params),
        )

    @staticmethod
    def get_material(
        org_id: str,
        material_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        row = _get_material_or_404(org_id, material_id)
        if actor_role.upper() == "STUDENT" and row["status"] != "PUBLISHED":
            raise NotFoundError("course_material", material_id)
        return row


# ---------------------------------------------------------------------------
# AssignmentService
# ---------------------------------------------------------------------------


class AssignmentService:
    """CRUD + lifecycle for assignments."""

    @staticmethod
    def create_assignment(
        org_id: str,
        course_id: str,
        faculty_id: str,
        title: str,
        description: str,
        max_marks: Decimal,
        due_date: str,
        co_id: str | None = None,
        passing_marks: Decimal | None = None,
        allow_late: bool = False,
        late_penalty_pct: Decimal | None = None,
        is_ai_generated: bool = False,
        ai_prompt_name: str | None = None,
        ai_prompt_version: int | None = None,
    ) -> dict[str, Any]:
        _assert_faculty_owns_course(org_id, course_id, faculty_id)

        due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
        if due_dt <= _NOW():
            raise ValueError("due_date must be in the future")

        if late_penalty_pct is None:
            late_penalty_pct = Decimal(
                str(PolicyStore.get(org_id, PolicyKey.LEARNING_LATE_PENALTY_PCT) or 10)
            )

        aid = str(uuid4())
        now = _NOW()
        execute_transaction(
            [
                (
                    """
                INSERT INTO assignments
                    (id, org_id, course_id, co_id, title, description,
                     max_marks, passing_marks, due_date, allow_late,
                     late_penalty_pct, is_ai_generated, ai_prompt_name,
                     ai_prompt_version, status, created_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s)
                """,
                    (
                        aid,
                        org_id,
                        course_id,
                        co_id,
                        title,
                        description,
                        max_marks,
                        passing_marks,
                        due_dt,
                        allow_late,
                        late_penalty_pct,
                        is_ai_generated,
                        ai_prompt_name,
                        ai_prompt_version,
                        faculty_id,
                        now,
                    ),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.ENTITY_CREATED,
            actor_id=faculty_id,
            entity_type="assignment",
            entity_id=aid,
            org_id=org_id,
            metadata={"title": title, "due_date": due_date, "ai": is_ai_generated},
        )
        return _fetch_assignment(org_id, aid)

    @staticmethod
    def publish_assignment(
        org_id: str,
        assignment_id: str,
        faculty_id: str,
    ) -> dict[str, Any]:
        row = _get_assignment_or_404(org_id, assignment_id)
        result = StateRegistry.validate_transition(
            "assignment", row["status"], "PUBLISHED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        now = _NOW()
        execute_transaction(
            [
                (
                    """
                UPDATE assignments
                SET status='PUBLISHED', published_at=%s, updated_at=%s
                WHERE id=%s AND org_id=%s
                """,
                    (now, now, assignment_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=faculty_id,
            entity_type="assignment",
            entity_id=assignment_id,
            org_id=org_id,
            metadata={"status": "PUBLISHED"},
        )
        DomainEventBus.publish(
            DomainEvent(
                event_type="assignment.published",
                org_id=org_id,
                entity_type="assignment",
                entity_id=assignment_id,
                actor_id=faculty_id,
                payload={
                    "assignment_id": assignment_id,
                    "course_id": str(row["course_id"]),
                    "title": row["title"],
                    "due_date": row["due_date"].isoformat()
                    if row.get("due_date")
                    else None,
                },
            )
        )
        return _fetch_assignment(org_id, assignment_id)

    @staticmethod
    def close_assignment(
        org_id: str,
        assignment_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """PUBLISHED → CLOSED. Called by faculty manually or by Celery beat."""
        row = _get_assignment_or_404(org_id, assignment_id)
        result = StateRegistry.validate_transition(
            "assignment", row["status"], "CLOSED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        now = _NOW()
        execute_transaction(
            [
                (
                    """
                UPDATE assignments
                SET status='CLOSED', closed_at=%s, updated_at=%s
                WHERE id=%s AND org_id=%s
                """,
                    (now, now, assignment_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="assignment",
            entity_id=assignment_id,
            org_id=org_id,
            metadata={"status": "CLOSED"},
        )
        return _fetch_assignment(org_id, assignment_id)

    @staticmethod
    def list_assignments(
        org_id: str,
        course_id: str,
        actor_role: str,
        student_id: str | None = None,
    ) -> list[dict[str, Any]]:
        is_student = actor_role.upper() == "STUDENT"
        if is_student:
            # Join submission status for the student
            rows = execute_query(
                """
                SELECT a.*,
                       s.status AS submission_status,
                       s.marks_awarded,
                       s.effective_marks,
                       s.submitted_at AS my_submitted_at
                FROM assignments a
                LEFT JOIN assignment_submissions s
                    ON s.assignment_id = a.id AND s.student_id = %s
                WHERE a.org_id = %s AND a.course_id = %s
                  AND a.status IN ('PUBLISHED','CLOSED')
                ORDER BY a.due_date
                """,
                (student_id, org_id, course_id),
            )
        else:
            rows = execute_query(
                """
                SELECT a.*,
                       COUNT(s.id) FILTER (WHERE s.status='SUBMITTED') AS pending_review,
                       COUNT(s.id) FILTER (WHERE s.status='GRADED') AS graded_count,
                       COUNT(s.id) AS total_submissions
                FROM assignments a
                LEFT JOIN assignment_submissions s ON s.assignment_id = a.id
                WHERE a.org_id = %s AND a.course_id = %s AND a.status != 'ARCHIVED'
                GROUP BY a.id
                ORDER BY a.due_date
                """,
                (org_id, course_id),
            )
        return rows

    @staticmethod
    def get_assignment(
        org_id: str,
        assignment_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        row = _get_assignment_or_404(org_id, assignment_id)
        if actor_role.upper() == "STUDENT" and row["status"] == "DRAFT":
            raise NotFoundError("assignment", assignment_id)
        return row


# ---------------------------------------------------------------------------
# SubmissionService
# ---------------------------------------------------------------------------


class SubmissionService:
    """Student submission lifecycle + faculty grading."""

    @staticmethod
    def save_draft(
        org_id: str,
        assignment_id: str,
        student_id: str,
        content_text: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Upsert DRAFT submission. Assignment must be PUBLISHED, student enrolled."""
        asgn = _get_assignment_or_404(org_id, assignment_id)
        if asgn["status"] != "PUBLISHED":
            raise ValueError("Assignment is not open for submissions")
        _assert_student_enrolled(org_id, str(asgn["course_id"]), student_id)

        existing = execute_query(
            "SELECT id, status FROM assignment_submissions WHERE assignment_id=%s AND student_id=%s",
            (assignment_id, student_id),
        )
        now = _NOW()
        if existing:
            if existing[0]["status"] != "DRAFT":
                raise ValueError("Submission already submitted — cannot edit")
            execute_transaction(
                [
                    (
                        """
                    UPDATE assignment_submissions
                    SET content_text=%s, file_url=%s, updated_at=%s
                    WHERE id=%s
                    """,
                        (content_text, file_url, now, existing[0]["id"]),
                    )
                ]
            )
            AuditLog.log(
                action=AuditAction.UPDATE,
                actor_id=student_id,
                entity_type="assignment_submission",
                entity_id=existing[0]["id"],
                org_id=org_id,
                metadata={"action": "update_draft"},
            )
            return _fetch_submission(existing[0]["id"])

        sid = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO assignment_submissions
                    (id, org_id, assignment_id, student_id, content_text,
                     file_url, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,'DRAFT',%s)
                """,
                    (
                        sid,
                        org_id,
                        assignment_id,
                        student_id,
                        content_text,
                        file_url,
                        now,
                    ),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.ENTITY_CREATED,
            actor_id=student_id,
            entity_type="assignment_submission",
            entity_id=sid,
            org_id=org_id,
            metadata={"action": "create_draft"},
        )
        return _fetch_submission(sid)

    @staticmethod
    def submit(
        org_id: str,
        assignment_id: str,
        student_id: str,
    ) -> dict[str, Any]:
        """DRAFT → SUBMITTED."""
        existing = execute_query(
            "SELECT id, status FROM assignment_submissions WHERE assignment_id=%s AND student_id=%s",
            (assignment_id, student_id),
        )
        if not existing:
            raise NotFoundError(
                "assignment_submission", f"{assignment_id}/{student_id}"
            )

        row = existing[0]
        result = StateRegistry.validate_transition(
            "assignment_submission", row["status"], "SUBMITTED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        asgn = _get_assignment_or_404(org_id, assignment_id)
        now = _NOW()
        is_late = (
            now > asgn["due_date"].replace(tzinfo=timezone.utc)
            if asgn["due_date"].tzinfo is None
            else now > asgn["due_date"]
        )

        # Check max late days policy
        if is_late:
            max_late = int(
                PolicyStore.get(org_id, PolicyKey.LEARNING_MAX_LATE_DAYS) or 3
            )
            delta_days = (
                (now - asgn["due_date"]).days if not asgn.get("allow_late") else 0
            )
            if not asgn["allow_late"] or delta_days > max_late:
                raise ValueError(
                    f"Submission deadline passed (allow_late={asgn['allow_late']}, max_late_days={max_late})"
                )

        # Auto-begin-review if policy is set
        auto = PolicyStore.get(org_id, PolicyKey.LEARNING_AUTO_BEGIN_REVIEW)
        if auto:
            result_auto = StateRegistry.validate_transition(
                "assignment_submission", "SUBMITTED", "UNDER_REVIEW"
            )
            if not result_auto.allowed:
                raise ValueError(result_auto.reason)

        queries = [
            (
                """
            UPDATE assignment_submissions
            SET status='SUBMITTED', submitted_at=%s, is_late=%s, updated_at=%s
            WHERE id=%s
            """,
                (now, is_late, now, row["id"]),
            )
        ]

        if auto:
            queries.append(
                (
                    "UPDATE assignment_submissions SET status='UNDER_REVIEW', updated_at=%s WHERE id=%s",
                    (now, row["id"]),
                )
            )

        execute_transaction(queries)

        sub = _fetch_submission(row["id"])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=student_id,
            entity_type="assignment_submission",
            entity_id=row["id"],
            org_id=org_id,
            metadata={"status": "SUBMITTED", "is_late": is_late, "auto_review": auto},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="assignment.submitted",
                org_id=org_id,
                entity_type="assignment_submission",
                entity_id=row["id"],
                actor_id=student_id,
                payload={
                    "submission_id": row["id"],
                    "assignment_id": assignment_id,
                    "assignment_title": asgn["title"],
                    "course_id": str(asgn["course_id"]),
                    "student_id": student_id,
                    "submitted_at": now.isoformat(),
                    "is_late": is_late,
                },
            )
        )

        return sub

    @staticmethod
    def begin_review(
        org_id: str,
        submission_id: str,
        faculty_id: str,
    ) -> dict[str, Any]:
        """SUBMITTED → UNDER_REVIEW."""
        row = _fetch_submission(submission_id)
        result = StateRegistry.validate_transition(
            "assignment_submission", row["status"], "UNDER_REVIEW"
        )
        if not result.allowed:
            raise ValueError(result.reason)
        now = _NOW()
        execute_transaction(
            [
                (
                    "UPDATE assignment_submissions SET status='UNDER_REVIEW', updated_at=%s WHERE id=%s",
                    (now, submission_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=faculty_id,
            entity_type="assignment_submission",
            entity_id=submission_id,
            org_id=org_id,
            metadata={"status": "UNDER_REVIEW"},
        )
        return _fetch_submission(submission_id)

    @staticmethod
    def grade_submission(
        org_id: str,
        submission_id: str,
        faculty_id: str,
        marks_awarded: Decimal,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """UNDER_REVIEW → GRADED. Computes late_deduction, fires attainment event."""
        sub = _fetch_submission(submission_id)
        result = StateRegistry.validate_transition(
            "assignment_submission", sub["status"], "GRADED"
        )
        if not result.allowed:
            raise ValueError(result.reason)

        asgn = _get_assignment_or_404(org_id, str(sub["assignment_id"]))
        if marks_awarded < 0 or marks_awarded > asgn["max_marks"]:
            raise ValueError(f"marks_awarded must be between 0 and {asgn['max_marks']}")

        # Late deduction
        late_deduction = Decimal("0")
        if sub["is_late"] and sub["submitted_at"] and asgn["due_date"]:
            penalty_pct = Decimal(
                str(PolicyStore.get(org_id, PolicyKey.LEARNING_LATE_PENALTY_PCT) or 10)
            )
            days_late = max(0, (sub["submitted_at"] - asgn["due_date"]).days)
            late_deduction = min(
                marks_awarded,
                (penalty_pct / 100) * Decimal(str(asgn["max_marks"])) * days_late,
            )
        effective = max(Decimal("0"), marks_awarded - late_deduction)

        now = _NOW()
        execute_transaction(
            [
                (
                    """
                UPDATE assignment_submissions
                SET status='GRADED', marks_awarded=%s, late_deduction=%s,
                    effective_marks=%s, feedback=%s, graded_by=%s, graded_at=%s, updated_at=%s
                WHERE id=%s
                """,
                    (
                        marks_awarded,
                        late_deduction,
                        effective,
                        feedback,
                        faculty_id,
                        now,
                        now,
                        submission_id,
                    ),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=faculty_id,
            entity_type="assignment_submission",
            entity_id=submission_id,
            org_id=org_id,
            metadata={"status": "GRADED", "marks": float(marks_awarded)},
        )

        graded = _fetch_submission(submission_id)
        DomainEventBus.publish(
            DomainEvent(
                event_type="assignment.graded",
                org_id=org_id,
                entity_type="assignment_submission",
                entity_id=submission_id,
                actor_id=faculty_id,
                payload={
                    "submission_id": submission_id,
                    "assignment_id": str(sub["assignment_id"]),
                    "student_id": str(sub["student_id"]),
                    "marks_awarded": float(marks_awarded),
                    "effective_marks": float(effective),
                    "max_marks": float(asgn["max_marks"]),
                    "co_id": str(asgn["co_id"]) if asgn.get("co_id") else None,
                    "feedback_available": bool(feedback),
                },
            )
        )
        return graded

    @staticmethod
    def return_to_student(
        org_id: str,
        submission_id: str,
        faculty_id: str,
    ) -> dict[str, Any]:
        """GRADED → RETURNED. Makes feedback visible to student."""
        sub = _fetch_submission(submission_id)
        result = StateRegistry.validate_transition(
            "assignment_submission", sub["status"], "RETURNED"
        )
        if not result.allowed:
            raise ValueError(result.reason)
        now = _NOW()
        execute_transaction(
            [
                (
                    "UPDATE assignment_submissions SET status='RETURNED', updated_at=%s WHERE id=%s",
                    (now, submission_id),
                )
            ]
        )
        return _fetch_submission(submission_id)

    @staticmethod
    def list_submissions(
        org_id: str,
        assignment_id: str,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list = [org_id, assignment_id]
        where = "org_id=%s AND assignment_id=%s"
        if status_filter:
            where += " AND status=%s"
            params.append(status_filter)
        return execute_query(
            f"SELECT * FROM assignment_submissions WHERE {where} ORDER BY submitted_at NULLS LAST",  # noqa: S608
            tuple(params),
        )

    @staticmethod
    def get_my_submission(
        org_id: str,
        assignment_id: str,
        student_id: str,
    ) -> dict[str, Any] | None:
        rows = execute_query(
            "SELECT * FROM assignment_submissions WHERE assignment_id=%s AND student_id=%s",
            (assignment_id, student_id),
        )
        return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_material(org_id: str, material_id: str) -> dict[str, Any]:
    rows = execute_query(
        "SELECT * FROM course_materials WHERE id=%s AND org_id=%s",
        (material_id, org_id),
    )
    if not rows:
        raise NotFoundError("course_material", material_id)
    return dict(rows[0])


def _get_material_or_404(org_id: str, material_id: str) -> dict[str, Any]:
    return _fetch_material(org_id, material_id)


def _fetch_assignment(org_id: str, assignment_id: str) -> dict[str, Any]:
    rows = execute_query(
        "SELECT * FROM assignments WHERE id=%s AND org_id=%s", (assignment_id, org_id)
    )
    if not rows:
        raise NotFoundError("assignment", assignment_id)
    return dict(rows[0])


def _get_assignment_or_404(org_id: str, assignment_id: str) -> dict[str, Any]:
    return _fetch_assignment(org_id, assignment_id)


def _fetch_submission(submission_id: str) -> dict[str, Any]:
    rows = execute_query(
        "SELECT * FROM assignment_submissions WHERE id=%s", (submission_id,)
    )
    if not rows:
        raise NotFoundError("assignment_submission", submission_id)
    return dict(rows[0])


def _assert_faculty_owns_course(org_id: str, course_id: str, faculty_id: str) -> None:
    rows = execute_query(
        "SELECT id FROM courses WHERE id=%s AND org_id=%s AND faculty_id=%s",
        (course_id, org_id, faculty_id),
    )
    if not rows:
        raise PermissionError(
            f"Faculty {faculty_id} is not assigned to course {course_id}"
        )


def _assert_student_enrolled(org_id: str, course_id: str, student_id: str) -> None:
    rows = execute_query(
        """
        SELECT id FROM course_enrollments
        WHERE org_id=%s AND course_id=%s AND student_id=%s AND status='ENROLLED'
        """,
        (org_id, course_id, student_id),
    )
    if not rows:
        raise PermissionError(
            f"Student {student_id} is not enrolled in course {course_id}"
        )
