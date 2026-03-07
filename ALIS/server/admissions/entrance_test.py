"""
P7 — Entrance Test Management (Stage 5A)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 2 (Scheduling) + Layer 6 (Audit)

Manages institution-administered entrance tests:
  - Test creation and lifecycle (DRAFT → PUBLISHED → ONGOING → COMPLETED)
  - Slot scheduling (capacity management with atomic seat booking)
  - Applicant registration + admit card generation
  - Attendance recording
  - Score entry (total + section-wise breakdown)

External exams (JEE/NEET/CAT) use entrance_exam_scores on the applicant;
this module handles institution-administered tests only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Test status order (forward-only)
_TEST_STATUS_ORDER = ["DRAFT", "PUBLISHED", "ONGOING", "COMPLETED", "CANCELLED"]
_VALID_TEST_TRANSITIONS = {
    "DRAFT": {"PUBLISHED", "CANCELLED"},
    "PUBLISHED": {"ONGOING", "CANCELLED"},
    "ONGOING": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


# =============================================================================
# Pydantic Models
# =============================================================================

class AdmissionsTestCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    test_type: str = Field(
        ..., description="WRITTEN | ONLINE_PROCTORED | INTERVIEW_PI | INTERVIEW_GD | PORTFOLIO_REVIEW | EXTERNAL_SCORE_ONLY"
    )
    program_name: Optional[str] = None
    intake_batch: str = Field(..., min_length=2, max_length=50)
    mode: str = Field(default="OFFLINE", description="ONLINE | OFFLINE | HYBRID")
    duration_minutes: Optional[int] = Field(default=None, ge=5, le=480)
    total_marks: Optional[int] = Field(default=None, ge=1)
    passing_marks: Optional[int] = Field(default=None, ge=0)
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    instructions: Optional[str] = None
    proctoring_tool: Optional[str] = None
    external_test: bool = False


class AdmissionsTestRead(BaseModel):
    id: str
    org_id: str
    name: str
    test_type: str
    program_name: Optional[str] = None
    intake_batch: str
    mode: str
    duration_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    passing_marks: Optional[int] = None
    sections: Optional[List[Any]] = None
    instructions: Optional[str] = None
    proctoring_tool: Optional[str] = None
    external_test: bool = False
    status: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class TestSlotCreate(BaseModel):
    test_id: str
    slot_date: str = Field(..., description="ISO date: YYYY-MM-DD")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    capacity: int = Field(..., ge=1, le=1000)
    venue: Optional[str] = None
    online_link: Optional[str] = None


class TestSlotRead(BaseModel):
    id: str
    org_id: str
    test_id: str
    slot_date: Any  # date
    start_time: Any  # time
    end_time: Any  # time
    capacity: int
    booked_count: int
    venue: Optional[str] = None
    online_link: Optional[str] = None
    status: str
    created_at: datetime


class TestRegistrationCreate(BaseModel):
    test_id: str
    slot_id: str
    applicant_id: str


class TestRegistrationRead(BaseModel):
    id: str
    org_id: str
    test_id: str
    slot_id: Optional[str] = None
    applicant_id: str
    admit_card_path: Optional[str] = None
    admit_card_sent_at: Optional[datetime] = None
    attendance_status: str
    registered_at: datetime


class TestScoreCreate(BaseModel):
    test_id: str
    applicant_id: str
    total_score: Optional[float] = None
    section_scores: Dict[str, Any] = Field(default_factory=dict)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    rank_in_test: Optional[int] = Field(default=None, ge=1)
    remarks: Optional[str] = None


class TestScoreRead(BaseModel):
    id: str
    org_id: str
    test_id: str
    applicant_id: str
    total_score: Optional[float] = None
    section_scores: Optional[Dict[str, Any]] = None
    percentile: Optional[float] = None
    rank_in_test: Optional[int] = None
    remarks: Optional[str] = None
    entered_by: str
    entered_at: datetime


# =============================================================================
# ADMISSIONS TEST SERVICE
# =============================================================================

class AdmissionsTestService:

    @classmethod
    def create(
        cls,
        request: AdmissionsTestCreate,
        org_id: str,
        actor_id: str,
    ) -> AdmissionsTestRead:
        test_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO admissions_tests (
                    id, org_id, name, test_type, program_name, intake_batch,
                    mode, duration_minutes, total_marks, passing_marks,
                    sections, instructions, proctoring_tool, external_test,
                    status, created_by, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    test_id, org_id,
                    request.name, request.test_type,
                    request.program_name, request.intake_batch,
                    request.mode,
                    request.duration_minutes, request.total_marks, request.passing_marks,
                    json.dumps(request.sections),
                    request.instructions, request.proctoring_tool, request.external_test,
                    "DRAFT", actor_id, now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="admissions_test",
            entity_id=test_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"name": request.name, "intake_batch": request.intake_batch},
        )
        return cls.get(test_id, org_id)

    @classmethod
    def get(cls, test_id: str, org_id: str) -> AdmissionsTestRead:
        rows = execute_query(
            "SELECT * FROM admissions_tests WHERE id = %s AND org_id = %s",
            (test_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Admissions test '{test_id}' not found.")
        return AdmissionsTestRead(**rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        intake_batch: Optional[str] = None,
        program_name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[AdmissionsTestRead]:
        conditions = ["org_id = %s"]
        params: list = [org_id]
        if intake_batch:
            conditions.append("intake_batch = %s")
            params.append(intake_batch)
        if program_name:
            conditions.append("program_name = %s")
            params.append(program_name)
        if status:
            conditions.append("status = %s")
            params.append(status)

        rows = execute_query(
            f"SELECT * FROM admissions_tests WHERE {' AND '.join(conditions)} "
            "ORDER BY created_at DESC",
            tuple(params),
        )
        return [AdmissionsTestRead(**r) for r in rows]

    @classmethod
    def update_status(
        cls,
        test_id: str,
        org_id: str,
        new_status: str,
        actor_id: str,
    ) -> AdmissionsTestRead:
        rows = execute_query(
            "SELECT status FROM admissions_tests WHERE id = %s AND org_id = %s",
            (test_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Admissions test '{test_id}' not found.")

        current = rows[0]["status"]
        allowed = _VALID_TEST_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise BusinessRuleViolation(
                message=f"Illegal test status transition: {current} → {new_status}",
                details={"allowed": list(allowed)},
            )

        now = datetime.now(timezone.utc)
        execute_transaction([
            (
                "UPDATE admissions_tests SET status = %s, updated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (new_status, now, test_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="admissions_test",
            entity_id=test_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"from": current, "to": new_status},
        )
        return cls.get(test_id, org_id)


# =============================================================================
# TEST SLOT SERVICE
# =============================================================================

class TestSlotService:

    @classmethod
    def add_slot(
        cls,
        request: TestSlotCreate,
        org_id: str,
        actor_id: str,
    ) -> TestSlotRead:
        # Verify test exists and is in DRAFT/PUBLISHED state
        rows = execute_query(
            "SELECT status FROM admissions_tests WHERE id = %s AND org_id = %s",
            (request.test_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Test '{request.test_id}' not found.")
        if rows[0]["status"] not in ("DRAFT", "PUBLISHED"):
            raise BusinessRuleViolation(
                message=f"Slots can only be added to DRAFT or PUBLISHED tests. "
                        f"Current: {rows[0]['status']}"
            )

        slot_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO test_slots (
                    id, org_id, test_id, slot_date, start_time, end_time,
                    capacity, booked_count, venue, online_link, status, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    slot_id, org_id, request.test_id,
                    request.slot_date, request.start_time, request.end_time,
                    request.capacity, 0,
                    request.venue, request.online_link,
                    "OPEN", now,
                ),
            )
        ])
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="test_slot",
            entity_id=slot_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"test_id": request.test_id, "date": request.slot_date},
        )
        return cls.get(slot_id, org_id)

    @classmethod
    def get(cls, slot_id: str, org_id: str) -> TestSlotRead:
        rows = execute_query(
            "SELECT * FROM test_slots WHERE id = %s AND org_id = %s",
            (slot_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Test slot '{slot_id}' not found.")
        return TestSlotRead(**rows[0])

    @classmethod
    def list_for_test(cls, test_id: str, org_id: str) -> List[TestSlotRead]:
        rows = execute_query(
            "SELECT * FROM test_slots WHERE test_id = %s AND org_id = %s "
            "ORDER BY slot_date ASC, start_time ASC",
            (test_id, org_id),
        )
        return [TestSlotRead(**r) for r in rows]


# =============================================================================
# TEST REGISTRATION SERVICE
# =============================================================================

class TestRegistrationService:

    @classmethod
    def register(
        cls,
        request: TestRegistrationCreate,
        org_id: str,
        actor_id: str,
    ) -> TestRegistrationRead:
        """
        Register an applicant for a test slot.

        Atomically increments slot.booked_count, fails if slot is FULL.
        Enforces: one registration per (test, applicant).
        """
        # Check for duplicate registration
        existing = execute_query(
            "SELECT id FROM test_registrations WHERE test_id = %s AND applicant_id = %s",
            (request.test_id, request.applicant_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' is already registered for test '{request.test_id}'."
            )

        # Check slot availability
        slot_rows = execute_query(
            "SELECT capacity, booked_count, status FROM test_slots "
            "WHERE id = %s AND org_id = %s",
            (request.slot_id, org_id),
        )
        if not slot_rows:
            raise BusinessRuleViolation(message=f"Slot '{request.slot_id}' not found.")

        slot = slot_rows[0]
        if slot["status"] != "OPEN":
            raise BusinessRuleViolation(
                message=f"Slot '{request.slot_id}' is not open for booking. Status: {slot['status']}"
            )
        if slot["booked_count"] >= slot["capacity"]:
            raise BusinessRuleViolation(
                message=f"Slot '{request.slot_id}' is full ({slot['capacity']}/{slot['capacity']} booked)."
            )

        reg_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO test_registrations (
                    id, org_id, test_id, slot_id, applicant_id,
                    attendance_status, registered_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    reg_id, org_id,
                    request.test_id, request.slot_id, request.applicant_id,
                    "REGISTERED", now,
                ),
            ),
            # Atomic increment
            (
                "UPDATE test_slots SET booked_count = booked_count + 1, "
                "status = CASE WHEN booked_count + 1 >= capacity THEN 'FULL' ELSE 'OPEN' END "
                "WHERE id = %s AND org_id = %s",
                (request.slot_id, org_id),
            ),
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="test_registration",
            entity_id=reg_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"test_id": request.test_id, "applicant_id": request.applicant_id},
        )
        return cls.get(reg_id, org_id)

    @classmethod
    def get(cls, reg_id: str, org_id: str) -> TestRegistrationRead:
        rows = execute_query(
            "SELECT * FROM test_registrations WHERE id = %s AND org_id = %s",
            (reg_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Registration '{reg_id}' not found.")
        return TestRegistrationRead(**rows[0])

    @classmethod
    def list_for_test(
        cls, test_id: str, org_id: str
    ) -> List[TestRegistrationRead]:
        rows = execute_query(
            "SELECT * FROM test_registrations WHERE test_id = %s AND org_id = %s "
            "ORDER BY registered_at ASC",
            (test_id, org_id),
        )
        return [TestRegistrationRead(**r) for r in rows]

    @classmethod
    def list_for_applicant(
        cls, applicant_id: str, org_id: str
    ) -> List[TestRegistrationRead]:
        rows = execute_query(
            "SELECT * FROM test_registrations WHERE applicant_id = %s AND org_id = %s "
            "ORDER BY registered_at ASC",
            (applicant_id, org_id),
        )
        return [TestRegistrationRead(**r) for r in rows]

    @classmethod
    def record_attendance(
        cls,
        reg_id: str,
        org_id: str,
        attendance_status: str,
        actor_id: str,
    ) -> TestRegistrationRead:
        """Mark attendance: REGISTERED → PRESENT | ABSENT | CANCELLED."""
        valid = {"PRESENT", "ABSENT", "CANCELLED"}
        if attendance_status not in valid:
            raise BusinessRuleViolation(
                message=f"Invalid attendance status: {attendance_status}",
                details={"valid": list(valid)},
            )
        execute_transaction([
            (
                "UPDATE test_registrations SET attendance_status = %s "
                "WHERE id = %s AND org_id = %s",
                (attendance_status, reg_id, org_id),
            )
        ])
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="test_registration",
            entity_id=reg_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"attendance_status": attendance_status},
        )
        return cls.get(reg_id, org_id)

    @classmethod
    def generate_admit_card(
        cls,
        reg_id: str,
        org_id: str,
        actor_id: str,
    ) -> TestRegistrationRead:
        """
        Generate and link an admit card PDF for a test registration.

        Generates a placeholder path; in production this would invoke
        a PDF generation service and store to MinIO.
        """
        rows = execute_query(
            "SELECT id, applicant_id, test_id, admit_card_path "
            "FROM test_registrations WHERE id = %s AND org_id = %s",
            (reg_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Registration '{reg_id}' not found.")

        reg = rows[0]
        if reg["admit_card_path"]:
            # Already generated — return as-is
            return cls.get(reg_id, org_id)

        # Build admit card path (placeholder — replace with PDF service in prod)
        admit_card_path = (
            f"admit_cards/{org_id}/{reg['test_id']}/{reg['applicant_id']}_admit_card.pdf"
        )
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "UPDATE test_registrations "
                "SET admit_card_path = %s, admit_card_sent_at = %s "
                "WHERE id = %s AND org_id = %s",
                (admit_card_path, now, reg_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="test_registration",
            entity_id=reg_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={"admit_card_path": admit_card_path},
        )
        return cls.get(reg_id, org_id)


# =============================================================================
# TEST SCORE SERVICE
# =============================================================================

class TestScoreService:

    @classmethod
    def enter_score(
        cls,
        request: TestScoreCreate,
        org_id: str,
        actor_id: str,
    ) -> TestScoreRead:
        """
        Enter or update a test score for an applicant.

        Upsert: if score already exists, overwrite (re-valuation scenario).
        """
        score_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                "DELETE FROM test_scores "
                "WHERE test_id = %s AND applicant_id = %s AND org_id = %s",
                (request.test_id, request.applicant_id, org_id),
            ),
            (
                """
                INSERT INTO test_scores (
                    id, org_id, test_id, applicant_id,
                    total_score, section_scores, percentile, rank_in_test,
                    remarks, entered_by, entered_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                """,
                (
                    score_id, org_id,
                    request.test_id, request.applicant_id,
                    request.total_score,
                    json.dumps(request.section_scores or {}),
                    request.percentile,
                    request.rank_in_test,
                    request.remarks,
                    actor_id, now,
                ),
            ),
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="test_score",
            entity_id=score_id,
            org_id=org_id,
            module="M1",
            wizard="Entrance Test",
            success=True,
            metadata={
                "test_id": request.test_id,
                "applicant_id": request.applicant_id,
                "total_score": request.total_score,
            },
        )
        return cls.get_for_applicant(request.test_id, request.applicant_id, org_id)

    @classmethod
    def get_for_applicant(
        cls, test_id: str, applicant_id: str, org_id: str
    ) -> TestScoreRead:
        rows = execute_query(
            "SELECT * FROM test_scores "
            "WHERE test_id = %s AND applicant_id = %s AND org_id = %s",
            (test_id, applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"No score found for applicant '{applicant_id}' in test '{test_id}'."
            )
        return TestScoreRead(**rows[0])

    @classmethod
    def list_for_test(cls, test_id: str, org_id: str) -> List[TestScoreRead]:
        rows = execute_query(
            "SELECT * FROM test_scores WHERE test_id = %s AND org_id = %s "
            "ORDER BY rank_in_test ASC NULLS LAST, total_score DESC NULLS LAST",
            (test_id, org_id),
        )
        return [TestScoreRead(**r) for r in rows]
