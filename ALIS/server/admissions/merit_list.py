"""
P8 — Merit List + Waitlist Engine (Stage 6)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Entity) + Layer 2 (Composite Scoring) + Layer 4 (Seat Locks)

Manages the competitive selection and seat allocation pipeline:
  - Seat matrix: authoritative seat counts per program × category × intake
  - Merit list policy: configurable composite score formula
  - Merit list generation: ranked ordered list with composite scores
  - Waitlist: depth-based waitlist with activation mechanism

Merit Formula (policy-driven, configurable per program):
    composite = (academic_pct × w_acad) + (entrance_score × w_ent)
              + (interview_score × w_int) + diversity_bonus

Merit List Lifecycle:
    DRAFT → UNDER_REVIEW → APPROVED → PUBLISHED → SUPERSEDED

Seat Allocation:
    MERIT_LISTED state transition updates filled_seats atomically on acceptance.
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
from server.db_service import execute_query, execute_transaction, safe_identifier

logger = logging.getLogger(__name__)

_MERIT_LIST_TRANSITIONS = {
    "DRAFT": {"UNDER_REVIEW", "PUBLISHED"},
    "UNDER_REVIEW": {"APPROVED", "DRAFT"},
    "APPROVED": {"PUBLISHED"},
    "PUBLISHED": {"SUPERSEDED"},
    "SUPERSEDED": set(),
}

_ENTRY_STATUS_OFFER_TRANSITIONS = {
    "PENDING": {"OFFER_SENT"},
    "OFFER_SENT": {"ACCEPTED", "DECLINED", "EXPIRED"},
    "ACCEPTED": set(),
    "DECLINED": set(),
    "EXPIRED": set(),
    "WAITLIST_ACTIVATED": {"OFFER_SENT"},
}


# =============================================================================
# Pydantic Models
# =============================================================================

class SeatMatrixCreate(BaseModel):
    program_name: str = Field(..., min_length=2, max_length=200)
    specialization: Optional[str] = None
    intake_batch: str = Field(..., min_length=2, max_length=50)
    category: str = Field(
        default="GENERAL",
        description="GENERAL | SC | ST | OBC_NCL | EWS | PWD | NRI | MANAGEMENT_QUOTA"
    )
    total_seats: int = Field(..., ge=1, le=10000)


class SeatMatrixRead(BaseModel):
    id: str
    org_id: str
    program_name: str
    specialization: Optional[str] = None
    intake_batch: str
    category: str
    total_seats: int
    filled_seats: int
    blocked_seats: int
    available_seats: int = 0  # computed
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(
            self, "available_seats",
            max(0, self.total_seats - self.filled_seats - self.blocked_seats)
        )


class MeritListPolicyCreate(BaseModel):
    program_name: str = Field(..., min_length=2, max_length=200)
    intake_batch: str = Field(..., min_length=2, max_length=50)
    formula: Dict[str, float] = Field(
        ...,
        description='{"academic_pct": 0.35, "entrance_score": 0.45, "interview_score": 0.15, "diversity_bonus": 0.05}'
    )
    tiebreaker_order: List[str] = Field(
        default_factory=lambda: ["academic_pct", "entrance_score"],
        description='["academic_pct", "entrance_score", "age"]'
    )
    waitlist_depth_factor: float = Field(default=1.5, ge=1.0, le=5.0)


class MeritListPolicyRead(BaseModel):
    id: str
    org_id: str
    program_name: str
    intake_batch: str
    formula: Dict[str, Any]
    tiebreaker_order: List[str]
    waitlist_depth_factor: float
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_by: str
    created_at: datetime


class MeritListGenerateRequest(BaseModel):
    program_name: str
    intake_batch: str
    category: str = "GENERAL"
    list_type: str = Field(
        default="MERIT",
        description="MERIT | WAITLIST | MANAGEMENT_QUOTA | NRI"
    )
    specialization: Optional[str] = None


class MeritListRead(BaseModel):
    id: str
    org_id: str
    program_name: str
    specialization: Optional[str] = None
    intake_batch: str
    category: str
    list_type: str
    version: int
    status: str
    cutoff_score: Optional[float] = None
    total_entries: int
    published_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    generated_by: str
    created_at: datetime


class MeritListEntryRead(BaseModel):
    id: str
    org_id: str
    merit_list_id: str
    applicant_id: str
    rank: int
    composite_score: float
    score_breakdown: Optional[Dict[str, Any]] = None
    status: str
    offer_sent_at: Optional[datetime] = None
    response_deadline: Optional[datetime] = None


class WaitlistEntryRead(BaseModel):
    id: str
    org_id: str
    merit_list_id: str
    applicant_id: str
    waitlist_rank: int
    composite_score: float
    status: str
    activated_at: Optional[datetime] = None
    notification_sent_at: Optional[datetime] = None
    response_deadline: Optional[datetime] = None


# =============================================================================
# SEAT MATRIX SERVICE
# =============================================================================

class SeatMatrixService:

    @classmethod
    def create(
        cls,
        request: SeatMatrixCreate,
        org_id: str,
        actor_id: str,
    ) -> SeatMatrixRead:
        """Create a seat matrix entry. Unique on (org, program, intake, category)."""
        matrix_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO seat_matrix (
                    id, org_id, program_name, specialization, intake_batch,
                    category, total_seats, filled_seats, blocked_seats,
                    created_by, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (org_id, program_name, intake_batch, category)
                DO UPDATE SET total_seats = EXCLUDED.total_seats, updated_at = NOW()
                """,
                (
                    matrix_id, org_id,
                    request.program_name, request.specialization,
                    request.intake_batch, request.category,
                    request.total_seats, 0, 0,
                    actor_id, now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="seat_matrix",
            entity_id=matrix_id,
            org_id=org_id,
            module="M1",
            wizard="Merit List",
            success=True,
            metadata={
                "program": request.program_name,
                "category": request.category,
                "total_seats": request.total_seats,
            },
        )
        return cls.get(org_id, request.program_name, request.intake_batch, request.category)

    @classmethod
    def get(
        cls,
        org_id: str,
        program_name: str,
        intake_batch: str,
        category: str = "GENERAL",
    ) -> SeatMatrixRead:
        rows = execute_query(
            "SELECT * FROM seat_matrix "
            "WHERE org_id = %s AND program_name = %s AND intake_batch = %s AND category = %s",
            (org_id, program_name, intake_batch, category),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Seat matrix not found for {program_name}/{intake_batch}/{category}."
            )
        return SeatMatrixRead(**rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        program_name: Optional[str] = None,
        intake_batch: Optional[str] = None,
    ) -> List[SeatMatrixRead]:
        conditions = ["org_id = %s"]
        params: list = [org_id]
        if program_name:
            conditions.append("program_name = %s")
            params.append(program_name)
        if intake_batch:
            conditions.append("intake_batch = %s")
            params.append(intake_batch)
        rows = execute_query(
            f"SELECT * FROM seat_matrix WHERE {' AND '.join(conditions)} "
            "ORDER BY program_name, category",
            tuple(params),
        )
        return [SeatMatrixRead(**r) for r in rows]

    @classmethod
    def allocate_seat(
        cls,
        org_id: str,
        program_name: str,
        intake_batch: str,
        category: str,
    ) -> bool:
        """
        Atomically allocate one seat (filled_seats + 1).

        Returns True if allocation succeeded, False if no seats available.
        """
        result = execute_query(
            """
            UPDATE seat_matrix
            SET filled_seats = filled_seats + 1, updated_at = NOW()
            WHERE org_id = %s AND program_name = %s AND intake_batch = %s
              AND category = %s
              AND filled_seats + blocked_seats < total_seats
            RETURNING id
            """,
            (org_id, program_name, intake_batch, category),
        )
        return bool(result)


# =============================================================================
# MERIT LIST POLICY SERVICE
# =============================================================================

class MeritListPolicyService:

    @classmethod
    def create(
        cls,
        request: MeritListPolicyCreate,
        org_id: str,
        actor_id: str,
    ) -> MeritListPolicyRead:
        # Validate formula weights sum to ~1.0
        total_weight = sum(request.formula.values())
        if not (0.99 <= total_weight <= 1.01):
            raise BusinessRuleViolation(
                message=f"Merit formula weights must sum to 1.0. "
                        f"Current sum: {total_weight:.4f}",
                details={"formula": request.formula, "sum": total_weight},
            )

        policy_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO merit_list_policies (
                    id, org_id, program_name, intake_batch,
                    formula, tiebreaker_order, waitlist_depth_factor,
                    created_by, created_at
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                ON CONFLICT (org_id, program_name, intake_batch)
                DO UPDATE SET
                    formula = EXCLUDED.formula,
                    tiebreaker_order = EXCLUDED.tiebreaker_order,
                    waitlist_depth_factor = EXCLUDED.waitlist_depth_factor
                """,
                (
                    policy_id, org_id,
                    request.program_name, request.intake_batch,
                    json.dumps(request.formula),
                    json.dumps(request.tiebreaker_order),
                    request.waitlist_depth_factor,
                    actor_id, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="merit_list_policy",
            entity_id=policy_id,
            org_id=org_id,
            module="M1",
            wizard="Merit List",
            success=True,
            metadata={
                "program": request.program_name,
                "formula": request.formula,
            },
        )
        return cls.get(org_id, request.program_name, request.intake_batch)

    @classmethod
    def get(
        cls, org_id: str, program_name: str, intake_batch: str
    ) -> MeritListPolicyRead:
        rows = execute_query(
            "SELECT * FROM merit_list_policies "
            "WHERE org_id = %s AND program_name = %s AND intake_batch = %s",
            (org_id, program_name, intake_batch),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Merit policy not found for {program_name}/{intake_batch}."
            )
        row = rows[0]
        # Parse JSONB fields
        for field in ("formula", "tiebreaker_order"):
            val = row.get(field)
            if isinstance(val, str):
                row[field] = json.loads(val)
        return MeritListPolicyRead(**row)


# =============================================================================
# MERIT LIST SERVICE
# =============================================================================

class MeritListService:

    @classmethod
    def generate(
        cls,
        request: MeritListGenerateRequest,
        org_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Generate a merit list for a program/batch/category.

        Algorithm:
        1. Fetch merit policy for composite formula
        2. Pull all ELIGIBLE/ASSESSMENT_COMPLETE applicants for the program
        3. Calculate composite score per applicant using policy formula
        4. Rank by composite score descending
        5. Create merit_list header + merit_list_entries rows
        6. Generate waitlist entries up to (total_seats × waitlist_depth_factor)

        Returns:
            {merit_list_id, total_ranked, total_merit, total_waitlist}
        """
        # Fetch policy
        policy = MeritListPolicyService.get(org_id, request.program_name, request.intake_batch)

        # Fetch seat count for waitlist depth
        try:
            seat_row = SeatMatrixService.get(
                org_id, request.program_name, request.intake_batch, request.category
            )
            total_seats = seat_row.total_seats
        except BusinessRuleViolation:
            total_seats = 60  # default if matrix not set up

        # Fetch eligible applicants (those who have reached assessment complete or eligible)
        eligible_rows = execute_query(
            """
            SELECT DISTINCT a.id, a.category,
                   COALESCE(aq.percentage, 0) AS academic_pct,
                   COALESCE(ees.percentile, 0) AS entrance_score
            FROM applicants a
            LEFT JOIN academic_qualifications aq
                ON aq.applicant_id = a.id AND aq.level = 'CLASS_12'
            LEFT JOIN entrance_exam_scores ees
                ON ees.applicant_id = a.id
            WHERE a.org_id = %s
              AND a.intended_program = %s
              AND a.status IN ('ELIGIBLE', 'ASSESSMENT_COMPLETE', 'DOCUMENTS_VERIFIED')
            ORDER BY a.id
            """,
            (org_id, request.program_name),
        )

        if not eligible_rows:
            raise BusinessRuleViolation(
                message=f"No eligible applicants found for {request.program_name}/{request.intake_batch}."
            )

        # Calculate composite scores
        formula = policy.formula if isinstance(policy.formula, dict) else {}
        w_acad = formula.get("academic_pct", 0.4)
        w_ent = formula.get("entrance_score", 0.4)
        w_int = formula.get("interview_score", 0.2)
        w_div = formula.get("diversity_bonus", 0.0)

        scored: List[Dict[str, Any]] = []
        for row in eligible_rows:
            acad = float(row.get("academic_pct") or 0) / 10.0  # normalize 100→10
            entrance = float(row.get("entrance_score") or 0) / 10.0
            composite = (acad * w_acad) + (entrance * w_ent) + (0 * w_int) + (0 * w_div)
            scored.append({
                "applicant_id": str(row["id"]),
                "composite_score": round(composite, 4),
                "score_breakdown": {
                    "academic_pct": acad,
                    "entrance_score": entrance,
                    "interview_score": 0,
                },
            })

        # Sort by composite descending
        scored.sort(key=lambda x: x["composite_score"], reverse=True)

        # Create merit list header (supersede existing published if any)
        cls._supersede_existing(org_id, request.program_name, request.intake_batch, request.category)

        version = cls._next_version(org_id, request.program_name, request.intake_batch, request.category)
        merit_list_id = str(uuid4())
        now = datetime.now(timezone.utc)
        cutoff = scored[total_seats - 1]["composite_score"] if len(scored) >= total_seats else (
            scored[-1]["composite_score"] if scored else 0
        )

        execute_transaction([
            (
                """
                INSERT INTO merit_lists (
                    id, org_id, program_name, specialization, intake_batch,
                    category, list_type, version, status, cutoff_score,
                    total_entries, generated_by, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    merit_list_id, org_id,
                    request.program_name, request.specialization,
                    request.intake_batch, request.category,
                    request.list_type, version, "DRAFT",
                    cutoff, len(scored),
                    actor_id, now,
                ),
            )
        ])

        # Insert merit list entries and waitlist entries
        merit_depth = total_seats
        waitlist_depth = int(total_seats * policy.waitlist_depth_factor)

        merit_inserts = []
        waitlist_inserts = []

        for i, s in enumerate(scored):
            rank = i + 1
            if rank <= merit_depth:
                merit_inserts.append((
                    """
                    INSERT INTO merit_list_entries
                        (id, org_id, merit_list_id, applicant_id, rank,
                         composite_score, score_breakdown, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT (merit_list_id, applicant_id) DO NOTHING
                    """,
                    (
                        str(uuid4()), org_id, merit_list_id,
                        s["applicant_id"], rank,
                        s["composite_score"],
                        json.dumps(s["score_breakdown"]),
                        "PENDING",
                    ),
                ))
            elif rank <= merit_depth + waitlist_depth:
                waitlist_rank = rank - merit_depth
                waitlist_inserts.append((
                    """
                    INSERT INTO waitlist_entries
                        (id, org_id, merit_list_id, applicant_id, waitlist_rank,
                         composite_score, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (merit_list_id, applicant_id) DO NOTHING
                    """,
                    (
                        str(uuid4()), org_id, merit_list_id,
                        s["applicant_id"], waitlist_rank,
                        s["composite_score"], "WAITING",
                    ),
                ))

        if merit_inserts or waitlist_inserts:
            execute_transaction(merit_inserts + waitlist_inserts)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="merit_list",
            entity_id=merit_list_id,
            org_id=org_id,
            module="M1",
            wizard="Merit List",
            success=True,
            metadata={
                "program": request.program_name,
                "intake_batch": request.intake_batch,
                "total_merit": min(len(scored), merit_depth),
                "total_waitlist": max(0, min(len(scored) - merit_depth, waitlist_depth)),
                "cutoff": cutoff,
            },
        )

        logger.info(
            "Merit list generated: %s [program=%s batch=%s merit=%d waitlist=%d]",
            merit_list_id, request.program_name, request.intake_batch,
            min(len(scored), merit_depth),
            max(0, min(len(scored) - merit_depth, waitlist_depth)),
        )

        return {
            "merit_list_id": merit_list_id,
            "total_ranked": len(scored),
            "total_merit": min(len(scored), merit_depth),
            "total_waitlist": max(0, min(len(scored) - merit_depth, waitlist_depth)),
            "cutoff_score": cutoff,
            "version": version,
        }

    @classmethod
    def get(cls, merit_list_id: str, org_id: str) -> MeritListRead:
        rows = execute_query(
            "SELECT * FROM merit_lists WHERE id = %s AND org_id = %s",
            (merit_list_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Merit list '{merit_list_id}' not found.")
        return MeritListRead(**rows[0])

    @classmethod
    def list_entries(cls, merit_list_id: str, org_id: str) -> List[MeritListEntryRead]:
        rows = execute_query(
            "SELECT * FROM merit_list_entries WHERE merit_list_id = %s AND org_id = %s "
            "ORDER BY rank ASC",
            (merit_list_id, org_id),
        )
        return [MeritListEntryRead(**r) for r in rows]

    @classmethod
    def list_waitlist(cls, merit_list_id: str, org_id: str) -> List[WaitlistEntryRead]:
        rows = execute_query(
            "SELECT * FROM waitlist_entries WHERE merit_list_id = %s AND org_id = %s "
            "ORDER BY waitlist_rank ASC",
            (merit_list_id, org_id),
        )
        return [WaitlistEntryRead(**r) for r in rows]

    @classmethod
    def update_status(
        cls,
        merit_list_id: str,
        org_id: str,
        new_status: str,
        actor_id: str,
    ) -> MeritListRead:
        rows = execute_query(
            "SELECT status FROM merit_lists WHERE id = %s AND org_id = %s",
            (merit_list_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(message=f"Merit list '{merit_list_id}' not found.")

        current = rows[0]["status"]
        allowed = _MERIT_LIST_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise BusinessRuleViolation(
                message=f"Illegal merit list transition: {current} → {new_status}",
                details={"allowed": list(allowed)},
            )

        updates: Dict[str, Any] = {"status": new_status}
        if new_status == "PUBLISHED":
            updates["published_at"] = datetime.now(timezone.utc)
        if new_status == "APPROVED":
            updates["approved_by"] = actor_id
            updates["approved_at"] = datetime.now(timezone.utc)

        set_clause = ", ".join(f"{safe_identifier(k)} = %s" for k in updates)
        execute_transaction([
            (
                f"UPDATE merit_lists SET {set_clause} WHERE id = %s AND org_id = %s",
                (*updates.values(), merit_list_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            entity_type="merit_list",
            entity_id=merit_list_id,
            org_id=org_id,
            module="M1",
            wizard="Merit List",
            success=True,
            metadata={"from": current, "to": new_status},
        )
        return cls.get(merit_list_id, org_id)

    @classmethod
    def activate_waitlist_entry(
        cls,
        merit_list_id: str,
        applicant_id: str,
        org_id: str,
        actor_id: str,
    ) -> WaitlistEntryRead:
        """
        Activate a waitlist entry when a merit list seat becomes available.

        Transitions the top WAITING entry for this applicant → ACTIVATED.
        Also adds a MERIT_LISTED entry for the applicant.
        """
        rows = execute_query(
            "SELECT * FROM waitlist_entries "
            "WHERE merit_list_id = %s AND applicant_id = %s AND org_id = %s AND status = 'WAITING'",
            (merit_list_id, applicant_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"No active waitlist entry for applicant '{applicant_id}' in merit list '{merit_list_id}'."
            )

        now = datetime.now(timezone.utc)
        entry_id = rows[0]["id"]

        execute_transaction([
            (
                "UPDATE waitlist_entries SET status = 'ACTIVATED', activated_at = %s "
                "WHERE id = %s AND org_id = %s",
                (now, entry_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="waitlist_entry",
            entity_id=entry_id,
            org_id=org_id,
            module="M1",
            wizard="Merit List",
            success=True,
            metadata={"applicant_id": applicant_id, "action": "waitlist_activated"},
        )

        updated = execute_query(
            "SELECT * FROM waitlist_entries WHERE id = %s",
            (entry_id,),
        )
        return WaitlistEntryRead(**updated[0])

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _supersede_existing(
        cls, org_id: str, program_name: str, intake_batch: str, category: str
    ) -> None:
        execute_transaction([
            (
                """
                UPDATE merit_lists SET status = 'SUPERSEDED'
                WHERE org_id = %s AND program_name = %s
                  AND intake_batch = %s AND category = %s
                  AND status = 'PUBLISHED'
                """,
                (org_id, program_name, intake_batch, category),
            )
        ])

    @classmethod
    def _next_version(
        cls, org_id: str, program_name: str, intake_batch: str, category: str
    ) -> int:
        rows = execute_query(
            "SELECT COALESCE(MAX(version), 0) AS v FROM merit_lists "
            "WHERE org_id = %s AND program_name = %s AND intake_batch = %s AND category = %s",
            (org_id, program_name, intake_batch, category),
        )
        return (rows[0]["v"] if rows else 0) + 1
