# Architecture

The QUAICU Governance Kernel is a fail-closed, model/cloud-neutral **AI Action Governance** control plane. It enforces policy on every AI action and seals each one to an offline-verifiable RFC-6962 ledger.

> *"Don't just observe your AI. Govern it — and prove it."*

---

## The problem

AI is moving from advisory chatbots to **read-write agents** — the risk flips from hallucination to **unauthorized execution**. GRC tools document models but are blind at runtime. Observability watches but doesn't gate. Prompt firewalls secure the prompt, not the action. Hyperscaler guardrails lock you in.

Nobody owns *"mathematical proof of what the AI did, under which policy, approved by whom."* The kernel does.

---

## The governance lifecycle

Every AI action follows one non-bypassable sequence:

```
PROPOSE → EVALUATE → GATE → EXECUTE → SEAL → EMIT
          (policy +   (human    (state    (RFC-6962   (events,
           consent)    approval   change)   Merkle      after seal)
                       if needed)           proof)
```

Any failure, timeout, or error → **DENY or HALT**. An ungoverned action is a breach.

| Phase | What happens | Failure → |
|-------|-------------|-----------|
| **PROPOSE** | Action enters with idempotency key | Duplicate key → returns existing result |
| **EVALUATE** | Policies (CEL) + consent + model registry checked | Any error → **DENY** |
| **GATE** | Human approval routed if policy requires it | Timeout → **REJECTED** (never auto-approves) |
| **EXECUTE** | State change via durable workflow | Workflow failure → **HALT** |
| **SEAL** | Result written to RFC-6962 Merkle tree, HSM-signed | Seal failure → **HALTED** |
| **EMIT** | Structured event published after seal | Emit failure → logged, seal never rolls back |

---

## Hexagonal architecture (ports & adapters)

The core imports zero concrete libraries. Everything is swappable via config:

```
┌─────────────────────────────────┐
│   DELIVERY LAYER                │
│   SDK · REST API · Docker       │
├─────────────────────────────────┤
│   CORE KERNEL (14 layers)       │
│   Lifecycle spine + port APIs   │
├─────────────────────────────────┤
│   PLUGGABLE ADAPTERS            │
│   Inference · Storage · Identity│
│   Workflow · Ledger · HITL      │
├─────────────────────────────────┤
│   CONTENT PACKS (data not code) │
│   Policies · Regulatory packs   │
└─────────────────────────────────┘
```

**Port interfaces:**

| Port | Abstracts |
|------|-----------|
| `InferencePort` | Model calls (LLM generation) |
| `StoragePort` | Database (kernel-owned tables) |
| `IdentityPort` | Actor resolution |
| `WorkflowPort` | Durable workflow execution |
| `HITLPort` | Human-in-the-loop routing |
| `ConsentPort` | User consent verification |
| `EventBusPort` | Event emission after seal |

Onboarding a customer = pick a deployment mode + set adapters in config + load policy packs. **No core code is touched.**

---

## The 14 governance layers

**Core (K·01–K·08) — production-ready:**

| Layer | Name | Purpose |
|-------|------|---------|
| K·01 | Policy Engine | CEL-based rules, conflict resolution (deny wins) |
| K·02 | TrustLedger | RFC-6962 Merkle tree, cryptographic proofs, HSM-signed |
| K·03 | HITL Gate | Human-in-the-loop approvals, timeout = rejection |
| K·04 | DPDP Consent | Purpose-bound consent verification at eval-time |
| K·05 | AI Gateway | Model routing, PII masking, prompt logging, token budgets |
| K·06 | Process Engine | Durable workflows (Postgres state-machine or Temporal) |
| K·07 | Event Bus | Structured events emitted only after seal |
| K·08 | Model Registry | Per-tenant model allowlists |

**Extended (K·09–K·14) — built, awaiting pilot:**

| Layer | Name | Purpose |
|-------|------|---------|
| K·09 | Fairness | Background sweeps detecting bias across decisions |
| K·10 | Drift Monitor | Detects model behavior semantic drift |
| K·11 | Explainability | Reconstructs why any past decision was made |
| K·12 | Incident Engine | Post-breach rollbacks as governed actions |
| K·13 | Sandbox | "What if" replay — test policies before live |
| K·14 | Regulatory Mapping | Maps policies to regulations (RBI, GDPR, EU AI Act, DPDP) |

---

## Three deployment tiers (same image)

| | Sovereign | Dedicated | SaaS |
|---|---|---|---|
| **Who hosts** | Customer hardware | Customer cloud (VPC) | QUAICU |
| **Inference** | Ollama / vLLM (local) | Vertex / Bedrock (private) | OpenAI / Anthropic / Vertex |
| **Signing** | OpenBao (Ed25519) | Cloud KMS (ECDSA P-256) | Cloud KMS |
| **Isolation** | Physical | One DB per tenant | Schema-per-tenant + RLS |
| **Best for** | Banks, defence, regulated | Large enterprises | SaaS, startups, agencies |

---

## Why it wins

- **Offline-verifiable proof** — a regulator verifies the bundle without trusting QUAICU
- **Model-neutral** — OpenAI / Anthropic / Vertex / Bedrock / Ollama, all governed identically
- **Sovereign** — customer-hosted, customer-held KMS; fits RBI/DPDP localization requirements
- **Turnkey regimes** — RBI FREE-AI, DPDP, EU AI Act policy packs ship in the box

---

## Honest status

!!! success "Production"
    K·01–K·08 are live in production at Woxsen University under the ALIS deployment.

!!! info "Built, awaiting pilot"
    K·09–K·14 are built and passing their test suites. First live deployment via design-partner pilot.

!!! warning "In progress"
    SOC 2, pen-test, K·02 crypto third-party review, and counsel-signed DPA/MSA are in progress. Some managed cloud adapters are validated against fake clients — the pilot is where they first run for real.
