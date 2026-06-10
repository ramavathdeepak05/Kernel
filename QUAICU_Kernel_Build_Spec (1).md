# QUAICU Standalone Kernel — Tech Stack & Build Specification

**Version 1.0 · June 2026**
**Audience:** Engineering team building the standalone kernel
**Status:** Greenfield build. This is the spec to build against.
**Companion doc:** *QUAICU Governance Kernel — Product Documentation* (what the kernel is; this doc is how to build it).

---

## 0. Context (read first)

We are building the governance kernel **fresh** as a standalone product — not extracting it from the existing deployed product. The standalone kernel will be sold three ways to three kinds of customer:

- **Delivery modes:** Python SDK · FastAPI (REST) · Docker image
- **Customers:** AI agencies · product companies · banks/regulated enterprises

**Two facts that shape everything:**

1. **Build fresh — no reference from the previous product.** The existing deployed product proves the K·01–K·07 *concept* works in production (keep that for the sales and credibility story), but this build takes **no code, no schema, and no design reference from it.** Everything is built clean from this spec. K·08–K·14 are net-new with no prior implementation anywhere. Do not claim K·08–K·14 as shipped until they are. **Consequence:** there is no proven codebase to diff against, so correctness must be guaranteed by rigorous spec-driven testing (§8) — this is non-negotiable for a governance product.
2. **One core, zero forks.** The whole point of this build is that one codebase serves all three customer types. Differences between an agency, a product company, and a bank are absorbed as **configuration, adapters, and content packs — never as branches of core code.** The day someone forks core for "the bank version," this build has failed.

---

## Start Here (reading order for a new developer)

1. **§0 + §1** — why this exists and the rules that never bend (especially fail-closed, the Core Invariants, and the **Frozen Architecture Decisions**). Read these before writing any code.
2. **Glossary** (below) — so you use the words the way the rest of the team does.
3. **§4 Architecture + §5 Ports** — the shape of the system and the interfaces you build against.
4. **§7 Repo Structure** — where things live.
5. **§6 Build Order** — what to build first and when a layer is "done."
6. **§10 Worked Example** — see the whole lifecycle in real code before you start.
7. **§2 + §3** — the stack and the reasoning behind each choice. **§8** — the rules CI will enforce on your PRs.

If you only remember two things: **fail closed** (§1), and **one core, no forks** (§1).

## Glossary (ubiquitous language — use these exact terms)

Divergent vocabulary is how a spec drifts into divergent implementations. These terms mean exactly this, everywhere — in code, docs, and conversation.

| Term | Definition |
|------|-----------|
| **Action** | A proposed change to institutional state. The atomic unit the kernel governs. Has a type, a payload, an actor, and a tenant. |
| **Proposal** | The act of submitting an action. A proposal **never** executes directly — it enters the lifecycle. |
| **Governed action** | An action that has completed the full lifecycle (evaluate → gate → execute → seal → emit). |
| **Policy** | A rule, stored as **data** (not code), that evaluates an action and returns allow / deny / require-approval. |
| **Evaluation** | The Policy Engine step that resolves an action against all applicable active policies. |
| **Gate** | The HITL checkpoint. If a policy returns require-approval, the action halts here until a human decides. |
| **Execute** | The state transition that actually changes institutional state — only after evaluate and gate pass. |
| **Seal** | Writing the completed action to the TrustLedger with its integrity proof. |
| **Emit** | Publishing the structured event after seal. |
| **Actor** | The authenticated identity (human or system) on whose behalf an action is proposed. Resolved via `IdentityPort`. |
| **Tenant** | An isolated customer boundary. No state, decision, or ledger entry crosses it. |
| **Port** | An interface in `core/ports/` that core depends on. Core never imports a concrete implementation. |
| **Adapter** | A concrete implementation of a port (e.g., the Temporal `WorkflowPort` adapter), selected by config. |
| **Content pack** | Policies and regulatory maps shipped as data, loaded per customer. Not code. |
| **Fail-closed** | On any failure or uncertainty, deny or halt — never allow. |
| **Layer** | One of the 14 governance capabilities (K·01–K·14). |
| **ActionState** | The lifecycle state of an action: `PROPOSED → EVALUATING → PENDING_APPROVAL → EXECUTING → SEALING → SEALED → COMPLETED`, plus terminal `DENIED` / `HALTED` / `CANCELLED`. Distinct from **Decision** (a state is where the action *is*; a decision is what a policy *returned*). |
| **Decision** | The Policy Engine's output for an action: `allow` · `deny` · `require_approval`. It drives the next ActionState; it is not itself a state. |
| **Idempotency key** | Caller-supplied key, unique per `(tenant, key)`. Re-submitting the same key returns the existing action — it never re-executes, re-seals, or re-emits. |
| **Impact report** | The backtest / shadow-mode output (decision distribution, the actions whose decision flips, the fairness delta) a reviewer signs before a policy may move to `ACTIVATED` (F-10). |
| **Inclusion proof / Consistency proof / Signed Tree Head (STH)** | The three RFC 6962 artifacts K·02 produces: proof that an entry is in the log; proof the log was not retroactively edited; and the signed Merkle root at a point in time. |

---

This is a **governance product**. It optimizes for **correctness, auditability, portability, and operational simplicity in someone else's environment** — not raw performance or novelty. Every stack and design decision below serves that order of priorities.

1. **One core, no forks.** Customer-specific behavior lives in config, adapters, or content packs.
2. **Ports and adapters (hexagonal).** Core depends on interfaces, never on concrete implementations. The host (or config) supplies the implementations.
3. **Core owns its storage.** The kernel ships its own schema and migrations. It never assumes the host's database or domain tables.
4. **Zero domain imports.** A grep of `core/` for any domain concept (student, loan, patient, etc.) must return nothing.
5. **Config over code.** A new customer is onboarded by selecting adapters and loading policy/regulatory packs — not by editing core.
6. **Prove, don't assume.** With no prior implementation to test against, correctness is established by spec-driven testing — per-layer acceptance suites, property-based tests for invariants (ledger integrity, deterministic policy evaluation), and golden cases derived directly from policies and regulations. See §8.
7. **It runs in untrusted environments.** Threat-model accordingly: encryption at rest, signed releases, supply-chain hygiene, least privilege.
8. **Fail closed, always.** If any part of the chain fails, errors, times out, or is uncertain, the action is **denied or halted — never allowed through.** A governance kernel that fails open is worse than no kernel, because it manufactures false assurance. "If the policy service is unreachable, let it proceed" is a catastrophic bug, not a convenience. This applies everywhere: policy eval, consent check, HITL routing, ledger seal. If you can't seal it, you can't execute it.

### Core Invariants (must always hold — these are testable, not aspirational)

These are the properties every layer and the system as a whole must guarantee. Each one gets property-based tests (§8).

- **Fail-closed:** any failure or ambiguity → DENY/HALT. Never allow.
- **No bypass:** there is no code path that executes or seals an action which skipped evaluation and gating. Even administrative actions are governed actions.
- **Determinism:** identical inputs produce an identical policy decision. No hidden state, no wall-clock-dependent branching in evaluation.
- **Total conflict resolution:** policy evaluation never returns "undefined." Deny overrides allow; most-specific scope wins; the resolution order is explicit and exhaustive.
- **Tenant isolation:** no data, decision, policy, or ledger entry ever crosses a tenant boundary. Enforced at every layer and tested adversarially.
- **Ledger immutability & forward-verifiability:** a sealed entry is never modified. The proof format must remain verifiable for the life of the product — you can change how you seal *new* entries, but you can never break verification of *old* ones.
- **Idempotency:** re-submitting the same proposal (same idempotency key) must not double-execute, double-seal, or double-emit.
- **Trustworthy ordering:** ledger ordering depends on a consistent clock and monotonic sequence; handle clock skew explicitly, especially in air-gapped deployments where there is no external time source.
- **Replay fidelity & side-effect freedom:** any governed action can be re-derived from the ledger using the policy versions and recorded results in effect *at the time* — and replay reconstructs or re-evaluates only; it never re-performs an external side effect. See §3.13.

### Frozen Architecture Decisions (ADRs) — settled, do not reopen

These are foundational. Each underpins multiple other parts of the system, so re-litigating one destabilizes far more than itself. **They do not change via code review.** Superseding one requires a written ADR that documents the new context, gets leadership sign-off, and updates every dependent section — not a PR comment and not a "quick exception." If you find yourself wanting to reopen one, that is almost always a signal you are solving the problem in the wrong place. The default answer to "can we reopen this?" is **no**.

| ADR | Frozen Decision | Settled — the move it forecloses |
|-----|-----------------|----------------------------------|
| **F-01** | **One core, no forks.** One core codebase serves all customers. | "Let's fork a bank-specific build." No — customer divergence lives in config, adapters, and content packs, never a code branch. |
| **F-02** | **Governance is the product — model- and deployment-agnostic.** The kernel governs the action regardless of which model produced it or where it runs. | "Let's bundle our own models / mandate local inference / become a model vendor." No — inference and deployment are pluggable choices, not the product. |
| **F-03** | **Fail-closed everywhere.** Any failure, timeout, or ambiguity → deny/halt. | "Let it through if the policy service is slow or down." No — failing open manufactures false assurance; it is the worst possible bug here. |
| **F-04** | **No bypass — governance is total.** No path executes or seals an action that skipped evaluation and gating; even admin actions are governed. | "Add a fast-path that skips the kernel for low-risk or admin actions." No — there is no shortcut around Ring 0. |
| **F-05** | **CEL is the policy condition language** (declarative envelope + CEL; deterministic, sandboxed). | "Allow Python expressions / invent a DSL / embed raw Rego." No — Python and custom DSLs are rejected; Rego only ever behind the authoring API, never raw. |
| **F-06** | **RFC 6962-style transparency log for the ledger — no custom proof structures.** | "Design our own proof format / optimize the Merkle tree our way." No — every deviation from RFC 6962 is liability we must defend to a reviewer. |
| **F-07** | **Per-tenant ledger, always** — per-tenant tables inside the tenant's schema, never a shared table keyed by `tenant_id`. | "Consolidate ledgers into one table with a tenant_id for scale." No — cross-tenant ledger contamination must be *impossible*, not merely unlikely. |
| **F-08** | **Ports and adapters (hexagonal).** Core depends only on `core/ports/` interfaces. | "Call this model SDK / database / queue directly from core to save a layer." No — core never imports a concrete implementation. |
| **F-09** | **Replay-safe, side-effect-free execution.** Actions are re-derivable from the ledger using the versions/results in effect at the time; non-determinism is recorded, never recomputed; replay never causes an external effect. | "Recompute model calls on replay / let replay re-trigger effects / record only outcomes, not inputs." No — replay fidelity is load-bearing for audit, rollback, and sandbox. |
| **F-10** | **Simulation before enforcement.** No policy enforces until simulated; high-impact activations are gated on a reviewed impact report (backtest, plus shadow mode above threshold). | "Push this policy straight to production to move faster." No — the activation gate is enforced in the lifecycle state machine, not optional. |
| **F-11** | **Config over code.** Onboarding a customer is configuration + content packs, never editing core. | "Just add a small `if` for this one customer." No — that is the first crack in F-01. |

If a customer requirement appears to need violating one of these, the requirement is met through the adapter, config, or content-pack layers — or it is declined. The frozen set is not negotiable per deal.

> **Two ADR tiers — don't confuse them.** F-01–F-11 above are the *frozen* foundational decisions; they live here and only change via the formal supersede process. *Extension* ADRs — design decisions made while building **within** these constraints — are logged separately in `New/quaicu-kernel/docs/adr/` (ADR-0001 froze the code contract surface; ADR-0002+ record composable governance, the decision-only authorization surface, zero-friction integration, and the durable policy store). Extension ADRs must each stay consistent with the frozen set; none supersedes an F-ADR. As of 2026-06-10 every shipped extension upholds F-01–F-11 (e.g. composable profiles are presets, not forks → F-01; the durable policy store keeps CEL, the F-10 activation gate, and config-over-code → F-05/F-10/F-11).

---

## 2. Recommended Tech Stack

| Concern | Choice | Status vs prior stack |
|---------|--------|----------------------|
| Core language | **Python 3.11+** | Keep (matches proven code, AI ecosystem) |
| Hot-path language (optional) | **Go** — only if profiling proves a bottleneck | New / deferred |
| API framework | **FastAPI** | Keep |
| Primary datastore | **PostgreSQL 16+ with pgvector** | Keep |
| Schema migrations | **Alembic** | Keep |
| Secrets management | **OpenBao** (MPL 2.0) | **CHANGED from Vault — see §3.1** |
| Durable workflow / Process Engine | **Temporal** (tiered) or Postgres state machine | **New — see §3.2** |
| Lightweight async (monitoring jobs) | **ARQ** or **Dramatiq** | **CHANGED from Celery — see §3.3** |
| Audit ledger structure | **Merkle / transparency-log on PostgreSQL** | **CHANGED from plain hash chain — see §3.4** |
| Object storage | **MinIO** (S3-compatible) | Keep |
| Inference (pluggable) | **Local:** Ollama / vLLM / TGI · **Cloud:** OpenAI, Anthropic, Gemini · **Hyperscaler:** Bedrock, Azure OpenAI, Vertex | Keep (pluggable — see §3.5) |
| Orchestration | **k3s / docker-compose** (small, sovereign) · **K8s** (dedicated, cloud) | **CHANGED — tiered, see §3.6** |
| Infrastructure-as-code | **OpenTofu** | **CHANGED from Terraform — see §3.7** |
| Observability | **OpenTelemetry + Prometheus + Grafana + Loki** | Keep |
| Admin console / dashboards | **React 19 + TypeScript** | Keep |
| SDK | **Python SDK** (`@governed` decorator) · other languages via generated REST clients | New |

---

## 3. Stack Decisions in Detail

### 3.1 OpenBao instead of HashiCorp Vault — **do this, it's a licensing issue**

Vault is under the Business Source License (BSL 1.1) since August 2023. BSL prohibits offering the software as a hosted or **embedded** service to third parties in competition with HashiCorp's paid products. Our model — embedding a secrets layer into a kernel we license and ship to third parties (agencies, product companies, banks) — sits squarely in the use BSL restricts.

**OpenBao** is the Linux Foundation fork under MPL 2.0 (a genuine open-source license with no such restriction). It is **API-compatible** with Vault — the existing Vault client libraries and providers work against it largely unchanged. It also includes **namespaces (multi-tenancy) for free**, which Vault gates behind Enterprise — directly useful given the kernel is inherently multi-tenant.

**Action:** Build against OpenBao from day one. Do not introduce a Vault dependency. Have legal confirm our specific exposure, but the safe and cheaper path is OpenBao regardless.

### 3.2 Process Engine (K·06) — durable execution

K·06 is a durable state machine with human-in-the-loop pauses (K·03) and incident rollback (K·12). This is exactly what durable-execution engines (Temporal, and alternatives like Restate/DBOS) provide natively: durable state, automatic retries, signal-based human pauses, and replay — which for a governance product is correctness you can show an auditor, not just convenience.

**The tension:** Temporal adds a server to operate, which fights the air-gapped/sovereign simplicity goal for small deployments.

**Decision — tier it behind a port:**
- Define a `WorkflowEngine` port (see §5).
- **Dedicated / cloud tier:** Temporal (self-hosted) adapter.
- **Small / sovereign / air-gapped tier:** a lightweight Postgres-backed state-machine adapter (no extra server).
- **Resolved:** both adapters ship. Build the Postgres adapter first (it unblocks the sovereign tier and the earliest runnable build); build the Temporal adapter alongside and select per deployment via config. Neither is "the default" globally — the tier and the customer's operational capacity decide which is active.

Never let workflow-engine choice leak into core logic — it's an adapter behind `WorkflowPort`.

### 3.3 Async jobs — ARQ/Dramatiq, not Celery

For a fresh build, Celery is heavy and aging. Durable, long-running governed workflows belong in the Process Engine (§3.2). For the lighter background work — fairness sweeps (K·09), drift monitoring (K·10), scheduled evidence generation — use a lean async task runner: **ARQ** (asyncio-native, pairs well with FastAPI) or **Dramatiq**. Keep it behind a small interface so it's swappable.

### 3.4 TrustLedger (K·02) — Merkle / transparency-log, not a plain hash chain

The ledger is the product's credibility. A plain hash chain is O(n) to verify — a regulator verifying integrity has to walk the entire chain. Build the ledger as a **Merkle-tree / transparency-log structure** (the model behind certificate transparency, Trillian, Sigstore) on top of PostgreSQL. This gives:
- **Efficient inclusion proofs** — prove a specific action is in the ledger without replaying everything.
- **Efficient consistency proofs** — prove the ledger hasn't been tampered with or retroactively edited.
- A clean `verify` operation that returns a signed integrity proof suitable for regulatory submission.

This is contained to one layer and directly strengthens the audit story that is the entire pitch. Per-tenant ledger; no cross-tenant structure.

**Resolved: build in-house** (not a third-party library). This is the right call for control and zero external dependency in air-gapped installs — but understand what it commits you to. The ledger is the **single highest-risk piece of correctness in the entire kernel**: it is the artifact a bank's security reviewer and a regulator will scrutinize hardest, and a subtle flaw in the integrity proof undermines the whole product. Building it in-house therefore requires disproportionate rigor:
- Property-based tests proving the invariants always hold (append-only, inclusion proofs verify, consistency proofs detect any retroactive edit, hash chain unbroken under concurrent writes).
- Published, versioned test vectors for the proof format.
- A **third-party cryptographic review** of the implementation before it ships to any bank. Budget for this explicitly — it is a sales asset as much as a safeguard.
- Use well-understood, standard primitives (e.g., SHA-256, RFC 6962-style Merkle structures). Do not invent the cryptography; only build the implementation.

**Scope discipline (per review):** implement a **minimal RFC 6962-style transparency log first** — append-only Merkle tree, signed tree heads, inclusion proofs, and consistency proofs exactly as the RFC defines them. **Do not design any custom proof structures.** RFC 6962 is the certificate-transparency standard; it is peer-reviewed, widely implemented, and is what an external reviewer will expect to see. Every deviation from it is liability you take on and have to defend. Ship the standard log, get it reviewed, and only consider extensions later if a concrete requirement forces it — never invent a bespoke proof format up front. Treat the RFC as the spec for this layer.

### 3.5 Inference — pluggable, governed, never hardcoded

The AI Gateway (K·05) abstracts the inference runtime. Backends are config-selected per tenant:
- **Local:** Ollama (simplest, air-gapped), vLLM (high throughput), TGI.
- **Cloud APIs:** OpenAI, Anthropic, Gemini.
- **Hyperscaler-in-tenancy:** AWS Bedrock, Azure OpenAI, Google Vertex.

Adding a backend must not change core. The active backend is itself a governed decision — recorded in the Model Registry (K·08) and the ledger. PII masking happens at the Gateway before transmission, for **every** backend including cloud. (See the product doc §1.5 for the deployment/inference tiers.)

### 3.6 Orchestration — tier it to the customer

Full Kubernetes for a small sovereign install is an operational burden on a customer who may have no platform team. Match the weight to the deployment:
- **Small / sovereign / air-gapped:** k3s, or docker-compose for the simplest installs.
- **Dedicated / cloud:** full K8s.
- Ship **Helm charts** that work for both. The kernel image is identical; only the orchestration wrapper differs.

### 3.7 OpenTofu instead of Terraform

Terraform is also under BSL. For consistency with the OpenBao decision and to keep our shipped/embedded IaC unrestricted, use **OpenTofu** (the MPL 2.0 fork). API/HCL-compatible.

### 3.8 Hot-path language — Python now, Go only on evidence

Every governed action passes through the Policy Engine and AI Gateway, so latency there compounds. **Do not pre-optimize.** Build in Python. If profiling later shows the Python layer itself (not the database or model calls — which are the usual real bottlenecks) is the constraint at a high-volume customer, the move is a **polyglot split**: keep Python for the AI Service and move the hot path (policy evaluation, ledger append, gateway routing) to **Go** — which also compiles to a single static binary, valuable for air-gapped installs. Treat this as a scale-driven decision with profiling evidence, not a day-one choice.

### 3.9 Policy authoring & language (K·01) — *resolves the biggest open gap*

Until this is fixed, K·01 is underspecified. **Decision: a declarative policy envelope (YAML to author, stored as JSON) + CEL (Common Expression Language) for conditions.**

**Why CEL, not the alternatives:**
- **CEL** is deterministic, **non-Turing-complete (guaranteed to terminate)**, sandboxed (no I/O, no clock, no randomness, no side effects), fast, and embeddable. It is proven at scale in Kubernetes admission control. Its constraints are exactly what our Core Invariants demand — determinism, total evaluation, fail-closed. This is the recommendation.
- **Python expressions — rejected outright.** `eval` is non-deterministic, unsandboxable in practice, and a security hole. It violates the determinism and isolation invariants. Never.
- **Rego / OPA — considered, deferred.** More powerful than we need, a heavier dependency, and harder for compliance officers and partners (KPMG-type) to read and audit. Revisit only if policy *composition* complexity genuinely demands it — and if so, behind the same authoring API, not exposed raw.
- **Pure YAML/JSON with no expression language — insufficient.** Real policies need thresholds, comparisons, and combinations; a data format alone can't express them. Hence the envelope-plus-CEL split.

**Policy envelope (the authorable unit):**

```yaml
id: ciro.ifrs9.stage_transition
version: 3
governs: ciro.ifrs9.stage_transition      # action type this policy applies to
scope: { tenant: "*" }                     # tenant / segment selector
condition: |                               # CEL — deterministic, bounded, sandboxed
  action.payload.to_stage > action.payload.from_stage
  && action.payload.exposure > 5000000
decision: require_approval                 # allow | deny | require_approval
approvers: ["role:risk_head"]              # required if decision == require_approval
regulatory_refs: ["rbi.ifrs9.staging",     # links to K·14 regulation catalog
                  "rbi.free_ai.governance"]
lifecycle: ACTIVATED                        # DRAFT → REVIEW → ACTIVATED → DEPRECATED
```

**Authoring pipeline (and how it ties to other layers):** author in YAML → JSON-schema validation → **CEL compile-check** (must compile, must be statically bounded) → **dry-run in Sandbox (K·13)** against historical ledger data to see what it would change → human review → activate. Activated versions are immutable; a change is a new version. CEL evaluation has no access to wall-clock, network, or randomness — this is what guarantees the determinism invariant.

**Policy simulation before enforcement (mandatory, two modes).** No policy enforces until it has been simulated. There are two complementary modes, both **side-effect-free** (per §3.13 — a simulated decision never enforces, never triggers a real HITL request, never seals a production ledger entry; results go to a clearly-marked sandbox/shadow partition):

- **Backtest (historical).** The candidate policy runs against past ledger actions via K·13 / counterfactual replay. Tells you what *would have* changed on historical data. Fast, always required.
- **Shadow mode (live / dark launch).** The candidate evaluates **in parallel with the active policy on live incoming actions** — its decision is recorded but **not enforced**; the active policy still governs. After a configured window or volume, compare shadow vs active. Catches current-traffic behavior a historical backtest cannot. This is the mode bank risk teams expect before any rule change goes live.

Both modes emit a structured **impact report**: decision distribution active vs candidate, the specific actions whose decision would flip, and the **fairness delta** (via K·09). The report is what a reviewer signs off.

**Activation gate (this is the part that must be enforced, not optional).** A policy version cannot transition to `ACTIVATED` unless:
- a **backtest impact report** exists and has been reviewed and acknowledged; and
- for changes whose backtest projects an impact above a configurable threshold (e.g., % of decisions that flip, or any fairness-delta breach), a **shadow-mode window** has been run and cleared first.

Low-impact or first-time policies: backtest suffices. High-impact changes: shadow mode is required before enforcement. The gate is enforced in the lifecycle state machine — there is no path from `REVIEW` to `ACTIVATED` that skips it.

**Single-action pre-flight.** Separately, the `POST /kernel/v1/policy/evaluate` endpoint dry-runs a *single* proposed action without enforcing — so a host app can ask "would this be allowed?" before proposing. Also side-effect-free.

### 3.10 Multi-tenancy & scaling model — *explicit decisions banks will ask for*

The isolation **invariant** (§1) says nothing crosses a tenant boundary. Here is how that is realized physically, by tier:

| Tier | Database | Schema | Isolation basis |
|------|----------|--------|-----------------|
| **Sovereign** | One DB, one tenant, on their hardware | n/a (single tenant) | Physical |
| **Dedicated** | One DB **instance per tenant** in their VPC | n/a (single tenant) | Instance |
| **Shared** (small, QUAICU-hosted) | Shared instance | **Schema-per-tenant** (default) | Schema + Row-Level Security as defense-in-depth |

**Decisions:**
- **Schema-per-tenant is the default for the shared tier** — each tenant gets its own schema, tables, and migrations. Strong isolation, clean per-tenant export/delete, defensible to a bank's reviewer.
- **Row-Level Security (RLS)** is enabled as a backstop even under schema-per-tenant — defense in depth.
- **Shared-schema-with-tenant_id-column is rejected as the default.** A single mis-filtered query leaks across tenants — unacceptable against the isolation invariant. Use it *only* if forced to scale to many thousands of tiny tenants where per-schema overhead bites, and even then it never applies to the ledger.
- **The ledger is always per-tenant tables inside the tenant's schema — never a shared ledger table keyed by tenant_id.** Cross-tenant ledger contamination is the precise failure a bank fears; the architecture must make it *impossible*, not merely unlikely.

**Scaling:** schema-per-tenant scales comfortably to hundreds–low-thousands of tenants per database; beyond that, shard tenants across databases (the Control Plane already manages tenant→DB placement). Migrations roll out per-schema under controlled orchestration.

### 3.11 Regulatory Mapping specification (K·14) — *engineering, not vision*

Concrete definitions for the four things the review flagged as missing.

**Mapping format.** Two versioned data structures, shipped as content packs:
- *Regulation catalog* — each requirement is `{ id, regulation, version, clause, description }`, e.g. `rbi.free_ai.sutra.3`.
- *Mapping* — a many-to-many relation between a **requirement-version** and a **policy-version**. Policies declare `regulatory_refs`; the mapping materializes the inverse (requirement → enforcing policies).

**Evidence generation process.** Given `(requirement, time_period)`:
1. Resolve the policies mapped to that requirement **that were active during the period** (not now).
2. Find the governed actions those policy-versions evaluated within the period.
3. Collect the corresponding ledger entries and their RFC 6962 inclusion proofs.
4. Emit a **signed evidence pack** = human-readable document + machine-readable manifest + ledger proof references, verifiable via the K·02 `verify` operation.
This is **point-in-time correct** — evidence reflects the rules and policies as they stood *then*, which is what an auditor actually needs.

**Regulatory update mechanism.** A regulation change is published as a **new catalog version**. Mappings that reference changed requirements are automatically flagged `review_required`. A human then reviews and updates the affected policies. **Nothing auto-changes policy** — auto-mutating governance from a regulatory feed is itself a risk; the system surfaces the impact and requires human action.

**Versioning strategy.** The catalog is versioned independently of policies. Mappings pin specific versions of both. Evidence is always generated against the versions active in the queried window. This keeps historical evidence stable even as regulations and policies evolve.

### 3.12 AI Gateway full specification (K·05) — *the four deferred concerns*

§3.5 covers pluggable inference. This covers the governance concerns a reviewer correctly flagged. (Deep PII-masking implementation remains the dedicated workstream from §9 Decision 4; the *design shape* is specified here so it is no longer a black box.)

**PII masking (design shape):**
- *Detection* — primary signal is **tenant-declared sensitive fields** (from the action schema), augmented by pattern/regex detectors and optional NER. Tenant-declared is the reliable backbone; detectors catch free-text leakage.
- *Masking* — sensitive spans are tokenized; the reversible token→value mapping is held in the **tenant's own storage and never transmitted to the model**.
- *Re-hydration* — tokens are mapped back to values in the response, in-tenant.
- *Honest residual risk* — masking free-text is best-effort, not perfect. For maximum-sensitivity workloads the answer is the **Sovereign tier** (local inference, nothing transmitted). The kernel records, per action, which masking was applied — so the guarantee is never ambiguous.

**Prompt logging strategy:**
- Every model call logs prompt hash, response hash, model+version, runtime/location, tenant, and originating action — **sealed to the ledger**.
- The full **masked** prompt/response is stored in tenant storage with **configurable retention**; raw unmasked content is never stored outside the tenant and never leaves for cloud/hyperscaler tiers.
- Logging is **mandatory and fail-closed**: if a call cannot be logged, the call is not made. An unlogged model call is, by definition, ungoverned.

**Model routing policies:**
- Routing is **policy-driven (K·01)**: `(action type, data sensitivity, tenant)` → permitted model(s).
- Enforced against the per-tenant allowlist in the **Model Registry (K·08)**.
- **Fail-closed**: if no permitted model is available, **deny** — never silently fall back to an unapproved model.
- The routing decision (which model, why) is recorded with the action.

**Cost governance:**
- Per-tenant **token/cost budgets** enforced at the gateway.
- **Cost attribution per action and per tenant** recorded — for chargeback and as part of the audit trail.
- Budget-exhaustion behavior is policy-configured (`block` | `degrade to a cheaper permitted model` | `alert`) but **defaults to `block` (fail-closed)** for governed actions.

### 3.13 Replayability — *make it a first-class concern, not an assumption*

Replay was assumed in several layers (K·02 state reconstruction, K·12 rollback, K·13 sandbox, K·14 point-in-time evidence, and Temporal's K·06 execution model) but never specified. Audit, rollback, sandbox, and evidence all depend on it, so it needs explicit requirements or those features break silently.

**Three replay modes — distinct requirements, do not conflate:**
1. **State reconstruction** — rebuild institutional state as of any time T by re-applying recorded state transitions from the ledger.
2. **Decision (audit) replay** — re-derive *why* a past action was decided as it was, using the policy versions, inputs, consent state, assurance signals, and recorded model outputs **as they were at the time.** Point-in-time correct.
3. **Counterfactual replay** — re-run historical actions against *candidate* policies or models to see what would change. This is the Sandbox (K·13).

**Ledger capture requirement (K·02): record inputs and results, not just outcomes.** Each sealed entry must hold enough to reconstruct the decision — the action payload, actor, the **policy versions** evaluated, the evaluation result, consent state, the assurance signals (K·08–K·11), and the **recorded non-deterministic results**, chiefly the model output from the Gateway (K·05). An entry that records only "approved by policy X" is not replayable.

**Non-determinism rule (mandatory — the Temporal pattern):** anything non-deterministic — model calls, external lookups, time, randomness — has its result **recorded at original execution and reused on replay, never recomputed.** You cannot replay a model call by calling the model again; you replay from the recorded response. This is precisely why determinism is a Core Invariant and why the Gateway logs every response.

**Side-effect freedom (critical):** replay **reconstructs or re-evaluates; it never re-performs external effects.** Replaying a loan reclassification must not re-disburse; replaying a notification must not re-send. `execute` (the single real state change) and replay are cleanly separated — replay reads recorded effects, it does not trigger new ones. A replay that causes a side effect is a critical bug, tested against explicitly.

**Implication for K·06 (Process Engine):** workflow logic must be replay-safe — deterministic, with all external/non-deterministic operations behind **recorded activities.** This is native to the Temporal adapter (its model *is* deterministic replay) and an explicit requirement on the Postgres state-machine adapter: a process's state must be reconstructable purely from its recorded transition events. No workflow branch may depend on un-recorded wall-clock, randomness, or live external state.

**Build note:** this points the ledger toward an **event-sourced** shape — the recorded events are the source of truth and current state is a projection of them. Decide this explicitly during K·02 design; retrofitting event-sourcing onto a state-first ledger is expensive.

---

## 4. Architecture: One Core, Four Layers of Packaging

```
┌──────────────────────────────────────────────────────┐
│ DELIVERY ADAPTERS (thin wrappers over core)            │
│   Python SDK   ·   FastAPI/REST   ·   Docker image     │
├──────────────────────────────────────────────────────┤
│ CORE KERNEL — ONE CODEBASE, NO FORKS, NO DOMAIN IMPORTS│
│   Lifecycle spine + 14 layers + PORT INTERFACES         │
├──────────────────────────────────────────────────────┤
│ PLUGGABLE ADAPTERS (selected by config)                │
│   Inference · HITL · Identity · Storage · Workflow      │
├──────────────────────────────────────────────────────┤
│ CONTENT PACKS (data, not code)                         │
│   Policy packs · Regulatory maps (RBI, EU AI Act, DPDP) │
└──────────────────────────────────────────────────────┘
```

Onboarding a customer = pick a deployment target + set adapters in config + load relevant packs. No core code is touched.

---

## 5. The Ports (core depends on these interfaces, not implementations)

Define these as `typing.Protocol` (or ABC) interfaces in `core/ports/`. Adapters in `adapters/` implement them; config selects which. Signatures below are the contract — types are illustrative but the shape is binding. **Every port method must honor fail-closed:** on error or timeout, raise — never return a permissive default.

```python
# core/ports/inference.py
class InferencePort(Protocol):
    async def generate(self, *, prompt: Prompt, model_ref: ModelRef,
                       tenant: TenantId) -> ModelResponse: ...
    # Implementations: ollama, vllm, tgi, openai, anthropic, bedrock, azure_openai, vertex
    # Core NEVER imports a model SDK directly — only this port.

# core/ports/hitl.py
class HITLPort(Protocol):
    async def request_approval(self, *, action: Action, approvers: list[ApproverRef],
                               tenant: TenantId) -> ApprovalHandle: ...
    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision: ...   # PENDING|APPROVED|REJECTED
    # Implementations: webhook (default), email, slack, inapp
    # Timeout/escalation is policy-configured; a timeout resolves to a fail-closed outcome (no approval ⇒ no execute).

# core/ports/identity.py
class IdentityPort(Protocol):
    async def resolve_actor(self, *, context: RequestContext,
                            tenant: TenantId) -> Actor: ...
    # Kernel takes identity from the host; it does NOT own auth.
    # Implementations: oidc, jwt, host_provided

# core/ports/storage.py
class StoragePort(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[Transaction]: ...
    # Kernel-owned schema only. Transactional. Core NEVER assumes the host's tables.
    # Implementation: postgres

# core/ports/workflow.py
class WorkflowPort(Protocol):
    async def start(self, *, definition: ProcessDef, payload: dict,
                    tenant: TenantId) -> WorkflowHandle: ...
    async def signal(self, handle: WorkflowHandle, signal: Signal) -> None: ...
    async def state(self, handle: WorkflowHandle) -> ProcessState: ...
    # Implementations: postgres_statemachine (sovereign, built first), temporal (dedicated/cloud)
```

**The lifecycle contract** every governed action follows (this is the core API the delivery adapters expose). Each arrow is a point where fail-closed applies — a failure at any step aborts the action; it does not skip ahead.

```
propose(action) → evaluate(K·01, K·04, K·08–K·11) → gate(K·03) →
execute(K·06) → seal(K·02) → emit(K·07)

   any error / timeout / ambiguity at any arrow  ⇒  DENY / HALT (never proceed)
```

---

## 6. Build Order

Build the spine and ports first; everything hangs off them. This is a **strict sequence** — build each step only after the steps it depends on. The *needs / because* on each line is the dependency; do not reorder past it.

1. **Spine + ports + errors + types** (`core/lifecycle`, `core/ports`, `core/errors`, `core/types`). *Needs:* nothing. *Because:* every layer plugs into the spine and imports the port interfaces and shared types — nothing compiles or runs without them.
2. **K·01 Policy Engine.** *Needs:* 1. *Because:* it is the lifecycle's `evaluate` step; no action reaches `execute` without it (F-04). Conditions are CEL; conflict resolution is total.
3. **K·02 TrustLedger.** *Needs:* 1 + StoragePort. *Because:* it is the `seal` step — no action is "done" until sealed — and its record-inputs-and-results shape (F-09 / §3.13) dictates what every later layer must record. Fix the event-sourced ledger shape **here**, before any assurance layer writes into it; retrofitting it later is expensive.
4. **K·03 HITL.** *Needs:* 1, 2. *Because:* it is the `gate` step, and the gate only fires when K·01 returns `require_approval`. A timeout here resolves fail-closed (REJECTED).
5. **K·06 Process Engine.** *Needs:* 1, 4. *Because:* it durably holds the HITL pause across restarts and later powers K·12 rollback. Build the **Postgres state-machine adapter first** (unblocks the sovereign tier and the earliest runnable loop); build the **Temporal adapter alongside** — both pass the same `WorkflowPort` conformance suite; config selects.
6. **K·07 Event Bus.** *Needs:* 2. *Because:* `emit` happens only after `seal`; a failed emit never alters a sealed outcome. Completes the lifecycle loop.
7. **K·05 AI Gateway.** *Needs:* 1, 2. *Because:* routing is a K·01 policy decision and every model call is sealed to K·02. Build early — it is part of the first runnable loop. Calls go through `InferencePort` only; prompt logging is fail-closed.
8. **K·04 DPDP Consent.** *Needs:* 1, 2. *Because:* it is a second `evaluate`-time signal whose state is recorded in the ledger entry for point-in-time replay. Build when the first client touches personal data.
9. **K·08 Model Registry.** *Needs:* 7. *Because:* it holds the per-tenant model allowlist the Gateway enforces, and K·09–K·11 reference registered models — so it must exist before any assurance layer.
10. **K·09 Fairness · K·10 Drift · K·11 Explainability.** *Needs:* 2, 9. *Because:* they read registered models (K·08) and recorded inputs/results (K·02) to produce assurance signals and feed K·01 impact reports. They run as lean async sweeps (ARQ/Dramatiq), never in the hot path.
11. **K·13 Sandbox.** *Needs:* 1, 2. *Because:* counterfactual replay (recorded model outputs + a candidate policy, written only to a shadow partition) is what K·01's mandatory backtest (F-10) runs on. **Forward-dependency note:** until K·13 exists, K·01's activation gate cannot be fully automated — gate activations manually and mark them backtest-pending.
12. **K·12 Incident.** *Needs:* 2, 5. *Because:* rollback is itself a governed action through the full lifecycle (no out-of-band effects) and reconstructs pre-incident state by replaying K·02.
13. **K·14 Regulatory Mapping.** *Needs:* 1, 2. *Because:* point-in-time evidence packs are built from K·02 inclusion proofs and the K·01 policy versions (with `regulatory_refs`) active in the queried window.

### Scope (all 14 layers)

The delivery target is the **full 14-layer kernel (K·01–K·14)**, each built to its per-layer Definition of Done below. Build in the strict order above; a complete, demonstrable governance loop comes together once K·01, K·02, K·03, K·05, and K·07 are standing, with the remaining layers continuing from there — but every layer is in scope and none is deferred out of the build.

**Keep claims honest:** K·01–K·07 rebuild a concept already proven in the existing deployment; K·08–K·14 are genuine net-new with no prior implementation. Do not describe K·08–K·14 as shipped until they meet their Definition of Done.

### Definition of Done (every layer must meet all of these)

A layer is not "done" when the happy path works. It is done when:

- [ ] **Public API documented** — quickstart + reference in `docs/`. A layer with no docs is not shipped.
- [ ] **Conformance suite passing** — spec-derived golden cases covering the layer's defined behavior.
- [ ] **Invariant property tests passing** — the relevant Core Invariants (§1) proven, not assumed. (e.g., K·02: inclusion/consistency proofs always verify; K·01: evaluation total and deterministic.)
- [ ] **Fail-closed tested** — faults injected (dependency down, timeout, malformed input) and verified to DENY/HALT, never allow.
- [ ] **Tenant isolation tested** — adversarial test confirms no cross-tenant leakage.
- [ ] **Replay-safe** — for layers that touch state or the lifecycle: replay reconstructs faithfully from recorded inputs/results, and a replay-causes-no-side-effect test passes.
- [ ] **Telemetry emitted** — traces + metrics via OpenTelemetry, so a host can observe it.
- [ ] **Migrations included** if the layer owns tables.
- [ ] **Security review** for the security-critical layers (K·02 ledger, K·04 consent, K·05 gateway) — including the external crypto review for K·02 before any bank deployment.

#### Per-layer "done when" (the layer-specific stop condition, on top of the universal checklist above)

This is the crisp stop condition for each layer — what makes *this* layer done, beyond the nine boxes every layer shares. Coverage floors (per the testing strategy, §8): **K·02 95%**; **K·01, K·03, K·04, lifecycle, and tenant isolation 90%**.

| Layer | Done when (in addition to the universal checklist) |
|-------|----------------------------------------------------|
| **K·01 Policy** | CEL compiles + evaluates deterministically; conflict resolution total (deny > require_approval > allow; empty set → deny); no `REVIEW → ACTIVATED` path without a reviewed impact report (F-10); shadow mode runs side-effect-free. |
| **K·02 Ledger** | RFC 6962 inclusion **and** consistency proofs verify (0x00/0x01 domain separation); per-tenant tables only (F-07); append-only enforced at the DB; `seal` failure → action **HALTED**, never executed; STH signed via OpenBao. |
| **K·03 HITL** | `require_approval` suspends the action durably; approve/reject resumes correctly; timeout → **REJECTED** (never auto-approve); approver authority enforced by the lifecycle, not the port. |
| **K·04 Consent** | missing / expired / withdrawn consent → **DENY**; consent state recorded in the ledger entry; resolvable point-in-time for replay. |
| **K·05 Gateway** | all calls via `InferencePort` (no model SDK in core); prompt logged **before** the call (log-fail → DENY); PII masked before transmission with a per-tenant token map; no approved model → **DENY** (no fallback); budget exhausted → `block` by default. |
| **K·06 Process** | Postgres **and** Temporal adapters pass the same `WorkflowPort` conformance suite; all non-determinism behind recorded activities; state reconstructable from events; pause survives restart; adapter chosen by config. |
| **K·07 Events** | events emitted **only after** seal; emit is best-effort and never alters a sealed outcome; events carry tenant + action id; at-least-once delivery with idempotent consumers. |
| **K·08 Registry** | per-tenant model allowlist enforced by the Gateway; model + version recorded with each governed action; consulted before K·09–K·11. |
| **K·09 Fairness** | fairness metrics computed over registered models; fairness delta feeds the K·01 impact report; runs as an async sweep, not in the hot path. |
| **K·10 Drift** | drift measured against a recorded baseline; breaches raise K·12 incidents; deterministic given recorded inputs. |
| **K·11 Explain** | an explanation is derivable from recorded inputs/results for any governed action (point-in-time, no model re-call); attached to audit replay. |
| **K·12 Incident** | rollback runs as a governed action through the full lifecycle (no out-of-band effects); replay reconstructs pre-incident state; incidents link to the triggering ledger entries. |
| **K·13 Sandbox** | counterfactual replay uses recorded model outputs + the candidate policy; writes only to a shadow/sandbox partition; a zero-production-side-effect test passes; powers the F-10 backtest. |
| **K·14 RegMap** | evidence is point-in-time correct (policies/regulations as they were then); the signed evidence pack verifies via K·02 `verify`; a regulation change flags mappings `review_required` and never auto-mutates policy. |

---

## 7. Proposed Repository Structure

```
quaicu-kernel/
├── core/                      # ONE codebase · no forks · zero domain imports
│   ├── lifecycle/             # propose→evaluate→gate→execute→seal→emit
│   ├── policy/                # K·01
│   ├── ledger/                # K·02  (Merkle / transparency-log)
│   ├── hitl/                  # K·03
│   ├── consent/               # K·04
│   ├── gateway/               # K·05
│   ├── process/               # K·06
│   ├── events/                # K·07
│   ├── registry/              # K·08
│   ├── fairness/              # K·09
│   ├── drift/                 # K·10
│   ├── explain/               # K·11
│   ├── incident/              # K·12
│   ├── sandbox/               # K·13
│   ├── regmap/                # K·14
│   └── ports/                 # InferencePort, HITLPort, IdentityPort, StoragePort, WorkflowPort
├── adapters/                  # implement ports · selected by config
│   ├── inference/             # ollama, vllm, openai, anthropic, bedrock, azure, vertex
│   ├── hitl/                  # webhook, email, slack, inapp
│   ├── identity/              # oidc, jwt, host_provided
│   ├── storage/               # postgres
│   └── workflow/              # postgres_statemachine, temporal
├── delivery/                  # the three modes — THIN wrappers over core
│   ├── sdk/                   # Python SDK (@governed)
│   ├── api/                   # FastAPI REST (also generates the OpenAPI clients)
│   └── docker/                # Dockerfile · compose · helm charts (k3s + K8s)
├── packs/                     # CONTENT, not code
│   ├── policies/              # policy packs per domain
│   └── regmaps/               # RBI FREE-AI, EU AI Act, DPDP, NAAC mappings
├── migrations/                # Alembic — kernel owns its schema
├── tests/
│   ├── conformance/           # spec-driven acceptance + golden cases per layer
│   ├── property/              # invariants: ledger integrity, deterministic policy eval
│   ├── unit/
│   └── integration/
└── docs/                      # developer docs — quickstart per mode, API ref, guides
```

---

## 8. Engineering Non-Negotiables

- [ ] **No forks of `core/`.** Customer differences = config + adapters + packs.
- [ ] **Zero domain imports in `core/`.** Add a CI check that greps for domain terms and fails the build if found.
- [ ] **Core depends only on `core/ports/` interfaces** — never on a concrete adapter or a model SDK.
- [ ] **Kernel owns its storage** (its own schema + Alembic migrations). Never read/write host tables.
- [ ] **Correctness established without an oracle.** With no prior implementation to diff against, every layer ships with: a spec-derived acceptance suite, property-based tests for invariants (ledger is append-only and Merkle inclusion/consistency proofs always hold; policy evaluation is deterministic and conflict-resolution is total — no undefined outcomes), and golden test cases derived directly from policies and regulatory requirements. No layer is "done" without its correctness suite.
- [ ] **Secrets via OpenBao only.** No Vault dependency.
- [ ] **Semantic versioning** — the kernel is a versioned dependency now; breaking changes are major bumps.
- [ ] **Signed releases + SBOM** — it runs in customers' (including banks') environments; supply-chain integrity is part of the product.
- [ ] **Encryption at rest** for ledger, consent, and secrets.
- [ ] **Docs ship with every layer.** A layer without a quickstart and API reference is not done.

---

## 9. Resolved Decisions

| # | Decision | Resolution | Build implication |
|---|----------|-----------|-------------------|
| 1 | Workflow engine for K·06 | **Temporal + Postgres state-machine, both, used as needed** | Both adapters ship behind `WorkflowPort`; config selects per deployment tier. Postgres adapter first (sovereign tier, built first), Temporal alongside for dedicated/cloud. No global default. |
| 2 | Merkle ledger build vs buy | **Build in-house** | Highest-risk correctness component. Implement a **minimal RFC 6962-style transparency log — no custom proof structures.** Requires property-based invariant tests, published test vectors, standard primitives only, and a third-party cryptographic review before any bank deployment. See §3.4. |
| 3 | Open-core boundary | **No open core — fully proprietary** | Single private repo; proprietary license headers throughout; no open/commercial module split. **Trade-off to manage:** you lose open source as an adoption and trust lever for the developer audience — replace it with a sandbox/free tier, strong docs, and published security attestations (see note below). |
| 4 | PII masking approach (K·05) | **Dedicated internal task** | The Gateway's governance design (masking shape, prompt logging, routing, cost) is now specified in **§3.12**; the deep PII-masking *implementation* remains the owned workstream with a dedicated design review. Security-critical — reviewed before the Gateway ships for any cloud-inference tier. |

**Note on Decision 3 (no open core):** With the code closed, technical buyers and developers can't build trust by reading it. For a *governance* product that trust matters more than usual. Compensate deliberately: a hosted sandbox or free tier so developers can try the SDK without procurement, first-class docs, and third-party security/crypto attestations (the ledger review from Decision 2 doubles as one). This is a go-to-market consideration, not a code one — flag it to whoever owns developer adoption.

---

## 10. Worked Example (see the whole thing before you build)

This is what integration looks like in each of the three delivery modes. The governance is identical across all three — only the surface differs.

### One action, traced end-to-end (concrete values)

One real action — an IFRS-9 loan-stage reclassification at a bank tenant — walked through every step of the lifecycle. This is what happens under the hood regardless of delivery mode. Inputs:

- **Action:** type `ciro.ifrs9.stage_transition`, payload `{ loan_id: "4471", from_stage: 1, to_stage: 2, exposure: 7_500_000 }`
- **Actor:** `alice` (`role:risk_analyst`) · **Tenant:** `ciro-bank` · **Idempotency key:** `ifrs9-4471-2026-06-05-001`
- **Governing policy** `ciro.ifrs9.stage_transition` v3: condition `to_stage > from_stage && exposure > 5_000_000` → `require_approval`, approvers `["role:risk_head"]`.

| # | Step | What happens (concrete) | ActionState after |
|---|------|--------------------------|-------------------|
| 1 | **propose** | Idempotency check on `(ciro-bank, ifrs9-4471-2026-06-05-001)` via INSERT…ON CONFLICT → no existing row, inserted. | `PROPOSED` |
| 2 | **evaluate** (K·01, K·04) | Resolve policies for `(type, tenant)` → v3 applies. CEL: `2 > 1 && 7_500_000 > 5_000_000` → `true` → **Decision = require_approval**. Consent (K·04) present. Deterministic: same inputs → same decision. | `PENDING_APPROVAL` |
| 3 | **gate** (K·03, durable via K·06) | HITL request to `role:risk_head`; action suspended durably. `bob` approves at T+4m → `poll` returns `APPROVED`. *(If rejected, or the 24h timeout fires → `DENIED`; the body never runs.)* | `EXECUTING` |
| 4 | **execute** (K·06) | The decorated body runs — the **only** real state change: `update_stage("4471", 2)`. Its result is recorded for replay. | `SEALING` |
| 5 | **seal** (K·02) | Build canonical entry `{ action, actor: alice, policy_version: 3, decision: require_approval, approver: bob, consent_state, recorded_result, model_output: none }`. `leaf = SHA256(0x00 ‖ entry)`. Append under `SELECT … FOR UPDATE` → `ledger_seq = 81923`. New STH signed (Ed25519 via OpenBao); inclusion proof generated. *(If seal fails → `HALTED` + alert, never `COMPLETED`.)* | `SEALED → COMPLETED` |
| 6 | **emit** (K·07) | After seal, publish `action.completed { action_id, tenant: ciro-bank, type, ledger_seq: 81923 }`. Best-effort — a failed emit does not change the sealed outcome. | `COMPLETED` |

**Later, on replay (F-09):** audit replay re-derives this decision from entry `81923` using **policy v3 as recorded** (not the current active policy) and the **recorded** execute result — it does not re-call any model and does not re-run `update_stage`. A replay that re-disburses or re-notifies is a critical bug, tested against explicitly.

### Python SDK — the `@governed` decorator

```python
from quaicu_kernel import Kernel

# Selects adapters (inference, hitl, identity, storage, workflow) and loads
# content packs — all from config. No core code is customer-specific.
kernel = Kernel.from_config("kernel.toml")

@kernel.governed(policy="ciro.ifrs9.stage_transition")
async def reclassify_loan(loan_id: str, from_stage: int, to_stage: int, *, actor):
    # This body is the EXECUTE step. It runs ONLY after evaluate + gate pass.
    # If policy denies, or HITL rejects, or any step errors → this never runs.
    await ledger_db.update_stage(loan_id, to_stage)

# Under the hood the decorator runs the full lifecycle:
#   propose → evaluate(K·01,K·04,K·08–K·11) → gate(K·03) →
#   execute(this fn) → seal(K·02) → emit(K·07)
# A require-approval policy suspends between gate and execute until a human decides.
```

### REST API — for non-Python / existing systems

```
POST /kernel/v1/actions/propose
  { "type": "ciro.ifrs9.stage_transition",
    "payload": { "loan_id": "4471", "from": 1, "to": 2 },
    "idempotency_key": "..." }
→ 202 { "action_id": "...", "state": "PENDING_APPROVAL" }

POST /kernel/v1/actions/{id}/approve     # the human gate (K·03)
→ 200 { "state": "EXECUTED", "ledger_seq": 81923, "proof": "..." }

GET  /kernel/v1/ledger/{entity}/trail    # K·02 — verifiable history
GET  /kernel/v1/ledger/verify            # returns a signed integrity proof
```

### Docker — fastest path, zero language dependency

```bash
docker run quaicu/kernel \
  -e CONFIG=/etc/kernel/kernel.toml \
  -v ./packs:/packs \
  -p 7000:7000
# Exposes the same REST API above. Adapters and packs come from config + mount.
```

### What a `kernel.toml` looks like (this is the "config not code" promise made real)

```toml
[deployment]      tier = "sovereign"          # sovereign | private_cloud | cloud
[adapters]
  inference       = "vllm"                    # swap to "bedrock" or "openai" — no code change
  hitl            = "webhook"
  identity        = "oidc"
  storage         = "postgres"
  workflow        = "postgres_statemachine"   # or "temporal" for dedicated/cloud
[packs]
  policies        = ["ciro.ifrs9", "dpdp.core"]
  regmaps         = ["rbi.free_ai", "dpdp.2023"]
```

Onboarding the next customer — agency, product company, or bank — is editing this file and loading different packs. That is the entire point of the build.

---

*Build spec v1.0 · June 2026. Pair with the Product Documentation. All §9 decisions resolved. The single most important rule on this page: one core, no forks.*
