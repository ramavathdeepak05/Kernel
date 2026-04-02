"""
Plan Store — S9

Dynamic plan configuration stored in cp_plans table.
Replaces the hardcoded PLAN_CONFIGS dict in billing_models.py at runtime.

Falls back to PLAN_CONFIGS when the cp_plans table is empty (backward compat).
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from control_plane.billing_models import PLAN_CONFIGS, PlanConfig

logger = logging.getLogger(__name__)


class PlanStore:
    """CRUD for billing plan configurations stored in cp_plans."""

    def get(self, plan_name: str) -> PlanConfig:
        """
        Get a plan by name. Tries DB first, falls back to hardcoded.
        """
        from control_plane import db

        rows = db.query(
            "SELECT * FROM cp_plans WHERE name = %s AND status = 'active'",
            (plan_name,),
        )
        if rows:
            return _row_to_config(rows[0])

        # Fallback to hardcoded
        return PLAN_CONFIGS.get(plan_name, PLAN_CONFIGS["starter"])

    def list_all(self, include_archived: bool = False) -> List[PlanConfig]:
        """List all plans."""
        from control_plane import db

        if include_archived:
            rows = db.query("SELECT * FROM cp_plans ORDER BY monthly_price_usd")
        else:
            rows = db.query(
                "SELECT * FROM cp_plans WHERE status = 'active' ORDER BY monthly_price_usd"
            )

        if not rows:
            return list(PLAN_CONFIGS.values())

        return [_row_to_config(r) for r in rows]

    def create(
        self,
        name: str,
        monthly_price_usd: Decimal,
        token_quota: int,
        storage_gb_quota: int,
        api_call_quota: int,
        active_user_quota: int,
        overage_token_per_1k: Decimal,
        overage_storage_gb: Decimal,
        overage_api_per_1k: Decimal,
        overage_user: Decimal,
    ) -> PlanConfig:
        """Create a new plan. Raises on duplicate name."""
        from control_plane import db

        db.execute(
            """
            INSERT INTO cp_plans
                (name, monthly_price_usd, token_quota, storage_gb_quota,
                 api_call_quota, active_user_quota,
                 overage_token_per_1k, overage_storage_gb,
                 overage_api_per_1k, overage_user, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
            """,
            (
                name, str(monthly_price_usd), token_quota, storage_gb_quota,
                api_call_quota, active_user_quota,
                str(overage_token_per_1k), str(overage_storage_gb),
                str(overage_api_per_1k), str(overage_user),
            ),
        )
        logger.info("PlanStore: created plan %s ($%s/mo)", name, monthly_price_usd)
        return self.get(name)

    def update(self, name: str, **fields) -> Optional[PlanConfig]:
        """Update specific fields of a plan."""
        from control_plane import db

        allowed = {
            "monthly_price_usd", "token_quota", "storage_gb_quota",
            "api_call_quota", "active_user_quota",
            "overage_token_per_1k", "overage_storage_gb",
            "overage_api_per_1k", "overage_user",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(name)

        set_clauses = ", ".join(f"{k} = %s" for k in updates)
        params = list(str(v) if isinstance(v, Decimal) else v for v in updates.values())
        params.append(name)

        db.execute(
            f"UPDATE cp_plans SET {set_clauses}, updated_at = NOW() WHERE name = %s",
            tuple(params),
        )
        return self.get(name)

    def archive(self, name: str) -> bool:
        """Soft-archive a plan (existing tenants keep it; new signups can't use it)."""
        from control_plane import db

        db.execute(
            "UPDATE cp_plans SET status = 'archived', updated_at = NOW() WHERE name = %s",
            (name,),
        )
        return True


def _row_to_config(row: dict) -> PlanConfig:
    return PlanConfig(
        name=row["name"],
        monthly_price_usd=Decimal(str(row["monthly_price_usd"])),
        token_quota=int(row["token_quota"]),
        storage_gb_quota=int(row["storage_gb_quota"]),
        api_call_quota=int(row["api_call_quota"]),
        active_user_quota=int(row["active_user_quota"]),
        overage_token_per_1k=Decimal(str(row["overage_token_per_1k"])),
        overage_storage_gb=Decimal(str(row["overage_storage_gb"])),
        overage_api_per_1k=Decimal(str(row["overage_api_per_1k"])),
        overage_user=Decimal(str(row["overage_user"])),
    )
