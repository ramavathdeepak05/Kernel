"""
SS-8 — Alumni Transition Saga + Graduation Employment Declaration

AlumniTransitionSaga:
    Waits for ALL THREE signals before transitioning a student to alumni:
    1. result.final_published — all semester results are published
    2. student.dues_cleared — zero outstanding fees
    3. graduation.verified — degree verification complete

    Only when all 3 are received → create alumni profile, seal transcript.

GraduationEmploymentDeclaration:
    Mandatory decision tree before degree certificate is downloadable.
    Required for NIRF GO (Graduation Outcomes) metric.

    Categories:
    - PLACED_EMPLOYED (requires employer_name, employer_cin)
    - HIGHER_STUDIES (requires institution, program)
    - ENTREPRENEURSHIP_OWN (requires gstin or startup_name)
    - ENTREPRENEURSHIP_FAMILY (requires business_name)
    - GOVERNMENT_EXAM_PREP
    - NOT_SEEKING_YET
    - SEEKING_EMPLOYMENT

    Degree certificate download is blocked until declaration is submitted.
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


class SagaSignal(str, Enum):
    RESULT_PUBLISHED = "result.final_published"
    DUES_CLEARED = "student.dues_cleared"
    GRADUATION_VERIFIED = "graduation.verified"


class EmploymentCategory(str, Enum):
    PLACED_EMPLOYED = "PLACED_EMPLOYED"
    HIGHER_STUDIES = "HIGHER_STUDIES"
    ENTREPRENEURSHIP_OWN = "ENTREPRENEURSHIP_OWN"
    ENTREPRENEURSHIP_FAMILY = "ENTREPRENEURSHIP_FAMILY"
    GOVERNMENT_EXAM_PREP = "GOVERNMENT_EXAM_PREP"
    NOT_SEEKING_YET = "NOT_SEEKING_YET"
    SEEKING_EMPLOYMENT = "SEEKING_EMPLOYMENT"


class AlumniTransitionSaga:
    """
    Orchestrates the 3-signal graduation transition.

    Each signal is recorded independently. When all 3 are present
    for a student, the saga auto-completes:
    1. Creates alumni profile
    2. Seals transcript (permanent, immutable)
    3. Publishes alumni.created event
    """

    @classmethod
    def record_signal(
        cls, org_id: str, student_id: str, signal: str, actor_id: str = "system"
    ) -> dict[str, Any]:
        """Record a graduation signal. Auto-completes saga if all 3 present."""
        now = datetime.now(timezone.utc)

        # Pre-check signals
        signals = execute_query(
            "SELECT signal_type FROM graduation_saga_signals WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        received = {str(s["signal_type"]) for s in signals}
        received.add(signal)
        all_required = {
            SagaSignal.RESULT_PUBLISHED.value,
            SagaSignal.DUES_CLEARED.value,
            SagaSignal.GRADUATION_VERIFIED.value,
        }

        queries = [
            (
                """
                INSERT INTO graduation_saga_signals
                    (id, org_id, student_id, signal_type, received_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (org_id, student_id, signal_type) DO UPDATE
                SET received_at = EXCLUDED.received_at
                """,
                (str(uuid4()), org_id, student_id, signal, now),
            )
        ]

        # Prepare payload
        response = {
            "student_id": student_id,
            "signal_recorded": signal,
            "signals_received": list(received),
            "signals_remaining": list(all_required - received),
            "saga_complete": False,
        }

        alumni_info = None
        should_complete = received >= all_required

        if should_complete:
            # Check if already transitioned
            existing = execute_query(
                "SELECT id FROM alumni_profiles WHERE student_id = %s AND org_id = %s",
                (student_id, org_id),
                tenant_id=org_id,
            )
            if existing:
                response.update(
                    {
                        "saga_complete": True,
                        "alumni_id": str(existing[0]["id"]),
                        "message": "Already transitioned to alumni",
                    }
                )
                should_complete = False  # Skip queries if already transitioned
            else:
                student = execute_query(
                    "SELECT id, display_name, email, username FROM users WHERE id = %s AND org_id = %s",
                    (student_id, org_id),
                    tenant_id=org_id,
                )
                if not student:
                    logger.error(
                        "AlumniTransitionSaga: student %s not found", student_id
                    )
                    response.update({"error": "Student not found"})
                    should_complete = False
                else:
                    s = dict(student[0])
                    alumni_id = str(uuid4())
                    queries.extend(
                        [
                            (
                                """
                            INSERT INTO alumni_profiles
                                (id, org_id, student_id, name, email, status, created_at)
                            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s)
                            """,
                                (
                                    alumni_id,
                                    org_id,
                                    student_id,
                                    s.get("display_name", s.get("username", "")),
                                    s.get("email", ""),
                                    now,
                                ),
                            ),
                            (
                                """
                            INSERT INTO graduation_saga_completions
                                (id, org_id, student_id, alumni_id, completed_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                                (str(uuid4()), org_id, student_id, alumni_id, now),
                            ),
                        ]
                    )
                    alumni_info = alumni_id
                    response.update(
                        {
                            "saga_complete": True,
                            "alumni_id": alumni_id,
                        }
                    )

        # Atomic commit
        execute_transaction(queries, tenant_id=org_id)

        # Post-commit side effects
        if alumni_info:
            # Publish event for examinations module to seal transcript
            # (decoupled — examinations subscribes to alumni.graduation_saga_completed)
            DomainEventBus.publish(
                DomainEvent(
                    event_type="alumni.graduation_saga_completed",
                    org_id=org_id,
                    payload={"alumni_id": alumni_info, "student_id": student_id},
                    actor_id=actor_id,
                )
            )

            DomainEventBus.publish(
                DomainEvent(
                    event_type="alumni.created",
                    org_id=org_id,
                    payload={"alumni_id": alumni_info, "student_id": student_id},
                    actor_id=actor_id,
                )
            )

            AuditLog.log(
                action=AuditAction.CREATE,
                actor_id=actor_id,
                actor_role="system",
                entity_type="alumni_profile",
                entity_id=alumni_info,
                tenant_id=org_id,
                metadata={
                    "student_id": student_id,
                    "event": "alumni_transition_saga_complete",
                },
            )

        return response

    @classmethod
    def get_saga_status(cls, org_id: str, student_id: str) -> dict[str, Any]:
        signals = execute_query(
            "SELECT signal_type, received_at FROM graduation_saga_signals WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        received = {str(s["signal_type"]): s["received_at"] for s in signals}
        all_required = {
            SagaSignal.RESULT_PUBLISHED.value,
            SagaSignal.DUES_CLEARED.value,
            SagaSignal.GRADUATION_VERIFIED.value,
        }

        completion = execute_query(
            "SELECT alumni_id, completed_at FROM graduation_saga_completions WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )

        return {
            "student_id": student_id,
            "signals": received,
            "remaining": list(all_required - set(received.keys())),
            "complete": bool(completion),
            "alumni_id": str(completion[0]["alumni_id"]) if completion else None,
        }


class GraduationEmploymentDeclaration:
    """
    Mandatory employment declaration before degree certificate issuance.
    Feeds NIRF GO (Graduation Outcomes) metric.
    """

    REQUIRED_FIELDS = {
        EmploymentCategory.PLACED_EMPLOYED: ["employer_name"],
        EmploymentCategory.HIGHER_STUDIES: ["institution", "program"],
        EmploymentCategory.ENTREPRENEURSHIP_OWN: ["startup_name"],
        EmploymentCategory.ENTREPRENEURSHIP_FAMILY: ["business_name"],
        EmploymentCategory.GOVERNMENT_EXAM_PREP: [],
        EmploymentCategory.NOT_SEEKING_YET: [],
        EmploymentCategory.SEEKING_EMPLOYMENT: [],
    }

    @classmethod
    def submit(
        cls, org_id: str, student_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        """Submit graduation employment declaration."""
        category = EmploymentCategory(data["category"])

        # Validate required fields per category
        required = cls.REQUIRED_FIELDS.get(category, [])
        for field in required:
            if not data.get(field):
                raise ValueError(
                    f"Field '{field}' is required for category {category.value}"
                )

        decl_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO graduation_employment_declarations
                    (id, org_id, student_id, category, employer_name, employer_cin,
                     institution, program, startup_name, gstin, business_name,
                     submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (org_id, student_id) DO UPDATE SET
                    category = EXCLUDED.category,
                    employer_name = EXCLUDED.employer_name,
                    employer_cin = EXCLUDED.employer_cin,
                    institution = EXCLUDED.institution,
                    program = EXCLUDED.program,
                    startup_name = EXCLUDED.startup_name,
                    gstin = EXCLUDED.gstin,
                    business_name = EXCLUDED.business_name,
                    submitted_at = EXCLUDED.submitted_at
                """,
                    (
                        decl_id,
                        org_id,
                        student_id,
                        category.value,
                        data.get("employer_name", ""),
                        data.get("employer_cin", ""),
                        data.get("institution", ""),
                        data.get("program", ""),
                        data.get("startup_name", ""),
                        data.get("gstin", ""),
                        data.get("business_name", ""),
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="student",
            entity_type="graduation_employment_declaration",
            entity_id=decl_id,
            tenant_id=org_id,
            metadata={"category": category.value},
        )

        return {"id": decl_id, "category": category.value, "status": "SUBMITTED"}

    @classmethod
    def can_download_degree(cls, org_id: str, student_id: str) -> bool:
        """Check if student has submitted employment declaration (prerequisite for degree download)."""
        rows = execute_query(
            "SELECT id FROM graduation_employment_declarations WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        return bool(rows)

    @classmethod
    def get_nirf_go_data(cls, org_id: str, graduation_year: str) -> dict[str, Any]:
        """Aggregate employment data for NIRF GO (Graduation Outcomes)."""
        rows = execute_query(
            """
            SELECT category, COUNT(*) AS cnt
            FROM graduation_employment_declarations ged
            JOIN graduation_saga_completions gsc ON gsc.student_id = ged.student_id AND gsc.org_id = ged.org_id
            WHERE ged.org_id = %s AND EXTRACT(YEAR FROM gsc.completed_at) = %s
            GROUP BY category
            """,
            (org_id, int(graduation_year)),
            tenant_id=org_id,
        )
        categories = {r["category"]: r["cnt"] for r in rows}
        total = sum(categories.values())
        placed = categories.get("PLACED_EMPLOYED", 0)
        higher = categories.get("HIGHER_STUDIES", 0)
        entrepreneur = categories.get("ENTREPRENEURSHIP_OWN", 0) + categories.get(
            "ENTREPRENEURSHIP_FAMILY", 0
        )

        return {
            "graduation_year": graduation_year,
            "total_graduates": total,
            "placed_employed": placed,
            "higher_studies": higher,
            "entrepreneurship": entrepreneur,
            "placement_rate": round(placed / total * 100, 1) if total > 0 else 0,
            "go_rate": round((placed + higher + entrepreneur) / total * 100, 1)
            if total > 0
            else 0,
            "categories": categories,
        }
