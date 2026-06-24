# QUAICU Security Whitepaper

> **Audience:** CISO / security review / vendor risk. **Version 1.0 · June 2026.**
> A sales-engineering security overview to support a buyer's security review. It complements (does not
> replace) the operational [`SECURITY.md`](../../SECURITY.md) (posture + vulnerability disclosure +
> shared-responsibility) and the pre-answered [`CAIQ_SIG_ANSWERS.md`](CAIQ_SIG_ANSWERS.md). For the
> regulator-evidence mapping see [`COMPLIANCE_MATRIX.md`](COMPLIANCE_MATRIX.md); for architecture see
> [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

## 1. What QUAICU is (security framing)

QUAICU is a **fail-closed, model/cloud-neutral governance kernel** that sits between your AI and the
outside world. Every AI-driven action runs **propose → evaluate → gate → execute → seal → emit**; no
action reaches execution without passing policy (and, when required, a human), and every executed
action is sealed to a tamper-evident transparency log. The security value proposition is **non-
repudiation**: mathematical proof of what the AI did, under which policy, approved by whom — verifiable
offline, independent of QUAICU.

## 2. Threat model & trust boundaries

**Assets:** tenant policies, governed-action records (the ledger), personal/regulated data passing
through the gateway, signing keys, API credentials.

**Primary threats we design against:**
- **Unauthorized AI execution** — an agent taking a high-risk action without policy/human approval.
  → fail-closed lifecycle + no-bypass invariant (§3); HITL gate for high-risk actions.
- **Audit tampering / repudiation** — altering or denying what happened. → append-only RFC-6962 ledger
  with signed tree heads; offline verification (§4).
- **Cross-tenant data exposure.** → schema-per-tenant + RLS + connection isolation (§5).
- **PII leakage to model providers.** → masking before transmission at the gateway (§6).
- **Credential/edge abuse** — key theft, rate-limit evasion via spoofed client IP. → HMAC-peppered API
  keys; edge-secret-authenticated real-client-IP (§6, §8).

**Out of scope (shared responsibility):** vulnerabilities *within* third-party managed platforms
(their providers own those), the security of the customer's own agent/app, and prompt-injection
defense (a partner/OSS layer per the product strategy). See [`SECURITY.md`](../../SECURITY.md).

## 3. Core security invariants (testable, enforced every build)

These are automated test properties, not aspirations (see `ARCHITECTURE.md` → Security Guarantees):

| Invariant | Meaning |
|---|---|
| **Fail-closed** | any failure/timeout/error → DENY or HALT, never allow |
| **No bypass** | no code path reaches execute without evaluate (+ gate when required); even admin actions are governed |
| **Determinism** | same inputs → same decision (no wall-clock/randomness in evaluation) |
| **Total conflict resolution** | deny > require_approval > allow; policies never return "undefined" |
| **Tenant isolation** | nothing crosses a tenant boundary; adversarially tested |
| **Ledger immutability** | a sealed entry is never modified; proofs verify for the life of the product |
| **Idempotency** | re-submitting an action never double-executes/seals/emits |
| **Replay fidelity** | any action re-derivable from the ledger; replay causes no external effects |

## 4. Cryptographic design (the moat)

- **K·02 TrustLedger** is an **RFC 6962** Merkle transparency log (the Certificate-Transparency
  standard) — SHA-256 leaves/nodes with domain separation; inclusion + consistency proofs; **per-tenant
  tables, never a shared ledger** (Frozen Decision F-07).
- **Signed tree heads.** Each STH is signed by a pluggable signer: **Ed25519** (software / OpenBao
  transit, sovereign tier) or **ECDSA P-256** via **GCP Cloud KMS / AWS KMS** (HSM-rooted, FIPS).
- **Offline verification.** An exported proof bundle (`GET /v1/ledger/{tenant}/export`) embeds the
  signing public key; a regulator verifies inclusion proofs + the STH signature with
  `core.regmap.export.verify_ledger_proof_bundle` — **no kernel access, no network**. The signing
  algorithm is inferred from the key type, so a KMS-signed bundle verifies with the same offline code
  as the Ed25519 one. (Runnable: [underwriting demo](../../examples/underwriting-demo/README.md).)
- **Independent review.** A third-party cryptographic review of the ledger is **commissioned** and is a
  pre-bank-deployment gate (W2-1, `docs/operations/CRYPTO_REVIEW_RFQ.md`). We state this openly.

## 5. Tenant isolation

- **Schema-per-tenant** — each tenant gets its own schema and table set (not a shared `tenant_id`
  column). The ledger is *always* per-tenant.
- **Row-Level Security** as defense-in-depth even under schema-per-tenant — a mis-filtered query hits an
  empty set, never another tenant's data; `SET LOCAL app.current_tenant` per transaction.
- A path/tenant mismatch is a **403**, never a silent empty read. Cross-tenant scenarios are tested
  adversarially at every layer (Frozen Decision F-07; `quaicu-tenant-isolation`).

## 6. Data handling

- **PII masking before transmission** — the K·05 gateway masks via a swappable `MaskingPort` (regex
  default; managed Cloud DLP option) before a prompt leaves the tenant boundary; responses are
  rehydrated. An unlogged model call is a denied call.
- **Consent at decision-time** — K·04 denies on missing/expired/withdrawn consent and seals the consent
  state (point-in-time resolvable on replay).
- **Provable erasure** — crypto-shred (`core/erasure/`) with an HSM-backed KMS keyring: destroying a
  subject's wrapped DEK renders their data unrecoverable — evidence, not a promise.
- **Per-deployment data flow** — Sovereign (air-gapped, local inference), Dedicated (customer VPC, no
  egress, customer KMS), SaaS (schema-per-tenant + RLS). Residency: `docs/operations/DATA_RESIDENCY.md`.
- **Authentication** — API keys stored as **HMAC-SHA256 with a server-side pepper** (never blank in
  prod); OIDC verification for IdP deployments; bearer console sessions.

## 7. Key management & supply chain

- **Signing keys** live in OpenBao (sovereign) or Cloud KMS HSMs (dedicated/SaaS); customer-held KMS is
  supported for sovereignty. Rotation schedule + custody: `docs/operations/RETENTION_WORM_KEYROTATION.md`.
- **Secrets** resolve from the environment / Secret Manager at load (`${ENV}` placeholders in config —
  no secrets in files).
- **CI supply chain** — a **blocking** lint + unit-test gate, plus image scanning (Trivy), dependency
  audit (pip-audit), and a CycloneDX SBOM in **report mode** (graduating to blocking as the backlog
  clears). See `cloudbuild.yaml` + `docs/operations/VULN_MANAGEMENT.md`. (Image signing: not yet.)
- **Edge** — the Cloudflare Worker forwards a verified real client IP authenticated by a shared
  `X-Edge-Auth` secret, so rate-limiting can't be defeated by spoofing `X-Forwarded-For`.

## 8. Assurance roadmap (honest status)

These **gate** a regulated sale and are tracked on `ACTION_TRACKER.md` (Waves 2–3). Status as of
2026-06-25 (`docs/compliance/WAVE2_COMPLIANCE_CLOCKS.md`):

| Item | Status |
|---|---|
| K·02 independent crypto review (W2-1) | RFQ finalized — send-ready (longest pole) |
| SOC 2 Type I → Type II (W2-2) | Not started — start the clock |
| Independent penetration test (W2-3) | SoW drafted (`docs/compliance/PENTEST_SOW.md`) — book a firm |
| ISO 27001 (+27701) (W2-4) | Not started |
| GDPR Art.28 DPA + SCCs (W2-5 / W3-2) | Starter drafted (`docs/legal/DPA_ART28_STARTER.md`) — counsel to finalize |
| Enterprise MSA (W3-1) | Starter drafted — counsel to finalize |
| CAIQ / SIG | Pre-answered (`CAIQ_SIG_ANSWERS.md`) |
| Incident response + breach notification | Runbook (`docs/operations/INCIDENT_RESPONSE.md`; GDPR-72h / DPDP) |

**We don't overstate.** Where a control is in progress (the certs above) or validated against fake
clients rather than live cloud (some managed adapters), we say so — a design partner's pilot is where
those run against a real environment.

## 9. Quick reference for a security reviewer

- **Architecture & invariants:** [`ARCHITECTURE.md`](../../ARCHITECTURE.md)
- **Posture & vuln disclosure & shared responsibility:** [`SECURITY.md`](../../SECURITY.md)
- **Pre-answered questionnaire:** [`CAIQ_SIG_ANSWERS.md`](CAIQ_SIG_ANSWERS.md)
- **Regime → control mapping:** [`COMPLIANCE_MATRIX.md`](COMPLIANCE_MATRIX.md)
- **See it run (offline-verifiable proof):** [`examples/underwriting-demo/`](../../examples/underwriting-demo/README.md)
