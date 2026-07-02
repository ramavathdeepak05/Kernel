# State-of-Durability Audit (Tracker D0-1)

> **Deliverable for ACTION_TRACKER D0-1.** A code-cited trace of every correctness-critical store on
> the **operated plane** (the shared SaaS app), confirming which run on a durable adapter and
> identifying every remaining in-memory hot-path *with its file*. This audit feeds **D0-5** (durable
> hot-path closure) and flags follow-ups. **Dated 2026-06-30.**

## What "operated plane" means

The shared SaaS app is built by `build_saas_app` (`delivery/sdk/saas_app.py:76`) behind
`TieredKernelProvider.for_saas` (`delivery/sdk/provider.py:89`). It pre-builds **two** kernels from
TOML — one per served tier — and routes each request to the kernel for the tenant's tier:

- **STARTER** — `delivery/docker/kernel.starter.toml` (in-memory tier, free).
- **BUSINESS** — `delivery/docker/kernel.business.toml` (durable Postgres + CEL tier).

ENTERPRISE is **not** on this plane — it ships as a dedicated, license-gated single-kernel deployment
(`delivery/entrypoint.py` + `for_enterprise`), so it is out of scope for this audit.

Adapter selection happens in `Kernel.from_config` (`delivery/sdk/kernel.py:473`): each `[adapters].<port>`
key names a concrete adapter from `_ADAPTER_REGISTRY` (`delivery/sdk/kernel.py:114`). **Critically, the
action repository defaults to in-memory when no `storage` key is declared** — `repo:
ActionRepository = _InMemoryActionRepository()` (`delivery/sdk/kernel.py:502`, class at
`delivery/sdk/kernel.py:71`).

## Per-tier adapter matrix

| Store (correctness-critical) | STARTER | BUSINESS | Durable on BUSINESS? |
|---|---|---|---|
| Action repo (idempotency) | *(no `storage`)* → `_InMemoryActionRepository` | `postgres_storage` | ✅ |
| Policy store | `cel_policy`, **no** `policy_store` (in-memory, seeded) | `cel_policy` + `postgres_policy` | ✅ |
| Ledger (K·02) | `memory_ledger` (ephemeral) | `gcp_kms_ledger` + `ledger_store = postgres_ledger` | ✅ |
| HITL approvals queue | `in_process`, **no** `store` (per-process) | `in_process` + `store = postgres` (migration 013) | ✅ |
| Event bus (K·07) | `memory_events` | `memory_events` | ⚠️ in-memory (see Gap 2) |
| Entitlements / plans | durable — `[entitlements].dsn` in `kernel.saas.toml` | same | ✅ |
| Accounts (self-serve) | durable — `[account].dsn` in `kernel.saas.toml` (migration 006) | same | ✅ |
| Usage meter | `core/metering` (per-process) | same | ⚠️ per-process (see Gap 3) |

### BUSINESS tier — durable on every correctness-critical store ✅
`kernel.business.toml` declares `storage = postgres_storage`, `policy_store = postgres_policy`,
`ledger = gcp_kms_ledger` + `ledger_store = postgres_ledger`, and `hitl = in_process` with
`store = postgres` (migration 013). Entitlements and accounts are durable via the `[entitlements]` and
`[account]` DSNs in `kernel.saas.toml`. The durable entitlement repository **is genuinely wired**:
`build_entitlement_store` returns `EntitlementStore(repository=PostgresEntitlementRepository(dsn))`
when an `[entitlements]` section supplies a DSN (`delivery/sdk/entitlements_config.py:42-58`). This
confirms the tracker's "verified baseline correction" — durable entitlements exist; **confirm, don't
rebuild** (D0-5).

## Gaps / in-memory hot-paths on the operated plane

### Gap 1 — STARTER tier is fully in-memory on the hot path  *(✅ RESOLVED in D0-5, 2026-07-01)*
> **Resolved.** The two-kernel plane (in-memory STARTER + durable BUSINESS) was replaced by a **single
> durable kernel** (`delivery/docker/kernel.shared.toml`) serving all self-serve tenants on Postgres +
> KMS ledger; the tier is now a pure feature gate (entitlements), so STARTER is durable and a
> STARTER→BUSINESS upgrade is a feature unlock, not a migration. There is **no in-memory hot-path on the
> operated plane** → `--workers > 1` is safe. Proven by `tests/conformance/storage/test_shared_plane.py`
> (idempotency + durability across workers). See ADR-0013. *Historical description of the gap follows.*

`kernel.starter.toml` declares **no `storage`** → the action repo is `_InMemoryActionRepository`
(`delivery/sdk/kernel.py:71`, defaulted at `:502`); `ledger = memory_ledger`; **no `policy_store`**
(in-memory seeded store); `hitl = in_process` with **no `store`** (per-process queue).

**Consequence:** idempotency keys and the approvals queue live in per-worker process memory. With
**>1 Cloud Run instance** or **`--workers > 1`**, the same idempotency key handled by two workers can
**double-execute** (the idempotency guard at `_InMemoryActionRepository.insert_if_absent`,
`delivery/sdk/kernel.py:77`, only dedupes within one process), and `/v1/approvals` is inconsistent
across instances. The in-memory ledger is also ephemeral (mitigated for audit by the `log_sink` →
Cloud Logging; see Gap 2).

**Open question for D0-5 (not resolved here):** is STARTER intended to run pinned to a single instance
(free tier, accept the limitation + document it), or must its action repo / approvals queue go durable
like BUSINESS? D0-5 decides and either pins or wires Postgres.

### Gap 2 — Event bus is in-memory on both tiers
Both tiers declare `events = memory_events` (`InMemoryEventBusAdapter`). **Documented as
not-correctness-critical** in the `kernel.prod.toml` header: the dashboard read-model derives from the
durable **ledger**, not the event bus, and STARTER additionally streams every sealed action to the
`quaicu.audit` logger via `[events].log_sink = true` (→ Cloud Logging) for a durable audit trail. With
>1 worker, events are not cross-worker. **Flag, not block** — move to a broker only if cross-worker
event fan-out becomes a requirement.

### Gap 3 — Usage meter is per-process
`core/metering` counters are per-worker. **Documented best-effort** (`kernel.prod.toml` header): quota
enforcement never over-counts (each worker undercounts independently), so it fails safe. **Flag** —
move to a shared store (e.g. Redis) for exact cross-worker metering.

### Gap 4 — RLS defense-in-depth is partial  *(follow-up isolation task)*
RLS is enabled by migrations `004_enable_rls` and `007_rls_hydration_sentinel`, but **only on three
tables**: `quaicu_actions`, `quaicu_ledger_entries`, `quaicu_ledger_sth`
(`_TABLES` in `004_enable_rls.py:26` and `007_rls_hydration_sentinel.py:33`). The durable **policy
store, approvals queue, and entitlements/accounts** tables have **no RLS policy**, and their Postgres
adapters (`adapters/policy/postgres.py`, `adapters/hitl/postgres_store.py`,
`adapters/entitlements/postgres.py`) **do not set `app.current_tenant`** — only `adapters/storage/postgres.py`
and `adapters/ledger/postgres.py` set the GUC (via `adapters/storage/isolation.py`). Those non-RLS
tables therefore enforce tenant isolation by **query-level `tenant_id` predicate alone**. The F-07
belt-and-braces guarantee holds for actions+ledger but not yet for policy/approvals/entitlements.
**Flag for a follow-up RLS-extension task** (extend `_TABLES` + have those adapters set the GUC per
transaction).

### Gap 5 — No consent adapter on the operated plane
Neither operated tier declares a `consent` adapter under `[adapters]`, so **K·04 DPDP consent is not
enforced** on the shared plane (the `consent` wiring path exists at `delivery/sdk/kernel.py:532` but is
unused by these configs). **Flag** — intersects the T-5 legal-gating workstream; enabling consent on
the operated plane is a product+legal decision, not a pure code gap.

## Summary — what feeds D0-5 and what is a follow-up

- **D0-5 (durable hot-path closure):** Gap 1 — decide STARTER single-instance-pin vs. durable action
  repo + approvals queue; confirm `PostgresEntitlementRepository` wired into `build_saas_app` (already
  is, `entitlements_config.py:56`); add the horizontal-worker correctness test the DoD requires.
- **Follow-up (new task, not in current phase scope):** Gap 4 — extend RLS coverage to the policy,
  approvals, and entitlements/accounts tables + set the tenant GUC in those adapters.
- **Accepted/flagged (documented, fail-safe):** Gap 2 (event bus), Gap 3 (usage meter).
- **Product+legal decision:** Gap 5 (consent on the operated plane; see T-5).
