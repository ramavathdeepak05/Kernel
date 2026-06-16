# QUAICU Kernel — Enterprise Cloud Strategy (GCP-first, AWS at parity)

**Audience:** Product Owner, sales engineering, partner solution architects.
**Status:** Living document — 2026-06-16. Pairs with [ADR-0012](../adr/0012-cloud-native-adapters.md).
**Thesis:** Regulated institutions (Tier-1 banks, insurance, healthcare) will not self-host OpenBao,
Kafka, or Temporal — the operational overhead and the SOC2 / ISO 27001 / FedRAMP audit surface are
dealbreakers. Replacing those with **cloud-managed services** shifts the infra-compliance burden to
the cloud provider, lowers our support cost, and lets us spend cloud credits instead of payroll. The
kernel's hexagonal **ports/adapters** architecture (F-08) makes this a matter of writing new adapter
classes against existing ports — **no core rewrites** (one contained crypto change; see §2).

> **Scope of this pass:** two reference adapters are *implemented and tested* — the GCP Cloud KMS
> ledger signer and the Vertex AI inference adapter. Every other component below is *specified* with
> its target port, file path, and the design decisions needed to build it. Items marked
> **✅ shipped** are in the tree today; **◻ specified** are pick-up-and-build follow-ups.

---

## 1. Port → managed-service mapping

The kernel already exposes frozen ports; the registry (`delivery/sdk/kernel.py:_ADAPTER_REGISTRY`) is
the single wiring seam. Each row is a new adapter, selected by a TOML `[adapters]` key.

| Capability (port) | Current OSS stack | GCP managed (lead) | AWS parity | Compliance value | Status |
|---|---|---|---|---|---|
| Durable storage (`StoragePort`) | PostgreSQL (asyncpg) | **Cloud SQL / AlloyDB** | Aurora Serverless v2 | 100% code-compatible; multi-AZ failover, PITR; favored over self-managed DBs | ✅ works as-is |
| Ledger signing (`TreeSigner`) | OpenBao transit (Ed25519) | **Cloud KMS (ECDSA P-256)** | KMS (Ed25519 or ECDSA) | FIPS 140-2 L3 HSM; private key never extractable | ✅ **shipped** (`gcp_kms_ledger`) |
| Inference (`InferencePort`) | OpenAI-compat / Ollama | **Vertex AI (Gemini)** | Bedrock | Private inference, no public egress, no base-model training on data | ✅ **shipped** (`vertex_inference`) |
| PII masking (no port yet) | regex (`core/gateway/masking.py`) | **Cloud DLP API** | Comprehend / Macie | ML PII detection vs brittle regex; the compliance gold standard | ◻ specified (§3) |
| Erasure keyring (`ShredKeyring`) | `InMemoryShredKeyring` | **Cloud KMS envelope** | KMS envelope | Provable crypto-shred via HSM key destruction | ◻ specified (§2) |
| Event bus (`EventPort`/`EventBus`) | in-memory | **Pub/Sub** | EventBridge / MSK | Serverless fan-out to SIEM (Splunk/Chronicle), no Kafka cluster | ◻ specified (§6) |
| Durable workflows (`WorkflowPort`) | Postgres state-machine / Temporal | **Cloud Workflows** | Step Functions | Serverless `waitForTaskToken` HITL; zero compute while waiting | ◻ specified (§7) |
| Identity (`IdentityPort`) | OIDC JWKS / JWT | **Identity Platform** | Cognito | Federated SAML/OIDC to Okta/Azure AD/Ping | ✅ via existing `oidc` |
| Billing/metering | Stripe / Razorpay | **GCP Marketplace Metering** | AWS Marketplace Metering | Buy on cloud commit credits; zero procurement friction | ◻ specified (§5) |

---

## 2. Security & sovereignty — Cloud KMS

### Ledger signing (✅ shipped)
The K·02 TrustLedger signs Signed Tree Heads. The new `GcpKmsTreeSigner`
(`adapters/ledger/gcp_kms.py`) keeps the signing key in **Cloud KMS HSM** (FIPS 140-2 L3): the private
key is never in process memory and cannot be extracted even by an admin with project-owner access —
the standard sovereign-ledger mandate, met out of the box.

**Crypto decision (see ADR-0012):** GCP Cloud KMS has **no Ed25519** for asymmetric signing, so the
signer uses **ECDSA P-256** (`EC_SIGN_P256_SHA256`) — itself RFC 6962-conformant. The offline
regulator verifier (`core/regmap/export.py`) was made **algorithm-aware by public-key type** (no wire
tag, no storage migration), so a KMS-signed bundle verifies with the same code a regulator runs for an
Ed25519 bundle. **AWS parity:** AWS KMS *does* support Ed25519 (`ECC_NIST_EDWARDS25519`, since Nov
2025) — an AWS signer could be a drop-in for the existing Ed25519 scheme *or* use ECDSA. **Action:**
the pending K·02 external crypto review must now cover the ECDSA-P256 STH path.

### Crypto-shred erasure (◻ specified)
`core/erasure/engine.py` already implements per-subject DEK envelope encryption behind the
`ShredKeyring` protocol (`core/erasure/keyring.py`), today backed by `InMemoryShredKeyring`. Build a
`GcpKmsShredKeyring(ShredKeyring)`:
- `get_or_create(ref)` → KMS `GenerateDataKey`-equivalent (a per-subject/-tenant CryptoKey or wrapped
  DEK); store the *wrapped* DEK with the ciphertext.
- `get(key_id)` → KMS `Decrypt` to unwrap the DEK.
- `destroy(ref)` → `DestroyCryptoKeyVersion` (GCP) / `ScheduleKeyDeletion` (AWS) → **provable,
  HSM-backed erasure**. The existing `CipherToken` envelope and `SubjectErasedError` (410 Gone) flow
  are unchanged. **Difficulty: LOW** — the port exists; only the keyring backend changes.

---

## 3. PII masking upgrade — Cloud DLP / Comprehend (◻ specified)

Today `core/gateway/masking.py` is **concrete regex** (`mask_text`, `mask_payload`, `_DEFAULT_PATTERNS`
for EMAIL/PAN/AADHAAR/SSN/phone/credit-card) with **no port** — the one component not yet abstracted.
Regulators know regex is brittle against obfuscation, typos, and unstructured text.

**Plan:**
1. Introduce `MaskingPort` (a `core/gateway/` Protocol): `mask(text, ctx) -> str` and
   `mask_payload(payload, ctx) -> dict`, preserving the existing `MaskingContext` tokenization
   (stable `[MASKED:<uuid>]` tokens + rehydrate) so the rest of the Gateway is untouched.
2. Refactor the current regex implementation into the **default** adapter implementing `MaskingPort`
   (zero behavior change, no new dependency).
3. Add `CloudDLPMaskingAdapter` (GCP DLP `deidentify_content`) and an AWS `ComprehendMaskingAdapter`
   (`detect_pii_entities`). DLP is the industry compliance standard and understands *context* (a
   9-digit account number vs an SSN). Wire via `_build_gateway` (`delivery/sdk/kernel.py`) + a
   `masking` config key. **Difficulty: MODERATE** — requires the new port + Gateway refactor first.

Masking must still run **before** the `InferencePort` call (the port contract: it receives only
already-masked prompts), so a DLP miss never reaches Vertex/Bedrock.

---

## 4. Private inference / zero-egress topology

The single slide that closes a bank CISO: **prompts never touch the public internet and are never used
to train base models.** `VertexInferenceAdapter` (✅ shipped) routes to Vertex AI; `BedrockInferenceAdapter`
(◻ AWS parity) is the same `InferencePort` shape.

```
                 Customer GCP project (or ours, single-tenant)
   ┌─────────────────────────────────────────────────────────────────┐
   │  VPC (no public egress)                                           │
   │                                                                   │
   │   ┌──────────────┐     Private Service Connect      ┌──────────┐  │
   │   │ QUAICU Kernel │ ───────────────────────────────▶│ Vertex AI│  │
   │   │ (Cloud Run/GKE)│   (private endpoint, no NAT)    │ (Gemini) │  │
   │   └──────┬────────┘                                  └──────────┘  │
   │          │ private IP                                              │
   │   ┌──────▼────────┐   ┌───────────┐   ┌───────────┐               │
   │   │  Cloud SQL    │   │ Cloud KMS │   │  Cloud DLP│               │
   │   │ (PG, private) │   │  (HSM)    │   │ (de-id)   │               │
   │   └───────────────┘   └───────────┘   └───────────┘               │
   └─────────────────────────────────────────────────────────────────┘
        egress to api.openai.com  ✗ blocked by VPC-SC perimeter
```

- **GCP:** Private Service Connect (PSC) to Vertex; **VPC Service Controls** perimeter to block data
  exfiltration; CMEK on Cloud SQL/KMS.
- **AWS:** PrivateLink to Bedrock; VPC endpoints for KMS/S3; SCP guardrails.

---

## 5. Marketplace packaging & metering

Two SKUs, one codebase (the existing `TieredKernelProvider`, `delivery/sdk/provider.py`):

**Model A — SaaS shared plane (high margin).** Multi-tenant on **Cloud Run / GKE** (AWS: ECS Fargate /
EKS) + **Cloud SQL** with RLS tenant isolation (migration 004, `app.current_tenant`). We host on our
credits; bill via the marketplace metering API. Maps to `kernel.saas.toml` + `entrypoint_saas.py`.

**Model B — customer-hosted single-tenant (high ACV).** Packaged as **Terraform / Deployment Manager**
(◻ to author); the customer clicks "Deploy" and the kernel runs in *their* project using *their* KMS +
Vertex + Cloud SQL. They pay infra on cloud commit credits; we charge license. Bypasses ~90% of vendor
security questionnaires (we never hold their data). Maps to `kernel.gcp.toml` + the enterprise license
gate (`provider.for_enterprise`).

**Metering adapter (✅ scaffold shipped).** `adapters/billing/marketplace.py`
(`MarketplaceMeteringReporter`) reads each tenant's usage from any `UsageMeter` and reports the
**delta since last report** to the marketplace, best-effort. The cloud API call is an injected `send`
seam — `gcp_sender` (Service Control) / `aws_sender` (BatchMeterUsage) — lazy-SDK scaffolds to finish
against the real APIs. A scheduler (Cloud Scheduler / EventBridge / ARQ) calls `report_all(meter,
tenants)` periodically. The inbound *entitlement* half (tier changes) reuses the existing
`BillingEvent` → `BillingEngine` path, exactly like Stripe/Razorpay.

> **✅ Shared meter shipped:** `adapters/metering/redis_meter.py` (`RedisUsageMeter`) gives exact
> cross-worker/replica counts as a drop-in for the in-process meter — selected by
> `[metering].redis_url` / `REDIS_URL` (`delivery/sdk/metering_config.py`). The in-process meter
> remains the default (safe, never over-counts) for single-worker/dev.

---

## 6. Event fan-out — Pub/Sub / EventBridge (◻ specified)

`EventPort`/`EventBus` (`emit(action, entry)`) currently has the in-memory adapter. Add
`PubSubEventAdapter` (GCP) / `EventBridgeEventAdapter` (AWS) that publish the sealed `LedgerEntry` after
seal (K·07: emit is best-effort, after-seal, never rolls back). Fan out to SIEM (Chronicle/Splunk),
compliance loggers, and webhooks. Keep at-least-once + idempotent consumers (dedupe by event id).
**Difficulty: LOW** — single-method port.

---

## 7. HITL & durable workflows — Cloud Workflows / Step Functions (◻ specified)

`HITLPort` (`request_approval` + `poll`) has `InProcessHITLPort` (local `ApprovalStore` + `expires_at`
polling) and `WebhookHITLAdapter`. Add a `CloudWorkflowsHITLAdapter` (GCP) / `StepFunctionsHITLAdapter`
(AWS) using the **callback / `waitForTaskToken`** pattern: `request_approval` starts an execution that
pauses (up to a year, zero compute) and emails the approver (Cloud Tasks + SendGrid / SES); the
approver's click returns the task token and resumes; `poll` maps execution status →
`PENDING/APPROVED/REJECTED/TIMED_OUT`. Fail-closed: unreachable backend → `TIMED_OUT`. Approval state
lives on the cloud service, not the kernel. **Difficulty: LOW-MODERATE.**

`WorkflowPort` (`start`/`signal`/`state`) gets the analogous serverless adapter, replacing the need to
operate a Temporal cluster for the sovereign/MVP path.

---

## 8. Performance & HA

- **DB:** Cloud SQL/AlloyDB (Aurora Serverless v2) with bounded asyncpg pools per replica; size pools
  to `(max_connections / replicas)` with headroom; enable PITR. AlloyDB for read-heavy dashboard
  read-models.
- **HITL at scale:** serverless `waitForTaskToken`/Cloud Workflows means millions of concurrent
  *pending* approvals at zero idle compute — the key scaling win over polling.
- **KMS:** cache the public key (the signer already does) and the key-version resolution; one
  `asymmetric_sign` round-trip per governed action (a seal), not per request — acceptable latency.
- **Autoscaling:** Cloud Run min-instances for warm starts; HPA on GKE keyed on CPU + request
  concurrency. The kernel is HA-safe with `KERNEL_WORKERS > 1` when all correctness-critical state is
  durable (`kernel.prod.toml` / `kernel.gcp.toml`).
- **Credit utilization:** load-test Cloud SQL/AlloyDB under parallel HITL; run DLP/Comprehend at scale
  to tune the masking adapter; build the marketplace-metering integration test harness.

---

## 9. Identity federation (✅ via existing `oidc`)

Identity Platform (GCP) / Cognito (AWS) front the customer's enterprise IdP (Azure AD, Okta, Ping) via
SAML/OIDC and issue OIDC tokens the existing `adapters/identity/oidc.py` verifies (issuer + audience +
JWKS, fail-closed). `kernel.gcp.toml` wires `identity = "oidc"`. No new adapter required.

---

## 10. Build order (recommended)

1. ✅ Cloud KMS signer + algorithm-aware verifier (done) — the regulator-credibility anchor.
2. ✅ Vertex inference (done) — the AI-sovereignty demo.
3. ◻ `MaskingPort` + Cloud DLP adapter — closes the "regex is flawed" objection.
4. ✅ Marketplace metering reporter (scaffold) + shared Redis meter — unlocks cloud-credit billing;
   finish the cloud `send` seams + add a periodic scheduler.
5. ◻ KMS-envelope `ShredKeyring` — provable erasure for DPDP/GDPR.
6. ◻ Pub/Sub events + Cloud Workflows HITL — operational scale.
7. ◻ Terraform/Deployment Manager templates — the one-click customer-hosted SKU.

**Out of scope here (non-code):** K·02 external cryptographic review (now covering the ECDSA-P256 STH
path) and regulatory policy content packs.
