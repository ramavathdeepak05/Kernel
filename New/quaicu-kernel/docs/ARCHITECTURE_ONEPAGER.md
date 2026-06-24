# QUAICU — Architecture One-Pager

> *"Don't just observe your AI. Govern it — and prove it."* A fail-closed, model/cloud-neutral
> **AI Action Governance** control plane: it enforces policy on AI *actions* and seals every one to an
> **offline-verifiable** RFC-6962 ledger. **The moat = non-repudiation × neutrality × sovereignty.**
> Full doc: [`../ARCHITECTURE.md`](../ARCHITECTURE.md) · See it run: [`examples/underwriting-demo/`](../examples/underwriting-demo/README.md).

## The problem
AI is moving from advisory chatbots to **read-write agents** — the risk flips from *hallucination* to
**unauthorized execution**. GRC tools document models but are blind at runtime; observability watches
but doesn't gate; prompt firewalls secure the prompt, not the action; hyperscaler guardrails lock you
in. Nobody owns *"mathematical proof of what the AI did, under which policy, approved by whom."*

## The lifecycle (every action, no bypass, fail-closed)
```
PROPOSE → EVALUATE → GATE → EXECUTE → SEAL → EMIT
          (policy +   (human    (state    (RFC-6962   (events,
           consent)    approval   change)   Merkle      after seal)
                       if needed)           proof)
```
Any failure/timeout/error → **DENY or HALT**. An ungoverned action is, by definition, a breach.

## The 14 governance layers (all built)
**Core (K·01–K·08):** Policy Engine (CEL) · TrustLedger (RFC-6962, HSM/KMS-signed) · HITL Gate ·
DPDP Consent · AI Gateway (mask + budget + log) · Process Engine · Event Bus · Model Registry.
**Extended (K·09–K·14):** Fairness · Drift · Explainability · Incident/rollback · Sandbox ·
Regulatory Mapping (signed evidence packs).

## Architecture: one core, swap everything else by config
**Hexagonal (ports & adapters).** Core imports zero concrete libraries. Onboard a customer = pick a
deployment mode + set adapters in config + load policy packs. **No core code is touched.**
Ports: `InferencePort` · `StoragePort` · `IdentityPort` · `WorkflowPort` · `HITLPort` · `ConsentPort` ·
`EventBusPort` (+ pluggable ledger signing).

## Three deployment tiers (same image)
| | Sovereign / air-gapped | Dedicated / customer VPC | SaaS shared |
|---|---|---|---|
| Hosts | customer hardware | customer cloud | QUAICU |
| Inference | Ollama / vLLM (local) | Vertex / Bedrock (private) | OpenAI / Anthropic / Vertex / Bedrock |
| Signing | OpenBao (Ed25519) | Cloud KMS HSM (ECDSA P-256) | Cloud KMS |
| Isolation | physical | one DB / tenant | schema-per-tenant + RLS |

## Three ways to integrate
1. **Python SDK** — `@kernel.guard(policy="credit.approve")` on an existing function; signature unchanged.
2. **REST API** — `POST /v1/...` from any language (auto OpenAPI docs).
3. **Docker** — `docker compose up`; governed in minutes.

## Why it wins
- **Offline-verifiable proof** — a regulator verifies the bundle without trusting QUAICU (the moat).
- **Neutral** — OpenAI / Azure / Anthropic / Vertex / Bedrock, all governed; no lock-in.
- **Sovereign** — customer-hosted, customer-held KMS; fits RBI/DPDP localization.
- **Turnkey regimes** — RBI FREE-AI / DPDP / EU AI Act policy packs ship in the box.

## Honest status
All 14 layers build and pass the suite; K·01–K·08 are the most exercised. The certs a regulated buyer
requires — **SOC 2, pen-test, K·02 crypto review, counsel-signed DPA/MSA** — are **in progress**
(Waves 2–3). Some managed cloud adapters are validated against fake clients, not live cloud (a pilot is
where they first run for real). See [`compliance/SECURITY_WHITEPAPER.md`](compliance/SECURITY_WHITEPAPER.md)
and [`compliance/COMPLIANCE_MATRIX.md`](compliance/COMPLIANCE_MATRIX.md).
