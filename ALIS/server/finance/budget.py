"""
FM-6 — Budget Planning & Monitoring

Implements:
- Annual budget creation per department/cost center
- Budget approval workflow (DRAFT → SUBMITTED → APPROVED → ACTIVE)
- Budget utilization tracking (committed, spent, available)
- Monthly variance alerts (>10% deviation)
- Board notification on >20% overrun
- Budget approval unlocks Purchase Requisition system

State Machine:
    DRAFT → SUBMITTED → APPROVED → ACTIVE → FROZEN → CLOSED
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


class BudgetStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


BUDGET_TRANSITIONS = {
    BudgetStatus.DRAFT: {BudgetStatus.SUBMITTED},
    BudgetStatus.SUBMITTED: {BudgetStatus.APPROVED, BudgetStatus.DRAFT},
    BudgetStatus.APPROVED: {BudgetStatus.ACTIVE},
    BudgetStatus.ACTIVE: {BudgetStatus.FROZEN, BudgetStatus.CLOSED},
    BudgetStatus.FROZEN: {BudgetStatus.ACTIVE, BudgetStatus.CLOSED},
    BudgetStatus.CLOSED: set(),
}


class BudgetService:
    @classmethod
    def create_budget(
        cls,
        org_id: str,
        data: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        """Create an annual budget for a department/cost center."""
        budget_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO budgets
                    (id, org_id, financial_year, department, cost_center,
                     allocated_amount, committed_amount, spent_amount,
                     status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 0, 0, %s, %s, %s)
                """,
                    (
                        budget_id,
                        org_id,
                        data["financial_year"],
                        data["department"],
                        data.get("cost_center", ""),
                        data["allocated_amount"],
                        BudgetStatus.DRAFT.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        return {"id": budget_id, "status": BudgetStatus.DRAFT.value}

    @classmethod
    def advance_status(
        cls,
        org_id: str,
        budget_id: str,
        target: str,
        actor_id: str,
    ) -> dict[str, Any]:
        rows = execute_query(
            "SELECT status, department FROM budgets WHERE id = %s AND org_id = %s",
            (budget_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Budget {budget_id} not found")
        current = BudgetStatus(rows[0]["status"])
        target_status = BudgetStatus(target)
        if target_status not in BUDGET_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Invalid transition: {current.value} → {target_status.value}"
            )

        execute_transaction(
            [
                (
                    "UPDATE budgets SET status = %s, updated_at = NOW() WHERE id = %s AND org_id = %s",
                    (target_status.value, budget_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        if target_status == BudgetStatus.APPROVED:
            DomainEventBus.publish(
                DomainEvent(
                    event_type="budget.approved",
                    org_id=org_id,
                    payload={
                        "budget_id": budget_id,
                        "department": rows[0]["department"],
                    },
                    actor_id=actor_id,
                )
            )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="finance",
            entity_type="budget",
            entity_id=budget_id,
            tenant_id=org_id,
            metadata={"from": current.value, "to": target_status.value},
        )
        return {"id": budget_id, "status": target_status.value}

    @classmethod
    def record_commitment(
        cls,
        org_id: str,
        budget_id: str,
        amount: float,
        reference: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Record a budget commitment (PO approved → funds committed)."""
        budget = cls._get(org_id, budget_id)
        if budget["status"] != BudgetStatus.ACTIVE.value:
            raise ValueError("Budget must be ACTIVE to record commitments")

        new_committed = float(budget["committed_amount"]) + amount
        available = (
            float(budget["allocated_amount"])
            - new_committed
            - float(budget["spent_amount"])
        )
        if available < 0:
            raise ValueError(
                f"Insufficient budget: allocated={budget['allocated_amount']}, "
                f"committed={new_committed}, spent={budget['spent_amount']}"
            )

        execute_transaction(
            [
                (
                    "UPDATE budgets SET committed_amount = committed_amount + %s, updated_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (amount, budget_id, org_id),
                ),
                (
                    """
                INSERT INTO budget_transactions
                    (id, org_id, budget_id, transaction_type, amount, reference, created_at)
                VALUES (%s, %s, %s, 'COMMITMENT', %s, %s, NOW())
                """,
                    (str(uuid4()), org_id, budget_id, amount, reference),
                ),
            ],
            tenant_id=org_id,
        )

        return {"budget_id": budget_id, "committed": amount, "available": available}

    @classmethod
    def record_expenditure(
        cls,
        org_id: str,
        budget_id: str,
        amount: float,
        reference: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Record actual expenditure (payment made → commitment becomes spent)."""
        cls._get(org_id, budget_id)
        execute_transaction(
            [
                (
                    "UPDATE budgets SET spent_amount = spent_amount + %s, "
                    "committed_amount = GREATEST(committed_amount - %s, 0), updated_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (amount, amount, budget_id, org_id),
                ),
                (
                    """
                INSERT INTO budget_transactions
                    (id, org_id, budget_id, transaction_type, amount, reference, created_at)
                VALUES (%s, %s, %s, 'EXPENDITURE', %s, %s, NOW())
                """,
                    (str(uuid4()), org_id, budget_id, amount, reference),
                ),
            ],
            tenant_id=org_id,
        )

        return {"budget_id": budget_id, "spent": amount}

    @classmethod
    def check_variance(cls, org_id: str) -> list[dict[str, Any]]:
        """Monthly variance check — returns budgets with >10% deviation."""
        rows = execute_query(
            """
            SELECT id, department, financial_year, allocated_amount, spent_amount,
                   committed_amount,
                   CASE WHEN allocated_amount > 0
                        THEN ((spent_amount + committed_amount) / allocated_amount * 100)
                        ELSE 0 END AS utilization_pct
            FROM budgets
            WHERE org_id = %s AND status = 'ACTIVE'
            ORDER BY utilization_pct DESC
            """,
            (org_id,),
            tenant_id=org_id,
        )
        alerts = []
        for r in rows:
            util = float(r["utilization_pct"])
            if util > 120:
                alerts.append(
                    {
                        **dict(r),
                        "severity": "CRITICAL",
                        "message": f">20% overrun ({util:.0f}%)",
                    }
                )
            elif util > 110:
                alerts.append(
                    {
                        **dict(r),
                        "severity": "WARNING",
                        "message": f">10% deviation ({util:.0f}%)",
                    }
                )
        return alerts

    @classmethod
    def get_summary(cls, org_id: str, financial_year: str) -> list[dict[str, Any]]:
        rows = execute_query(
            "SELECT id, department, cost_center, allocated_amount, committed_amount, "
            "spent_amount, status FROM budgets "
            "WHERE org_id = %s AND financial_year = %s ORDER BY department",
            (org_id, financial_year),
            tenant_id=org_id,
        )
        return [dict(r) for r in rows]

    @classmethod
    def _get(cls, org_id: str, budget_id: str) -> dict[str, Any]:
        rows = execute_query(
            "SELECT * FROM budgets WHERE id = %s AND org_id = %s",
            (budget_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Budget {budget_id} not found")
        return dict(rows[0])
