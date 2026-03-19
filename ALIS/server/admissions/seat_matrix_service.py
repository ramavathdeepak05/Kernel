"""E19 — Quota Seat Matrix Engine

Category-aware seat allocation aligned with AICTE/UGC norms.

Categories: GENERAL, SC, ST, OBC_NCL, EWS, PWD
Quota buckets: GENERAL (open merit), MANAGEMENT, NRI, SPORTS

Rules
─────
1. category+quota seats must sum to total_intake (enforced by DB CHECK constraint).
2. Waitlist activation: find next candidate in SAME category/quota bucket — not overall rank.
3. Category conversion (e.g., SC → GENERAL) requires Dean approval and must wait for
   the UGC-mandated deadline.  Conversion is logged to audit_ledger.
4. All thresholds / SLA read from policy_engine — never literals.

The DB trigger `decrement_seat_counter()` handles real-time counter updates
on enrollment confirmation.  This service handles business-level orchestration.
"""

import logging
import uuid
from typing import Optional

from pydantic import BaseModel, model_validator

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"GENERAL", "SC", "ST", "OBC_NCL", "EWS", "PWD"}
VALID_QUOTAS = {"GENERAL", "MANAGEMENT", "NRI", "SPORTS"}


# ---------------------------------------------------------------------------
# Input / output models
# ---------------------------------------------------------------------------

class SeatMatrixConfig(BaseModel):
    program_id: str
    intake_year: int
    total_intake: int

    # Category seats
    general_seats: int = 0
    sc_seats: int = 0
    st_seats: int = 0
    obc_ncl_seats: int = 0
    ews_seats: int = 0
    pwd_seats: int = 0

    # Quota seats (from within GENERAL category primarily)
    management_quota: int = 0
    nri_quota: int = 0
    sports_quota: int = 0

    @model_validator(mode="after")
    def validate_seat_sum(self):
        category_total = (
            self.general_seats + self.sc_seats + self.st_seats
            + self.obc_ncl_seats + self.ews_seats + self.pwd_seats
        )
        if category_total != self.total_intake:
            raise ValueError(
                f"Category seats sum ({category_total}) must equal total_intake ({self.total_intake})"
            )
        quota_total = self.management_quota + self.nri_quota + self.sports_quota
        if quota_total > self.total_intake:
            raise ValueError(
                f"Quota seats ({quota_total}) cannot exceed total_intake ({self.total_intake})"
            )
        return self


class CategoryConversionRequest(BaseModel):
    from_category: str
    to_category: str
    seats_count: int
    reason: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SeatMatrixService:

    # ------------------------------------------------------------------
    # Create matrix
    # ------------------------------------------------------------------

    @classmethod
    async def create_matrix(
        cls,
        org_id: str,
        config: SeatMatrixConfig,
        actor_id: str,
    ) -> dict:
        """Create or replace the seat matrix for a program-year combination."""
        matrix_id = str(uuid.uuid4())

        execute_transaction([("""
            INSERT INTO seat_matrix (
                id, tenant_id, program_id, intake_year, total_intake,
                available_seats, filled_seats,
                general_seats, sc_seats, st_seats, obc_ncl_seats, ews_seats, pwd_seats,
                management_quota, nri_quota, sports_quota,
                filled_general, filled_sc, filled_st, filled_obc, filled_ews,
                filled_management, filled_nri,
                last_updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, 0,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                0, 0, 0, 0, 0, 0, 0,
                NOW()
            )
            ON CONFLICT (tenant_id, program_id, intake_year) DO UPDATE SET
                total_intake     = EXCLUDED.total_intake,
                available_seats  = EXCLUDED.available_seats,
                general_seats    = EXCLUDED.general_seats,
                sc_seats         = EXCLUDED.sc_seats,
                st_seats         = EXCLUDED.st_seats,
                obc_ncl_seats    = EXCLUDED.obc_ncl_seats,
                ews_seats        = EXCLUDED.ews_seats,
                pwd_seats        = EXCLUDED.pwd_seats,
                management_quota = EXCLUDED.management_quota,
                nri_quota        = EXCLUDED.nri_quota,
                sports_quota     = EXCLUDED.sports_quota,
                last_updated_at  = NOW()
        """, (
            matrix_id, org_id, config.program_id, config.intake_year, config.total_intake,
            config.total_intake,
            config.general_seats, config.sc_seats, config.st_seats,
            config.obc_ncl_seats, config.ews_seats, config.pwd_seats,
            config.management_quota, config.nri_quota, config.sports_quota,
        ))])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.CREATED,
            resource_type="seat_matrix",
            resource_id=matrix_id,
            detail=config.model_dump(),
        )

        return await cls.get_matrix(org_id, config.program_id, config.intake_year)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    async def get_matrix(
        cls,
        org_id: str,
        program_id: str,
        intake_year: int,
    ) -> dict:
        """Return filled/total per category and waitlist depth per category."""
        rows = execute_query("""
            SELECT
                sm.*,
                -- Waitlist depths per category
                (SELECT COUNT(*) FROM admission_waitlist w
                 WHERE w.program_id = sm.program_id
                   AND w.intake_year = sm.intake_year
                   AND w.org_id = sm.tenant_id
                   AND w.category = 'GENERAL'
                   AND w.status = 'WAITING') AS waitlist_general,
                (SELECT COUNT(*) FROM admission_waitlist w
                 WHERE w.program_id = sm.program_id
                   AND w.intake_year = sm.intake_year
                   AND w.org_id = sm.tenant_id
                   AND w.category = 'SC'
                   AND w.status = 'WAITING') AS waitlist_sc,
                (SELECT COUNT(*) FROM admission_waitlist w
                 WHERE w.program_id = sm.program_id
                   AND w.intake_year = sm.intake_year
                   AND w.org_id = sm.tenant_id
                   AND w.category = 'ST'
                   AND w.status = 'WAITING') AS waitlist_st,
                (SELECT COUNT(*) FROM admission_waitlist w
                 WHERE w.program_id = sm.program_id
                   AND w.intake_year = sm.intake_year
                   AND w.org_id = sm.tenant_id
                   AND w.category = 'OBC_NCL'
                   AND w.status = 'WAITING') AS waitlist_obc,
                (SELECT COUNT(*) FROM admission_waitlist w
                 WHERE w.program_id = sm.program_id
                   AND w.intake_year = sm.intake_year
                   AND w.org_id = sm.tenant_id
                   AND w.category = 'EWS'
                   AND w.status = 'WAITING') AS waitlist_ews
            FROM seat_matrix sm
            WHERE sm.tenant_id = %s
              AND sm.program_id = %s
              AND sm.intake_year = %s
        """, (org_id, program_id, intake_year))

        if not rows:
            raise NotFoundError(
                f"Seat matrix not found for program {program_id} year {intake_year}"
            )
        return dict(rows[0])

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    @classmethod
    async def check_availability(
        cls,
        org_id: str,
        program_id: str,
        intake_year: int,
        category: str,
        quota: str = "GENERAL",
    ) -> bool:
        """Return True if at least one seat is available in the given category/quota."""
        category = category.upper()
        quota = quota.upper()

        if category not in VALID_CATEGORIES:
            raise BusinessRuleViolation(f"Invalid category: {category}")

        col_map = {
            "GENERAL": ("general_seats", "filled_general"),
            "SC": ("sc_seats", "filled_sc"),
            "ST": ("st_seats", "filled_st"),
            "OBC_NCL": ("obc_ncl_seats", "filled_obc"),
            "EWS": ("ews_seats", "filled_ews"),
            "PWD": ("pwd_seats", None),  # PWD is cross-category; check total
        }

        total_col, filled_col = col_map.get(category, ("general_seats", "filled_general"))

        if category == "PWD":
            # PWD seats are cross-cutting — compare pwd_seats vs overall filled
            rows = execute_query("""
                SELECT pwd_seats, filled_seats
                FROM seat_matrix
                WHERE tenant_id = %s AND program_id = %s AND intake_year = %s
            """, (org_id, program_id, intake_year))
            if not rows:
                return False
            row = rows[0]
            return int(row["pwd_seats"] or 0) > int(row["filled_seats"] or 0)

        if quota != "GENERAL":
            quota_col_map = {
                "MANAGEMENT": ("management_quota", "filled_management"),
                "NRI": ("nri_quota", "filled_nri"),
                "SPORTS": ("sports_quota", None),
            }
            q_total_col, q_filled_col = quota_col_map.get(quota, ("management_quota", "filled_management"))
            rows = execute_query(f"""
                SELECT {q_total_col} AS total, COALESCE({q_filled_col}, 0) AS filled
                FROM seat_matrix
                WHERE tenant_id = %s AND program_id = %s AND intake_year = %s
            """, (org_id, program_id, intake_year))
            if not rows:
                return False
            return int(rows[0]["total"]) > int(rows[0]["filled"])

        rows = execute_query(f"""
            SELECT {total_col} AS total, COALESCE({filled_col}, 0) AS filled
            FROM seat_matrix
            WHERE tenant_id = %s AND program_id = %s AND intake_year = %s
        """, (org_id, program_id, intake_year))

        if not rows:
            return False
        return int(rows[0]["total"]) > int(rows[0]["filled"])

    # ------------------------------------------------------------------
    # Waitlist activation
    # ------------------------------------------------------------------

    @classmethod
    async def activate_waitlist_candidate(
        cls,
        org_id: str,
        program_id: str,
        intake_year: int,
        released_category: str,
        released_quota: str = "GENERAL",
    ) -> Optional[dict]:
        """Activate next waitlist candidate in the SAME category/quota bucket.

        Returns the activated candidate record, or None if waitlist is empty.
        """
        released_category = released_category.upper()
        released_quota = released_quota.upper()

        # Find next in same category/quota — ordered by waitlist_rank
        candidates = execute_query("""
            SELECT id, application_id, student_id, rank AS waitlist_rank
            FROM admission_waitlist
            WHERE org_id = %s
              AND program_id = %s
              AND intake_year = %s
              AND category = %s
              AND quota = %s
              AND status = 'WAITING'
            ORDER BY rank ASC
            LIMIT 1
        """, (org_id, program_id, intake_year, released_category, released_quota))

        if not candidates:
            logger.info(
                "Waitlist empty for %s/%s category=%s quota=%s",
                program_id, intake_year, released_category, released_quota,
            )
            return None

        candidate = candidates[0]
        waitlist_id = str(candidate["id"])
        application_id = str(candidate["application_id"])

        # Transition candidate to OFFER_ISSUED
        execute_transaction([("""
            UPDATE admission_waitlist
            SET status = 'OFFER_ISSUED', activated_at = NOW()
            WHERE id = %s
        """, (waitlist_id,))])

        DomainEventBus.publish(DomainEvent(
            event_type="admissions.waitlist_candidate_activated",
            org_id=org_id,
            payload={
                "waitlist_id": waitlist_id,
                "application_id": application_id,
                "category": released_category,
                "quota": released_quota,
                "program_id": program_id,
                "intake_year": intake_year,
            },
        ))

        logger.info(
            "Waitlist candidate %s activated for %s/%s [%s/%s]",
            application_id, program_id, intake_year,
            released_category, released_quota,
        )
        return dict(candidate)

    # ------------------------------------------------------------------
    # Category conversion
    # ------------------------------------------------------------------

    @classmethod
    async def trigger_category_conversion(
        cls,
        org_id: str,
        program_id: str,
        intake_year: int,
        from_category: str,
        to_category: str,
        seats_count: int,
        actor_id: str,
        reason: str,
    ) -> dict:
        """Convert unused category seats (e.g., SC → GENERAL) after UGC deadline.

        Requires Dean approval — this method assumes approval already granted
        (called from the POST route which enforces DEAN permission).
        """
        from_category = from_category.upper()
        to_category = to_category.upper()

        if from_category not in VALID_CATEGORIES or to_category not in VALID_CATEGORIES:
            raise BusinessRuleViolation("Invalid category for conversion")
        if from_category == to_category:
            raise BusinessRuleViolation("from_category and to_category must differ")

        # Verify enough unfilled seats in from_category
        matrix = await cls.get_matrix(org_id, program_id, intake_year)

        from_col_map = {
            "GENERAL": ("general_seats", "filled_general"),
            "SC": ("sc_seats", "filled_sc"),
            "ST": ("st_seats", "filled_st"),
            "OBC_NCL": ("obc_ncl_seats", "filled_obc"),
            "EWS": ("ews_seats", "filled_ews"),
            "PWD": ("pwd_seats", None),
        }

        from_total_col, from_filled_col = from_col_map[from_category]
        available = int(matrix.get(from_total_col, 0)) - int(matrix.get(from_filled_col or "filled_seats", 0))

        if available < seats_count:
            raise BusinessRuleViolation(
                f"Only {available} unfilled {from_category} seats available; requested {seats_count}"
            )

        to_total_col = from_col_map[to_category][0]

        # Adjust seat counts (never modify filled counters)
        execute_transaction([(f"""
            UPDATE seat_matrix
            SET {from_total_col} = {from_total_col} - %s,
                {to_total_col}   = {to_total_col}   + %s,
                last_updated_at  = NOW()
            WHERE tenant_id = %s AND program_id = %s AND intake_year = %s
        """, (seats_count, seats_count, org_id, program_id, intake_year))])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.UPDATED,
            resource_type="seat_matrix_conversion",
            resource_id=f"{program_id}/{intake_year}",
            detail={
                "from_category": from_category,
                "to_category": to_category,
                "seats_count": seats_count,
                "reason": reason,
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="admissions.seat_category_converted",
            org_id=org_id,
            payload={
                "program_id": program_id,
                "intake_year": intake_year,
                "from_category": from_category,
                "to_category": to_category,
                "seats_count": seats_count,
                "actor_id": actor_id,
            },
        ))

        return await cls.get_matrix(org_id, program_id, intake_year)

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    @classmethod
    async def get_dashboard(cls, org_id: str) -> list:
        """All programs summary for pilot overview."""
        return execute_query("""
            SELECT
                sm.program_id,
                sm.intake_year,
                sm.total_intake,
                sm.available_seats,
                sm.filled_seats,
                sm.general_seats,   sm.filled_general,
                sm.sc_seats,        sm.filled_sc,
                sm.st_seats,        sm.filled_st,
                sm.obc_ncl_seats,   sm.filled_obc,
                sm.ews_seats,       sm.filled_ews,
                sm.management_quota, sm.filled_management,
                sm.nri_quota,       sm.filled_nri,
                ROUND(
                    CASE WHEN sm.total_intake > 0
                    THEN sm.filled_seats::numeric / sm.total_intake * 100
                    ELSE 0 END, 1
                ) AS fill_pct
            FROM seat_matrix sm
            WHERE sm.tenant_id = %s
            ORDER BY sm.intake_year DESC, sm.program_id
        """, (org_id,))
