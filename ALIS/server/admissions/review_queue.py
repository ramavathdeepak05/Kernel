"""
Review Queue — E04-S12

Surfaces borderline cases (REVIEW_REQUIRED decisions from PolicyEvaluator)
to the staff dashboard. Staff approves or rejects → pipeline resumes.

Table: review_items
  status: PENDING → APPROVED | REJECTED
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .policy_engine import PolicyDecision, PolicyOutcome

logger = logging.getLogger(__name__)


class ReviewStatus:
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReviewQueue:
    """Service for enqueuing flagged items and recording staff decisions."""

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    @classmethod
    def enqueue(
        cls,
        org_id: str,
        entity_type: str,
        entity_id: str,
        decision: PolicyDecision,
        actor_id: str = "system",
    ) -> dict:
        """
        Add a borderline applicant to the review queue.
        Idempotent: if a PENDING item already exists for this entity, returns it.

        Args:
            entity_type: e.g. "applicant"
            entity_id:   applicant UUID
            decision:    PolicyDecision with REVIEW_REQUIRED outcome
        """
        if decision.outcome != PolicyOutcome.REVIEW_REQUIRED:
            raise BusinessRuleViolation(
                message=f"Only REVIEW_REQUIRED decisions can be enqueued, got {decision.outcome}"
            )

        # Idempotency — check for existing PENDING item
        existing = execute_query(
            "SELECT id FROM review_items WHERE org_id = %s AND entity_type = %s AND entity_id = %s AND status = 'PENDING'",
            (org_id, entity_type, entity_id),
        )
        if existing:
            rows = execute_query(
                "SELECT * FROM review_items WHERE id = %s",
                (existing[0]["id"],),
            )
            return dict(rows[0])

        item_id = str(uuid.uuid4())
        execute_transaction([
            (
                """
                INSERT INTO review_items
                    (id, org_id, entity_type, entity_id, reason, flags,
                     policy_key, policy_value, actual_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item_id,
                    org_id,
                    entity_type,
                    entity_id,
                    decision.reason,
                    json.dumps(decision.flags),
                    decision.trigger_key,
                    json.dumps(decision.trigger_value),
                    json.dumps(decision.actual_value),
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="review_item",
            entity_id=item_id,
            org_id=org_id,
            module="E04-S12",
            metadata={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "reason": decision.reason,
                "flags": decision.flags,
            },
        )

        logger.info("ReviewQueue: enqueued %s %s — %s", entity_type, entity_id, decision.reason)
        return {"id": item_id, "status": ReviewStatus.PENDING, "entity_id": entity_id}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def list_pending(cls, org_id: str, entity_type: Optional[str] = None) -> list[dict]:
        """List all pending review items for an org."""
        if entity_type:
            rows = execute_query(
                "SELECT * FROM review_items WHERE org_id = %s AND entity_type = %s AND status = 'PENDING' ORDER BY created_at",
                (org_id, entity_type),
            )
        else:
            rows = execute_query(
                "SELECT * FROM review_items WHERE org_id = %s AND status = 'PENDING' ORDER BY created_at",
                (org_id,),
            )
        return [dict(r) for r in rows]

    @classmethod
    def get(cls, org_id: str, item_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM review_items WHERE id = %s AND org_id = %s",
            (item_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Review item {item_id} not found")
        return dict(rows[0])

    # ------------------------------------------------------------------
    # Decide
    # ------------------------------------------------------------------

    @classmethod
    def decide(
        cls,
        org_id: str,
        item_id: str,
        decision: str,      # "APPROVED" | "REJECTED"
        decided_by: str,
        note: Optional[str] = None,
    ) -> dict:
        """
        Record a staff decision on a review item.
        After this call, the automation pipeline must be re-triggered by the caller.

        Args:
            decision: "APPROVED" or "REJECTED"
            decided_by: actor_id of the staff member
            note: Optional reasoning
        """
        if decision not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
            raise BusinessRuleViolation(message=f"Invalid decision: {decision}. Must be APPROVED or REJECTED")

        item = cls.get(org_id, item_id)
        if item["status"] != ReviewStatus.PENDING:
            raise BusinessRuleViolation(
                message=f"Review item {item_id} is already {item['status']}"
            )

        execute_transaction([
            (
                """
                UPDATE review_items
                SET status = %s, decision = %s, decided_by = %s, decided_at = NOW(), decision_note = %s
                WHERE id = %s AND org_id = %s
                """,
                (decision, decision, decided_by, note, item_id, org_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.OVERRIDE_APPROVED if decision == ReviewStatus.APPROVED else AuditAction.OVERRIDE_REJECTED,
            actor_id=decided_by,
            actor_type="human",
            entity_type="review_item",
            entity_id=item_id,
            org_id=org_id,
            module="E04-S12",
            metadata={
                "entity_type": item["entity_type"],
                "entity_id": item["entity_id"],
                "decision": decision,
                "note": note,
            },
        )

        logger.info(
            "ReviewQueue: %s decided %s on %s %s",
            decided_by, decision, item["entity_type"], item["entity_id"],
        )

        updated = cls.get(org_id, item_id)
        return dict(updated)
