"""Entitlement & tiering — public surface of `core/entitlements` (ADR-0009).

Import from here, not from submodules, to keep the internal structure free to evolve.
"""

from __future__ import annotations

from core.entitlements.engine import EntitlementEngine
from core.entitlements.model import (
    TIER_MATRIX,
    CustomerPlan,
    FeatureTier,
    PlanStatus,
    TierSpec,
)
from core.entitlements.repository import EntitlementRepository
from core.entitlements.store import EntitlementStore

__all__ = [
    "TIER_MATRIX",
    "CustomerPlan",
    "EntitlementEngine",
    "EntitlementRepository",
    "EntitlementStore",
    "FeatureTier",
    "PlanStatus",
    "TierSpec",
]
