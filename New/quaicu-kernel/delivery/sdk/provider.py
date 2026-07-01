"""Tiered kernel provider — routes a tenant to the kernel its commercial tier is served by (ADR-0009).

On the **shared SaaS plane**, one process pre-builds a STARTER kernel (memory ledger + always_allow)
and a BUSINESS kernel (Postgres + CEL + HITL + JWT). Because the storage/ledger/consent adapters are
already tenant-scoped internally, all STARTER tenants can share the STARTER kernel and all BUSINESS
tenants the BUSINESS kernel — we route per request by the tenant's tier, no kernel-per-tenant. A
STARTER tenant physically cannot reach BUSINESS features: its requests land on a kernel that lacks
the CEL/Postgres adapters.

On a **dedicated ENTERPRISE deployment**, the provider serves a single ENTERPRISE kernel, built only
after an offline license verifies (see `verify_enterprise_license`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from core.entitlements import EntitlementEngine, EntitlementStore, FeatureTier
from core.errors import FeatureNotEntitledError, LicenseInvalidError
from core.license import License, load_public_key, verify_license
from core.types import TenantId
from delivery.sdk.kernel import Kernel

log = logging.getLogger("quaicu.provider")


class TieredKernelProvider:
    """Resolves the `Kernel` that serves a given tenant, based on its entitlement tier."""

    def __init__(
        self,
        kernels: dict[FeatureTier, Kernel],
        entitlements: EntitlementEngine,
    ) -> None:
        if not kernels:
            raise ValueError("TieredKernelProvider needs at least one tier kernel.")
        self._kernels = kernels
        self._entitlements = entitlements

    @property
    def entitlements(self) -> EntitlementEngine:
        return self._entitlements

    def served_tiers(self) -> frozenset[FeatureTier]:
        """The tiers this deployment can actually serve (which kernels were built)."""
        return frozenset(self._kernels)

    def tier_for(self, tenant: TenantId) -> FeatureTier:
        """The tenant's tier (fail-closed via the entitlement engine)."""
        return self._entitlements.tier_for(tenant)

    def kernel_for(self, tenant: TenantId) -> Kernel:
        """Return the kernel serving ``tenant``.

        Fail-closed: raises if the tenant is unprovisioned/inactive (entitlement engine) or if its
        tier is not served by this deployment (e.g. an ENTERPRISE tenant hitting the SaaS plane).
        """
        tier = self._entitlements.tier_for(tenant)
        kernel = self._kernels.get(tier)
        if kernel is None:
            raise FeatureNotEntitledError(
                f"Tier {tier.value} is not served by this deployment "
                f"(serves: {sorted(t.value for t in self._kernels)}).",
                detail={"tenant": str(tenant), "tier": tier.value},
            )
        return kernel

    # ── Lifecycle (delegates to each distinct kernel once) ───────────────────────

    async def startup(self) -> None:
        for kernel in self._distinct_kernels():
            await kernel.startup()

    async def shutdown(self) -> None:
        for kernel in self._distinct_kernels():
            await kernel.shutdown()

    def _distinct_kernels(self) -> list[Kernel]:
        seen: list[Kernel] = []
        for kernel in self._kernels.values():
            if all(kernel is not k for k in seen):
                seen.append(kernel)
        return seen

    # ── Builders ─────────────────────────────────────────────────────────────────

    @classmethod
    def for_saas(
        cls,
        *,
        tier_config_paths: dict[FeatureTier, str | Path],
        entitlement_store: EntitlementStore,
    ) -> "TieredKernelProvider":
        """Build the shared SaaS plane from one TOML per served tier (STARTER, BUSINESS).

        Each path is a standard kernel config (``[adapters]`` + sections) describing that tier's
        adapter set. Enterprise is intentionally excluded — it ships as a dedicated deployment.
        """
        kernels: dict[FeatureTier, Kernel] = {}
        for tier, path in tier_config_paths.items():
            if tier is FeatureTier.ENTERPRISE:
                raise ValueError(
                    "ENTERPRISE is a dedicated deployment; use for_enterprise(), not for_saas()."
                )
            kernels[tier] = Kernel.from_config(path)
        return cls(kernels, EntitlementEngine(entitlement_store))

    @classmethod
    def for_shared_saas(
        cls,
        *,
        config_path: str | Path,
        entitlement_store: EntitlementStore,
    ) -> "TieredKernelProvider":
        """Build the shared self-serve plane: ONE durable kernel serving STARTER **and** BUSINESS.

        Supersedes ``for_saas`` (two kernels by tier). A single durable kernel
        (``kernel.shared.toml``) is mapped to every self-serve tier, so all self-serve tenants share
        the same Postgres + KMS ledger. The commercial tier is a pure feature gate enforced at the API
        edge by the ``EntitlementEngine`` (quotas, rate limit, ``max_policies``, premium capabilities) —
        not a different data store. A STARTER→BUSINESS upgrade is therefore a feature unlock, not a data
        migration: the tenant's data is already durable here.

        Enterprise is intentionally excluded — it ships as a dedicated deployment (``for_enterprise``).
        """
        kernel = Kernel.from_config(config_path)
        # Map every self-serve tier to the SAME instance; routing by tier then resolves to one kernel,
        # and `_distinct_kernels` dedupes so startup/shutdown run exactly once.
        kernels = {FeatureTier.STARTER: kernel, FeatureTier.BUSINESS: kernel}
        return cls(kernels, EntitlementEngine(entitlement_store))

    @classmethod
    def for_enterprise(
        cls,
        *,
        config_path: str | Path,
        license_token: str,
        public_key_pem_or_hex: str,
        entitlement_store: EntitlementStore,
        now: datetime | None = None,
    ) -> "TieredKernelProvider":
        """Build a dedicated ENTERPRISE deployment, refusing to boot without a valid license.

        Verifies the offline license first (fail-closed). Only on success is the ENTERPRISE kernel
        constructed and returned, so an expired or forged license prevents the process from serving.
        """
        verify_enterprise_license(
            license_token, public_key_pem_or_hex, now=now
        )
        kernel = Kernel.from_config(config_path)
        return cls({FeatureTier.ENTERPRISE: kernel}, EntitlementEngine(entitlement_store))


def verify_enterprise_license(
    license_token: str,
    public_key_pem_or_hex: str,
    *,
    tenant: str | None = None,
    now: datetime | None = None,
) -> License:
    """Verify an offline Enterprise license at boot. Raises `LicenseInvalidError` (fail-closed).

    If ``tenant`` is given, also asserts the license covers it.
    """
    public_key = load_public_key(public_key_pem_or_hex)
    lic = verify_license(license_token, public_key, now=now or datetime.now(timezone.utc))
    if tenant is not None and not lic.covers_tenant(tenant):
        raise LicenseInvalidError(
            f"License {lic.license_id!r} does not cover tenant {tenant!r}.",
            detail={"license_id": lic.license_id, "tenant": tenant},
        )
    log.info("enterprise license verified: id=%s licensee=%s", lic.license_id, lic.licensee)
    return lic
