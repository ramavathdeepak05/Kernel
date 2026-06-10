# BUILD JOURNAL — QUAICU Kernel

The single live view of *what is built, what is in flight, and what is blocked*. The orchestrator
maintains it; every agent reads it before starting (to check its Definition of Ready) and appends a log
entry on finishing (AGENTS.md §5). This is the team's shared working memory — if it isn't here, the
next cold agent doesn't know it happened.

- **Status values:** `pending` · `ready` (DoR met, dispatchable) · `in_progress` · `in_review` · `done`.
- **Definition of Ready / Done:** AGENTS.md §5; per-layer DoD: build spec §6.
- **Dependency rule:** never start a unit whose *Blocked by* is not `done`. The *why* of each dependency
  is in build spec §6.

---

## Current status (2026-06-10)

**All 14 governance layers + the delivery phase are built and green. Suite: 506 tests passing,
9 skipped.** Four feature waves have landed on top of the core kernel since the Wave-2 milestone
below: (1) full layer completion + delivery, (2) a security-hardening + composable-governance pass,
(3) a decision-only authorize/monitor surface + reference PEP, and (4) a zero-friction integration
layer. See the Log for the per-wave detail.

The kernel now exposes three integration modes — REST API (`/v1/actions`, `/v1/authorize`,
`/v1/inference`, `/v1/ledger`), the Python SDK (`@kernel.guard` / `kernel.wrap` / `kernel.proxy` /
`kernel.check` / `kernel.generate` / `for_agent`), and a reference enforcement-point middleware —
all running over one composable `GovernanceProfile` model with per-agent identity.

### Next planned work — Policy Management API + Dashboards
Before that work can start, a gap audit (2026-06-10) found the following must be closed first. **The
real CEL `PolicyEngine` (`core/policy/`) is built and tested but is NOT reachable through
`Kernel.from_config` — only the dev `always_allow` adapter is registered, and there are no policy
CRUD routes, no policy persistence adapter, and no dashboard read-models.** Detailed gap list is in
the Log entry dated 2026-06-10 ("Pre-management-API gap audit").

### Open follow-ups (ADR candidates / pre-sale blockers)
- **Capture the approving identity (still open).** The lifecycle records *that* a HITL gate was
  approved but not *who* — `ApprovalDecision` is a status enum. K·03's `ApprovalRecord.decided_by`
  captures it at the HITL layer, but the approver is not yet threaded into the sealed `LedgerEntry`
  (the lifecycle passes `approver=None`). Threading it through needs a frozen-surface change → ADR.
- **K·02 external cryptographic review (still open, pre-sale critical path).** OpenBao signer adapter
  now provides durable Ed25519 signing, but the tree/entries are still in-memory and the RFC 6962
  implementation has not had a third-party crypto review (spec §3.4). On the critical path for banks.
- **Durable ledger persistence.** `OpenBaoLedgerAdapter` wraps an in-memory TrustLedger: durable
  signing key, ephemeral tree/entries (lost on restart). Needs a persistent tree backend.
- **Policy content packs.** K·14 regmap catalog + K·01 CEL engine exist, but no actual RBI / EU AI
  Act / DPDP rule sets are written. The kernel enforces rules; the rules themselves are unwritten.

---

## Work queue (dependency-ordered)

| Wave | Unit | Dir | Owner | Status | Blocked by | DoD |
|------|------|-----|-------|--------|-----------|-----|
| 0 | Frozen contract surface | `core/ports`, `core/types.py`, `core/errors.py` | orchestrator | **done** | — | ADR-0001 |
| 0 | Lifecycle spine | `core/lifecycle/` | orchestrator | **done** | contract surface | §6 |
| 1 | K·01 Policy Engine | `core/policy/` | policy-agent | **done** | lifecycle spine | §6 (K·01) |
| 1 | K·02 TrustLedger | `core/ledger/` | ledger-agent | **done** | lifecycle spine | §6 (K·02) |
| 2 | K·03 HITL | `core/hitl/` | hitl-agent | **done** | K·01 | §6 (K·03) |
| 2 | K·05 AI Gateway | `core/gateway/` | gateway-agent | **done** | K·01, K·02 | §6 (K·05) |
| 2 | K·07 Event Bus | `core/events/` | events-agent | **done** | K·02 | §6 (K·07) |
| 2 | Inference adapters | `adapters/inference/` | adapter-inference | **done** | InferencePort (frozen) | conformance |
| 2 | HITL adapters | `adapters/hitl/` | adapter-hitl | **done** | HITLPort (frozen) | conformance |
| 2 | Storage adapter | `adapters/storage/` | adapter-storage | **done** | StoragePort (frozen) | conformance |
| 2 | Identity adapters | `adapters/identity/` | adapter-identity | **done** | IdentityPort (frozen) | conformance |
| 3 | K·06 Process Engine | `core/process/` | process-agent | **done** | K·03 | §6 (K·06) |
| 3 | Workflow adapters | `adapters/workflow/` | adapter-workflow | **done** (in-memory; Temporal pending) | WorkflowPort, K·06 | conformance |
| 3 | K·04 DPDP Consent | `core/consent/` | consent-agent | **done** | K·02 | §6 (K·04) |
| 4 | K·08 Model Registry | `core/registry/` | registry-agent | **done** | K·05 | §6 (K·08) |
| 4 | K·09 Fairness | `core/fairness/` | fairness-agent | **done** | K·08, K·02 | §6 (K·09) |
| 4 | K·10 Drift | `core/drift/` | drift-agent | **done** | K·08, K·02 | §6 (K·10) |
| 4 | K·11 Explainability | `core/explain/` | explain-agent | **done** | K·08, K·02 | §6 (K·11) |
| 5 | K·13 Sandbox | `core/sandbox/` | sandbox-agent | **done** | K·01, K·02 | §6 (K·13) |
| 5 | K·12 Incident | `core/incident/` | incident-agent | **done** | K·06, K·02 | §6 (K·12) |
| 5 | K·14 Regulatory Mapping | `core/regmap/` | regmap-agent | **done** | K·01, K·02 | §6 (K·14) |
| ↳ | Delivery (SDK · API · Docker) | `delivery/` | delivery-agent | **done** | per delivered layer | §6, §8 |

> **Forward dependency (now resolved in code):** K·01's activation gate (F-10) needs K·13's
> counterfactual backtest. K·13 (`run_counterfactual_backtest`) is built, but its `SandboxRun`
> output is not yet wired to produce the `ImpactReport` that `PolicyStore.activate` consumes — the
> bridge (SandboxRun + K·09 fairness_delta → ImpactReport) is a pre-management-API item (see 06-10 log).

---

## Log (append-only — newest first)

Each entry: date · unit · agent · what changed · what it now exposes · follow-ups.

- **2026-06-10 · Pre-management-API gap audit · orchestrator** — Audit before planning the Policy
  Management API + dashboards. **Gaps found (must close first):**
  1. **CEL engine not wired to config.** `Kernel._ADAPTER_REGISTRY` registers only `always_allow`
     for the `PolicyEvaluator` slot. The real `core/policy/PolicyEngine`+`PolicyStore` can only be
     injected via `from_parts` in code — `from_config` cannot select it. A management API is
     meaningless until config can wire the CEL engine. **Fix:** register `cel_policy` →
     `(PolicyEngine over PolicyStore)`; expose the store to the API layer.
  2. **No policy persistence.** `PolicyStore` is in-memory + `threading.Lock`; restart loses all
     policies. `adapters/policy/` has only `always_allow`. **Fix:** a Postgres-backed policy store
     (mirror the K·02/storage adapter pattern) or the API will write to volatile memory.
  3. **No policy CRUD surface.** `delivery/api/routes/` has actions/authorize/inference/ledger but
     no `/v1/policies`. Need register / list / get / activate / deprecate, all authz-gated.
  4. **F-10 activation gate has no ImpactReport producer.** `PolicyStore.activate` requires an
     acknowledged `ImpactReport` (decision_distribution, flip_count, **fairness_delta**), but K·13
     `run_counterfactual_backtest` returns a `SandboxRun` (flip_rate, counts) — nobody converts
     SandboxRun (+ K·09 fairness) into an ImpactReport. Without this bridge, activation is either
     blocked or bypassed. **Fix:** a backtest→ImpactReport assembler + a `/v1/policies/{id}/simulate`
     route over the ledger entries.
  5. **No dashboard read-models.** Dashboards need aggregates (decision counts, denial rate over
     time, top-denied action types, HITL queue depth, policy hit counts, drift/fairness status). The
     ledger exposes only `get_entries(tenant)` (full scan); events are in-memory only — no query/
     aggregation API and no durable event sink. **Fix:** a read-model/projection layer + query routes.
  6. **No authz for the control plane itself.** Who may author/activate/deprecate a policy? Needs an
     RBAC check on the management routes (a policy governs the policy API — dogfood the kernel).
  **Exposes** the dependency-ordered plan: wire CEL engine → policy persistence → CRUD routes →
  backtest/ImpactReport bridge → read-models → dashboards. No code changed in this entry.

- **2026-06-10 · Zero-friction integration · delivery** (commit `590e2073`) — Added integration
  primitives so an existing codebase adopts governance by *adding lines only* — no function-signature
  or call-site changes. `core/lifecycle/context.py` (actor `ContextVar`, task-local; `actor_scope`
  /`async_actor_scope`); `kernel.actor_context(actor)` (bind identity once per request/session);
  `@kernel.guard(policy=...)` (decorate any existing fn, signature unchanged, actor from ContextVar);
  `kernel.wrap(fn, policy=...)` (programmatic form for third-party callables); `kernel.proxy(obj,
  policies={...})` (`delivery/sdk/proxy.py` — transparent object proxy governing only listed dotted
  method paths, all other attribute access passes through). 20 new tests; suite 486 → **506**.

- **2026-06-10 · Decision-only authorize + monitor + reference PEP · lifecycle/delivery** (commit
  `66f49319`) — Split decision from execution (PDP/PEP). `core/lifecycle/decision.py`
  (`AuthorizationResult`); `LifecycleEngine.decide()` (side-effect-free verdict — no insert, no state
  transition, no emit; best-effort monitoring seal); `_consent_verdict()` (non-mutating consent check
  shared by `run`+`decide`); `GovernanceProfile.monitor()` preset; `kernel.check()` /
  `BoundAgent.check()` (never raise on DENY — caller is the PEP); `POST /v1/authorize` (pure PDP,
  always 200, verdict in body); `delivery/api/middleware.py` (`GovernanceMiddleware`, opt-in via
  `create_app(enforce_paths=...)`). Under the default `all()` profile every decision is sealed to the
  ledger (tamper-evident monitoring). 40 new tests; suite 446 → 486.

- **2026-06-10 · Security hardening + composable governance · multiple** (commit `5dc7ca75`) —
  Two efforts. **(a) 8 security/fail-closed fixes** from a full-codebase review: REST API requires a
  bearer token (actor from token, never body); ledger trail route + cross-tenant 403 + `get_entries`;
  real pattern-based PII masking (PAN/Aadhaar/email/phone/SSN/CC) replacing a no-op stub; consent
  fail-open fixed (non-active → DENY); HITL role-based approver authz + self-approval guard; storage
  failures HALT instead of escaping `run()`; identity resolved before idempotency insert (no poisoned
  slot); Merkle leaf now commits payload + non-dict result. **(b) Composable governance + agent
  integration:** `GovernanceProfile` (`core/lifecycle/profile.py` — per-call layer toggles + presets
  all/standard/gateway_only/audit_only; engine `run(profile=)` honors each layer + a standalone
  consent step; enforced layers sealed into the leaf); AI Gateway wired into the Kernel
  (`kernel.generate()`, `POST /v1/inference`, `[gateway]`/`[governance]` config); `kernel.governed_tool()`
  + `kernel.for_agent()` → `BoundAgent` (per-agent identity in the ledger). Suite 402 → 446.

- **2026-06-08/09 · Production adapters + CI/CD · delivery** (commits `cb2b956f`, `7075e9cb`,
  `fb6fbc34`) — `adapters/storage/postgres.py` + Alembic migrations (StoragePort); OpenBao signer
  adapter for durable Ed25519 STH signing (K·02); GitHub Actions CI + signed Docker release pipeline
  (cosign keyless). Suite reached 402. **Follow-up:** ledger tree/entries still in-memory behind the
  OpenBao signer; external crypto review still outstanding.

- **2026-06-07 · All 14 layers + delivery complete (Waves 3–5) · multiple** (commit `648be5a2`) —
  Completed K·04 Consent, K·06 Process, K·08 Registry, K·09 Fairness, K·10 Drift, K·11 Explainability,
  K·12 Incident, K·13 Sandbox (`run_counterfactual_backtest`), K·14 Regulatory Mapping
  (`RegulationCatalog` + `generate_evidence_pack`), plus the adapters (inference/hitl/storage/identity/
  workflow) and the delivery phase (SDK `Kernel`, FastAPI app + routes, Dockerfile/Helm). This is the
  point the work-queue table above transitioned almost entirely to **done**.

- **2026-06-06 · Lifecycle spine · orchestrator** — Built `core/lifecycle/`: `transitions.py`
  (`VALID_TRANSITIONS` + `assert_transition`), `protocols.py` (`PolicyEvaluator`, `Ledger`, `EventBus`,
  `ActionRepository` collaborator contracts that K·01/K·02/K·07/storage implement), and `engine.py`
  (`LifecycleEngine.run` driving propose→evaluate→gate→execute→seal→emit, fail-closed at every arrow,
  no-bypass by construction). Added `pyproject.toml` (pytest asyncio + ruff/mypy config) and a 21-test
  suite (`tests/unit/lifecycle/`) proving allow/deny/approve/reject/timeout, policy-error→deny,
  execute-error→halt, seal-error→halt-not-complete, emit-error→still-complete, idempotency, and the
  transition guard. All green; `core/` passes the domain/import/eval gates. **Exposes** the collaborator
  protocols K·01 and K·02 must implement next. **Follow-up:** approver-identity capture (see above).

- **2026-06-06 · K·07 Event Bus · events-agent** — Built `core/events/`: `model.py` (frozen
  `DomainEvent` base + `ActionCompletedEvent`/`ActionDeniedEvent`/`ActionHaltedEvent` + `make_completed_event`
  helper), `bus.py` (`InMemoryEventBus` — `subscribe` by event type, async `emit` with fan-out,
  subscriber-failure swallowed + logged (best-effort), idempotency guard by `action_id`, `emitted`
  property and `clear()` for test inspection, `threading.Lock` for thread safety). 15 tests green:
  12 unit + 3 conformance (post-seal evidence, emit-failure isolation, tenant+action_id carriage).
  **Exposes** `InMemoryEventBus` implementing the `EventBus` protocol. K·08 is now unblocked.

- **2026-06-06 · K·05 AI Gateway · gateway-agent** — Built `core/gateway/`: `allowlist.py`
  (`InMemoryModelAllowlist` — per-tenant permitted model ids; K·08 will replace), `masking.py`
  (`MaskingConfig`, `MaskingContext` with token→value map, `mask_payload` for declared sensitive
  fields), `budget.py` (`InMemoryBudgetTracker` — thread-safe per-tenant token + cost budget,
  `check_and_consume` raises `GatewayBudgetExceededError` fail-closed), `log.py`
  (`InMemoryPromptLog` — write-before-call enforced, `inject_failure()` test hook, `record_response`
  post-call), `engine.py` (`AIGateway` — 7-step governance: allowlist → mask → log → budget →
  generate → record hash → return with `recorded_output`). Conformance test verifies no model SDK
  in `core/`. 18 tests green: 15 unit + 3 conformance. **Exposes** `AIGateway` for integration;
  `recorded_output` carries log_id, prompt_hash, response_hash for ledger replay (F-09).

- **2026-06-06 · K·03 HITL · hitl-agent** — Built `core/hitl/`: `model.py` (frozen
  `ApprovalRecord` with `handle_id`, `required_approvers`, `decided_by`/`decided_at` — resolves
  the open ADR on approver identity capture), `store.py` (`ApprovalStore` — thread-safe
  `threading.Lock`), `engine.py` (`InProcessHITLPort` — implements `HITLPort` protocol
  structurally; `request_approval` creates timed records; `poll` checks expiry fail-closed;
  `approve`/`reject` with authority enforcement: `user:` refs validated exactly, `role:` refs
  deferred to adapter in production; `force_expire` for test/admin; `get_record` for audit). 19
  tests green: 16 unit + 3 conformance (durable suspension, timeout→TIMED_OUT fail-closed,
  approver identity recorded). **Resolves** the open ADR: `ApprovalRecord.decided_by` captures who
  approved. K·06 is now unblocked.

- **2026-06-06 · K·02 TrustLedger · ledger-agent** — Built `core/ledger/`: `merkle.py` (RFC 6962
  Merkle tree — `leaf_hash`/`internal_hash` with 0x00/0x01 domain separation, `compute_root`,
  `inclusion_proof`, `consistency_proof`, `verify_inclusion`, `verify_consistency`), `signer.py`
  (`SignedTreeHead`, `TreeSigner` Protocol, `InMemoryEd25519Signer` — ephemeral Ed25519 key; real
  OpenBao signer is a Wave 2 adapter), `engine.py` (`TrustLedger.seal` — per-tenant `MerkleTree`
  keyed by `TenantId`, `asyncio.Lock` for concurrent-safe append, canonical JSON serialization for
  leaf hashing, `LedgerSealError` on any failure). 31 tests green: 14 Merkle unit tests (domain
  separation, empty/single/two-leaf roots, all-positions inclusion, consistency, tamper detection),
  12 engine tests (seal, sequential seq, tenant isolation, cross-tenant tree independence, inclusion
  proof, consistency proof, failure → `LedgerSealError`, STH signing, recorded_result, approver,
  leaf_hash roundtrip, concurrent seals), 7 RFC 6962 conformance vectors. **Exposes** `TrustLedger`
  implementing the `Ledger` protocol — K·05 and K·07 plug in next. **Follow-up:** external crypto
  review required before bank deployment (spec §3.4); OpenBao signer adapter in Wave 2.

- **2026-06-06 · K·01 Policy Engine · policy-agent** — Built `core/policy/`: `model.py`
  (`PolicyLifecycle` DRAFT/REVIEW/ACTIVATED/DEPRECATED, frozen `PolicyEnvelope` with CEL `condition`
  field, `ImpactReport` with F-10 `acknowledged` gate), `store.py` (`PolicyStore` — CEL compile at
  `register` time via `celpy`, F-10 gate enforced in `activate`, thread-safe via `threading.Lock`,
  `lookup` filters by ACTIVATED + governs + tenant scope), `evaluator.py` (`PolicyEngine.evaluate`
  — total conflict resolution: deny > require_approval > allow; empty/no-match → `PolicyNotFoundError`
  (lifecycle maps to DENY); CEL runtime error → `PolicyEvaluationError` (lifecycle maps to DENY);
  CEL activation map flattens action into dot-free names: `payload_<key>`, `actor_id`, etc.). 22
  tests green: 19 unit + 3 conformance (spec §10 IFRS9 golden cases). **Exposes** `PolicyEngine`
  implementing the `PolicyEvaluator` protocol — K·03, K·05 depend on this. **Forward-dependency:**
  K·01 activation gate (F-10) cannot be fully automated until K·13 Sandbox lands; gate policy
  activations manually, mark backtest-pending.

- **2026-06-06 · Frozen contract surface · orchestrator** — Committed `core/ports/` (5 Protocols),
  `core/types.py` (ids, `ActionState`/`Decision`/`ApprovalDecision`, `Action`/`Actor`/`RequestContext`/
  `EvaluationResult`/`LedgerEntry` + port types), `core/errors.py` (`QUAICUError` tree incl. Gateway &
  Consent branches). Verified by `py_compile` + import smoke test. Decisions recorded in ADR-0001
  (immutable models via `with_state`; one error tree; minimal `Transaction`/`ProcessDef`). **Unblocks
  all of Wave 1+.** Next: dispatch the lifecycle spine, then K·01 and K·02 in parallel.
