"""E18 — Convocation Management Service

Degree audit automation, gold medal computation, seating generation.
Gold medal computed on CGPA WITHOUT grace marks (policy-controlled).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------

class ConvocationStatus(str, Enum):
    PLANNED             = "PLANNED"
    AUDIT_RUNNING       = "AUDIT_RUNNING"
    AUDIT_COMPLETE      = "AUDIT_COMPLETE"
    SEATING_GENERATED   = "SEATING_GENERATED"
    COMPLETED           = "COMPLETED"
    CANCELLED           = "CANCELLED"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ConvocationService:
    """E18 — Convocation lifecycle: creation → degree audit → gold medals → seating."""

    # ------------------------------------------------------------------ #
    # create_convocation
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_convocation(
        org_id: str,
        title: str,
        ceremony_date: str,
        academic_year: str,
        batch_year: int,
        venue: Optional[str] = None,
        chief_guest: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new convocation event in PLANNED status."""
        convocation_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO convocation_events
                    (id, org_id, title, ceremony_date, academic_year, batch_year,
                     venue, chief_guest, status, created_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    convocation_id,
                    org_id,
                    title,
                    ceremony_date,
                    academic_year,
                    batch_year,
                    venue,
                    chief_guest,
                    ConvocationStatus.PLANNED,
                    created_by,
                    now,
                    now,
                ),
            )
        ])

        DomainEventBus.publish(DomainEvent(
            event_type="convocation.created",
            org_id=org_id,
            entity_type="convocation_event",
            entity_id=convocation_id,
            actor_id=created_by or "system",
            payload={
                "convocation_id": convocation_id,
                "title": title,
                "ceremony_date": ceremony_date,
                "academic_year": academic_year,
                "batch_year": batch_year,
            },
        ))

        logger.info("ConvocationService: created convocation %s for org %s", convocation_id, org_id)

        return {
            "convocation_id": convocation_id,
            "org_id": org_id,
            "title": title,
            "ceremony_date": ceremony_date,
            "academic_year": academic_year,
            "batch_year": batch_year,
            "venue": venue,
            "chief_guest": chief_guest,
            "status": ConvocationStatus.PLANNED,
            "created_by": created_by,
            "created_at": now.isoformat(),
        }

    # ------------------------------------------------------------------ #
    # run_degree_audit
    # ------------------------------------------------------------------ #

    @staticmethod
    def run_degree_audit(
        convocation_id: str,
        org_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Run the degree eligibility audit for all students in the convocation batch.

        Queries students by batch_year from the convocation, evaluates eligibility
        criteria (backlogs, distinction threshold from policy), and bulk-inserts
        audit records.
        """
        # Fetch convocation
        rows = execute_query(
            "SELECT * FROM convocation_events WHERE id = %s AND org_id = %s",
            (convocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Convocation {convocation_id} not found")
        convocation = rows[0]

        allowed_statuses = {ConvocationStatus.PLANNED, ConvocationStatus.AUDIT_COMPLETE}
        if convocation["status"] not in {s.value for s in allowed_statuses}:
            raise BusinessRuleViolation(
                f"Degree audit can only be run when convocation is in "
                f"PLANNED or AUDIT_COMPLETE status; current: {convocation['status']}"
            )

        batch_year = convocation["batch_year"]

        # Mark as AUDIT_RUNNING
        execute_transaction([
            (
                "UPDATE convocation_events SET status = %s, updated_at = %s WHERE id = %s",
                (ConvocationStatus.AUDIT_RUNNING, datetime.now(timezone.utc), convocation_id),
            )
        ])

        # Policy thresholds (R1 — no hardcoded thresholds)
        distinction_threshold = float(
            policy_engine.get_value(
                "convocation.distinction_cgpa_threshold",
                org_id,
                default=8.5,
            )
        )

        # Query all eligible students for this batch
        student_rows = execute_query(
            """
            SELECT s.id AS student_id, s.program_id,
                   COALESCE(s.cgpa, 0) AS cgpa,
                   COALESCE(s.cgpa_without_grace, s.cgpa, 0) AS cgpa_without_grace,
                   COUNT(CASE WHEN sa.status = 'PENDING' THEN 1 END) AS backlogs_pending
            FROM students s
            LEFT JOIN student_assessments sa
                ON sa.student_id = s.id AND sa.status = 'PENDING'
            WHERE s.org_id = %s AND s.batch_year = %s AND s.status = 'ENROLLED'
            GROUP BY s.id, s.program_id, s.cgpa, s.cgpa_without_grace
            """,
            (org_id, batch_year),
        )

        now = datetime.now(timezone.utc)
        audit_inserts = []
        eligible_count = 0
        ineligible_count = 0

        for student in student_rows:
            backlogs_pending = int(student["backlogs_pending"] or 0)
            cgpa = float(student["cgpa"] or 0)
            cgpa_without_grace = float(student["cgpa_without_grace"] or 0)

            eligible_for_degree = backlogs_pending == 0  # dues assume cleared
            eligible_for_distinction = cgpa >= distinction_threshold

            if eligible_for_degree:
                eligible_count += 1
            else:
                ineligible_count += 1

            audit_id = str(uuid4())
            audit_inserts.append((
                """
                INSERT INTO convocation_degree_audits
                    (id, convocation_id, student_id, program_id,
                     cgpa, cgpa_without_grace, backlogs_pending,
                     eligible_for_degree, eligible_for_distinction,
                     eligible_for_gold_medal,
                     distinction_threshold_used,
                     audited_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)
                ON CONFLICT (convocation_id, student_id) DO UPDATE
                    SET cgpa = EXCLUDED.cgpa,
                        cgpa_without_grace = EXCLUDED.cgpa_without_grace,
                        backlogs_pending = EXCLUDED.backlogs_pending,
                        eligible_for_degree = EXCLUDED.eligible_for_degree,
                        eligible_for_distinction = EXCLUDED.eligible_for_distinction,
                        eligible_for_gold_medal = FALSE,
                        distinction_threshold_used = EXCLUDED.distinction_threshold_used,
                        audited_at = EXCLUDED.audited_at
                """,
                (
                    audit_id,
                    convocation_id,
                    student["student_id"],
                    student["program_id"],
                    cgpa,
                    cgpa_without_grace,
                    backlogs_pending,
                    eligible_for_degree,
                    eligible_for_distinction,
                    distinction_threshold,
                    now,
                    now,
                ),
            ))

        if audit_inserts:
            execute_transaction(audit_inserts)

        total_audited = len(student_rows)

        # Mark AUDIT_COMPLETE
        execute_transaction([
            (
                "UPDATE convocation_events SET status = %s, updated_at = %s WHERE id = %s",
                (ConvocationStatus.AUDIT_COMPLETE, datetime.now(timezone.utc), convocation_id),
            )
        ])

        DomainEventBus.publish(DomainEvent(
            event_type="convocation.audit_complete",
            org_id=org_id,
            entity_type="convocation_event",
            entity_id=convocation_id,
            actor_id=actor_id,
            payload={
                "convocation_id": convocation_id,
                "eligible_count": eligible_count,
                "ineligible_count": ineligible_count,
                "total_audited": total_audited,
            },
        ))

        logger.info(
            "ConvocationService: audit complete for %s — %d eligible / %d ineligible",
            convocation_id, eligible_count, ineligible_count,
        )

        return {
            "convocation_id": convocation_id,
            "total_audited": total_audited,
            "eligible_count": eligible_count,
            "ineligible_count": ineligible_count,
        }

    # ------------------------------------------------------------------ #
    # compute_gold_medals
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_gold_medals(
        convocation_id: str,
        org_id: str,
        actor_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Compute gold medal winners per program.

        Policy-driven: 'convocation.gold_medal_exclude_grace' controls whether
        cgpa_without_grace or cgpa is used for ranking (R1).
        """
        rows = execute_query(
            "SELECT * FROM convocation_events WHERE id = %s AND org_id = %s",
            (convocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Convocation {convocation_id} not found")
        convocation = rows[0]

        if convocation["status"] != ConvocationStatus.AUDIT_COMPLETE:
            raise BusinessRuleViolation(
                f"Gold medals can only be computed when convocation is AUDIT_COMPLETE; "
                f"current: {convocation['status']}"
            )

        # Policy: exclude grace marks from gold medal ranking (R1)
        gold_medal_exclude_grace = str(
            policy_engine.get_value(
                "convocation.gold_medal_exclude_grace",
                org_id,
                default="true",
            )
        ).lower() in ("true", "1", "yes")

        # Find the top student per program among eligible graduates
        winners = execute_query(
            """
            SELECT DISTINCT ON (program_id) student_id, program_id,
                   cgpa_without_grace, cgpa
            FROM convocation_degree_audits
            WHERE convocation_id = %s AND eligible_for_degree = TRUE
            ORDER BY program_id, cgpa_without_grace DESC
            """,
            (convocation_id,),
        )

        if not winners:
            return []

        now = datetime.now(timezone.utc)
        medal_inserts = []
        audit_updates = []
        medal_records = []

        for winner in winners:
            medal_id = str(uuid4())
            effective_cgpa = (
                float(winner["cgpa_without_grace"] or 0)
                if gold_medal_exclude_grace
                else float(winner["cgpa"] or 0)
            )

            medal_inserts.append((
                """
                INSERT INTO gold_medal_computations
                    (id, convocation_id, student_id, program_id,
                     cgpa_used, cgpa_without_grace, exclude_grace_applied,
                     computed_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (convocation_id, program_id) DO UPDATE
                    SET student_id = EXCLUDED.student_id,
                        cgpa_used = EXCLUDED.cgpa_used,
                        cgpa_without_grace = EXCLUDED.cgpa_without_grace,
                        exclude_grace_applied = EXCLUDED.exclude_grace_applied,
                        computed_at = EXCLUDED.computed_at
                """,
                (
                    medal_id,
                    convocation_id,
                    winner["student_id"],
                    winner["program_id"],
                    effective_cgpa,
                    float(winner["cgpa_without_grace"] or 0),
                    gold_medal_exclude_grace,
                    now,
                    now,
                ),
            ))

            audit_updates.append((
                """
                UPDATE convocation_degree_audits
                SET eligible_for_gold_medal = TRUE
                WHERE convocation_id = %s AND student_id = %s
                """,
                (convocation_id, winner["student_id"]),
            ))

            medal_records.append({
                "medal_id": medal_id,
                "convocation_id": convocation_id,
                "student_id": winner["student_id"],
                "program_id": winner["program_id"],
                "cgpa_used": effective_cgpa,
                "cgpa_without_grace": float(winner["cgpa_without_grace"] or 0),
                "exclude_grace_applied": gold_medal_exclude_grace,
                "computed_at": now.isoformat(),
            })

        execute_transaction(medal_inserts + audit_updates)

        logger.info(
            "ConvocationService: computed %d gold medals for convocation %s",
            len(medal_records), convocation_id,
        )

        return medal_records

    # ------------------------------------------------------------------ #
    # generate_seating
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_seating(
        convocation_id: str,
        org_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Generate sequential seat assignments for all eligible graduates.

        Seats are grouped by program then sorted by student name.
        Numbering pattern: {ROW_LETTER}{seat_in_row:02d} (e.g. A01, A02 … A10, B01 …).
        10 seats per row.
        """
        rows = execute_query(
            "SELECT * FROM convocation_events WHERE id = %s AND org_id = %s",
            (convocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Convocation {convocation_id} not found")
        convocation = rows[0]

        allowed = {
            ConvocationStatus.AUDIT_COMPLETE,
            ConvocationStatus.SEATING_GENERATED,
        }
        if convocation["status"] not in {s.value for s in allowed}:
            raise BusinessRuleViolation(
                f"Seating can only be generated when convocation is AUDIT_COMPLETE "
                f"or SEATING_GENERATED (re-generate); current: {convocation['status']}"
            )

        # Fetch eligible students ordered by program then student name
        eligible = execute_query(
            """
            SELECT cda.student_id, cda.program_id,
                   COALESCE(s.full_name, s.first_name || ' ' || s.last_name, s.id) AS student_name,
                   p.code AS program_code
            FROM convocation_degree_audits cda
            JOIN students s ON s.id = cda.student_id
            LEFT JOIN programs p ON p.id = cda.program_id
            WHERE cda.convocation_id = %s AND cda.eligible_for_degree = TRUE
            ORDER BY cda.program_id, student_name
            """,
            (convocation_id,),
        )

        if not eligible:
            return {"seats_generated": 0, "convocation_id": convocation_id}

        now = datetime.now(timezone.utc)
        seats_per_row = 10
        seating_inserts = []

        # Delete any existing seating for idempotent re-generation
        execute_transaction([
            (
                "DELETE FROM convocation_seating WHERE convocation_id = %s",
                (convocation_id,),
            )
        ])

        for idx, student in enumerate(eligible):
            overall_seat = idx + 1  # 1-based
            row_index = (overall_seat - 1) // seats_per_row       # 0-based row
            seat_in_row = ((overall_seat - 1) % seats_per_row) + 1  # 1-based within row

            # Row label: A–Z, then AA, AB … (simple alphabetic)
            if row_index < 26:
                row_label = chr(ord("A") + row_index)
            else:
                first = chr(ord("A") + (row_index // 26) - 1)
                second = chr(ord("A") + (row_index % 26))
                row_label = first + second

            seat_number = f"{row_label}{seat_in_row:02d}"
            seat_id = str(uuid4())
            program_code = student.get("program_code") or student["program_id"][:8].upper()

            seating_inserts.append((
                """
                INSERT INTO convocation_seating
                    (id, convocation_id, student_id, program_id,
                     seat_number, program_code, overall_position,
                     assigned_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    seat_id,
                    convocation_id,
                    student["student_id"],
                    student["program_id"],
                    seat_number,
                    program_code,
                    overall_seat,
                    now,
                    now,
                ),
            ))

        if seating_inserts:
            execute_transaction(seating_inserts)

        execute_transaction([
            (
                "UPDATE convocation_events SET status = %s, updated_at = %s WHERE id = %s",
                (ConvocationStatus.SEATING_GENERATED, datetime.now(timezone.utc), convocation_id),
            )
        ])

        DomainEventBus.publish(DomainEvent(
            event_type="convocation.seating_generated",
            org_id=org_id,
            entity_type="convocation_event",
            entity_id=convocation_id,
            actor_id=actor_id,
            payload={
                "convocation_id": convocation_id,
                "seats_generated": len(seating_inserts),
            },
        ))

        logger.info(
            "ConvocationService: seating generated — %d seats for convocation %s",
            len(seating_inserts), convocation_id,
        )

        return {
            "seats_generated": len(seating_inserts),
            "convocation_id": convocation_id,
        }

    # ------------------------------------------------------------------ #
    # get_convocation
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_convocation(convocation_id: str, org_id: str) -> Dict[str, Any]:
        """Fetch a convocation with audit summary stats and gold medal count."""
        rows = execute_query(
            "SELECT * FROM convocation_events WHERE id = %s AND org_id = %s",
            (convocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Convocation {convocation_id} not found")
        convocation = dict(rows[0])

        # Audit summary
        audit_summary = execute_query(
            """
            SELECT
                COUNT(*) AS total_audited,
                COUNT(CASE WHEN eligible_for_degree THEN 1 END) AS eligible_count,
                COUNT(CASE WHEN NOT eligible_for_degree THEN 1 END) AS ineligible_count,
                COUNT(CASE WHEN eligible_for_distinction THEN 1 END) AS distinction_count,
                COUNT(CASE WHEN eligible_for_gold_medal THEN 1 END) AS gold_medal_count
            FROM convocation_degree_audits
            WHERE convocation_id = %s
            """,
            (convocation_id,),
        )
        convocation["audit_summary"] = dict(audit_summary[0]) if audit_summary else {}

        # Gold medals
        medals = execute_query(
            "SELECT * FROM gold_medal_computations WHERE convocation_id = %s ORDER BY program_id",
            (convocation_id,),
        )
        convocation["gold_medals"] = [dict(m) for m in medals]

        return convocation

    # ------------------------------------------------------------------ #
    # list_convocations
    # ------------------------------------------------------------------ #

    @staticmethod
    def list_convocations(org_id: str) -> List[Dict[str, Any]]:
        """List all convocation events for the organisation."""
        rows = execute_query(
            """
            SELECT * FROM convocation_events
            WHERE org_id = %s
            ORDER BY ceremony_date DESC
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]
