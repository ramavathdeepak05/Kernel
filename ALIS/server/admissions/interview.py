"""
P7 — Interview Management (Stage 5B)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 2 (Scheduling + Scoring) + Layer 6 (Audit)

Manages the interview pipeline for admissions:
  - Panel creation (PI / GD / Portfolio) with evaluators and parameters
  - Interview scheduling (one-on-one and group)
  - Attendance tracking
  - Multi-evaluator scorecard submission
  - Aggregate score calculation for merit list
"""

from __future__ import annotations

import builtins
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class InterviewPanelCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    program_name: str | None = None
    intake_batch: str = Field(..., min_length=2, max_length=50)
    panel_members: list[dict[str, Any]] = Field(
        default_factory=list,
        description='[{"user_id": "...", "name": "...", "role": "HOD"}, ...]',
    )
    evaluation_parameters: list[dict[str, Any]] = Field(
        default_factory=list,
        description='[{"name": "Communication", "max_score": 10}, ...]',
    )


class InterviewPanelRead(BaseModel):
    id: str
    org_id: str
    name: str
    program_name: str | None = None
    intake_batch: str
    panel_members: list[Any] | None = None
    evaluation_parameters: list[Any] | None = None
    status: str
    created_by: str
    created_at: datetime


class InterviewScheduleCreate(BaseModel):
    panel_id: str
    applicant_id: str
    interview_type: str = Field(default="PI", description="PI | GD | PORTFOLIO")
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    mode: str = Field(default="OFFLINE", description="ONLINE | OFFLINE")
    venue: str | None = None
    online_link: str | None = None


class InterviewScheduleRead(BaseModel):
    id: str
    org_id: str
    panel_id: str
    applicant_id: str
    interview_type: str
    scheduled_at: datetime
    duration_minutes: int
    mode: str
    venue: str | None = None
    online_link: str | None = None
    calendar_invite_sent: bool
    attendance_status: str
    created_at: datetime
    updated_at: datetime | None = None


class InterviewScorecardCreate(BaseModel):
    schedule_id: str
    applicant_id: str
    parameter_scores: dict[str, Any] = Field(
        ..., description='{"Communication": 8, "Knowledge": 7}'
    )
    total_score: float | None = None
    qualitative_remarks: str | None = None
    recommendation: str = Field(
        ..., description="STRONG_ADMIT | ADMIT | BORDERLINE | REJECT"
    )


class InterviewScorecardRead(BaseModel):
    id: str
    org_id: str
    schedule_id: str
    applicant_id: str
    evaluator_id: str
    parameter_scores: dict[str, Any] | None = None
    total_score: float | None = None
    qualitative_remarks: str | None = None
    recommendation: str
    submitted_at: datetime


# =============================================================================
# INTERVIEW PANEL SERVICE
# =============================================================================


class InterviewPanelService:
    @classmethod
    def create(
        cls,
        request: InterviewPanelCreate,
        org_id: str,
        actor_id: str,
    ) -> InterviewPanelRead:
        panel_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO interview_panels (
                    id, org_id, name, program_name, intake_batch,
                    panel_members, evaluation_parameters,
                    status, created_by, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                """,
                    (
                        panel_id,
                        org_id,
                        request.name,
                        request.program_name,
                        request.intake_batch,
                        json.dumps(request.panel_members),
                        json.dumps(request.evaluation_parameters),
                        "ACTIVE",
                        actor_id,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="interview_panel",
            entity_id=panel_id,
            org_id=org_id,
            module="M1",
            wizard="Interview Management",
            success=True,
            metadata={"name": request.name, "intake_batch": request.intake_batch},
        )
        return cls.get(panel_id, org_id)

    @classmethod
    def get(cls, panel_id: str, org_id: str) -> InterviewPanelRead:
        rows = execute_query(
            "SELECT * FROM interview_panels WHERE id = %s AND org_id = %s",
            (panel_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Interview panel '{panel_id}' not found."
            )
        return InterviewPanelRead(**rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        intake_batch: str | None = None,
        program_name: str | None = None,
    ) -> builtins.list[InterviewPanelRead]:
        conditions = ["org_id = %s"]
        params: list = [org_id]
        if intake_batch:
            conditions.append("intake_batch = %s")
            params.append(intake_batch)
        if program_name:
            conditions.append("program_name = %s")
            params.append(program_name)
        rows = execute_query(
            f"SELECT * FROM interview_panels WHERE {' AND '.join(conditions)} "  # noqa: S608
            "ORDER BY created_at DESC",
            tuple(params),
        )
        return [InterviewPanelRead(**r) for r in rows]


# =============================================================================
# INTERVIEW SCHEDULE SERVICE
# =============================================================================


class InterviewScheduleService:
    @classmethod
    def schedule(
        cls,
        request: InterviewScheduleCreate,
        org_id: str,
        actor_id: str,
    ) -> InterviewScheduleRead:
        """
        Schedule an interview for an applicant.

        Validates panel exists and is ACTIVE.
        Prevents duplicate scheduling for same (panel, applicant).
        """
        # Verify panel
        panel_rows = execute_query(
            "SELECT status FROM interview_panels WHERE id = %s AND org_id = %s",
            (request.panel_id, org_id),
        )
        if not panel_rows:
            raise BusinessRuleViolation(
                message=f"Panel '{request.panel_id}' not found."
            )
        if panel_rows[0]["status"] != "ACTIVE":
            raise BusinessRuleViolation(
                message=f"Panel '{request.panel_id}' is not ACTIVE. "
                f"Status: {panel_rows[0]['status']}"
            )

        # Check for duplicate
        existing = execute_query(
            "SELECT id FROM interview_schedules "
            "WHERE panel_id = %s AND applicant_id = %s AND org_id = %s "
            "AND attendance_status NOT IN ('CANCELLED')",
            (request.panel_id, request.applicant_id, org_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' already has an active "
                f"interview scheduled with panel '{request.panel_id}'."
            )

        schedule_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO interview_schedules (
                    id, org_id, panel_id, applicant_id, interview_type,
                    scheduled_at, duration_minutes, mode, venue, online_link,
                    calendar_invite_sent, attendance_status,
                    created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                    (
                        schedule_id,
                        org_id,
                        request.panel_id,
                        request.applicant_id,
                        request.interview_type,
                        request.scheduled_at,
                        request.duration_minutes,
                        request.mode,
                        request.venue,
                        request.online_link,
                        False,
                        "SCHEDULED",
                        now,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="interview_schedule",
            entity_id=schedule_id,
            org_id=org_id,
            module="M1",
            wizard="Interview Management",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "panel_id": request.panel_id,
                "scheduled_at": request.scheduled_at.isoformat(),
            },
        )
        return cls.get(schedule_id, org_id)

    @classmethod
    def get(cls, schedule_id: str, org_id: str) -> InterviewScheduleRead:
        rows = execute_query(
            "SELECT * FROM interview_schedules WHERE id = %s AND org_id = %s",
            (schedule_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Interview schedule '{schedule_id}' not found."
            )
        return InterviewScheduleRead(**rows[0])

    @classmethod
    def list_for_applicant(
        cls, applicant_id: str, org_id: str
    ) -> list[InterviewScheduleRead]:
        rows = execute_query(
            "SELECT * FROM interview_schedules "
            "WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY scheduled_at ASC",
            (applicant_id, org_id),
        )
        return [InterviewScheduleRead(**r) for r in rows]

    @classmethod
    def list_for_panel(cls, panel_id: str, org_id: str) -> list[InterviewScheduleRead]:
        rows = execute_query(
            "SELECT * FROM interview_schedules "
            "WHERE panel_id = %s AND org_id = %s "
            "ORDER BY scheduled_at ASC",
            (panel_id, org_id),
        )
        return [InterviewScheduleRead(**r) for r in rows]

    @classmethod
    def update_attendance(
        cls,
        schedule_id: str,
        org_id: str,
        attendance_status: str,
        actor_id: str,
    ) -> InterviewScheduleRead:
        valid = {"COMPLETED", "ABSENT", "CANCELLED", "RESCHEDULED"}
        if attendance_status not in valid:
            raise BusinessRuleViolation(
                message=f"Invalid attendance status: {attendance_status}",
                details={"valid": list(valid)},
            )
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    "UPDATE interview_schedules "
                    "SET attendance_status = %s, updated_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (attendance_status, now, schedule_id, org_id),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="interview_schedule",
            entity_id=schedule_id,
            org_id=org_id,
            module="M1",
            wizard="Interview Management",
            success=True,
            metadata={"attendance_status": attendance_status},
        )
        return cls.get(schedule_id, org_id)


# =============================================================================
# INTERVIEW SCORECARD SERVICE
# =============================================================================


class InterviewScorecardService:
    @classmethod
    def submit(
        cls,
        request: InterviewScorecardCreate,
        org_id: str,
        evaluator_id: str,
    ) -> InterviewScorecardRead:
        """
        Submit a scorecard for an interview.

        One scorecard per evaluator per schedule. Subsequent calls overwrite.
        Auto-calculates total_score from parameter_scores if not provided.
        """
        valid_recs = {"STRONG_ADMIT", "ADMIT", "BORDERLINE", "REJECT"}
        if request.recommendation not in valid_recs:
            raise BusinessRuleViolation(
                message=f"Invalid recommendation: {request.recommendation}",
                details={"valid": list(valid_recs)},
            )

        # Auto-calculate total if not provided
        total = request.total_score
        if total is None and request.parameter_scores:
            total = sum(
                float(v)
                for v in request.parameter_scores.values()
                if isinstance(v, (int, float))
            )

        scorecard_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    "DELETE FROM interview_scorecards "
                    "WHERE schedule_id = %s AND evaluator_id = %s AND org_id = %s",
                    (request.schedule_id, evaluator_id, org_id),
                ),
                (
                    """
                INSERT INTO interview_scorecards (
                    id, org_id, schedule_id, applicant_id,
                    evaluator_id, parameter_scores, total_score,
                    qualitative_remarks, recommendation, submitted_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                """,
                    (
                        scorecard_id,
                        org_id,
                        request.schedule_id,
                        request.applicant_id,
                        evaluator_id,
                        json.dumps(request.parameter_scores),
                        total,
                        request.qualitative_remarks,
                        request.recommendation,
                        now,
                    ),
                ),
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=evaluator_id,
            entity_type="interview_scorecard",
            entity_id=scorecard_id,
            org_id=org_id,
            module="M1",
            wizard="Interview Management",
            success=True,
            metadata={
                "schedule_id": request.schedule_id,
                "recommendation": request.recommendation,
                "total_score": total,
            },
        )

        rows = execute_query(
            "SELECT * FROM interview_scorecards WHERE id = %s",
            (scorecard_id,),
        )
        return InterviewScorecardRead(**rows[0])

    @classmethod
    def list_for_schedule(
        cls, schedule_id: str, org_id: str
    ) -> list[InterviewScorecardRead]:
        rows = execute_query(
            "SELECT * FROM interview_scorecards "
            "WHERE schedule_id = %s AND org_id = %s "
            "ORDER BY submitted_at ASC",
            (schedule_id, org_id),
        )
        return [InterviewScorecardRead(**r) for r in rows]

    @classmethod
    def get_aggregate_score(cls, schedule_id: str, org_id: str) -> dict[str, Any]:
        """
        Calculate the aggregate score across all evaluator scorecards.

        Returns:
            {average_total: float, evaluator_count: int,
             recommendation_summary: {STRONG_ADMIT: n, ADMIT: n, ...}}
        """
        rows = execute_query(
            "SELECT total_score, recommendation FROM interview_scorecards "
            "WHERE schedule_id = %s AND org_id = %s",
            (schedule_id, org_id),
        )
        if not rows:
            return {
                "average_total": 0.0,
                "evaluator_count": 0,
                "recommendation_summary": {},
            }

        scores = [r["total_score"] for r in rows if r["total_score"] is not None]
        avg = sum(scores) / len(scores) if scores else 0.0

        rec_summary: dict[str, int] = {}
        for r in rows:
            rec = r["recommendation"]
            rec_summary[rec] = rec_summary.get(rec, 0) + 1

        return {
            "average_total": round(avg, 4),
            "evaluator_count": len(rows),
            "recommendation_summary": rec_summary,
        }
