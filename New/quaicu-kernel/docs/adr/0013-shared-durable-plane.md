# ADR-0013: Shared durable self-serve plane — upgrade is a feature unlock, not a migration

- **Status:** Accepted
- **Date:** 2026-07-01
- **Supersedes:** the two-kernel plane shape of [ADR-0009](0009-composable-tiering-entitlements.md)
  (the `EntitlementEngine` + tier model from 0009 is retained and extended)
- **Tracker:** D0-5

## Context

ADR-0009 served the shared SaaS plane with **two kernels**: an in-memory STARTER kernel and a durable
(Postgres + KMS) BUSINESS kernel, with `TieredKernelProvider.for_saas` routing each tenant to its tier's
kernel. This had two consequences we no longer want:

1. **STARTER had an in-memory hot-path** (action repo, ledger, approvals queue) — per-process
   idempotency and a lost-on-restart queue, so the STARTER service could not run `--workers > 1` or
   multiple instances safely (D0-1 durability audit, Gap 1).
2. **A STARTER→BUSINESS upgrade was a clean-slate, not a migration.** The two kernels had different
   data stores, so a tenant's actions, ledger, and authored policies did **not** carry across an
   upgrade — only the account + plan (durable, tier-independent) survived.

The owner's requirement: STARTER and BUSINESS **share one server**, and an upgrade must be a **feature
unlock, not a data migration**.

## Decision

Serve **all** self-serve tenants (STARTER + BUSINESS) from a **single durable kernel**
(`delivery/docker/kernel.shared.toml`: `postgres_storage` + `postgres_policy` +
`gcp_kms_ledger`/`postgres_ledger` + `in_process`+postgres HITL store, `default_profile = "standard"`).
The **commercial tier becomes a pure feature gate** enforced at the API edge by the `EntitlementEngine`
(quotas, rate limit, `max_policies`, premium capabilities) — **not** a different data store.

- `TieredKernelProvider.for_shared_saas(config_path, entitlement_store)` builds one kernel and maps it
  to every served self-serve tier; `build_saas_app` reads a single `[plane] config = "…"`.
- `TIER_MATRIX` STARTER `allowed_adapters` is the durable set (same as BUSINESS); the tier differences
  are the quotas + premium capabilities.
- Because a tenant's data is durable + tenant-scoped from signup, `set_tier` (the upgrade) moves **no
  data** — it just lifts limits / unlocks features. This is the literal "feature unlock, not migration".

ENTERPRISE is unchanged: a dedicated, license-gated single-kernel deployment (`for_enterprise`).

## Consequences

- **No in-memory hot-path on the operated plane** → `--workers > 1` and multi-instance are safe
  (resolves D0-1 Gap 1). Proven by `tests/conformance/storage/test_shared_plane.py`.
- **Lossless upgrade** — actions, ledger, and policies persist across a tier flip; verified by the same
  suite (`test_upgrade_is_metadata_only_and_data_survives`) and the unit-level
  `tests/unit/api/test_policy_quota.py::test_upgrade_is_a_feature_unlock_not_a_migration`.
- **Structural isolation became explicit gating.** The two-kernel design kept STARTER out of BUSINESS
  features *structurally* (its kernel lacked the adapters). With one shared kernel that wall is gone, so
  tier features are now enforced as **explicit fail-closed `EntitlementEngine` checks** at the edge.
  Implemented for `max_policies` (`delivery/api/routes/policies.py`); profile selection has no
  tenant-facing surface; the BYO AI gateway (`/v1/ai/*`) is intentionally available to all tiers.
- **Cost trade-off (accepted):** the free STARTER tier now uses Postgres + KMS — the former
  zero-dependency in-memory free tier is gone. The in-memory adapters remain for local dev
  (`kernel.dev.toml`) and tests.
- **Open follow-up:** the durable policy/approvals/entitlement tables isolate tenants by query predicate
  but are not yet under RLS (D0-1 Gap 4); the merge doesn't worsen this (BUSINESS already shared a
  policy store) and it stays a separate tracked task. The `register_policy` tenant-stamp is a partial
  hardening.
