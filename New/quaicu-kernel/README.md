<p align="center">
  <strong>QUAICU GOVERNANCE KERNEL</strong>
</p>

<p align="center">
  <em>Deterministic AI governance — one core, no forks, fail-closed everywhere.</em>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#the-14-layers">The 14 Layers</a> ·
  <a href="#delivery-modes">Delivery Modes</a> ·
  <a href="#development">Development</a> ·
  <a href="#testing">Testing</a> ·
  <a href="#license">License</a>
</p>

---

## What is this?

The QUAICU Governance Kernel is a **standalone, embeddable governance engine** for AI-powered systems. It ensures that every action taken by an AI system — from model inference to institutional state changes — passes through a deterministic, auditable, tamper-evident governance pipeline before it executes.

**The problem it solves:** regulated enterprises (banks, insurers, government bodies), AI product companies, and AI agencies all need to prove that their AI systems operate within policy, comply with regulation, and leave a verifiable audit trail. Building this from scratch for each product is expensive, error-prone, and nearly impossible to certify. QUAICU provides it as a pluggable kernel.

**The guarantee:** every governed action follows a strict lifecycle:

```
propose → evaluate → gate → execute → seal → emit
```

Any failure, timeout, or ambiguity at any step **denies or halts** — the kernel never fails open.

---

## Key Principles

| Principle | What it means |
|-----------|---------------|
| **One core, no forks** | One codebase serves all customers. Differences are absorbed as configuration, adapters, and content packs — never as code branches. |
| **Fail-closed everywhere** | Any failure or uncertainty → deny/halt. A governance kernel that fails open manufactures false assurance. |
| **No bypass** | No code path executes or seals an action that skipped evaluation and gating. Even admin actions are governed. |
| **Deterministic evaluation** | Identical inputs produce identical policy decisions. No hidden state, no wall-clock branching in evaluation. |
| **Tenant isolation** | No data, decision, policy, or ledger entry crosses a tenant boundary. Enforced at every layer. |
| **Ports and adapters** | Core depends on interfaces (`core/ports/`), never on concrete implementations. The host supplies implementations via config. |
| **Zero domain imports** | `core/` contains no domain concepts (student, loan, patient). It governs *actions* generically. |
| **Replay-safe** | Every governed action is re-derivable from the ledger. Replay reconstructs — it never re-performs side effects. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  DELIVERY ADAPTERS (thin wrappers over core)             │
│    Python SDK  ·  FastAPI / REST  ·  Docker image        │
├──────────────────────────────────────────────────────────┤
│  CORE KERNEL — one codebase, no forks, no domain imports │
│    Lifecycle spine + 14 layers + PORT INTERFACES          │
├──────────────────────────────────────────────────────────┤
│  PLUGGABLE ADAPTERS (selected by config)                 │
│    Inference · HITL · Identity · Storage · Workflow       │
├──────────────────────────────────────────────────────────┤
│  CONTENT PACKS (data, not code)                          │
│    Policy packs · Regulatory maps (RBI, EU AI Act, DPDP)  │
└──────────────────────────────────────────────────────────┘
```

Onboarding a customer = pick adapters in config + load the relevant policy/regulatory packs. No core code is touched.

---

## The 14 Layers

The kernel is composed of 14 governance capabilities, each built as an independent layer that plugs into the lifecycle spine:

| Layer | Name | Purpose |
|-------|------|---------|
| **K·01** | Policy Engine | Evaluates actions against all applicable policies. CEL conditions, total conflict resolution, deterministic. |
| **K·02** | TrustLedger | RFC 6962-style Merkle transparency log. Append-only, per-tenant, with inclusion & consistency proofs. |
| **K·03** | HITL Gate | Human-in-the-loop approval checkpoint. Timeout → reject (fail-closed). |
| **K·04** | DPDP Consent | Data protection consent checks at evaluation time. State recorded for point-in-time replay. |
| **K·05** | AI Gateway | PII masking, model routing, prompt logging, cost governance. Every model call is governed and sealed. |
| **K·06** | Process Engine | Durable state machine with HITL pauses and incident rollback. Postgres or Temporal adapter. |
| **K·07** | Event Bus | Structured event emission after seal. A failed emit never alters a sealed outcome. |
| **K·08** | Model Registry | Per-tenant model allowlists. The gateway enforces against it. |
| **K·09** | Fairness | Bias detection and fairness sweeps over recorded decisions. |
| **K·10** | Drift Monitor | Detects model and decision drift over time. |
| **K·11** | Explainability | Generates decision explanations from recorded inputs and policy versions. |
| **K·12** | Incident Engine | Governed rollback — itself a governed action through the full lifecycle. |
| **K·13** | Sandbox | Counterfactual replay: run historical actions against candidate policies in a shadow partition. |
| **K·14** | Regulatory Mapping | Maps policies to regulatory requirements. Generates signed, point-in-time evidence packs. |

---

## Delivery Modes

The kernel ships three ways for three kinds of customer:

| Mode | Use case | How it works |
|------|----------|--------------|
| **Python SDK** | AI agencies & product companies embedding governance into their own apps | `from quaicu_kernel import Kernel` — the `@governed` decorator wraps any function in the governance lifecycle. |
| **FastAPI (REST)** | Product companies & enterprises integrating via HTTP | `POST /kernel/v1/actions/propose` — standard REST API with OpenAPI spec. |
| **Docker image** | Regulated enterprises running in their own infrastructure | Self-contained image with all dependencies. Helm charts for k3s / K8s. |

---

## Tech Stack

| Concern | Choice |
|---------|--------|
| Core language | Python 3.11+ |
| Policy conditions | CEL (Common Expression Language) — deterministic, sandboxed, guaranteed-terminating |
| API framework | FastAPI |
| Primary datastore | PostgreSQL 16+ |
| Schema migrations | Alembic |
| Secrets management | OpenBao (MPL 2.0 — Vault-compatible, BSL-free) |
| Durable workflow | Temporal (dedicated tier) / Postgres state machine (sovereign tier) |
| Audit ledger | RFC 6962 Merkle transparency log on PostgreSQL |
| Object storage | MinIO (S3-compatible) |
| Inference (pluggable) | Ollama · vLLM · TGI · OpenAI · Anthropic · Gemini · Bedrock · Azure OpenAI · Vertex |
| Orchestration | k3s / docker-compose (sovereign) · K8s (cloud) |
| IaC | OpenTofu (MPL 2.0 — Terraform-compatible, BSL-free) |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki |

---

## Repository Structure

```
quaicu-kernel/
├── core/                      # The kernel — no domain imports, no concrete deps
│   ├── __init__.py            # Package root, version
│   ├── types.py               # Frozen shared value types (Action, LedgerEntry, etc.)
│   ├── errors.py              # Kernel error hierarchy
│   ├── ports/                 # Port interfaces (core depends on THESE, not implementations)
│   │   ├── consent.py         # ConsentPort — DPDP consent checks
│   │   ├── hitl.py            # HITLPort — human-in-the-loop approval
│   │   ├── identity.py        # IdentityPort — actor resolution
│   │   ├── inference.py       # InferencePort — model invocation
│   │   ├── storage.py         # StoragePort — kernel-owned DB transactions
│   │   └── workflow.py        # WorkflowPort — durable process execution
│   ├── lifecycle/             # K·00 — the governance spine
│   │   ├── engine.py          # Lifecycle engine (propose → seal → emit)
│   │   ├── protocols.py       # Layer protocols the engine calls
│   │   └── transitions.py     # Valid state transitions
│   ├── policy/                # K·01 — Policy Engine
│   │   ├── evaluator.py       # CEL-based policy evaluation
│   │   ├── model.py           # Policy data model
│   │   └── store.py           # In-memory policy store
│   ├── ledger/                # K·02 — TrustLedger
│   │   ├── engine.py          # Ledger engine (seal, verify, prove)
│   │   ├── merkle.py          # RFC 6962 Merkle tree implementation
│   │   └── signer.py          # Ed25519 Signed Tree Head (STH)
│   ├── hitl/                  # K·03 — Human-in-the-Loop Gate
│   │   ├── engine.py          # Approval routing and fail-closed timeout
│   │   ├── model.py           # HITL data model
│   │   └── store.py           # Approval request store
│   ├── consent/               # K·04 — DPDP Consent Engine
│   │   ├── engine.py          # Consent evaluation engine
│   │   └── purpose.py         # Purpose-based consent model
│   ├── gateway/               # K·05 — AI Gateway
│   │   ├── engine.py          # Gateway engine (mask → route → log → invoke)
│   │   ├── allowlist.py       # Model allowlist enforcement
│   │   ├── budget.py          # Per-tenant token/cost budget enforcement
│   │   ├── log.py             # Prompt/response logging (fail-closed)
│   │   └── masking.py         # PII masking pipeline
│   ├── process/               # K·06 — Process Engine
│   │   ├── definitions.py     # Process/step definitions DSL
│   │   └── errors.py          # Process-specific errors
│   └── events/                # K·07 — Event Bus
│       ├── bus.py             # In-process event bus
│       └── model.py           # Event data model
├── tests/
│   ├── conformance/           # Spec-derived golden/contract test suites
│   │   ├── policy/            # K·01 conformance
│   │   ├── ledger/            # K·02 conformance
│   │   ├── hitl/              # K·03 conformance
│   │   ├── gateway/           # K·05 conformance
│   │   └── events/            # K·07 conformance
│   └── unit/                  # Unit tests
├── docs/
│   ├── BUILD_JOURNAL.md       # Chronological build decisions and progress
│   └── adr/                   # Architecture Decision Records
├── AGENTS.md                  # AI agent coding guidelines for this repo
├── CODEOWNERS                 # Per-layer ownership
├── pyproject.toml             # Project config, deps, tool settings
└── .gitignore
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- `pip` or `uv`

### Install dependencies

```bash
cd New/quaicu-kernel
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

Run specific test categories:

```bash
# Conformance tests (spec-derived golden cases)
pytest -m conformance

# Property-based invariant tests
pytest -m property

# Tenant isolation tests
pytest -m tenant_isolation
```

---

## Development

### Core Invariants (enforced by tests)

Every PR must preserve these — they are testable, not aspirational:

1. **Fail-closed** — any failure or ambiguity → DENY/HALT
2. **No bypass** — no path executes an action that skipped evaluation and gating
3. **Determinism** — identical inputs → identical policy decision
4. **Total conflict resolution** — policy evaluation never returns "undefined"
5. **Tenant isolation** — no data crosses a tenant boundary
6. **Ledger immutability** — a sealed entry is never modified
7. **Idempotency** — re-submitting the same proposal never double-executes
8. **Trustworthy ordering** — ledger ordering depends on consistent clock + monotonic sequence
9. **Replay fidelity** — governed actions are re-derivable from the ledger; replay never causes side effects

### Adding a new layer

1. Create `core/<layer>/` with `__init__.py`, `engine.py`, and any layer-specific models
2. If the layer needs external dependencies, define a port in `core/ports/`
3. Wire into the lifecycle engine via `core/lifecycle/protocols.py`
4. Add conformance tests in `tests/conformance/<layer>/`
5. Update `CODEOWNERS`

### Policy authoring

Policies are authored in YAML with CEL conditions:

```yaml
id: risk.high_value_transfer
version: 1
governs: payment.transfer
scope: { tenant: "*" }
condition: |
  action.payload.amount > 1000000
  && action.payload.currency == "INR"
decision: require_approval
approvers: ["role:risk_head", "role:cfo"]
regulatory_refs: ["rbi.kyc.large_transfers"]
lifecycle: ACTIVATED
```

The authoring pipeline: **YAML → JSON-schema validation → CEL compile-check → dry-run in sandbox → human review → activate.** Activated versions are immutable.

---

## Multi-Tenancy

| Tier | Database | Isolation |
|------|----------|-----------|
| **Sovereign** | Dedicated DB on customer hardware | Physical |
| **Dedicated** | Dedicated DB instance in customer VPC | Instance |
| **Shared** | Shared instance, schema-per-tenant + RLS | Schema + Row-Level Security |

The ledger is **always per-tenant tables** — never a shared table keyed by `tenant_id`. Cross-tenant ledger contamination is architecturally impossible.

---

## Deployment Tiers

| Tier | Orchestration | Workflow Engine | Inference |
|------|---------------|-----------------|-----------|
| **Sovereign / Air-gapped** | docker-compose or k3s | Postgres state machine | Ollama (local) |
| **Dedicated** | K8s in customer VPC | Temporal | vLLM / TGI / cloud APIs |
| **Cloud (QUAICU-hosted)** | K8s | Temporal | Any permitted model via Gateway |

---

## Testing Strategy

| Category | Scope | Tools |
|----------|-------|-------|
| **Conformance** | Spec-derived golden cases per layer | pytest |
| **Property-based** | Core invariants (determinism, ledger integrity, tenant isolation) | Hypothesis |
| **Chaos** | Fault injection (dependency down, timeouts, malformed input) → must fail closed | pytest |
| **Tenant isolation** | Adversarial cross-tenant leakage tests | pytest |
| **Integration** | Full lifecycle with real Postgres | pytest + testcontainers |

Coverage floors: **K·02 → 95%** · **K·01, K·03, K·04, lifecycle, tenant isolation → 90%**

---

## Security Model

- **Fail-closed by default** — unlogged model calls are blocked; unreachable policy services deny
- **RFC 6962 transparency log** — tamper-evident, externally verifiable audit trail
- **Ed25519 Signed Tree Heads** — cryptographic proof of ledger integrity
- **OpenBao secrets management** — MPL 2.0 licensed, Vault-compatible
- **PII masking before transmission** — sensitive fields never reach cloud model providers
- **Zero trust in host environment** — encryption at rest, signed releases, least privilege
- **External crypto review** required before bank deployment

---

## Build Status

| Layer | Status | Notes |
|-------|--------|-------|
| Spine + Ports + Types | ✅ Built | Lifecycle engine, all 6 ports, frozen shared types |
| K·01 Policy Engine | ✅ Built | CEL evaluation, total conflict resolution, conformance suite |
| K·02 TrustLedger | ✅ Built | RFC 6962 Merkle tree, Ed25519 STH, inclusion/consistency proofs |
| K·03 HITL Gate | ✅ Built | Approval routing, fail-closed timeout, conformance suite |
| K·04 DPDP Consent | ✅ Built | Purpose-based consent engine |
| K·05 AI Gateway | ✅ Built | PII masking, model routing, budget enforcement, prompt logging |
| K·06 Process Engine | 🔨 In progress | Process definitions and step DSL |
| K·07 Event Bus | ✅ Built | In-process event bus with conformance suite |
| K·08–K·14 | 📋 Planned | Net-new layers with no prior implementation |

---

## Contributing

See [AGENTS.md](AGENTS.md) for coding guidelines, the layer ownership model, and the Definition of Done checklist every PR must satisfy.

Key rules:
- **Never import domain concepts into `core/`** — a `grep` of `core/` for student, loan, patient, etc. must return nothing
- **Never import concrete implementations into `core/`** — only port interfaces
- **Every layer must pass** the universal Definition of Done checklist before merge
- **Frozen types and ports** require an ADR + leadership sign-off to change

---

## License

Proprietary — © 2026 QUAICU. All rights reserved.
