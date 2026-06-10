<p align="center">
  <img src="https://img.shields.io/badge/QUAICU-Governance%20Kernel-0A0A0A?style=for-the-badge&labelColor=6C3AED&color=0A0A0A" alt="QUAICU Governance Kernel" />
</p>

<h1 align="center">The Governance Layer Your AI Can't Ship Without</h1>

<p align="center">
  <strong>A standalone, embeddable governance engine that makes every AI action<br/>auditable, policy-compliant, and tamper-evident — <em>before</em> it executes.</strong>
</p>

<p align="center">
  Drop it into a Python app, call it over REST, or run it air-gapped in a bank.<br/>
  One core. No forks. Fails closed, always.
</p>

<p align="center">
  <a href="#-the-problem">Problem</a>&nbsp;·&nbsp;
  <a href="#-how-it-works">How It Works</a>&nbsp;·&nbsp;
  <a href="#-why-quaicu">Why QUAICU</a>&nbsp;·&nbsp;
  <a href="#-14-governance-layers">14 Layers</a>&nbsp;·&nbsp;
  <a href="#-deploy-your-way">Deploy</a>&nbsp;·&nbsp;
  <a href="#-quickstart">Quickstart</a>&nbsp;·&nbsp;
  <a href="#-build-status">Status</a>&nbsp;·&nbsp;
  <a href="#-license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/RFC%206962-compliant-2962FF?style=flat-square" />
  <img src="https://img.shields.io/badge/tests-532%20passing-00C853?style=flat-square" />
  <img src="https://img.shields.io/badge/fail--closed-by%20design-6C3AED?style=flat-square" />
  <img src="https://img.shields.io/badge/license-proprietary-555?style=flat-square" />
</p>

---

<p align="center">
  <strong>Evaluate&nbsp;→ Gate&nbsp;→ Execute&nbsp;→ Seal.</strong>&nbsp; Every AI decision, governed and provable —<br/>
  so when the regulator asks <em>"what did your model do, and were you allowed to?"</em>, you have the receipt.
</p>

<table align="center">
<tr>
<td align="center" width="33%"><strong>🔐 Provable</strong><br/><sub>RFC 6962 tamper-evident ledger.<br/>Verifiable by a third party.</sub></td>
<td align="center" width="33%"><strong>⛔ Fail-closed</strong><br/><sub>Any error or doubt → deny/halt.<br/>Never manufactures false assurance.</sub></td>
<td align="center" width="33%"><strong>🔌 Portable</strong><br/><sub>Runs in your VPC, on-prem,<br/>or fully air-gapped.</sub></td>
</tr>
</table>

<br/>

---

<br/>

## 🔥 The Problem

You're shipping AI that makes decisions about real people — loans, grades, hiring, risk scores. Regulators are watching. Your board is asking. And right now you have **no provable record** of what your AI decided, why, or whether it was even allowed to.

Building governance from scratch for every product is:

- **Expensive** — months of engineering on audit trails, policy engines, and consent flows
- **Error-prone** — one `if` statement away from failing open and manufacturing false assurance
- **Impossible to certify** — your auditor can't verify a bespoke system they've never seen

**QUAICU is that governance layer, built once, correctly — so you don't.**

<br/>

---

<br/>

## ⚡ How It Works

Every governed action runs the same strict, deterministic lifecycle. No exceptions. No shortcuts. No silent failures.

```
┌─────────┐    ┌──────────┐    ┌──────┐    ┌─────────┐    ┌──────┐    ┌──────┐
│ PROPOSE │──▶ │ EVALUATE │──▶ │ GATE │──▶ │ EXECUTE │──▶ │ SEAL │──▶ │ EMIT │
└─────────┘    └──────────┘    └──────┘    └─────────┘    └──────┘    └──────┘
                    │              │            │             │
                Policies +     Human-in-     State        Tamper-
                consent        the-loop      change       evident
                (CEL)          (if req'd)    applied      ledger entry
```

> **The guarantee:** any failure, timeout, or ambiguity at **any** step → the action is **denied or halted**. The kernel never fails open. Ever. A governance kernel that fails open is worse than none — it manufactures false assurance.

<br/>

---

<br/>

## 💎 Why QUAICU

| | |
|---|---|
| **Governance is the product** | Not a feature bolted onto a model. The kernel governs the action regardless of which model produced it or where it runs — model- and deployment-agnostic. |
| **One core, no forks** | Every customer runs the *same* codebase. Differences live in config, adapters, and content packs — never a branch. What we certify once, every customer inherits. |
| **Prove, don't assert** | The ledger is an RFC 6962 transparency log — the same standard behind certificate transparency. Your auditor verifies it independently; they don't take your word. |
| **No bypass** | There is no fast-path. Even admin actions are governed actions. Nothing executes or seals without passing evaluation and gating. |
| **Deterministic & replayable** | Identical inputs → identical decision. Any sealed action is re-derivable from the ledger — replay reconstructs, never re-runs side effects. |
| **Runs in someone else's environment** | Encryption at rest, signed releases, least privilege, air-gap-ready. Built to be trusted on hardware you don't control. |

<br/>

---

<br/>

## 🛡️ 14 Governance Layers

Not a single feature — a **full governance stack**, built as independent, composable layers on a shared lifecycle spine.

| | Layer | What It Does |
|---|---|---|
| **K·01** | **Policy Engine** | Evaluates every action against all applicable policies. CEL conditions, total conflict resolution, fully deterministic. |
| **K·02** | **TrustLedger** | RFC 6962 Merkle transparency log. Append-only, per-tenant, with cryptographic inclusion & consistency proofs. |
| **K·03** | **HITL Gate** | Human-in-the-loop approval. Timeout → reject. No silent approvals, ever. |
| **K·04** | **DPDP Consent** | Purpose-bound consent checked at evaluation time. Missing / expired / withdrawn → deny. |
| **K·05** | **AI Gateway** | PII masking → model routing → prompt logging → cost governance. Every model call governed and sealed. |
| **K·06** | **Process Engine** | Durable state machine with HITL pauses and incident rollback. Postgres or Temporal adapter. |
| **K·07** | **Event Bus** | Structured events emitted only after seal. A failed emit never alters a sealed outcome. |
| **K·08** | **Model Registry** | Per-tenant model allowlists the gateway enforces. No approved model → deny, no fallback. |
| **K·09** | **Fairness** | Bias and fairness sweeps over recorded decisions; the delta feeds policy impact reports. |
| **K·10** | **Drift Monitor** | Detects model and decision drift against a recorded baseline; breaches raise incidents. |
| **K·11** | **Explainability** | Point-in-time explanations derived from recorded inputs — no model re-call. |
| **K·12** | **Incident Engine** | Rollback as a *governed action* through the full lifecycle. No out-of-band effects. |
| **K·13** | **Sandbox** | Counterfactual replay: test candidate policies against history before they ever enforce. |
| **K·14** | **Regulatory Mapping** | Maps policies → regulations. Generates signed, point-in-time evidence packs that verify against the ledger. |

<br/>

---

<br/>

## 🏗️ Architecture

One core. No forks. No domain imports. Customer differences are configuration — never code branches.

```
╔══════════════════════════════════════════════════════════════╗
║  DELIVERY ADAPTERS  (thin wrappers over core)                ║
║    Python SDK  ·  FastAPI / REST  ·  Docker Image            ║
╠══════════════════════════════════════════════════════════════╣
║  CORE KERNEL  —  one codebase, no forks, zero domain imports ║
║    Lifecycle Spine  +  14 Governance Layers  +  Port APIs    ║
╠══════════════════════════════════════════════════════════════╣
║  PLUGGABLE ADAPTERS  (selected by config)                    ║
║    Inference · HITL · Identity · Storage · Workflow           ║
╠══════════════════════════════════════════════════════════════╣
║  CONTENT PACKS  (data, not code)                             ║
║    Policy Packs  ·  Regulatory Maps (RBI · EU AI Act · DPDP) ║
╚══════════════════════════════════════════════════════════════╝
```

**Onboarding a customer** = pick adapters in config + load relevant policy packs. Zero core code touched.

<br/>

---

<br/>

## 🚀 Deploy Your Way

Three delivery modes. Three customer profiles. One kernel.

<table>
<tr>
<td valign="top" width="33%">

### 🐍 Python SDK

**For: AI agencies & product teams**

Govern an existing function — no signature change.

```python
from delivery.sdk import Kernel

kernel = Kernel.from_config("kernel.toml")

@kernel.guard(policy="loan.approve")
async def approve_loan(application):
    ...                       # unchanged

# set the actor once at the boundary
async with kernel.actor_context(user):
    await approve_loan(app)   # call-site unchanged
```

</td>
<td valign="top" width="33%">

### 🌐 REST API

**For: polyglot stacks & enterprises**

Standard OpenAPI. Any language.

```bash
POST /v1/authorize          # or /v1/actions/propose
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "type": "loan.approve",
  "payload": { ... }
}
# actor is resolved from the
# token — never sent in the body
```

</td>
<td valign="top" width="33%">

### 🐳 Docker Image

**For: regulated enterprises**

Self-contained. Air-gappable.

```bash
docker pull quaicu/kernel:latest

# or deploy to k3s / K8s
helm install quaicu-kernel \
  ./charts/kernel
```

</td>
</tr>
</table>

<br/>

---

<br/>

## 🔒 Security That Auditors Love

This isn't security theater. Every mechanism is independently verifiable.

| Capability | Implementation |
|---|---|
| **Tamper-evident audit trail** | RFC 6962 Merkle transparency log — the standard behind certificate transparency |
| **Cryptographic ledger integrity** | Ed25519 Signed Tree Heads with inclusion & consistency proofs |
| **PII protection** | Sensitive fields masked before transmission — raw data never leaves the tenant boundary |
| **Secrets management** | OpenBao (MPL 2.0) — Vault-compatible, no BSL restrictions |
| **Fail-closed by default** | Unlogged model calls are blocked. Unreachable policy services deny. Period. |
| **Zero-trust posture** | Encryption at rest, signed releases, least privilege, supply-chain hygiene |

> 🏦 **External cryptographic review** is required before any bank deployment — and we budget for it, because it's a sales asset, not just a safeguard.

<br/>

---

<br/>

## 🏢 Multi-Tenancy That Banks Trust

Tenant isolation isn't a filter. It's an architectural guarantee.

| Tier | Isolation | How |
|---|---|---|
| **Sovereign** | Physical | Dedicated DB on customer hardware |
| **Dedicated** | Instance | Dedicated DB instance in customer VPC |
| **Shared** | Schema + RLS | Schema-per-tenant with Row-Level Security as defense-in-depth |

> **The ledger is always per-tenant tables** — never a shared table keyed by `tenant_id`. Cross-tenant contamination is **architecturally impossible**, not merely unlikely.

<br/>

---

<br/>

## 📐 Core Invariants

These aren't aspirational. They're **property-tested in CI on every commit.**

| Invariant | What It Means |
|---|---|
| **Fail-closed** | Any failure or ambiguity → DENY/HALT. Never allow. |
| **No bypass** | No path executes an action that skipped evaluation and gating. Even admin actions are governed. |
| **Determinism** | Identical inputs → identical decision. No hidden state. No wall-clock branching. |
| **Total conflict resolution** | Policy evaluation never returns "undefined." Resolution order is explicit and exhaustive. |
| **Tenant isolation** | No data, decision, or ledger entry crosses a tenant boundary. Tested adversarially. |
| **Ledger immutability** | A sealed entry is never modified. Old proofs remain verifiable forever. |
| **Idempotency** | Re-submitting the same proposal never double-executes, double-seals, or double-emits. |
| **Replay fidelity** | Every governed action is re-derivable from the ledger. Replay reconstructs — never re-performs side effects. |

<br/>

---

<br/>

## 📊 Build Status

All 14 governance layers and the delivery phase are built and green. **532 tests** passing across unit, conformance, and SDK end-to-end suites. Postgres storage + policy adapters, OpenBao signer, Docker image, Helm chart, and CI/signed-release pipeline shipped.

<sub>✅ Shipped · 🔨 In progress · 📋 Planned</sub>

| Layer | Status | Notes |
|---|---|---|
| Spine · Ports · Types | ✅ **Shipped** | Lifecycle engine, all ports (inference/hitl/identity/storage/workflow/consent), frozen shared types |
| K·01 Policy Engine | ✅ **Shipped** | CEL evaluation, total conflict resolution; config-wireable + **durable policy store** (write-through cache, Postgres) |
| K·02 TrustLedger | ✅ **Shipped** | RFC 6962 Merkle tree, Ed25519 STH, inclusion/consistency proofs, conformance suite |
| K·03 HITL Gate | ✅ **Shipped** | Approval routing, role-based authz + self-approval guard, fail-closed timeout |
| K·04 DPDP Consent | ✅ **Shipped** | Purpose-bound consent, fail-closed on missing/expired/withdrawn, standalone composable layer |
| K·05 AI Gateway | ✅ **Shipped** | PII masking, model routing, budget, prompt logging; wired to `kernel.generate()` + `/v1/inference` |
| K·06 Process Engine | ✅ **Shipped** | Durable process/step machine (in-memory adapter; Temporal pending) |
| K·07 Event Bus | ✅ **Shipped** | Emit-after-seal event bus with conformance suite |
| K·08 Model Registry | ✅ **Shipped** | Per-tenant model allowlists enforced by the gateway |
| K·09 Fairness | ✅ **Shipped** | Bias/fairness sweeps over recorded decisions |
| K·10 Drift Monitor | ✅ **Shipped** | Decision/model drift against a recorded baseline |
| K·11 Explainability | ✅ **Shipped** | Point-in-time explanations from recorded inputs, no model re-call |
| K·12 Incident Engine | ✅ **Shipped** | Rollback as a governed action |
| K·13 Sandbox | ✅ **Shipped** | Counterfactual replay / backtest of candidate policies |
| K·14 Regulatory Mapping | ✅ **Shipped** | Policy→regulation mapping + signed evidence packs |
| Delivery (SDK · REST · Docker · Helm) | ✅ **Shipped** | `Kernel` SDK, FastAPI app + routes, Postgres adapters, OpenBao signer, CI/signed releases |

**Recent capability waves** (see `docs/adr/`):

| Capability | Status | Notes |
|---|---|---|
| Composable governance ([ADR-0002](New/quaicu-kernel/docs/adr/0002-composable-governance-profile.md)) | ✅ **Shipped** | `GovernanceProfile` — enforce each layer independently, as a pack, or all; presets + per-action config |
| Decision-only authorize / monitor ([ADR-0003](New/quaicu-kernel/docs/adr/0003-decision-only-authorization-surface.md)) | ✅ **Shipped** | `kernel.check()` / `POST /v1/authorize` (pure PDP) + reference enforcement-point middleware |
| Zero-friction integration ([ADR-0004](New/quaicu-kernel/docs/adr/0004-zero-friction-integration.md)) | ✅ **Shipped** | `@kernel.guard` / `kernel.wrap` / `kernel.proxy` + `actor_context` — no signature or call-site changes |
| Policy management API + dashboards | 🔨 **In progress** | Durable store + SDK write-through shipped ([ADR-0005](New/quaicu-kernel/docs/adr/0005-durable-policy-store-write-through.md)); HTTP CRUD routes, simulate, and read-models next |

<br/>

---

<br/>

## 🧪 Quickstart

**Prerequisites:** Python 3.11+ and `pip` (or `uv`).

```bash
# 1. install dependencies (from the repo root)
pip install -e .

# 2. run the kernel test suite (532 tests)
cd New/quaicu-kernel
pytest

# 3. run a specific category
pytest -m conformance        # spec-derived golden cases
pytest -m tenant_isolation   # adversarial cross-tenant tests
```

<br/>

---

<br/>

## 🧰 Tech Stack

Every choice optimizes for **correctness, auditability, and portability** — not novelty.

| Concern | Choice | Why |
|---|---|---|
| Core language | **Python 3.11+** | Ecosystem fit, AI-native, proven |
| Policy language | **CEL** | Deterministic, sandboxed, guaranteed-terminating |
| API framework | **FastAPI** | Async, type-safe, auto-documented |
| Primary datastore | **PostgreSQL 16+** | Battle-tested, pgvector-ready |
| Audit ledger | **RFC 6962 Merkle log on Postgres** | Verifiable, standard, peer-reviewed |
| Secrets | **OpenBao** (MPL 2.0) | Vault-compatible, BSL-free |
| Durable workflow | **Temporal** / **Postgres state machine** | Tiered by deployment |
| Inference | **Ollama · vLLM · TGI · OpenAI · Anthropic · Gemini · Bedrock · Azure OpenAI · Vertex** | Pluggable, governed, never hardcoded |
| Orchestration | **k3s / docker-compose / K8s** | Matched to the customer tier |
| IaC | **OpenTofu** (MPL 2.0) | Terraform-compatible, BSL-free |
| Observability | **OpenTelemetry + Prometheus + Grafana + Loki** | Full-stack, vendor-neutral |

<br/>

---

<br/>

## 📁 Repository Structure

The kernel package lives under `New/quaicu-kernel/`; the workspace root holds the spec, the working agreement, and the skill library that guides the build.

```
Kernel/
├── README.md                       # this page
├── AGENTS.md                       # the multi-agent working agreement (read first)
├── SKILLS.md                       # directory → skill routing map (read-first protocol)
├── QUAICU_Kernel_Build_Spec.md     # the authoritative build specification
├── .agents/skills/                 # curated skill library (quaicu-* layer + stack skills)
└── New/quaicu-kernel/              # ── the kernel package ──
    ├── core/                       #   zero domain imports, zero concrete deps
    │   ├── types.py                #     frozen shared value types
    │   ├── errors.py               #     kernel error hierarchy
    │   ├── ports/                  #     port interfaces — core depends ONLY on these
    │   ├── lifecycle/              #     spine + GovernanceProfile + decision-only path
    │   ├── policy/                 #     K·01 — Policy Engine (CEL) + durable repository port
    │   ├── ledger/                 #     K·02 — TrustLedger (RFC 6962)
    │   ├── hitl/                   #     K·03 — Human-in-the-Loop Gate
    │   ├── consent/                #     K·04 — DPDP Consent
    │   ├── gateway/                #     K·05 — AI Gateway
    │   ├── process/                #     K·06 — Process Engine
    │   ├── events/                 #     K·07 — Event Bus
    │   ├── registry/               #     K·08 — Model Registry
    │   ├── fairness/               #     K·09 — Fairness sweeps
    │   ├── drift/                  #     K·10 — Drift Monitor
    │   ├── explain/                #     K·11 — Explainability
    │   ├── incident/               #     K·12 — Incident Engine
    │   ├── sandbox/                #     K·13 — Counterfactual Sandbox
    │   └── regmap/                 #     K·14 — Regulatory Mapping
    ├── adapters/                   #   pluggable, selected by config (never imported by core)
    │   ├── policy/ inference/ hitl/ identity/ storage/ ledger/ events/ workflow/
    ├── delivery/                   #   thin wrappers over core
    │   ├── sdk/                     #     Kernel SDK: guard/wrap/proxy/generate/check/for_agent
    │   └── api/                     #     FastAPI app, routes, governance middleware (PEP)
    ├── tests/
    │   ├── conformance/            #     spec-derived golden suites per layer
    │   └── unit/                   #     unit tests
    ├── docs/
    │   ├── BUILD_JOURNAL.md        #     chronological build decisions
    │   └── adr/                    #     Architecture Decision Records (0001–0005)
    └── CODEOWNERS                  #     per-layer ownership
```

<br/>

---

<br/>

## 🤝 Contributing

See **[AGENTS.md](AGENTS.md)** for the working agreement, the layer-ownership model, and the Definition of Done — and **[SKILLS.md](SKILLS.md)** for which skill to read before touching each part of the kernel.

**The rules that don't bend:**

- `core/` contains **zero domain concepts** — `grep` for student, loan, patient must return nothing
- `core/` imports **zero concrete implementations** — only port interfaces
- Every layer must pass the **universal Definition of Done** before merge
- Frozen types and ports require an **ADR + leadership sign-off** to change

<br/>

---

<br/>

## 📜 License

Proprietary. © 2026 QUAICU. All rights reserved.

<br/>

<p align="center">
  <strong>QUAICU Governance Kernel</strong><br/>
  <em>Because "trust us, the AI is fine" doesn't pass an audit.</em>
</p>
