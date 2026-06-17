<p align="center">
  <img src="https://img.shields.io/badge/QUAICU-Sovereign%20Governance%20Kernel-0A0A0A?style=for-the-badge&labelColor=6C3AED&color=0A0A0A" alt="QUAICU Sovereign Governance Kernel" />
</p>

<h1 align="center">The Sovereign Governance Layer Your AI Can't Ship Without</h1>

<p align="center">
  <strong>A standalone, fail-closed, zero-trust governance engine that makes every AI-driven action and model inference policy-compliant, auditable, and mathematically provable — <em>before</em> execution.</strong>
</p>

<p align="center">
  Embed the Python SDK, run the container locally, or deploy air-gapped in a secure cloud.<br/>
  One core. Zero forks. Fails closed, always.
</p>

<p align="center">
  <a href="#-the-problem">The Problem</a>&nbsp;·&nbsp;
  <a href="#-how-it-works">How It Works</a>&nbsp;·&nbsp;
  <a href="#-why-quaicu">Why QUAICU</a>&nbsp;·&nbsp;
  <a href="#-quickstart">Quickstart</a>&nbsp;·&nbsp;
  <a href="#-architecture--14-layers">14 Layers</a>&nbsp;·&nbsp;
  <a href="#-licensing">Licensing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/RFC%206962-compliant-2962FF?style=flat-square" alt="RFC 6962 Compliant" />
  <img src="https://img.shields.io/badge/fail--closed-by%20design-6C3AED?style=flat-square" alt="Fail-Closed by Design" />
  <img src="https://img.shields.io/badge/multi--tenant-schema--level-00C853?style=flat-square" alt="Schema Multi-Tenant" />
  <img src="https://img.shields.io/badge/license-proprietary-555?style=flat-square" alt="Proprietary License" />
</p>

---

<p align="center">
  <strong>Evaluate&nbsp;→ Gate&nbsp;→ Execute&nbsp;→ Seal&nbsp;→ Emit.</strong>&nbsp; Every autonomous decision, governed and provable —<br/>
  so when the regulator asks <em>"why did your AI do that, and who approved it?"</em>, you have the receipt.
</p>

<table align="center">
<tr>
<td align="center" width="33%"><strong>🔐 Cryptographically Provable</strong><br/><sub>RFC 6962 Merkle transparency logs, verified independently by third-party auditors.</sub></td>
<td align="center" width="33%"><strong>⛔ Strictly Fail-Closed</strong><br/><sub>Any error, latency, or ambiguity → deny/halt. We never manufacture false assurance.</sub></td>
<td align="center" width="33%"><strong>🏢 Absolute Multi-Tenancy</strong><br/><sub>Hard schema-per-tenant isolation with native Postgres Row-Level Security (RLS).</sub></td>
</tr>
</table>

<br/>

## 🔥 The Problem

You are shipping generative AI agents making autonomous decisions—approving credit, adjusting pricing, accessing medical histories, or communicating with customers. Regulators are watching. Your legal team is nervous. And right now, you have **no tamper-evident record** of what your AI did, why, or whether it had the consent to do so.

Standard application backends aren't built to solve this:
*   **Bespoke Audit Logs are Mutable:** Standard databases can be modified by admins, making them useless under rigorous regulatory audits (EU AI Act, DPDP, HIPAA).
*   **Traditional Gateways are Static:** Standard API gateways cannot inspect prompt context, mask dynamic PII, evaluate sandboxed policies, or halt actions for human-in-the-loop review.
*   **Fail-Open Traps:** If your tracking or policy microservice is slow, traditional microservice gateways default to letting the action proceed. This **fails open**, creating severe compliance liability.

**QUAICU is the sovereign governance layer built once, correctly, so you don't have to.**

<br/>

## ⚡ How It Works

The QUAICU Kernel intercepts every proposed action at **Ring 0** and drives it through a strict, deterministic, and transaction-bound lifecycle:

```
┌─────────┐      ┌──────────┐      ┌──────┐      ┌─────────┐      ┌──────┐      ┌──────┐
│ PROPOSE │ ───▶ │ EVALUATE │ ───▶ │ GATE │ ───▶ │ EXECUTE │ ───▶ │ SEAL │ ───▶ │ EMIT │
└─────────┘      └──────────┘      └──────┘      └─────────┘      └──────┘      └──────┘
                      │                │              │              │
                  Policies &       Human-In-        Actual        Signed Merkle
                  DPDP Consent     The-Loop        Inference/     Receipt (K-02)
                  (CEL Sandboxed)  Timeout Gate    State Change   (Fail-Closed)
```

> **The Sovereign Guarantee:** If *any* step fails, times out, or errors, the action is **denied or halted**. The kernel never fails open. Period. An action is only executed if it is successfully evaluated, approved, and guaranteed to be cryptographically sealed in the ledger.

<br/>

## 🛠️ Zero-Friction Developer Experience

We believe that governance shouldn't slow developers down. The QUAICU SDK allows you to protect any existing application code or agentic tool **without changing its method signature or call sites.**

### 1. Guard Existing App Functions (Zero Friction)
Wrap functions with `@kernel.guard` and define the actor once at your request or task boundary:

```python
from delivery.sdk.kernel import Kernel
from core.types import Actor, ActorId

# 1. Initialize the Kernel client
kernel = Kernel.from_parts(
    tenant="demo-tenant",
    api_key="qk_test_local", 
    endpoint="http://localhost:8000"
)

# 2. Guard your existing function — signature and return types are untouched
@kernel.guard(policy="credit.approve")
async def approve_credit_line(loan_id: str, amount: float) -> dict:
    return {"status": "approved", "loan_id": loan_id, "amount": amount}

# 3. Bind the actor context at your request boundary
async def request_handler(user_id: str):
    user_actor = Actor(id=ActorId(user_id), tenant="demo-tenant", roles=("underwriter",))
    
    async with kernel.actor_context(user_actor):
        # Calls execute normally; unauthorized actors raise LifecycleDeniedError
        result = await approve_credit_line(loan_id="L-9821", amount=75000.0)
        return result
```

### 2. Guard Agentic Tools (Framework Agnostic)
Wrap any standard LangGraph, CrewAI, or Semantic Kernel tool. If the model attempts to invoke a tool without meeting your compliance policy, QUAICU intercepts and blocks it:

```python
@kernel.governed_tool(policy="customer.export_pii", name="export_data")
def export_user_data(customer_id: str) -> str:
    return f"Extracted personal records for {customer_id}"
```

### 3. Check Permissions Silently (Pure Monitor/PDP)
Ask the kernel for a policy verdict without executing the state change. Perfect for UI conditional rendering or async background monitoring:

```python
verdict = await kernel.check(
    policy="credit.approve",
    payload={"amount": 75000.0},
    actor=user_actor
)

if verdict.allowed:
    print(f"Action permitted. Policy Versions: {verdict.policy_versions}")
else:
    print(f"Action Blocked. Reason: {verdict.reason}")
```

<br/>

## 🐳 Quickstart: Run the Sovereign Tier locally (60 Seconds)

Experience QUAICU locally on your machine running inside a lightweight, secure container.

### 1. Boot the Container
Create a simple `docker-compose.yml` file to pull and start the pre-built Sovereign Tier image:

```yaml
version: '3.8'
services:
  quaicu-kernel:
    image: your-docker-registry/quaicu-kernel:free-tier
    container_name: quaicu-kernel
    ports:
      - "8000:8000"
    environment:
      - KERNEL_HOST=0.0.0.0
      - KERNEL_PORT=8000
```

Fire it up:
```bash
docker compose up -d
```
The interactive API documentation is now live at `http://localhost:8000/docs`.

### 2. Verify Your Configuration
Initialize the SDK pointing to your local container using the local developer bypass key `qk_test_local`, or sign up for our [Hosted SaaS Free Tier](https://your-website.com) to instantly acquire a cloud API key (`qk_live_...`).

<br/>

## 🛡️ Hardened Production-Grade Architecture

QUAICU is built for adversarial, high-risk environments where compliance breaches are existential.

*   **HSM-Backed Merkle Signing — your choice of signer:** **OpenBao** (MPL 2.0, Ed25519 — free of HashiCorp's BSL restrictions) for sovereign/air-gapped deployments, or **GCP Cloud KMS** (ECDSA P-256, FIPS 140-2 Level 3 HSM) where the private key provably never leaves the hardware. The signed-tree-head verifier is algorithm-aware, so regulator evidence packs verify offline regardless of signer.
*   **Physical Multi-Tenancy (F-07):** Ledger entries are written to isolated, schema-per-tenant PostgreSQL database schemas. Guarded with native **Row-Level Security (RLS)** as defense-in-depth, preventing cross-tenant data leaks.
*   **Production API Hardening:** 
    *   **HMAC-SHA256 API Key hashing** with a secure environment-injected salt pepper (`QUAICU_API_KEY_PEPPER`).
    *   **Rate Limiting with verification keys:** Authed requests are safely rate-limited based on secure tenant contexts, while unauthenticated traffic falls back to secure client-IP rate limiting, protecting the gateway from denial-of-service (DoS) attacks.
*   **Hexagonal Boundaries (F-08):** Core governance logic (`core/`) relies completely on ports (interfaces) and imports zero concrete libraries. Moving from local development to managed cloud is a config change, never a rewrite — drop-in adapters already ship for **GCP Cloud KMS** signing and **Vertex AI** (private, no public-internet egress) inference, plus Postgres/Cloud SQL storage and a Redis shared meter.

<br/>

## 🏢 The 14 Sovereign Governance Layers

QUAICU is not a single safety hook. It is a unified, 14-layer enterprise-grade governance stack:

| Layer | Name | What It Solves |
|---|---|---|
| **K·01** | **Policy Engine** | Sandboxed Common Expression Language (CEL) policy envelopes. Total conflict resolution. |
| **K·02** | **TrustLedger** | RFC 6962 Merkle tree. Append-only transaction log generating inclusion & consistency proofs. |
| **K·03** | **HITL Gate** | Human-in-the-loop approval queues. Escapes silent approvals and enforces strict timeout-rejections. |
| **K·04** | **DPDP Consent** | Purpose-bound user consent verification checked at evaluate-time. Expired/missing consent → auto-deny. |
| **K·05** | **AI Gateway** | Fail-closed prompt logging, token budget governance, and regex/Presidio PII masking. |
| **K·06** | **Process Engine** | Durable workflow step-machines, abstracting Postgres state-engines or highly resilient Temporal clusters. |
| **K·07** | **Event Bus** | Best-effort emission of structured transactional events *only* after successful cryptographic ledger sealing. |
| **K·08** | **Model Registry** | Per-tenant model allowlists. Attempts to reach unauthorized, unapproved model nodes → auto-deny. |
| **K·09** | **Fairness** | Independent background async sweeps validating bias thresholds across historical decisions. |
| **K·10** | **Drift Monitor** | Detects model response or prompt payload semantic drift against a golden baseline. |
| **K·11** | **Explainability** | Point-in-time decision explaining. Reconstructs policy states from sealed inputs with no model re-calls. |
| **K·12** | **Incident Engine** | Enforces post-breach workflow rollbacks *as* fully governed and audited actions. |
| **K·13** | **Sandbox** | Counterfactual replay: allows you to run historical transactions against candidate policy sets before activating. |
| **K·14** | **Regulatory Mapping** | Maps live policy trees to external compliance structures (RBI, GDPR, EU AI Act) to export signed evidence packs. |

<br/>

## 💼 Licensing & Commercial Tiers

Unlock advanced cloud adapters, high-scale storage, and production-grade guarantees:

*   **Sovereign (Free Plan):** Local Docker container and SaaS Starter Tier. Real CEL policy enforcement (the free tier ships seeded, enforcing policies — not a pass-through), up to **10,000 governed actions/day** and 60 requests/min. In-memory storage + a structured audit stream (Cloud Logging), local signing, and community support. Self-serve signup (`POST /v1/signup`) mints a tenant + API key instantly.
*   **BYOL Private Cloud (Enterprise EULA):** Deploy fully isolated inside your own AWS/GCP VPC — a one-command Terraform module stands up Cloud Run + Cloud KMS (HSM) + Cloud SQL in *your* project, so your data never leaves it. Integrates with OpenBao or Cloud KMS HSMs, dedicated PostgreSQL with multi-tenant RLS, and custom regulatory content packs (a starter DPDP pack ships). Offline-verifiable license keys.
*   **Dedicated Enterprise SaaS:** Zero-management hosting on isolated single-tenant cloud servers. Custom SLA, dedicated throughput rates, and direct expert compliance support.

For commercial licenses and specialized bank EULAs, reach out to [our licensing team](https://your-website.com/pricing).

---

<p align="center">
  <strong>QUAICU Governance Kernel</strong><br/>
  <em>Because "trust us, the AI is fine" does not pass an audit.</em>
</p>
