<p align="center">
  <img src="https://img.shields.io/badge/QUAICU-Governance%20Kernel-0A0A0A?style=for-the-badge&labelColor=6C3AED&color=0A0A0A" alt="QUAICU Governance Kernel" />
</p>

<h1 align="center">
  The Governance Layer Your AI Can't Ship Without
</h1>

<p align="center">
  <strong>A standalone, embeddable governance engine that makes every AI action auditable, policy-compliant, and tamper-evident — before it executes.</strong>
</p>

<p align="center">
  <a href="#-the-problem">Problem</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-how-it-works">How It Works</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-14-governance-layers">14 Layers</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-deploy-your-way">Deploy</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-quickstart">Quickstart</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-tech-stack">Stack</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/license-proprietary-6C3AED?style=flat-square" />
  <img src="https://img.shields.io/badge/status-active%20development-00C853?style=flat-square" />
  <img src="https://img.shields.io/badge/RFC%206962-compliant-blue?style=flat-square" />
</p>

---

<br/>

## 🔥 The Problem

You're building AI-powered products. Your models make decisions that affect real people — loans, grades, hiring, risk scoring. Regulators are watching. Your board is asking questions. And right now, you have **no provable record** of what your AI decided, why, or whether it was allowed to.

Building governance from scratch for every product is:

- **Expensive** — months of engineering on audit trails, policy engines, and consent flows  
- **Error-prone** — one `if` statement away from failing open and manufacturing false assurance  
- **Impossible to certify** — because your auditor can't verify a bespoke system they've never seen  

**QUAICU solves this in one layer.**

<br/>

---

<br/>

## ⚡ How It Works

Every governed action follows a strict, deterministic lifecycle. No exceptions. No shortcuts. No silent failures.

```
┌─────────┐     ┌──────────┐     ┌──────┐     ┌─────────┐     ┌──────┐     ┌──────┐
│ PROPOSE │────▶│ EVALUATE │────▶│ GATE │────▶│ EXECUTE │────▶│ SEAL │────▶│ EMIT │
└─────────┘     └──────────┘     └──────┘     └─────────┘     └──────┘     └──────┘
                     │                │             │              │
                  Policies         Human-in-      State        Tamper-
                  checked          the-loop       change       evident
                  (CEL)            approval       applied      ledger
                                   (if req'd)                  entry
```

> **The guarantee:** any failure, timeout, or ambiguity at **any** step → the action is **denied or halted**. The kernel never fails open. Ever.

<br/>

---

<br/>

## 🏗️ Architecture

One core. No forks. No domain imports. Customer differences are configuration — never code branches.

```
╔══════════════════════════════════════════════════════════════╗
║  DELIVERY ADAPTERS                                          ║
║    Python SDK  ·  FastAPI / REST  ·  Docker Image            ║
╠══════════════════════════════════════════════════════════════╣
║  CORE KERNEL                                                 ║
║    Lifecycle Spine  +  14 Governance Layers  +  Port APIs    ║
╠══════════════════════════════════════════════════════════════╣
║  PLUGGABLE ADAPTERS  (selected by config)                    ║
║    Inference · HITL · Identity · Storage · Workflow           ║
╠══════════════════════════════════════════════════════════════╣
║  CONTENT PACKS  (data, not code)                             ║
║    Policy Packs  ·  Regulatory Maps (RBI, EU AI Act, DPDP)   ║
╚══════════════════════════════════════════════════════════════╝
```

**Onboarding a customer** = pick adapters in config + load relevant policy packs. Zero core code touched.

<br/>

---

<br/>

## 🛡️ 14 Governance Layers

The kernel isn't a single feature — it's a **full governance stack**, built as independent, composable layers on a shared lifecycle spine.

| | Layer | What It Does |
|---|---|---|
| **K·01** | **Policy Engine** | Evaluates every action against all applicable policies. CEL conditions. Total conflict resolution. Deterministic. |
| **K·02** | **TrustLedger** | RFC 6962 Merkle transparency log. Append-only, per-tenant, with cryptographic inclusion & consistency proofs. |
| **K·03** | **HITL Gate** | Human-in-the-loop approval. Timeout → reject. No silent approvals. |
| **K·04** | **DPDP Consent** | Data protection consent checks at evaluation time. Point-in-time replay. |
| **K·05** | **AI Gateway** | PII masking → model routing → prompt logging → cost governance. Every model call governed and sealed. |
| **K·06** | **Process Engine** | Durable state machine with HITL pauses and incident rollback. Postgres or Temporal adapter. |
| **K·07** | **Event Bus** | Structured event emission post-seal. A failed emit never alters a sealed outcome. |
| **K·08** | **Model Registry** | Per-tenant model allowlists. The gateway enforces against it. |
| **K·09** | **Fairness** | Bias detection and fairness sweeps over recorded decisions. |
| **K·10** | **Drift Monitor** | Detects model and decision drift over time. |
| **K·11** | **Explainability** | Generates decision explanations from recorded inputs and policy versions. |
| **K·12** | **Incident Engine** | Governed rollback — itself a governed action through the full lifecycle. |
| **K·13** | **Sandbox** | Counterfactual replay: run historical actions against candidate policies before enforcement. |
| **K·14** | **Regulatory Mapping** | Maps policies → regulatory requirements. Generates signed, point-in-time evidence packs. |

<br/>

---

<br/>

## 🚀 Deploy Your Way

Three delivery modes. Three customer profiles. One kernel.

<table>
<tr>
<td align="center" width="33%">

### 🐍 Python SDK

**For: AI agencies & product companies**

Embed governance directly into your app with a single decorator.

```python
from quaicu_kernel import Kernel

kernel = Kernel(config="quaicu.yaml")

@kernel.governed
async def approve_loan(application):
    # Your logic here
    # The kernel handles the rest
    ...
```

</td>
<td align="center" width="33%">

### 🌐 REST API

**For: Product companies & enterprises**

Standard OpenAPI. Integrate from any language.

```bash
POST /kernel/v1/actions/propose
Content-Type: application/json

{
  "type": "loan.approve",
  "payload": { ... },
  "actor": "user:analyst-42"
}
```

</td>
<td align="center" width="33%">

### 🐳 Docker Image

**For: Regulated enterprises**

Self-contained. Air-gappable. Helm charts included.

```bash
docker pull quaicu/kernel:latest

# Or deploy to k3s/K8s
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

This isn't security theater. Every mechanism is verifiable.

| Capability | Implementation |
|---|---|
| **Tamper-evident audit trail** | RFC 6962 Merkle transparency log — the same standard behind certificate transparency |
| **Cryptographic ledger integrity** | Ed25519 Signed Tree Heads (STH) with inclusion & consistency proofs |
| **PII protection** | Sensitive fields masked before transmission — raw data never leaves the tenant boundary |
| **Secrets management** | OpenBao (MPL 2.0) — Vault-compatible, no BSL restrictions |
| **Fail-closed by default** | Unlogged model calls are blocked. Unreachable policy services deny. Period. |
| **Zero trust posture** | Encryption at rest, signed releases, least privilege, supply-chain hygiene |

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

## 🧪 Quickstart

### Prerequisites

- Python 3.11+
- `pip` or `uv`

### Install

```bash
cd New/quaicu-kernel
pip install -e ".[dev]"
```

### Run the test suite

```bash
pytest
```

### Run specific test categories

```bash
# Spec-derived golden cases
pytest -m conformance

# Property-based invariant tests  
pytest -m property

# Adversarial cross-tenant leakage tests
pytest -m tenant_isolation
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
| Orchestration | **k3s / docker-compose / K8s** | Matched to customer |
| IaC | **OpenTofu** (MPL 2.0) | Terraform-compatible, BSL-free |
| Observability | **OpenTelemetry + Prometheus + Grafana + Loki** | Full-stack, vendor-neutral |

<br/>

---

<br/>

## 📐 Core Invariants

These aren't aspirational. They're **tested in CI on every commit.**

| Invariant | What It Means |
|---|---|
| **Fail-closed** | Any failure or ambiguity → DENY/HALT. Never allow. |
| **No bypass** | No code path executes an action that skipped evaluation and gating. Even admin actions are governed. |
| **Determinism** | Identical inputs → identical policy decision. No hidden state. No wall-clock branching. |
| **Total conflict resolution** | Policy evaluation never returns "undefined." Resolution order is explicit and exhaustive. |
| **Tenant isolation** | No data, decision, or ledger entry crosses a tenant boundary. Tested adversarially. |
| **Ledger immutability** | A sealed entry is never modified. Old proofs remain verifiable forever. |
| **Idempotency** | Re-submitting the same proposal never double-executes, double-seals, or double-emits. |
| **Replay fidelity** | Every governed action is re-derivable from the ledger. Replay reconstructs — never re-performs side effects. |

<br/>

---

<br/>

## 📊 Build Status

| Layer | Status | Notes |
|---|---|---|
| Spine + Ports + Types | ✅ **Shipped** | Lifecycle engine, all 6 ports, frozen shared types |
| K·01 Policy Engine | ✅ **Shipped** | CEL evaluation, total conflict resolution, conformance suite |
| K·02 TrustLedger | ✅ **Shipped** | RFC 6962 Merkle tree, Ed25519 STH, inclusion/consistency proofs |
| K·03 HITL Gate | ✅ **Shipped** | Approval routing, fail-closed timeout, conformance suite |
| K·04 DPDP Consent | ✅ **Shipped** | Purpose-based consent engine |
| K·05 AI Gateway | ✅ **Shipped** | PII masking, model routing, budget enforcement, prompt logging |
| K·06 Process Engine | 🔨 **In Progress** | Process definitions and step DSL |
| K·07 Event Bus | ✅ **Shipped** | In-process event bus with conformance suite |
| K·08–K·14 | 📋 **Planned** | Net-new layers — no prior implementation |

<br/>

---

<br/>

## 📁 Repository Structure

```
quaicu-kernel/
├── core/                       # The kernel — zero domain imports, zero concrete deps
│   ├── types.py                # Frozen shared value types (Action, LedgerEntry, etc.)
│   ├── errors.py               # Kernel error hierarchy
│   ├── ports/                  # Port interfaces — core depends ONLY on these
│   │   ├── consent.py          #   ConsentPort
│   │   ├── hitl.py             #   HITLPort
│   │   ├── identity.py         #   IdentityPort
│   │   ├── inference.py        #   InferencePort
│   │   ├── storage.py          #   StoragePort
│   │   └── workflow.py         #   WorkflowPort
│   ├── lifecycle/              # K·00 — the governance spine
│   ├── policy/                 # K·01 — Policy Engine (CEL)
│   ├── ledger/                 # K·02 — TrustLedger (RFC 6962)
│   ├── hitl/                   # K·03 — Human-in-the-Loop Gate
│   ├── consent/                # K·04 — DPDP Consent
│   ├── gateway/                # K·05 — AI Gateway
│   ├── process/                # K·06 — Process Engine
│   └── events/                 # K·07 — Event Bus
├── tests/
│   ├── conformance/            # Spec-derived golden test suites per layer
│   └── unit/                   # Unit tests
├── docs/
│   ├── BUILD_JOURNAL.md        # Chronological build decisions
│   └── adr/                    # Architecture Decision Records
├── AGENTS.md                   # AI agent coding guidelines
├── CODEOWNERS                  # Per-layer ownership
└── pyproject.toml              # Project config & dependencies
```

<br/>

---

<br/>

## 🤝 Contributing

See [AGENTS.md](New/quaicu-kernel/AGENTS.md) for coding guidelines, the layer ownership model, and the Definition of Done checklist.

**The rules that don't bend:**

- `core/` contains **zero domain concepts** — `grep` for student, loan, patient must return nothing  
- `core/` imports **zero concrete implementations** — only port interfaces  
- Every layer must pass the **universal Definition of Done** before merge  
- Frozen types and ports require an **ADR + leadership sign-off** to change  

<br/>

---

<br/>

<p align="center">
  <strong>QUAICU Governance Kernel</strong><br/>
  <em>Because "trust us, the AI is fine" doesn't pass an audit.</em>
</p>

<p align="center">
  © 2026 QUAICU · All rights reserved · Proprietary
</p>
