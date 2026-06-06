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

## Current status (2026-06-06)

**Wave 2 complete.** K·03 HITL, K·05 AI Gateway, and K·07 Event Bus are built and green. Full
suite: **126 tests passing** (21 lifecycle · 22 K·01 · 31 K·02 · 19 K·03 · 18 K·05 · 15 K·07).
**The first runnable governance loop is now in place: K·01 → K·03 → K·05 → K·02 → K·07.**

Wave 3 unblocked:
- **K·06 Process Engine** (`core/process/`) — depends on K·03 ✓
- **K·04 DPDP Consent** (`core/consent/`) — depends on K·02 ✓
- **K·08 Model Registry** (`core/registry/`) — depends on K·07 ✓

K·06 and K·04 can run in parallel; K·08 depends on K·07 (now done) so it is also dispatchable.

### Open follow-ups (ADR candidates — orchestrator to schedule)
- **Capture the approving identity.** The lifecycle records *that* a HITL gate was approved but not
  *who* approved it, because `ApprovalDecision` is a status enum. Recording the approver requires
  extending the frozen HITL result type (e.g. an `ApprovalOutcome` carrying the approver `ApproverRef`).
  This is a frozen-surface change → needs an ADR before K·03 ships. Tracked here so it is not lost.
- **K·02 external cryptographic review.** The in-memory Ed25519 signer uses an ephemeral key; the
  real OpenBao signer is a Wave 2 adapter. Before any bank deployment the ledger implementation
  requires a third-party crypto review (spec §3.4 — budgeted explicitly).

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
| 2 | Inference adapters | `adapters/inference/` | adapter-inference | pending | InferencePort (frozen) | conformance |
| 2 | HITL adapters | `adapters/hitl/` | adapter-hitl | pending | HITLPort (frozen) | conformance |
| 2 | Storage adapter | `adapters/storage/` | adapter-storage | pending | StoragePort (frozen) | conformance |
| 2 | Identity adapters | `adapters/identity/` | adapter-identity | pending | IdentityPort (frozen) | conformance |
| 3 | K·06 Process Engine | `core/process/` | process-agent | pending | K·03 | §6 (K·06) |
| 3 | Workflow adapters (pg first, temporal) | `adapters/workflow/` | adapter-workflow | pending | WorkflowPort, K·06 | conformance |
| 3 | K·04 DPDP Consent | `core/consent/` | consent-agent | pending | K·02 | §6 (K·04) |
| 4 | K·08 Model Registry | `core/registry/` | registry-agent | pending | K·05 | §6 (K·08) |
| 4 | K·09 Fairness | `core/fairness/` | fairness-agent | pending | K·08, K·02 | §6 (K·09) |
| 4 | K·10 Drift | `core/drift/` | drift-agent | pending | K·08, K·02 | §6 (K·10) |
| 4 | K·11 Explainability | `core/explain/` | explain-agent | pending | K·08, K·02 | §6 (K·11) |
| 5 | K·13 Sandbox | `core/sandbox/` | sandbox-agent | pending | K·01, K·02 | §6 (K·13) |
| 5 | K·12 Incident | `core/incident/` | incident-agent | pending | K·06, K·02 | §6 (K·12) |
| 5 | K·14 Regulatory Mapping | `core/regmap/` | regmap-agent | pending | K·01, K·02 | §6 (K·14) |
| ↳ | Delivery (SDK · API · Docker) | `delivery/` | delivery-agent | pending | per delivered layer | §6, §8 |

> **Forward dependency:** K·01's activation gate (F-10) needs K·13's counterfactual backtest. Until
> K·13 (Wave 5) lands, gate policy activations manually and mark them backtest-pending (build spec §6).

---

## Log (append-only — newest first)

Each entry: date · unit · agent · what changed · what it now exposes · follow-ups.

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
