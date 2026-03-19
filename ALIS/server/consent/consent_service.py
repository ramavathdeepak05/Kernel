"""E21 — DPDP Consent Management Service

MODULE: Consent Management (E21)
LAYER: Layer 1 (Module Purpose) — data access requires explicit consent under DPDP Act 2023
ENTITY: ConsentRecord, ErasureRequest

Implements:
- give_consent   — UPSERT consent for one or more purposes
- withdraw_consent — mark consent as WITHDRAWN
- has_consent    — gate-check (True if GIVEN and not expired)
- request_erasure — right-to-erasure, emits USER_ERASURE_REQUESTED domain event
- mark_module_erased — module-by-module erasure acknowledgement
- reject_erasure — ADMIN rejection path

Hard Constraints:
- All methods are synchronous (psycopg2)
- execute_query for SELECTs, execute_transaction for writes
- %s placeholders throughout
- IDs are UUID strings
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import uuid4

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# All supported purposes — "ALL" is a wildcard covering every module.
PURPOSES = [
    "ADMISSIONS",
    "ACADEMICS",
    "FINANCE",
    "HR",
    "COMMUNICATIONS",
    "ANALYTICS",
    "ALL",
]

# Modules that participate in right-to-erasure.
# Each module's event handler must call mark_module_erased() when done.
ALL_MODULES = [
    "admissions",
    "academics",
    "examinations",
    "finance",
    "hr",
    "student_services",
    "communication",
    "reporting",
    "alumni",
]


def _row_to_dict(row) -> dict:
    """Normalise a psycopg2 RealDictRow into a plain dict with serialisable values."""
    if row is None:
        return {}
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


class ConsentService:
    """DPDP Consent Management — synchronous service."""

    PURPOSES = PURPOSES

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def get_consents(org_id: str, user_id: str) -> List[dict]:
        """Return all consent records for a user within a tenant."""
        rows = execute_query(
            """
            SELECT id, org_id, user_id::text, purpose, status,
                   given_at, withdrawn_at, expires_at,
                   ip_address::text, user_agent, metadata,
                   created_at, updated_at
            FROM consent_records
            WHERE org_id = %s AND user_id = %s::uuid
            ORDER BY purpose
            """,
            (org_id, user_id),
            tenant_id=org_id,
        )
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    def has_consent(org_id: str, user_id: str, purpose: str) -> bool:
        """
        Return True if the user has an active GIVEN consent for the given purpose
        (or for the ALL wildcard), and the record has not expired.
        """
        rows = execute_query(
            """
            SELECT id
            FROM consent_records
            WHERE org_id = %s
              AND user_id = %s::uuid
              AND purpose IN (%s, 'ALL')
              AND status = 'GIVEN'
              AND (expires_at IS NULL OR expires_at > NOW())
            LIMIT 1
            """,
            (org_id, user_id, purpose),
            tenant_id=org_id,
        )
        return bool(rows)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @staticmethod
    def give_consent(
        org_id: str,
        user_id: str,
        purposes: List[str],
        ip_address: str = None,
        user_agent: str = None,
    ) -> List[dict]:
        """
        UPSERT consent records for the requested purposes.

        Sets status = 'GIVEN', given_at = NOW() for each purpose.
        Uses INSERT … ON CONFLICT DO UPDATE so it is idempotent.
        """
        invalid = [p for p in purposes if p not in PURPOSES]
        if invalid:
            raise ValueError(f"Invalid consent purposes: {invalid}. Valid: {PURPOSES}")

        now = datetime.now(timezone.utc)
        statements = []
        for purpose in purposes:
            record_id = str(uuid4())
            statements.append((
                """
                INSERT INTO consent_records (
                    id, org_id, user_id, purpose, status,
                    given_at, withdrawn_at, ip_address, user_agent,
                    metadata, created_at, updated_at
                ) VALUES (
                    %s::uuid, %s, %s::uuid, %s, 'GIVEN',
                    %s, NULL, %s::inet, %s,
                    '{}', %s, %s
                )
                ON CONFLICT (org_id, user_id, purpose) DO UPDATE SET
                    status       = 'GIVEN',
                    given_at     = EXCLUDED.given_at,
                    withdrawn_at = NULL,
                    ip_address   = EXCLUDED.ip_address,
                    user_agent   = EXCLUDED.user_agent,
                    updated_at   = EXCLUDED.updated_at
                """,
                (
                    record_id, org_id, user_id, purpose,
                    now, ip_address, user_agent,
                    now, now,
                ),
            ))

        execute_transaction(statements, tenant_id=org_id)
        return ConsentService.get_consents(org_id, user_id)

    @staticmethod
    def withdraw_consent(
        org_id: str,
        user_id: str,
        purposes: List[str],
    ) -> List[dict]:
        """
        Withdraw consent for the requested purposes.

        Sets status = 'WITHDRAWN', withdrawn_at = NOW().
        Only affects records in GIVEN or PENDING status.
        """
        invalid = [p for p in purposes if p not in PURPOSES]
        if invalid:
            raise ValueError(f"Invalid consent purposes: {invalid}. Valid: {PURPOSES}")

        now = datetime.now(timezone.utc)
        statements = []
        for purpose in purposes:
            statements.append((
                """
                UPDATE consent_records
                SET status       = 'WITHDRAWN',
                    withdrawn_at = %s,
                    updated_at   = %s
                WHERE org_id  = %s
                  AND user_id  = %s::uuid
                  AND purpose  = %s
                  AND status  IN ('GIVEN', 'PENDING')
                """,
                (now, now, org_id, user_id, purpose),
            ))

        execute_transaction(statements, tenant_id=org_id)
        return ConsentService.get_consents(org_id, user_id)

    # ------------------------------------------------------------------
    # Erasure
    # ------------------------------------------------------------------

    @staticmethod
    def request_erasure(
        org_id: str,
        user_id: str,
        requested_by: str,
        reason: str = None,
    ) -> dict:
        """
        Create an erasure_requests row for a user (right-to-erasure under DPDP Act 2023).

        modules_queued is initialised to ALL_MODULES.
        due_by = NOW() + 30 days.
        Emits the USER_ERASURE_REQUESTED domain event.
        """
        erasure_id = str(uuid4())
        now = datetime.now(timezone.utc)
        due_by = now + timedelta(days=30)

        from psycopg2.extras import Json as PgJson  # type: ignore

        execute_transaction(
            [
                (
                    """
                    INSERT INTO erasure_requests (
                        id, org_id, user_id, requested_by, reason,
                        status, modules_queued, modules_done,
                        due_by, created_at, updated_at
                    ) VALUES (
                        %s::uuid, %s, %s::uuid, %s::uuid, %s,
                        'PENDING', %s, '{}',
                        %s, %s, %s
                    )
                    """,
                    (
                        erasure_id, org_id, user_id, requested_by, reason,
                        ALL_MODULES,
                        due_by, now, now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        # Emit domain event so every module can act asynchronously
        try:
            from server.core.domain_events import DomainEvent, DomainEventBus
            DomainEventBus.publish(DomainEvent(
                event_type="USER_ERASURE_REQUESTED",
                entity_type="erasure_request",
                entity_id=erasure_id,
                org_id=org_id,
                payload={
                    "user_id": user_id,
                    "requested_by": requested_by,
                    "reason": reason,
                    "due_by": due_by.isoformat(),
                    "modules_queued": ALL_MODULES,
                },
            ))
        except Exception:
            logger.warning(
                "ConsentService.request_erasure: failed to publish domain event "
                "(non-fatal — erasure row already written)",
                exc_info=True,
            )

        return ConsentService.get_erasure_status(org_id, user_id) or {}

    @staticmethod
    def get_erasure_status(org_id: str, user_id: str) -> Optional[dict]:
        """Return the most recent erasure request for a user, or None."""
        rows = execute_query(
            """
            SELECT id::text, org_id, user_id::text, requested_by::text,
                   reason, status, modules_queued, modules_done,
                   due_by, completed_at, rejected_at, rejection_reason,
                   created_at, updated_at
            FROM erasure_requests
            WHERE org_id = %s AND user_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (org_id, user_id),
            tenant_id=org_id,
        )
        if not rows:
            return None
        return _row_to_dict(rows[0])

    @staticmethod
    def mark_module_erased(erasure_id: str, module: str) -> None:
        """
        Mark a module as having completed its erasure obligations.

        Moves `module` from modules_queued → modules_done.
        If modules_queued becomes empty, transitions status → COMPLETED.
        """
        now = datetime.now(timezone.utc)
        # Use system-level transaction because this is called by internal
        # module workers that don't necessarily have a tenant ContextVar set.
        from server.db_service import execute_system_transaction
        execute_system_transaction(
            [
                (
                    """
                    UPDATE erasure_requests
                    SET modules_queued  = array_remove(modules_queued, %s),
                        modules_done    = array_append(modules_done, %s),
                        updated_at      = %s,
                        status          = CASE
                            WHEN array_remove(modules_queued, %s) = '{}'::text[]
                            THEN 'COMPLETED'
                            ELSE status
                        END,
                        completed_at    = CASE
                            WHEN array_remove(modules_queued, %s) = '{}'::text[]
                            THEN %s
                            ELSE completed_at
                        END
                    WHERE id = %s::uuid
                      AND status IN ('PENDING', 'IN_PROGRESS')
                    """,
                    (module, module, now, module, module, now, erasure_id),
                ),
                # Flip PENDING → IN_PROGRESS once work has started (idempotent)
                (
                    """
                    UPDATE erasure_requests
                    SET status     = 'IN_PROGRESS',
                        updated_at = %s
                    WHERE id = %s::uuid
                      AND status   = 'PENDING'
                      AND modules_queued != '{}'::text[]
                    """,
                    (now, erasure_id),
                ),
            ]
        )

    @staticmethod
    def reject_erasure(erasure_id: str, reason: str, org_id: str) -> dict:
        """
        Reject an erasure request (ADMIN action).

        Only PENDING or IN_PROGRESS requests may be rejected.
        Returns the updated erasure row.
        """
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                    UPDATE erasure_requests
                    SET status           = 'REJECTED',
                        rejection_reason = %s,
                        rejected_at      = %s,
                        updated_at       = %s
                    WHERE id       = %s::uuid
                      AND org_id   = %s
                      AND status  IN ('PENDING', 'IN_PROGRESS')
                    """,
                    (reason, now, now, erasure_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        rows = execute_query(
            """
            SELECT id::text, org_id, user_id::text, requested_by::text,
                   reason, status, modules_queued, modules_done,
                   due_by, completed_at, rejected_at, rejection_reason,
                   created_at, updated_at
            FROM erasure_requests
            WHERE id = %s::uuid AND org_id = %s
            """,
            (erasure_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Erasure request {erasure_id} not found or not rejectable")
        return _row_to_dict(rows[0])
