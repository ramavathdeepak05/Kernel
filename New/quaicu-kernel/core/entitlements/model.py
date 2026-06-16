"""Entitlement & tiering — data model (ADR-0009).

`CustomerPlan` is the authoritative, immutable record of which commercial tier a tenant is on.
`TierSpec` declares what a tier *grants* — the set of adapters it may use, the governance profiles
it may run, and its quotas. `TIER_MATRIX` is the **single source of truth** consumed by both the
`TieredKernelProvider` (to pick which pre-built kernel serves a tenant) and the `EntitlementEngine`
(to gate features and enforce quotas).

Tiers map to the commercial packaging:
  - STARTER    — self-serve, memory-only, audit trail (always_allow + in-memory ledger).
  - BUSINESS   — SaaS: durable Postgres + CEL policy engine + HITL + JWT identity.
  - ENTERPRISE — dedicated deploy: OpenBao tamper-proof ledger, per-tenant keys, custom profiles.

Design rules (same freeze discipline as `core/policy/model.py`): immutable dataclasses; a tier's
grants live only in `TIER_MATRIX`, never duplicated onto a plan. Governance profiles are referenced
by **preset name** (str) so this module stays free of any `core/lifecycle` import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.types import TenantId


class FeatureTier(str, Enum):
    """The commercial tier a tenant is provisioned on. Ordered STARTER < BUSINESS < ENTERPRISE."""

    STARTER = "STARTER"
    BUSINESS = "BUSINESS"
    ENTERPRISE = "ENTERPRISE"


class PlanStatus(str, Enum):
    """Lifecycle of a tenant's plan. Only ACTIVE plans are entitled to serve traffic."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"      # e.g. payment failed; fail-closed until resolved
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TierSpec:
    """What a tier grants. Declarative; the kernel provider and entitlement checks read this.

    ``allowed_adapters`` are the ``_ADAPTER_REGISTRY`` names a tenant on this tier may use, plus the
    composite names ``cel_policy`` (the CEL engine, wired via ``Kernel._build_policy``). ``-1`` quota
    means unbounded.
    """

    tier: FeatureTier
    allowed_adapters: frozenset[str]
    default_profile: str                      # GovernanceProfile preset name
    allowed_profiles: frozenset[str]
    max_policies: int                         # -1 = unbounded
    max_actions_per_day: int                  # -1 = unbounded
    rate_limit_per_min: int                   # -1 = unbounded
    requires_license: bool = False            # ENTERPRISE boots only with a valid offline license


# ── The tier matrix — single source of truth ───────────────────────────────────

TIER_MATRIX: dict[FeatureTier, TierSpec] = {
    FeatureTier.STARTER: TierSpec(
        tier=FeatureTier.STARTER,
        # In-memory, but governance-capable: the CEL engine + a small policy allowance so the free
        # tier actually enforces (ships with a seeded allow-baseline + a deny guardrail — see
        # kernel.starter.toml — and a tenant may author a few of their own).
        allowed_adapters=frozenset(
            {
                "always_allow", "cel_policy", "memory_policy",
                "memory_ledger", "memory_storage", "memory_events", "webhook",
            }
        ),
        default_profile="standard",
        allowed_profiles=frozenset({"standard", "audit_only", "monitor"}),
        max_policies=5,
        max_actions_per_day=10_000,
        rate_limit_per_min=60,
    ),
    FeatureTier.BUSINESS: TierSpec(
        tier=FeatureTier.BUSINESS,
        allowed_adapters=frozenset(
            {
                "cel_policy", "postgres_policy", "memory_policy",
                "postgres_storage", "postgres_ledger", "memory_ledger_repo",
                "memory_events", "webhook", "jwt", "openai_compat",
            }
        ),
        default_profile="standard",
        allowed_profiles=frozenset(
            {"all", "standard", "gateway_only", "audit_only", "monitor"}
        ),
        max_policies=200,
        max_actions_per_day=1_000_000,
        rate_limit_per_min=600,
    ),
    FeatureTier.ENTERPRISE: TierSpec(
        tier=FeatureTier.ENTERPRISE,
        # everything, including the tamper-proof OpenBao ledger
        allowed_adapters=frozenset(
            {
                "cel_policy", "postgres_policy", "memory_policy",
                "postgres_storage", "postgres_ledger", "memory_ledger_repo",
                "openbao_ledger", "memory_events", "webhook", "jwt", "openai_compat",
            }
        ),
        default_profile="all",
        allowed_profiles=frozenset(
            {"all", "standard", "gateway_only", "audit_only", "monitor"}
        ),
        max_policies=-1,
        max_actions_per_day=-1,
        rate_limit_per_min=-1,
        requires_license=True,
    ),
}


@dataclass(frozen=True)
class CustomerPlan:
    """An immutable record of a tenant's commercial plan.

    A tenant's *grants* are derived from ``TIER_MATRIX[self.tier]`` (see ``spec``) — never duplicated
    here — so a tier definition change applies to every tenant on that tier without a data migration.
    ``billing_ref`` links the plan to its Stripe / Razorpay subscription so webhooks can flip the tier.
    """

    tenant_id: TenantId
    tier: FeatureTier
    status: PlanStatus
    created_at: datetime
    updated_at: datetime
    billing_provider: str | None = None       # "stripe" | "razorpay" | None
    billing_ref: str | None = None            # external subscription id
    # Enterprise contracts may override individual quotas; empty for self-serve tiers.
    quota_overrides: dict[str, int] = field(default_factory=dict)

    @property
    def spec(self) -> TierSpec:
        """The tier grants for this plan, from the single-source-of-truth matrix."""
        return TIER_MATRIX[self.tier]

    @property
    def is_active(self) -> bool:
        return self.status is PlanStatus.ACTIVE
