"""
HR-6 — Separation & Exit

Implements:
- Separation initiation → fires separation.initiated event
- EC-ACA-02: triggers CourseHandoverWorkflow (Academic module)
- No-dues clearance across all departments
- Gratuity computation per Payment of Gratuity Act:
    (Basic + DA) × 15/26 × completed_years
- EL encashment with 300-day cap
- Handover package: generated BEFORE LMS access revoked

State Machine:
    INITIATED → HANDOVER_PENDING → NO_DUES_PENDING → SETTLEMENT_PENDING → COMPLETED

No-dues departments:
    Library, Finance, IT, Hostel, Lab, Department (HOD), Admin
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.core.audit import AuditLog, AuditAction
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class SeparationStatus(str, Enum):
    INITIATED = "INITIATED"
    HANDOVER_PENDING = "HANDOVER_PENDING"
    NO_DUES_PENDING = "NO_DUES_PENDING"
    SETTLEMENT_PENDING = "SETTLEMENT_PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NoDuesStatus(str, Enum):
    PENDING = "PENDING"
    CLEARED = "CLEARED"
    BLOCKED = "BLOCKED"  # Has outstanding items


NO_DUES_DEPARTMENTS = [
    "LIBRARY", "FINANCE", "IT", "HOSTEL", "LAB", "DEPARTMENT", "ADMIN",
]


class SeparationService:

    @classmethod
    def initiate(cls, org_id: str, staff_id: str, data: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
        """Initiate employee separation. Fires separation.initiated event."""
        sep_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO separations
                    (id, org_id, staff_id, separation_type, reason,
                     last_working_date, status, initiated_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sep_id, org_id, staff_id,
                    data.get("separation_type", "RESIGNATION"),
                    data.get("reason", ""),
                    data.get("last_working_date"),
                    SeparationStatus.INITIATED.value, actor_id, now,
                ),
            ),
        ], tenant_id=org_id)

        # Create no-dues records for all departments
        for dept in NO_DUES_DEPARTMENTS:
            execute_transaction([
                (
                    """
                    INSERT INTO no_dues_clearances
                        (id, org_id, separation_id, staff_id, department, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (str(uuid4()), org_id, sep_id, staff_id, dept,
                     NoDuesStatus.PENDING.value, now),
                )
            ], tenant_id=org_id)

        # Fire separation.initiated → triggers Academic CourseHandoverWorkflow (EC-ACA-02)
        DomainEventBus.publish(DomainEvent(
            event_type="separation.initiated",
            org_id=org_id,
            payload={
                "separation_id": sep_id,
                "staff_id": staff_id,
                "last_working_date": str(data.get("last_working_date", "")),
                "separation_type": data.get("separation_type", "RESIGNATION"),
            },
            actor_id=actor_id,
        ))

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_role="admin",
            entity_type="separation", entity_id=sep_id, tenant_id=org_id,
            metadata={"staff_id": staff_id, "type": data.get("separation_type", "RESIGNATION")},
        )

        return {"id": sep_id, "status": SeparationStatus.INITIATED.value}

    @classmethod
    def clear_no_dues(cls, org_id: str, clearance_id: str, actor_id: str) -> Dict[str, Any]:
        """Department head clears no-dues for a specific department."""
        execute_transaction([
            ("UPDATE no_dues_clearances SET status = %s, cleared_by = %s, cleared_at = NOW() "
             "WHERE id = %s AND org_id = %s AND status = %s",
             (NoDuesStatus.CLEARED.value, actor_id, clearance_id, org_id, NoDuesStatus.PENDING.value))
        ], tenant_id=org_id)
        return {"id": clearance_id, "status": NoDuesStatus.CLEARED.value}

    @classmethod
    def check_all_cleared(cls, org_id: str, separation_id: str) -> Dict[str, Any]:
        """Check if all no-dues departments have cleared."""
        rows = execute_query(
            "SELECT department, status FROM no_dues_clearances "
            "WHERE separation_id = %s AND org_id = %s ORDER BY department",
            (separation_id, org_id), tenant_id=org_id,
        )
        departments = [dict(r) for r in rows]
        all_cleared = all(d["status"] == NoDuesStatus.CLEARED.value for d in departments)
        pending = [d["department"] for d in departments if d["status"] != NoDuesStatus.CLEARED.value]

        return {
            "separation_id": separation_id,
            "all_cleared": all_cleared,
            "departments": departments,
            "pending_departments": pending,
        }

    @classmethod
    def compute_gratuity(
        cls, basic_salary: float, da: float, completed_years: float,
    ) -> Dict[str, Any]:
        """
        Compute gratuity per Payment of Gratuity Act, 1972.

        Formula: (Basic + DA) × 15/26 × completed_years
        Maximum: ₹20,00,000 (20 lakh) per Act
        Minimum service: 5 years (4 years 240 days rounds up)
        """
        if completed_years < 4.66:  # ~4 years 240 days
            return {
                "eligible": False,
                "reason": f"Minimum 5 years of service required (has {completed_years:.1f})",
                "gratuity_amount": 0,
            }

        # Round up to nearest year if > 6 months
        years = int(completed_years)
        if completed_years - years >= 0.5:
            years += 1

        gratuity = (basic_salary + da) * 15 / 26 * years
        max_gratuity = 2000000.0  # ₹20 lakh cap
        gratuity = min(gratuity, max_gratuity)

        return {
            "eligible": True,
            "basic_salary": basic_salary,
            "da": da,
            "completed_years": completed_years,
            "years_considered": years,
            "gratuity_amount": round(gratuity, 2),
            "formula": f"({basic_salary} + {da}) × 15/26 × {years}",
            "capped": gratuity >= max_gratuity,
        }

    @classmethod
    def compute_el_encashment(
        cls, basic_salary: float, el_balance_days: int,
    ) -> Dict[str, Any]:
        """
        Compute Earned Leave encashment.

        Maximum: 300 days (government norm, most institutions follow this).
        Rate: Basic salary / 30 per day.
        """
        max_days = 300
        encashable_days = min(el_balance_days, max_days)
        daily_rate = basic_salary / 30
        amount = round(daily_rate * encashable_days, 2)

        return {
            "el_balance_days": el_balance_days,
            "encashable_days": encashable_days,
            "daily_rate": round(daily_rate, 2),
            "encashment_amount": amount,
            "max_days": max_days,
            "capped": el_balance_days > max_days,
        }

    @classmethod
    def compute_full_settlement(
        cls, org_id: str, staff_id: str, separation_id: str,
    ) -> Dict[str, Any]:
        """Compute full and final settlement for an employee."""
        staff = execute_query(
            "SELECT basic_salary, da, date_of_joining, el_balance FROM staff_profiles "
            "WHERE id = %s AND org_id = %s",
            (staff_id, org_id), tenant_id=org_id,
        )
        if not staff:
            raise ValueError(f"Staff {staff_id} not found")
        s = dict(staff[0])

        basic = float(s.get("basic_salary", 0))
        da = float(s.get("da", 0))
        joining = s.get("date_of_joining")
        el_balance = int(s.get("el_balance", 0))

        if joining:
            if isinstance(joining, str):
                joining = datetime.fromisoformat(joining)
            service_years = (datetime.now(timezone.utc) - joining).days / 365.25
        else:
            service_years = 0

        gratuity = cls.compute_gratuity(basic, da, service_years)
        el = cls.compute_el_encashment(basic, el_balance)
        no_dues = cls.check_all_cleared(org_id, separation_id)

        total = gratuity["gratuity_amount"] + el["encashment_amount"]

        return {
            "staff_id": staff_id,
            "separation_id": separation_id,
            "gratuity": gratuity,
            "el_encashment": el,
            "no_dues": no_dues,
            "total_settlement": round(total, 2),
            "can_process": no_dues["all_cleared"],
        }
