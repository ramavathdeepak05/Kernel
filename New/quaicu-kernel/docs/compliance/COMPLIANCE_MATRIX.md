# QUAICU Compliance Matrix — regime requirement → kernel layer → evidence

> **DRAFT — not legal advice / not a certification.** This maps common regulatory requirements to the
> **built** kernel layers and features that help satisfy them, and to the **evidence** QUAICU produces.
> QUAICU is an *enforcement + evidence control plane* — it enforces the policies **you** configure and
> emits tamper-evident proof; it does **not** by itself make you compliant, and inclusion here is not a
> statement of certification. Confirm applicability with your compliance team / counsel. Cross-refs:
> [`SECURITY_WHITEPAPER.md`](SECURITY_WHITEPAPER.md), [`CAIQ_SIG_ANSWERS.md`](CAIQ_SIG_ANSWERS.md),
> [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), the policy packs under
> [`../policy-packs/`](../policy-packs/), and the runnable
> [underwriting demo](../../examples/underwriting-demo/README.md).

## How to read this

Every governed action flows **propose → evaluate → gate → execute → seal → emit**, fail-closed at every
arrow. A regulator's question — *"what did the AI do, under which policy, approved by whom, and can you
prove it?"* — is answered by the **K·02 signed proof bundle** (`GET /v1/ledger/{tenant}/export`),
verifiable **offline** via `core.regmap.export.verify_ledger_proof_bundle`.

---

## A. Layer × capability (what each kernel layer enforces / evidences)

| Layer | Enforces | Evidence it produces |
|-------|----------|----------------------|
| **K·01 Policy Engine** | CEL rules per action; deny-overrides; fail-closed on error/empty | policy id + version sealed on the action |
| **K·02 TrustLedger** | append-only RFC-6962 Merkle log, per-tenant, HSM/KMS-signed | inclusion + consistency proofs; signed tree head; **offline-verifiable bundle** |
| **K·03 HITL Gate** | high-risk actions pause for a human; timeout → reject (never auto-approve) | approver identity sealed on the action (ADR-0007) |
| **K·04 Consent** | missing/expired/withdrawn consent → DENY at evaluate-time | consent state sealed, point-in-time resolvable on replay |
| **K·05 AI Gateway** | PII masking before transmission; per-tenant budget; prompt logging | masked-payload + model id/version on the sealed entry |
| **K·08 Model Registry** | per-tenant model allowlist; unapproved model → DENY | model id + version recorded per action |
| **K·14 Regulatory Mapping** | policy ↔ regulation links; point-in-time correctness | **signed evidence pack** (human + machine readable + proof refs) |
| **K·09–K·11 Assurance** | fairness / drift / explainability sweeps over sealed history | point-in-time explanations attached to audit replay |
| **K·12 Incident / K·13 Sandbox** | rollbacks as governed actions; what-if policy backtests | sealed incident actions; impact reports before activation |

---

## B. India — RBI FREE-AI (model-risk, ex-post accountability, human oversight)

Beachhead regime (`docs/strategy/MARKET_2026_2027.md`). Grounded in
[`../policy-packs/rbi/`](../policy-packs/rbi/README.md).

| RBI requirement (theme) | Kernel layer → built feature | Evidence |
|---|---|---|
| **Human accountability for AI-assisted decisions** | K·03 HITL gate — `require_approval` routes high-risk drafts to a named approver (`/v1/approvals`) | approver identity sealed on the action |
| **Model-risk management** | K·08 model registry (per-tenant allowlist) + K·10 drift sweeps over sealed history | model id/version per action; drift breach → K·12 incident |
| **Ex-post auditability** | K·02 ledger seal + `GET /v1/ledger/{tenant}/export` | offline-verifiable RFC-6962 proof bundle |
| **Payment-data localization** | K·01 pack `rbi-payment-data-localization` (deny if `data.store` outside India) | sealed DENY with `rbi.localization.payment_data` ref |
| **Encryption at rest** | K·01 pack `rbi-encryption-at-rest` | sealed decision + ref |
| **Material-outsourcing governance** (approval, right-to-audit, exit plan) | K·01 pack `rbi-material-outsourcing-approval` / `-audit-rights` / `-exit-plan` | sealed approval/deny with `rbi.outsourcing.*` refs |
| **Access logging** | K·01 pack `rbi-access-logging` (deny unlogged grant) | sealed decision + ref |

> Demonstrated by the [underwriting demo](../../examples/underwriting-demo/README.md): low-risk → allow
> → seal; high-risk → HITL approve → seal; over-limit → deny.

---

## C. India — DPDP Act 2023 (consent, purpose limitation, erasure, transfer)

Grounded in [`../policy-packs/dpdp/`](../policy-packs/dpdp/README.md). DPDP Rules notified Nov 2025,
full applicability ~May 2027 — **ahead of the cliff** is the selling point.

| DPDP requirement | Kernel layer → built feature | Evidence |
|---|---|---|
| **Consent before processing** | K·04 consent layer (evaluate-time DENY) + K·01 pack `dpdp-consent-required` | consent state sealed; DENY with `dpdp.consent.art.6` |
| **Purpose limitation** | K·01 pack `dpdp-purpose-limitation` (purpose ∉ permitted set → deny) | sealed decision + `dpdp.purpose.art.6` |
| **Data-principal erasure rights** | crypto-shred erasure (`core/erasure/`, HSM-backed `GcpKmsShredKeyring`, W6-4) + pack `dpdp-erased-subject` | provable destruction (DEK destroyed → unrecoverable) |
| **Data minimisation** | K·05 gateway PII masking before transmission (`MaskingPort`: regex / Cloud DLP) | masked payload on the sealed entry |
| **Cross-border transfer control** | K·01 pack `dpdp-cross-border-review` → `role:dpo` approval | sealed approval with `dpdp.transfer.art.16` |

---

## D. EU — AI Act (Regulation (EU) 2024/1689)

The **2027 expansion** wave (high-risk obligations ~Dec 2027 per the strategy memo). Grounded in
[`../policy-packs/eu-ai-act/`](../policy-packs/eu-ai-act/README.md).

| EU AI Act requirement | Kernel layer → built feature | Evidence |
|---|---|---|
| **Prohibited practices (Art. 5)** | K·01 pack `eu-ai-act-prohibited-risk` / `-prohibited-use` (deny) | sealed DENY with `prohibited.art.5` |
| **Human oversight for high-risk (Art. 14)** | K·01 pack `eu-ai-act-high-risk-oversight` → K·03 HITL approval | approver identity sealed; `oversight.art.14` |
| **Transparency / AI disclosure (Art. 50)** | K·01 packs `eu-ai-act-transparency-disclosure` / `-deepfake-labeling` | sealed review decision + `transparency.art.50` |
| **Lifetime event logging (high-risk)** | K·02 append-only per-tenant ledger | inclusion proofs over the full action history |
| **Point-in-time conformity evidence** | K·14 evidence packs (policies/regulations as they stood at action time) | signed evidence pack + proof refs |

---

## E. What QUAICU does **NOT** do (scope boundary)

- It does **not** certify you compliant, replace your DPIA/conformity assessment, or constitute legal
  advice. Policy packs are **starters** to adapt with counsel — you own whether a rule is correct for
  your licence category / risk classification.
- It does **not** classify your AI system's risk, write your model documentation, or detect
  prompt-injection — those are partner/OSS concerns per the strategy (`MARKET_2026_2027.md` §8).
- Assurance items that **gate** a regulated sale are tracked separately and are **in progress**, not
  complete: SOC 2 (W2-2), independent pen-test (W2-3), the K·02 third-party crypto review (W2-1), and a
  counsel-signed DPA/MSA (Waves 2–3). See [`SECURITY_WHITEPAPER.md`](SECURITY_WHITEPAPER.md) §7.
- Several managed adapters (Cloud DLP masking, HSM erasure keyring, Anthropic/Vertex/Bedrock gateway
  shims, AWS Step Functions) are validated against **fake clients, not live cloud APIs** — a design
  partner's pilot is where they first run against a real environment.
