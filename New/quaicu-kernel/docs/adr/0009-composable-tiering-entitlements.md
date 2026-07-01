# ADR-0009: Composable tiering via `EntitlementEngine` + shared-plane kernel routing

- **Status:** Accepted — **plane shape superseded by [ADR-0013](0013-shared-durable-plane.md)**
- **Date:** 2026-06-13
- **Decided by:** orchestrator

> **Update (2026-07-01, ADR-0013):** the *two-kernel* plane below (in-memory STARTER kernel + durable
> BUSINESS kernel routed by tier) is replaced by a **single durable kernel** serving all self-serve
> tiers, with the tier as a pure feature gate (upgrade = feature unlock, not migration). The
> `EntitlementEngine` + `TIER_MATRIX` model in this ADR is retained; only the per-tier-kernel routing is
> superseded.
- **Affects:** `core/entitlements/` (new), `core/license/` (new), `core/errors.py`, `delivery/sdk/provider.py` (new), `delivery/sdk/kernel.py`

## Context

The governance engine is feature-complete, but it cannot yet be *sold* in tiers. Two productization
facts force a design:

1. **One codebase must express three commercial tiers** (Starter / Business / Enterprise) without a
   per-tier fork — the same constraint ADR-0001 (frozen contract surface) and ADR-0002 (composable
   `GovernanceProfile`) already protect for governance postures, now applied to packaging.
2. **The deployment shapes differ.** Starter + Business are sold as a **shared multi-tenant SaaS
   plane** (tier resolved per request from the tenant's plan); Enterprise is sold as a **dedicated,
   on-prem/private-cloud deployment**. Today `Kernel.from_config()` wires exactly one global adapter
   set per process and the API holds a single `app.state.kernel` — there is no notion of "which tier
   is this tenant" anywhere.

The enabling observation: the storage, ledger, and consent adapters are **already tenant-scoped
internally** (every query carries `tenant_id`; the in-memory ledger keys Merkle trees by `TenantId`).
So the shared plane does **not** need a kernel per tenant — it needs one pre-built kernel per *tier*,
and a router that picks the right one from the tenant's entitlement. Physical adapter separation makes
tier isolation structural: a Starter tenant's request lands on a kernel that has no CEL/Postgres
adapter wired, so it *cannot* reach Business features even if the entitlement check were bypassed.

## Decision

Introduce two additive `core/` modules and one SDK module — no change to the frozen `core/types.py`
or `core/ports/*`:

- **`core/entitlements/`** — `FeatureTier` (STARTER/BUSINESS/ENTERPRISE), `CustomerPlan` (immutable;
  tenant + tier + status + billing refs + optional per-tenant quota overrides), and `TIER_MATRIX`,
  the **single source of truth** mapping each tier to the `_ADAPTER_REGISTRY` names it may use, the
  `GovernanceProfile` preset names it may run (referenced by name to avoid a `core/lifecycle`
  import), and its quotas. `EntitlementEngine` is a thin, **fail-closed** query layer over an
  `EntitlementStore` (in-memory read cache + optional durable `EntitlementRepository` write-through +
  `hydrate()`, mirroring `core/policy`): an unprovisioned or non-ACTIVE plan grants nothing.
- **`core/license/`** — an offline-verifiable Enterprise `License` (Ed25519, same `cryptography`
  primitives as `core/ledger/signer.py`). `verify_license` is fail-closed on missing/malformed/
  expired/forged tokens and needs no network, so air-gapped installs work.
- **`delivery/sdk/provider.py`** — `TieredKernelProvider` resolves `kernel_for(tenant)` by tier:
  `for_saas(...)` pre-builds the STARTER and BUSINESS kernels (shared pooled resources) and routes
  per request; `for_enterprise(...)` builds the single ENTERPRISE kernel **only after the offline
  license verifies**, so a bad license stops the process from serving.

New error types are added to the frozen `core/errors.py` under existing-style parents, recorded here
per ADR-0001's incremental-freeze rule: `EntitlementError` (+ `PlanNotFoundError`,
`FeatureNotEntitledError`, `QuotaExceededError`) and `LicenseError` (+ `LicenseInvalidError`).

## Consequences

- A single binary serves all three tiers; the shared plane routes by tier with structural (not just
  policy) isolation between Starter and Business.
- Tier definitions live in one matrix — changing a tier's grants applies to every tenant on it with
  no data migration. Billing-driven tier flips (ADR-future Stripe/Razorpay webhooks) are a single
  `set_tier_persisted` call.
- Enterprise deployments fail closed without a valid license; the license is verifiable offline.
- Quota and profile gating are available to the API edge for per-request enforcement (rate limits,
  policy-count caps) in later waves.
- Forbidden: duplicating a tier's grants onto a `CustomerPlan`; selecting adapters per tenant inside a
  single kernel (use the per-tier kernel routing instead); any entitlement check that defaults-open.

## Alternatives considered

- **One kernel per tenant.** Rejected — unnecessary given adapters are already tenant-scoped; it
  would multiply connection pools and startup cost with no isolation benefit over per-tier kernels.
- **A single binary, one tier per deployment (startup-only entitlement).** Rejected as the primary
  model — it cannot host Starter and Business tenants on one shared plane, which the SaaS economics
  require. (It remains exactly how the Enterprise dedicated deployment works.)
- **Feature flags inside one maximal kernel.** Rejected — a Starter tenant would share a process that
  *has* the CEL/OpenBao adapters wired, making isolation a matter of a correct `if` rather than
  physical separation; weaker security story for regulated buyers.
